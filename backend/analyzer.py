import logging
import time
import traceback
import pandas as pd
import numpy as np
from typing import Any

logger = logging.getLogger("datacruncher.analyzer")

JOB_STORE: dict[str, dict[str, Any]] = {}

CARDINALITY_THRESHOLD = 0.05
MIN_ROWS_FOR_CLUSTERING = 10_000


# ── Helpers ───────────────────────────────────────────────────────────────────

def _update(job_id: str, progress: float, message: str):
    JOB_STORE[job_id]["progress"] = progress
    JOB_STORE[job_id]["message"] = message
    # Briefly release the GIL so Flask HTTP threads can process status/results
    # requests without waiting for the full pandas stage to complete.
    time.sleep(0)


def _safe_join(series: pd.Series, sep: str = " | ", limit: int = 5) -> str:
    """Join unique non-null values from a series into a string — never raises."""
    try:
        vals = []
        for v in series.dropna().unique()[:limit]:
            try:
                s = str(v)
                if s not in ("nan", "None", ""):
                    vals.append(s)
            except Exception:
                pass
        return sep.join(vals) if vals else ""
    except Exception:
        return ""


def _safe_mode(series: pd.Series):
    """Return the most frequent non-null value — never raises."""
    try:
        clean = series.dropna()
        if clean.empty:
            return None
        mode = clean.mode()
        return mode.iloc[0] if not mode.empty else clean.iloc[0]
    except Exception:
        try:
            return series.dropna().iloc[0]
        except Exception:
            return None


def _apply_conditional_labels(df: pd.DataFrame, conditional_labels: list[dict], issues: list) -> pd.DataFrame:
    """Evaluate conditions on the grouped result and add computed label columns."""
    df = df.copy()
    for cl in conditional_labels:
        label_col  = cl.get("label_column", "Label")
        default    = cl.get("default_label", "")
        conditions = cl.get("conditions", [])
        df[label_col] = default
        for cond in conditions:
            col   = cond.get("column")
            op    = cond.get("op")
            val   = cond.get("value")
            label = cond.get("label", "")
            if not col or col not in df.columns:
                issues.append(f"Conditional label: column '{col}' not found")
                continue
            try:
                num = pd.to_numeric(df[col], errors="coerce")
                if   op == "gt":  mask = num > float(val)
                elif op == "lt":  mask = num < float(val)
                elif op == "gte": mask = num >= float(val)
                elif op == "lte": mask = num <= float(val)
                elif op == "eq":  mask = df[col].astype(str) == str(val)
                elif op == "neq": mask = df[col].astype(str) != str(val)
                else:
                    issues.append(f"Unknown op '{op}' in conditional label — skipped")
                    continue
                df.loc[mask, label_col] = label
            except Exception as e:
                issues.append(f"Conditional label on '{col}' ({op} '{val}'): {e}")
    return df


def _sanitize_df(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """
    Pre-clean the dataframe before analysis:
    - Replace +/-inf with NaN
    - Drop entirely-empty rows
    - Reset index
    Returns cleaned df and list of issue notes.
    """
    notes: list[str] = []
    df = df.copy()

    # Replace infinities in numeric columns
    try:
        num_cols = df.select_dtypes(include=[np.number]).columns
        if len(num_cols):
            inf_mask = df[num_cols].isin([np.inf, -np.inf])
            inf_count = int(inf_mask.sum().sum())
            if inf_count:
                df[num_cols] = df[num_cols].replace([np.inf, -np.inf], np.nan)
                notes.append(f"{inf_count} infinite value(s) replaced with NaN across numeric columns")
    except Exception as e:
        notes.append(f"Infinity scan skipped: {e}")

    # Drop rows that are entirely NaN
    try:
        all_null = df.isnull().all(axis=1)
        n_empty = int(all_null.sum())
        if n_empty:
            df = df[~all_null]
            notes.append(f"{n_empty} completely-empty row(s) removed")
    except Exception as e:
        notes.append(f"Empty-row removal skipped: {e}")

    df = df.reset_index(drop=True)
    return df, notes


# ── Main analysis ─────────────────────────────────────────────────────────────

def run_analysis(job_id: str, df: pd.DataFrame):
    data_issues: list[str] = []

    try:
        JOB_STORE[job_id]["status"] = "processing"
        original_count = len(df)

        # Sanitise
        _update(job_id, 0.03, "Sanitising data…")
        try:
            df, sanity_notes = _sanitize_df(df)
            data_issues.extend(sanity_notes)
        except Exception as e:
            data_issues.append(f"Sanitisation step failed: {e}")
        sanitized_count = len(df)

        # Store df_original early so /columns endpoint is usable during processing
        JOB_STORE[job_id]["df_original"] = df
        JOB_STORE[job_id]["original_count_snapshot"] = original_count

        # ── Stage 1: Exact deduplication ──────────────────────────────────────
        _update(job_id, 0.10, "Removing exact duplicates…")
        try:
            df_s1 = df.drop_duplicates().reset_index(drop=True)
            exact_removed = sanitized_count - len(df_s1)
        except Exception as e:
            data_issues.append(f"Exact deduplication skipped: {e}")
            df_s1 = df
            exact_removed = 0

        # ── Stage 2: Column profiling ──────────────────────────────────────────
        _update(job_id, 0.25, "Profiling columns…")
        n = len(df_s1)
        grouping_keys: list[str] = []
        numeric_cols: list[str] = []
        string_cols: list[str] = []
        col_info: list[dict] = []

        for col in df_s1.columns:
            try:
                ratio = df_s1[col].nunique() / n if n > 0 else 1.0
                dtype = df_s1[col].dtype

                if ratio <= CARDINALITY_THRESHOLD:
                    grouping_keys.append(col)
                    col_info.append({
                        "column": col,
                        "cardinality_ratio": round(ratio, 4),
                        "role": "grouping_key",
                        "reason": f"Only {round(ratio * 100, 2)}% unique values — categorical",
                    })
                elif pd.api.types.is_numeric_dtype(dtype):
                    numeric_cols.append(col)
                    col_info.append({
                        "column": col,
                        "cardinality_ratio": round(ratio, 4),
                        "role": "numeric_aggregate",
                        "reason": "Numeric with high cardinality — summed across groups",
                    })
                else:
                    string_cols.append(col)
                    col_info.append({
                        "column": col,
                        "cardinality_ratio": round(ratio, 4),
                        "role": "string_collapse",
                        "reason": "Text column — most frequent value retained per group",
                    })
            except Exception as e:
                data_issues.append(f"Column '{col}' skipped during profiling: {e}")

        # Fallback: no grouping keys found → pick the lowest-cardinality column
        if not grouping_keys and col_info:
            best = min(col_info, key=lambda x: x["cardinality_ratio"])
            best["role"] = "grouping_key"
            best["reason"] += " (auto-selected — no low-cardinality column found)"
            grouping_keys.append(best["column"])
            numeric_cols = [c for c in numeric_cols if c != best["column"]]
            string_cols = [c for c in string_cols if c != best["column"]]

        # ── Stage 3: Smart GroupBy compression ────────────────────────────────
        _update(job_id, 0.48, "Compressing groups…")
        try:
            df_s3, agg_info = _groupby_compress(df_s1, grouping_keys, numeric_cols, string_cols, data_issues)
        except Exception as e:
            logger.error(f"[{job_id}] GroupBy stage failed: {e}\n{traceback.format_exc()}")
            data_issues.append(f"GroupBy compression failed ({e}) — using deduplicated data as-is")
            df_s3 = df_s1.copy()
            df_s3["_record_count"] = 1
            agg_info = []

        # Publish stage-3 results immediately — frontend can show these while stages 4-5 run
        JOB_STORE[job_id]["df_result"] = df_s3
        JOB_STORE[job_id]["stages_complete"] = 3

        # ── Stage 4: String normalisation ─────────────────────────────────────
        _update(job_id, 0.70, "Normalising string columns…")
        try:
            df_s4, norm_info = _normalize_strings(df_s3, string_cols, data_issues)
        except Exception as e:
            logger.warning(f"[{job_id}] String normalisation failed: {e}")
            data_issues.append(f"String normalisation skipped: {e}")
            df_s4 = df_s3
            norm_info = []

        JOB_STORE[job_id]["df_result"] = df_s4
        JOB_STORE[job_id]["stages_complete"] = 4

        # ── Stage 5: Optional KMeans clustering ───────────────────────────────
        deep_compress_applied = False
        if len(df_s4) > MIN_ROWS_FOR_CLUSTERING and numeric_cols:
            _update(job_id, 0.83, "Applying numeric clustering…")
            try:
                df_s4 = _cluster_compress(df_s4, numeric_cols, grouping_keys, string_cols, data_issues)
                deep_compress_applied = True
                JOB_STORE[job_id]["df_result"] = df_s4
                JOB_STORE[job_id]["stages_complete"] = 5
            except Exception as e:
                logger.warning(f"[{job_id}] KMeans stage failed: {e}")
                data_issues.append(f"KMeans clustering skipped: {e}")

        _update(job_id, 0.96, "Finalising results…")
        compressed_count = len(df_s4)
        compression_ratio = round((1 - compressed_count / original_count) * 100, 2) if original_count else 0

        stages = [
            {"stage": "Original", "rows_before": original_count, "rows_after": original_count},
            {"stage": "Sanitisation", "rows_before": original_count, "rows_after": sanitized_count},
            {"stage": "Exact Deduplication", "rows_before": sanitized_count, "rows_after": len(df_s1)},
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
            "data_issues": data_issues,
        }

        JOB_STORE[job_id]["df_result"] = df_s4   # final (may already be set, kept in sync)
        JOB_STORE[job_id]["analysis"] = analysis
        JOB_STORE[job_id]["grouping_keys"] = grouping_keys
        JOB_STORE[job_id]["numeric_cols"] = numeric_cols
        JOB_STORE[job_id]["string_cols"] = string_cols
        JOB_STORE[job_id]["status"] = "complete"
        _update(job_id, 1.0, "Done")

    except Exception as exc:
        logger.error(f"[{job_id}] run_analysis crashed: {exc}\n{traceback.format_exc()}")
        JOB_STORE[job_id]["status"] = "error"
        JOB_STORE[job_id]["message"] = str(exc)
        JOB_STORE[job_id]["data_issues"] = data_issues


def run_reanalysis(job_id: str, grouping_keys: list[str], aggregations: dict[str, str], filters: list[dict], conditional_labels: list[dict] | None = None):
    data_issues: list[str] = []

    try:
        JOB_STORE[job_id]["status"] = "processing"
        _update(job_id, 0.10, "Applying filters…")

        df = JOB_STORE[job_id]["df_original"].copy()

        # Sanitise before re-analysis too
        try:
            df, sanity_notes = _sanitize_df(df)
            data_issues.extend(sanity_notes)
        except Exception as e:
            data_issues.append(f"Sanitisation skipped: {e}")

        # Apply user filters row-by-row with per-filter error recovery
        for f in filters:
            col = f.get("column")
            op = f.get("op")
            val = f.get("value")
            if not col or col not in df.columns:
                data_issues.append(f"Filter skipped — column '{col}' not found")
                continue
            try:
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
                else:
                    data_issues.append(f"Unknown filter operator '{op}' — skipped")
            except Exception as e:
                data_issues.append(f"Filter on '{col}' ({op} '{val}') skipped: {e}")

        _update(job_id, 0.35, "Compressing with custom grouping…")

        # Classify remaining columns
        numeric_cols: list[str] = []
        string_cols: list[str] = []
        for col in df.columns:
            if col in grouping_keys or col in aggregations:
                continue
            if pd.api.types.is_numeric_dtype(df[col].dtype):
                numeric_cols.append(col)
            else:
                string_cols.append(col)

        # Build aggregation map from user-specified methods
        agg_map: dict[str, Any] = {}
        for col, method in aggregations.items():
            if col not in df.columns or col in grouping_keys:
                continue
            try:
                if method in ("sum", "mean", "min", "max"):
                    agg_map[col] = method
                elif method == "most_frequent":
                    agg_map[col] = _safe_mode
                elif method == "concatenate":
                    agg_map[col] = _safe_join
                else:
                    data_issues.append(f"Unknown aggregation '{method}' for '{col}' — using most_frequent")
                    agg_map[col] = _safe_mode
            except Exception as e:
                data_issues.append(f"Aggregation setup for '{col}' failed: {e}")

        # Auto-fill columns not explicitly configured
        for col in numeric_cols:
            if col not in agg_map:
                agg_map[col] = "sum"
        for col in string_cols:
            if col not in agg_map:
                agg_map[col] = _safe_mode

        # Handle _record_count carry-forward
        if "_record_count" in df.columns:
            agg_map["_record_count"] = "sum"
        else:
            df["_record_count"] = 1
            agg_map["_record_count"] = "sum"

        if grouping_keys and agg_map:
            try:
                df_result = df.groupby(grouping_keys, as_index=False).agg(agg_map)
            except Exception as e:
                logger.error(f"[{job_id}] Custom groupby failed: {e}\n{traceback.format_exc()}")
                data_issues.append(f"Custom groupby failed ({e}) — returning filtered rows as-is")
                df_result = df
        else:
            df_result = df

        if conditional_labels:
            _update(job_id, 0.88, "Applying conditional labels…")
            try:
                df_result = _apply_conditional_labels(df_result, conditional_labels, data_issues)
            except Exception as e:
                data_issues.append(f"Conditional labels step failed: {e}")

        _update(job_id, 0.92, "Finalising custom results…")

        original_count = len(JOB_STORE[job_id]["df_original"])
        compressed_count = len(df_result)
        compression_ratio = round((1 - compressed_count / original_count) * 100, 2) if original_count else 0

        JOB_STORE[job_id]["df_result"] = df_result
        JOB_STORE[job_id]["analysis"]["compressed_count"] = compressed_count
        JOB_STORE[job_id]["analysis"]["compression_ratio"] = compression_ratio
        JOB_STORE[job_id]["analysis"]["data_issues"] = data_issues
        JOB_STORE[job_id]["status"] = "complete"
        _update(job_id, 1.0, "Done")

    except Exception as exc:
        logger.error(f"[{job_id}] run_reanalysis crashed: {exc}\n{traceback.format_exc()}")
        JOB_STORE[job_id]["status"] = "error"
        JOB_STORE[job_id]["message"] = str(exc)
        JOB_STORE[job_id]["data_issues"] = data_issues


# ── Stage helpers ─────────────────────────────────────────────────────────────

def _groupby_compress(
    df: pd.DataFrame,
    grouping_keys: list,
    numeric_cols: list,
    string_cols: list,
    issues: list,
) -> tuple[pd.DataFrame, list]:
    agg_map: dict[str, Any] = {}
    agg_info: list[dict] = []

    for col in numeric_cols:
        agg_map[col] = "sum"
        agg_info.append({"column": col, "method": "sum", "note": "Summed across grouped rows"})

    for col in string_cols:
        agg_map[col] = _safe_join

    if not grouping_keys:
        df = df.copy()
        df["_record_count"] = 1
        return df, agg_info

    df = df.copy()
    df["_record_count"] = 1
    agg_map["_record_count"] = "sum"

    try:
        df_result = df.groupby(grouping_keys, as_index=False, dropna=False).agg(agg_map)
    except Exception as e:
        issues.append(f"groupby with dropna=False failed ({e}), retrying with dropna=True")
        df_result = df.groupby(grouping_keys, as_index=False, dropna=True).agg(agg_map)

    return df_result, agg_info


def _normalize_strings(
    df: pd.DataFrame,
    string_cols: list,
    issues: list,
) -> tuple[pd.DataFrame, list]:
    norm_info: list[dict] = []
    df = df.copy()

    for col in string_cols:
        if col not in df.columns:
            continue
        try:
            def most_frequent_token(val):
                if val is None or (isinstance(val, float) and np.isnan(val)):
                    return val
                text = str(val)
                parts = [p.strip() for p in text.split("|") if p.strip()]
                if not parts:
                    return text
                freq: dict[str, int] = {}
                for p in parts:
                    freq[p] = freq.get(p, 0) + 1
                return max(freq, key=lambda k: freq[k])

            variants_col = f"{col}_variants"
            df[variants_col] = df[col].astype(str)
            df[col] = df[col].apply(most_frequent_token)
            norm_info.append({
                "column": col,
                "method": "most_frequent_token",
                "variants_column": variants_col,
                "note": "Dominant pipe-delimited token retained; originals stored in _variants column",
            })
        except Exception as e:
            issues.append(f"String normalisation for column '{col}' skipped: {e}")

    return df, norm_info


def _cluster_compress(
    df: pd.DataFrame,
    numeric_cols: list,
    grouping_keys: list,
    string_cols: list,
    issues: list,
) -> pd.DataFrame:
    from sklearn.cluster import MiniBatchKMeans
    from sklearn.preprocessing import StandardScaler

    available = [c for c in numeric_cols if c in df.columns]
    if not available:
        return df

    df = df.copy()
    X = df[available].fillna(0).values.astype(float)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    n_clusters = max(50, len(df) // 100)
    n_clusters = min(n_clusters, len(df))

    kmeans = MiniBatchKMeans(n_clusters=n_clusters, random_state=42, n_init=3)
    df["_cluster"] = kmeans.fit_predict(X_scaled)

    keys = grouping_keys + ["_cluster"]
    agg_map: dict[str, Any] = {"_record_count": "sum"}

    for col in available:
        agg_map[col] = "sum"

    for col in string_cols:
        if col in df.columns:
            agg_map[col] = _safe_mode

    for col in [c for c in df.columns if c.endswith("_variants")]:
        if col in df.columns:
            agg_map[col] = _safe_join

    try:
        df_clustered = df.groupby(keys, as_index=False, dropna=False).agg(agg_map)
    except Exception as e:
        issues.append(f"Cluster groupby with dropna=False failed ({e}), retrying")
        df_clustered = df.groupby(keys, as_index=False, dropna=True).agg(agg_map)

    if "_cluster" in df_clustered.columns:
        df_clustered = df_clustered.drop(columns=["_cluster"])
    return df_clustered
