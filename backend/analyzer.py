import uuid
import pandas as pd
import numpy as np
from typing import Any

# In-memory store: job_id -> { status, progress, message, df_original, df_result, analysis }
JOB_STORE: dict[str, dict[str, Any]] = {}

CARDINALITY_THRESHOLD = 0.05  # columns with <= 5% unique ratio become grouping keys
MIN_ROWS_FOR_CLUSTERING = 10_000


def _update(job_id: str, progress: float, message: str):
    JOB_STORE[job_id]["progress"] = progress
    JOB_STORE[job_id]["message"] = message


def run_analysis(job_id: str, df: pd.DataFrame):
    try:
        JOB_STORE[job_id]["status"] = "processing"
        original_count = len(df)

        # ── Stage 1: Exact deduplication ──────────────────────────────────────
        _update(job_id, 0.05, "Removing exact duplicates…")
        df_s1 = df.drop_duplicates()
        exact_removed = original_count - len(df_s1)

        # ── Stage 2: Column profiling ──────────────────────────────────────────
        _update(job_id, 0.20, "Profiling columns…")
        n = len(df_s1)
        grouping_keys = []
        numeric_cols = []
        string_cols = []
        col_info = []

        for col in df_s1.columns:
            ratio = df_s1[col].nunique() / n if n > 0 else 1.0
            dtype = df_s1[col].dtype

            if ratio <= CARDINALITY_THRESHOLD:
                grouping_keys.append(col)
                col_info.append({
                    "column": col,
                    "cardinality_ratio": round(ratio, 4),
                    "role": "grouping_key",
                    "reason": f"Only {round(ratio*100, 2)}% unique values — categorical column",
                })
            elif pd.api.types.is_numeric_dtype(dtype):
                numeric_cols.append(col)
                col_info.append({
                    "column": col,
                    "cardinality_ratio": round(ratio, 4),
                    "role": "numeric_aggregate",
                    "reason": "Numeric column with high cardinality — will be summed & averaged",
                })
            else:
                string_cols.append(col)
                col_info.append({
                    "column": col,
                    "cardinality_ratio": round(ratio, 4),
                    "role": "string_collapse",
                    "reason": "String column — most frequent value retained, variants stored",
                })

        # Fallback: if no grouping keys found, pick lowest-cardinality column
        if not grouping_keys and len(df_s1.columns) > 0:
            best = min(col_info, key=lambda x: x["cardinality_ratio"])
            best["role"] = "grouping_key"
            best["reason"] += " (auto-selected as fallback grouping key)"
            grouping_keys.append(best["column"])
            if best["column"] in numeric_cols:
                numeric_cols.remove(best["column"])
            if best["column"] in string_cols:
                string_cols.remove(best["column"])

        # ── Stage 3: Smart GroupBy compression ────────────────────────────────
        _update(job_id, 0.45, "Compressing groups…")
        df_s3, agg_info = _groupby_compress(df_s1, grouping_keys, numeric_cols, string_cols)

        # ── Stage 4: String normalization ─────────────────────────────────────
        _update(job_id, 0.70, "Normalising string columns…")
        df_s4, norm_info = _normalize_strings(df_s3, string_cols, grouping_keys)

        # ── Stage 5: Optional KMeans clustering ───────────────────────────────
        deep_compress_applied = False
        if len(df_s4) > MIN_ROWS_FOR_CLUSTERING and numeric_cols:
            _update(job_id, 0.80, "Applying numeric clustering for deeper compression…")
            df_s4 = _cluster_compress(df_s4, numeric_cols, grouping_keys, string_cols)
            deep_compress_applied = True

        _update(job_id, 0.95, "Finalising results…")
        compressed_count = len(df_s4)
        compression_ratio = round((1 - compressed_count / original_count) * 100, 2) if original_count else 0

        stages = [
            {"stage": "Original", "rows_before": original_count, "rows_after": original_count},
            {"stage": "Exact Deduplication", "rows_before": original_count, "rows_after": len(df_s1)},
            {"stage": "GroupBy Compression", "rows_before": len(df_s1), "rows_after": len(df_s3)},
            {"stage": "String Normalisation", "rows_before": len(df_s3), "rows_after": len(df_s4)},
        ]
        if deep_compress_applied:
            stages.append({"stage": "KMeans Clustering", "rows_before": len(df_s4), "rows_after": compressed_count})

        analysis = {
            "grouping_keys": [c for c in col_info if c["role"] == "grouping_key"],
            "exact_duplicates_removed": exact_removed,
            "aggregations": agg_info,
            "string_normalizations": norm_info,
            "col_profiles": col_info,
            "stages": stages,
            "original_count": original_count,
            "compressed_count": compressed_count,
            "compression_ratio": compression_ratio,
            "deep_compress_applied": deep_compress_applied,
        }

        JOB_STORE[job_id]["df_original"] = df
        JOB_STORE[job_id]["df_result"] = df_s4
        JOB_STORE[job_id]["analysis"] = analysis
        JOB_STORE[job_id]["grouping_keys"] = grouping_keys
        JOB_STORE[job_id]["numeric_cols"] = numeric_cols
        JOB_STORE[job_id]["string_cols"] = string_cols
        JOB_STORE[job_id]["status"] = "complete"
        _update(job_id, 1.0, "Done")

    except Exception as exc:
        JOB_STORE[job_id]["status"] = "error"
        JOB_STORE[job_id]["message"] = str(exc)


def run_reanalysis(job_id: str, grouping_keys: list[str], aggregations: dict[str, str], filters: list[dict]):
    try:
        JOB_STORE[job_id]["status"] = "processing"
        _update(job_id, 0.10, "Applying filters…")

        df = JOB_STORE[job_id]["df_original"].copy()

        # Apply user filters
        for f in filters:
            col, op, val = f.get("column"), f.get("op"), f.get("value")
            if col not in df.columns:
                continue
            if op == "eq":
                df = df[df[col].astype(str) == str(val)]
            elif op == "neq":
                df = df[df[col].astype(str) != str(val)]
            elif op == "gt":
                df = df[pd.to_numeric(df[col], errors="coerce") > float(val)]
            elif op == "lt":
                df = df[pd.to_numeric(df[col], errors="coerce") < float(val)]
            elif op == "contains":
                df = df[df[col].astype(str).str.contains(str(val), case=False, na=False)]

        _update(job_id, 0.30, "Compressing with custom grouping…")

        # Derive numeric and string cols from what's left after grouping keys
        all_cols = [c for c in df.columns if c in df.columns]
        numeric_cols = []
        string_cols = []
        for col in all_cols:
            if col in grouping_keys:
                continue
            if col in aggregations:
                continue  # handled explicitly
            if pd.api.types.is_numeric_dtype(df[col].dtype):
                numeric_cols.append(col)
            else:
                string_cols.append(col)

        # Build custom agg map
        agg_map: dict[str, Any] = {}
        for col, method in aggregations.items():
            if col not in df.columns or col in grouping_keys:
                continue
            if method == "sum":
                agg_map[col] = "sum"
            elif method == "mean":
                agg_map[col] = "mean"
            elif method == "min":
                agg_map[col] = "min"
            elif method == "max":
                agg_map[col] = "max"
            elif method == "most_frequent":
                agg_map[col] = lambda s: s.mode().iloc[0] if not s.mode().empty else s.iloc[0]
            elif method == "concatenate":
                agg_map[col] = lambda s: " | ".join(s.astype(str).unique()[:10])

        # Auto-fill remaining cols
        for col in numeric_cols:
            if col not in agg_map:
                agg_map[col] = "sum"
        for col in string_cols:
            if col not in agg_map:
                agg_map[col] = lambda s: s.mode().iloc[0] if not s.mode().empty else s.iloc[0]

        if grouping_keys and agg_map:
            agg_map["_record_count"] = "sum" if "_record_count" in df.columns else None
            if agg_map.get("_record_count") is None:
                del agg_map["_record_count"]
                df["_record_count"] = 1
                agg_map["_record_count"] = "sum"
            df_result = df.groupby(grouping_keys, as_index=False).agg(agg_map)
        else:
            df["_record_count"] = 1
            df_result = df

        _update(job_id, 0.90, "Finalising custom results…")

        original_count = len(JOB_STORE[job_id]["df_original"])
        compressed_count = len(df_result)
        compression_ratio = round((1 - compressed_count / original_count) * 100, 2) if original_count else 0

        JOB_STORE[job_id]["df_result"] = df_result
        JOB_STORE[job_id]["analysis"]["compressed_count"] = compressed_count
        JOB_STORE[job_id]["analysis"]["compression_ratio"] = compression_ratio
        JOB_STORE[job_id]["status"] = "complete"
        _update(job_id, 1.0, "Done")

    except Exception as exc:
        JOB_STORE[job_id]["status"] = "error"
        JOB_STORE[job_id]["message"] = str(exc)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _groupby_compress(df: pd.DataFrame, grouping_keys: list, numeric_cols: list, string_cols: list):
    agg_map: dict[str, Any] = {}
    agg_info = []

    for col in numeric_cols:
        agg_map[f"{col}"] = "sum"
        agg_info.append({"column": col, "method": "sum", "note": "Numeric column summed across grouped rows"})

    for col in string_cols:
        agg_map[col] = lambda s: " | ".join(s.astype(str).unique()[:5])

    if not grouping_keys:
        df["_record_count"] = 1
        return df, agg_info

    df["_record_count"] = 1
    agg_map["_record_count"] = "sum"

    if agg_map:
        df_result = df.groupby(grouping_keys, as_index=False).agg(agg_map)
    else:
        df_result = df.groupby(grouping_keys, as_index=False).size().rename(columns={"size": "_record_count"})

    return df_result, agg_info


def _normalize_strings(df: pd.DataFrame, string_cols: list, grouping_keys: list):
    norm_info = []
    for col in string_cols:
        if col not in df.columns:
            continue
        # Parse pipe-delimited back into list, pick most frequent token
        def most_frequent(val):
            parts = [p.strip() for p in str(val).split("|")]
            freq = {}
            for p in parts:
                freq[p] = freq.get(p, 0) + 1
            return max(freq, key=freq.get)

        variants_col = f"{col}_variants"
        df[variants_col] = df[col]
        df[col] = df[col].apply(most_frequent)
        norm_info.append({
            "column": col,
            "method": "most_frequent",
            "variants_column": variants_col,
            "note": "Dominant value retained; original variants stored in _variants column",
        })
    return df, norm_info


def _cluster_compress(df: pd.DataFrame, numeric_cols: list, grouping_keys: list, string_cols: list):
    from sklearn.cluster import MiniBatchKMeans
    from sklearn.preprocessing import StandardScaler

    available = [c for c in numeric_cols if c in df.columns]
    if not available:
        return df

    X = df[available].fillna(0).values
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    n_clusters = max(50, len(df) // 100)
    n_clusters = min(n_clusters, len(df))

    kmeans = MiniBatchKMeans(n_clusters=n_clusters, random_state=42, n_init=3)
    df = df.copy()
    df["_cluster"] = kmeans.fit_predict(X_scaled)

    keys = grouping_keys + ["_cluster"]
    agg_map: dict[str, Any] = {"_record_count": "sum"}
    for col in available:
        agg_map[col] = "sum"
    for col in string_cols:
        if col in df.columns:
            agg_map[col] = lambda s: s.mode().iloc[0] if not s.mode().empty else s.iloc[0]
    variants_cols = [c for c in df.columns if c.endswith("_variants")]
    for col in variants_cols:
        agg_map[col] = lambda s: " | ".join(s.astype(str).unique()[:3])

    df_clustered = df.groupby(keys, as_index=False).agg(agg_map)
    df_clustered = df_clustered.drop(columns=["_cluster"])
    return df_clustered
