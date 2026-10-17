# Pre-registered answer-quality experiment

The 34-case original baseline is frozen under tag `rag-baseline-2026-10-16-v3`.
The 12 new synthetic transfer cases were committed/pushed in `dbcbff0` before any
answer prompt changes, and their original outputs were captured from that clean
commit with the original RAG runtime (9/12 automatic passes; human unreviewed).
They are same-author transfer checks, not an independently blinded holdout.

Protocol: one initial candidate, same model digest/temperature/seed/token cap,
same datasets and retrieval code; preserve every answer including regressions.
Do not edit reference patterns based on generated answers. Report automatic and
human scores separately. After seeing transfer results, further tuning makes
these cases development data. No resume claim of human accuracy improvement is
valid until comparable human judgments have been obtained for new answers.


## Complete experiment record

Candidate 1 (`6401829`) used long, explicit instructions: original rules 29/34,
transfer rules 8/12, both worse than baseline. Outputs are retained, not discarded.
Candidate 2 (`1c303d2`) is an exploratory shorter prompt, tested after observing
candidate 1: original rules 33/34, transfer rules 11/12. The original protocol's
single-candidate transfer check is therefore exhausted; later transfer results are
exploratory development checks, not a fresh blinded holdout. Canonical abstention
wording also affects regex matches; proxy gains alone do not prove semantic gains.

All runs used identical model digest and options (temperature 0, seed 101, cap512).
Original dataset bytes and reference rules did not change. Context comparison found
33/34 original cases had identical retrieved passages/sources; the stress case's
retrieval differed when rebuilding the temporary index. Every automatic-rule gain
and regression occurred among matched contexts; do not attribute the stress-case
answer improvement exclusively to the prompt. All 12 transfer contexts matched.
See the generated comparison JSON for per-case evidence, gains and regressions.

Candidate 2 original rule gains: shipping-april and cross-booking; regression:
museum-refund (wrong refusal despite the 48-hour sentence in retrieved context).
Transfer gains: last-entry, two-fees, closed-day; regression: old-price.
The rule-passing museum-opening answer still contradicts itself about weekdays.
Claude CLI model reading (not human approval) independently flagged the refund and
opening-day failures plus minor language/wording issues. Its suggestion that refund
failure may be due to missing/truncated context was checked and rejected: the exact
48-hour evidence is present. No observed-failure regexes were added to raise scores.

The original owner-reviewed human accuracy remains **28/34 (82.35%)**. New human
accuracy and human accuracy delta remain **unknown** until the owner reviews new
answers. This branch is an experiment for review, not a production-ready accuracy
claim. Nothing was merged or deployed. A defensible resume statement today is:
"Built a reproducible bilingual RAG evaluation pipeline with immutable baseline
artifacts, response-bound human review, paired experiments and regression tracking."
Do not write "human accuracy improved from 82.35% to 97.06%": those are different
metrics. After independent human review, cite the actual numerator/denominator and
synthetic-development scope.

Research: considered existing RAG patterns from
[LangChain rag-from-scratch](https://github.com/langchain-ai/rag-from-scratch) and
[Meta Llama cookbook](https://github.com/meta-llama/llama-cookbook).
No upstream code copied and no new agent framework/model installed. The current
failure is evidence use at generation, so a small shared prompt change is tested
before adding retrieval or multi-call model complexity. These sources do not prove
that the prompt is effective; the saved local runs are the evidence.
