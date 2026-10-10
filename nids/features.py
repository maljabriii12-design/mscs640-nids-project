"""Phase 1b: preprocessing and feature selection.

``FlowPreprocessor`` is fitted on the training split only and then frozen
into the model bundle, so validation, test, the hidden leaderboard set and
dashboard uploads all go through exactly the same transformation:

1. Align columns to those seen in training (a missing column becomes NaN).
2. Impute NaN (which includes the former +/-Inf values) with the training median.
3. Clip every column to its training [1-q, q] quantile range, which bounds the
   heavy tails of rate and duration features.
4. Signed log transform ``sign(x) * log1p(|x|)``: flow sizes, durations and
   rates span many orders of magnitude, and the transform makes them usable by
   the neural network. Being monotone, it has no effect on tree splits.
5. Standardise (mean 0, std 1), for the MLP and autoencoder.

Feature selection runs in three stages, all on training data:

* **Constant / near-constant removal.** Several CICFlowMeter columns (the
  bulk-rate averages, ``Bwd PSH Flags``, ``Bwd URG Flags``...) are zero for
  every flow in this dataset.
* **Redundancy removal.** Of each group of columns with |Pearson r| above the
  threshold (computed after the log transform), only the most important one is
  kept. ``Subflow Fwd Pkts`` duplicates ``Tot Fwd Pkts``, for example.
* **Relevance ranking.** An ExtraTrees model with balanced class weights ranks
  the remaining columns by impurity importance, and the ``top_k`` best are
  kept. The ranking is saved and plotted for the paper.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.model_selection import train_test_split

from .config import LABEL_COL

log = logging.getLogger(__name__)


def signed_log1p(x: np.ndarray) -> np.ndarray:
    return np.sign(x) * np.log1p(np.abs(x))


def _stratified_subsample(X: pd.DataFrame, y: np.ndarray, n: int, seed: int):
    if len(X) <= n:
        return X, y
    counts = pd.Series(y).value_counts()
    if counts.min() < 2:  # stratify needs >= 2 per class
        idx = np.random.default_rng(seed).choice(len(X), n, replace=False)
        return X.iloc[idx], y[idx]
    Xs, _, ys, _ = train_test_split(X, y, train_size=n, stratify=y, random_state=seed)
    return Xs, ys


class FlowPreprocessor(BaseEstimator, TransformerMixin):
    def __init__(self, variance_threshold: float = 0.0, correlation_threshold: float = 0.98,
                 top_k: int | None = 40, clip_quantile: float = 0.9999,
                 rank_rows: int = 200_000, seed: int = 42):
        self.variance_threshold = variance_threshold
        self.correlation_threshold = correlation_threshold
        self.top_k = top_k
        self.clip_quantile = clip_quantile
        self.rank_rows = rank_rows
        self.seed = seed

    # -- helpers -----------------------------------------------------------
    def _base(self, X: pd.DataFrame, cols: list[str]) -> np.ndarray:
        """Align, impute, clip and log-transform; no scaling."""
        A = X.reindex(columns=cols).to_numpy(dtype=np.float64, copy=True)
        med = np.array([self.medians_[c] for c in cols])
        lo = np.array([self.clip_lo_[c] for c in cols])
        hi = np.array([self.clip_hi_[c] for c in cols])
        nan = np.isnan(A)
        if nan.any():
            A[nan] = np.take(med, np.nonzero(nan)[1])
        np.clip(A, lo, hi, out=A)
        return signed_log1p(A)

    # -- sklearn API ------------------------------------------------------
    def fit(self, X: pd.DataFrame, y=None):
        X = X.drop(columns=[LABEL_COL], errors="ignore")
        cols = list(X.columns)
        self.input_columns_ = cols
        self.report_: dict = {"n_input": len(cols)}

        q = self.clip_quantile
        arr = X.to_numpy(dtype=np.float64)
        self.medians_ = dict(zip(cols, np.nan_to_num(np.nanmedian(arr, axis=0), nan=0.0)))
        lo = np.nanquantile(arr, 1 - q, axis=0)
        hi = np.nanquantile(arr, q, axis=0)
        self.clip_lo_ = dict(zip(cols, np.nan_to_num(lo, nan=0.0)))
        self.clip_hi_ = dict(zip(cols, np.nan_to_num(hi, nan=0.0)))
        del arr

        Xs, ys = X, y
        if y is not None:
            Xs, ys = _stratified_subsample(X, np.asarray(y), self.rank_rows, self.seed)
        B = self._base(Xs, cols)

        # 1. constant / near-constant
        var = B.var(axis=0)
        keep = var > self.variance_threshold
        self.report_["constant_removed"] = [c for c, k in zip(cols, keep) if not k]
        cols = [c for c, k in zip(cols, keep) if k]
        B = B[:, keep]

        # Importance on the surviving columns (also used to break ties below)
        importances = None
        if ys is not None:
            et = ExtraTreesClassifier(n_estimators=100, max_features="sqrt", min_samples_leaf=2,
                                      class_weight="balanced", n_jobs=-1, random_state=self.seed)
            et.fit(B, ys)
            importances = dict(zip(cols, et.feature_importances_))

        # 2. redundancy: greedy, most important column first
        order = sorted(range(len(cols)), key=lambda j: -(importances or {}).get(cols[j], 0.0))
        corr = np.abs(np.corrcoef(B, rowvar=False))
        corr = np.nan_to_num(corr, nan=0.0)
        kept: list[int] = []
        removed_corr = {}
        for j in order:
            hit = next((k for k in kept if corr[j, k] > self.correlation_threshold), None)
            if hit is None:
                kept.append(j)
            else:
                removed_corr[cols[j]] = cols[hit]
        self.report_["correlated_removed"] = removed_corr
        cols = [cols[j] for j in kept]           # already ordered by importance

        # 3. relevance: keep top_k
        if self.top_k and len(cols) > self.top_k:
            self.report_["low_importance_removed"] = cols[self.top_k:]
            cols = cols[: self.top_k]
        self.selected_columns_ = cols
        self.feature_importances_ = {c: float((importances or {}).get(c, np.nan)) for c in cols}
        self.report_["n_selected"] = len(cols)

        Bsel = self._base(X, cols)
        self.mean_ = Bsel.mean(axis=0)
        std = Bsel.std(axis=0)
        self.std_ = np.where(std > 1e-12, std, 1.0)
        log.info("feature selection: %d -> %d columns", self.report_["n_input"], len(cols))
        return self

    def transform(self, X: pd.DataFrame) -> np.ndarray:
        missing = [c for c in self.selected_columns_ if c not in X.columns]
        if missing:
            log.warning("%d expected columns missing, imputing with training medians: %s",
                        len(missing), missing[:5])
        B = self._base(X, self.selected_columns_)
        return ((B - self.mean_) / self.std_).astype(np.float32)

    def get_feature_names_out(self, input_features=None):
        return np.array(self.selected_columns_)
