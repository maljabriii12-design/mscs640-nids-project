# Reproducibility check (task M1)

Run by Mesalam Abdullah Al-Nabit on a fresh clone, following CONTRIBUTING.md Section 1 and 2
(README.md Sections 1 and 2).

## Environment

| Item | Value |
|---|---|
| Date | 2026-10-11 |
| OS | Microsoft Windows 11 Enterprise (10.0.26200) |
| Python | 3.12.10 (installed with `winget install Python.Python.3.12`) |
| Git | 2.56.0.windows.2 |
| Shell | Windows PowerShell |

## Steps and timings

| Step | Command | Time | Result |
|---|---|---|---|
| Install Python | `winget install --id Python.Python.3.12 -e --scope user` | 62 s | OK |
| Create venv | `python -m venv .venv` | 7 s | OK |
| Install requirements | `pip install -r requirements.txt` | 150 s | OK |
| Tests | `python -m pytest -q` | 32 s | **7 passed** |
| Synthetic data | `python main.py --config configs/smoke.json synth` | 3 s | OK |
| Smoke pipeline | `python main.py --config configs/smoke.json all` | 25 s | OK, `models/smoke/nids_bundle.joblib` written |
| Dashboard | `python main.py serve --model models/smoke/nids_bundle.joblib` | starts in a few seconds | Serving on http://127.0.0.1:5000 |

Total from a machine without Python to a running dashboard: about 5 minutes.
The smoke run uses synthetic flows; its scores are not reported anywhere.

## Issues found on a fresh Windows machine

1. **`python` not found.** On a new Windows install, typing `python` opens a Microsoft Store
   stub ("Python was not found; run without arguments to install from the Microsoft Store").
   Python must be installed first (python.org with "Add Python to PATH", or
   `winget install Python.Python.3.12`), and PowerShell reopened afterwards.
2. **Script execution policy.** `.venv\Scripts\activate` can fail with
   "running scripts is disabled on this system". Fix:
   `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then activate again.

Everything else in the README ran as written, with no changes needed.
