"""Disk persistence: QA cache + quiz progress + paging.

- qa_cache.json: hash(question) -> {question, options, answer, engine, evidence, ts}
  Solved once, never re-queried (protects time + server context).
- progress.json: {bank, section, offset, pos, user_answers, q_times}
  Resume exactly where you left (e.g. Q40), across restarts.
- Paging: PAGE = 50. Current page renders instantly; next page pre-verifies
  in background so "next 50" never waits.
"""
import hashlib
import json
import os

PAGE = 50
BASE = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE, 'qa_cache.json')
PROGRESS_FILE = os.path.join(BASE, 'progress.json')
HISTORY_FILE = os.path.join(BASE, 'history.json')
ATTEMPTS_FILE = os.path.join(BASE, 'attempts.jsonl')

def qhash(question, options):
    h = hashlib.sha256()
    h.update(question.strip().encode('utf-8', 'ignore'))
    for o in (options or []):
        h.update(b'\x00')
        h.update(o.strip().encode('utf-8', 'ignore'))
    return h.hexdigest()[:16]

def load_cache():
    try:
        with open(CACHE_FILE, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def save_cache(cache):
    tmp = CACHE_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(tmp, CACHE_FILE)

def cache_get(cache, question, options):
    return cache.get(qhash(question, options))

def cache_put(cache, question, options, answer, engine='', evidence=None, confidence=0.65):
    cache[qhash(question, options)] = {
        'question': question[:2000], 'options': options,
        'answer': answer, 'engine': engine, 'evidence': (evidence or [])[:5],
        'confidence': confidence,
    }

def load_progress():
    try:
        with open(PROGRESS_FILE, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def save_progress(prog):
    tmp = PROGRESS_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(prog, f, ensure_ascii=False)
    os.replace(tmp, PROGRESS_FILE)

def clear_answers(prog):
    prog['user_answers'] = {}
    prog['q_times'] = {}
    prog['pos'] = 0
    save_progress(prog)

def _load_json(path, default):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default

def _save_json(path, obj):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)

def load_history():
    return _load_json(HISTORY_FILE, {})

def save_history(h):
    _save_json(HISTORY_FILE, h)

def record_result(qid, section, correct):
    """Update spaced-repetition stats. Returns entry."""
    import time as _t
    h = load_history()
    e = h.get(qid, {'seen': 0, 'correct': 0, 'wrong': 0, 'streak': 0})
    e['seen'] += 1
    e['section'] = section or ''
    e['last_ts'] = _t.time()
    if correct:
        e['correct'] += 1
        e['streak'] = e.get('streak', 0) + 1
    else:
        e['wrong'] += 1
        e['streak'] = 0
    h[qid] = e
    save_history(h)
    return e

def weakness(e):
    if not e or not e.get('seen'):
        return 0.5  # unseen sorts between mastered and weak
    return e.get('wrong', 0) / max(1, e.get('seen', 0))

def log_attempt(rec):
    import time as _t
    rec = dict(rec)
    rec.setdefault('ts', _t.time())
    with open(ATTEMPTS_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')

def load_attempts():
    out = []
    try:
        with open(ATTEMPTS_FILE, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
    except FileNotFoundError:
        pass
    return out
