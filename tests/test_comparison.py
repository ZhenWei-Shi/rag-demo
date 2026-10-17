import copy
import hashlib
import json
from pathlib import Path
import pytest
from evaluation.compare import compare
from evaluation.metrics import Reference,verify_report

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'evaluation/baselines/2026-10-16-local-v1'


def load(path):return json.loads(path.read_text(encoding='utf8'))


def test_published_baseline_exact_bytes_and_human_judgments():
    manifest=load(BASE/'manifest.json')
    for name,digest in manifest['files_sha256'].items():assert hashlib.sha256((BASE/name).read_bytes()).hexdigest()==digest,name
    before=load(BASE/'report.json');ref=Reference.load(BASE/'dataset.json')
    result=compare(ref,before,before,load(BASE/'review.json'),load(BASE/'review.json'))
    assert result['before_human_accuracy']==28/34
    assert result['human_accuracy_delta']==0
    assert result['retrieval_unchanged_for_all']


def test_new_answers_never_inherit_old_human_accuracy():
    before=load(BASE/'report.json');ref=Reference.load(BASE/'dataset.json')
    result=compare(ref,before,before,load(BASE/'review.json'))
    assert result['after_human_accuracy'] is None and result['human_accuracy_delta'] is None


@pytest.mark.parametrize('key,value',[('model_digest','another-model'),('generation',{'seed':999}),('provider','cloud')])
def test_incomparable_run_settings_rejected(key,value):
    before=load(BASE/'report.json');after=copy.deepcopy(before);after[key]=value
    with pytest.raises(ValueError,match='Incomparable'):compare(Reference.load(BASE/'dataset.json'),before,after)


def test_saved_experiment_assessments_are_recomputed():
    root=ROOT/'evaluation/experiments/quality-v1'
    for name,dataset in [('transfer-before.json','transfer-v1.json'),('candidate-1-original.json','dataset.json'),('candidate-1-transfer.json','transfer-v1.json'),('candidate-2-original.json','dataset.json'),('candidate-2-transfer.json','transfer-v1.json')]:
        verify_report(load(root/name),Reference.load(ROOT/'evaluation'/dataset))


def test_published_owner_result_manifest_and_comparison():
    folder=ROOT/'evaluation/experiments/quality-v1';manifest=load(folder/'owner-manifest.json')
    for name,digest in manifest['files_sha256'].items():assert hashlib.sha256((folder/name).read_bytes()).hexdigest()==digest,name
    result=compare(Reference.load(BASE/'dataset.json'),load(BASE/'report.json'),load(folder/'candidate-2-original.json'),load(BASE/'review.json'),load(folder/'candidate-2-owner-review.json'))
    assert result['before_human_accuracy']==28/34
    assert result['after_human_accuracy']==32/34
    assert result['human_accuracy_delta']==pytest.approx(4/34)
    public=load(folder/'comparison-owner.json')
    assert len(public['human_gains'])==5 and public['human_regressions']==['museum-refund']
