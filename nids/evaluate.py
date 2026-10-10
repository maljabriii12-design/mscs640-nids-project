"""Metrics, figures and LaTeX tables.

The headline metric is **macro F1**: the unweighted mean of per-class F1, so
SQL Injection counts as much as Benign. Accuracy is reported as well, but on
this data a model that predicts "Benign" for everything is already about 83%
accurate.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from sklearn.metrics import (accuracy_score, auc, balanced_accuracy_score,  # noqa: E402
                             confusion_matrix, f1_score, precision_recall_fscore_support,
                             roc_auc_score, roc_curve)


# ----------------------------------------------------------------------------
# Metrics
# ----------------------------------------------------------------------------
def compute_metrics(y_true: np.ndarray, proba: np.ndarray, names: list[str],
                    benign_index: int) -> dict:
    y_pred = proba.argmax(axis=1)
    labels = np.arange(len(names))
    p, r, f, s = precision_recall_fscore_support(y_true, y_pred, labels=labels, zero_division=0)
    present = np.unique(y_true)
    m = {
        "macro_f1": float(f1_score(y_true, y_pred, labels=present, average="macro", zero_division=0)),
        "weighted_f1": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "per_class": {
            names[i]: {"precision": float(p[i]), "recall": float(r[i]), "f1": float(f[i]),
                       "support": int(s[i])}
            for i in labels if s[i] > 0
        },
    }
    # Attack-vs-benign view, which is what a SOC analyst acts on
    t_att = y_true != benign_index
    p_att = y_pred != benign_index
    tp, fp = int((t_att & p_att).sum()), int((~t_att & p_att).sum())
    fn, tn = int((t_att & ~p_att).sum()), int((~t_att & ~p_att).sum())
    m["binary"] = {
        "detection_rate": tp / max(tp + fn, 1),
        "false_positive_rate": fp / max(fp + tn, 1),
        "precision": tp / max(tp + fp, 1),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
    }
    try:
        m["binary"]["roc_auc"] = float(roc_auc_score(t_att, 1.0 - proba[:, benign_index]))
        if len(present) > 2:
            P = proba[:, present]
            P = P / np.clip(P.sum(axis=1, keepdims=True), 1e-12, None)
            m["macro_roc_auc_ovr"] = float(roc_auc_score(y_true, P, multi_class="ovr",
                                                         labels=present, average="macro"))
    except ValueError:
        pass
    return m


# ----------------------------------------------------------------------------
# Figures
# ----------------------------------------------------------------------------
def _save(fig, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200, bbox_inches="tight")
    fig.savefig(path.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)


def plot_confusion(y_true, y_pred, names, path: Path, title: str = ""):
    present = np.unique(np.concatenate([y_true, y_pred]))
    cm = confusion_matrix(y_true, y_pred, labels=present)
    norm = cm / np.clip(cm.sum(axis=1, keepdims=True), 1, None)
    n = len(present)
    fig, ax = plt.subplots(figsize=(0.55 * n + 2.5, 0.55 * n + 2))
    ax.imshow(norm, cmap="Blues", vmin=0, vmax=1)
    ticks = [names[i] for i in present]
    ax.set_xticks(range(n), ticks, rotation=60, ha="right", fontsize=7)
    ax.set_yticks(range(n), ticks, fontsize=7)
    for i in range(n):
        for j in range(n):
            if cm[i, j]:
                ax.text(j, i, f"{norm[i, j]:.2f}", ha="center", va="center", fontsize=5.5,
                        color="white" if norm[i, j] > 0.5 else "black")
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    if title:
        ax.set_title(title, fontsize=9)
    _save(fig, path)


def plot_roc(y_true, proba, names, benign_index, path: Path, title: str = ""):
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
    ax = axes[0]
    cmap = plt.get_cmap("tab20")
    for k, i in enumerate(np.unique(y_true)):
        t = (y_true == i).astype(int)
        if t.min() == t.max():
            continue
        fpr, tpr, _ = roc_curve(t, proba[:, i])
        ax.plot(fpr, tpr, lw=1.1, color=cmap(k % 20), label=f"{names[i]} ({auc(fpr, tpr):.3f})")
    ax.plot([0, 1], [0, 1], "k--", lw=0.6)
    ax.set_xscale("symlog", linthresh=1e-3)
    ax.set_xlim(0, 1)
    ax.set_xlabel("False positive rate (symlog)")
    ax.set_ylabel("True positive rate")
    ax.set_title("One-vs-rest ROC per class", fontsize=9)
    ax.legend(fontsize=5.5, loc="lower right")

    ax = axes[1]
    t = (y_true != benign_index).astype(int)
    if t.min() != t.max():
        fpr, tpr, _ = roc_curve(t, 1 - proba[:, benign_index])
        ax.plot(fpr, tpr, lw=1.4, label=f"attack vs benign (AUC {auc(fpr, tpr):.4f})")
    ax.plot([0, 1], [0, 1], "k--", lw=0.6)
    ax.set_xscale("symlog", linthresh=1e-3)
    ax.set_xlim(0, 1)
    ax.set_xlabel("False positive rate (symlog)")
    ax.set_title("Binary detection ROC", fontsize=9)
    ax.legend(fontsize=7, loc="lower right")
    if title:
        fig.suptitle(title, fontsize=10)
    _save(fig, path)


def plot_class_distribution(total_counts: dict, sample_counts: dict, path: Path):
    labels = list(total_counts)
    fig, ax = plt.subplots(figsize=(8, 3.6))
    x = np.arange(len(labels))
    ax.bar(x - 0.2, [total_counts[l] for l in labels], 0.4, label="full dataset")
    ax.bar(x + 0.2, [sample_counts.get(l, 0) for l in labels], 0.4, label="cleaned sample")
    ax.set_yscale("log")
    ax.set_xticks(x, labels, rotation=55, ha="right", fontsize=7)
    ax.set_ylabel("flows (log scale)")
    ax.legend(fontsize=8)
    _save(fig, path)


def plot_feature_importance(importances: dict, path: Path, top: int = 20):
    items = sorted(importances.items(), key=lambda kv: -kv[1])[:top][::-1]
    fig, ax = plt.subplots(figsize=(6, 0.22 * len(items) + 1))
    ax.barh([k for k, _ in items], [v for _, v in items])
    ax.tick_params(axis="y", labelsize=7)
    ax.set_xlabel("ExtraTrees impurity importance")
    _save(fig, path)


def plot_autoencoder(scores_benign, scores_attack, threshold, path: Path):
    fig, ax = plt.subplots(figsize=(6, 3.2))
    bins = np.logspace(np.log10(max(min(scores_benign.min(), scores_attack.min()), 1e-6)),
                       np.log10(max(scores_benign.max(), scores_attack.max())), 80)
    ax.hist(scores_benign, bins=bins, alpha=0.6, density=True, label="Benign")
    ax.hist(scores_attack, bins=bins, alpha=0.6, density=True, label="Attack")
    ax.axvline(threshold, color="k", ls="--", lw=0.8, label="threshold")
    ax.set_xscale("log")
    ax.set_xlabel("reconstruction error")
    ax.legend(fontsize=8)
    _save(fig, path)


# ----------------------------------------------------------------------------
# LaTeX tables (\input-ed by paper/main.tex)
# ----------------------------------------------------------------------------
def _tex(s: str) -> str:
    return (str(s).replace("\\", r"\textbackslash{}").replace("&", r"\&").replace("%", r"\%")
            .replace("_", r"\_").replace("#", r"\#"))


def write_latex_tables(results: dict, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    best = results["best_model"]

    rows = []
    for key, r in results["models"].items():
        name = _tex(r["display_name"]) + (r" $\star$" if key == best else "")
        rows.append(f"{name} & {r['val']['macro_f1']:.4f} & {r['test']['macro_f1']:.4f} & "
                    f"{r['test']['weighted_f1']:.4f} & {r['test']['accuracy']:.4f} & "
                    f"{r['train_seconds']:.0f} \\\\")
    (out_dir / "model_comparison.tex").write_text(
        "\\begin{tabular}{lccccr}\n\\toprule\n"
        "Model & Val $F_1^{M}$ & Test $F_1^{M}$ & Test $F_1^{W}$ & Test Acc. & Train (s) \\\\\n"
        "\\midrule\n" + "\n".join(rows) + "\n\\bottomrule\n\\end{tabular}\n", encoding="utf-8")

    pc = results["models"][best]["test"]["per_class"]
    rows = [f"{_tex(c)} & {v['precision']:.3f} & {v['recall']:.3f} & {v['f1']:.3f} & {v['support']:,} \\\\"
            for c, v in pc.items()]
    (out_dir / "per_class.tex").write_text(
        "\\begin{tabular}{lcccr}\n\\toprule\n"
        "Class & Prec. & Rec. & $F_1$ & Support \\\\\n\\midrule\n" + "\n".join(rows) +
        "\n\\bottomrule\n\\end{tabular}\n", encoding="utf-8")

    ds = results["dataset"]
    rows = [f"{_tex(c)} & {n:,} & {ds['sample_label_counts'].get(c, 0):,} \\\\"
            for c, n in ds["total_label_counts"].items()]
    (out_dir / "dataset.tex").write_text(
        "\\begin{tabular}{lrr}\n\\toprule\nClass & All flows & Clean sample \\\\\n\\midrule\n"
        + "\n".join(rows) + "\n\\bottomrule\n\\end{tabular}\n", encoding="utf-8")

    b = results["models"][best]["test"]["binary"]
    macros = {
        "BestModel": _tex(results["models"][best]["display_name"]),
        "BestMacroFOne": f"{results['models'][best]['test']['macro_f1']:.4f}",
        "BestAccuracy": f"{results['models'][best]['test']['accuracy']:.4f}",
        "DetectionRate": f"{100 * b['detection_rate']:.2f}\\%",
        "FalsePositiveRate": f"{100 * b['false_positive_rate']:.3f}\\%",
        "NumRawFlows": f"{ds['rows_seen']:,}",
        "NumSampleFlows": f"{sum(ds['sample_label_counts'].values()):,}",
        "NumFeaturesIn": str(results["features"]["n_input"]),
        "NumFeaturesOut": str(results["features"]["n_selected"]),
        "DataSourceNote": _tex(results.get("data_note", "")),
    }
    if "autoencoder" in results:
        a = results["autoencoder"]
        macros["AEDetectionRate"] = f"{100 * a['detection_rate']:.2f}\\%"
        macros["AEFalsePositiveRate"] = f"{100 * a['false_positive_rate']:.2f}\\%"
        macros["AEAUC"] = f"{a['roc_auc']:.4f}"
    (out_dir / "macros.tex").write_text(
        "\n".join(f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in macros.items()) + "\n",
        encoding="utf-8")


def save_json(obj, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, default=float)
