# Contributing

Team: **Mohammed Amer Al-Jabri** ([@maljabriii12-design](https://github.com/maljabriii12-design)) and
**Mesalam Abdullah Al-Nabit** ([@malnabit](https://github.com/malnabit)). The course requires that both members
commit to this repository, so each of us pushes our own work from our own machine.

## 1. One-time setup (Windows)

Install [Git](https://git-scm.com) and [Python 3.12](https://www.python.org/downloads/)
(tick "Add Python to PATH"). Then in PowerShell:

```powershell
git clone https://github.com/maljabriii12-design/mscs640-nids-project.git
cd mscs640-nids-project
git config user.name "Your Name"
git config user.email "you@example.com"     # the email on your GitHub account
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

The first `git clone` or `git push` opens a GitHub window; sign in with **your own** account
and click **Authorize**. Never commit with someone else's name or credentials.

## 2. Check that it runs

```powershell
python -m pytest -q
python main.py --config configs/smoke.json synth
python main.py --config configs/smoke.json all
python main.py serve --model models/smoke/nids_bundle.joblib   # http://127.0.0.1:5000
```

The smoke run uses synthetic flows and takes about 3 minutes. Its numbers must never be reported.
If any step fails, or a README instruction is unclear on a fresh machine, fix it: the TA will
clone and run this repository, and reproducibility is 15% of the grade.

## 3. Division of work

| Area | Owner |
|---|---|
| Data pipeline, models, training on the real dataset | Mohammed |
| Deployment of the dashboard (live URL) | Mohammed |
| Reproducibility check on a second machine, README fixes | Mesalam |
| Paper: Introduction and Related Work | Mesalam |
| Dashboard UI improvements (`webapp/templates/`) | Mesalam |
| Paper: Methodology, Results, Conclusion | Mohammed |
| Demo-day slides and talk | Both |

Update this table if the split changes; the paper should describe who did what.

## 4. Daily workflow

```powershell
git pull                          # get your teammate's latest work first
# ... make your changes ...
git add -A
git commit -m "Short description of the change"
git push
```

If `git pull` reports a conflict, open the file, keep the right version of the marked lines,
then `git add` and `git commit`.

## 5. Rules

- **Do not commit data or models.** `data/raw/`, `data/processed/`, `models/` and `reports/`
  are in `.gitignore`; the dataset is downloaded with `python main.py download`.
- **Citations must be real.** Every entry in `paper/references.bib` must exist and support the
  sentence that cites it. Fabricated or misattributed references count as academic misconduct.
- **Disclose AI use.** If you use an AI tool, tell your teammate what you used it for, so the
  "Statement on the Use of AI Tools" at the end of the paper is accurate for both of us.
- **No copied text** without quotation marks and a citation.
