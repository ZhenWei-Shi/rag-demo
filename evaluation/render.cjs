// Reuse Promptfoo for local per-case HTML/JSON reports. No LLM judge is configured.
const fs = require('node:fs');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const Replay = require('./replay-provider.cjs');
const verifyFramework = require('./framework-check.cjs');
const root = path.resolve(__dirname, '..');
const options = {report:path.join(__dirname,'results/latest.json'),dataset:path.join(__dirname,'dataset.json')};
for (let i=2; i<process.argv.length; i+=2) {
  const key = process.argv[i].slice(2);
  if (!process.argv[i].startsWith('--') || !Object.hasOwn(options,key) || !process.argv[i+1]) throw new Error('Use --report PATH and/or --dataset PATH');
  options[key] = path.resolve(process.argv[i+1]);
}
const providerConfig = {reportPath:options.report, datasetPath:options.dataset};
const replay = new Replay({config:providerConfig});
const report = replay.report;
const directory = path.dirname(options.report);
const configPath = path.join(directory,'promptfooconfig.json');
const triagePath=path.join(directory,path.basename(options.report,'.json')+'.triage.json');
const triage=new Map();
if (fs.existsSync(triagePath)) {
  const notes=JSON.parse(fs.readFileSync(triagePath));
  if (notes.run_id!==report.run_id || notes.dataset_sha256!==report.dataset_sha256 || notes.reviewer_kind!=='model') throw new Error('Triage is stale or not clearly labelled as model commentary');
  for (const item of notes.rows) {
    if (triage.has(item.id) || replay.rows.get(item.id)?.response_sha256!==item.response_sha256) throw new Error('Triage response binding mismatch');
    triage.set(item.id,item.note);
  }
}
const {labels}=verifyFramework;
const config = {
  description:'LOCAL OLLAMA '+report.model+' — RULE CHECKS ONLY; HUMAN REVIEW PENDING; VERIFIED ACCURACY UNKNOWN; NOT PRODUCTION CLOUD METRICS',
  prompts:['{{question}}'],
  providers:[{id:'file://'+path.join(__dirname,'replay-provider.cjs').replaceAll('\\','/'), config:providerConfig}],
  evaluateOptions:{maxConcurrency:1},
  tests:report.rows.map(row => ({description:row.id+' / '+row.category,
    vars:{case_id:row.id,question:row.question,reference_answer:row.reference_answer,
      human_review:'UNREVIEWED — human accuracy unknown',
      retrieved_sources:(row.response.sources||[]).join(', '),
      expected_evidence:replay.dataset.cases.find(c=>c.id===row.id).facts.map(f=>'['+f.source+'] '+f.quote).join('\n'),
      model_triage:triage.has(row.id)?'AI MODEL NOTE (not human approval): '+triage.get(row.id):''},
    assert:Object.entries(row.assessment.checks).filter(([,value])=>value!==null).map(([key])=>({
      type:'javascript',metric:labels[key],value:`const r=context.providerResponse.metadata;
return {pass:r.checks.${key} === true, score:r.checks.${key} === true ? 1 : 0, reason:'${labels[key]} is a bounded proxy; inspect the complete answer before confirming correctness'};`
    }))}))
};
fs.writeFileSync(configPath,JSON.stringify(config,null,2)+'\n');
const pkg=JSON.parse(fs.readFileSync(path.join(root,'node_modules/promptfoo/package.json')));
const bin=typeof pkg.bin==='string'?pkg.bin:pkg.bin.promptfoo;
const cli=path.resolve(root,'node_modules/promptfoo',bin);
const env={...process.env,
  PROMPTFOO_DISABLE_TELEMETRY:'1',PROMPTFOO_DISABLE_UPDATE:'1',PROMPTFOO_DISABLE_REMOTE_GENERATION:'true',
  PROMPTFOO_DISABLE_SHARING:'1',PROMPTFOO_SELF_HOSTED:'1',
  PROMPTFOO_CONFIG_DIR:path.join(directory,'.promptfoo'),PROMPTFOO_LOG_DIR:path.join(directory,'.promptfoo/logs')};
for (const key of Object.keys(env)) if (/(?:API_KEY|ACCESS_KEY|SECRET|TOKEN|^OPENAI_|^ANTHROPIC_|^LLM_)/i.test(key)) delete env[key];
// Run outside the repository root so Promptfoo does not auto-load a production .env.
for (const name of ['promptfoo.html','promptfoo.json']) fs.rmSync(path.join(directory,name),{force:true});
const result=spawnSync(process.execPath,[cli,'eval','-c',configPath,'--no-cache',
  '-o',path.join(directory,'promptfoo.html'),'-o',path.join(directory,'promptfoo.json')],
  {cwd:directory,env,stdio:'inherit',windowsHide:true,timeout:120000});
if (result.error) throw result.error;
const verified=verifyFramework(report,JSON.parse(fs.readFileSync(path.join(directory,'promptfoo.json'))));
console.log('Framework/scorer agreement: '+JSON.stringify(verified));
process.exit(result.status ?? 2);
