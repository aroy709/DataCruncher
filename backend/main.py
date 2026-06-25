import io
import json
import threading
import uuid
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS

from analyzer import JOB_STORE, run_analysis, run_reanalysis

app = Flask(__name__)
CORS(app, origins=["http://localhost:5173", "http://127.0.0.1:5173"])

UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


# ── Upload ─────────────────────────────────────────────────────────────────────

@app.post("/upload")
def upload_file():
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
        return jsonify({"detail": f"Could not parse file: {exc}"}), 422

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
        "status": job["status"],
        "progress": job["progress"],
        "message": job["message"],
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
    job, err = _get_job(job_id)
    if err:
        return err
    if job["status"] != "complete":
        return jsonify({"detail": "Results not ready yet"}), 400

    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 100))

    df: pd.DataFrame = job["df_result"]
    total = len(df)
    start = (page - 1) * limit
    page_df = df.iloc[start:start + limit]

    page_df = page_df.replace({float("inf"): None, float("-inf"): None})
    page_df = page_df.where(page_df.notna(), other=None)

    return jsonify({
        "data": page_df.to_dict(orient="records"),
        "columns": list(df.columns),
        "total": total,
        "page": page,
        "limit": limit,
        "original_count": job["analysis"]["original_count"],
        "compressed_count": job["analysis"]["compressed_count"],
        "compression_ratio": job["analysis"]["compression_ratio"],
    })


# ── Re-analyse with custom config ─────────────────────────────────────────────

@app.post("/reanalyze/<job_id>")
def reanalyze(job_id):
    job, err = _get_job(job_id)
    if err:
        return err
    if job["df_original"] is None:
        return jsonify({"detail": "Original data not available"}), 400

    body = request.get_json(force=True) or {}
    grouping_keys = body.get("grouping_keys", [])
    aggregations = body.get("aggregations", {})
    filters = body.get("filters", [])

    job["status"] = "queued"
    job["progress"] = 0.0
    job["message"] = "Queued for re-analysis…"

    threading.Thread(
        target=run_reanalysis,
        args=(job_id, grouping_keys, aggregations, filters),
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
    df: pd.DataFrame = job["df_result"]
    df = df.replace({float("inf"): None, float("-inf"): None})

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
        return jsonify({"detail": "Data not available"}), 400

    df: pd.DataFrame = job["df_original"]
    cols = []
    for col in df.columns:
        cols.append({
            "name": col,
            "dtype": str(df[col].dtype),
            "is_numeric": pd.api.types.is_numeric_dtype(df[col].dtype),
            "unique_count": int(df[col].nunique()),
            "sample": [str(v) for v in df[col].dropna().unique()[:5]],
        })
    return jsonify({
        "columns": cols,
        "current_grouping_keys": job.get("grouping_keys", []),
        "current_numeric_cols": job.get("numeric_cols", []),
        "current_string_cols": job.get("string_cols", []),
    })


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_job(job_id: str):
    job = JOB_STORE.get(job_id)
    if job is None:
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
    app.run(port=8000, debug=True)
