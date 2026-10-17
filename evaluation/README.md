# Independent RAG answer evaluation

> **Local Ollama evaluation only. Human review is pending; confirmed answer
> accuracy is unknown. Automatic rule passes are not human-approved answers and
> do not measure the hosted cloud model.**

This is an evaluation tool, separate from the public demo's request flow. It runs
the real `/upload` and `/ask` endpoints against a disposable local library and
uses the locally installed Ollama model. It never indexes into the existing local
or public libraries. No cloud LLM key or paid judge is required.

## Run it

From the repository root, in your Python environment:

```bash
pip install -r requirements.txt -r requirements-dev.txt
ollama pull llama3.2
python -c "from rag.embedder import warmup; warmup()"
python -m evaluation.run run
```

Ollama must already be running. The pull and embedding warmup are one-time network
preparation. Evaluation uses the embedding cache with Hub offline flags set
before Python starts. It forces local Ollama at `127.0.0.1:11434`, independent of
your production `LLM_PROVIDER` or `RAG_DATA_DIR`. Python 3.12 was tested locally.
This version does not run the hosted cloud-model configuration.

For a quick smoke check, preserve the full-suite baseline by using a separate file:

```bash
python -m evaluation.run run --limit 3 --output evaluation/results/smoke.json
```

Generate the per-case HTML and JSON report with the existing
[Promptfoo](https://github.com/promptfoo/promptfoo) runner (MIT, pinned `0.124.1`):

```bash
npm ci --ignore-scripts
npm run eval:report
```

The adapter also requires the same Python environment for independent dataset-backed
verification. Activate it before running Node, or set `RAG_EVAL_PYTHON` to that
interpreter's absolute path (PowerShell: `$env:RAG_EVAL_PYTHON='C:\path\python.exe'`).
The report never supplies an executable path.

Node `>=22.22.0` is required; Node 24.16.0 was tested. Open
`evaluation/results/promptfoo.html`. It shows questions, reference answers, model
answers, retrieved sources/passages, individual rule checks, pending human-review
status and any response-bound model reading notes. Promptfoo **replays saved
answers**; rendering the report does not generate new answers or call a judge.
The renderer verifies that every Promptfoo verdict agrees with its recorded rule
verdict. An assertion-parser failure cannot silently become a quality score.

Promptfoo returns **exit 100** when any rule assertions fail; the HTML/JSON reports
are still written. A failed quality gate is different from a crashed evaluator.
The wrapper disables common hosted features, telemetry, sharing and update checks,
uses a separate local config directory, and runs outside the repository root so
Promptfoo does not auto-load its `.env`. Only a local replay provider and ordinary
JavaScript assertions are configured. These settings are not a network firewall.

## What the metrics mean

The checked-in `dataset.json` has 14 **fictional** documents and 34 development
questions: English/Chinese facts, numbers, identifiers, negation, dates/versions,
boundaries, multi-document questions, unknown facts, chat follow-ups and a long-tail
fact with repetitive distractors. Each answerable fact has accepted patterns and
an exact quote in its named source; dataset validation checks those quotes before
any inference. Refusal cases do not invent a source answer.

- **Expected-evidence recall:** required gold quotes found in retrieved chunks
  from the correct files. This does not measure every retrieved chunk's relevance.
- **Fact-pattern match:** expected values/aliases appear in the answer. It does
  not understand every negation, extra claim, unit conversion or contradiction.
- **Source coverage:** expected filenames are returned. A source filename alone
  does not prove every generated claim is grounded.
- **Refusal rule checks:** expected absence expressions appear, without listed
  forbidden guesses. Unexpected paraphrases and unsupported additions may need
  human judgment.
- **Rule pass rate:** all applicable checks passed for a case. This is **not
  whole-answer accuracy or faithfulness**.
- **Human-confirmed suite accuracy / groundedness:** reported only after every
  case in a complete run has a decisive, response-bound human label. Pending,
  unsure or partial reviews leave these values `null`. Partial-review coverage and
  accuracy among decisive reviews are shown separately to expose selection bias.

The dataset was created during development, is disclosed, and is not representative
of production traffic or a blinded holdout. Do not tune the system to these answers
and then describe its score as general accuracy. Add independently labelled,
representative real documents before making deployment-quality claims.

## Human review

Each generation run writes `latest.json` and `latest.review.json`. In the review
template, inspect the **entire answer** against the actual source documents,
including extra claims, dates, units, contradictions and appropriate abstention.
Set `correctness` and `groundedness` to `pass`, `fail` or `unsure`, identify the
human `reviewer`, and record reasons. Keep `pending` where no review occurred.
Do not turn an AI model's reading notes into claimed human approvals.

```bash
python -m evaluation.run score --report evaluation/results/latest.json --review evaluation/results/latest.review.json --output evaluation/results/reviewed-summary.json
```

Labels bind to the run ID, dataset SHA256, case ID and response SHA256. They cannot
be carried forward to a new response/run without explicit re-review. Missing or
duplicate labels, modified responses and stale bindings are rejected. Execution
failures cannot be manually approved as correct answers. Code/scorer bugs require
a documented correction; do not edit a frozen model answer to improve its score.

## First real local baseline (2026-10-16)

The first complete run used `llama3.2:latest`, model digest
`a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72`,
temperature 0, seed 101, at most 512 generated tokens. Dataset SHA256:
`b5d3b3c2b1d07b8102c972bf39a1d4cf00080058e7b9692fc2eeca48b61facc0`.
Original generation/scoring source commit: `e862492` (clean working tree). Renderer-only
compatibility fixes followed; the dataset and answers were not regenerated or
edited to raise their scores.

- 34/34 requests completed; 32/34 automatic rule passes. Human-review coverage is 0%; confirmed accuracy is unknown.
- All 32 required fact quotes were retrieved; 30/32 expected answer-fact patterns
  matched. All six unknown-fact questions passed the refusal rules.
- Two rule failures: the April shipping-price question wrongly abstained despite
  retrieved evidence; the multi-document booking/refund question omitted the
  refund notice period.
- Codex's subsequent **model self-review** flagged three additional rule-pass
  answers: opening hours accompanied by wrong opening-day wording; a membership
  answer containing the right price while denying the source supplied it; and a
  code answer with a contradictory introductory refusal. These are reading notes
  for human review, not independent approvals or automatic human labels.
- Human review is pending. **32/34 rule passes are not a confirmed answer accuracy, and none of
  these results describe the hosted cloud model's performance.**

No retrieval or answer-generation behavior was changed in this feature to improve
the baseline. The purpose is to make such failures visible and reproducible.

## Reproducibility and data handling

Raw answers, chunks, individual checks, provider/model digest, generation options,
dataset fingerprint, Git commit and dirty-tree flag are saved. Different runtimes
or repeated generations may still vary despite the seed. The first baseline used
a clean source tree; renderer/reporting changes do not change its original answers.

Each run owns a temporary database. A parent process cleans it only after the
worker releases native Chroma handles, including on Windows. The worker has a
wall-clock limit, each local model request has a timeout and a token cap, and
checkpoints are written to `<output-stem>.partial.json` instead of overwriting a
previous baseline. A completed attempt with HTTP/model execution errors exits 2
and keeps its checkpoint; it does not promote a new baseline or review template.
`complete` means every question was attempted; `all_executed` separately records
whether every response executed successfully. A healthy run with rule failures
still produces a baseline for review. Partial or changed-dataset reports
are rejected by the full-suite HTML renderer.

`evaluation/results/`, model output/review files, Promptfoo config/log databases
and `node_modules/` are ignored by Git. Evaluation code, Node tooling and outputs
are excluded from Docker build contexts; no evaluation endpoint or unauthenticated
server-side benchmark was added. New private datasets require explicit local
handling and must never be committed to the public repository.

## Tests and tool selection

```bash
python -m pytest -q --tb=short tests
npm run test:eval-adapter
```

105 Python tests and eleven Node adapter/integration-contract tests passed locally.
The real Promptfoo export was additionally checked against all 34 recorded rule
verdicts. Initial standard-answer validation found a missing refusal paraphrase;
this was corrected before freezing the dataset. A single-line JavaScript assertion
format initially failed in Promptfoo 0.124.1; using its documented multiline
function-body format fixed reporting. Neither issue was counted as a RAG failure.

[Ragas](https://github.com/vibrantlabsai/ragas) (Apache-2.0) was also evaluated as
a candidate. Its [factual-correctness metric](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/factual_correctness/)
uses model-based claim evaluation. This first version uses Promptfoo's existing
[custom-provider](https://www.promptfoo.dev/docs/providers/custom-api/) and
[assertion](https://www.promptfoo.dev/docs/configuration/expected-outputs/) support
for a local replay report, keeping model-judge cost and scorer uncertainty out of
the reported deterministic checks. Promptfoo is a development dependency only;
its broader dependency tree is not installed on the 2GB production server.

Development followed GitHub Flow: a separate branch was created before changes,
based on the unmerged reliability PR because the benchmark depends on that runtime.
Its PR targets the reliability branch until PR #1 is merged, then should be retargeted
to `master`. Codex implemented, integrated and verified the feature. After the user authorized
using their CLI quotas, Claude (reported model `claude-opus-5-5`) reviewed scoring,
record integrity and runner failure handling; its first 120-second attempt timed
out and a 240-second retry succeeded. Gemini reviewed report interpretation and
presentation (the CLI did not report a model ID). Accepted findings led to
reference-backed score recomputation, exact serialized-response hashing,
execution-bound reviews, preserved baselines, observed local generation and
per-assertion framework checks. Gemini's proposed "0% human-verified accuracy"
wording was rejected: review coverage is 0%, while accuracy is unknown. Claude's
filename-to-filesystem escape concern did not reproduce: the API stores filenames
as database metadata. These are model reviews, not human approval or CI. Tev1
routing was not used for these consultations. No merge or production deployment
occurred.


## Report integrity and schema migration

Schema 2 verifies the raw dataset fingerprint, ordered case coverage, case metadata,
exact serialized response bytes and an error/generation record binding. Every
stored rule assessment is recomputed from the actual reference dataset before
scoring or rendering. The Python verifier and Node adapter preserve the original
UTF-8 JSON string, so Unicode and numbers such as `1.0`/`1e-5` do not depend on
cross-language serialization conventions. NaN and Infinity are rejected.
Human labels additionally bind to the execution record. These are consistency
checks for local files, not cryptographic proof of who generated or reviewed them;
a person able to replace all inputs can create another consistent record.

The first baseline's schema-1 file was preserved separately, then migrated without
new inference, answer edits, dataset changes or verdict changes. Its generation
commit remains `e862492`; later verifier/renderer changes are separate provenance.
Legacy model observations are retained rather than invented retroactively.

```bash
python -m evaluation.run verify --report evaluation/results/latest.json
python -m evaluation.run migrate --report evaluation/results/baseline-v1.json --output evaluation/results/migrated.json
```

Migration requires a different output path and identical dataset, original response
hashes and unchanged verdicts. Existing human labels require deliberate re-review
under the new execution binding; migration does not approve them automatically.

## Development dependency audit (2026-10-16)

`npm audit` reports **10 high-severity dependency entries, zero critical** for the
pinned Promptfoo development tree. These include three underlying advisories;
the remaining entries are parent dependency propagation, not ten demonstrated
exploits in this evaluator:

- [basic-ftp directory-listing CPU denial of service](https://github.com/advisories/GHSA-c475-qrg2-pj4r),
  patched in 6.2.1; `get-uri@8.0.1` currently requests `basic-ftp@^5.3.1`, so this
  requires a major-version dependency change rather than a routine compatible bump.
- [braces nested-pattern stack exhaustion](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm),
  with no patched version listed at review time.
- [node-forge RSA signature verification](https://github.com/advisories/GHSA-86w9-cpqp-85rv),
  with no patched version listed at review time.

The configured replay does not intentionally use FTP, JKS certificate verification
or filesystem watch mode. Exploit reachability has not been exhaustively verified.
Do not expose the Promptfoo server or execute untrusted providers/configuration.
The Node tree is development-only and excluded from production Docker contexts;
this feature did not install it on the server. The audit's proposed downgrade to
Promptfoo 0.116.7 was not applied blindly. Resolving these upstream dependencies
remains open; this project does not claim a clean dependency audit.

A second focused Claude review was checked against the actual CLI and source.
Accepted refinements archive prior baselines/human labels before replacement,
keep same-run labels, block partial overwrites of a full custom baseline, separate
framework quality failures/errors, preserve earlier generation truncation signals
and record unencodable outputs as individual errors. The CLI already blocks
`--limit` overwriting the default full baseline; the original broad overwrite
claim omitted that guard. The current app always invokes the LLM for this
nonempty corpus; a hypothetical future shortcut would require an explicit
contract update rather than silently claiming model inference occurred.

A real fault-injection replay distinguished 31 rule passes, 2 quality failures and
1 recorded HTTP error. A real one-second parent timeout exited nonzero and left
no disposable database behind. The final runner was also exercised on three
real local questions; this smoke result is partial and cannot be a full-suite
accuracy estimate. Starting the smoke initially found Ollama stopped; its existing
local service was restarted, without pulling or changing the model.

## Chinese offline human review

Use the new card layout instead of searching through the wide Promptfoo table:

```bash
python -m evaluation.review_page --report evaluation/results/latest.json --review evaluation/results/latest.review.json --output evaluation/results/baseline-review.html
python -m evaluation.review_page --report evaluation/experiments/quality-v1/candidate-2-original.json --baseline evaluation/baselines/2026-10-16-local-v1/report.json --baseline-review evaluation/baselines/2026-10-16-local-v1/review.json --output evaluation/results/comparison-review.html
```

Open the generated HTML locally. Each card clearly labels the question, original
model answer, reference, expected evidence and actual retrieved/full documents.
English questions have Chinese reading aids with the original question alongside.
Comparisons show baseline human judgments beside the new, initially unreviewed
answer. Correctness and evidence support are separate selectors. Browser storage
is keyed to run/dataset/response/execution bindings; the old baseline's judgments
are never copied to a new run. Input is rendered as text, not executable HTML.

Selections/notes stay in this browser until you export the review JSON. Export
requires a reviewer for completed labels. Give the exported file to the project
maintainer and use the existing `score --review PATH` command to verify/aggregate;
the page does not silently overwrite repository files. Regenerating a page reads
the explicitly supplied review file. Avoid using shared browser profiles for
private datasets; all shipped examples here are fictional/public.

Validation: combined branch 117 Python tests and 11 Node tests passed locally.
An isolated headless Edge profile exercised navigation, search/filter, empty
results, immediate note persistence without blur, export bindings, failed-answer
pass prohibition and reset on the next valid answer, and 390px/1200px layouts.
QA labels were never written back to real human reviews. Gemini CLI review led
to immediate note saving and avoiding reviewer reassignment on unchanged export.
Its case-order, incoming-label-binding and permanently-disabled-option claims did
not reproduce: Python enforces case order and response bindings, and JS resets
the disabled flag per row. Claude's answer reading is model commentary, not a
human label. No production deployment or merged PR is claimed.
