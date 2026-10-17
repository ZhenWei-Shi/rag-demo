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
