// Reuse Promptfoo for local per-case HTML/JSON reports. No LLM judge is configured.
const fs = require('node:fs');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const Replay = require('./replay-provider.cjs');
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
const labels = {execution:'Execution', required_facts:'Fact pattern', evidence_retrieval:'Expected evidence',
  source_coverage:'Expected source', refusal:'Refusal pattern', no_forbidden_claim:'Forbidden pattern absent'};
const config = {
  description:'RAG synthetic development suite — automated RULE checks, not human-confirmed accuracy',
  prompts:['{{question}}'],
  providers:[{id:'file://'+path.join(__dirname,'replay-provider.cjs').replaceAll('\\','/'), config:providerConfig}],
  evaluateOptions:{maxConcurrency:1},
  tests:report.rows.map(row => ({description:row.id+' / '+row.category,
    vars:{case_id:row.id,question:row.question},
    assert:Object.entries(row.assessment.checks).filter(([,value])=>value!==null).map(([key])=>({
      type:'javascript',metric:labels[key],value:`const r=JSON.parse(output); return {pass:r.checks.${key} === true, score:r.checks.${key} === true ? 1 : 0, reason:'${labels[key]} is a bounded proxy; inspect the complete answer before confirming correctness'};`
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
const result=spawnSync(process.execPath,[cli,'eval','-c',configPath,'--no-cache',
  '-o',path.join(directory,'promptfoo.html'),'-o',path.join(directory,'promptfoo.json')],
  {cwd:directory,env,stdio:'inherit',windowsHide:true,timeout:120000});
if (result.error) throw result.error;
process.exit(result.status ?? 2);
