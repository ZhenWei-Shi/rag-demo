# Answer language regression

Recorded 2026-10-27. This experiment checks response language separately from
factual correctness on fictional development documents. It is a frozen-context
generation replay, not a production accuracy or end-to-end retrieval benchmark.

The baseline prompt sometimes copied Chinese wording into English answers:
`lab-capacity` and `library-renewal` were in Chinese; `cross-fees` used the Chinese
unit word `积分`. The revised prompt gives an explicit requested reply language
priority, otherwise follows the current question, and translates ordinary unit
words without changing quantities or converting units/currencies. Source names,
proper names and technical identifiers remain intact. Missing information is
reported in the selected language without a fixed bilingual refusal template.

## Observed results

- Original 34 synthetic questions: language compliance **31/34 → 34/34**
  (91.18% → 100%, +8.82 percentage points); factual correctness **34/34 → 34/34**.
- Six newly frozen language checks: **6/6** factual and language passes. They cover
  Chinese source text, multi-part questions, prior-turn language, explicit output
  language overriding the question language, and a missing-information refusal.
- The generation compatibility tests passed **5/5**, covering the existing Ollama
  routes plus OpenAI-compatible normal/streamed messages, history limits, context
  ordering, unchanged inputs and empty streaming deltas. Stubbed transport tests
  do not establish LLM language quality.

Both runs requested the existing `deepseek-chat` configuration and received
`deepseek-flash`. Each question had one generation with temperature 0, thinking
disabled and max_tokens 512. The fixed run used 40 requests and no retries.
The original 34 contexts are exactly those in
`../quality-v1/candidate-2-original.json`. The new cases use full source excerpts
from the existing fictional documents. They were frozen before the fixed run;
they are additional development checks, not a representative blind holdout.

`results.json` preserves all baseline and fixed answer text, UTF-8 answer hashes,
per-question labels, generation settings and the six additional cases. Existing
datasets, frozen model answers and owner-reviewed labels were not overwritten.
The source documents and original questions are in `../../dataset.json`; the
SHA256 of its bytes must match `original_dataset_sha256` in the result record.

## Review and limits

Claude drafted the minimal prompt change and compatibility tests. Codex integrated
them, removed an unnecessary arithmetic restriction, ran the isolated evaluation,
and checked every raw answer. Gemini independently reviewed the supplied code and
40 answers, finding no blockers and passing all factual, grounding and language
checks. Gemini did not supply a confirmable model ID. These are AI judgments,
not new human review. Standard codes such as USD and mm are allowed in either
response language; ordinary Chinese unit words in English prose are not.

This is a small, exposed synthetic set with one sample per question. The baseline
was an earlier run, not a contemporaneous randomized comparison. A matching
hosted model name does not pin weights, and temperature 0 does not guarantee
repeatability. No claim is made about all queries, other languages, live retrieval,
OCR, production streaming or production deployment. CI status belongs to the
pull request and is not inferred from these recorded local results.
