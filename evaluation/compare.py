"""Compare saved runs with matched dataset/model settings; never infer human labels."""
import argparse
import json
from pathlib import Path
from evaluation.metrics import Reference, summarize


def compare(reference,before,after,before_review=None,after_review=None):
    first=summarize(before,reference,before_review);second=summarize(after,reference,after_review)
    for key in ('model_digest','generation','provider'):
        if before.get(key)!=after.get(key):raise ValueError('Incomparable '+key)
    if not first['complete_suite'] or not second['complete_suite']:raise ValueError('Comparison requires complete suites')
    if not before['all_executed'] or not after['all_executed']:raise ValueError('Resolve execution errors before comparing quality')
    changed=[]
    for old,new in zip(before['rows'],after['rows']):
        changed.append({'id':old['id'],'before_rule':old['assessment']['rule_pass'],'after_rule':new['assessment']['rule_pass'],
          'answer_changed':old['response']['answer']!=new['response']['answer'],
          'retrieval_unchanged':old['response']['chunks']==new['response']['chunks'] and old['response']['sources']==new['response']['sources']})
    human_before=first['human_review']['confirmed_suite_accuracy'];human_after=second['human_review']['confirmed_suite_accuracy']
    return {'dataset_sha256':reference.sha256,'before_run':before['run_id'],'after_run':after['run_id'],
       'model_digest':before['model_digest'],'generation':before['generation'],
       'before_rule_passed':first['rule_passed'],'after_rule_passed':second['rule_passed'],'cases':len(changed),
       'rule_gains':[r['id'] for r in changed if not r['before_rule'] and r['after_rule']],
       'rule_regressions':[r['id'] for r in changed if r['before_rule'] and not r['after_rule']],
       'retrieval_unchanged_for_all':all(r['retrieval_unchanged'] for r in changed),
       'context_matched_cases':sum(r['retrieval_unchanged'] for r in changed),
       'context_matched_before_passed':sum(r['before_rule'] for r in changed if r['retrieval_unchanged']),
       'context_matched_after_passed':sum(r['after_rule'] for r in changed if r['retrieval_unchanged']),
       'before_human_accuracy':human_before,'after_human_accuracy':human_after,
       'human_accuracy_delta':human_after-human_before if human_before is not None and human_after is not None else None,
       'rows':changed,'limitation':'Rules are proxies; newly generated answers require fresh human review. Disclosed synthetic development cases do not establish general accuracy.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('dataset','before','after','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--before-review',type=Path);p.add_argument('--after-review',type=Path);args=p.parse_args()
    load=lambda path:json.loads(path.read_text(encoding='utf8')) if path else None
    result=compare(Reference.load(args.dataset),load(args.before),load(args.after),load(args.before_review),load(args.after_review))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
