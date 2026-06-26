import io
import json
import logging
import math
import time
import threading
import uuid
from pathlib import Path

import numpy as np
import pandas as pd
from flask import Flask, Response, jsonify, request, send_file
from flask_cors import CORS

from analyzer import JOB_STORE, run_analysis, run_reanalysis

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("datacruncher")

app = Flask(__name__)
CORS(app, origins=["http://localhost:5173", "http://127.0.0.1:5173"])

UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


# ── Upload ─────────────────────────────────────────────────────────────────────

@app.post("/upload")
def upload_file():
    t0 = time.perf_counter()
    if "file" not in request.files:
        return jsonify({"detail": "No file provided"}), 400

    file = request.files["file"]
    ext = Path(file.filename or "").suffix.lower()
    if ext not in {".csv", ".xlsx", ".xls", ".json"}:
        return jsonify({"detail": f"Unsupported file type: {ext}"}), 400

    job_id = str(uuid.uuid4())
    dest = UPLOAD_DIR / f"{job_id}{ext}"
    file.save(dest)

    try:
        df = _parse_file(dest, ext)
    except Exception as exc:
        logger.error(f"[{job_id}] File parse failed: {exc}")
        return jsonify({"detail": f"Could not parse file: {exc}"}), 422

    logger.info(
        f"[{job_id}] Uploaded {file.filename!r} "
        f"— {len(df):,} rows × {len(df.columns)} cols "
        f"in {(time.perf_counter()-t0)*1000:.0f}ms"
    )

    JOB_STORE[job_id] = {
        "status": "queued",
        "progress": 0.0,
        "message": "Queued…",
        "df_original": None,
        "df_result": None,
        "analysis": None,
        "grouping_keys": [],
        "numeric_cols": [],
        "string_cols": [],
    }

    threading.Thread(target=run_analysis, args=(job_id, df), daemon=True).start()
    return jsonify({"job_id": job_id})


# ── Status ─────────────────────────────────────────────────────────────────────

@app.get("/status/<job_id>")
def get_status(job_id):
    job, err = _get_job(job_id)
    if err:
        return err
    return jsonify({
        "status":          job["status"],
        "progress":        job["progress"],
        "message":         job["message"],
        "stages_complete": job.get("stages_complete", 0),
    })


# ── Analysis explanation ───────────────────────────────────────────────────────

@app.get("/analysis/<job_id>")
def get_analysis(job_id):
    job, err = _get_job(job_id)
    if err:
        return err
    if job["status"] != "complete":
        return jsonify({"detail": "Analysis not complete yet"}), 400
    return jsonify(job["analysis"])


# ── Results (paginated) ────────────────────────────────────────────────────────

@app.get("/results/<job_id>")
def get_results(job_id):
    t0 = time.perf_counter()
    job, err = _get_job(job_id)
    if err:
        return err

    # Available as soon as stage 3 (GroupBy) has published df_result
    df = job.get("df_result")
    if df is None:
        logger.info(f"[{job_id}] /results called but stage 3 not done yet")
        return jsonify({"detail": "Results not ready yet — waiting for stage 3"}), 400

    is_partial = job["status"] != "complete"

    try:
        page  = max(1, int(request.args.get("page",  1)))
        limit = max(1, min(500, int(request.args.get("limit", 100))))
    except (TypeError, ValueError):
        page, limit = 1, 100

    total = len(df)
    start = (page - 1) * limit
    end   = min(start + limit, total)

    t1 = time.perf_counter()
    page_df = df.iloc[start:end].copy()
    logger.info(f"[{job_id}] slice [{start}:{end}] of {total:,} rows took {(time.perf_counter()-t1)*1000:.1f}ms")

    # ── Clean: inf → NaN, then NaN → None ──────────────────────────────────────
    # Two-step so every cell is a JSON-safe value before serialisation.
    # Step 1: replace ±inf in numeric columns (to_json cannot encode inf)
    t2 = time.perf_counter()
    num_cols = page_df.select_dtypes(include=[np.number]).columns
    if len(num_cols):
        page_df[num_cols] = page_df[num_cols].replace([np.inf, -np.inf], np.nan)
    # Step 2: replace every remaining NaN (any dtype) with Python None.
    # pandas' to_json emits null for None; for float NaN in object-dtype columns
    # some pandas versions emit the bare token NaN which is invalid JSON.
    page_df = page_df.where(page_df.notna(), other=None)
    logger.info(f"[{job_id}] inf+nan clean took {(time.perf_counter()-t2)*1000:.1f}ms")

    # ── Serialise data with pandas' C-level JSON encoder ─────────────────────
    t3 = time.perf_counter()
    data_json_str = page_df.to_json(orient="records", date_format="iso", default_handler=str)
    logger.info(f"[{job_id}] to_json took {(time.perf_counter()-t3)*1000:.1f}ms")

    # ── Build meta ────────────────────────────────────────────────────────────
    if is_partial:
        original_count    = job.get("original_count_snapshot", total)
        compressed_count  = total
        compression_ratio = 0.0
    else:
        original_count    = job["analysis"]["original_count"]
        compressed_count  = job["analysis"]["compressed_count"]
        compression_ratio = job["analysis"]["compression_ratio"]

    # Use _to_py_num to ensure no numpy scalar or float('nan') reaches json.dumps —
    # Python's json module silently emits the bare token NaN for float('nan'),
    # which is invalid JSON and causes "Unexpected token N" in the browser.
    meta = json.dumps({
        "columns":           [str(c) for c in df.columns],
        "total":             int(total),
        "page":              int(page),
        "limit":             int(limit),
        "is_partial":        bool(is_partial),
        "original_count":    _to_py_num(original_count),
        "compressed_count":  _to_py_num(compressed_count),
        "compression_ratio": _to_py_num(compression_ratio),
    })
    # Splice pre-encoded data into the meta envelope (avoids json.loads round-trip)
    body = meta[:-1] + ', "data": ' + data_json_str + "}"

    logger.info(
        f"[{job_id}] /results page={page} total={total:,} partial={is_partial} "
        f"— {(time.perf_counter()-t0)*1000:.0f}ms total"
    )
    return Response(body, mimetype="application/json")


# ── Re-analyse with custom config ─────────────────────────────────────────────

@app.post("/reanalyze/<job_id>")
def reanalyze(job_id):
    job, err = _get_job(job_id)
    if err:
        return err
    if job["df_original"] is None:
        return jsonify({"detail": "Original data not available"}), 400

    body = request.get_json(force=True) or {}
    grouping_keys      = body.get("grouping_keys", [])
    aggregations       = body.get("aggregations", {})
    filters            = body.get("filters", [])
    conditional_labels = body.get("conditional_labels", [])

    logger.info(f"[{job_id}] Re-analysis requested — keys={grouping_keys} filters={len(filters)} cond_labels={len(conditional_labels)}")

    job["status"]   = "queued"
    job["progress"] = 0.0
    job["message"]  = "Queued for re-analysis…"

    threading.Thread(
        target=run_reanalysis,
        args=(job_id, grouping_keys, aggregations, filters, conditional_labels),
        daemon=True,
    ).start()
    return jsonify({"job_id": job_id, "status": "queued"})


# ── Export ─────────────────────────────────────────────────────────────────────

@app.get("/export/<job_id>")
def export_results(job_id):
    job, err = _get_job(job_id)
    if err:
        return err
    if job["status"] != "complete":
        return jsonify({"detail": "Results not ready yet"}), 400

    fmt = request.args.get("format", "csv")
    df  = job["df_result"].copy()
    num_cols = df.select_dtypes(include=[np.number]).columns
    if len(num_cols):
        df[num_cols] = df[num_cols].replace([np.inf, -np.inf], np.nan)
    df = df.where(df.notna(), other=None)

    logger.info(f"[{job_id}] Export requested format={fmt} rows={len(df):,}")

    if fmt == "xlsx":
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Compressed")
        buf.seek(0)
        return send_file(
            buf,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"compressed_{job_id}.xlsx",
        )
    else:
        buf = io.BytesIO(df.to_csv(index=False).encode())
        buf.seek(0)
        return send_file(
            buf,
            mimetype="text/csv",
            as_attachment=True,
            download_name=f"compressed_{job_id}.csv",
        )


# ── Column metadata (for CustomisePanel) ──────────────────────────────────────

@app.get("/columns/<job_id>")
def get_columns(job_id):
    job, err = _get_job(job_id)
    if err:
        return err
    if job["df_original"] is None:
        return jsonify({"detail": "Data not available — analysis still in early stages"}), 400

    t0 = time.perf_counter()
    df = job["df_original"]
    cols = []
    for col in df.columns:
        try:
            cols.append({
                "name":        col,
                "dtype":       str(df[col].dtype),
                "is_numeric":  pd.api.types.is_numeric_dtype(df[col].dtype),
                "unique_count": int(df[col].nunique()),
                "sample":      [str(v) for v in df[col].dropna().unique()[:5]],
            })
        except Exception as e:
            logger.warning(f"[{job_id}] Column metadata for '{col}' failed: {e}")

    logger.info(f"[{job_id}] /columns profiled {len(cols)} cols in {(time.perf_counter()-t0)*1000:.0f}ms")
    return jsonify({
        "columns":              cols,
        "current_grouping_keys": job.get("grouping_keys", []),
        "current_numeric_cols":  job.get("numeric_cols", []),
        "current_string_cols":   job.get("string_cols", []),
    })


# ── Helpers ────────────────────────────────────────────────────────────────────

def _to_py_num(v):
    """Convert any numpy scalar, NaN, or inf to a plain JSON-safe Python number.
    NaN / inf → 0 (never let them reach json.dumps which would write the bare token NaN).
    """
    if v is None:
        return 0
    try:
        if isinstance(v, (np.integer,)):
            return int(v)
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return 0
        return f if isinstance(v, (float, np.floating)) else int(f)
    except (TypeError, ValueError):
        return 0


def _get_job(job_id: str):
    job = JOB_STORE.get(job_id)
    if job is None:
        logger.warning(f"Job not found: {job_id}")
        return None, (jsonify({"detail": f"Job {job_id} not found"}), 404)
    return job, None


def _parse_file(path: Path, ext: str) -> pd.DataFrame:
    if ext == ".csv":
        return pd.read_csv(path, low_memory=False)
    elif ext in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    elif ext == ".json":
        with open(path) as f:
            raw = json.load(f)
        if isinstance(raw, list):
            return pd.DataFrame(raw)
        elif isinstance(raw, dict):
            return pd.DataFrame([raw])
        else:
            raise ValueError("JSON must be an array or object")
    raise ValueError(f"Unknown extension: {ext}")


if __name__ == "__main__":
    # threaded=True lets Flask handle concurrent requests (status polls + results fetch)
    # without each one blocking the others
    app.run(port=8000, debug=True, threaded=True)
