// Promptfoo custom provider: replay immutable local outputs, never call a model.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const hash = value => crypto.createHash('sha256').update(value).digest('hex');
const {spawnSync} = require('node:child_process');
const {isDeepStrictEqual} = require('node:util');
module.exports = class ReplayProvider {
  constructor(options) {
    const config = options.config || {};
    this.dataset = JSON.parse(fs.readFileSync(config.datasetPath));
    this.report = JSON.parse(fs.readFileSync(config.reportPath));
    const report = this.report;
    if (report.schema_version !== 2 || !report.run_id || !report.complete ||
        report.dataset_sha256 !== hash(fs.readFileSync(config.datasetPath))) {
      throw new Error('Report is incomplete, invalid, or belongs to a changed dataset');
    }
    const ids = this.dataset.cases.map(c => c.id).sort();
    const rows = report.rows.map(r => r.id).sort();
    if (new Set(rows).size !== rows.length || report.suite_cases !== ids.length || JSON.stringify(ids) !== JSON.stringify(rows)) {
      throw new Error('Report must cover every dataset case exactly once');
    }
    // A caller-selected interpreter, never a path supplied by the report.
    const verified=spawnSync(process.env.RAG_EVAL_PYTHON || 'python',
      ['-m','evaluation.run','verify','--dataset',path.resolve(config.datasetPath),'--report',path.resolve(config.reportPath)],
      {cwd:path.resolve(__dirname,'..'),encoding:'utf8',timeout:15000,windowsHide:true});
    if (verified.error || verified.status!==0) throw new Error('Dataset-backed verification failed: '+(verified.error?.message || verified.stderr));
    this.rows = new Map(report.rows.map(row => {
      if (typeof row.response_json!=='string' || hash(row.response_json)!==row.response_sha256 || !isDeepStrictEqual(JSON.parse(row.response_json),row.response)) throw new Error('Modified response: '+row.id);
      return [row.id, row];
    }));
  }
  id() { return 'LOCAL-OLLAMA-REPLAY:'+this.report.model; }
  async callApi(prompt, context) {
    const row = this.rows.get(context?.vars?.case_id);
    if (!row || prompt.trim() !== row.question.trim()) return {error:'Unknown case or question/report mismatch'};
    const metadata={run_id:this.report.run_id, case_id:row.id, response_sha256:row.response_sha256,
        checks:row.assessment.checks, rule_pass:row.assessment.rule_pass,
        sources:row.response?.sources, retrieved_chunks:row.response?.chunks, record_sha256:row.record_sha256};
    if (!row.assessment.checks.execution) return {error:'Recorded execution failure: '+row.assessment.error,metadata};
    return {output:row.response.answer,metadata};
  }
};
