import copy
import json
from pathlib import Path
import pytest
from evaluation.metrics import (response_hash, review_template, score_response, summarize,
                                validate_dataset, verify_report)

CASE={'id':'fact','category':'number','question':'What is the booking window?',
      'reference_answer':'23 days.','unanswerable':False,
      'facts':[{'source':'memo.txt','quote':'Booking window: 23 days.','patterns':[r'(?<!\d)23(?!\d)']}],
      'forbidden_patterns':[r'not\s+23']}
RESPONSE={'answer':'23 days.','sources':['memo.txt'],'chunks':[{'source':'memo.txt','text':'Booking window: 23 days.'}]}

def make_report(count=1,complete=True):
    rows=[]
    for i in range(count):
        response=copy.deepcopy(RESPONSE)
        rows.append({'id':str(i),'category':'number','unanswerable':False,'question':CASE['question'],
                     'reference_answer':CASE['reference_answer'],'response':response,
                     'response_sha256':response_hash(response),'assessment':score_response(CASE,response)})
    return {'schema_version':1,'run_id':'run-a','dataset_sha256':'dataset-a','suite_cases':count,'complete':complete,'rows':rows}

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
    report['rows'][0].update(response=response,response_sha256=response_hash(response),assessment=score_response(CASE,response))
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
    review['rows'][0]['correctness']='pass';report['complete']=False
    assert summarize(report,review)['human_review']['confirmed_suite_accuracy'] is None

@pytest.mark.parametrize('key,value',[('run_id','another-run'),('dataset_sha256','other-dataset')])
def test_old_review_cannot_bind_to_new_run_or_dataset(key,value):
    report=make_report();review=review_template(report);review[key]=value
    with pytest.raises(ValueError):summarize(report,review)

def test_changed_answer_invalidates_report_and_human_review():
    report=make_report();review=review_template(report)
    report['rows'][0]['response']['answer']='24 days.'
    with pytest.raises(ValueError,match='modified response'):summarize(report,review)
    report['rows'][0]['response_sha256']=response_hash(report['rows'][0]['response'])
    with pytest.raises(ValueError,match='binding'):summarize(report,review)

def test_duplicate_reviews_or_missing_reviewer_rejected():
    report=make_report();review=review_template(report)
    review['rows'].append(copy.deepcopy(review['rows'][0]))
    with pytest.raises(ValueError,match='Duplicate'):summarize(report,review)
    review['rows'].pop();review['rows'][0]['correctness']='pass'
    with pytest.raises(ValueError,match='reviewer'):summarize(report,review)

def test_execution_failure_cannot_be_manually_approved_as_a_correct_answer():
    report=make_report();report['rows'][0]['assessment']=score_response(CASE,RESPONSE,'HTTP_500')
    review=review_template(report);review['rows'][0].update(correctness='pass',reviewer='fixture')
    with pytest.raises(ValueError,match='execution failure'):summarize(report,review)

def test_gold_quote_must_exist_and_case_ids_are_unique():
    data={'schema_version':1,'documents':{'memo.txt':'Booking window: 23 days.'},'cases':[copy.deepcopy(CASE)]}
    validate_dataset(data)
    data['cases'][0]['facts'][0]['quote']='imaginary passage'
    with pytest.raises(ValueError,match='absent'):validate_dataset(data)
    data['cases']=[copy.deepcopy(CASE),copy.deepcopy(CASE)]
    with pytest.raises(ValueError,match='unique'):validate_dataset(data)
