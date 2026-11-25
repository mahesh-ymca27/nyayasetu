# NyayaSetu (न्याय सेतु): AI Legal Assistant for India's New Criminal Laws

On **1 July 2024** India replaced the Indian Penal Code (IPC), the Code of Criminal Procedure (CrPC) and the
Indian Evidence Act (IEA) with the **Bharatiya Nyaya Sanhita (BNS)**, **Bharatiya Nagarik Suraksha Sanhita
(BNSS)** and **Bharatiya Sakshya Adhiniyam (BSA)**. Citizens, police and lawyers still think in old section
numbers. NyayaSetu answers legal questions in English, Hindi or Hinglish with **verified citations**, converts
old sections to new ones, and **reads legal PDFs** (FIRs, judgments, notices) to find and convert every reference.

## Features

| Module | What it does |
|---|---|
| **Dashboard** | Corpus statistics, BNS chapter chart, offence classification (cognizable/bailable), usage analytics, activity feed |
| **AI Legal Assistant** | Retrieval-augmented answers streamed from Groq; Hindi/Hinglish support; voice input; citation verification; offline fallback |
| **IPC → BNS Converter** | Old ↔ new lookup with word-level diff of the two texts, punishment/bail facts, bulk conversion of pasted passages, full correspondence table |
| **Document Analyzer** | PDF/TXT upload → page-wise text extraction, document-type detection, legal-reference detection and conversion, entity extraction (dates, ₹ amounts, FIR no., police station, phone, email), AI summary with timeline, Q&A over the document, export to TXT / Markdown / JSON |
| **Law Library** | Browse all 2,354 sections of the six codes by chapter |
| **Knowledge Graph** | Interactive force-directed graph of codes → chapters → sections with old→new succession edges |
| **Evaluation Lab** | Benchmark of TF-IDF vs BM25 vs NyayaSetu Hybrid retrieval (Hit@k, MRR) and accuracy of the automatic code aligner |
| **Auth** | Register / sign in (PBKDF2 password hashing, HMAC-signed tokens) |

## Quick start (Windows / macOS / Linux)

Requires Python 3.10+.

```bash
cd nyayasetu
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env        # macOS/Linux: cp .env.example .env
# open .env and paste your Groq key: GROQ_API_KEY=gsk_...
python run.py
```

Open **http://localhost:8000** and sign in with the demo account **demo@nyayasetu.in / demo1234**.
Interactive API documentation (Swagger) is at **http://localhost:8000/docs**.

Without a Groq key the app still works in *offline mode*: retrieval, conversion, PDF analysis, graph and
evaluation are all local; only the written AI answers and AI summaries need the key.

**Running the tests:** `pip install -r requirements-dev.txt`, then `python -m pytest`. The tests use a
temporary database and never call Groq, so they don't touch your data or your API quota. GitHub Actions runs
them on Linux and Windows for every pull request.

**Demo script (5 minutes):** Dashboard → Converter (IPC 420, then "Load sample" → Detect & convert) →
Assistant (ask a Hindi question) → Document Analyzer ("Try a sample FIR", open each tab) → Knowledge Graph →
Evaluation Lab.

## Architecture

```
Browser (HTML/CSS/JS SPA, SVG charts, canvas graph)
   │  REST + Server-Sent Events (streaming answers)
FastAPI backend (backend/main.py)
   ├── search.py      BM25 / TF-IDF index, Hindi-Hinglish vocabulary, hybrid ranking
   ├── detector.py    regex detection of "u/s 420/406 IPC", "S. 154 Cr.P.C.", "धारा 302" … + conversion
   ├── rag.py         prompt building, Groq streaming, citation verification, document summaries
   ├── pdf_service.py pypdf extraction, document classification, entity extraction, chunking
   ├── graph.py       knowledge-graph views
   ├── evaluation.py  retrieval benchmark
   ├── llm.py         Groq OpenAI-compatible client (standard library only)
   └── db.py          SQLite: users, queries, documents, activity
data/  sections.json · mappings.json · classification.json · eval_questions.json
```

### How an answer is produced
1. **Query understanding**: Hindi/Hinglish/colloquial words are expanded to statutory terms
   (e.g. *dhokha → cheating*, *दहेज → dowry*); with a key, Groq also rewrites the query into keywords.
2. **Hybrid retrieval**: BM25 over section text (headings weighted ×3), plus a boost for any section the
   user names explicitly ("IPC 420") and its 2023 successor, plus a mapping boost that lifts the new-code
   section whenever an old-code section ranks well.
3. **Generation**: the top sections (with punishment, cognizable/bailable status and predecessor) go to
   Groq with instructions to answer only from that context and cite as `[BNS 318]`.
4. **Verification**: every citation in the answer is checked to exist in the corpus and to be among the
   retrieved sources; the UI shows "4/4 citations verified" and marks ungrounded ones in red.

## Results (Evaluation Lab, 42 labelled questions)

| Method | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---|---|---|---|
| TF-IDF keyword | 17% | 31% | 41% | 0.273 |
| BM25 | 26% | 50% | 55% | 0.393 |
| **NyayaSetu Hybrid** | **71%** | **93%** | **100%** | **0.825** |

Automatic alignment (CrPC→BNSS, IEA→BSA) against well-known transitions: **17/18 (94%)** and **11/12 (92%)**.

Note: the Hindi/Hinglish vocabulary was written with this question set in view, so these numbers are
optimistic. A larger held-out question set is listed under future work.

## Data sources and credits

- **[kanoonhq/open-laws](https://github.com/kanoonhq/open-laws)** (CC0): full text of IPC, CrPC, IEA, BNS, BNSS, BSA.
- **[JasonTKG/bns-sections](https://github.com/JasonTKG/bns-sections)** (CC0): official NCRB BNS↔IPC
  correspondence table and the BNSS First Schedule classification of offences.
- Statutory text is from the Gazette of India; reproduction of Acts is permitted under Copyright Act 1957 s.52(1)(q).
- LLM inference: [Groq](https://groq.com).
- Retrieval ideas inspired by [LightRAG](https://github.com/HKUDS/LightRAG) (graph + keyword dual-level retrieval).

To rebuild `data/` from the raw datasets:
`python scripts/build_corpus.py --open-laws <open-laws/data> --bns <bns-sections>`

## Limitations and future work

- Scanned PDFs without a text layer need OCR (e.g. Tesseract), which is not included yet.
- Hindi statute text is not in the dataset; Hindi answers are produced by the LLM from English text.
- Mappings for BNSS and BSA are automatic (≈92–94% on the check set) and are labelled as such in the UI.
- Future work: OCR, semantic embeddings, a larger held-out evaluation set, case-law search, and a mobile app.

**Disclaimer:** NyayaSetu provides legal information, not legal advice.
