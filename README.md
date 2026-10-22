# PDF to Quiz with AI

> Turn any objective (MCQ) PDF into a practice test, take it, and get SSC-style scoring - with AI filling missing answer keys.

**By Akhil Binjola**

## Intro

**PDF to Quiz with AI** is a full-stack quiz generator built for competitive-exam aspirants (SSC CGL, UPSC, banking, etc.). Upload any objective PDF containing Q1. stem (a)(b)(c)(d) Ans.(x) questions and the app will:

1. **Parse** the PDF into structured MCQs (question + 4 options + answer) using pdfplumber, even when answers are missing.
2. **Auto-fill missing answers** by searching the web (DuckDuckGo / Wikipedia) and running a local 2B LLM (Qwen3.5-2B GGUF) to pick A/B/C/D - with evidence URLs shown for verification.
3. **Let you take the test** with timer, shuffle, paging (50 Qs/page), per-question review, and spaced-repetition modes (retry mistakes, weakest-first, unseen).
4. **Score it** SSC-style (+2 correct, -0.5 wrong, 0 skip) with per-question time tracking and analytics (score trend, accuracy by section, weakest questions).
5. **Persist progress** across restarts so you can resume exactly where you left off (e.g. Q40).

It ships in two flavors:
- **Streamlit app** (pp.py) - full-featured, with background AI fill, doubt chat, and analytics.
- **Web app** (web/index.html) - single-file, runs in any browser with no install (uses pdf.js + localStorage).

## Tech Stack

### Backend / Core (Python)
| Component | Technology |
|-----------|-----------|
| Language | Python 3.14 |
| Web framework | Streamlit >= 1.33 |
| PDF parsing | pdfplumber >= 4.0 |
| Web search | ddgs (DuckDuckGo) + Wikipedia API |
| HTTP client | requests >= 2.31 |
| LLM inference | llama-cpp-python (GGUF, Qwen3.5-2B) OR llama-server (OpenAI-style API) |
| Data handling | pandas >= 2.0, json |
| Persistence | Local JSON files (qa_cache, progress, history, attempts) |

### Frontend (Web App)
| Component | Technology |
|-----------|-----------|
| Markup | HTML5 |
| Styling | CSS3 (custom, dark theme) |
| Logic | Vanilla JavaScript (ES6+) |
| PDF parsing (browser) | pdf.js 3.11 (CDN) |
| Storage | localStorage |
| No build step / no framework | Single self-contained file |

### AI / ML
| Component | Technology |
|-----------|-----------|
| Local LLM | Qwen3.5-2B-Uncensored (GGUF Q4_K_M) |
| Inference engine | llama.cpp (via llama-cpp-python or llama-server) |
| Prompting | Completion + chat endpoints, temperature 0.0 for determinism |
| Web grounding | DuckDuckGo text search + Wikipedia snippets |
| Fallback | Word-overlap heuristic (always available) |
| Caching | SHA256-keyed QA cache (never re-solve) |

### Dev / Tooling
| Component | Technology |
|-----------|-----------|
| IDE | VS Code |
| Python env | CPython 3.14 |
| OS | Windows 11 |
| Version control | Git |

## Architecture

`
PDF-Quiz-Generator/
  app.py              # Streamlit UI (Load -> Key -> Test -> Analytics)
  parser.py           # PDF -> questions (regex + pdfplumber)
  solver.py           # Web search + 2B LLM answer suggestion + doubt chat
  scorer.py           # SSC-style scoring
  store.py            # Cache, progress, history, attempts persistence
  sample_questions.json
  web/
    index.html        # Browser-only version (pdf.js + localStorage)
  requirements.txt
  README.md
`

## Features
- **PDF parsing** (parser.py, pdfplumber): extracts Q1. stem (a)(b)(c)(d) Ans.(x) even when some answers are missing.
- **Answer key editor**: missing answers flagged REVIEW; one-click **Auto-fill with Web + 2B** (solver.py).
- **2B + web solver**: DuckDuckGo (ddgs) / Wikipedia snippets -> your local GGUF via llama-cpp picks A/B/C/D:
  - Default model: D:\models\HauhauCS\Qwen3.5-2B-Uncensored-HauhauCS-Aggressive\Qwen3.5-2B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf
  - Override: $env:MODEL_GGUF="path\to\other.gguf"
  - If llama-cpp/model missing, falls back to word-overlap heuristic. AI answers always flagged + show evidence URLs.
- **Quiz + scoring** (scorer.py): SSC default +2 / -0.5, skips = 0, unkeyed Qs excluded, timer, shuffle, per-question review, CSV export.
- **Instant feedback**: "Check Answer" button tells you right/wrong immediately; if wrong, AI explains why the correct option is right and your pick is wrong.
- **Doubt chat**: ask the AI about any question (grounded on web evidence).
- **Spaced repetition**: retry mistakes, weakest-first, unseen filters.
- **Doubt chat**: ask the 2B model about any question (grounded on web evidence).
- **Analytics**: score trend, accuracy per attempt, avg time per Q, accuracy by section, weakest questions.

## Run

### Streamlit (full features)
`powershell
cd D:\projects\PDF-Quiz-Generator
pip install streamlit pdfplumber requests ddgs pandas
streamlit run app.py
`
Open the URL shown (usually http://localhost:8501). Upload any SSC PDF in the UI, or tick the bundled sample.

### Web app (no install)
Open web/index.html in any modern browser. Upload a PDF or load the combined JSON.

## Local model (for Auto-fill missing answers)

You only need a model that can search the web and run in llama-server. Run any GGUF in llama-server (port 8080) and the app will use it via the OpenAI-style API. No model loading in Python required.
pip install llama-cpp-python compiles from source on Windows and can take 10+ min.
Faster: install a prebuilt wheel, e.g. from https://github.com/abetlen/llama-cpp-python/releases
matching your Python (3.14) + CPU/CUDA, then:
`powershell
pip install <downloaded-wheel>.whl
="D:\models\HauhauCS\Qwen3.5-2B-Uncensored-HauhauCS-Aggressive\Qwen3.5-2B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf"
streamlit run app.py
`
Without it the app still works (PDF answers + manual keys + heuristic). You can also run llama-server on port 8080 instead.

## Files
- pp.py - Streamlit UI (Load -> Key -> Test -> Analytics)
- parser.py - PDF -> questions
- solver.py - web + 2B suggestions + doubt chat
- scorer.py - scoring
- store.py - cache, progress, history, attempts
- sample_questions.json - 10 SSC-style Qs to try without a PDF
- web/index.html - browser-only version
