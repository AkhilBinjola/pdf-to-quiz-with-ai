"""Fill missing answers: web snippets + llama-server (8080) -> direct GGUF -> heuristic.

Order:
1. llama-server at LLAMA_SERVER (default http://localhost:8080), OpenAI-style
   /v1/chat/completions then legacy /completion. No model load in Python.
2. Direct GGUF via llama-cpp (MODEL_GGUF) if server down.
3. Word-overlap heuristic (always available, flagged).
"""
import json
import os
import re
import requests

# Path to any small GGUF model (e.g. a Qwen 2B Q4_K_M). Empty = skip direct loading.
MODEL_GGUF = os.environ.get('MODEL_GGUF', '')
LLAMA_SERVER = os.environ.get('LLAMA_SERVER', 'http://localhost:8080')

_LLM = None

def web_search(query, k=5):
    try:
        from ddgs import DDGS
        out = []
        with DDGS() as ddg:
            for r in ddg.text(query, max_results=k):
                out.append({'title': r.get('title', ''),
                            'snippet': r.get('body', ''),
                            'url': r.get('href', '')})
        if out:
            return out
    except Exception:
        pass
    try:
        r = requests.get('https://en.wikipedia.org/w/api.php',
                         params={'action': 'query', 'list': 'search',
                                 'srsearch': query, 'format': 'json',
                                 'srlimit': k}, timeout=15)
        out = []
        for hit in r.json().get('query', {}).get('search', []):
            clean = re.sub(r'<[^>]+>', '', hit.get('snippet', ''))
            out.append({'title': hit.get('title', ''), 'snippet': clean,
                        'url': 'https://en.wikipedia.org/wiki/' + hit.get('title', '').replace(' ', '_')})
        return out
    except Exception:
        return []

def server_health():
    try:
        r = requests.get(LLAMA_SERVER + '/health', timeout=5)
        return r.status_code == 200
    except Exception:
        return False

def _server_pick(question, options, snippets):
    prompt = (
        'Multiple choice. Reply with ONLY one letter: A, B, C or D.\n'
        f'Question: {question}\n'
        + '\n'.join(f'{c}: {o}' for c, o in zip('ABCD', options))
        + f'\nWeb evidence:\n{snippets[:2000]}\nAnswer:'
    )
    # OpenAI-style chat endpoint (llama-server --jinja supports it)
    try:
        r = requests.post(LLAMA_SERVER + '/v1/chat/completions', json={
            'messages': [{'role': 'user', 'content': prompt}],
            'max_tokens': 5, 'temperature': 0.0}, timeout=120)
        if r.status_code == 200:
            txt = r.json()['choices'][0]['message']['content'].strip().upper()
            m = re.search(r'\b([ABCD])\b', txt)
            if m:
                return m.group(1), 'llama-server:Qwen3.5-2B'
    except Exception:
        pass
    try:
        r = requests.post(LLAMA_SERVER + '/completion', json={
            'prompt': prompt, 'n_predict': 5, 'temperature': 0.0}, timeout=120)
        if r.status_code == 200:
            txt = r.json().get('content', '').strip().upper()
            m = re.search(r'\b([ABCD])\b', txt)
            if m:
                return m.group(1), 'llama-server:Qwen3.5-2B'
    except Exception:
        pass
    return None, None

def _direct_pick(question, options, snippets):
    global _LLM
    if not os.path.exists(MODEL_GGUF):
        return None, None
    from llama_cpp import Llama
    if _LLM is None:
        _LLM = Llama(model_path=MODEL_GGUF, n_ctx=4096, verbose=False)
    prompt = (
        'Multiple choice. Reply with ONLY one letter: A, B, C or D.\n'
        f'Question: {question}\n'
        + '\n'.join(f'{c}: {o}' for c, o in zip('ABCD', options))
        + f'\nWeb evidence:\n{snippets[:2000]}\nAnswer:'
    )
    out = _LLM(prompt, max_tokens=5, temperature=0.0)
    txt = out['choices'][0]['text'].strip().upper()
    m = re.search(r'\b([ABCD])\b', txt)
    if m:
        return m.group(1), 'gguf-direct:Qwen3.5-2B'
    return None, None

def _overlap_pick(options, snippets):
    words = set(re.findall(r'[a-z]{3,}', snippets.lower()))
    scores = []
    for o in options:
        ow = set(re.findall(r'[a-z]{3,}', o.lower()))
        scores.append(len(words & ow))
    best = max(range(4), key=lambda i: scores[i])
    conf = 0.35 if sum(scores) == 0 else 0.35 + 0.4 * (scores[best] / max(1, sum(scores)))
    return 'ABCD'[best], round(min(conf, 0.75), 2)

def suggest_answer(question, options, max_evidence_chars=1200):
    # Cache-first: never re-solve or re-hit the server for known Qs.
    try:
        from store import load_cache, cache_get, cache_put
        _cache = load_cache()
        hit = cache_get(_cache, question, options)
        if hit and hit.get('answer'):
            return {'answer': hit['answer'], 'confidence': hit.get('confidence', 0.9),
                    'evidence': hit.get('evidence', []),
                    'engine': 'cache:' + str(hit.get('engine', ''))}
    except Exception:
        _cache = None
    hits = web_search(question[:300], k=5)
    blobs = ' '.join(h.get('snippet', '') for h in hits)[:max_evidence_chars]
    urls = [h['url'] for h in hits if h.get('url')]
    if not blobs.strip():
        return {'answer': None, 'confidence': 0.0, 'evidence': [], 'engine': 'none'}
    try:
        ans, engine = _server_pick(question, options, blobs)
        if ans:
            res = {'answer': ans, 'confidence': 0.7, 'evidence': urls, 'engine': engine}
            try:
                from store import save_cache, cache_put
                _c = load_cache()
                cache_put(_c, question, options, ans, engine, urls)
                save_cache(_c)
            except Exception:
                pass
            return res
    except Exception:
        pass
    try:
        ans, engine = _direct_pick(question, options, blobs)
        if ans:
            res = {'answer': ans, 'confidence': 0.65, 'evidence': urls, 'engine': engine}
            try:
                from store import save_cache, cache_put
                _c = load_cache()
                cache_put(_c, question, options, ans, engine, urls)
                save_cache(_c)
            except Exception:
                pass
            return res
    except Exception:
        pass
    ans, conf = _overlap_pick(options, blobs)
    return {'answer': ans, 'confidence': conf, 'evidence': urls, 'engine': 'overlap-heuristic'}


# ---- safety: relevance + injection + rate limits ----
import time as _time

_QUIZ_INTENT = re.compile(
    r'\b(explain|answer|option|mean|correct|wrong|doubt|solve|reason|synonym|antonym|grammar)\b'
    r'|\b(is the answer|whats the ans|i dont know|i could not|tell me)\b', re.I)
_BAD_PROMPT = re.compile(
    r'(ignore (previous|all|your)|disregard .*instruction|system prompt|you are now|'
    r'\bDAN\b|jailbreak|bypass|reveal .*prompt|forget .*rule|pretend (you|to be))', re.I)
_LAST_CALL = [0.0]
MIN_GAP = 3.0  # seconds between model calls (server overload guard)

def doubt_allowed(question, options, doubt):
    """True if the doubt may reach the model. Blocks off-topic/injection/oversize."""
    d = (doubt or '').strip()
    if not (3 <= len(d) <= 300):
        return False, 'Keep doubts to one short question (under 300 characters).'
    if _BAD_PROMPT.search(d):
        return False, 'That looks like an instruction override — I only answer doubts about this question.'
    low = d.lower()
    if _QUIZ_INTENT.search(low):
        return True, ''
    qwords = set(re.findall(r'[a-z]{4,}', (question or '').lower()))
    owords = set()
    for o in (options or []):
        owords |= set(re.findall(r'[a-z]{4,}', o.lower()))
    dwords = set(re.findall(r'[a-z]{4,}', low))
    if dwords & (qwords | owords):
        return True, ''
    return False, 'Please ask about this question only (options A-D or the concept tested).'

def _rate_ok():
    now = _time.time()
    if now - _LAST_CALL[0] < MIN_GAP:
        return False
    _LAST_CALL[0] = now
    return True

DOUBT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'doubts.json')

LEAK_RE = re.compile(
    r'^(wait,?|hmm+|okay,?|let me|is there a mistake)|<think>|\(quick take from model notes\)',
    re.I)

def _is_leak(text):
    t = (text or '').strip()
    if LEAK_RE.search(t):
        return True
    low = t.lower()
    return ('one-sentence explanation: final answer' in low
            and len(t) < 80)

def load_doubts():
    try:
        with open(DOUBT_FILE, encoding='utf-8') as f:
            d = json.load(f)
    except Exception:
        return {}
    # one-time sanitize: drop legacy thinking-leak assistant messages
    changed = False
    for qid, hist in list(d.items()):
        clean = [m for m in hist
                 if not (m.get('role') == 'assistant' and _is_leak(m.get('content', '')))]
        if len(clean) != len(hist):
            d[qid] = clean
            changed = True
    if changed:
        try:
            save_doubts(d)
        except Exception:
            pass
    return d

def save_doubts(d):
    tmp = DOUBT_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, DOUBT_FILE)

THINK_PREFIX = re.compile(
    r'^(wait,?|hmm+|let me|okay,?|ok,?|so,?|well,?|actually,?|is it possible|what if|suppose|assume|let\'s assume|is there a mistake)\b',
    re.I)

def _strip_thinking(text):
    """Drop thinking-style lines, keep explanatory sentences."""
    keep = []
    for line in re.split(r'\n+', text):
        line = re.sub(r'^[\*\-\d\.\)\s]+', '', line).strip()
        if not line or THINK_PREFIX.match(line):
            continue
        if len(line) < 25:
            continue
        keep.append(line)
    return ' '.join(keep)

def _final_letter(*texts):
    for t in texts:
        m = re.findall(r'final answer\s*[:\-]?\s*\(?\s*([A-D])\b', t, re.I)
        if m:
            return m[-1].upper()
    return None

def _completion_doubt(question, options, doubt, evidence, gold=None):
    """Direct completion (no chat template) - avoids endless thinking loops.

    Call 1 (no evidence/doubt lines - probe-verified decisive shape): letter.
    Call 2 ('Because' sentence starter): one-line explanation. First line only.
    If gold is already known (PDF/cache), skip call 1.
    """
    def _gen(prompt, n):
        r = requests.post(LLAMA_SERVER + '/completion', json={
            'prompt': prompt, 'n_predict': n, 'temperature': 0.0,
            'stop': []}, timeout=300)
        return r.json().get('content', '') if r.status_code == 200 else ''
    base = (f'Question: {question[:600]}\n'
            + ' '.join(f'{c}: {o}' for c, o in zip('ABCD', options)) + '\n')
    letter = (gold or '').upper() if gold in ('A', 'B', 'C', 'D') else ''
    if not letter:
        try:
            out1 = _gen(base + 'Correct option and one-line reason:\nAnswer:', 40)
        except Exception:
            return '', ''
        m = re.search(r'Answer:\s*\(?\s*([A-D])\b', out1, re.I)
        letter = m.group(1).upper() if m else ''
    if not letter:
        return '', ''
    def _reason(ask):
        try:
            out = _gen(base + f'Correct option: {letter}\n'
                       f'The student asks: {ask} One-sentence explanation:\n', 80)
            line = out.split('\n')[0].strip()
            line = _strip_thinking(line)
            line = re.sub(r'^answer\s*[:\-]?\s*(\([A-D]\)|[A-D][\.\)]?)?\s*', '', line, flags=re.I).strip()
            low = line.lower()
            echo = ('student asks' in low
                    or low.startswith(('because the student', 'the student'))
                    or 'one-sentence explanation' in low
                    or 'one sentence explanation' in low
                    or 'explain in one sentence' in low
                    or low.startswith('correct option:')
                    or 'the student asks:' in low)
            if len(line) < 15 or echo:
                return ''
            return line
        except Exception:
            return ''
    reason = _reason(doubt[:150])
    if not reason:
        reason = _reason('')  # retry without doubt text (echo guard)
    if not reason and evidence.strip():
        # grounded fallback: best evidence sentence (prefers one naming the answer)
        sents = [s.strip() for s in re.split(r'(?<=[.!?])\s+', evidence)
                 if len(s.strip()) > 40]
        opt_text = ''
        if letter in 'ABCD':
            opt_text = options['ABCD'.index(letter)].lower()
        pick = next((s for s in sents if opt_text and opt_text[:12] in s.lower()),
                    sents[0] if sents else '')
        if pick:
            reason = 'Reference: ' + pick[:300]
    if reason and not re.search(r'final answer', reason, re.I):
        reason += f' Final answer: {letter}.'
    return (reason or f'Final answer: {letter}.')[:700], ''

def chat_about(question, options, history, doubt, max_history=6, gold=None):
    """Answer a doubt about one MCQ via llama-server. Stateless per call.

    history: list of {role, content} (user/assistant), trimmed to last N.
    Returns a CLEAN reply (thinking stripped, ends with Answer: X).
    Grounds the model with web evidence so it stops speculating.
    """
    ok, why = doubt_allowed(question, options, doubt)
    if not ok:
        return why + ' No AI call was made.'
    if not _rate_ok():
        return 'Easy — wait a few seconds between questions so the AI is not overloaded.'
    ev = ' '.join(h.get('snippet', '') for h in web_search(question[:250], k=3))[:800]
    if len(ev.strip()) < 100 and gold in ('A', 'B', 'C', 'D'):
        # retry search anchored on the known answer for a quotable fact
        opt = options['ABCD'.index(gold)]
        ev2 = ' '.join(h.get('snippet', '') for h in web_search(f'{question[:150]} {opt}', k=3))[:800]
        if len(ev2.strip()) > len(ev.strip()):
            ev = ev2
    ctx = ('You are an SSC-CGL tutor. Do NOT show thinking or say "wait". '
           'Give 2-3 sentences of explanation, then end with exactly: Final answer: <letter>.\n'
           f'Question: {question[:800]}\n'
           + '\n'.join(f'{c}: {o}' for c, o in zip('ABCD', options))
           + (f'\nReference facts: {ev}\n' if ev.strip() else '\n'))
    msgs = [{'role': 'system', 'content': ctx[:2500]}]
    for m in (history or [])[-max_history:]:
        c = m['content']
        if m['role'] == 'assistant' and len(c) > 600:
            c = c[:600]  # keep history lean; past replies were already cleaned
        msgs.append({'role': m['role'], 'content': c[:1000]})
    msgs.append({'role': 'user', 'content': doubt[:1000] +
                 '\nInstruction: explain in 2-3 sentences, then write exactly: Final answer: <A/B/C/D>.'})
    raw_content, raw_think = '', ''
    try:
        # completion endpoint first: decisive, no thinking-loop risk
        raw_content, _ = _completion_doubt(question, options, doubt, ev, gold)
        if not _final_letter(raw_content, ''):
            raw_content, raw_think = '', ''
            r = requests.post(LLAMA_SERVER + '/v1/chat/completions', json={
                'messages': msgs, 'max_tokens': 2048, 'temperature': 0.2}, timeout=300)
            if r.status_code == 200:
                msg = r.json()['choices'][0]['message']
                raw_content = (msg.get('content') or '').strip()
                raw_think = (msg.get('reasoning_content') or '').strip()
    except Exception:
        return 'Model server is unreachable (start llama-server on :8080). Your doubt is saved and will send later.'
    letter = _final_letter(raw_content, raw_think)
    if not letter:
        m = re.search(r'\b([A-D])\b', raw_content)
        if m and len(raw_content) < 300:
            letter = m.group(1)
    if not letter:
        # last resort: strongest option signal from grounded reasoning
        for src in (raw_think, raw_content):
            ms = re.findall(r'option\s*\(?\s*([A-D])\b.{0,60}?(?:correct|best|answer|likely)',
                            src, re.I)
            if ms:
                letter = ms[-1].upper()
                break
    body = _strip_thinking(raw_content)[:600]
    body = re.sub(r'^(final answer\s*[:\-]?\s*(\([A-D]\)|[A-D][\.\)]?)?\.?\s*)', '', body, flags=re.I).strip()
    opt_text = options['ABCD'.index(letter)] if letter in ('A', 'B', 'C', 'D') else ''
    if letter and body:
        return f'Option {letter} ({opt_text}): {body}'[:500]
    if letter:
        if opt_text:
            return f'Option {letter} ({opt_text}). Final answer: {letter}.'
        return f'Final answer: {letter}.'
    if body:
        return body[:600] + ' (Model is unsure — please verify this one.)'
    return 'Model could not settle on an answer — please verify this one manually.'
