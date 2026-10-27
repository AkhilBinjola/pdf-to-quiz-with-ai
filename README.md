# PDF to Quiz with AI

> Turn any objective (MCQ) PDF into a timed practice test with SSC-style scoring, and let a small local LLM fill in missing answer keys.

**By Akhil Binjola**

<!-- Add a screenshot or GIF here: ![demo](docs/demo.gif) -->

## Overview

Built for competitive-exam aspirants (SSC CGL, UPSC, banking, etc.). Upload a PDF with questions in the form `Q1. stem (a)(b)(c)(d) Ans.(x)` and the app will:

1. **Parse** the PDF into structured MCQs (question, four options, answer) using `pdfplumber` and regex, even when answers are missing.
2. **Auto-fill missing answers** by searching the web (DuckDuckGo / Wikipedia) and asking a local ~2B LLM to pick A/B/C/D. Evidence URLs are shown so you can verify, and AI-filled answers are always flagged.
3. **Run the test** with a timer, shuffle, paging (50 questions per page), per-question review, and spaced-repetition modes (retry mistakes, weakest-first, unseen).
4. **Score it** SSC-style (+2 correct, -0.5 wrong, 0 skip) with per-question time tracking and analytics.
5. **Save progress** across restarts so you can resume exactly where you left off.

It comes in two versions:

- **Streamlit app** (`app.py`): full features, including background AI fill, doubt chat and analytics.
- **Web app** (`web/index.html`): a single file that runs in any browser with no install (pdf.js + localStorage).

## Features

- **PDF parsing** (`parser.py`): extracts questions even when some answers are missing.
- **Answer key editor**: missing answers are flagged for review, with one-click auto-fill using web search plus the local LLM (`solver.py`).
- **Quiz and scoring** (`scorer.py`): +2 / -0.5 / 0 by default, unkeyed questions excluded, timer, shuffle, CSV export.
- **Instant feedback**: "Check Answer" shows right or wrong immediately, and the AI explains the correct option when you miss.
- **Doubt chat**: ask the AI about any question, grounded on web evidence.
- **Spaced repetition**: retry mistakes, weakest-first, unseen questions.
- **Analytics**: score trend, accuracy per attempt, average time per question, accuracy by section, weakest questions.

## Tech stack

| Area | Technology |
|---|---|
| Language | Python 3 |
| UI | Streamlit |
| PDF parsing | pdfplumber (Python), pdf.js (browser) |
| Web grounding | ddgs (DuckDuckGo), Wikipedia API |
| Local LLM | llama.cpp via `llama-cpp-python` or `llama-server` (any small GGUF, e.g. Qwen 2B Q4_K_M), temperature 0 |
| Fallback | Word-overlap heuristic (always available) |
| Caching | SHA-256-keyed answer cache, so a question is never solved twice |
| Persistence | Local JSON files (cache, progress, history, attempts) |
| Browser app | HTML, CSS, vanilla JavaScript, localStorage |

## Project structure

```
app.py                  Streamlit UI (Load -> Key -> Test -> Analytics)
parser.py               PDF -> questions (regex + pdfplumber)
solver.py               Web search + LLM answer suggestion + doubt chat
scorer.py               SSC-style scoring
store.py                Cache, progress, history, attempts persistence
sample_questions.json   10 sample questions to try without a PDF
web/index.html          Browser-only version
requirements.txt
```

## Run

### Streamlit (full features)

```bash
git clone https://github.com/AkhilBinjola/pdf-to-quiz-with-ai
cd pdf-to-quiz-with-ai
pip install -r requirements.txt
streamlit run app.py
```

Open the URL shown (usually http://localhost:8501), then upload an SSC-style PDF or tick the bundled sample.

### Web app (no install)

Open `web/index.html` in any modern browser, then upload a PDF or load a JSON file.

## Optional: local model for auto-fill

Auto-fill needs a small local model. Pick one:

- **llama-server (recommended):** run any GGUF model with `llama-server` on port 8080 and the app uses it through the OpenAI-style API. Override the address with the `LLAMA_SERVER` environment variable.
- **Direct loading:** set `MODEL_GGUF` to the path of a `.gguf` file and the app loads it with `llama-cpp-python`.

  ```bash
  # macOS / Linux
  export MODEL_GGUF=/path/to/model.gguf
  # Windows PowerShell
  $env:MODEL_GGUF="C:\path\to\model.gguf"
  ```

`pip install llama-cpp-python` compiles from source on Windows and can take 10+ minutes. A prebuilt wheel from the [llama-cpp-python releases](https://github.com/abetlen/llama-cpp-python/releases) is faster.

Without a model the app still works: PDF answers, manual keys and the heuristic fallback are all available.

## License

MIT
