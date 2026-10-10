#!/usr/bin/env python3
"""Network intrusion detection on CSE-CIC-IDS2018: command-line entry point.

    python main.py download            # fetch the 10 ML-ready CSVs into data/raw
    python main.py prepare             # Phase 1: chunked cleaning + stratified sampling
    python main.py train               # Phase 2: features, imbalance, models, evaluation
    python main.py predict IN.csv -o OUT.csv   # score new traffic / the hidden test set
    python main.py serve               # Phase 3: threat-detection dashboard (Flask)
    python main.py all                 # prepare + train
    python main.py synth               # synthetic schema-identical data for smoke tests

Global options: --config FILE (JSON overriding configs/default.json), -v.
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path

from nids.config import load_config, resolve

BUCKET_PREFIX = "s3://cse-cic-ids2018/Processed Traffic Data for ML Algorithms/"
SMALLEST_DAY = "Thursday-01-03-2018_TrafficForML_CICFlowMeter.csv"


def cmd_download(cfg, args):
    """AWS CLI if present (the instructor's command), otherwise plain HTTPS."""
    raw = resolve(cfg["paths"]["raw_dir"])
    raw.mkdir(parents=True, exist_ok=True)
    if shutil.which("aws") and not args.http:
        if args.smallest:
            cmd = ["aws", "s3", "cp", "--no-sign-request", BUCKET_PREFIX + SMALLEST_DAY, str(raw)]
        else:
            cmd = ["aws", "s3", "sync", "--no-sign-request", BUCKET_PREFIX, str(raw)]
        logging.info("running: %s", " ".join(cmd))
        subprocess.run(cmd, check=True)
    else:
        from nids.download import download
        download(raw, only=SMALLEST_DAY if args.smallest else None)


def cmd_synth(cfg, args):
    from nids.synthetic import make_synthetic
    raw = resolve(cfg["paths"]["raw_dir"])
    out = Path(args.out) if args.out else (raw if "synthetic" in str(raw) else raw / "synthetic")
    paths = make_synthetic(out, n_benign=args.benign, n_attack=args.attack, seed=cfg["seed"])
    for p in paths:
        print(p)
    print("NOTE: synthetic data is for smoke-testing only; never report results on it.")


def cmd_prepare(cfg, args):
    from nids.pipeline import prepare
    prepare(cfg)


def cmd_train(cfg, args):
    from nids.pipeline import train
    if args.tune:
        cfg["tuning"]["enabled"] = True
    res = train(cfg)
    best = res["models"][res["best_model"]]
    print(json.dumps({
        "best_model": best["display_name"],
        "val_macro_f1": round(best["val"]["macro_f1"], 4),
        "test_macro_f1": round(best["test"]["macro_f1"], 4),
        "test_accuracy": round(best["test"]["accuracy"], 4),
        "all_models_test_macro_f1": {r["display_name"]: round(r["test"]["macro_f1"], 4)
                                     for r in res["models"].values()},
    }, indent=2))


def cmd_predict(cfg, args):
    from nids.predict import load_bundle, predict_file
    bundle = load_bundle(args.model)
    n = predict_file(args.input, args.output, bundle)
    print(f"wrote {n:,} predictions to {args.output}")


def cmd_serve(cfg, args):
    from webapp.app import create_app
    app = create_app(args.model)
    app.run(host=args.host, port=args.port, debug=False)


def cmd_all(cfg, args):
    cmd_prepare(cfg, args)
    cmd_train(cfg, args)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", help="JSON file overriding configs/default.json")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("download", help="download the dataset with the AWS CLI")
    p.add_argument("--smallest", action="store_true", help=f"only {SMALLEST_DAY} (103 MB)")
    p.add_argument("--http", action="store_true", help="use HTTPS even if the AWS CLI exists")
    p.set_defaults(func=cmd_download)

    p = sub.add_parser("synth", help="write schema-identical synthetic CSVs (testing only)")
    p.add_argument("--out")
    p.add_argument("--benign", type=int, default=60_000)
    p.add_argument("--attack", type=int, default=3_000)
    p.set_defaults(func=cmd_synth)

    sub.add_parser("prepare", help="Phase 1: clean + sample raw CSVs").set_defaults(func=cmd_prepare)

    p = sub.add_parser("train", help="Phase 2: train and evaluate all models")
    p.add_argument("--tune", action="store_true", help="random search over GBDT hyper-parameters")
    p.set_defaults(func=cmd_train)

    p = sub.add_parser("all", help="prepare + train")
    p.add_argument("--tune", action="store_true")
    p.set_defaults(func=cmd_all)

    p = sub.add_parser("predict", help="score a CSV of flows")
    p.add_argument("input")
    p.add_argument("-o", "--output", default="reports/predictions.csv")
    p.add_argument("--model", help="path to a model bundle (default models/nids_bundle.joblib)")
    p.set_defaults(func=cmd_predict)

    p = sub.add_parser("serve", help="Phase 3: run the dashboard")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=5000)
    p.add_argument("--model")
    p.set_defaults(func=cmd_serve)

    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    cfg = load_config(args.config)
    args.func(cfg, args)


if __name__ == "__main__":
    main()
