# NyayaSetu: report outline and viva preparation

## Suggested report chapters
1. **Introduction**: the 1 July 2024 transition; the problem (people know old section numbers; legal text is
   hard to read; FIRs and documents still cite IPC/CrPC).
2. **Literature review**: retrieval-augmented generation (Lewis et al., 2020), BM25 (Robertson & Zaragoza, 2009),
   graph-based RAG (LightRAG, EMNLP 2025), legal NLP for Indian languages.
3. **Requirements**: functional (ask, convert, analyse PDFs, browse, graph, evaluate, auth) and
   non-functional (response under 2 s for retrieval, verified citations, works offline without an API key).
4. **System design**: architecture diagram from README; ER diagram below; sequence of an /api/ask request.
5. **Implementation**: one subsection per backend module (search, detector, rag, pdf_service, db).
6. **Results**: Evaluation Lab tables and charts; alignment accuracy; screenshots of every page.
7. **Conclusion and future work**: OCR, embeddings, held-out evaluation set, case law.

## ER diagram (SQLite)
```
users (id PK, name, email UNIQUE, role, password_hash, created_at)
  │1
  ├──< queries   (id PK, user_id FK, question, language, mode, top_section, sources, citation_score, latency_ms, created_at)
  ├──< documents (id PK, user_id FK, filename, size_bytes, pages, words, doc_type, references_count, analysis, page_text, summary, created_at)
  └──< activity  (id PK, user_id FK, kind, title, detail, created_at)
```

## Likely viva questions
- **What is RAG and why use it?** The LLM only sees retrieved statute text, so answers stay grounded and every
  claim can be cited. Without retrieval an LLM may invent section numbers.
- **What is BM25?** A ranking function that scores documents by term frequency with saturation (k1 = 1.5) and
  document-length normalisation (b = 0.75), weighted by inverse document frequency.
- **What does "hybrid" add over BM25?** Hindi/Hinglish vocabulary expansion, direct resolution of section
  references such as "IPC 420", and a boost from an old-code section to its 2023 successor. MRR rose from 0.393 to 0.825.
- **How do you stop hallucinated citations?** The prompt tells the model to cite only `[ACT N]` tags from the
  context, and `verify_citations()` checks every cited section against the corpus and the retrieved set.
- **Where do the mappings come from?** BNS↔IPC is the official NCRB table. CrPC→BNSS and IEA→BSA come from our
  aligner: TF-IDF cosine on headings (0.6) and body text (0.4), with a positional prior. It scores 94% and 92% on known pairs.
- **How is the PDF processed?** pypdf extracts text page by page. Regular expressions find statute references
  and entities. Keyword scoring classifies the document type. Text is chunked into 180-word windows for Q&A.
- **How are passwords stored?** PBKDF2-HMAC-SHA256 with 200,000 iterations and a random salt. Session tokens
  are HMAC-signed and expire after 24 hours.
- **Limitations?** No OCR for scanned PDFs, no Hindi statute text, and a small evaluation set.
