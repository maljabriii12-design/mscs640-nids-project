# Experiment log

Raw outputs (logs, `results.json`, figures, model bundle) are kept locally under `reports/`,
which is not committed; this file records what was run and what came out.

## Data used

Nine of the ten CSE-CIC-IDS2018 days (2.6 GB). `Thuesday-20-02-2018` (3.9 GB, the only day with
`DDoS attacks-LOIC-HTTP`) is not used yet, so that class is missing from training.

- 8,284,195 flows read; 59 repeated header rows removed; NaN in `Flow Byts/s` (22,954) and
  Inf in `Flow Byts/s` (13,353) / `Flow Pkts/s` (36,307) handled.
- Per-class sampling (Benign capped at 1M, attacks at 200k), then de-duplication:
  2,339,194 -> 1,383,462 rows (505,364 exact duplicates, 450,368 ambiguous-label rows).
- Split 70/15/15: 968,424 / 207,519 / 207,519. 78 -> 40 features. SMOTE to 20,000 for small
  classes plus class weights.

## Finding: FTP-BruteForce and DoS-SlowHTTPTest share their feature vectors

With the original `drop` policy (remove every copy of a feature vector that appears with more
than one label), `FTP-BruteForce` fell from 193,360 flows to 2 and `DoS attacks-SlowHTTPTest`
from 139,890 to 3. Their flows are identical on all 78 features, so no model can separate them.
Commit `0de7f5c` adds a `majority` policy (keep one copy, labelled with the class the vector
carries most often in the full data, correcting sample counts by sampling probability) and makes
it the default.

## Run 1 - 2026-10-10, nine days, `ambiguous_policy = drop`

Test macro-F1 (12 classes present in the test split; FTP-BruteForce and SlowHTTPTest absent):

| Model | Test macro-F1 |
|---|---|
| Random Forest | 0.8567 |
| XGBoost | 0.9149 |
| MLP | 0.8128 |
| Soft-vote ensemble | 0.8809 |
| Random Forest + class bias | 0.9210 |
| **XGBoost + class bias (best on validation)** | **0.9340** |
| MLP + class bias | 0.8515 |
| Soft-vote ensemble + class bias | 0.9205 |

Best model: accuracy 0.9237, balanced accuracy 0.9380, macro ROC-AUC (OvR) 0.9942; binary
attack-vs-benign detection rate 0.9238, false-positive rate 0.0764.

Per-class test F1 (best model): Bot, DDOS HOIC, DDOS LOIC-UDP, DoS GoldenEye, DoS Hulk,
SSH-Bruteforce 1.000; DoS Slowloris 0.999; Brute Force -XSS 0.986; Benign 0.938;
SQL Injection 0.870; Brute Force -Web 0.821; **Infilteration 0.595** (weakest: its flows
resemble Benign).

Caveat: the 0.934 overstates performance on the hidden test set, which will contain
FTP-BruteForce and SlowHTTPTest flows this model never learned.

Training time on a 14-core laptop: RF 26 s, XGBoost 577 s (595 rounds), MLP 2,509 s (40 epochs).

## Next

- Run 2: same data with `ambiguous_policy = majority` (the default since `0de7f5c`), then compare.
- Optionally add `Thuesday-20-02-2018` for `DDoS attacks-LOIC-HTTP`.
- Deploy the dashboard at `https://ids.batch5ai.lol` (DNS record already points to the VM).
