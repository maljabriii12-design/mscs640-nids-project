"""End-to-end orchestration: prepare -> train -> evaluate -> bundle."""
from __future__ import annotations

import json
import logging
import platform
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.model_selection import ParameterSampler, train_test_split
from sklearn.preprocessing import LabelEncoder

from . import evaluate as ev
from .config import BENIGN, LABEL_COL, resolve
from .data import build_sample, list_raw_files, save_summary
from .features import FlowPreprocessor
from .imbalance import rebalance
from .models import (DISPLAY_NAMES, TRAINERS, AutoencoderDetector, ClassBiasedModel,
                     SoftVoteEnsemble)

log = logging.getLogger(__name__)

BUNDLE_NAME = "nids_bundle.joblib"


# ----------------------------------------------------------------------------
# Phase 1: prepare
# ----------------------------------------------------------------------------
def prepare(cfg: dict) -> Path:
    paths = cfg["paths"]
    files = list_raw_files(resolve(paths["raw_dir"]), cfg["data"]["file_glob"])
    if not files:
        raise FileNotFoundError(
            f"No CSV files under {resolve(paths['raw_dir'])}. Run `python main.py download` "
            "or `python main.py synth` first.")
    log.info("found %d raw files", len(files))
    sample, summary = build_sample(files, cfg, cfg["seed"])
    out = resolve(paths["processed"])
    out.parent.mkdir(parents=True, exist_ok=True)
    sample.to_pickle(out)
    save_summary(summary, out.with_suffix(".summary.json"))
    log.info("saved %s rows to %s", f"{len(sample):,}", out)
    return out


# ----------------------------------------------------------------------------
# Phase 2: train
# ----------------------------------------------------------------------------
def split_three_way(y: np.ndarray, test_size: float, val_size: float, seed: int):
    """Stratified train/val/test indices; classes too small to split stay in train."""
    idx = np.arange(len(y))
    counts = pd.Series(y).value_counts()
    tiny = counts.index[counts < 6]
    tiny_mask = np.isin(y, tiny)
    rest = idx[~tiny_mask]
    tr, te = train_test_split(rest, test_size=test_size, stratify=y[rest], random_state=seed)
    tr, va = train_test_split(tr, test_size=val_size / (1 - test_size), stratify=y[tr],
                              random_state=seed)
    tr = np.concatenate([tr, idx[tiny_mask]])
    return np.sort(tr), np.sort(va), np.sort(te)


def tune_gbdt(cfg, X, y, w, Xv, yv, benign_idx, names, seed):
    from .models import fit_gbdt

    tcfg = cfg["tuning"]
    rng = np.random.default_rng(seed)
    if len(y) > tcfg["subsample"]:
        sel = rng.choice(len(y), tcfg["subsample"], replace=False)
        X, y, w = X[sel], y[sel], (None if w is None else w[sel])
    space = {
        "learning_rate": [0.03, 0.05, 0.1, 0.2],
        "max_depth": [6, 8, 10, 12],
        "max_leaf_nodes": [31, 63, 127, 255],
        "l2_regularization": [0.0, 0.5, 1.0, 5.0],
    }
    base = dict(cfg["models"]["gbdt"])
    trials = []
    for params in ParameterSampler(space, n_iter=tcfg["n_iter"], random_state=seed):
        p = {**base, **params}
        t0 = time.time()
        model = fit_gbdt(p, X, y, w, Xv, yv, seed)
        f1 = ev.compute_metrics(yv, model.predict_proba(Xv), names, benign_idx)["macro_f1"]
        trials.append({"params": params, "val_macro_f1": f1, "seconds": time.time() - t0})
        log.info("tuning %s -> val macro-F1 %.4f", params, f1)
    best = max(trials, key=lambda t: t["val_macro_f1"])
    return best["params"], trials


def _stratified_rows(df: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    """Small demo file: every class present, proportional otherwise."""
    if len(df) <= n:
        return df
    per = max(n // (2 * df[LABEL_COL].nunique()), 1)
    rng = np.random.default_rng(seed)
    picks = [rng.choice(idx, min(len(idx), per), replace=False)
             for idx in df.groupby(LABEL_COL).indices.values()]
    take = df.iloc[np.concatenate(picks)]
    rest = df.drop(take.index)
    fill = rest.sample(min(len(rest), n - len(take)), random_state=seed)
    return pd.concat([take, fill]).sample(frac=1, random_state=seed)


def train(cfg: dict) -> dict:
    seed = cfg["seed"]
    paths = cfg["paths"]
    data_path = resolve(paths["processed"])
    if not data_path.exists():
        raise FileNotFoundError(f"{data_path} not found; run `python main.py prepare` first")
    df = pd.read_pickle(data_path)
    summary_path = data_path.with_suffix(".summary.json")
    dataset = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    log.info("loaded %s flows, %d classes", f"{len(df):,}", df[LABEL_COL].nunique())

    enc = LabelEncoder().fit(df[LABEL_COL])
    names = list(enc.classes_)
    benign_idx = names.index(BENIGN) if BENIGN in names else 0
    y_all = enc.transform(df[LABEL_COL]).astype(np.int64)
    X_df = df.drop(columns=[LABEL_COL])

    tr, va, te = split_three_way(y_all, cfg["data"]["test_size"], cfg["data"]["val_size"], seed)
    log.info("split train/val/test = %d/%d/%d", len(tr), len(va), len(te))

    model_dir = resolve(paths["model_dir"])
    model_dir.mkdir(parents=True, exist_ok=True)
    demo = _stratified_rows(df.iloc[te], 5000, seed)
    demo.to_csv(model_dir / "demo_test_flows.csv", index=False)

    # --- preprocessing & feature selection (train only) -----------------
    fcfg = cfg["features"]
    pre = FlowPreprocessor(fcfg["variance_threshold"], fcfg["correlation_threshold"],
                           fcfg["top_k"], fcfg["clip_quantile"], seed=seed)
    pre.fit(X_df.iloc[tr], y_all[tr])
    Xtr, Xva, Xte = (pre.transform(X_df.iloc[i]) for i in (tr, va, te))
    ytr, yva, yte = y_all[tr], y_all[va], y_all[te]
    del df, X_df

    # --- imbalance (train only) -------------------------------------------
    Xb, yb, wb = rebalance(Xtr, ytr, cfg["imbalance"], benign_idx, seed)

    results: dict = {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "labels": names,
        "split_sizes": {"train": int(len(tr)), "val": int(len(va)), "test": int(len(te)),
                        "train_after_rebalance": int(len(yb))},
        "train_class_counts_after_rebalance": {names[c]: int(n) for c, n in
                                               zip(*np.unique(yb, return_counts=True))},
        "features": {**pre.report_, "selected": pre.selected_columns_,
                     "importances": pre.feature_importances_},
        "dataset": dataset,
        "data_note": cfg.get("data_note", ""),
        "models": {},
    }

    mcfg = cfg["models"]
    if cfg["tuning"]["enabled"] and mcfg["gbdt"]["enabled"]:
        best_params, trials = tune_gbdt(cfg, Xb, yb, wb, Xva, yva, benign_idx, names, seed)
        mcfg["gbdt"].update(best_params)
        results["tuning"] = {"best_params": best_params, "trials": trials}

    fitted = {}
    for key, trainer in TRAINERS.items():
        if not mcfg[key]["enabled"]:
            continue
        log.info("training %s ...", key)
        t0 = time.time()
        model = trainer(mcfg[key], Xb, yb, wb, Xva, yva, seed)
        secs = time.time() - t0
        fitted[key] = model
        display = DISPLAY_NAMES[key]
        if key == "gbdt":
            display = "XGBoost" if getattr(model, "engine_", "") == "xgboost" else "Hist. GBDT"
        results["models"][key] = {
            "display_name": display,
            "train_seconds": secs,
            "val": ev.compute_metrics(yva, model.predict_proba(Xva), names, benign_idx),
            "test": ev.compute_metrics(yte, model.predict_proba(Xte), names, benign_idx),
        }
        log.info("%s: val macro-F1 %.4f | test macro-F1 %.4f (%.0fs)", display,
                 results["models"][key]["val"]["macro_f1"],
                 results["models"][key]["test"]["macro_f1"], secs)

    if mcfg["ensemble"]["enabled"] and len(fitted) >= 2:
        ens = SoftVoteEnsemble(dict(fitted))
        fitted["ensemble"] = ens
        results["models"]["ensemble"] = {
            "display_name": DISPLAY_NAMES["ensemble"],
            "train_seconds": sum(r["train_seconds"] for r in results["models"].values()),
            "val": ev.compute_metrics(yva, ens.predict_proba(Xva), names, benign_idx),
            "test": ev.compute_metrics(yte, ens.predict_proba(Xte), names, benign_idx),
        }

    # Decision-rule tuning: per-class weights fitted on validation macro-F1
    if cfg.get("decision", {}).get("class_bias_tuning", True):
        for key in list(fitted):
            model = fitted[key]
            w = ClassBiasedModel.fit_weights(model.predict_proba(Xva), yva)
            if np.allclose(w, 1.0):
                continue
            tuned = ClassBiasedModel(model, w)
            tkey = f"{key}_biased"
            fitted[tkey] = tuned
            results["models"][tkey] = {
                "display_name": results["models"][key]["display_name"] + " + class bias",
                "train_seconds": results["models"][key]["train_seconds"],
                "class_weights": {names[i]: float(v) for i, v in enumerate(w)},
                "val": ev.compute_metrics(yva, tuned.predict_proba(Xva), names, benign_idx),
                "test": ev.compute_metrics(yte, tuned.predict_proba(Xte), names, benign_idx),
            }

    # Model selection uses validation macro-F1 only; the test split is never consulted.
    best = max(results["models"], key=lambda k: results["models"][k]["val"]["macro_f1"])
    results["best_model"] = best
    log.info("best model on validation: %s", best)
    best_model = fitted[best]

    # --- unsupervised autoencoder ----------------------------------------
    ae = None
    acfg = mcfg["autoencoder"]
    if acfg["enabled"]:
        rng = np.random.default_rng(seed)
        ben_tr = Xtr[ytr == benign_idx]
        if len(ben_tr) > acfg["benign_fit_rows"]:
            ben_tr = ben_tr[rng.choice(len(ben_tr), acfg["benign_fit_rows"], replace=False)]
        ae = AutoencoderDetector(acfg["hidden_layer_sizes"], acfg["max_iter"],
                                 acfg["threshold_quantile"], seed)
        ae.fit(ben_tr, Xva[yva == benign_idx])
        s = ae.score(Xte)
        t_att = yte != benign_idx
        flag = s > ae.threshold_
        from sklearn.metrics import roc_auc_score
        results["autoencoder"] = {
            "threshold": ae.threshold_,
            "detection_rate": float(flag[t_att].mean()) if t_att.any() else 0.0,
            "false_positive_rate": float(flag[~t_att].mean()),
            "roc_auc": float(roc_auc_score(t_att, s)) if 0 < t_att.sum() < len(t_att) else float("nan"),
            "per_class_detection": {names[c]: float(flag[yte == c].mean())
                                    for c in np.unique(yte) if c != benign_idx},
        }
        ev.plot_autoencoder(s[~t_att], s[t_att], ae.threshold_,
                            resolve(paths["paper_figures"]) / "autoencoder_scores.png")

    # --- figures & tables --------------------------------------------------
    fig_dir = resolve(paths["paper_figures"])
    proba_te = best_model.predict_proba(Xte)
    title = results["models"][best]["display_name"]
    ev.plot_confusion(yte, proba_te.argmax(1), names, fig_dir / "confusion_matrix.png",
                      f"{title}: test set, row-normalised")
    ev.plot_roc(yte, proba_te, names, benign_idx, fig_dir / "roc_curves.png")
    ev.plot_feature_importance(pre.feature_importances_, fig_dir / "feature_importance.png")
    if dataset.get("total_label_counts"):
        ev.plot_class_distribution(dataset["total_label_counts"], dataset["sample_label_counts"],
                                   fig_dir / "class_distribution.png")
        ev.write_latex_tables(results, resolve(paths["paper_generated"]))

    report_dir = resolve(paths["report_dir"])
    ev.save_json(results, report_dir / "results.json")

    bundle = {
        "preprocessor": pre,
        "model": best_model,
        "model_key": best,
        "model_name": title,
        "label_names": names,
        "benign_index": benign_idx,
        "autoencoder": ae,
        "keep_dst_port": cfg["data"]["keep_dst_port"],
        "metrics": {"test": results["models"][best]["test"], "val": results["models"][best]["val"]},
        "created_utc": results["created_utc"],
        "versions": {"python": platform.python_version(), "sklearn": sklearn.__version__,
                     "numpy": np.__version__, "pandas": pd.__version__},
        "data_note": cfg.get("data_note", ""),
    }
    joblib.dump(bundle, model_dir / BUNDLE_NAME, compress=3)
    log.info("saved model bundle to %s", model_dir / BUNDLE_NAME)
    return results
