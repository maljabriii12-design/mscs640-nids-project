"""Synthetic flows with the exact CSE-CIC-IDS2018 schema, for smoke tests only.

These rows are **not** real traffic and must never be used to report
results. They exist so that the pipeline, the tests and the dashboard can run
end to end on a machine without the 6.4 GB dataset (CI, a TA's laptop before
downloading). The generator also reproduces the dataset's defects (``Infinity``
rates, NaNs, duplicate rows, a repeated header line, label overlap between web
attacks, Infilteration that resembles Benign) so the cleaning code is
exercised.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import LABELS

COLUMNS = [
    "Dst Port", "Protocol", "Timestamp", "Flow Duration", "Tot Fwd Pkts", "Tot Bwd Pkts",
    "TotLen Fwd Pkts", "TotLen Bwd Pkts", "Fwd Pkt Len Max", "Fwd Pkt Len Min",
    "Fwd Pkt Len Mean", "Fwd Pkt Len Std", "Bwd Pkt Len Max", "Bwd Pkt Len Min",
    "Bwd Pkt Len Mean", "Bwd Pkt Len Std", "Flow Byts/s", "Flow Pkts/s", "Flow IAT Mean",
    "Flow IAT Std", "Flow IAT Max", "Flow IAT Min", "Fwd IAT Tot", "Fwd IAT Mean",
    "Fwd IAT Std", "Fwd IAT Max", "Fwd IAT Min", "Bwd IAT Tot", "Bwd IAT Mean", "Bwd IAT Std",
    "Bwd IAT Max", "Bwd IAT Min", "Fwd PSH Flags", "Bwd PSH Flags", "Fwd URG Flags",
    "Bwd URG Flags", "Fwd Header Len", "Bwd Header Len", "Fwd Pkts/s", "Bwd Pkts/s",
    "Pkt Len Min", "Pkt Len Max", "Pkt Len Mean", "Pkt Len Std", "Pkt Len Var", "FIN Flag Cnt",
    "SYN Flag Cnt", "RST Flag Cnt", "PSH Flag Cnt", "ACK Flag Cnt", "URG Flag Cnt",
    "CWE Flag Count", "ECE Flag Cnt", "Down/Up Ratio", "Pkt Size Avg", "Fwd Seg Size Avg",
    "Bwd Seg Size Avg", "Fwd Byts/b Avg", "Fwd Pkts/b Avg", "Fwd Blk Rate Avg",
    "Bwd Byts/b Avg", "Bwd Pkts/b Avg", "Bwd Blk Rate Avg", "Subflow Fwd Pkts",
    "Subflow Fwd Byts", "Subflow Bwd Pkts", "Subflow Bwd Byts", "Init Fwd Win Byts",
    "Init Bwd Win Byts", "Fwd Act Data Pkts", "Fwd Seg Size Min", "Active Mean", "Active Std",
    "Active Max", "Active Min", "Idle Mean", "Idle Std", "Idle Max", "Idle Min", "Label",
]

# per-class generative profile:
# ports, protocol, log10 duration (us) mean/sd, fwd pkts lam, bwd pkts lam,
# fwd len mean, bwd len mean, init fwd win, PSH prob
PROFILES = {
    "Benign":                   ([53, 443, 80, 3389, 445, 0], 6, 5.0, 1.6, 6, 6, 120, 600, 8192, 0.4),
    "FTP-BruteForce":           ([21], 6, 0.5, 0.3, 1, 1, 0, 0, 26883, 0.0),
    "SSH-Bruteforce":           ([22], 6, 5.6, 0.4, 22, 32, 70, 90, 26883, 0.9),
    "DoS attacks-GoldenEye":    ([80], 6, 6.6, 0.4, 5, 4, 70, 900, 26883, 0.9),
    "DoS attacks-Slowloris":    ([80], 6, 7.0, 0.3, 3, 1, 50, 0, 26883, 0.6),
    "DoS attacks-Hulk":         ([80], 6, 4.0, 0.5, 3, 4, 120, 400, 225, 0.8),
    "DoS attacks-SlowHTTPTest": ([21], 6, 0.6, 0.3, 1, 1, 0, 0, 26883, 0.0),
    "DDoS attacks-LOIC-HTTP":   ([80], 6, 4.4, 0.6, 4, 3, 80, 300, 8192, 0.8),
    "DDOS attack-HOIC":         ([80], 6, 3.8, 0.4, 3, 3, 110, 0, 32738, 0.7),
    "DDOS attack-LOIC-UDP":     ([80], 17, 7.1, 0.1, 160, 140, 10, 10, -1, 0.0),
    "Brute Force -Web":         ([80], 6, 6.7, 0.5, 18, 16, 260, 900, 8192, 0.9),
    "Brute Force -XSS":         ([80], 6, 6.7, 0.5, 20, 17, 300, 950, 8192, 0.9),
    "SQL Injection":            ([80], 6, 6.5, 0.6, 12, 10, 330, 1200, 8192, 0.9),
    "Infilteration":            ([53, 443, 80, 445], 6, 5.1, 1.6, 6, 5, 130, 550, 8192, 0.4),
    "Bot":                      ([8080], 6, 4.2, 0.6, 2, 1, 160, 120, 237, 0.6),
}


def _flows(label: str, n: int, rng: np.random.Generator) -> pd.DataFrame:
    ports, proto, mu, sd, lf, lb, mlf, mlb, win, psh = PROFILES[label]
    dur = np.where(rng.random(n) < 0.03, 0.0, 10 ** rng.normal(mu, sd, n)).round()
    fwd = 1 + rng.poisson(lf, n)
    bwd = rng.poisson(lb, n)
    flen_mean = np.abs(rng.normal(mlf, 0.35 * mlf + 5, n))
    blen_mean = np.where(bwd > 0, np.abs(rng.normal(mlb, 0.35 * mlb + 5, n)), 0)
    flen_std = flen_mean * rng.uniform(0.0, 0.8, n)
    blen_std = blen_mean * rng.uniform(0.0, 0.8, n)
    tot_f, tot_b = fwd * flen_mean, bwd * blen_mean
    pkts = fwd + bwd
    secs = dur / 1e6
    with np.errstate(divide="ignore", invalid="ignore"):
        byts_s = (tot_f + tot_b) / secs           # Inf when duration is 0, as in the CSVs
        pkts_s = pkts / secs
        fwd_s, bwd_s = fwd / secs, bwd / secs
    iat_mean = dur / np.maximum(pkts - 1, 1)
    iat_std = iat_mean * rng.uniform(0.2, 1.5, n)
    idle = np.where(rng.random(n) < 0.2, dur * rng.uniform(0.2, 0.9, n), 0)
    active = np.where(idle > 0, dur * rng.uniform(0.0, 0.1, n), 0)
    plen_mean = (tot_f + tot_b) / pkts
    plen_std = np.sqrt((flen_std ** 2 + blen_std ** 2) / 2)
    d = {
        "Dst Port": rng.choice(ports, n),
        "Protocol": np.full(n, proto),
        "Timestamp": pd.Timestamp("2018-03-01 09:00:00")
                     + pd.to_timedelta(rng.integers(0, 8 * 3600, n), unit="s"),
        "Flow Duration": dur, "Tot Fwd Pkts": fwd, "Tot Bwd Pkts": bwd,
        "TotLen Fwd Pkts": tot_f.round(), "TotLen Bwd Pkts": tot_b.round(),
        "Fwd Pkt Len Max": (flen_mean + 2 * flen_std).round(), "Fwd Pkt Len Min": np.zeros(n),
        "Fwd Pkt Len Mean": flen_mean, "Fwd Pkt Len Std": flen_std,
        "Bwd Pkt Len Max": (blen_mean + 2 * blen_std).round(), "Bwd Pkt Len Min": np.zeros(n),
        "Bwd Pkt Len Mean": blen_mean, "Bwd Pkt Len Std": blen_std,
        "Flow Byts/s": byts_s, "Flow Pkts/s": pkts_s,
        "Flow IAT Mean": iat_mean, "Flow IAT Std": iat_std,
        "Flow IAT Max": iat_mean + 2 * iat_std, "Flow IAT Min": iat_mean * rng.uniform(0, .3, n),
        "Fwd IAT Tot": dur * rng.uniform(0.5, 1, n), "Fwd IAT Mean": iat_mean * 1.5,
        "Fwd IAT Std": iat_std * 1.2, "Fwd IAT Max": iat_mean * 3, "Fwd IAT Min": iat_mean * .2,
        "Bwd IAT Tot": dur * rng.uniform(0, 1, n), "Bwd IAT Mean": iat_mean * 1.7,
        "Bwd IAT Std": iat_std * 1.1, "Bwd IAT Max": iat_mean * 3.2, "Bwd IAT Min": iat_mean * .1,
        "Fwd PSH Flags": (rng.random(n) < psh * .1).astype(int), "Bwd PSH Flags": np.zeros(n),
        "Fwd URG Flags": np.zeros(n), "Bwd URG Flags": np.zeros(n),
        "Fwd Header Len": fwd * (20 if proto == 17 else 32), "Bwd Header Len": bwd * 32,
        "Fwd Pkts/s": fwd_s, "Bwd Pkts/s": bwd_s,
        "Pkt Len Min": np.zeros(n), "Pkt Len Max": np.maximum(flen_mean, blen_mean) * 2,
        "Pkt Len Mean": plen_mean, "Pkt Len Std": plen_std, "Pkt Len Var": plen_std ** 2,
        "FIN Flag Cnt": (rng.random(n) < .3).astype(int),
        "SYN Flag Cnt": (rng.random(n) < (.6 if label.startswith("FTP") else .1)).astype(int),
        "RST Flag Cnt": (rng.random(n) < .05).astype(int),
        "PSH Flag Cnt": (rng.random(n) < psh).astype(int),
        "ACK Flag Cnt": (rng.random(n) < .5).astype(int),
        "URG Flag Cnt": (rng.random(n) < .05).astype(int),
        "CWE Flag Count": np.zeros(n), "ECE Flag Cnt": (rng.random(n) < .05).astype(int),
        "Down/Up Ratio": (bwd / fwd).round(),
        "Pkt Size Avg": plen_mean * pkts / np.maximum(pkts - 1, 1),
        "Fwd Seg Size Avg": flen_mean, "Bwd Seg Size Avg": blen_mean,
        "Fwd Byts/b Avg": np.zeros(n), "Fwd Pkts/b Avg": np.zeros(n),
        "Fwd Blk Rate Avg": np.zeros(n), "Bwd Byts/b Avg": np.zeros(n),
        "Bwd Pkts/b Avg": np.zeros(n), "Bwd Blk Rate Avg": np.zeros(n),
        "Subflow Fwd Pkts": fwd, "Subflow Fwd Byts": tot_f.round(),
        "Subflow Bwd Pkts": bwd, "Subflow Bwd Byts": tot_b.round(),
        "Init Fwd Win Byts": np.where(rng.random(n) < .85, win, rng.choice([-1, 8192, 65535], n)),
        "Init Bwd Win Byts": rng.choice([-1, 0, 219, 26883, 65535], n),
        "Fwd Act Data Pkts": np.maximum(fwd - 1, 0), "Fwd Seg Size Min": np.full(n, 20 if proto == 6 else 8),
        "Active Mean": active, "Active Std": active * .1, "Active Max": active * 1.2,
        "Active Min": active * .8, "Idle Mean": idle, "Idle Std": idle * .1,
        "Idle Max": idle * 1.1, "Idle Min": idle * .9,
        "Label": np.full(n, label),
    }
    df = pd.DataFrame(d)[COLUMNS]
    nan_rows = rng.random(n) < 0.002
    df.loc[nan_rows, "Flow Byts/s"] = np.nan
    return df


def make_synthetic(out_dir: str | Path, n_benign: int = 60_000, n_attack: int = 3_000,
                   seed: int = 0, days: int = 2) -> list[Path]:
    """Write ``days`` CSVs; attacks split across days like the real capture."""
    rng = np.random.default_rng(seed)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    attacks = [l for l in LABELS if l != "Benign"]
    groups = [attacks[i::days] for i in range(days)]
    small = {"SQL Injection": 60, "Brute Force -XSS": 150, "Brute Force -Web": 300}
    paths = []
    for day, group in enumerate(groups):
        parts = [_flows("Benign", n_benign // days, rng)]
        for lab in group:
            parts.append(_flows(lab, min(n_attack, small.get(lab, n_attack)), rng))
        df = pd.concat(parts, ignore_index=True).sample(frac=1, random_state=seed + day)
        df = pd.concat([df, df.sample(frac=0.01, random_state=day)])   # duplicates
        p = out_dir / f"SYNTHETIC-Day{day + 1}_TrafficForML_CICFlowMeter.csv"
        # the real files spell infinite rates as "Infinity"
        for col in ("Flow Byts/s", "Flow Pkts/s", "Fwd Pkts/s", "Bwd Pkts/s"):
            v = df[col]
            df[col] = v.astype(object).where(~np.isinf(v), "Infinity")
        mid = len(df) // 2
        df.iloc[:mid].to_csv(p, index=False)
        with open(p, "a", encoding="utf-8") as fh:          # header repeated mid-file
            fh.write(",".join(COLUMNS) + "\n")
        df.iloc[mid:].to_csv(p, index=False, header=False, mode="a")
        paths.append(p)
    return paths
