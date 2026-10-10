"""Phase 1c: class-imbalance handling.

Benign is about 83% of CSE-CIC-IDS2018 and the smallest attack classes
(SQL Injection, Brute Force -XSS) have fewer than 300 flows out of 16
million. Three measures, all applied to the **training split only** (the
validation and test splits keep their natural distribution, so the reported
scores stay honest):

* ``undersample_majority``: random under-sampling of Benign down to a cap.
* ``smote``: SMOTE (Chawla et al., 2002). For each minority class below the
  target size, synthetic flows are drawn on the line segment between a real
  flow and one of its k nearest same-class neighbours. It runs in the
  standardised log-feature space produced by ``FlowPreprocessor``, where
  Euclidean distance is meaningful.
* ``class_weights``: per-class loss weights ``(n_max / n_c) ** power``. With
  ``power = 1`` this is the classic "balanced" weighting; 0.5 (the default) is
  damped, so that once SMOTE has lifted the rare classes, Benign precision is
  not sacrificed entirely.

The SMOTE implementation is self-contained (NumPy + scikit-learn
NearestNeighbors) and follows the original algorithm, so the pipeline has no
hard dependency on imbalanced-learn.
"""
from __future__ import annotations

import logging

import numpy as np
from sklearn.neighbors import NearestNeighbors

log = logging.getLogger(__name__)


def undersample_majority(X: np.ndarray, y: np.ndarray, majority: int, cap: int | None,
                         seed: int) -> tuple[np.ndarray, np.ndarray]:
    if not cap:
        return X, y
    idx_major = np.flatnonzero(y == majority)
    if len(idx_major) <= cap:
        return X, y
    rng = np.random.default_rng(seed)
    keep_major = rng.choice(idx_major, cap, replace=False)
    keep = np.sort(np.concatenate([np.flatnonzero(y != majority), keep_major]))
    return X[keep], y[keep]


def smote(X: np.ndarray, y: np.ndarray, target: int, k: int = 5,
          seed: int = 42) -> tuple[np.ndarray, np.ndarray]:
    """Oversample every class with fewer than ``target`` rows up to ``target``."""
    rng = np.random.default_rng(seed)
    new_X, new_y = [X], [y]
    for cls in np.unique(y):
        Xc = X[y == cls]
        n = len(Xc)
        n_new = target - n
        if n_new <= 0:
            continue
        if n == 1:                       # nothing to interpolate with
            synth = np.repeat(Xc, n_new, axis=0)
        else:
            kk = min(k, n - 1)
            nn = NearestNeighbors(n_neighbors=kk + 1).fit(Xc)
            _, neigh = nn.kneighbors(Xc)  # column 0 is the point itself
            base = rng.integers(0, n, n_new)
            pick = neigh[base, rng.integers(1, kk + 1, n_new)]
            lam = rng.random((n_new, 1)).astype(X.dtype)
            synth = Xc[base] + lam * (Xc[pick] - Xc[base])
        new_X.append(synth.astype(X.dtype))
        new_y.append(np.full(n_new, cls, dtype=y.dtype))
        log.info("SMOTE class %s: %d -> %d", cls, n, target)
    return np.concatenate(new_X), np.concatenate(new_y)


def class_weights(y: np.ndarray, power: float = 0.5) -> dict[int, float]:
    classes, counts = np.unique(y, return_counts=True)
    raw = (counts.max() / counts) ** power
    # normalise so the average per-sample weight is 1
    mean_w = (raw * counts).sum() / counts.sum()
    return {int(c): float(w / mean_w) for c, w in zip(classes, raw)}


def sample_weights(y: np.ndarray, weights: dict[int, float]) -> np.ndarray:
    lut = np.zeros(int(y.max()) + 1, dtype=np.float64)
    for c, w in weights.items():
        lut[c] = w
    return lut[y]


def rebalance(X: np.ndarray, y: np.ndarray, cfg: dict, majority: int, seed: int):
    """Apply the configured strategy; returns X, y, sample_weight (or None)."""
    strategy = cfg["strategy"]
    before = {int(k): int(v) for k, v in zip(*np.unique(y, return_counts=True))}
    X, y = undersample_majority(X, y, majority, cfg.get("benign_train_cap"), seed)
    if "smote" in strategy:
        X, y = smote(X, y, cfg["smote_target"], cfg["smote_k"], seed)
    w = None
    if "weights" in strategy:
        w = sample_weights(y, class_weights(y, cfg["weight_power"]))
    after = {int(k): int(v) for k, v in zip(*np.unique(y, return_counts=True))}
    log.info("rebalance (%s): %s -> %s", strategy, before, after)
    perm = np.random.default_rng(seed).permutation(len(y))
    return X[perm], y[perm], (None if w is None else w[perm])
