"""Isolated, local-only answer evaluation through the real FastAPI upload/ask API."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from uuid import uuid4
from datetime import datetime, timezone

from evaluation.metrics import (fingerprint, response_hash, review_template,
                                summarize, validate_dataset, Reference, bind_row, verify_report, serialize)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT/'evaluation/dataset.json'


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    stage = path.with_suffix(path.suffix+'.tmp')
    stage.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf8')
    os.replace(stage, path)


def load_dataset(path):
    raw = Path(path).read_bytes()
    dataset = json.loads(raw)
    validate_dataset(dataset)
    return dataset, fingerprint(raw)


def worker(args):
    directory = Path(args.worker_data).resolve()
    if directory.parent != Path(tempfile.gettempdir()).resolve() or not directory.name.startswith('rag-accuracy-'):
        raise ValueError('Worker only accepts its disposable temporary directory')
    reference = Reference.load(args.dataset)
    dataset, digest = reference.data, reference.sha256
    os.environ['RAG_DATA_DIR'] = str(directory/'data')
    os.environ['LLM_PROVIDER'] = 'ollama'
    os.environ['OLLAMA_MODEL'] = args.model
    os.chdir(ROOT)
    import ollama
    from fastapi.testclient import TestClient
    import app
    client = ollama.Client(host='http://127.0.0.1:11434', timeout=90)
    installed = client.list().models
    wanted = args.model if ':' in args.model else args.model+':latest'
    model = next((item for item in installed if item.model == wanted), None)
    if model is None:
        raise ValueError('Requested Ollama model is not installed; pull it explicitly first')
    generation = {'temperature': 0, 'seed': 101, 'num_predict': 512}
    last = {}
    def local_chat(*chat_args, **kwargs):
        kwargs['options'] = {**kwargs.get('options', {}), **generation}
        value = client.chat(*chat_args, **kwargs)
        last.update({'observed_calls':last.get('observed_calls',0)+1, 'model':value.model, 'done_reason':value.done_reason, 'prompt_eval_count':value.prompt_eval_count,
                     'eval_count':value.eval_count, 'done_reasons':last.get('done_reasons',[])+[value.done_reason]})
        return value
    ollama.chat = local_chat
    try:
        commit = subprocess.run(['git','-c',f'safe.directory={ROOT.as_posix()}', 'rev-parse','HEAD'],cwd=ROOT,
                                capture_output=True,text=True,check=True).stdout.strip()
        dirty = bool(subprocess.run(['git','-c',f'safe.directory={ROOT.as_posix()}', 'status','--porcelain'],cwd=ROOT,
                                    capture_output=True,text=True,check=True).stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = None, None
    report = {'schema_version':2,'run_id':uuid4().hex,'created_at':datetime.now(timezone.utc).isoformat(),
              'dataset_sha256':digest,'dataset_version':dataset['dataset_version'],'suite_cases':len(dataset['cases']),
              'scope':dataset['scope'],'provider':'ollama','model':model.model,'model_digest':model.digest,
              'generation':generation,'git_commit':commit,'working_tree_dirty':dirty,
              'complete':False,'all_executed':True,'rows':[]}
    selected = dataset['cases'][:args.limit] if args.limit else dataset['cases']
    checkpoint = Path(args.output).with_name(Path(args.output).stem+'.partial.json')
    write_json(checkpoint,report)
    with TestClient(app.app, raise_server_exceptions=False) as api:
        for name, content in dataset['documents'].items():
            response = api.post('/upload',files={'file':(name,content.encode('utf8'))})
            if response.status_code != 200:
                raise ValueError('Synthetic corpus ingestion failed with HTTP '+str(response.status_code))
        listed = api.get('/documents').json()['documents']
        if sorted(listed) != sorted(dataset['documents']):
            raise ValueError('Disposable library does not match the reference corpus')
        if not (directory/'data'/'versions.sqlite3').is_file():
            raise ValueError('Disposable library manifest was not created')
        for index, case in enumerate(selected,1):
            started = time.perf_counter()
            last.clear()
            result, error = {}, None
            try:
                response = api.post('/ask',json={'question':case['question'],'history':case.get('history',[])})
                if response.status_code == 200:
                    result = response.json()
                else:
                    error = 'HTTP_'+str(response.status_code)
                error = generation_error(error, last)
                if 'length' in last.get('done_reasons',[]):
                    error = error or 'GENERATION_TOKEN_LIMIT'
            except Exception as exc:
                # Exception text may include request configuration; record only its type.
                error = type(exc).__name__
            result,error = encodable_response(result,error)
            row = bind_row(case,result,error,last.copy(),seconds=round(time.perf_counter()-started,3))
            report['rows'].append(row)
            report['complete'] = len(report['rows']) == report['suite_cases']
            report['all_executed'] = all(r['assessment']['checks']['execution'] for r in report['rows'])
            write_json(checkpoint, report)
            print(f'{index}/{len(selected)} {case["id"]}: '+('rule-pass' if row['assessment']['rule_pass'] else 'REVIEW'),flush=True)
    promoted = finalize(report,reference,args.output)
    print(json.dumps(report['summary'],ensure_ascii=False),flush=True)
    if not promoted:
        raise SystemExit(2)


def encodable_response(result,error=None):
    try:
        serialize(result).encode('utf8')
        return result,error
    except (UnicodeError,ValueError,TypeError):
        return {},error or 'INVALID_RESPONSE_ENCODING'


def generation_error(error, observation):
    return error or (None if observation.get('observed_calls',0)>0 else 'GENERATION_NOT_OBSERVED')


def finalize(report, reference, output):
    report['summary'] = summarize(report,reference)
    checkpoint = Path(output).with_name(Path(output).stem+'.partial.json')
    write_json(checkpoint, report)
    # Healthy partial smoke outputs are allowed in separate files, but cannot
    # replace a full baseline. Keep both prior reports and human notes by content.
    output = Path(output)
    if not report['all_executed']:
        return False
    prior = json.loads(output.read_text(encoding='utf8')) if output.exists() else None
    if not report['complete'] and prior and prior.get('complete'):
        return False
    template = review_template(report,reference)
    review_path = output.with_name(output.stem+'.review.json')
    if review_path.exists():
        previous = review_path.read_bytes()
        old_review = json.loads(previous)
        if old_review.get('run_id') == report['run_id']:
            summarize(report,reference,old_review)
            template = old_review
        else:
            archive = output.parent/'archive'/('review-'+fingerprint(previous)+'.json')
            write_json(archive,old_review)
    if prior and prior.get('run_id') != report['run_id']:
        previous = output.read_bytes()
        write_json(output.parent/'archive'/('report-'+fingerprint(previous)+'.json'),prior)
    write_json(review_path,template)
    write_json(output,report)
    return True


def migrate(report, reference, source_digest):
    if report.get('schema_version') != 1 or report.get('dataset_sha256') != reference.sha256:
        raise ValueError('Only schema 1 reports from this exact dataset may be migrated')
    old_rows = report['rows']
    report['rows'] = []
    for old in old_rows:
        case = reference.cases[old['id']]
        if response_hash(old['response']) != old['response_sha256']:
            raise ValueError('Modified legacy response')
        if any(old.get(k)!=case[k] for k in ('question','reference_answer','category','unanswerable')):
            raise ValueError('Legacy case differs from frozen dataset')
        row = bind_row(case,old['response'],old['assessment']['error'],old.get('generation'),seconds=old.get('seconds'))
        if row['assessment'] != old['assessment']:
            raise ValueError('Legacy checks changed; migration must not change verdicts')
        report['rows'].append(row)
    report.update(schema_version=2, all_executed=all(r['assessment']['checks']['execution'] for r in report['rows']),
                  migration={'from_schema':1,'source_file_sha256':source_digest,
                             'note':'Original responses retained; no new generation. Legacy observations are unchanged.'})
    verify_report(report,reference)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command',required=True)
    run = commands.add_parser('run',help='Generate real local answers in a disposable library')
    run.add_argument('--dataset',type=Path,default=DEFAULT_DATASET)
    run.add_argument('--output',type=Path,default=ROOT/'evaluation/results/latest.json')
    run.add_argument('--model',default='llama3.2')
    run.add_argument('--limit',type=int)
    run.add_argument('--worker-data',help=argparse.SUPPRESS)
    run.add_argument('--timeout',type=int,default=1200,help='Whole worker wall-clock limit in seconds')
    score = commands.add_parser('score',help='Recompute summary, optionally with response-bound human labels')
    score.add_argument('--report',type=Path,required=True)
    score.add_argument('--review',type=Path)
    score.add_argument('--output',type=Path)
    check = commands.add_parser('verify',help='Validate dataset, responses and every recomputed rule')
    check.add_argument('--report',type=Path,required=True)
    migration = commands.add_parser('migrate',help='Explicitly migrate schema 1, preserving original answers/verdicts')
    migration.add_argument('--report',type=Path,required=True)
    migration.add_argument('--output',type=Path,required=True)
    for command in (score,check,migration):command.add_argument('--dataset',type=Path,default=DEFAULT_DATASET)
    args = parser.parse_args()
    if args.command in ('verify','migrate'):
        raw=args.report.read_bytes();report=json.loads(raw);reference=Reference.load(args.dataset)
        if args.command=='migrate':
            if args.output.resolve()==args.report.resolve():parser.error('Preserve the original report in a separate file')
            report=migrate(report,reference,fingerprint(raw));finalize(report,reference,args.output)
        else:verify_report(report,reference)
        print('Report verified against frozen dataset')
        return
    if args.command == 'score':
        report = json.loads(args.report.read_text(encoding='utf8'))
        review = json.loads(args.review.read_text(encoding='utf8')) if args.review else None
        result = summarize(report,Reference.load(args.dataset),review)
        if args.output:write_json(args.output,result)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return
    if args.limit is not None and args.limit <= 0 or not 1 <= args.timeout <= 7200:
        parser.error('Use a positive limit and timeout in 1..7200')
    args.dataset, args.output = args.dataset.resolve(), args.output.resolve()
    load_dataset(args.dataset)
    if args.limit and args.output == ROOT/'evaluation/results/latest.json':
        parser.error('Partial runs need a separate --output; preserve the full-suite baseline')
    if args.worker_data:
        worker(args)
        return
    # Parent owns cleanup after the child releases Chroma native handles on Windows.
    with tempfile.TemporaryDirectory(prefix='rag-accuracy-') as directory:
        env = os.environ.copy()
        env.update({'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','ANONYMIZED_TELEMETRY':'False',
                    'OMP_NUM_THREADS':'2','MKL_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'2'})
        command = [sys.executable,'-m','evaluation.run','run','--dataset',str(args.dataset),
                   '--output',str(args.output),'--model',args.model,'--worker-data',directory]
        if args.limit:command += ['--limit',str(args.limit)]
        proc = subprocess.Popen(command,cwd=ROOT,env=env)
        try:
            code = proc.wait(timeout=args.timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            proc.kill();proc.wait()
            raise SystemExit('Evaluation interrupted; checkpoint remains incomplete and is not an accuracy result')
        if code:raise SystemExit(code)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError) as exc:
        raise SystemExit(f'Evaluation configuration/report error: {exc}')
