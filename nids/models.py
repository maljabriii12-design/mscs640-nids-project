"""Phase 2: model zoo.

* **Random Forest**: the required baseline (Breiman, 2001).
* **Gradient-boosted trees**: XGBoost (Chen & Guestrin, 2016) when it is
  installed, otherwise scikit-learn's histogram GBDT, which uses the same
  histogram split-finding idea. Early stopping runs on the validation split.
* **MLP**: a feed-forward network (three ReLU layers, Adam, L2 penalty, early
  stopping) trained with class-weighted cross-entropy through
  ``sample_weight``.
* **Autoencoder**: an unsupervised anomaly detector trained to reconstruct
  Benign flows only. A flow is flagged when its reconstruction error exceeds
  a high quantile of Benign validation errors. It needs no attack labels, so
  it is the component that could catch an attack type that is absent from
  training (the zero-day scenario in the brief).
* **Soft-voting ensemble**: averages the class probabilities of the
  supervised models.

Every supervised model exposes ``predict_proba`` over the encoded classes
``0..K-1``, so evaluation and inference treat them all the same way.
"""
from __future__ import annotations

import logging
import warnings

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.exceptions import ConvergenceWarning
from sklearn.neural_network import MLPClassifier, MLPRegressor

log = logging.getLogger(__name__)

try:  # optional, preferred when available
    import xgboost as xgb  # type: ignore
    HAS_XGB = True
except Exception:  # pragma: no cover - depends on environment
    xgb = None
    HAS_XGB = False


def build_random_forest(p: dict, seed: int) -> RandomForestClassifier:
    return RandomForestClassifier(
        n_estimators=p["n_estimators"], max_depth=p["max_depth"],
        min_samples_leaf=p["min_samples_leaf"], max_features=p["max_features"],
        max_samples=p.get("max_samples"), bootstrap=True, n_jobs=-1, random_state=seed)


def fit_random_forest(p, X, y, w, Xv, yv, seed):
    model = build_random_forest(p, seed)
    model.fit(X, y, sample_weight=w)
    return model


def fit_gbdt(p, X, y, w, Xv, yv, seed):
    engine = p.get("engine", "auto")
    if engine == "xgboost" and not HAS_XGB:
        raise ImportError("gbdt.engine is 'xgboost' but xgboost is not installed")
    if HAS_XGB and engine in ("auto", "xgboost"):
        # XGBoost switches to a binary objective when y has two classes, and
        # "mlogloss" then fails; pick the matching eval metric.
        eval_metric = "logloss" if len(np.unique(y)) == 2 else "mlogloss"
        model = xgb.XGBClassifier(
            n_estimators=p["n_estimators"], learning_rate=p["learning_rate"],
            max_depth=p["max_depth"], reg_lambda=p["l2_regularization"],
            tree_method="hist", eval_metric=eval_metric, early_stopping_rounds=p["early_stopping_rounds"],
            subsample=0.8, colsample_bytree=0.8, n_jobs=-1, random_state=seed)
        model.fit(X, y, sample_weight=w, eval_set=[(Xv, yv)], verbose=False)
        model.engine_ = "xgboost"
        log.info("XGBoost stopped at %s rounds", getattr(model, "best_iteration", "?"))
    else:
        model = HistGradientBoostingClassifier(
            max_iter=p["n_estimators"], learning_rate=p["learning_rate"],
            max_depth=p["max_depth"], max_leaf_nodes=p["max_leaf_nodes"],
            l2_regularization=p["l2_regularization"], early_stopping=True,
            validation_fraction=0.1, n_iter_no_change=p["early_stopping_rounds"],
            random_state=seed)
        model.fit(X, y, sample_weight=w)
        model.engine_ = "sklearn-hist-gbdt"
        log.info("HistGBDT stopped at %d iterations", model.n_iter_)
    return model


def fit_mlp(p, X, y, w, Xv, yv, seed):
    model = MLPClassifier(
        hidden_layer_sizes=tuple(p["hidden_layer_sizes"]), activation="relu",
        solver="adam", alpha=p["alpha"], batch_size=p["batch_size"],
        learning_rate_init=p["learning_rate_init"], max_iter=p["max_iter"],
        early_stopping=True, validation_fraction=0.1,
        n_iter_no_change=p["n_iter_no_change"], random_state=seed)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConvergenceWarning)
        try:
            model.fit(X, y, sample_weight=w)
        except TypeError:  # scikit-learn < 1.7 has no sample_weight for MLP
            log.warning("this scikit-learn MLP has no sample_weight; training unweighted")
            model.fit(X, y)
    log.info("MLP trained for %d epochs", model.n_iter_)
    return model


class SoftVoteEnsemble:
    """Average of member probabilities (members must share the class encoding)."""

    def __init__(self, members: dict, weights: dict | None = None):
        self.members = members
        self.weights = weights or {k: 1.0 for k in members}

    def predict_proba(self, X):
        total = sum(self.weights.values())
        return sum(self.weights[k] * m.predict_proba(X) for k, m in self.members.items()) / total

    def predict(self, X):
        return self.predict_proba(X).argmax(axis=1)


class AutoencoderDetector:
    """Benign-only autoencoder; anomaly score = mean squared reconstruction error."""

    def __init__(self, hidden_layer_sizes=(32, 8, 32), max_iter=30, threshold_quantile=0.99,
                 seed=42):
        self.hidden_layer_sizes = tuple(hidden_layer_sizes)
        self.max_iter = max_iter
        self.threshold_quantile = threshold_quantile
        self.seed = seed

    def fit(self, X_benign: np.ndarray, X_benign_val: np.ndarray):
        self.net_ = MLPRegressor(hidden_layer_sizes=self.hidden_layer_sizes, activation="relu",
                                 solver="adam", batch_size=1024, max_iter=self.max_iter,
                                 early_stopping=True, n_iter_no_change=4, random_state=self.seed)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ConvergenceWarning)
            self.net_.fit(X_benign, X_benign)
        self.threshold_ = float(np.quantile(self.score(X_benign_val), self.threshold_quantile))
        return self

    def score(self, X: np.ndarray) -> np.ndarray:
        return np.mean((self.net_.predict(X) - X) ** 2, axis=1)

    def predict(self, X: np.ndarray) -> np.ndarray:
        return (self.score(X) > self.threshold_).astype(int)


TRAINERS = {
    "random_forest": fit_random_forest,
    "gbdt": fit_gbdt,
    "mlp": fit_mlp,
}

DISPLAY_NAMES = {
    "random_forest": "Random Forest",
    "gbdt": "XGBoost" if HAS_XGB else "Hist. GBDT",
    "mlp": "MLP",
    "ensemble": "Soft-vote ensemble",
}


class ClassBiasedModel:
    """Wraps a probabilistic classifier with per-class multiplicative weights.

    ``argmax(p)`` is the Bayes decision for accuracy, not for macro F1. With
    the weights ``w`` the decision becomes ``argmax(p * w)``. They are fitted
    by coordinate ascent on validation macro F1 (the test split is never
    used), which lets the model trade a little Benign recall for recall on
    the rare classes. Outputs are renormalised, so ``predict_proba`` remains a
    distribution.
    """

    def __init__(self, base, weights: np.ndarray):
        self.base = base
        self.weights = np.asarray(weights, dtype=np.float64)

    def predict_proba(self, X):
        p = self.base.predict_proba(X) * self.weights
        return p / p.sum(axis=1, keepdims=True)

    def predict(self, X):
        return self.predict_proba(X).argmax(axis=1)

    @staticmethod
    def fit_weights(proba_val: np.ndarray, y_val: np.ndarray, rounds: int = 3) -> np.ndarray:
        present = np.unique(y_val)
        k = proba_val.shape[1]
        grid = np.exp(np.linspace(np.log(0.05), np.log(20), 25))
        w = np.ones(k)
        y_val = np.asarray(y_val, dtype=np.int64)

        def score(wv):  # macro-F1 over classes present in y_val, via a bincount confusion matrix
            pred = (proba_val * wv).argmax(1)
            cm = np.bincount(y_val * k + pred, minlength=k * k).reshape(k, k)
            tp = np.diag(cm)[present].astype(float)
            denom = cm.sum(0)[present] + cm.sum(1)[present]
            return float(np.mean(np.where(denom > 0, 2 * tp / np.maximum(denom, 1), 0.0)))

        best = score(w)
        for _ in range(rounds):
            improved = False
            for c in present:
                for g in grid:
                    trial = w.copy()
                    trial[c] = g
                    s = score(trial)
                    if s > best + 1e-6:
                        best, w, improved = s, trial, True
            if not improved:
                break
        return w
