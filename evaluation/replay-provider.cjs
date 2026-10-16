// Promptfoo custom provider: replay immutable local outputs, never call a model.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const hash = value => crypto.createHash('sha256').update(value).digest('hex');
function canonical(value) {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value && typeof value === 'object') return '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + canonical(value[k])).join(',') + '}';
  return JSON.stringify(value);
}
module.exports = class ReplayProvider {
  constructor(options) {
    const config = options.config || {};
    this.dataset = JSON.parse(fs.readFileSync(config.datasetPath));
    this.report = JSON.parse(fs.readFileSync(config.reportPath));
    const report = this.report;
    if (report.schema_version !== 1 || !report.run_id || !report.complete ||
        report.dataset_sha256 !== hash(fs.readFileSync(config.datasetPath))) {
      throw new Error('Report is incomplete, invalid, or belongs to a changed dataset');
    }
    const ids = this.dataset.cases.map(c => c.id).sort();
    const rows = report.rows.map(r => r.id).sort();
    if (new Set(rows).size !== rows.length || report.suite_cases !== ids.length || JSON.stringify(ids) !== JSON.stringify(rows)) {
      throw new Error('Report must cover every dataset case exactly once');
    }
    this.rows = new Map(report.rows.map(row => {
      if (hash(canonical(row.response)) !== row.response_sha256) throw new Error('Modified response: ' + row.id);
      return [row.id, row];
    }));
  }
  id() { return 'local-rag-answer-replay'; }
  async callApi(prompt, context) {
    const row = this.rows.get(context?.vars?.case_id);
    if (!row || prompt.trim() !== row.question) return {error:'Unknown case or question/report mismatch'};
    if (!row.assessment.checks.execution) return {error:'Recorded execution failure: ' + row.assessment.error};
    return {output:JSON.stringify({...row.response, checks:row.assessment.checks, rule_pass:row.assessment.rule_pass}),
      metadata:{run_id:this.report.run_id, case_id:row.id, response_sha256:row.response_sha256}};
  }
};
module.exports.canonical = canonical;
