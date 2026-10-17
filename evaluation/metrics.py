"""Transparent rule proxies and response-bound human review, not an LLM judge."""
import hashlib
import json
import re
from collections import defaultdict


def fingerprint(data):
    return hashlib.sha256(data).hexdigest()


def serialize(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def response_hash(response):
    return fingerprint(serialize(response).encode('utf8'))


class Reference:
    def __init__(self, raw):
        self.data = json.loads(raw)
        validate_dataset(self.data)
        self.sha256 = fingerprint(raw)
        self.cases = {case['id']: case for case in self.data['cases']}

    @classmethod
    def load(cls, path):
        from pathlib import Path
        return cls(Path(path).read_bytes())


def bind_row(case, response, error=None, generation=None, **extra):
    # Hash exactly these UTF-8 bytes in every language; do not reserialize in JS.
    raw = serialize(response)
    row = dict(extra, id=case['id'], category=case['category'], question=case['question'],
               reference_answer=case['reference_answer'], unanswerable=case['unanswerable'],
               case_sha256=response_hash(case), response=response, response_json=raw,
               response_sha256=fingerprint(raw.encode('utf8')), error=error,
               generation=generation or {}, assessment=score_response(case, response, error))
    row['record_json'] = serialize(record_value(row))
    row['record_sha256'] = record_hash(row)
    return row


def record_value(row):
    return {key:row[key] for key in ('case_sha256','response_sha256','error','generation')}


def record_hash(row):
    return fingerprint(row['record_json'].encode('utf8'))


def json_equal(left, right):
    # JSON number 1.0 and 1 are semantically equivalent; true and 1 are not.
    if isinstance(left,bool) or isinstance(right,bool):return type(left) is type(right) and left==right
    if isinstance(left,(int,float)) and isinstance(right,(int,float)):return left==right
    if type(left) is not type(right):return False
    if isinstance(left,dict):return left.keys()==right.keys() and all(json_equal(left[k],right[k]) for k in left)
    if isinstance(left,list):return len(left)==len(right) and all(json_equal(a,b) for a,b in zip(left,right))
    return left==right


def normalize(text):
    return ' '.join(text.casefold().split())


def validate_dataset(dataset):
    if not isinstance(dataset,dict):raise ValueError('Dataset must be an object')
    if dataset.get('schema_version') != 1 or not dataset.get('documents') or not dataset.get('cases'):
        raise ValueError('Need versioned documents and nonempty cases')
    for key in ('dataset_version', 'scope'):
        if not isinstance(dataset.get(key), str) or not dataset[key].strip():
            raise ValueError('Missing dataset '+key)
    documents = dataset['documents']
    if not isinstance(documents, dict) or not isinstance(dataset['cases'], list):
        raise ValueError('Documents/cases have invalid types')
    for name, text in documents.items():
        if not isinstance(name, str) or any(x in name for x in ('/', '\\', '\x00')) or not name.endswith(('.txt', '.md')):
            raise ValueError('Dataset document names must be plain TXT/MD filenames')
        if not isinstance(text, str) or not text.strip() or len(text.encode('utf8')) > 20 * 1024 * 1024:
            raise ValueError('Invalid dataset document')
    seen = set()
    for case in dataset['cases']:
        if not isinstance(case,dict):raise ValueError('Case must be an object')
        if not isinstance(case.get('id'), str) or not case['id'] or case['id'] in seen:
            raise ValueError('Case IDs must be nonempty and unique')
        seen.add(case['id'])
        for key in ('question', 'reference_answer', 'category'):
            if not isinstance(case.get(key), str) or not case[key].strip():
                raise ValueError('Missing case '+key)
        if len(case['question']) > 2000 or type(case.get('unanswerable')) is not bool:
            raise ValueError('Invalid question or answerability')
        history = case.get('history', [])
        if (not isinstance(history, list) or len(history)>6 or
            any(not isinstance(turn, dict) or turn.get('role') not in ('user','assistant') or
                not isinstance(turn.get('content'), str) or not 0<len(turn['content'])<=8000 for turn in history) or
            sum(len(turn['content']) for turn in history)>24000):
            raise ValueError('Invalid history')
        for key in ('forbidden_patterns','refusal_patterns'):
            if not isinstance(case.get(key, []), list):
                raise ValueError('Pattern collections must be lists')
        facts = case.get('facts', [])
        if not isinstance(facts, list) or bool(facts) == case['unanswerable']:
            raise ValueError('Answerable cases need facts; unanswerable cases must not invent them')
        patterns = list(case.get('forbidden_patterns', []))
        if case['unanswerable']:
            if not case.get('refusal_patterns'):
                raise ValueError('Unanswerable case needs refusal checks')
            patterns += case['refusal_patterns']
        for fact in facts:
            if not isinstance(fact,dict) or not isinstance(fact.get('source'),str) or fact['source'] not in documents or not isinstance(fact.get('quote'),str) or not fact['quote']:
                raise ValueError('Fact must cite an existing source and exact evidence')
            if normalize(fact['quote']) not in normalize(documents[fact['source']]):
                raise ValueError('Gold evidence absent from source: '+case['id'])
            if not isinstance(fact.get('patterns'),list) or not fact['patterns']:
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


def verify_report(report, reference):
    try:
        _verify_report(report,reference)
    except (KeyError,TypeError,AttributeError,UnicodeError) as exc:
        raise ValueError('Malformed report structure or response encoding') from exc


def _verify_report(report, reference):
    if report.get('schema_version') != 2 or not report.get('run_id') or not report.get('rows'):
        raise ValueError('Invalid report; schema 1 requires explicit migration')
    if report.get('dataset_sha256') != reference.sha256:
        raise ValueError('Dataset changed since generation')
    data = reference.data
    if (report.get('suite_cases') != len(data['cases']) or report.get('dataset_version') != data['dataset_version']
            or report.get('scope') != data['scope']):
        raise ValueError('Report suite metadata differs from reference dataset')
    rows = report['rows']
    ids = [row['id'] for row in rows]
    expected = list(reference.cases)
    if ids != expected[:len(ids)] or len(ids)>len(expected):
        raise ValueError('Cases must be a unique dataset prefix in dataset order')
    if type(report.get('complete')) is not bool or report['complete'] != (ids == expected):
        raise ValueError('Report completeness differs from dataset coverage')
    for row in rows:
        case = reference.cases[row['id']]
        if row.get('case_sha256') != response_hash(case) or any(row.get(k) != case[k] for k in
                ('question','reference_answer','category','unanswerable')):
            raise ValueError('Report case differs from reference dataset')
        raw = row.get('response_json')
        if (not isinstance(raw,str) or fingerprint(raw.encode('utf8')) != row.get('response_sha256')
                or not json_equal(json.loads(raw), row['response'])):
            raise ValueError('Modified response or serialized response mismatch')
        if row.get('error') is not None and (not isinstance(row['error'],str) or not row['error']):
            raise ValueError('Invalid execution error')
        serialize(row['response'])  # Reject NaN/Infinity even when both projections contain it.
        if record_hash(row) != row.get('record_sha256') or not json_equal(json.loads(row['record_json']),record_value(row)):
            raise ValueError('Modified execution record')
        if row.get('assessment') != score_response(case,row['response'],row['error']):
            raise ValueError('Stored assessment differs from recomputed reference checks')
    healthy = all(row['assessment']['checks']['execution'] for row in rows)
    if type(report.get('all_executed')) is not bool or report['all_executed'] != healthy:
        raise ValueError('Execution summary differs from recorded results')


def summarize(report, reference, review=None):
    verify_report(report, reference)
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
            if item.get('record_sha256') != known[item['id']]['record_sha256']:
                raise ValueError('Human review execution-record binding does not match')
            for key in ('correctness', 'groundedness'):
                if item.get(key) not in ('pass', 'fail', 'unsure', 'pending'):
                    raise ValueError('Invalid human verdict')
            if (item['correctness'] != 'pending' or item['groundedness'] != 'pending') and (not isinstance(item.get('reviewer'), str) or not item['reviewer'].strip()):
                raise ValueError('Completed human labels need a reviewer')
            if not known[item['id']]['assessment']['checks']['execution'] and (item['correctness']=='pass' or item['groundedness']=='pass'):
                raise ValueError('An execution failure cannot be reviewed as a correct/grounded answer')
            labels.append(item)
        reviewed = [item for item in labels if item['correctness'] != 'pending']
        decisive = [item for item in reviewed if item['correctness'] in ('pass', 'fail')]
        grounded = [item for item in labels if item['groundedness'] in ('pass', 'fail')]
        full = summary['complete_suite'] and report['all_executed']
        summary['human_review'] = {
            'reviewed': len(reviewed), 'coverage': len(reviewed)/total,
            'accuracy_on_decisive_reviews': sum(x['correctness']=='pass' for x in decisive)/len(decisive) if decisive else None,
            'confirmed_suite_accuracy': sum(x['correctness']=='pass' for x in decisive)/total if full and len(decisive)==total else None,
            'confirmed_suite_groundedness': sum(x['groundedness']=='pass' for x in grounded)/total if full and len(grounded)==total else None,
        }
    return summary


def review_template(report, reference):
    verify_report(report, reference)
    return {'run_id': report['run_id'], 'dataset_sha256': report['dataset_sha256'],
            'instructions': 'Review the whole answer against source documents, including extra claims, negations, units, dates and refusal. Do not treat pattern hits as human correctness.',
            'rows': [{'id': row['id'], 'response_sha256': row['response_sha256'], 'record_sha256': row['record_sha256'],
                      'question': row['question'], 'reference_answer': row['reference_answer'],
                      'answer': row['response'].get('answer', '') if isinstance(row['response'],dict) else '', 'correctness': 'pending',
                      'groundedness': 'pending', 'reviewer': '', 'notes': ''} for row in report['rows']]}
