import copy
import json
from pathlib import Path
import pytest
from evaluation.metrics import (response_hash, review_template, score_response, summarize,
                                validate_dataset, verify_report, Reference, bind_row, serialize)
from evaluation import metrics
from evaluation.run import finalize, generation_error, migrate, encodable_response

CASE={'id':'fact','category':'number','question':'What is the booking window?',
      'reference_answer':'23 days.','unanswerable':False,
      'facts':[{'source':'memo.txt','quote':'Booking window: 23 days.','patterns':[r'(?<!\d)23(?!\d)']}],
      'forbidden_patterns':[r'not\s+23']}
RESPONSE={'answer':'23 days.','sources':['memo.txt'],'chunks':[{'source':'memo.txt','text':'Booking window: 23 days.'}]}

def reference(count=1):
    cases=[dict(copy.deepcopy(CASE),id=str(i)) for i in range(count)]
    return Reference(serialize({'schema_version':1,'dataset_version':'test-v1','scope':'fixture',
                               'documents':{'memo.txt':'Booking window: 23 days.'},'cases':cases}).encode('utf8'))


def make_report(count=1,complete=True):
    ref=reference(count)
    rows=[bind_row(case,copy.deepcopy(RESPONSE)) for case in ref.data['cases']]
    if not complete:rows=rows[:-1]
    return {'schema_version':2,'run_id':'run-a','dataset_sha256':ref.sha256,
            'dataset_version':'test-v1','scope':'fixture','suite_cases':count,
            'complete':complete,'all_executed':True,'rows':rows}


def summarize(report,review=None):
    return metrics.summarize(report,reference(report['suite_cases']),review)


def review_template(report):
    return metrics.review_template(report,reference(report['suite_cases']))


def test_gold_dataset_evidence_and_reference_answers_are_consistent():
    data=json.loads((Path(__file__).resolve().parents[1]/'evaluation/dataset.json').read_text(encoding='utf8'))
    validate_dataset(data)
    for case in data['cases']:
        sources=list(dict.fromkeys(f['source'] for f in case['facts']))
        response={'answer':case['reference_answer'],'sources':sources,
                  'chunks':[{'source':name,'text':data['documents'][name]} for name in sources]}
        assert score_response(case,response)['rule_pass'], case['id']

def test_number_substring_and_explicit_negation_do_not_pass():
    for answer in ['230 days.','not 23 days.']:
        result=score_response(CASE,{**RESPONSE,'answer':answer})
        assert not result['rule_pass']

def test_quote_from_wrong_source_is_not_evidence():
    result=score_response(CASE,{**RESPONSE,'chunks':[{'source':'other.txt','text':'Booking window: 23 days.'}]})
    assert not result['checks']['evidence_retrieval']
    assert not result['rule_pass']

def test_missing_source_is_distinct_from_missing_answer_fact():
    result=score_response(CASE,{**RESPONSE,'sources':[]})
    assert result['checks']['required_facts'] is True
    assert result['checks']['source_coverage'] is False

def test_keyword_hit_does_not_become_confirmed_correctness():
    report=make_report()
    response={**RESPONSE,'answer':'23 days. Also, the founder is an astronaut named Alice.'}
    report['rows'][0]=bind_row(reference().data['cases'][0],response)
    result=summarize(report)
    assert result['rule_pass_rate']==1
    assert result['human_review']['confirmed_suite_accuracy'] is None
    assert result['human_review']['confirmed_suite_groundedness'] is None

def test_refusal_with_invented_year_is_rejected_by_rule():
    case={'unanswerable':True,'refusal_patterns':['not provided'], 'forbidden_patterns':[r'\b20\d\d\b'],'facts':[]}
    assert score_response(case,{'answer':'The year is not provided.','sources':[],'chunks':[]})['rule_pass']
    assert not score_response(case,{'answer':'The year is not provided, but probably 2020.','sources':[],'chunks':[]})['rule_pass']

@pytest.mark.parametrize('response',[{},[],{'answer':None},{**RESPONSE,'chunks':[None]},{**RESPONSE,'sources':[1]}])
def test_bad_or_empty_outputs_are_execution_failures(response):
    assert not score_response(CASE,response)['checks']['execution']

def test_transport_error_never_counts_as_a_refusal():
    case={'unanswerable':True,'facts':[],'refusal_patterns':['not found'],'forbidden_patterns':[]}
    assert not score_response(case,{'answer':'not found','sources':[],'chunks':[]},'HTTP_404')['rule_pass']

def test_partial_reviews_report_coverage_without_suite_accuracy():
    report=make_report(2)
    review=review_template(report)
    review['rows'][0].update(correctness='pass',groundedness='pass',reviewer='fixture')
    result=summarize(report,review)['human_review']
    assert result['coverage']==0.5
    assert result['accuracy_on_decisive_reviews']==1
    assert result['confirmed_suite_accuracy'] is None

def test_complete_review_allows_dataset_scoped_accuracy():
    report=make_report(2);review=review_template(report)
    for item in review['rows']:item.update(correctness='pass',groundedness='pass',reviewer='fixture')
    review['rows'][1]['correctness']='fail'
    result=summarize(report,review)['human_review']
    assert result['confirmed_suite_accuracy']==0.5
    assert result['confirmed_suite_groundedness']==1

def test_unsure_or_partial_run_cannot_be_confirmed():
    report=make_report();review=review_template(report)
    review['rows'][0].update(correctness='unsure',groundedness='pass',reviewer='fixture')
    assert summarize(report,review)['human_review']['confirmed_suite_accuracy'] is None
    report=make_report(2,complete=False);review=review_template(report)
    review['rows'][0].update(correctness='pass',groundedness='pass',reviewer='fixture')
    assert summarize(report,review)['human_review']['confirmed_suite_accuracy'] is None

@pytest.mark.parametrize('key,value',[('run_id','another-run'),('dataset_sha256','other-dataset')])
def test_old_review_cannot_bind_to_new_run_or_dataset(key,value):
    report=make_report();review=review_template(report);review[key]=value
    with pytest.raises(ValueError):summarize(report,review)

def test_changed_answer_invalidates_report_and_human_review():
    report=make_report();review=review_template(report)
    report['rows'][0]['response']['answer']='24 days.'
    with pytest.raises(ValueError,match='[Mm]odified response'):summarize(report,review)
    report['rows'][0]=bind_row(reference().data['cases'][0],report['rows'][0]['response'])
    with pytest.raises(ValueError,match='binding'):summarize(report,review)

def test_duplicate_reviews_or_missing_reviewer_rejected():
    report=make_report();review=review_template(report)
    review['rows'].append(copy.deepcopy(review['rows'][0]))
    with pytest.raises(ValueError,match='Duplicate'):summarize(report,review)
    review['rows'].pop();review['rows'][0]['correctness']='pass'
    with pytest.raises(ValueError,match='reviewer'):summarize(report,review)

def test_execution_failure_cannot_be_manually_approved_as_a_correct_answer():
    report=make_report();report['rows'][0]=bind_row(reference().data['cases'][0],RESPONSE,'HTTP_500');report['all_executed']=False
    review=review_template(report);review['rows'][0].update(correctness='pass',reviewer='fixture')
    with pytest.raises(ValueError,match='execution failure'):summarize(report,review)

def test_gold_quote_must_exist_and_case_ids_are_unique():
    data={'schema_version':1,'dataset_version':'test','scope':'fixture','documents':{'memo.txt':'Booking window: 23 days.'},'cases':[copy.deepcopy(CASE)]}
    validate_dataset(data)
    data['cases'][0]['facts'][0]['quote']='imaginary passage'
    with pytest.raises(ValueError,match='absent'):validate_dataset(data)
    data['cases']=[copy.deepcopy(CASE),copy.deepcopy(CASE)]
    with pytest.raises(ValueError,match='unique'):validate_dataset(data)


@pytest.mark.parametrize('change',[
    lambda r:r['rows'][0]['assessment']['checks'].update(required_facts=False),
    lambda r:r.update(complete=False),
    lambda r:r.update(suite_cases=1),
    lambda r:r['rows'].pop(),
    lambda r:r['rows'][0].update(category='edited'),
    lambda r:r['rows'][0].update(error='HTTP_500'),
    lambda r:r.update(all_executed=False),
])
def test_dataset_backed_verification_rejects_tampered_scores_and_completeness(change):
    report=make_report(2);change(report)
    with pytest.raises(ValueError):verify_report(report,reference(2))


def test_floating_point_bytes_and_unicode_are_preserved_and_nonfinite_rejected():
    value={**RESPONSE,'float':1.0,'small':1e-5,'unicode':'银杉'}
    row=bind_row(reference().data['cases'][0],value)
    assert '1.0' in row['response_json'] and '1e-05' in row['response_json']
    report=make_report();report['rows'][0]=row
    verify_report(report,reference())
    with pytest.raises(ValueError):bind_row(CASE,{**RESPONSE,'float':float('nan')})


def test_failed_attempt_preserves_previous_baseline_and_review(tmp_path):
    output=tmp_path/'latest.json';review=tmp_path/'latest.review.json'
    output.write_text('prior baseline');review.write_text('prior labels')
    report=make_report();report['rows'][0]=bind_row(reference().data['cases'][0],{},'HTTP_500');report['all_executed']=False
    finalize(report,reference(),output)
    assert output.read_text()=='prior baseline' and review.read_text()=='prior labels'
    checkpoint=json.loads((tmp_path/'latest.partial.json').read_text())
    assert checkpoint['complete'] and checkpoint['summary']['execution_errors']==1
    assert checkpoint['summary']['human_review']['confirmed_suite_accuracy'] is None


def test_generation_parameters_need_observed_local_call():
    assert generation_error(None,{})=='GENERATION_NOT_OBSERVED'
    assert generation_error('HTTP_500',{})=='HTTP_500'
    assert generation_error(None,{'observed_calls':1}) is None


def test_nonstring_reviewer_is_not_a_human_approval():
    report=make_report();review=review_template(report)
    review['rows'][0].update(correctness='pass',reviewer=None)
    with pytest.raises(ValueError,match='reviewer'):summarize(report,review)


def test_explicit_legacy_migration_preserves_answers_and_verdicts():
    report=make_report();old=copy.deepcopy(report);old['schema_version']=1
    for row in old['rows']:
        for key in ('response_json','case_sha256','record_sha256','error'):row.pop(key)
    migrated=migrate(old,reference(),'original-file-sha')
    assert migrated['rows'][0]['response']==report['rows'][0]['response']
    assert migrated['rows'][0]['assessment']==report['rows'][0]['assessment']
    verify_report(migrated,reference())


@pytest.mark.parametrize('history',[None,[{'role':'system','content':'bad'}],[{'role':'user','content':None}]])
def test_dataset_rejects_invalid_history(history):
    data=copy.deepcopy(reference().data);data['cases'][0]['history']=history
    with pytest.raises(ValueError,match='history'):validate_dataset(data)


def test_partial_attempt_cannot_replace_existing_full_custom_baseline(tmp_path):
    output=tmp_path/'custom.json';prior=make_report(2)
    output.write_text(json.dumps(prior),encoding='utf8')
    assert not finalize(make_report(2,complete=False),reference(2),output)
    assert json.loads(output.read_text())==prior


def test_new_run_archives_human_labels_and_repeated_same_run_keeps_them(tmp_path):
    output=tmp_path/'latest.json';report=make_report()
    finalize(report,reference(),output)
    review_path=tmp_path/'latest.review.json';review=json.loads(review_path.read_text())
    review['rows'][0].update(correctness='fail',reviewer='fixture')
    review_path.write_text(json.dumps(review))
    finalize(report,reference(),output)
    assert json.loads(review_path.read_text())==review
    report['run_id']='new-run';finalize(report,reference(),output)
    archived=list((tmp_path/'archive').glob('review-*.json'))
    assert len(archived)==1 and json.loads(archived[0].read_text())==review
    assert json.loads(review_path.read_text())['rows'][0]['correctness']=='pending'


@pytest.mark.parametrize('value',[{'answer':'\ud800'}, {'answer':float('inf')}])
def test_invalid_encoding_is_one_case_error(value):
    assert encodable_response(value)==({},'INVALID_RESPONSE_ENCODING')
    assert encodable_response(value,'HTTP_500')==({},'HTTP_500')
