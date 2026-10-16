"""Transparent rule proxies and response-bound human review, not an LLM judge."""
import hashlib
import json
import re
from collections import defaultdict


def fingerprint(data):
    return hashlib.sha256(data).hexdigest()


def response_hash(response):
    return fingerprint(json.dumps(response, sort_keys=True, ensure_ascii=False,
                                  separators=(',', ':')).encode('utf8'))


def normalize(text):
    return ' '.join(text.casefold().split())


def validate_dataset(dataset):
    if dataset.get('schema_version') != 1 or not dataset.get('documents') or not dataset.get('cases'):
        raise ValueError('Need versioned documents and nonempty cases')
    documents = dataset['documents']
    for name, text in documents.items():
        if not isinstance(name, str) or any(x in name for x in ('/', '\\', '\x00')) or not name.endswith(('.txt', '.md')):
            raise ValueError('Dataset document names must be plain TXT/MD filenames')
        if not isinstance(text, str) or not text.strip() or len(text.encode('utf8')) > 20 * 1024 * 1024:
            raise ValueError('Invalid dataset document')
    seen = set()
    for case in dataset['cases']:
        if not isinstance(case.get('id'), str) or not case['id'] or case['id'] in seen:
            raise ValueError('Case IDs must be nonempty and unique')
        seen.add(case['id'])
        for key in ('question', 'reference_answer', 'category'):
            if not isinstance(case.get(key), str) or not case[key].strip():
                raise ValueError('Missing case '+key)
        if len(case['question']) > 2000 or type(case.get('unanswerable')) is not bool:
            raise ValueError('Invalid question or answerability')
        facts = case.get('facts', [])
        if not isinstance(facts, list) or bool(facts) == case['unanswerable']:
            raise ValueError('Answerable cases need facts; unanswerable cases must not invent them')
        patterns = list(case.get('forbidden_patterns', []))
        if case['unanswerable']:
            if not case.get('refusal_patterns'):
                raise ValueError('Unanswerable case needs refusal checks')
            patterns += case['refusal_patterns']
        for fact in facts:
            if fact.get('source') not in documents or not fact.get('quote'):
                raise ValueError('Fact must cite an existing source and exact evidence')
            if normalize(fact['quote']) not in normalize(documents[fact['source']]):
                raise ValueError('Gold evidence absent from source: '+case['id'])
            if not fact.get('patterns'):
                raise ValueError('Fact needs accepted answer patterns')
            patterns += fact['patterns']
        for pattern in patterns:
            if not isinstance(pattern, str) or re.search(pattern, '', flags=re.I):
                raise ValueError('Answer patterns cannot match the empty string')
            re.compile(pattern, re.I)


def matches(patterns, text):
    return any(re.search(pattern, text, flags=re.I) for pattern in patterns)


def score_response(case, response, error=None):
    if not isinstance(response, dict):
        response, error = {}, error or 'INVALID_RESPONSE_TYPE'
    answer = response.get('answer', '')
    chunks = response.get('chunks', [])
    sources = response.get('sources', [])
    if (not isinstance(answer, str) or not answer.strip() or not isinstance(chunks, list)
            or not isinstance(sources, list) or any(not isinstance(s, str) for s in sources)
            or any(not isinstance(c, dict) or not isinstance(c.get('source'), str)
                   or not isinstance(c.get('text'), str) for c in chunks)):
        error = error or 'INVALID_OR_EMPTY_RESPONSE'
        answer, chunks, sources = '', [], []
    forbidden = matches(case.get('forbidden_patterns', []), answer)
    facts = []
    for fact in case.get('facts', []):
        retrieved = any(chunk['source'] == fact['source'] and normalize(fact['quote']) in normalize(chunk['text'])
                        for chunk in chunks)
        facts.append({'name': fact.get('name', fact['quote']), 'source': fact['source'],
                      'answer_match': not bool(error) and matches(fact['patterns'], answer),
                      'evidence_retrieved': not bool(error) and retrieved,
                      'source_returned': not bool(error) and fact['source'] in sources})
    checks = {
        'execution': not bool(error),
        'required_facts': all(f['answer_match'] for f in facts) if facts else None,
        'evidence_retrieval': all(f['evidence_retrieved'] for f in facts) if facts else None,
        'source_coverage': all(f['source_returned'] for f in facts) if facts else None,
        'refusal': (not bool(error) and matches(case['refusal_patterns'], answer)) if case['unanswerable'] else None,
        'no_forbidden_claim': not bool(error) and not forbidden,
    }
    return {'checks': checks, 'facts': facts,
            'rule_pass': all(value for value in checks.values() if value is not None),
            'error': error}


def verify_report(report, dataset_sha256=None):
    if report.get('schema_version') != 1 or not report.get('run_id') or not report.get('rows'):
        raise ValueError('Invalid report')
    if dataset_sha256 and report.get('dataset_sha256') != dataset_sha256:
        raise ValueError('Dataset changed since generation')
    ids = set()
    for row in report['rows']:
        if row['id'] in ids or response_hash(row['response']) != row['response_sha256']:
            raise ValueError('Duplicate case or modified response')
        ids.add(row['id'])


def summarize(report, review=None):
    verify_report(report)
    rows = report['rows']
    total = len(rows)
    facts = [f for row in rows for f in row['assessment']['facts']]
    refusals = [row for row in rows if row['unanswerable']]
    categories = defaultdict(lambda: {'total': 0, 'rule_passed': 0})
    for row in rows:
        categories[row['category']]['total'] += 1
        categories[row['category']]['rule_passed'] += int(row['assessment']['rule_pass'])
    summary = {
        'evaluated_cases': total, 'suite_cases': report['suite_cases'],
        'complete_suite': report.get('complete', False) and total == report['suite_cases'],
        'execution_errors': sum(not row['assessment']['checks']['execution'] for row in rows),
        'rule_passed': sum(row['assessment']['rule_pass'] for row in rows),
        'rule_pass_rate': sum(row['assessment']['rule_pass'] for row in rows)/total,
        'fact_match_rate': sum(f['answer_match'] for f in facts)/len(facts) if facts else None,
        'retrieval_evidence_recall': sum(f['evidence_retrieved'] for f in facts)/len(facts) if facts else None,
        'refusal_rule_pass_rate': sum(row['assessment']['checks']['refusal'] and row['assessment']['checks']['no_forbidden_claim']
                                      for row in refusals)/len(refusals) if refusals else None,
        'categories': dict(categories),
        'human_review': {'reviewed': 0, 'coverage': 0.0, 'accuracy_on_decisive_reviews': None,
                         'confirmed_suite_accuracy': None, 'confirmed_suite_groundedness': None},
        'interpretation': 'Rule matches and evidence recall are proxies, not whole-answer correctness or faithfulness. Synthetic development suite, not population accuracy.',
    }
    if review is not None:
        if review.get('run_id') != report['run_id'] or review.get('dataset_sha256') != report['dataset_sha256']:
            raise ValueError('Human review belongs to a different run or dataset')
        known = {row['id']: row for row in rows}
        labels, seen = [], set()
        for item in review.get('rows', []):
            if item['id'] in seen or item['id'] not in known:
                raise ValueError('Duplicate or unknown reviewed case')
            seen.add(item['id'])
            if item.get('response_sha256') != known[item['id']]['response_sha256']:
                raise ValueError('Human review response binding does not match')
            for key in ('correctness', 'groundedness'):
                if item.get(key) not in ('pass', 'fail', 'unsure', 'pending'):
                    raise ValueError('Invalid human verdict')
            if (item['correctness'] != 'pending' or item['groundedness'] != 'pending') and not item.get('reviewer', '').strip():
                raise ValueError('Completed human labels need a reviewer')
            if not known[item['id']]['assessment']['checks']['execution'] and (item['correctness']=='pass' or item['groundedness']=='pass'):
                raise ValueError('An execution failure cannot be reviewed as a correct/grounded answer')
            labels.append(item)
        reviewed = [item for item in labels if item['correctness'] != 'pending']
        decisive = [item for item in reviewed if item['correctness'] in ('pass', 'fail')]
        grounded = [item for item in labels if item['groundedness'] in ('pass', 'fail')]
        full = summary['complete_suite']
        summary['human_review'] = {
            'reviewed': len(reviewed), 'coverage': len(reviewed)/total,
            'accuracy_on_decisive_reviews': sum(x['correctness']=='pass' for x in decisive)/len(decisive) if decisive else None,
            'confirmed_suite_accuracy': sum(x['correctness']=='pass' for x in decisive)/total if full and len(decisive)==total else None,
            'confirmed_suite_groundedness': sum(x['groundedness']=='pass' for x in grounded)/total if full and len(grounded)==total else None,
        }
    return summary


def review_template(report):
    verify_report(report)
    return {'run_id': report['run_id'], 'dataset_sha256': report['dataset_sha256'],
            'instructions': 'Review the whole answer against source documents, including extra claims, negations, units, dates and refusal. Do not treat pattern hits as human correctness.',
            'rows': [{'id': row['id'], 'response_sha256': row['response_sha256'],
                      'question': row['question'], 'reference_answer': row['reference_answer'],
                      'answer': row['response'].get('answer', ''), 'correctness': 'pending',
                      'groundedness': 'pending', 'reviewer': '', 'notes': ''} for row in report['rows']]}
