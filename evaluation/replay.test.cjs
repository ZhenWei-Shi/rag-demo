const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const crypto=require('node:crypto');
const Replay=require('./replay-provider.cjs');
function fixture(t) {
 const directory=fs.mkdtempSync(path.join(os.tmpdir(),'rag-replay-test-'));
 t.after(()=>fs.rmSync(directory,{recursive:true,force:true}));
 const datasetPath=path.join(directory,'dataset.json'), reportPath=path.join(directory,'report.json');
 fs.writeFileSync(datasetPath,JSON.stringify({cases:[{id:'a'}]}));
 const response={answer:'值为23',sources:['memo.txt'],chunks:[{source:'memo.txt',text:'值为23'}]};
 const row={id:'a',question:'What is the value?',response,
  response_sha256:crypto.createHash('sha256').update(Replay.canonical(response)).digest('hex'),
  assessment:{checks:{execution:true},rule_pass:true,error:null}};
 const report={schema_version:1,run_id:'run',complete:true,suite_cases:1,
  dataset_sha256:crypto.createHash('sha256').update(fs.readFileSync(datasetPath)).digest('hex'),rows:[row]};
 const write=()=>fs.writeFileSync(reportPath,JSON.stringify(report));write();
 return {config:{datasetPath,reportPath},report,write};
}
test('replays Unicode response only for matching case and question',async t=>{
 const f=fixture(t),p=new Replay({config:f.config});
 assert.equal(JSON.parse((await p.callApi('What is the value?',{vars:{case_id:'a'}})).output).answer,'值为23');
 assert.ok((await p.callApi('wrong question',{vars:{case_id:'a'}})).error);
 assert.ok((await p.callApi('What is the value?',{vars:{case_id:'missing'}})).error);
});
test('rejects changed dataset',t=>{const f=fixture(t);fs.appendFileSync(f.config.datasetPath,' ');assert.throws(()=>new Replay({config:f.config}),/dataset/);});
test('rejects edited model answer',t=>{const f=fixture(t);f.report.rows[0].response.answer='24';f.write();assert.throws(()=>new Replay({config:f.config}),/Modified response/);});
test('rejects incomplete or duplicated case reports',t=>{const f=fixture(t);f.report.complete=false;f.write();assert.throws(()=>new Replay({config:f.config}),/incomplete/);f.report.complete=true;f.report.rows.push(f.report.rows[0]);f.write();assert.throws(()=>new Replay({config:f.config}),/exactly once/);});
test('execution failures remain provider errors',async t=>{const f=fixture(t);f.report.rows[0].assessment={checks:{execution:false},error:'HTTP_500'};f.write();const p=new Replay({config:f.config});assert.match((await p.callApi('What is the value?',{vars:{case_id:'a'}})).error,/HTTP_500/);});
