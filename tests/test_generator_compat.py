import copy
import sys
import types

import pytest

from rag.generator import generate_answer, stream_answer

NS = types.SimpleNamespace


def _fake_openai(monkeypatch, calls):
    class FakeOpenAI:
        def __init__(self, **kwargs):
            calls.append(('client', kwargs))
            self.chat = NS(completions=NS(create=self._create))

        def _create(self, **kwargs):
            calls.append(('create', kwargs))
            if kwargs.get('stream'):
                return iter([NS(choices=[NS(delta=NS(content=c))]) for c in ('fix', None, '', 'ture')])
            return NS(choices=[NS(message=NS(content='fixture'))])

    module = types.ModuleType('openai')
    module.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, 'openai', module)
    monkeypatch.setenv('LLM_PROVIDER', 'openai_compat')
    monkeypatch.setenv('LLM_MODEL', 'compat-model')
    monkeypatch.setenv('LLM_API_KEY', 'test-key')
    monkeypatch.setenv('LLM_BASE_URL', 'http://compat.test/v1')


def _call(stream, question, chunks, history):
    if stream:
        return ''.join(stream_answer(question, chunks, history))
    return generate_answer(question, chunks, history)


@pytest.mark.parametrize('stream', [False, True])
def test_openai_compat_routes_keep_history_sources_and_inputs(monkeypatch, stream):
    calls = []
    _fake_openai(monkeypatch, calls)
    history = [{'role': 'user' if i % 2 == 0 else 'assistant', 'content': f'turn {i}'} for i in range(8)]
    chunks = [{'source': 'lab.md', 'text': '容量 30 人'}, {'source': 'fees.md', 'text': 'Fee: 50 CNY'}]
    before = copy.deepcopy((history, chunks))
    assert _call(stream, 'How many people fit?', chunks, history) == 'fixture'
    assert calls[0] == ('client', {'api_key': 'test-key', 'base_url': 'http://compat.test/v1'})
    create = calls[1][1]
    assert create['model'] == 'compat-model'
    assert bool(create.get('stream')) is stream
    messages = create['messages']
    assert messages[0]['role'] == 'system'
    assert '[Source: lab.md]\n容量 30 人\n\n---\n\n[Source: fees.md]\nFee: 50 CNY' in messages[0]['content']
    assert messages[1:-1] == history[-6:]
    assert messages[-1] == {'role': 'user', 'content': 'How many people fit?'}
    assert (history, chunks) == before


def test_openai_compat_stream_and_plain_send_identical_messages(monkeypatch):
    calls = []
    _fake_openai(monkeypatch, calls)
    chunks = [{'source': 'renewal.md', 'text': '续借 2 次'}]
    for stream in (False, True):
        _call(stream, 'Can I renew?', chunks, None)
    sent = [kwargs['messages'] for kind, kwargs in calls if kind == 'create']
    assert len(sent) == 2 and sent[0] == sent[1]
    assert [m['role'] for m in sent[0]] == ['system', 'user']
