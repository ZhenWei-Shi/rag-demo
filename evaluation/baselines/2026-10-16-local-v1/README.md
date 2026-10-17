# Frozen pre-improvement baseline

Published before answer-quality changes at the project owner's explicit request.
All documents and questions are fictional, public synthetic material. The original
answers and owner's response-bound human judgments are preserved without edits.
`manifest.json` contains SHA-256 fingerprints, model digest and generation parameters.
The Git commit/tag records publication; hashes alone are not a trusted timestamp.

- Human correctness: **28/34 (82.35%)**, including wording accuracy.
- Automatic rules: 32/34; these missed contradictions and must not replace human review.
- Human groundedness: not assessed. Not hosted-model or general business accuracy.
- Generated from clean source `e862492`; schema migration/verification at `a505953`.
- Not a blinded test: the author and system developer saw these failures before optimization.

Recheck from the repository root:

```bash
python -m evaluation.run score --dataset evaluation/baselines/2026-10-16-local-v1/dataset.json --report evaluation/baselines/2026-10-16-local-v1/report.json --review evaluation/baselines/2026-10-16-local-v1/review.json
```

For a resume, accurately describe establishing a reproducible bilingual RAG benchmark,
tracking retrieval versus answer quality, and identifying errors through human review.
No improvement claim is supported yet. Later comparisons must preserve model/dataset
conditions, show regressions as well as gains, and label model grading separately.

Publication correction: the first v1 Git tag normalized Windows newlines and therefore did not preserve the manifest byte hashes. Use tag rag-baseline-2026-10-16-v3, which preserves exact JSON bytes via .gitattributes and an explicitly refreshed Git index. The v1/v2 tags are retained for an honest audit trail; answers and verdicts did not change.
