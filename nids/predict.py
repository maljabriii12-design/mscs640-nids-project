"""Inference on new traffic: the hidden test set, the dashboard and the CLI."""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .config import BENIGN, LABEL_COL, resolve
from .data import clean_frame
from .pipeline import BUNDLE_NAME

log = logging.getLogger(__name__)

CONTEXT_COLUMNS = ["Timestamp", "Src IP", "Src Port", "Dst IP", "Dst Port", "Protocol"]

# Analyst-facing severity, for triage order in the threat report
SEVERITY = {
    "Benign": "None",
    "Infilteration": "Critical",
    "Bot": "Critical",
    "SQL Injection": "Critical",
    "DDOS attack-HOIC": "High",
    "DDOS attack-LOIC-UDP": "High",
    "DDoS attacks-LOIC-HTTP": "High",
    "DoS attacks-Hulk": "High",
    "DoS attacks-GoldenEye": "High",
    "DoS attacks-Slowloris": "Medium",
    "DoS attacks-SlowHTTPTest": "Medium",
    "Brute Force -XSS": "High",
    "Brute Force -Web": "Medium",
    "FTP-BruteForce": "Medium",
    "SSH-Bruteforce": "Medium",
}
SEVERITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "None": 4}

# Closest MITRE ATT&CK technique per class, so an alert names the adversary behaviour
# (https://attack.mitre.org/techniques/<id>/). Infilteration flows in this dataset are
# mostly the internal scanning that follows the initial compromise, hence T1046.
ATTACK_TECHNIQUE = {
    "Bot": ("T1071", "Application Layer Protocol"),
    "DDOS attack-HOIC": ("T1499", "Endpoint Denial of Service"),
    "DDoS attacks-LOIC-HTTP": ("T1499", "Endpoint Denial of Service"),
    "DDOS attack-LOIC-UDP": ("T1498", "Network Denial of Service"),
    "DoS attacks-Hulk": ("T1499", "Endpoint Denial of Service"),
    "DoS attacks-GoldenEye": ("T1499", "Endpoint Denial of Service"),
    "DoS attacks-Slowloris": ("T1499", "Endpoint Denial of Service"),
    "DoS attacks-SlowHTTPTest": ("T1499", "Endpoint Denial of Service"),
    "FTP-BruteForce": ("T1110", "Brute Force"),
    "SSH-Bruteforce": ("T1110", "Brute Force"),
    "Brute Force -Web": ("T1110", "Brute Force"),
    "Brute Force -XSS": ("T1190", "Exploit Public-Facing Application"),
    "SQL Injection": ("T1190", "Exploit Public-Facing Application"),
    "Infilteration": ("T1046", "Network Service Discovery"),
}


@lru_cache(maxsize=2)
def load_bundle(path: str | None = None) -> dict:
    p = Path(path) if path else resolve("models") / BUNDLE_NAME
    if not p.exists():
        raise FileNotFoundError(f"model bundle {p} not found; run `python main.py train` first")
    return joblib.load(p)


def predict_frame(raw: pd.DataFrame, bundle: dict) -> pd.DataFrame:
    """Score raw CICFlowMeter rows (any column order, Label optional)."""
    raw = raw.copy()
    raw.columns = [str(c).strip() for c in raw.columns]
    if LABEL_COL in raw.columns:
        raw = raw.loc[raw[LABEL_COL].astype(str).str.strip() != LABEL_COL]
    clean = clean_frame(raw, keep_dst_port=bundle["keep_dst_port"])
    X = bundle["preprocessor"].transform(clean.drop(columns=[LABEL_COL], errors="ignore"))
    proba = bundle["model"].predict_proba(X)
    names = np.array(bundle["label_names"])
    pred_idx = proba.argmax(axis=1)

    out = pd.DataFrame(index=raw.index)
    for c in CONTEXT_COLUMNS:
        if c in raw.columns:
            col = raw[c]
            if c in ("Src Port", "Dst Port", "Protocol"):
                col = pd.to_numeric(col, errors="coerce").round().astype("Int64")
            out[c] = col.values
    out["Predicted"] = names[pred_idx]
    out["Confidence"] = proba[np.arange(len(proba)), pred_idx].round(4)
    out["P(attack)"] = (1.0 - proba[:, bundle["benign_index"]]).round(4)
    out["Malicious"] = out["Predicted"] != BENIGN
    out["Severity"] = out["Predicted"].map(SEVERITY).fillna("High")
    out["ATT&CK"] = out["Predicted"].map(lambda c: ATTACK_TECHNIQUE.get(c, ("", ""))[0])
    ae = bundle.get("autoencoder")
    if ae is not None:
        score = ae.score(X)
        out["Anomaly score"] = score.round(5)
        out["Anomalous"] = score > ae.threshold_
    if LABEL_COL in raw.columns:
        out["True label"] = raw[LABEL_COL].fillna("").astype(str).str.strip().values
    return out.reset_index(drop=True)


def predict_file(in_path: str | Path, out_path: str | Path, bundle: dict,
                 chunksize: int = 200_000) -> int:
    """Chunked scoring of an arbitrarily large CSV; writes Label predictions."""
    n = 0
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    reader = pd.read_csv(in_path, chunksize=chunksize, low_memory=False, skipinitialspace=True,
                         encoding_errors="replace")
    for i, chunk in enumerate(reader):
        res = predict_frame(chunk, bundle)
        res = res.rename(columns={"Predicted": LABEL_COL})
        res.to_csv(out_path, mode="w" if i == 0 else "a", header=(i == 0), index=False)
        n += len(res)
        log.info("scored %s rows", f"{n:,}")
    return n
