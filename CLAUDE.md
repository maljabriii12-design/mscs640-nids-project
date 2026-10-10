# Project instructions for AI assistants

MSCS640 course project: network intrusion detection on CSE-CIC-IDS2018. Team of two:
Mohammed Amer Al-Jabri (owner, GitHub `maljabriii12-design`) and Mesalam Abdullah Al-Nabit
(GitHub `malnabit`). Read `README.md`, `CONTRIBUTING.md` and `docs/EXPERIMENTS.md` first.

## Ask who you are helping

Each student must commit their own work under their own account (a course requirement). At the
start of a session, ask which student you are helping. For Mesalam, work only on tasks M1-M5 in
`CONTRIBUTING.md` Section 3 and follow the prompt in Section 6 there.

## Hard rules

- Never fabricate references, numbers or results. Citations must be real and support the
  sentence; give title, authors, venue, year and DOI/URL so the student can verify them.
- Paper numbers, tables and figures come from `paper/generated/` and `paper/figures/`, written by
  `python main.py train`. Never edit those files by hand.
- Do not retrain on the real data, change `configs/`, `nids/` or `deploy/`, or touch the live
  server unless the student explicitly asks; the deployed model is documented in
  `docs/EXPERIMENTS.md` (run 3).
- Do not commit `data/`, `models/` or `reports/` (gitignored).
- Run `python -m pytest -q` before proposing a commit. Let the student commit and push.
- Dashboard templates are bilingual: text carries `data-i18n="key"`, Arabic strings live in
  `T.ar` in `webapp/templates/base.html`, English stays in the HTML as fallback. Never write
  `{#` in a Jinja template.
- Whatever you help with must be disclosed in the paper's "Statement on the Use of AI Tools".

## Commands

```bash
pip install -r requirements.txt
python -m pytest -q                                   # tests (about 1 minute)
python main.py --config configs/smoke.json synth      # synthetic smoke data
python main.py --config configs/smoke.json all        # smoke run (about 3 minutes)
python main.py serve --model models/smoke/nids_bundle.joblib
```
