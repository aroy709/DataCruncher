import io
import json
import uuid
from pathlib import Path

import pandas as pd
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from analyzer import JOB_STORE, run_analysis, run_reanalysis

app = FastAPI(title="DataCruncher API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


# ── Upload ─────────────────────────────────────────────────────────────────────

@app.post("/upload")
async def upload_file(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in {".csv", ".xlsx", ".xls", ".json"}:
        raise HTTPException(400, f"Unsupported file type: {ext}")

    job_id = str(uuid.uuid4())
    dest = UPLOAD_DIR / f"{job_id}{ext}"
    content = await file.read()
    dest.write_bytes(content)

    try:
        df = _parse_file(dest, ext)
    except Exception as exc:
        raise HTTPException(422, f"Could not parse file: {exc}")

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

    background_tasks.add_task(run_analysis, job_id, df)
    return {"job_id": job_id}


# ── Status ─────────────────────────────────────────────────────────────────────

@app.get("/status/{job_id}")
def get_status(job_id: str):
    job = _get_job(job_id)
    return {
        "status": job["status"],
        "progress": job["progress"],
        "message": job["message"],
    }


# ── Analysis explanation ───────────────────────────────────────────────────────

@app.get("/analysis/{job_id}")
def get_analysis(job_id: str):
    job = _get_job(job_id)
    if job["status"] != "complete":
        raise HTTPException(400, "Analysis not complete yet")
    return job["analysis"]


# ── Results (paginated) ────────────────────────────────────────────────────────

@app.get("/results/{job_id}")
def get_results(job_id: str, page: int = 1, limit: int = 100):
    job = _get_job(job_id)
    if job["status"] != "complete":
        raise HTTPException(400, "Results not ready yet")

    df: pd.DataFrame = job["df_result"]
    total = len(df)
    start = (page - 1) * limit
    end = start + limit
    page_df = df.iloc[start:end]

    # Replace NaN/inf with None for JSON safety
    page_df = page_df.replace({float("inf"): None, float("-inf"): None})
    page_df = page_df.where(page_df.notna(), other=None)

    return {
        "data": page_df.to_dict(orient="records"),
        "columns": list(df.columns),
        "total": total,
        "page": page,
        "limit": limit,
        "original_count": job["analysis"]["original_count"],
        "compressed_count": job["analysis"]["compressed_count"],
        "compression_ratio": job["analysis"]["compression_ratio"],
    }


# ── Re-analyse with custom config ─────────────────────────────────────────────

class ReanalyzeRequest(BaseModel):
    grouping_keys: list[str] = []
    aggregations: dict[str, str] = {}
    filters: list[dict] = []


@app.post("/reanalyze/{job_id}")
def reanalyze(job_id: str, req: ReanalyzeRequest, background_tasks: BackgroundTasks):
    job = _get_job(job_id)
    if job["df_original"] is None:
        raise HTTPException(400, "Original data not available")

    job["status"] = "queued"
    job["progress"] = 0.0
    job["message"] = "Queued for re-analysis…"

    background_tasks.add_task(
        run_reanalysis,
        job_id,
        req.grouping_keys,
        req.aggregations,
        req.filters,
    )
    return {"job_id": job_id, "status": "queued"}


# ── Export ─────────────────────────────────────────────────────────────────────

@app.get("/export/{job_id}")
def export_results(job_id: str, format: str = "csv"):
    job = _get_job(job_id)
    if job["status"] != "complete":
        raise HTTPException(400, "Results not ready yet")

    df: pd.DataFrame = job["df_result"]
    df = df.replace({float("inf"): None, float("-inf"): None})

    if format == "xlsx":
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Compressed")
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=compressed_{job_id}.xlsx"},
        )
    else:
        buf = io.StringIO()
        df.to_csv(buf, index=False)
        buf.seek(0)
        return StreamingResponse(
            io.BytesIO(buf.getvalue().encode()),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=compressed_{job_id}.csv"},
        )


# ── Column metadata (for CustomisePanel) ──────────────────────────────────────

@app.get("/columns/{job_id}")
def get_columns(job_id: str):
    job = _get_job(job_id)
    if job["df_original"] is None:
        raise HTTPException(400, "Data not available")
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
    return {
        "columns": cols,
        "current_grouping_keys": job.get("grouping_keys", []),
        "current_numeric_cols": job.get("numeric_cols", []),
        "current_string_cols": job.get("string_cols", []),
    }


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_job(job_id: str) -> dict:
    job = JOB_STORE.get(job_id)
    if job is None:
        raise HTTPException(404, f"Job {job_id} not found")
    return job


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
