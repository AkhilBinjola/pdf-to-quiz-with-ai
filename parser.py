"""Parse objective PDFs into {question, options[4], answer, source}."""
import re
import pdfplumber

OPTION_RE = re.compile(r'\(([A-Da-d])\)\s*(.*?)(?=\([A-Da-d]\)|$)', re.S)
Q_SPLIT_RE = re.compile(r'(?:^|\n)\s*Q\s*\.?\s*(\d+)\s*[\.\)]\s*', re.I)
ANS_RE = re.compile(r'Ans\s*\.?\s*\(?\s*([A-Da-d])\s*\)?', re.I)

def _clean(s: str) -> str:
    return re.sub(r'\s+', ' ', (s or '').strip())

def parse_text_to_questions(full_text: str, source: str = 'upload'):
    questions = []
    parts = Q_SPLIT_RE.split(full_text)
    # parts = [pre, qnum1, body1, qnum2, body2, ...]
    for i in range(1, len(parts), 2):
        qnum, body = parts[i], parts[i + 1] if i + 1 < len(parts) else ''
        ans = None
        m_ans = ANS_RE.search(body)
        if m_ans:
            ans = m_ans.group(1).upper()
            body = ANS_RE.sub('', body).strip()
        opts = OPTION_RE.findall(body)
        # keep only first 4 distinct A-D options in order
        seen, options = set(), []
        for label, text in opts:
            L = label.upper()
            if L in seen:
                continue
            seen.add(L)
            options.append(_clean(text))
            if len(options) == 4:
                break
        stem = _clean(OPTION_RE.sub('', body))
        if len(stem) < 5 and len(options) == 0:
            continue  # likely figure-only question, skip
        while len(options) < 4:
            options.append('')
        questions.append({
            'id': f'{source}-Q{qnum}',
            'number': int(qnum),
            'question': stem[:2000],
            'options': options[:4],
            'answer': ans,  # 'A'..'D' or None
            'source': source,
            'needs_review': ans is None,
        })
    return questions

def parse_pdf(path: str, source: str = None):
    source = source or path.split('\\')[-1].split('/')[-1]
    with pdfplumber.open(path) as doc:
        text = '\n'.join([p.extract_text() or '' for p in doc.pages])
    return parse_text_to_questions(text, source=source)

def to_answer_key(questions):
    return {q['id']: q['answer'] for q in questions}
