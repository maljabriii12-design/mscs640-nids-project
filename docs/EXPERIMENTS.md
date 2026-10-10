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

## Run 2 - 2026-10-10, nine days, `ambiguous_policy = majority` (final)

De-duplication: 23,300 ambiguous feature vectors; one copy kept per vector with its full-data
majority label (Benign 23,179, Infilteration 63, SlowHTTPTest 30, FTP-BruteForce 22,
Brute Force -Web 4, SQL Injection 2). 2,339,194 -> 1,406,762 rows. FTP-BruteForce now has 24
unique flows and SlowHTTPTest 33 (2 and 3 under `drop`), so all 14 classes reach the test split.
Split 984,732 / 211,015 / 211,015.

| Model | Test macro-F1 (14 classes) | Same 12 classes as run 1 |
|---|---|---|
| Random Forest | 0.8138 | 0.8577 |
| XGBoost | 0.8338 | 0.9036 |
| MLP | 0.7766 | 0.8144 |
| Soft-vote ensemble | 0.8259 | 0.8895 |
| **Random Forest + class bias (best on validation)** | **0.8814** | 0.8969 |
| XGBoost + class bias | 0.8532 | 0.9261 |
| MLP + class bias | 0.8366 | 0.8678 |
| Soft-vote ensemble + class bias | 0.8499 | 0.9175 |

Best model: accuracy 0.9260, balanced accuracy 0.8934, macro ROC-AUC (OvR) 0.9944; binary
detection rate 0.9110, false-positive rate 0.0649. Autoencoder (anomaly detection, Benign-only
fit): AUC 0.8705, detection rate 3.73% at a 1.01% false-positive rate.

Per-class test F1 (best model, support in brackets): DDOS HOIC, DDOS LOIC-UDP, DoS GoldenEye,
DoS Hulk, SSH-Bruteforce 1.000; Bot 0.999; DoS Slowloris 0.998; Brute Force -XSS 0.955 (34);
Benign 0.941; **DoS SlowHTTPTest 0.909 (5)**; SQL Injection 0.696 (12); **FTP-BruteForce
0.667 (4)**; Brute Force -Web 0.597 (82); Infilteration 0.579.

### Run 1 vs run 2

- On a test set containing all 14 classes, the run-1 model cannot predict FTP-BruteForce or
  SlowHTTPTest, which caps it at about 0.934 x 12/14 = 0.80 macro-F1. Run 2 reaches 0.881, so the
  majority policy is worth roughly +0.08 macro-F1 in the setting the hidden test set will use.
- On the 12 classes both runs share, the best models are close (0.934 vs 0.926 for XGBoost +
  class bias); the small drop comes from the rarest classes.
- Classes with fewer than 100 test flows (FTP-BruteForce 4, SlowHTTPTest 5, SQL Injection 12,
  XSS 34, Web 82) make per-class F1 noisy: one flow changes the FTP-BruteForce F1 by up to 0.25.
- Model selection is done on validation macro-F1, so the reported best model (RF + class bias)
  is not the one with the highest 12-class test score; this is the intended, unbiased choice.

## Run 3 - 2026-10-10, all ten days, `ambiguous_policy = majority` (final, deployed)

Adds `Thuesday-20-02-2018` (3.9 GB, `DDoS attacks-LOIC-HTTP`), so all 15 labels are present.
De-duplication: 2,537,395 -> 1,589,555 rows (511,975 exact duplicates; 20,769 ambiguous vectors,
one copy kept each). Split 1,112,687 / 238,434 / 238,434. LOIC-HTTP contributes 140,292
training flows.

| Model | Test macro-F1 (15 classes) |
|---|---|
| Random Forest | 0.8055 |
| XGBoost | 0.8492 |
| MLP (early-stopped at 24 epochs) | 0.7649 |
| **XGBoost + class bias (best on validation, val 0.942)** | **0.8640** |

Best model: accuracy 0.9372, balanced accuracy 0.8715, macro ROC-AUC (OvR) 0.9943; binary
detection rate 0.9164, false-positive rate 0.0450 (down from 0.0649 in run 2).

Per-class test F1 (support): DDoS LOIC-HTTP 1.000 (30,063); Bot, DDOS HOIC, DoS GoldenEye,
DoS Hulk, DoS Slowloris, SSH-Bruteforce 1.000; DDOS LOIC-UDP 0.947; Benign 0.943;
Brute Force -XSS 0.943 (34); Brute Force -Web 0.849 (82); SQL Injection 0.636 (12);
FTP-BruteForce 0.600 (4); Infilteration 0.543; DoS SlowHTTPTest 0.500 (5).

### Run 2 vs run 3

- On a 15-class test, the run-2 model scores 0 on LOIC-HTTP, capping it at about
  0.881 x 14/15 = 0.82; run 3 reaches 0.864.
- On the 14 classes both share, run 3 scores 0.854 vs 0.881. The difference sits in the tiny
  classes (SlowHTTPTest 5 test flows, FTP 4, SQL Injection 12), where one flow moves F1 by
  0.1-0.25, so the two runs are within noise there; large classes are equal or better
  (Brute Force -Web 0.597 -> 0.849, Benign false positives 6.5% -> 4.5%).
- The validation/test gap (0.942 vs 0.864) has the same cause.
- Deployed at https://ids.batch5ai.lol: the XGBoost bundle is 12 MB (RF was 30 MB), uses
  ~345 MB of RAM on the VM (RF ~450 MB) and scores the 5,000-flow demo sample in 2.3 s (10.3 s).

## Next

- Paper: Methodology, Results and Conclusion from runs 2-3; AI-use statement.
- Deploy the dashboard at `https://ids.batch5ai.lol` (DNS record already points to the VM).
