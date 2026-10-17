import copy
import json
import re
from pathlib import Path
import pytest
from evaluation.metrics import Reference,bind_row
from evaluation.review_page import build_page

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'evaluation/baselines/2026-10-16-local-v1'
load=lambda name:json.loads((BASE/name).read_text(encoding='utf8'))


def test_new_report_does_not_inherit_baseline_human_labels():
    report=load('report.json');report['run_id']='new-run'
    html=build_page(Reference.load(BASE/'dataset.json'),report,baseline=load('report.json'),baseline_review=load('review.json'))
    payload=json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>',html,re.S).group(1))
    assert payload['review'] is None
    assert payload['summary']['human_review']['confirmed_suite_accuracy'] is None
    assert payload['baseline_review']['rows'][0]['correctness']=='pass'


def test_answer_markup_cannot_escape_json_script():
    ref=Reference.load(BASE/'dataset.json');report=load('report.json')
    attack='</script><img src=x onerror=alert(1)>'
    response=copy.deepcopy(report['rows'][0]['response']);response['answer']=attack
    report['rows'][0]=bind_row(ref.data['cases'][0],response)
    html=build_page(ref,report)
    assert attack not in html
    payload=json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>',html,re.S).group(1))
    assert payload['report']['rows'][0]['response']['answer']==attack
    assert '.innerHTML' not in html


def test_stale_human_review_is_rejected():
    report=load('report.json');report['run_id']='changed'
    with pytest.raises(ValueError,match='different run'):build_page(Reference.load(BASE/'dataset.json'),report,load('review.json'))


def test_different_model_comparison_is_rejected():
    report=load('report.json');report['model_digest']='changed'
    with pytest.raises(ValueError,match='same model'):build_page(Reference.load(BASE/'dataset.json'),report,baseline=load('report.json'))
