// Separate operational failures from answer-quality failures, even on a failed case.
const {isDeepStrictEqual}=require('node:util');
const labels={execution:'Execution', required_facts:'Fact pattern', evidence_retrieval:'Expected evidence',
  source_coverage:'Expected source', refusal:'Refusal pattern', no_forbidden_claim:'Forbidden pattern absent'};
module.exports = function verifyFramework(report, exported) {
  const rows=exported?.results?.results;
  if (!Array.isArray(rows) || rows.length!==report.rows.length) throw new Error('Framework result coverage mismatch');
  const expected=new Map(report.rows.map(row=>[row.id,row]));
  const seen=new Set();let errors=0;
  for (const row of rows) {
    const id=row.vars?.case_id ?? row.testCase?.vars?.case_id;
    if (!expected.has(id) || seen.has(id)) throw new Error('Framework contains duplicate or unknown cases');
    seen.add(id);
    const original=expected.get(id), response=row.response, metadata=response?.metadata;
    if (metadata?.response_sha256!==original.response_sha256 || metadata?.record_sha256!==original.record_sha256 ||
        metadata?.run_id!==report.run_id || metadata?.case_id!==id ||
        !isDeepStrictEqual(metadata.checks,original.assessment.checks)) throw new Error('Framework response binding mismatch for '+id);
    if (row.success!==original.assessment.rule_pass) throw new Error('Framework assertion disagrees with the recorded rule result for '+id);
    if (!original.assessment.checks.execution) {
      errors++;
      if (response.error!=='Recorded execution failure: '+original.assessment.error) throw new Error('Unexpected framework execution error');
      continue;
    }
    if (response.error || response.output!==original.response.answer) throw new Error('Framework provider error or modified answer for '+id);
    const checks=Object.entries(original.assessment.checks).filter(([,v])=>v!==null);
    const components=row.gradingResult?.componentResults;
    if (!Array.isArray(components) || components.length!==checks.length) throw new Error('Missing framework component results for '+id);
    const remaining=new Map(checks.map(([key,value])=>[labels[key],value]));
    for (const component of components) {
      const metric=component.assertion?.metric;
      if (!remaining.has(metric) || component.pass!==remaining.get(metric) || component.score!==Number(remaining.get(metric)) ||
          component.assertion.type!=='javascript') throw new Error('Framework component disagrees with reference checks for '+id);
      remaining.delete(metric);
    }
  }
  const passed=rows.filter(row=>row.success).length,failed=rows.length-passed-errors;
  const stats=exported.results.stats;
  if (stats?.errors!==errors || stats?.successes!==passed || stats?.failures!==failed) throw new Error('Framework operational/quality count mismatch');
  return {cases:rows.length,passed,failed,errors};
};
module.exports.labels=labels;
