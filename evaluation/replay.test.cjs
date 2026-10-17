const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {spawnSync}=require('node:child_process');
const Replay=require('./replay-provider.cjs');
const verifyFramework=require('./framework-check.cjs');
function fixture(t,error=null,answer='值为23') {
 const directory=fs.mkdtempSync(path.join(os.tmpdir(),'rag-replay-test-'));
 t.after(()=>fs.rmSync(directory,{recursive:true,force:true}));
 const datasetPath=path.join(directory,'dataset.json'),reportPath=path.join(directory,'report.json');
 const data={schema_version:1,dataset_version:'fixture',scope:'synthetic',documents:{'memo.txt':'值为23'},
  cases:[{id:'a',question:' What is the value? ',category:'number',reference_answer:'值为23',unanswerable:false,
   facts:[{source:'memo.txt',quote:'值为23',patterns:['23']}],forbidden_patterns:[]}]};
 fs.writeFileSync(datasetPath,JSON.stringify(data));
 const py=`import json,sys
from evaluation.metrics import Reference,bind_row
ref=Reference.load(sys.argv[1]);error=json.loads(sys.argv[2]);answer=sys.argv[3]
response={'answer':answer,'sources':['memo.txt'],'chunks':[{'source':'memo.txt','text':'值为23'}],'one':1.0,'small':1e-5}
row=bind_row(ref.data['cases'][0],response,error)
print(json.dumps(dict(schema_version=2,run_id='run',model='fixture',complete=True,all_executed=error is None,suite_cases=1,dataset_version='fixture',scope='synthetic',dataset_sha256=ref.sha256,rows=[row]),ensure_ascii=False))`;
 const generated=spawnSync(process.env.RAG_EVAL_PYTHON||'python',['-c',py,datasetPath,JSON.stringify(error),answer],
  {cwd:path.resolve(__dirname,'..'),encoding:'utf8',env:{...process.env,PYTHONIOENCODING:'utf-8'},windowsHide:true});
 assert.equal(generated.status,0,generated.stderr);
 const report=JSON.parse(generated.stdout);
 const write=()=>fs.writeFileSync(reportPath,JSON.stringify(report));write();
 return {config:{datasetPath,reportPath},report,write};
}
function exported(report) {
 const original=report.rows[0];
 const metadata={run_id:report.run_id,case_id:original.id,response_sha256:original.response_sha256,
  record_sha256:original.record_sha256,checks:original.assessment.checks};
 return {results:{results:[{vars:{case_id:original.id},success:original.assessment.rule_pass,
  response:{output:original.response.answer,metadata},gradingResult:{componentResults:
   Object.entries(original.assessment.checks).filter(([,v])=>v!==null).map(([key,pass])=>({pass,score:Number(pass),assertion:{type:'javascript',metric:verifyFramework.labels[key]}}))}}],stats:{errors:0,successes:Number(original.assessment.rule_pass),failures:Number(!original.assessment.rule_pass)}}};
}
test('replays exact Python Unicode/float bytes and trims both question sides',async t=>{
 const f=fixture(t),p=new Replay({config:f.config});
 const result=await p.callApi('What is the value?',{vars:{case_id:'a'}});
 assert.equal(result.output,'值为23');assert.equal(result.metadata.checks.execution,true);
 assert.equal(result.metadata.retrieved_chunks[0].source,'memo.txt');
 assert.ok((await p.callApi('wrong',{vars:{case_id:'a'}})).error);
 assert.ok((await p.callApi('What is the value?',{vars:{case_id:'missing'}})).error);
});
test('rejects changed dataset',t=>{const f=fixture(t);fs.appendFileSync(f.config.datasetPath,' ');assert.throws(()=>new Replay({config:f.config}),/dataset/);});
test('rejects edited model answer',t=>{const f=fixture(t);f.report.rows[0].response.answer='24';f.write();assert.throws(()=>new Replay({config:f.config}),/[Mm]odified response/);});
test('rejects incomplete or duplicate coverage',t=>{const f=fixture(t);f.report.complete=false;f.write();assert.throws(()=>new Replay({config:f.config}),/incomplete/);f.report.complete=true;f.report.rows.push(f.report.rows[0]);f.write();assert.throws(()=>new Replay({config:f.config}),/exactly once/);});
test('recomputes checks rather than trusting edited assessments',t=>{const f=fixture(t);f.report.rows[0].assessment.checks.required_facts=false;f.write();assert.throws(()=>new Replay({config:f.config}),/recomputed/);});
test('recorded execution failure carries its original binding',async t=>{const f=fixture(t,'HTTP_500'),p=new Replay({config:f.config});const result=await p.callApi('What is the value?',{vars:{case_id:'a'}});assert.match(result.error,/HTTP_500/);assert.equal(result.metadata.record_sha256,f.report.rows[0].record_sha256);});
test('framework agreement validates each assertion, including failed quality cases',t=>{
 const f=fixture(t,null,'24'),output=exported(f.report);
 assert.deepEqual(verifyFramework(f.report,output),{cases:1,passed:0,failed:1,errors:0});
 output.results.results[0].gradingResult.componentResults[0].pass=false;
 assert.throws(()=>verifyFramework(f.report,output),/component disagrees/);
});
test('upstream error on an expected rule failure cannot masquerade as agreement',t=>{
 const f=fixture(t,null,'24'),output=exported(f.report);
 output.results.results[0].response.error='upstream crashed';
 assert.throws(()=>verifyFramework(f.report,output),/provider error/);
});
test('missing components or unexpected operational errors are rejected',t=>{
 const f=fixture(t),output=exported(f.report);
 output.results.stats.errors=1;assert.throws(()=>verifyFramework(f.report,output),/operational/);
 output.results.stats.errors=0;output.results.results[0].gradingResult.componentResults.pop();
 assert.throws(()=>verifyFramework(f.report,output),/component/);
});
test('framework rejects incomplete, duplicate, or unbound exports',t=>{
 const f=fixture(t),output=exported(f.report);
 assert.throws(()=>verifyFramework(f.report,{results:{results:[]}}),/coverage/);
 output.results.results[0].response.metadata.response_sha256='stale';assert.throws(()=>verifyFramework(f.report,output),/binding/);
 f.report.rows.push(f.report.rows[0]);output.results.results.push(output.results.results[0]);
 assert.throws(()=>verifyFramework(f.report,output),/binding|duplicate/);
});

test('framework counts execution errors separately from quality failures',t=>{
 const f=fixture(t,'HTTP_500'),output=exported(f.report);
 output.results.results[0].response.error='Recorded execution failure: HTTP_500';
 output.results.stats={successes:0,failures:0,errors:1};
 assert.deepEqual(verifyFramework(f.report,output),{cases:1,passed:0,failed:0,errors:1});
});
