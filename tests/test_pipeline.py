"""Smoke and unit tests. Run with ``python -m pytest`` or ``python -m unittest``.

The end-to-end test builds a small synthetic dataset with the real
CSE-CIC-IDS2018 schema in a temporary directory, so it needs neither the real
data nor network access.
"""
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from nids.config import LABELS, load_config
from nids.data import clean_frame, drop_duplicate_flows
from nids.imbalance import class_weights, smote


class TestCleaning(unittest.TestCase):
    def test_inf_nan_header_and_ids(self):
        raw = pd.DataFrame({
            " Dst Port": ["80", "22", "Dst Port"],
            "Src IP": ["1.1.1.1", "2.2.2.2", "Src IP"],
            "Timestamp": ["t", "t", "Timestamp"],
            "Flow Byts/s": ["Infinity", "NaN", "Flow Byts/s"],
            "Flow Duration": ["0", "1e40", "Flow Duration"],
            "Label": ["Benign", "SSH-Bruteforce", "Label"],
        })
        out = clean_frame(raw)
        self.assertEqual(len(out), 2)                       # repeated header removed
        self.assertNotIn("Src IP", out.columns)             # identifier dropped
        self.assertNotIn("Timestamp", out.columns)
        self.assertIn("Dst Port", out.columns)              # whitespace stripped
        self.assertTrue(out["Flow Byts/s"].isna().all())    # Inf and NaN -> NaN
        self.assertTrue(np.isfinite(out["Flow Duration"]).all())  # clipped to float32
        self.assertEqual(out["Label"].tolist(), ["Benign", "SSH-Bruteforce"])

    def test_dedup_and_ambiguous(self):
        df = pd.DataFrame({"a": [1, 1, 2, 2, 3], "b": [0, 0, 0, 0, 1],
                           "Label": ["Benign", "Benign", "Bot", "Benign", "Bot"]})
        out, info = drop_duplicate_flows(df)
        self.assertEqual(info["exact_duplicates_removed"], 1)
        self.assertEqual(info["ambiguous_label_rows_removed"], 2)
        self.assertEqual(len(out), 2)

    def test_ambiguous_majority_uses_full_data_counts(self):
        # vector (2,0): 2 sampled Benign rows vs 3 Bot rows. Benign was kept with
        # p=0.1, so it stands for ~20 real flows against 3 Bot -> Benign wins.
        df = pd.DataFrame({"a": [2, 2, 2, 2, 2, 3], "b": [0, 0, 0, 0, 0, 1],
                           "Label": ["Benign", "Benign", "Bot", "Bot", "Bot", "Bot"]})
        out, info = drop_duplicate_flows(df, policy="majority",
                                         keep_prob={"Benign": 0.1, "Bot": 1.0})
        self.assertEqual(sorted(map(tuple, out[["a", "Label"]].values.tolist())),
                         [(2, "Benign"), (3, "Bot")])
        self.assertEqual(info["ambiguous_vectors"], 1)
        self.assertEqual(info["ambiguous_vectors_kept_by_label"], {"Benign": 1})
        # without the correction the raw majority would wrongly be Bot
        out2, _ = drop_duplicate_flows(df, policy="majority", keep_prob={})
        self.assertIn((2, "Bot"), list(map(tuple, out2[["a", "Label"]].values.tolist())))


class TestImbalance(unittest.TestCase):
    def test_smote_reaches_target_and_interpolates(self):
        rng = np.random.default_rng(0)
        X = np.vstack([rng.normal(0, 1, (500, 3)), rng.normal(5, 0.1, (10, 3))]).astype(np.float32)
        y = np.array([0] * 500 + [1] * 10)
        Xs, ys = smote(X, y, target=200, k=3, seed=0)
        self.assertEqual((ys == 1).sum(), 200)
        self.assertEqual((ys == 0).sum(), 500)
        synth = Xs[len(X):]
        self.assertTrue((synth.min(0) >= X[y == 1].min(0) - 1e-5).all())
        self.assertTrue((synth.max(0) <= X[y == 1].max(0) + 1e-5).all())

    def test_class_weights(self):
        w = class_weights(np.array([0] * 900 + [1] * 100), power=1.0)
        self.assertAlmostEqual(w[1] / w[0], 9.0, places=5)


class TestModels(unittest.TestCase):
    def test_gbdt_leaf_cap_reaches_xgboost(self):
        from nids import models
        if not models.HAS_XGB:
            self.skipTest("xgboost not installed")
        rng = np.random.default_rng(0)
        X = rng.normal(size=(200, 4)).astype(np.float32)
        y = rng.integers(0, 3, 200)
        p = {"engine": "xgboost", "n_estimators": 5, "learning_rate": 0.1, "max_depth": 4,
             "l2_regularization": 1.0, "early_stopping_rounds": 2, "max_leaf_nodes": 7}
        m = models.fit_gbdt(p, X, y, None, X, y, 0)
        self.assertEqual(m.get_params()["max_leaves"], 7)
        m = models.fit_gbdt({**p, "max_leaf_nodes": None}, X, y, None, X, y, 0)
        self.assertEqual(m.get_params()["max_leaves"], 0)   # null = no limit, as in the reported runs


class TestReportLabels(unittest.TestCase):
    def test_every_attack_has_severity_and_attack_technique(self):
        from nids.predict import ATTACK_TECHNIQUE, SEVERITY
        attacks = {c for c in SEVERITY if c != "Benign"}
        self.assertEqual(len(attacks), 14)
        self.assertEqual(attacks, set(ATTACK_TECHNIQUE))
        for tid, name in ATTACK_TECHNIQUE.values():
            self.assertRegex(tid, r"^T\d{4}$")
            self.assertTrue(name)


class TestEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from nids.synthetic import make_synthetic
        cls.tmp = Path(tempfile.mkdtemp())
        make_synthetic(cls.tmp / "raw_synthetic", n_benign=16000, n_attack=600, seed=1)
        cls.cfg = load_config(overrides={
            "data_note": "synthetic test",
            "paths": {"raw_dir": str(cls.tmp / "raw_synthetic"),
                      "processed": str(cls.tmp / "sample.pkl"),
                      "model_dir": str(cls.tmp / "models"),
                      "report_dir": str(cls.tmp / "reports"),
                      "paper_generated": str(cls.tmp / "gen"),
                      "paper_figures": str(cls.tmp / "fig")},
            "data": {"chunksize": 5000, "cap_benign": 12000, "cap_attack": 600},
            "imbalance": {"smote_target": 300, "benign_train_cap": 6000},
            "models": {"random_forest": {"n_estimators": 20}, "gbdt": {"n_estimators": 30},
                       "mlp": {"hidden_layer_sizes": [32], "max_iter": 5},
                       "autoencoder": {"max_iter": 3, "benign_fit_rows": 4000}},
        })

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_full_pipeline(self):
        from nids.pipeline import prepare, train
        from nids.predict import load_bundle, predict_frame, predict_file

        prepare(self.cfg)
        res = train(self.cfg)
        self.assertIn(res["best_model"], res["models"])
        self.assertGreater(res["models"][res["best_model"]]["test"]["macro_f1"], 0.3)
        for f in ("model_comparison.tex", "per_class.tex", "dataset.tex", "macros.tex"):
            self.assertTrue((self.tmp / "gen" / f).exists(), f)
        self.assertTrue((self.tmp / "fig" / "confusion_matrix.png").exists())

        bundle = load_bundle(str(self.tmp / "models" / "nids_bundle.joblib"))
        raw = next(iter((self.tmp / "raw_synthetic").glob("*.csv")))
        out = predict_frame(pd.read_csv(raw, nrows=2000), bundle)
        self.assertEqual(len(out), 2000)
        self.assertTrue(set(out["Predicted"]) <= set(LABELS))

        n = predict_file(raw, self.tmp / "pred.csv", bundle, chunksize=7000)
        self.assertEqual(n, len(pd.read_csv(self.tmp / "pred.csv")))

        # dashboard
        from webapp.app import create_app
        client = create_app(str(self.tmp / "models" / "nids_bundle.joblib")).test_client()
        self.assertEqual(client.get("/").status_code, 200)
        r = client.post("/analyze", data={"file": (io.BytesIO(raw.read_bytes()[:300_000].rsplit(b"\n", 1)[0]), "x.csv")},
                        content_type="multipart/form-data")
        self.assertEqual(r.status_code, 302)
        page = client.get(r.headers["Location"])
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Threat report", page.data)
        api = client.post("/api/predict", json={"flows": [{"Dst Port": 22, "Protocol": 6}]})
        self.assertEqual(api.status_code, 200)
        self.assertEqual(json.loads(api.data)["n_flows"], 1)


if __name__ == "__main__":
    unittest.main()
