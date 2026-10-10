"""Phase 1a: loading and cleaning the raw CICFlowMeter CSVs.

The ten daily files total roughly 16 million flows (the largest day is about
4 GB), so nothing here ever loads a whole file. Building the training sample
takes two streaming passes:

1. **Count** -- read only the ``Label`` column of every file and tally how
   many flows each class has across all days.
2. **Sample** -- read the files again in chunks, clean each chunk, and keep
   each row with probability ``min(1, cap / count[label])``. Benign is
   down-sampled to ``cap_benign`` and every attack is kept whole up to
   ``cap_attack``, so the rare classes (SQL Injection has under 100 flows) are
   never thrown away.

Cleaning handles the problems actually present in the files: repeated header
rows in the middle of a file, identifier columns that only exist on some days,
``Infinity``/``NaN`` in the rate features (``Flow Byts/s`` and ``Flow
Pkts/s`` divide by a zero duration), values outside ``float32`` range, exact
duplicate flows, and flows whose features are identical but whose labels
disagree.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from .config import BENIGN, ID_COLUMNS, LABEL_COL, LABELS

log = logging.getLogger(__name__)

F32_MAX = float(np.finfo(np.float32).max)


# ----------------------------------------------------------------------------
# Cleaning
# ----------------------------------------------------------------------------
def clean_frame(df: pd.DataFrame, keep_dst_port: bool = True,
                stats: dict | None = None) -> pd.DataFrame:
    """Clean one chunk of raw flows.

    Returns a frame of ``float32`` features (non-finite values set to NaN, to
    be imputed later by the fitted preprocessor) plus the ``Label`` column if
    the input had one. ``stats`` (optional) accumulates EDA counters.
    """
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    labels = None
    if LABEL_COL in df.columns:
        lab = df[LABEL_COL].fillna("").astype(str).str.strip()
        header_rows = (lab == LABEL_COL) | (lab == "")   # header repeated mid-file / blank
        if header_rows.any():
            df = df.loc[~header_rows]
            lab = lab.loc[~header_rows]
            if stats is not None:
                stats["repeated_header_rows"] = stats.get("repeated_header_rows", 0) + int(header_rows.sum())
        labels = lab

    drop = [c for c in ID_COLUMNS if c in df.columns]
    if not keep_dst_port and "Dst Port" in df.columns:
        drop.append("Dst Port")
    feats = df.drop(columns=drop + ([LABEL_COL] if labels is not None else []))

    feats = feats.apply(pd.to_numeric, errors="coerce")
    values = feats.to_numpy(dtype=np.float64, copy=True)

    if stats is not None:
        nan_mask = np.isnan(values)
        inf_mask = np.isinf(values)
        miss = stats.setdefault("missing_per_column", Counter())
        infs = stats.setdefault("infinite_per_column", Counter())
        for j, col in enumerate(feats.columns):
            n_nan, n_inf = int(nan_mask[:, j].sum()), int(inf_mask[:, j].sum())
            if n_nan:
                miss[col] += n_nan
            if n_inf:
                infs[col] += n_inf
        stats["rows_seen"] = stats.get("rows_seen", 0) + len(values)

    values[~np.isfinite(values)] = np.nan
    np.clip(values, -F32_MAX, F32_MAX, out=values)
    out = pd.DataFrame(values.astype(np.float32), columns=feats.columns, index=feats.index)
    if labels is not None:
        out[LABEL_COL] = labels.values
    return out


def drop_duplicate_flows(df: pd.DataFrame, policy: str = "drop",
                         keep_prob: dict[str, float] | None = None) -> tuple[pd.DataFrame, dict]:
    """Remove exact duplicates and resolve flows whose label is ambiguous.

    Two flows with identical feature vectors but different labels cannot be
    separated by any model that sees only these features. ``policy`` decides
    what happens to such a vector:

    * ``"drop"`` -- drop every copy (no label noise, but a class whose flows
      are all shared with another class disappears).
    * ``"majority"`` -- keep one copy, labelled with the class it most often
      carries in the *full* data. Counts in the sample are divided by each
      class's sampling probability (``keep_prob``) so that down-sampled Benign
      is not under-counted. This is the Bayes-optimal label for that vector.

    In CSE-CIC-IDS2018 nearly all ``FTP-BruteForce`` and
    ``DoS attacks-SlowHTTPTest`` flows share one feature vector, so ``"drop"``
    removes both classes while ``"majority"`` keeps the more frequent one.
    """
    if policy not in ("drop", "majority"):
        raise ValueError(f"unknown ambiguous-label policy {policy!r}")
    feat_cols = [c for c in df.columns if c != LABEL_COL]
    n0 = len(df)
    h = pd.util.hash_pandas_object(df[feat_cols], index=False).to_numpy()
    tmp = pd.DataFrame({"h": h, "y": df[LABEL_COL].to_numpy()})
    n_labels = tmp.groupby("h")["y"].nunique()
    ambiguous = set(n_labels.index[n_labels > 1])
    amb_mask = tmp["h"].isin(ambiguous).to_numpy()
    dup_mask = tmp.duplicated(["h", "y"]).to_numpy()
    keep = ~(amb_mask | dup_mask)
    resolved: dict[str, int] = {}
    if policy == "majority" and ambiguous:
        amb = tmp.loc[amb_mask].copy()
        amb["pos"] = np.flatnonzero(amb_mask)
        probs = keep_prob or {}
        amb["w"] = 1.0 / amb["y"].map(lambda y: probs.get(y, 1.0))   # estimated full-data count
        weight = amb.groupby(["h", "y"])["w"].sum().reset_index()
        winner = weight.sort_values("w", ascending=False).drop_duplicates("h")
        firsts = amb.drop_duplicates(["h", "y"]).merge(winner[["h", "y"]], on=["h", "y"])
        keep[firsts["pos"].to_numpy()] = True
        resolved = firsts["y"].value_counts().to_dict()
    out = df.loc[keep].reset_index(drop=True)
    info = {
        "policy": policy,
        "rows_before": int(n0),
        "exact_duplicates_removed": int((dup_mask & ~amb_mask).sum()),
        "ambiguous_label_rows_removed": int(amb_mask.sum()) - sum(resolved.values()),
        "ambiguous_vectors": len(ambiguous),
        "ambiguous_vectors_kept_by_label": {k: int(v) for k, v in resolved.items()},
        "rows_after": int(len(out)),
    }
    return out, info


# ----------------------------------------------------------------------------
# Streaming over the raw files
# ----------------------------------------------------------------------------
def list_raw_files(raw_dir: str | Path, pattern: str) -> list[Path]:
    raw_dir = Path(raw_dir)
    files = sorted(raw_dir.rglob(pattern))
    if not files:  # fall back to any CSV (e.g. a renamed file)
        files = sorted(raw_dir.rglob("*.csv"))
    # Never mix synthetic smoke-test files into a real run.
    if "synthetic" not in str(raw_dir).lower():
        files = [f for f in files if "synthetic" not in str(f).lower()]
    return files


def _read_chunks(path: Path, chunksize: int, **kw):
    return pd.read_csv(path, chunksize=chunksize, low_memory=False,
                       skipinitialspace=True, encoding_errors="replace", **kw)


def count_labels(files: list[Path], chunksize: int) -> dict[str, dict[str, int]]:
    """Pass 1: per-file label counts, reading only the Label column."""
    per_file: dict[str, dict[str, int]] = {}
    for path in files:
        counts: Counter = Counter()
        for chunk in _read_chunks(path, chunksize * 4,
                                  usecols=lambda c: str(c).strip() == LABEL_COL):
            lab = chunk.iloc[:, 0].astype(str).str.strip()
            counts.update(lab[lab != LABEL_COL].tolist())
        per_file[path.name] = dict(counts)
        log.info("counted %-55s %s", path.name, dict(counts))
    return per_file


def keep_probabilities(totals: dict[str, int], cap_benign: int, cap_attack: int) -> dict[str, float]:
    probs = {}
    for label, n in totals.items():
        cap = cap_benign if label == BENIGN else cap_attack
        probs[label] = 1.0 if n <= cap else cap / n
    return probs


def build_sample(files: list[Path], cfg: dict, seed: int) -> tuple[pd.DataFrame, dict]:
    """Run both passes and return the cleaned, de-duplicated sample plus an EDA summary."""
    dcfg = cfg["data"]
    rng = np.random.default_rng(seed)

    per_file = count_labels(files, dcfg["chunksize"])
    totals: Counter = Counter()
    for c in per_file.values():
        totals.update(c)
    unknown = sorted(set(totals) - set(LABELS))
    if unknown:
        log.warning("labels not in the documented list (kept as-is): %s", unknown)
    probs = keep_probabilities(totals, dcfg["cap_benign"], dcfg["cap_attack"])

    stats: dict = {}
    parts = []
    columns: list[str] | None = None
    for path in files:
        for chunk in _read_chunks(path, dcfg["chunksize"]):
            clean = clean_frame(chunk, keep_dst_port=dcfg["keep_dst_port"], stats=stats)
            if clean.empty:
                continue
            p = clean[LABEL_COL].map(probs).fillna(1.0).to_numpy()
            clean = clean.loc[rng.random(len(clean)) < p]
            if columns is None:
                columns = list(clean.columns)
            parts.append(clean)
        log.info("sampled %s", path.name)

    # Days differ slightly in their columns (one day carries extra ID columns,
    # already dropped); align everything on the union, label last.
    all_cols = list(dict.fromkeys(c for part in parts for c in part.columns if c != LABEL_COL))
    sample = pd.concat([p.reindex(columns=all_cols + [LABEL_COL]) for p in parts],
                       ignore_index=True)
    for c in all_cols:
        sample[c] = sample[c].astype(np.float32)

    dedup_info = {"skipped": True}
    if dcfg["drop_duplicates"]:
        sample, dedup_info = drop_duplicate_flows(
            sample, policy=dcfg.get("ambiguous_policy", "drop"), keep_prob=probs)

    summary = {
        "files": [p.name for p in files],
        "per_file_label_counts": per_file,
        "total_label_counts": dict(sorted(totals.items(), key=lambda kv: -kv[1])),
        "keep_probability": probs,
        "sample_label_counts": sample[LABEL_COL].value_counts().to_dict(),
        "rows_seen": stats.get("rows_seen", 0),
        "repeated_header_rows": stats.get("repeated_header_rows", 0),
        "missing_per_column": dict(stats.get("missing_per_column", {})),
        "infinite_per_column": dict(stats.get("infinite_per_column", {})),
        "deduplication": dedup_info,
        "n_feature_columns": len(all_cols),
    }
    return sample, summary


def read_flows(path_or_buffer, keep_dst_port: bool = True, chunksize: int | None = None):
    """Read a CSV of new traffic for inference.

    Returns a cleaned frame (or an iterator of cleaned chunks if
    ``chunksize`` is given). Rows are aligned with the input, minus repeated
    header rows.
    """
    if chunksize:
        return (clean_frame(c, keep_dst_port) for c in _read_chunks(path_or_buffer, chunksize))
    raw = pd.read_csv(path_or_buffer, low_memory=False, skipinitialspace=True,
                      encoding_errors="replace")
    return clean_frame(raw, keep_dst_port)


def save_summary(summary: dict, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, default=int)
