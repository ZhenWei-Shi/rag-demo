"""Synthetic retrieval check, real embeddings, isolated DB; no LLM/API keys.

Run from repository root: python tests/evaluate_retrieval.py
These disclosed development cases are NOT a held-out accuracy benchmark.
"""
import json
import os
import sys
import tempfile
from pathlib import Path
import subprocess

if __name__ == '__main__' and '--worker' not in sys.argv:
    with tempfile.TemporaryDirectory(prefix='rag-retrieval-eval-') as isolated:
        subprocess.run([sys.executable, __file__, '--worker', isolated], check=True)
    sys.exit(0)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rag.embedder import embed, chunk_document
from rag import store

docs = {
    'long_target.txt': 'General checklist. ' + 'ok ' * 280 + 'The NOVA docking override code is GARNET-928.',
    'loan.txt': 'The Helios public library allows members to borrow books for 21 days. Annual membership costs 17 dollars.',
    'lab.md': '青杉实验室每周三下午两点开放。预约必须提前三天。每次最多十二人。演示代号是蓝鹭。',
    'parts.txt': 'Replacement part XR-71B requires a 13 millimeter socket. Part XR-71C needs a 19 millimeter socket.',
    'refund.txt': 'The Lumen shop accepts unopened product returns within 28 days. Refunds go to the original payment method.',
    'travel.txt': 'Orion staff must keep original receipts when claiming reimbursement for rail travel.',
    'backup.txt': 'For Aster deployments, archive the database every six hours. Keep the most recent fourteen copies.',
    'office.md': '赤松办公室每周五十六点关闭，紧急联系人为值班经理。节假日不开放。',
    'conflict_a.txt': 'Dated March 1: the Vega training fee is 40 credits. This memo does not supersede later notices.',
    'conflict_b.txt': 'Dated April 1: the Vega training fee is now 45 credits, superseding the March memo.',
}
for i in range(8):
    docs[f'distractor_{i}.txt'] = (f'NOVA docking override code bulletin {i}. The docking override code is not listed in this bulletin. '
        'Consult the general checklist for the actual authorization code. This bulletin only covers docking equipment maintenance.')
cases = [
    ('long-density-duplicates', 'What is the NOVA docking override code?', 'long_target.txt', 'GARNET-928'),
    ('english-fact', 'How long may Helios members keep borrowed books?', 'loan.txt', '21'),
    ('english-paraphrase', 'What is the annual cost to join Helios library?', 'loan.txt', '17'),
    ('chinese-booking', '青杉实验室要提前几天预约？', 'lab.md', '三天'),
    ('chinese-code', '青杉实验室的演示代号是什么？', 'lab.md', '蓝鹭'),
    ('identifier', 'Which socket does XR-71B need?', 'parts.txt', '13'),
    ('refund-paraphrase', 'How soon must I send back an unopened Lumen purchase?', 'refund.txt', '28'),
    ('reimbursement', 'What proof do Orion employees need for train expenses?', 'travel.txt', 'receipts'),
    ('backup', 'How frequently should the Aster database be archived?', 'backup.txt', 'six hours'),
    ('chinese-office', '赤松办公室周几几点关门？', 'office.md', '十六点'),
    ('latest-notice', 'What is the April Vega training fee?', 'conflict_b.txt', '45'),
    ('older-notice', 'What was the March Vega training fee?', 'conflict_a.txt', '40'),
]

if '--worker' in sys.argv:
    data = sys.argv[-1]
    os.environ['RAG_DATA_DIR'] = data
    store._collection = None
    store._client = None
    for name, text in docs.items():
        chunks = chunk_document(text)
        store.add_document(chunks, embed(chunks), name)
    results = []
    for label, question, source, fact in cases:
        vector = embed([question])[0]
        dense = store.query(vector)
        hybrid = store.query(vector, question=question)
        contains = lambda rows: any(row['source'] == source and fact in row['text'] for row in rows)
        results.append({'case': label, 'dense_recall_at_6': contains(dense),
                        'hybrid_recall_at_6': contains(hybrid), 'hybrid_sources': [r['source'] for r in hybrid]})
    print(json.dumps({'scope': '18 synthetic documents, 12 disclosed development queries; retrieval only, not answer accuracy',
                      'dense_hits': sum(r['dense_recall_at_6'] for r in results),
                      'hybrid_hits': sum(r['hybrid_recall_at_6'] for r in results), 'cases': results}, ensure_ascii=False, indent=2))
