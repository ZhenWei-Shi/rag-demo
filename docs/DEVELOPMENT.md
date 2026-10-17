# Development workflow and validation

Updated 2026-10-16. This portfolio project is developed with AI assistance. The
repository documents the implementation and checks rather than attributing all
work to a single unaided developer.

## Actual workflow for this update

1. The project owner selected the lightweight approach, requested a comprehensive
   self-check, and approved HTTPS setup and separation of private data from the
   public demonstration library.
2. Codex inspected the existing code, compared the local and deployed baselines,
   reproduced findings, implemented fixes, and handled integration and deployment.
3. Claude CLI reviewed backend behavior and Gemini CLI reviewed the frontend in
   the initial audit. Their suggestions were treated as hypotheses and checked
   against code and executable reproductions. They did not implement every fix.
4. An independent read-only patch review identified a long-answer/history-budget
   regression. Codex reproduced and repaired it, then repeated browser checks.
5. Before adding retrieval machinery, existing projects were evaluated. This
   update uses Rank-BM25 as a dependency and an implementation of rank fusion and
   MMR; it adds no second model or orchestration service.
6. Regression tests, a real-embedding retrieval comparison, synthetic live API
   checks, and real image-only PDF/OCR checks preceded publication. Source changes
   are published on a `codex/` branch with a pull request; private data and runtime
   secrets are excluded. Deployment backups are retained separately.

The optional local Tev1 router was observed in shadow mode during the initial
audit. It did not control the final implementation or establish a quality benefit.
Human direction and final engineering judgment remained necessary.

## Reproduce the local checks

Use a virtual environment and install `requirements.txt`, then `pytest` and
`httpx`. Run from the repository root:

```bash
python -m pytest -q --tb=short tests
python -m tools.evaluate_retrieval
python -m compileall -q app.py rag tests
git diff --check
```

The regression suite uses isolated data directories and mocked generation where
appropriate. Token-budget tests and the retrieval evaluation use the real
`all-MiniLM-L6-v2` tokenizer/model; the first run needs its Hugging Face download.
No production corpus or cloud LLM key is needed for these commands. The retrieval
evaluation runs in a child process so Chroma file handles close before temporary
data cleanup on Windows.

After the model has been downloaded, set `HF_HUB_OFFLINE=1` and
`TRANSFORMERS_OFFLINE=1` **before starting Python** to validate using its cache.
For constrained test hosts, also limit `OMP_NUM_THREADS`, `MKL_NUM_THREADS` and
`OPENBLAS_NUM_THREADS` (for example, to `2`). These settings affect this validation
process; do not silently change production service settings.

Before deployment, also syntax-check the inline frontend script with Node and
exercise both ordinary and streaming rendering in a browser. Test dependency
absence, dangerous Markdown/HTML, ordinary Markdown, filenames, failed replacement,
stream errors, clearing an active response, language switching, and long history.

## Results and limits of this update

- The same 65 regression tests passed locally on Python 3.12 and in an isolated
  test library on the deployed Python 3.10 server. Local warnings concern PyPDF2
  and Starlette/httpx; the server additionally reports an OpenTelemetry dependency
  deprecation. Compilation, frontend syntax and whitespace checks passed. The
  deployed runtime uses one Uvicorn worker.
- The checked-in retrieval evaluation contains **18 synthetic documents and 12
  disclosed development queries**. Target passage recall at six was 11/12 for
  dense search and 12/12 for BM25L + reciprocal rank fusion + MMR. This includes the
  previously failing long-tail fact with near-duplicate distractors. These cases
  influenced development: this is not a held-out benchmark, general accuracy
  estimate, or evidence of improved answer quality on arbitrary documents.
- Hybrid search scans the active text corpus for BM25 and reranks a bounded
  candidate pool using existing embeddings. It is intended for the small demo
  library, not a large corpus. MMR can trade relevance for diversity. English
  word/identifier and CJK unigram/bigram tokenization is deliberately simple;
  the embedding model is not a dedicated multilingual model.
- Browser checks preserved normal Markdown while blocking the reproduced unsafe
  rendering cases. These checks do not establish that every possible prompt
  injection or production attack is prevented. Citations expose retrieved sources;
  they do not verify every generated claim.
- Trusted HTTPS, HTTP redirection and a certificate renewal dry run passed.
  Temporary synthetic live uploads were removed after API/model/SSE checks.
- A real image-only synthetic PDF passed upload, OCR, embeddings, retrieval and
  cloud-LLM factual-answer/source checks in an isolated server data directory.
  The configured Aliyun OCR credential returned `InvalidAccessKeyId.Inactive`;
  **Tesseract performed the successful OCR**. A forced cloud failure also passed
  real Tesseract fallback. Cloud OCR itself is not verified as available.
- No Docker executable/engine was available in either test environment, so the
  image build was not executed. Docker remains an optional, unverified packaging
  route for this update. No CI run is claimed by these local results.

## Deployment and data handling

Run one worker per data directory. Back up the entire directory, including
`versions.sqlite3`, before changing indexes. For tokenizer-based reindexing,
prefer original source documents when available. The recovery helper
`python -m tools.reindex_existing` rebuilds from stored chunks; it cannot recover
text already lost before storage, and overlapping legacy chunks may duplicate text.
Stop the app and use the intended `RAG_DATA_DIR` when running maintenance.

The hosted library consists of the fictional samples in `docs/public-demo-*.md`.
Uploads and deletion are shared and unauthenticated. Use public material only.
The previous library is privately archived outside the website and is not part of
the source publication. Do not commit environment files, databases, cookies, keys,
backups or private source documents. Check the exact staged diff and file list
before committing; do not use a blanket add of runtime directories.

## Reused components and references

- [Rank-BM25](https://github.com/dorianbrown/rank_bm25), `0.2.2`, Apache-2.0,
  imported as a dependency; no upstream code copied into this repository.
- [DOMPurify](https://github.com/cure53/DOMPurify), `3.4.17`, vendored with the
  Apache-2.0 licensing option in `static/vendor/DOMPurify.LICENSE`.
- [MMR, Carbonell and Goldstein, SIGIR 1998](https://doi.org/10.1145/290941.291025),
  used as an algorithmic reference for relevance/diversity selection.


## Independent evaluation feature (2026-10-16)

The user selected an independent benchmark. Codex researched Ragas/Promptfoo,
created `codex/rag-accuracy-evaluation` before editing code, and implemented an
isolated real-API runner, frozen synthetic references, rule proxies, local
Promptfoo replay/reporting and human-review bindings. This feature depends on
the still-unmerged reliability PR and therefore uses that branch as its PR base;
retarget after the dependency merges. No merge or production deployment occurred.

Local verification: 105 Python tests, eleven Node contract tests, 34 real Ollama
answers and a Promptfoo export whose per-case verdicts agree with the scorer.
The initial baseline is 32/34 rule passes, with five model reading notes including
additional false positives. Human-confirmed accuracy remains unavailable until
human review is complete. This does not measure the hosted cloud model. Detailed
commands, scope and limitations: [evaluation/README.md](../evaluation/README.md).
After the user authorized CLI quota use, Claude reviewed scoring/runner integrity
(one timeout, successful retry) and Gemini reviewed report interpretation and
presentation. Codex checked their claims and added dataset-backed recomputation,
serialized-response/execution bindings, failed-run baseline protection and
per-assertion framework agreement. Findings that did not reproduce were not
implemented. All labels remain pending human review; model consultation is not
human approval. The Node dev tree has 10 high audit entries (three underlying
advisories), documented with scope and upstream limits in the evaluation README.
No clean-audit, CI, merge or deployment result is claimed.

## Answer-quality experiment and frozen evidence

Before changing runtime code, published the original synthetic dataset, raw answers,
owner's 28/34 human judgments, parameters and file digests. Windows Git newline
normalization was detected by checking actual Git blobs, corrected with exact-byte
attributes plus index refresh, and retained in the v1/v2/v3 tag audit trail. Use v3.
New transfer questions and original outputs were committed before prompt changes.
The original full suite remains disclosed development data; transfer checks became
exploratory after the failed first candidate was observed. No post-output reference
patterns were changed to increase scores. Full gains/regressions and comparability
limits are in evaluation/experiments/quality-v1. No human improvement, CI success,
merge or production deployment is claimed for these candidates. Claude CLI model
reading identified issues but did not fill human labels; its missing-context theory
for the refund error was rejected after checking the returned exact evidence.

## Offline human-review interface

A separate `codex/rag-review-page` branch follows the answer-quality experiment
branch. Codex implemented an offline Chinese card view and response-bound export;
Gemini reviewed the interface, with verified fixes and rejected false positives
recorded in evaluation/README.md. Headless Edge checks use an isolated temporary
browser profile; its QA selections are not actual human approvals. The combined
working tree passed 117 Python / 11 Node tests locally. This is local evidence,
not a CI result. Source and tests are committed; generated pages, downloads and
browser screenshots remain local ignored evidence.

## CI scope

The separate `codex/rag-ci` branch adds GitHub Actions regression jobs on pushes
and PRs. Official Actions were checked via the GitHub API and pinned to commits;
Python 3.12 uses CPU PyTorch and preloads the public embedding model before tests,
Node 24 runs replay contracts without lifecycle scripts. The jobs have read-only
repository permissions and do not run cloud/Ollama generation or deploy anything.
A green regression job does not clear the documented npm dependency audit warnings,
prove answer accuracy or constitute independent human approval. Report the actual
Actions outcome separately from the existing local 117/11 result.


## Imported owner review

The owner exported candidate-2 human judgments; all question/answer fields and
run/dataset/response/execution bindings were checked. One pending correctness
label was explicitly confirmed in chat. Original downloads and prior templates
remain local, read-only/archived; public files use a reviewer role rather than the
nickname. The 28/34 -> 32/34 same-owner development result, all gains/regressions
and comparability limits are preserved with a file manifest on a separate
codex/rag-human-results branch. Explicit review revisions also scope browser cache
keys, so regenerating a page from updated human labels cannot reload an older
cache. This does not silently replace unsaved edits from the same review revision.


## Responsibility cleanup (2026-10-17)

This independent branch starts from merged master `aae3135`; it does not merge or
deploy the pending container PR #7. Codex inventoried tracked files and references,
removed only the unreferenced early `rag_demo.py` implementation and unreachable
assistant-render branch, split HTTP schemas/routes from parsing/OCR, and separated
HTML/CSS/frontend ES modules. Supported offline maintenance commands now live in
`tools/`. See the current README tree for module ownership and command paths.

Claude CLI reviewed the proposed backend split and identified useful checks for
both imported embedding patch targets, lazy optional imports, router-before-static
mount order, 400/422/SSE contracts and future container copies. Codex implemented
the changes and adapted test patch targets to the true consuming modules. Claude
did not write the final source; Gemini and Tev1 were not invoked. No independent
human approval is claimed.

The initial 119 Python regressions passed after extraction. Two integration
contracts were added for the exact OpenAPI path/method set and the recursive
serving/MIME types of actual ES-module imports and CSS. The final suite and CI
results are recorded in the cleanup PR, separately from these earlier checks.
The browser fixture uses real routes/assets and in-memory Chroma with stubbed
embeddings/generation: it verifies language switching, streamed rendering,
sanitization, chunk toggles, deletion/reset, stream failure and an 8,001-character
answer followed by a usable follow-up with an omission notice. It is UI regression
validation, not a new model accuracy test. A stylesheet DOM accessor was unavailable
through the browser observation API; the styled screenshot and served-asset test
provide the actual layout/loading evidence instead.

Keep `rag/generator.py`, frozen JSON evidence and the data formats unchanged.
Legacy index reading/recovery code remains in use. Existing development advisories,
optional GCP peer inconsistency, inactive cloud key and network-path investigation
are not part of this refactor. Runtime configuration/private archives are untouched.

Container integration note: current master's `COPY . .` includes `api/`. Pending
PR #7 uses an explicit runtime whitelist and must also copy `api/` when combined
with this cleanup, then repeat its real container smoke test. Do not infer that
the old pre-cleanup green container check validates the combined tree. The cleanup
does not claim a local Docker build or production deployment.
