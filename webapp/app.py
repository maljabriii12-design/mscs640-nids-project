"""Phase 3: SOC threat-detection dashboard (Flask).

Upload a CICFlowMeter CSV and the pre-trained bundle scores every flow. The
threat report shows headline counts, the attack mix, the most targeted hosts
and ports, a triage table sorted by severity and confidence, and, when the
upload carries a ``Label`` column, live evaluation metrics with a confusion
matrix. Results can be downloaded as CSV; ``POST /api/predict`` returns JSON.
"""
from __future__ import annotations

import base64
import io
import logging
import os
import sys
import time
import uuid
from collections import OrderedDict
from pathlib import Path

import numpy as np
import pandas as pd
from flask import (Flask, Response, abort, jsonify, redirect, render_template, request,
                   url_for)

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nids.config import BENIGN  # noqa: E402
from nids.predict import ATTACK_TECHNIQUE, SEVERITY_ORDER, load_bundle, predict_frame  # noqa: E402

log = logging.getLogger(__name__)
MAX_TABLE_ROWS = 500
MAX_REPORTS = 8


def _confusion_png(y_true: pd.Series, y_pred: pd.Series) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.metrics import confusion_matrix

    labels = sorted(set(y_true) | set(y_pred))
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    norm = cm / np.clip(cm.sum(axis=1, keepdims=True), 1, None)
    n = len(labels)
    fig, ax = plt.subplots(figsize=(0.5 * n + 2.6, 0.5 * n + 2))
    ax.imshow(norm, cmap="Blues", vmin=0, vmax=1)
    ax.set_xticks(range(n), labels, rotation=60, ha="right", fontsize=7)
    ax.set_yticks(range(n), labels, fontsize=7)
    for i in range(n):
        for j in range(n):
            if cm[i, j]:
                ax.text(j, i, f"{cm[i, j]}", ha="center", va="center", fontsize=6,
                        color="white" if norm[i, j] > 0.5 else "black")
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def build_report(res: pd.DataFrame, filename: str, seconds: float) -> dict:
    n = len(res)
    mal = res[res["Malicious"]]
    counts = res["Predicted"].value_counts()
    attack_counts = counts.drop(BENIGN, errors="ignore")
    sev = mal["Severity"].value_counts()
    report = {
        "filename": filename,
        "n_flows": n,
        "n_malicious": int(len(mal)),
        "pct_malicious": 100.0 * len(mal) / max(n, 1),
        "n_critical": int(sev.get("Critical", 0)),
        "n_high": int(sev.get("High", 0)),
        "seconds": seconds,
        "class_bars": [(k, int(v), 100.0 * v / max(attack_counts.max(), 1),
                        *ATTACK_TECHNIQUE.get(k, ("", "")))
                       for k, v in attack_counts.items()],
        "severity": [(s, int(sev.get(s, 0))) for s in ("Critical", "High", "Medium")],
        "has_anomaly": "Anomalous" in res.columns,
        "has_truth": "True label" in res.columns,
    }
    if report["has_anomaly"]:
        report["n_anomalous"] = int(res["Anomalous"].sum())
        report["n_anomalous_only"] = int((res["Anomalous"] & ~res["Malicious"]).sum())

    def top(col, k=6):
        if col not in mal.columns or mal.empty:
            return []
        vc = mal[col].astype(str).value_counts().head(k)
        return [(i, int(v), 100.0 * v / max(vc.max(), 1)) for i, v in vc.items()]

    report["top_dst_ip"] = top("Dst IP")
    report["top_src_ip"] = top("Src IP")
    report["top_dst_port"] = top("Dst Port")

    triage = mal.assign(_s=mal["Severity"].map(SEVERITY_ORDER).fillna(9))
    triage = triage.sort_values(["_s", "Confidence"], ascending=[True, False]).drop(columns="_s")
    report["table_cols"] = [c for c in triage.columns if c not in ("Malicious",)]
    report["table"] = triage.head(MAX_TABLE_ROWS).to_dict("records")
    report["table_truncated"] = len(triage) > MAX_TABLE_ROWS

    if report["has_truth"]:
        from sklearn.metrics import accuracy_score, f1_score
        yt, yp = res["True label"], res["Predicted"]
        report["eval"] = {
            "macro_f1": f1_score(yt, yp, labels=sorted(set(yt)), average="macro", zero_division=0),
            "accuracy": accuracy_score(yt, yp),
            "detection_rate": float(((yt != BENIGN) & (yp != BENIGN)).sum() / max((yt != BENIGN).sum(), 1)),
            "fpr": float(((yt == BENIGN) & (yp != BENIGN)).sum() / max((yt == BENIGN).sum(), 1)),
        }
        report["confusion_png"] = _confusion_png(yt, yp)
    return report


def create_app(model_path: str | None = None) -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("NIDS_MAX_UPLOAD_MB", "1024")) * 2 ** 20
    model_path = model_path or os.environ.get("NIDS_MODEL")
    store: OrderedDict[str, tuple[pd.DataFrame, dict]] = OrderedDict()

    def bundle():
        return load_bundle(model_path)

    def model_card():
        try:
            b = bundle()
        except FileNotFoundError as e:
            return {"error": str(e)}
        m = b.get("metrics", {}).get("test", {})
        return {"name": b["model_name"], "created": b["created_utc"],
                "macro_f1": m.get("macro_f1"), "accuracy": m.get("accuracy"),
                "n_features": len(b["preprocessor"].selected_columns_),
                "n_classes": len(b["label_names"]), "note": b.get("data_note", ""),
                "has_ae": b.get("autoencoder") is not None}

    def demo_path() -> Path | None:
        base = Path(model_path).parent if model_path else ROOT / "models"
        p = base / "demo_test_flows.csv"
        return p if p.exists() else None

    def run(df: pd.DataFrame, name: str) -> str:
        t0 = time.time()
        res = predict_frame(df, bundle())
        rep = build_report(res, name, time.time() - t0)
        rid = uuid.uuid4().hex[:12]
        store[rid] = (res, rep)
        while len(store) > MAX_REPORTS:
            store.popitem(last=False)
        return rid

    @app.get("/")
    def index():
        return render_template("index.html", card=model_card(), demo=demo_path() is not None,
                               error=request.args.get("error"))

    @app.post("/analyze")
    def analyze():
        f = request.files.get("file")
        if not f or not f.filename:
            return redirect(url_for("index", error="Choose a CSV file first."))
        try:
            df = pd.read_csv(f, low_memory=False, skipinitialspace=True, encoding_errors="replace")
        except Exception as e:  # malformed upload
            return redirect(url_for("index", error=f"Could not parse CSV: {e}"))
        if df.empty:
            return redirect(url_for("index", error="The file has no rows."))
        try:
            rid = run(df, f.filename)
        except Exception as e:
            log.exception("prediction failed")
            return redirect(url_for("index", error=f"Prediction failed: {e}"))
        return redirect(url_for("report", rid=rid))

    @app.post("/demo")
    def demo():
        p = demo_path()
        if not p:
            abort(404)
        return redirect(url_for("report", rid=run(pd.read_csv(p, low_memory=False), p.name)))

    @app.get("/report/<rid>")
    def report(rid):
        if rid not in store:
            return redirect(url_for("index", error="That report has expired; upload again."))
        return render_template("report.html", r=store[rid][1], rid=rid, card=model_card())

    @app.get("/report/<rid>.csv")
    def download(rid):
        if rid not in store:
            abort(404)
        res = store[rid][0]
        only = request.args.get("only") == "malicious"
        data = (res[res["Malicious"]] if only else res).to_csv(index=False)
        return Response(data, mimetype="text/csv", headers={
            "Content-Disposition": f"attachment; filename=threat_report_{rid}.csv"})

    @app.post("/api/predict")
    def api_predict():
        f = request.files.get("file")
        if f:
            df = pd.read_csv(f, low_memory=False, skipinitialspace=True)
        else:
            payload = request.get_json(silent=True) or {}
            df = pd.DataFrame(payload.get("flows", []))
        if df.empty:
            return jsonify({"error": "no flows supplied"}), 400
        res = predict_frame(df, bundle())
        return jsonify({"n_flows": len(res), "n_malicious": int(res["Malicious"].sum()),
                        "predictions": res.to_dict("records")})

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "model": model_card()})

    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    create_app().run(debug=False)
