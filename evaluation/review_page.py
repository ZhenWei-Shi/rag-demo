"""Generate an offline Chinese card-based human review, with optional paired baseline."""
import argparse
import json
from pathlib import Path
from evaluation.metrics import Reference, summarize, response_hash

ROOT=Path(__file__).resolve().parents[1]


def build_page(reference, report, review=None, baseline=None, baseline_review=None):
    summary=summarize(report,reference,review)
    if baseline:
        summarize(baseline,reference,baseline_review)
        if baseline['model_digest']!=report['model_digest'] or baseline['generation']!=report['generation']:
            raise ValueError('Paired review requires the same model digest and generation parameters')
    payload={'dataset':reference.data,'report':report,'review':review,
             'baseline':baseline,'baseline_review':baseline_review,'summary':summary,
             'review_revision':response_hash(review) if review is not None else 'unreviewed',
             'translations':json.loads((ROOT/'evaluation/review-zh.json').read_text(encoding='utf8'))}
    payload['report']={**report,'summary':summary}
    # JSON is data, never markup; avoid closing the script element from an answer.
    encoded=json.dumps(payload,ensure_ascii=False,allow_nan=False).replace('&','\\u0026').replace('<','\\u003c').replace('>','\\u003e')
    template=(ROOT/'evaluation/review-template.html').read_text(encoding='utf8')
    return template.replace('/*PAYLOAD*/',encoded)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,default=ROOT/'evaluation/dataset.json')
    p.add_argument('--report',type=Path,default=ROOT/'evaluation/results/latest.json')
    p.add_argument('--review',type=Path)
    p.add_argument('--baseline',type=Path)
    p.add_argument('--baseline-review',type=Path)
    p.add_argument('--output',type=Path,default=ROOT/'evaluation/results/review.html')
    args=p.parse_args()
    load=lambda path:json.loads(path.read_text(encoding='utf8')) if path else None
    if args.baseline_review and not args.baseline:p.error('--baseline-review requires --baseline')
    page=build_page(Reference.load(args.dataset),load(args.report),load(args.review),load(args.baseline),load(args.baseline_review))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(page,encoding='utf8')
    print('Chinese review page: '+str(args.output.resolve()))


if __name__=='__main__':main()
