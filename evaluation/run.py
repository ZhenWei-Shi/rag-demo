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

from evaluation.metrics import (fingerprint, response_hash, review_template, score_response,
                                summarize, validate_dataset)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT/'evaluation/dataset.json'


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    stage = path.with_suffix(path.suffix+'.tmp')
    stage.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
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
    dataset, digest = load_dataset(args.dataset)
    os.environ['RAG_DATA_DIR'] = str(directory/'data')
    os.environ['LLM_PROVIDER'] = 'ollama'
    os.environ['OLLAMA_MODEL'] = args.model
    os.chdir(ROOT)
    import ollama
    import httpx
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
        last.update({'done_reason':value.done_reason, 'prompt_eval_count':value.prompt_eval_count,
                     'eval_count':value.eval_count})
        return value
    ollama.chat = local_chat
    try:
        commit = subprocess.run(['git','-c',f'safe.directory={ROOT.as_posix()}', 'rev-parse','HEAD'],cwd=ROOT,
                                capture_output=True,text=True,check=True).stdout.strip()
        dirty = bool(subprocess.run(['git','-c',f'safe.directory={ROOT.as_posix()}', 'status','--porcelain'],cwd=ROOT,
                                    capture_output=True,text=True,check=True).stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = None, None
    report = {'schema_version':1,'run_id':uuid4().hex,'created_at':datetime.now(timezone.utc).isoformat(),
              'dataset_sha256':digest,'dataset_version':dataset['dataset_version'],'suite_cases':len(dataset['cases']),
              'scope':dataset['scope'],'provider':'ollama','model':model.model,'model_digest':model.digest,
              'generation':generation,'git_commit':commit,'working_tree_dirty':dirty,
              'complete':False,'rows':[]}
    selected = dataset['cases'][:args.limit] if args.limit else dataset['cases']
    write_json(args.output,report)
    with TestClient(app.app, raise_server_exceptions=False) as api:
        for name, content in dataset['documents'].items():
            response = api.post('/upload',files={'file':(name,content.encode('utf8'))})
            if response.status_code != 200:
                raise ValueError('Synthetic corpus ingestion failed with HTTP '+str(response.status_code))
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
                if last.get('done_reason') == 'length':
                    error = 'GENERATION_TOKEN_LIMIT'
            except Exception as exc:
                # Exception text may include request configuration; record only its type.
                error = type(exc).__name__
            row = {'id':case['id'],'category':case['category'],'question':case['question'],
                   'reference_answer':case['reference_answer'],'unanswerable':case['unanswerable'],
                   'response':result,'response_sha256':response_hash(result),
                   'seconds':round(time.perf_counter()-started,3),'generation':last.copy(),
                   'assessment':score_response(case,result,error)}
            report['rows'].append(row)
            write_json(args.output, report)
            print(f'{index}/{len(selected)} {case["id"]}: '+('rule-pass' if row['assessment']['rule_pass'] else 'REVIEW'),flush=True)
    report['complete'] = len(selected) == report['suite_cases']
    report['summary'] = summarize(report)
    write_json(args.output,report)
    write_json(Path(args.output).with_name(Path(args.output).stem+'.review.json'),review_template(report))
    print(json.dumps(report['summary'],ensure_ascii=False),flush=True)


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
    args = parser.parse_args()
    if args.command == 'score':
        report = json.loads(args.report.read_text(encoding='utf8'))
        review = json.loads(args.review.read_text(encoding='utf8')) if args.review else None
        result = summarize(report,review)
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
