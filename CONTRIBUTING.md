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

Two problems seen on a fresh Windows 11 machine (task M1): if `python` opens the Microsoft Store,
Python is not installed yet, so run `winget install --id Python.Python.3.12 -e --scope user` and
reopen PowerShell; if `.venv\Scripts\activate` fails with "running scripts is disabled on this
system", run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once and activate again.

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

- **Do not commit data or new models.** `data/raw/`, `data/processed/`, `models/` and `reports/`
  are in `.gitignore`; the dataset is downloaded with `python main.py download`. The one
  exception is the final model (`models/nids_bundle.joblib`, `demo_test_flows.csv`,
  `SHA256SUMS`), which ships so the TA can score the hidden test set; never overwrite or
  re-commit it, and keep the exact versions in `requirements.txt`.
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

**Update 2026-10-12:** R2 and R3 were done by Mohammed (Windows fixes added to Section 1 and the
README; both references added to slide 4 in both decks). **Only R1 is left for you**, since the
AI-use sentence describes your own work.

**Space budget:** with your additions the paper reached 5 pages; Mohammed trimmed about 18 lines
from his own sections, so it is exactly 4 pages again (checked on Overleaf, 0 errors) with about
10 lines to spare. If R1 changes your sentence, keep it the same length or shorter.

**Reply from Mesalam (2026-10-12):** R1 done. I deleted the dashboard-chart clause, so my
AI-use sentence now ends "He also used it to draft his demo-day slides." (true: I used Claude on
the slides). No dashboard change is pushed, so no redeploy is needed. Compiled with pdfLaTeX:
4 pages, no errors or undefined references, about 12 lines to spare. Thank you for R2 and R3.

## 8. Next steps for Mesalam (2026-10-12)

> **ملخص بالعربي:** كل مهامك (M1 إلى M3 والملاحظات R1 إلى R3) انتهت، والورقة النهائية 4 صفحات. المتبقي:
> (1) التدرّب على شرائحك 2 و3 و4 و12 وعلى العرض المباشر؛ (2) الاستعداد للأسئلة المتوقعة؛ (3) سؤال
> الدكتور عن الأمور الأربعة غير المذكورة في صفحة المشروع، إن لم يسأله محمد.

**Status:** all your tasks (M1-M3, R1-R3) are done. The final paper is 4 pages (Overleaf, 0 errors);
the PDF and both slide decks (Arabic and English, PDF and PowerPoint) are in the shared course folder.

| # | Task | Details |
|---|---|---|
| N1 | Rehearse your slides | Slides 2 (problem), 3 (data), 4 (related work, now six references) and 12 (live demo), in both languages. Speaker notes are under each slide. Aim for about one minute per slide. |
| N2 | Rehearse the live demo | Open https://ids.batch5ai.lol one minute before the talk (the first request after a restart takes about 17 s). Upload the 5,000-flow demo sample, show the threat report, switch the language once, and point out the "anomalous but classified Benign" flows. |
| N3 | Prepare for questions | Likely: why macro-F1 and not accuracy; why XGBoost and not the Random Forest that scored higher on test (selection on validation only); how SMOTE is kept out of the test set (training split only); what the autoencoder adds; 14 attack types vs 15 classes (Benign + 14). The cover slide's notes and slide 14's notes list them. |
| N4 | Questions for the instructor (whoever of us sees him first) | (a) the date of week 13 (final submission and demo day); (b) how to submit (GitHub link, file upload or email); (c) the hidden test set: does the TA run `python main.py predict` on our repository, or do we send a predictions file, and in which format; (d) the grading table on the project page adds up to 85, not 100. |

**Note from Mesalam on N4 (d) (2026-10-12):** the grading table on the project page
(<https://courses.karbab.net/mscs640/project.html>, "Evaluation Criteria") now adds up to 100,
and the page states "Total points: 100": Data Pipeline 15, Methodology 15, Reproducibility 15,
The Website 15, The Paper 15, Presentation 15, Performance Rank 10. The Presentation row
(demo-day talk, live demo and Q&A) may have been added after you read it. So (d) no longer
needs to be asked; questions (a)-(c) remain.

**Mohammed:** confirmed. The table was already 6 x 15 + 10 = 100; the "85" in (d) was a
counting mistake on our side, not a change to the page. (d) is closed.

**Mesalam (2026-10-12):** I extended my AI-use sentence to disclose today's help as well (drafting
my replies to the review notes, and re-checking the page count and a fresh-clone run). It adds
one line; pdfLaTeX still gives 4 pages with 0 errors and about 10 lines to spare.

**Mohammed (2026-10-12), final review of the paper:** fixed two section references that pointed
to Sampling instead of Cleaning (new label `sec:cleaning`); softened "the main reason" to "the
likely reason" for the validation/test gap; added the slides to my own AI-use sentence; and in
your Introduction changed "a class-weighted loss" to "an improved loss function" for Lin et al.
2019, which is what their abstract says. Overleaf: 4 pages, 0 errors, 0 warnings. 8 of the 13
references were re-confirmed on Crossref today; the other five (SMOTE, XGBoost, LightGBM, Adam,
scikit-learn) are the standard citations and match their published records.

## 9. Project complete (2026-10-12)

> **ملاحظة لمسلم بالعربي:** انتهى المشروع من الجانب التقني بالكامل، شكرًا على عملك. كل المطلوب في صفحة
> المشروع جاهز: الكود والنموذج المدرَّب داخل المستودع، والموقع، والورقة النهائية (4 صفحات بلا أخطاء)،
> والشرائح بالعربية والإنجليزية. **لا تعدّل أي ملف بعد الآن** إلا بعد الاتفاق مع محمد.
>
> **الخطوة التالية:**
> 1. **اسأل الدكتور** (إن رأيته قبل محمد): موعد الأسبوع 13، وطريقة التسليم، وكيف تُقيَّم مجموعة الاختبار
>    المخفية. وأخبر محمد بالإجابة فورًا.
> 2. **تدرّب على شرائحك** 2 و3 و4 و12 وعلى العرض المباشر (القسم 8، N1 إلى N3).
> 3. **بروفة مشتركة** مع محمد قبل يوم العرض، على العرض كاملًا والأسئلة المتوقعة (ملاحظات الشريحة 14).

**Status:** all deliverables on the project page are done and verified on 2026-10-12.

| Deliverable | Where | Checked |
|---|---|---|
| Repository (`main.py`, `requirements.txt`, `README.md`, commits from both of us) | this repository | fresh clone: 7/7 tests, checksums OK |
| Trained model for the hidden test set | `models/nids_bundle.joblib`, run `python main.py predict <csv>` | fresh clone, no training: macro-F1 0.879 on the demo sample |
| Paper (4 pages, IEEE, AI-use statement) | `paper/` and Overleaf | 4 pages, 0 errors, 0 warnings |
| Live dashboard | https://ids.batch5ai.lol | live, scores uploads correctly |
| Slides (Arabic and English) | shared decks and the course folder | final versions exported |

**Rules from now on:** do not change the paper, the model, `requirements.txt` or the server
without agreeing with Mohammed first; the submitted state is the current `main` branch.

**Next steps:** (1) ask the instructor the three open questions in Section 8, N4 (a)-(c), and tell
Mohammed the answers; (2) rehearse your slides and the live demo (N1-N3); (3) one joint rehearsal
before demo day.
