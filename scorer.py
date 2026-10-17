"""SSC-style scoring: +marks for correct, -negative for wrong, 0 for skip."""

def score_test(questions, user_answers, marks_correct=2.0, marks_wrong=0.5):
    correct = wrong = skipped = unkeyed = 0
    details = []
    for q in questions:
        qid = q['id']
        gold = (q.get('answer') or '').upper() or None
        got = (user_answers.get(qid) or '').upper() or None
        if gold is None:
            unkeyed += 1
            status = 'unkeyed'
        elif got is None:
            skipped += 1
            status = 'skipped'
        elif got == gold:
            correct += 1
            status = 'correct'
        else:
            wrong += 1
            status = 'wrong'
        details.append({'id': qid, 'gold': gold, 'got': got, 'status': status})
    score = round(correct * marks_correct - wrong * marks_wrong, 2)
    max_score = round((len(questions) - unkeyed) * marks_correct, 2)
    return {
        'total': len(questions),
        'scored': len(questions) - unkeyed,
        'correct': correct,
        'wrong': wrong,
        'skipped': skipped,
        'unkeyed': unkeyed,
        'score': score,
        'max_score': max_score,
        'details': details,
    }
