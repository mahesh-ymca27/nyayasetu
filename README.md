# NyayaSetu (न्याय सेतु): AI Legal Assistant for India's New Criminal Laws

[![tests](https://github.com/mahesh-ymca27/nyayasetu/actions/workflows/tests.yml/badge.svg)](https://github.com/mahesh-ymca27/nyayasetu/actions/workflows/tests.yml)

On **1 July 2024** India replaced the Indian Penal Code (IPC), the Code of Criminal Procedure (CrPC) and the
Indian Evidence Act (IEA) with the **Bharatiya Nyaya Sanhita (BNS)**, the **Bharatiya Nagarik Suraksha Sanhita
(BNSS)** and the **Bharatiya Sakshya Adhiniyam (BSA)**. Citizens, police and lawyers still think in the old
section numbers, and FIRs, judgments and notices still cite them.

NyayaSetu answers legal questions in English, Hindi or Hinglish with **verified citations**, converts old
sections to new ones, **reads legal PDFs**, and analyses an incident with **its own trained model**: likely
charges, how serious they are, and the person's rights and options.

Legal information, not legal advice.

## Features

| Page | What it does |
|---|---|
| **Dashboard** | Corpus statistics, BNS sections per chapter, cognizable / bailable offences, trial courts, new offences in BNS, usage and activity |
| **AI Legal Assistant** | Retrieval-augmented answers streamed from Groq, in English, Hindi or Hinglish; every cited section is checked against the law text; voice input and read-aloud; offline answer if Groq is unavailable |
| **Case Analyzer** | Describe an incident; a trained model, fact rules and Groq together give the likely charges (with reasons), sections ruled out, punishment and bail, and remedies for the user's side (accused or complainant) |
| **IPC → BNS Converter** | Old ↔ new lookup with a word-level diff of the two texts and punishment / bail facts; bulk conversion of a pasted passage; the full correspondence table |
| **Document Analyzer** | PDF / TXT upload: text per page, document type, every legal reference found and converted (including "Section 154 of the Code" in judgments), dates, ₹ amounts, FIR numbers, police stations; AI summary, questions about the document, export to TXT / Markdown / JSON |
| **Law Library** | All 2,354 sections of the six codes, by chapter |
| **Knowledge Graph** | Interactive graph of codes → chapters → sections with old → new edges |
| **Evaluation Lab** | Retrieval benchmark, the trained model's test results, and model vs Groq vs hybrid |
| **Settings & login** | Groq connection and model; register / sign in (PBKDF2 password hashing, signed tokens) |

## Quick start

Requires Python 3.10+ (tested on 3.11 and 3.12, Windows and Linux).

```bash
git clone https://github.com/mahesh-ymca27/nyayasetu.git
cd nyayasetu
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS / Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env               # macOS / Linux: cp .env.example .env
# edit .env:  GROQ_API_KEY=gsk_...   (free key: https://console.groq.com/keys)
python run.py
```

Open **http://localhost:8000** and sign in with **demo@nyayasetu.in / demo1234**. API documentation (Swagger)
is at **http://localhost:8000/docs**.

Without a Groq key the app runs in **offline mode**: search, conversion, PDF analysis, the trained model, the
graph and the benchmarks all work locally; only the written AI answers, summaries and the Groq checks need
the key.

## How it works

```
Browser (HTML / CSS / JavaScript, SVG charts, canvas graph)
   │  REST + Server-Sent Events (streamed answers)
FastAPI backend
   ├── search.py         BM25 / TF-IDF index, Hindi-Hinglish vocabulary, hybrid ranking
   ├── detector.py       finds "u/s 420/406 IPC", "S. 154 Cr.P.C.", "धारा 302", "Section 154 of the Code" and converts them
   ├── rag.py            prompts, Groq streaming, citation verification, document summaries
   ├── case_analyzer.py  layered pipeline: understand → candidates → check → punishment → relief → verify
   ├── predictor.py      loads the trained Section Predictor and maps IPC predictions to BNS
   ├── ml/section_model.py  training, threshold tuning and evaluation of the model
   ├── pdf_service.py    PDF / TXT extraction, document type, entities, chunking
   ├── llm.py            Groq client (retry on dropped connections, retired-model fallback)
   ├── graph.py · evaluation.py · corpus.py · config.py
   └── db.py             SQLite: users, questions, documents, activity
data/    sections.json · mappings.json · classification.json · eval_questions.json
models/  section_predictor.joblib · section_predictor_metrics.json
```

### AI Legal Assistant (retrieval-augmented generation)
1. **Understand:** Hindi / Hinglish / everyday words are expanded to legal terms (*dhokha → cheating*,
   *दहेज → dowry*); Groq also rewrites the question into keywords (at most 4 seconds).
2. **Retrieve:** BM25 over the section texts, plus a boost for sections named in the question ("IPC 420") and
   their 2023 successors, and an old → new mapping boost.
3. **Generate:** Groq answers only from the retrieved sections and cites them as `[BNS 318]`.
4. **Verify:** each citation is checked against the corpus and the retrieved sources ("4/4 citations verified").

### Case Analyzer (trained model + rules + Groq)
Each layer does what it is best at, and the next layer checks it:

| Layer | By | Job |
|---|---|---|
| 1. Understand | Groq (rules offline) | Summary, the user's role, facts (death, injury, damage, intoxication, vehicle, false accusation…), and a formal court-style rewrite of the facts |
| 2. Candidates | **Trained model** + search + fact rules | The model reads the formal rewrite, which is closer to the judgments it was trained on |
| 3. Check | Fact rules, then Groq | Rules remove sections whose ingredients are missing (no death → no BNS 106); Groq judges only the candidates; unproven false-claim sections against the other side are "depends on evidence" |
| 4. Punishment & bail | BNSS First Schedule | From the official table, never from the LLM |
| 5. Relief | Corpus | E.g. anticipatory bail (BNSS 482), arrest rules (BNSS 35, 47), settlement (BNSS 359), false charge (BNS 248), quashing (BNSS 528); FIR rights for complainants |
| 6. Verify | Citation checker | Every cited section must be one of the allowed sections |

## The trained model: Section Predictor

- **Data:** IL-TUR Legal Statute Identification (ACL 2024): 42,750 training, 10,181 dev and 13,019 test case
  facts from Indian judgments, labelled with IPC sections (100 labels = 98 sections after merging sub-sections
  such as 376 and 376(2)).
- **Model:** TF-IDF (word 1–2 grams, 60,000 features) + one logistic-regression classifier per section
  (one-vs-rest), class-weighted; decision threshold tuned on the dev set (0.6).
- **Training:** 7 minutes on a laptop CPU (Intel i5-1235U, 10 threads); 21.5 MB model.
- **Train it yourself:** `pip install -r requirements-ml.txt`, then `python -m ml.train_section_predictor`
  (`--check` shows the labels without training; `--quick` trains on 5,000 cases).

## Results

**Section Predictor**, on 13,019 test cases never seen in training:

| Macro-F1 | Micro-F1 | Top-1 correct | Hit@3 | Recall@5 |
|---|---|---|---|---|
| **39.95%** | 49.16% | 64.37% | 81.84% | 57.38% |

For reference, the IL-TUR paper reports a macro-F1 of 28.08% for its LSI baseline. The setups are close but
not identical (98 merged labels here, threshold tuned on dev), so this is a comparison, not a claim of a new
state of the art.

**Retrieval** (AI Assistant), on 42 labelled questions in English, Hindi, Hinglish and section-number form:

| Method | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---|---|---|---|
| TF-IDF keyword | 17% | 31% | 41% | 0.273 |
| BM25 | 26% | 50% | 55% | 0.393 |
| **NyayaSetu Hybrid** | **71%** | **93%** | **100%** | **0.825** |

The Hindi / Hinglish vocabulary was written with this question set in view, so these numbers are optimistic.

**Automatic code alignment** (CrPC → BNSS, IEA → BSA) against well-known transitions: **17/18 (94%)** and
**11/12 (92%)**. A few merged sections (e.g. CrPC 41A → BNSS 35) are added by hand and labelled "curated".

**Model vs Groq vs hybrid**: which IPC sections apply, on 40 random IL-TUR test cases with known answers
(seed 7). Example-based scores, averaged over cases:

| Method | Precision | Recall | F1 | Micro-F1 | Sections per case | Not a real IPC section |
|---|---|---|---|---|---|---|
| **Trained model only** | 48.8% | **53.1%** | **44.9%** | **51.8%** | 4.7 | 0 |
| Groq only (`openai/gpt-oss-120b`) | 25.4% | 22.8% | 22.0% | 26.9% | 3.3 | 1 |
| Hybrid: model proposes 10, Groq chooses | **57.3%** | 35.1% | 37.8% | 43.4% | 2.5 | 0 |

- The trained model is about **twice as accurate as the LLM alone** (F1 44.9% vs 22.0%), and the LLM alone
  named one section that does not exist.
- The hybrid is the **most precise** (57.3%): the sections it names are most often right. It names fewer
  sections, so it misses more, and its recall is capped because the model's top-10 candidates contain 70% of the
  correct sections. The Case Analyzer favours precision, because naming a wrong charge misleads a user more than
  leaving a doubtful one under "depends on the evidence".
- Caveats: only 40 cases, and Groq saw the first 3,000 characters of each case while the model read the full
  text. Reproduce with `python -m ml.evaluate_case_pipeline --n 40` (needs the Groq key, about an hour on the
  free tier); the results also appear in the Evaluation Lab.

## Tests

`pip install -r requirements-dev.txt`, then `python -m pytest` (90 tests). They use a temporary database and
never call Groq. GitHub Actions runs them on Linux and Windows for every pull request, and also builds and
starts the deployment image (`docker` job).

## Deploying

Free on Hugging Face Spaces (2 vCPU, 16 GB RAM): see [DEPLOY.md](DEPLOY.md).

## Project structure

```
backend/        FastAPI app and all services (see "How it works")
frontend/       single-page web app (no build step); samples/ has a fictional FIR for demos
ml/             training and evaluation scripts for the Section Predictor
scripts/        corpus builder and sample-document generators
data/           the legal corpus built from the open datasets
models/         the trained model and its metrics
tests/          pytest suite
deploy/         Hugging Face Space files
docs/           report outline and viva notes
```

## Data sources and credits

- **[kanoonhq/open-laws](https://github.com/kanoonhq/open-laws)** (CC0): full text of IPC, CrPC, IEA, BNS, BNSS and BSA.
- **[JasonTKG/bns-sections](https://github.com/JasonTKG/bns-sections)** (CC0): the official NCRB BNS ↔ IPC
  correspondence table and the BNSS First Schedule classification of offences.
- **[IL-TUR](https://huggingface.co/datasets/Exploration-Lab/IL-TUR)** (Joshi et al., ACL 2024): the LSI task
  used to train the Section Predictor, under the dataset's terms of use.
- Statutory text is from the Gazette of India; reproduction of Acts is permitted under Copyright Act 1957 s.52(1)(q).
- LLM inference: [Groq](https://groq.com) (`openai/gpt-oss-120b`).
- Retrieval ideas inspired by [LightRAG](https://github.com/HKUDS/LightRAG).

To rebuild `data/` from the raw datasets:
`python scripts/build_corpus.py --open-laws <open-laws/data> --bns <bns-sections>`

## Limitations and future work

- The Section Predictor learned from formal judgment English and knows only the 98 most common IPC sections;
  short everyday descriptions are harder for it (the Case Analyzer's rewrite and checks reduce this).
- Scanned PDFs need OCR, which is not included.
- There is no Hindi statute text in the data; Hindi answers are written by the LLM from English text.
- BNSS and BSA mappings are mostly automatic (92–94% on the check set) and labelled as such.
- Free deployment has no permanent storage: users and uploads reset when the Space restarts.
- Future work: OCR, semantic embeddings, a fine-tuned InLegalBERT model, a larger held-out question set,
  PostgreSQL with pgvector, and case-law search.
