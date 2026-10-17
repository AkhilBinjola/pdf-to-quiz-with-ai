"""PDF to Quiz with AI - upload a PDF, get an MCQ test, score it (SSC +2 / -0.5)."""
import json
import random
import time
import streamlit as st

from parser import parse_pdf, parse_text_to_questions
from scorer import score_test
from solver import suggest_answer, chat_about, load_doubts, save_doubts
from store import PAGE, load_cache, save_cache, cache_get, load_progress, save_progress, clear_answers
from store import load_history, record_result, weakness, log_attempt, load_attempts

st.set_page_config(page_title='PDF to Quiz with AI', layout='wide')
st.title('PDF to Quiz with AI')

with st.sidebar:
    st.header('Settings')
    marks_correct = st.number_input('Marks per correct', value=2.0, step=0.5)
    marks_wrong = st.number_input('Negative per wrong', value=0.5, step=0.25)
    shuffle = st.checkbox('Shuffle questions', value=True)
    timer_min = st.number_input('Timer (minutes, 0 = off)', value=30, step=5)
    if st.button('Reset quiz'):
        st.session_state.pop('questions', None)
        st.session_state.pop('answers', None)
        st.session_state.pop('start_ts', None)
        st.rerun()

tab1, tab2, tab3, tab4 = st.tabs(['1. Load', '2. Answer key', '3. Take test + Score', '4. Analytics'])

with tab1:
    up = st.file_uploader('Upload objective PDF', type=['pdf'])
    sample = st.checkbox('...or try bundled SSC sample (10 Qs)', value=False)
    use_combined = st.checkbox('...or load F:\\ssc cgl combined JSON (550 Qs, mostly unkeyed - best for AI test)', value=False)
    section = st.text_input('Section filter (blank = all)', value='')
    max_qs = st.number_input('Max questions to load', value=50, min_value=5, max_value=550, step=5)
    if st.button('Parse'):
        if up is not None:
            with open('_upload.pdf', 'wb') as f:
                f.write(up.read())
            qs = parse_pdf('_upload.pdf', source=up.name)
        elif use_combined:
            raw = json.load(open(r'F:\ssc cgl\combined\all_questions_combined.json', encoding='utf-8'))
            qs = []
            for sec, items in raw.items():
                if section and section.lower() not in sec.lower():
                    continue
                for idx, it in enumerate(items):
                    parsed = parse_text_to_questions('Q1. ' + it.get('text', ''),
                                                     source=it.get('source', 'combined'))
                    if not parsed:
                        continue
                    q = parsed[0]
                    q['id'] = f"{sec[:12]}-{it.get('source', '?')}-{idx}"
                    q['section'] = sec
                    qs.append(q)
                    if len(qs) >= max_qs:
                        break
                if len(qs) >= max_qs:
                    break
        elif sample:
            demo = open('sample_questions.json', encoding='utf-8').read()
            qs = json.loads(demo)
        else:
            st.warning('Upload a PDF first.')
            qs = []
        if qs:
            if shuffle:
                random.shuffle(qs)
            st.session_state['questions'] = qs
            st.session_state['answers'] = {}
            st.session_state['start_ts'] = time.time()
            st.session_state['bank'] = {'kind': 'upload' if up is not None else ('combined' if use_combined else 'sample'),
                                        'section': section if use_combined else '', 'offset': 0}
            st.session_state['pos'] = 0
            st.session_state['q_times'] = {}
            st.session_state['q_enter_ts'] = time.time()
            save_progress({'bank': st.session_state['bank'], 'offset': 0, 'pos': 0,
                           'user_answers': {}, 'q_times': {}})
            st.success(f'Parsed {len(qs)} questions, {sum(1 for q in qs if q["answer"])} with answers from PDF.')

import threading

def _bg_fill_worker():
    ss = st.session_state
    qs = ss.get('questions', [])
    try:
        for q in qs:
            if not ss.get('fill_running'):
                break
            try:
                s = suggest_answer(q['question'], q['options'])
            except Exception:
                s = {'answer': None}
            if not s.get('answer'):
                continue
            if q.get('answer') and not q.get('ai_suggested'):
                # cross-check: PDF gold vs web+model verdict
                q['ai_check'] = s['answer']
                q['conflict'] = (s['answer'] != q['answer'])
            elif not q.get('answer'):
                q['answer'] = s['answer']
                q['ai_suggested'] = True
                q['confidence'] = s.get('confidence')
                q['evidence'] = s.get('evidence', [])
                q['engine'] = s.get('engine')
            ss['fill_done'] = sum(1 for x in qs if x.get('answer'))
    finally:
        ss['fill_running'] = False

@st.fragment(run_every=2)
def fill_status():
    qs = st.session_state.get('questions', [])
    if not qs:
        return
    done = sum(1 for q in qs if q.get('answer'))
    total = len(qs)
    st.progress(done / max(1, total), text=f'Verified {done}/{total} — quiz below works already')
    if st.session_state.get('fill_running'):
        st.caption('Filling in background… latest verified appear live. You can start the quiz now.')
    else:
        st.caption('Fill idle. Start it and keep using the quiz — no waiting.')

with tab2:
    qs = st.session_state.get('questions', [])
    if not qs:
        st.info('Parse a PDF first (tab 1).')
    else:
        st.write(f'{len(qs)} questions. Missing answers are marked REVIEW.')
        c1, c2 = st.columns(2)
        if c1.button('Start background fill (stream answers live)'):
            st.session_state['fill_running'] = True
            st.session_state['fill_done'] = sum(1 for q in qs if q.get('answer'))
            t = threading.Thread(target=_bg_fill_worker, daemon=True)
            t.start()
        if c2.button('Stop fill'):
            st.session_state['fill_running'] = False
        fill_status()
        st.caption('Tip: start the fill, then open tab 3 and begin — verified answers stream in without blocking.')
        for q in qs:
            flag = 'OK' if q.get('answer') and not q.get('ai_suggested') else ('AI?' if q.get('ai_suggested') else 'REVIEW')
            with st.expander(f"[{flag}] {q['id']}: {q['question'][:100]}"):
                st.write(q['question'])
                for c, o in zip('ABCD', q['options']):
                    st.write(f'**{c}.** {o}')
                cur = ['-'] + list('ABCD')
                val = st.selectbox('Correct option (- = unknown)',
                                   cur, index=cur.index(q.get('answer') or '-'), key='key_' + q['id'])
                q['answer'] = None if val == '-' else val
                if q.get('evidence'):
                    st.caption(f"AI engine: {q.get('engine')} conf={q.get('confidence')} | " +
                               ' '.join(q['evidence'][:3]))

@st.fragment(run_every=1)
def qtimer():
    ts = st.session_state.get('q_enter_ts')
    if not ts:
        return
    el = int(time.time() - ts)
    st.caption(f'Time on this question: {el // 60}:{el % 60:02d}')

def _accumulate_time():
    ss = st.session_state
    qid = ss.get('cur_qid')
    ts = ss.get('q_enter_ts')
    if qid and ts:
        el = time.time() - ts
        ss.setdefault('q_times', {})
        ss['q_times'][qid] = round(ss['q_times'].get(qid, 0) + el, 1)

def _save():
    ss = st.session_state
    save_progress({'bank': ss.get('bank', {}), 'offset': ss.get('page_offset', 0),
                   'pos': ss.get('pos', 0), 'user_answers': ss.get('quiz_answers', {}),
                   'q_times': ss.get('q_times', {})})

def _load_page(bank, offset, limit=PAGE):
    """Return list of questions for this page; combined re-parsed sliced, else session slice."""
    if (bank or {}).get('kind') == 'combined':
        raw = json.load(open(r'F:\ssc cgl\combined\all_questions_combined.json', encoding='utf-8'))
        items = []
        for sec, lst in raw.items():
            if bank.get('section') and bank['section'].lower() not in sec.lower():
                continue
            for idx, it in enumerate(lst):
                items.append((sec, idx, it))
        items = items[offset:offset + limit]
        out = []
        for sec, idx, it in items:
            p = parse_text_to_questions('Q1. ' + it.get('text', ''), source=it.get('source', 'combined'))
            if not p:
                continue
            q = p[0]
            q['id'] = f"{sec[:12]}-{it.get('source', '?')}-{idx}"
            q['section'] = sec
            out.append(q)
        # cache-first fill of answers (no repeat server hits)
        cache = load_cache()
        for q in out:
            hit = cache_get(cache, q['question'], q['options'])
            if hit and hit.get('answer') and not q.get('answer'):
                q['answer'] = hit['answer']
                q['ai_suggested'] = True
                q['engine'] = 'cache:' + str(hit.get('engine', ''))
        return out
    return st.session_state.get('questions', [])[offset:offset + limit]

def _preload_next(bank, offset, limit=PAGE):
    def run():
        try:
            _load_page(bank, offset + limit, limit)  # warms qa_cache.json via solver? no - parse+cache only
            nxt = _load_page(bank, offset + limit, limit)
            for q in nxt:
                if not q.get('answer'):
                    s = suggest_answer(q['question'], q['options'])
                    if s.get('answer'):
                        q['answer'] = s['answer']
            st.session_state['preloaded_offset'] = offset + limit
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start()

with tab3:
    # restore last session (e.g. left at Q40)
    if 'pos' not in st.session_state:
        prog = load_progress()
        st.session_state['pos'] = prog.get('pos', 0)
        st.session_state['quiz_answers'] = prog.get('user_answers', {})
        st.session_state['q_times'] = prog.get('q_times', {})
        st.session_state['page_offset'] = prog.get('offset', 0)
        if prog.get('bank'):
            st.session_state['bank'] = prog['bank']
        st.session_state['q_enter_ts'] = time.time()
    bank = st.session_state.get('bank', {'kind': 'sample'})
    offset = st.session_state.get('page_offset', 0)
    page = _load_page(bank, offset, PAGE)
    if not page:
        st.info('Parse a PDF first (tab 1).')
        st.stop()
    # auto web-verify missing answers on this page (web search + model, saved to cache)
    if any(not x.get('answer') for x in page) and not st.session_state.get('fill_running'):
        st.session_state['fill_running'] = True
        st.session_state['questions'] = page
        threading.Thread(target=_bg_fill_worker, daemon=True).start()
        st.caption('Verifying missing answers in background (web search + model)…')
    conflicts = [x for x in page if x.get('conflict')]
    if conflicts:
        st.warning(f'{len(conflicts)} PDF-vs-AI disagreements on this page — check tab 2.')
    mode = st.selectbox('Quiz mode', ['All', 'Retry mistakes', 'Weakest first', 'Unseen'],
                        key='quiz_mode')
    hist = load_history()
    if mode == 'Retry mistakes':
        page = [x for x in page if hist.get(x['id'], {}).get('wrong', 0) > 0]
    elif mode == 'Weakest first':
        page = sorted(page, key=lambda x: -weakness(hist.get(x['id'])))
    elif mode == 'Unseen':
        page = [x for x in page if not hist.get(x['id'], {}).get('seen')]
    if not page:
        st.info('No questions in this mode yet — try All, or attempt some first.')
        st.stop()
    pos = max(0, min(st.session_state.get('pos', 0), len(page) - 1))
    st.session_state['pos'] = pos
    q = page[pos]
    st.session_state['cur_qid'] = q['id']
    st.write(f"Question {offset + pos + 1} (page {offset + 1}-{offset + len(page)}) | "
             f"last saved pos restores here on restart")
    qtimer()
    st.subheader(q['question'])
    prev_pick = st.session_state.get('quiz_answers', {}).get(q['id'], 'Skip')
    opts = ['Skip'] + [f'{c}. {o}' for c, o in zip('ABCD', q['options'])]
    pick = st.radio('Your answer', opts, index=opts.index(prev_pick) if prev_pick in opts else 0,
                    key='pick_' + str(offset) + '_' + str(pos))
    # --- Immediate right/wrong feedback + AI explanation on wrong ---
    if st.button('Check Answer', key='check_' + str(offset) + '_' + str(pos)):
        st.session_state['quiz_answers'] = st.session_state.get('quiz_answers', {})
        st.session_state['quiz_answers'][q['id']] = pick
        got = None if pick == 'Skip' else pick[0]
        gold = (q.get('answer') or '').upper() or None
        if gold is None:
            st.info('No answer key for this Q. Asking AI...')
            with st.spinner('Asking AI...'):
                reply = chat_about(q['question'], q['options'], [], 'What is the correct option and why?', gold=None)
            st.write(reply)
        elif got is None:
            st.warning('Skipped. Correct answer: ' + gold)
        elif got == gold:
            st.success('Correct! Answer: ' + gold)
        else:
            st.error('Wrong. You picked ' + got + ', correct is ' + gold + '.')
            with st.spinner('Asking AI to explain...'):
                reply = chat_about(q['question'], q['options'], [], 'I answered ' + got + ' but it is wrong. Explain why ' + gold + ' is correct and why ' + got + ' is wrong.', gold=gold)
            st.write(reply)

    with st.expander('Doubts — ask about this question'):
        doubts = load_doubts()
        hist = doubts.get(q['id'], [])
        for m in hist:
            st.chat_message(m['role']).write(m['content'])
        d = st.text_input('Your doubt', key='doubt_' + str(offset) + '_' + str(pos),
                          placeholder='e.g. Why is option B wrong?')
        dc1, dc2, dc3 = st.columns(3)
        if dc1.button('Ask AI', key='ask_' + str(offset) + '_' + str(pos)) and d:
            hist.append({'role': 'user', 'content': d})
            with st.spinner('Asking AI...'):
                reply = chat_about(q['question'], q['options'], hist[:-1], d, gold=q.get('answer'))
            hist.append({'role': 'assistant', 'content': reply})
            doubts[q['id']] = hist
            save_doubts(doubts)
            st.rerun()
        if dc2.button('Explain this to me', key='exp_' + str(offset) + '_' + str(pos)):
            prompt = 'I could not answer this. Explain the concept step by step and tell me the answer.'
            hist.append({'role': 'user', 'content': prompt})
            with st.spinner('Asking AI...'):
                reply = chat_about(q['question'], q['options'], hist[:-1], prompt, gold=q.get('answer'))
            hist.append({'role': 'assistant', 'content': reply})
            doubts[q['id']] = hist
            save_doubts(doubts)
            st.rerun()
        if dc3.button('Clear chat', key='clr_' + str(offset) + '_' + str(pos)):
            doubts[q['id']] = []
            save_doubts(doubts)
            st.rerun()
    n1, n2, n3 = st.columns(3)
    if n1.button('Back'):
        _accumulate_time()
        st.session_state.setdefault('quiz_answers', {})[q['id']] = pick
        st.session_state['pos'] = max(0, pos - 1)
        st.session_state['q_enter_ts'] = time.time()
        _save()
        st.rerun()
    if n2.button('Save + Next'):
        _accumulate_time()
        st.session_state.setdefault('quiz_answers', {})[q['id']] = pick
        st.session_state['pos'] = min(len(page) - 1, pos + 1)
        st.session_state['q_enter_ts'] = time.time()
        _save()
        st.rerun()
    if n3.button('Submit page + Score'):
        _accumulate_time()
        st.session_state.setdefault('quiz_answers', {})[q['id']] = pick
        _save()
        ua = {qid: (None if v == 'Skip' else v[0]) for qid, v in st.session_state['quiz_answers'].items()}
        res = score_test(page, ua, marks_correct, marks_wrong)
        st.success(f"Score: {res['score']} / {res['max_score']} | Correct {res['correct']}, "
                   f"Wrong {res['wrong']}, Skipped {res['skipped']}, Unkeyed {res['unkeyed']}")
        times = st.session_state.get('q_times', {})
        tparts = []
        for d in res["details"][:10]:
            qid = d["id"]
            tparts.append(str(qid[-8:]) + "=" + str(times.get(qid, 0)))
        st.write("Per-question time (s): " + ", ".join(tparts))
        # spaced repetition + attempt log (powers Retry-mistakes + Analytics)
        by_sec = {}
        q_by_id = {x['id']: x for x in page}
        for d in res["details"]:
            if d["status"] in ("correct", "wrong"):
                qq = q_by_id.get(d["id"], {})
                record_result(d["id"], qq.get("section", ""), d["status"] == "correct")
                sec = qq.get("section", "") or "all"
                s = by_sec.setdefault(sec, {"correct": 0, "wrong": 0})
                s["correct" if d["status"] == "correct" else "wrong"] += 1
        log_attempt({"bank": bank, "offset": offset, "mode": st.session_state.get("quiz_mode"),
                     "score": res["score"], "max": res["max_score"], "correct": res["correct"],
                     "wrong": res["wrong"], "skipped": res["skipped"],
                     "avg_time": round(sum(times.values()) / max(1, len(times)), 1),
                     "by_section": by_sec})
    st.divider()
    p1, p2, p3 = st.columns(3)
    if p1.button('Re-quiz this 50'):
        prog = load_progress()
        clear_answers(prog)
        st.session_state['quiz_answers'] = {}
        st.session_state['q_times'] = {}
        st.session_state['pos'] = 0
        st.session_state['q_enter_ts'] = time.time()
        st.rerun()
    if p2.button('Back 50') and offset >= PAGE:
        _accumulate_time()
        _save()
        st.session_state['page_offset'] = offset - PAGE
        st.session_state['pos'] = 0
        st.session_state['q_enter_ts'] = time.time()
        _save()
        st.rerun()
    if p3.button('Next 50 (preloaded)'):
        _accumulate_time()
        _save()
        st.session_state['page_offset'] = offset + PAGE
        st.session_state['pos'] = 0
        st.session_state['q_enter_ts'] = time.time()
        _save()
        _preload_next(bank, offset + PAGE)  # next-next warms cache while you quiz
        st.rerun()
    if st.session_state.get('preloaded_offset') == offset + PAGE:
        st.caption('Next 50 already preloaded — instant.')
    else:
        if st.button('Preload next 50 now'):
            _preload_next(bank, offset)

with tab4:
    st.header('Performance analytics')
    attempts = load_attempts()
    hist = load_history()
    if not attempts and not hist:
        st.info('Attempt a quiz first — scores land here.')
    else:
        if attempts:
            st.subheader('Score trend')
            st.line_chart([a.get('score', 0) for a in attempts])
            st.subheader('Accuracy per attempt (%)')
            acc = [round(100 * a.get('correct', 0) / max(1, a.get('correct', 0) + a.get('wrong', 0)), 1)
                   for a in attempts]
            st.bar_chart(acc)
            st.subheader('Avg seconds per question')
            st.bar_chart([a.get('avg_time', 0) for a in attempts])
            agg = {}
            for a in attempts:
                for sec, s in (a.get('by_section') or {}).items():
                    g = agg.setdefault(sec, {'correct': 0, 'wrong': 0})
                    g['correct'] += s.get('correct', 0)
                    g['wrong'] += s.get('wrong', 0)
            if agg:
                st.subheader('Accuracy by section (%)')
                st.bar_chart({sec: round(100 * v['correct'] / max(1, v['correct'] + v['wrong']), 1)
                              for sec, v in agg.items()})
        if hist:
            weak = sorted(hist.items(), key=lambda kv: -weakness(kv[1]))[:10]
            st.subheader('Weakest questions (most-wrong first)')
            for qid, e in weak:
                if e.get('wrong'):
                    st.write(f"{qid}: {e['wrong']} wrong / {e['seen']} seen, streak {e.get('streak', 0)}")
