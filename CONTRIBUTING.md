# Contributing

Team: **Mohammed Amer Al-Jabri** ([@maljabriii12-design](https://github.com/maljabriii12-design)) and
**Mesalam Abdullah Al-Nabit** ([@malnabit](https://github.com/malnabit)). The course requires that both members
commit to this repository, so each of us pushes our own work from our own machine.

> **ملخص بالعربي لمسلم:** مهامك في القسم 3 أدناه (اختبار التشغيل، والمقدمة والدراسات السابقة في
> الورقة، وفقرتك في الإفصاح عن الذكاء الاصطناعي، وتحسين اللوحة اختياريًا، ونصف الشرائح). كل مهمة لها
> «تعريف الإنجاز». إذا استخدمت أداة ذكاء اصطناعي، أعطها النص الجاهز في القسم 6 كما هو، فهو يشرح لها
> المشروع وما يجوز وما لا يجوز. وارفع كل عمل بحسابك أنت (`malnabit`).

## 1. One-time setup (Windows)

Install [Git](https://git-scm.com) and [Python 3.12](https://www.python.org/downloads/)
(tick "Add Python to PATH"). Then in PowerShell:

```powershell
git clone https://github.com/maljabriii12-design/mscs640-nids-project.git
cd mscs640-nids-project
git config user.name "Mesalam Abdullah Al-Nabit"
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

## 3. Current state and tasks

**Done (Mohammed):** data pipeline, all ten days, models, the final run (XGBoost + class bias,
test macro-F1 0.864 over 15 classes; see [`docs/EXPERIMENTS.md`](docs/EXPERIMENTS.md)), the live
dashboard at <https://ids.batch5ai.lol> (Arabic/English), and the paper's Methodology. The
Results discussion and Conclusion are Mohammed's and will be finished after the tuning run.

**Mesalam's tasks**, in this order:

| # | Task | Files | Definition of done |
|---|---|---|---|
| M1 | **Reproducibility check** on your own Windows machine (15% of the grade: the TA will do exactly this) | `README.md`, new `docs/REPRODUCIBILITY.md` | Section 2 runs end to end on a fresh clone. Record in `docs/REPRODUCIBILITY.md` your OS, Python version, the time each step took and the `pytest` result. Fix any README step that was wrong or unclear. Commit and push. |
| M2 | **Introduction and Related Work** of the paper | `paper/main.tex` (section `Introduction`), `paper/references.bib` | The existing text is reviewed and improved in your own words. Every `\cite{}` points to a real paper that you opened and that supports the sentence. You may add 2-4 more references on ML-based intrusion detection on CSE-CIC-IDS2018 (e.g. deep learning or boosting studies), each checked the same way. Do not change other sections or any number. **Space budget:** the paper is exactly 4 pages (checked on Overleaf); you have about a quarter of a column (~12 lines) to spare, references included, so cut elsewhere in the Introduction if you add more. |
| M3 | **Your part of the AI-use statement** | `paper/main.tex` (section `Statement on the Use of AI Tools`) | Replace the red `\fillin{M.~A.~Al-Nabit: ...}` with one or two true sentences about how you used AI tools (or that you did not). |
| M4 | *(optional)* **Dashboard improvement** | `webapp/templates/` | One visible improvement, e.g. a severity doughnut chart or an "About this project" panel. Must keep `python -m pytest -q` green, keep the JBJ dark style, and give every new text both languages (see Section 5). Tell Mohammed before pushing; he redeploys the server. |
| M5 | **Demo-day slides** (with Mohammed) | shared deck (not in the repo) | Your half: problem, dataset, related work and the live demo walk-through. |

## 4. Daily workflow

```powershell
git pull                          # get your teammate's latest work first
# ... make your changes ...
python -m pytest -q               # must pass before every push
git add -A
git commit -m "Short description of the change"
git push
```

If `git pull` reports a conflict, open the file, keep the right version of the marked lines,
then `git add` and `git commit`. Make small commits, one per task or sub-task, so the history
shows who did what.

## 5. Rules

- **Do not commit data or models.** `data/raw/`, `data/processed/`, `models/` and `reports/`
  are in `.gitignore`; the dataset is downloaded with `python main.py download`.
- **Do not retrain or change results.** The numbers, tables and figures in the paper come from
  `paper/generated/` and `paper/figures/`, written by `python main.py train`; never edit them by
  hand. Do not edit `deploy/` or the server.
- **Citations must be real.** Every entry in `paper/references.bib` must exist and support the
  sentence that cites it. Fabricated or misattributed references count as academic misconduct.
  An AI tool may suggest references; you must open each one and confirm it before using it.
- **No copied text** without quotation marks and a citation.
- **Disclose AI use.** If you use an AI tool, say what for in M3.
- **Dashboard text is bilingual.** Templates mark text with `data-i18n="key"`; the Arabic string
  for each key lives in the `T.ar` table in `webapp/templates/base.html`. English is the fallback
  inside the HTML. Never write `{#` inside a template (Jinja treats it as a comment).

## 6. Prompt to give your AI assistant

If you use an AI tool (Claude Code, ChatGPT, Copilot...), start it from the repository folder and
paste this first:

```text
You are helping Mesalam Abdullah Al-Nabit, one of two students on the MSCS640 project
"Network Intrusion Detection on CSE-CIC-IDS2018" (repository: this folder). Read README.md,
CONTRIBUTING.md and docs/EXPERIMENTS.md before doing anything.

Mesalam's tasks are M1-M5 in CONTRIBUTING.md, Section 3. Work only on the task I name, and
stop when its "Definition of done" is met.

Rules you must follow:
1. Do not retrain models, run `main.py train`/`all` on the real data, or edit anything in
   paper/generated/, paper/figures/, deploy/, configs/ or nids/ unless I explicitly ask.
2. Never invent a reference, a number or a result. For any citation you suggest, give the
   full title, authors, venue, year and DOI or URL so I can open and verify it myself; mark
   anything you are not sure exists as UNVERIFIED.
3. Write paper text in clear academic English, in IEEE style, in my voice. The paper is
   exactly 4 pages with only ~12 lines to spare (new references included), so keep the
   Introduction and Related Work to about one column and cut as much as you add.
4. Run `python -m pytest -q` before suggesting a commit; it must pass.
5. Do not commit or push for me; show me the diff and the commit message, I will commit with
   my own GitHub account (malnabit).
6. Remind me to describe your help truthfully in task M3.
```

## 7. Review notes for Mesalam (2026-10-11)

> **ملخص بالعربي:** راجع محمد عملك. اختبار التشغيل ممتاز، والمرجعان الجديدان صحيحان (تحققنا منهما في
> سجل الناشر)، والمقدمة جيدة. المطلوب منك الآن: (1) تصحيح جملتك في الإفصاح، لأنها تذكر رسم الخطورة في
> لوحة التحكم ولم يُرفع أي تعديل عليها؛ (2) إضافة حلّي مشكلتي ويندوز اللتين وجدتهما إلى خطوات الإعداد؛
> (3) إضافة مرجعيك إلى الشريحة 4 والتدرّب على شرائحك. الورقة الآن 4 صفحات بالضبط، فلا تُطِل النص.

**Done well**
- M1: clear `docs/REPRODUCIBILITY.md`; fresh Windows 11 clone, 7/7 tests, smoke run and dashboard OK.
- M2: Introduction reads well. Both new references are real and match the publisher's record
  (Crossref): `karatas2020` (IEEE Access 8, 32150-32162) and `lin2019` (CLOUD 2019, LNCS, 161-176);
  the 96.2% accuracy you quote is in the Springer abstract. No numbers or other sections changed.

**Please fix**

| # | Note | What to do |
|---|---|---|
| R1 | Your AI-use sentence says you used Claude "to add the severity chart to the dashboard", but no dashboard change is in the repository. | Either push the chart (task M4 rules: tell Mohammed first, `pytest` green, both languages) or delete that clause. Keep "to draft his demo-day slides" only if you actually edited the slides. The statement must match what you did. |
| R2 | M1 asked you to fix README steps that were wrong or unclear. You found two real gaps (no Python on a fresh Windows; `activate` blocked by the execution policy). | Add both fixes as a short note in Section 1 of this file (and the README setup section). |
| R3 | Slide 4 (Related work) still lists only the original four papers. | Add your two references (Karatas et al. 2020; Lin et al. 2019) to slide 4 in both decks (you have Editor access), then practise slides 2, 3, 4 and 12. |

**Space budget:** with your additions the paper reached 5 pages; Mohammed trimmed about 18 lines
from his own sections, so it is exactly 4 pages again (checked on Overleaf, 0 errors) with about
10 lines to spare. If R1 changes your sentence, keep it the same length or shorter.
