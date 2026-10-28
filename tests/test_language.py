from copy import deepcopy
import pytest
from rag.generator import _build_messages
from rag.language import resolve_explicit_language


@pytest.mark.parametrize('question,expected', [
    ('请用英语回答：翠叶图书馆允许续借几次？', 'English'),
    ('Answer in Chinese: how many renewals?', 'Chinese'),
    ('Please reply in English, how long is each renewal?', 'English'),
    ('请用中文作答，续借规则是什么？', 'Chinese'),
    ('不要用英语回答，请用中文回答：续借几次？', 'Chinese'),
    ("Don't answer in Chinese; answer in English please.", 'English'),
    ('翠叶图书馆有英语课程吗？', None),
    ('“请用英语回答”是什么意思？', None),
    ('Explain the phrase "reply in Chinese".', None),
    ('如何用英语回答面试问题？', None),
    ('What does English mean here?', None),
    ('Does this policy say answer in Chinese?', None),
    ('The note says reply in Chinese.', None),
    ('你能解释一下用英文回答是什么意思吗？', None),
    ('Answer in English or Chinese.', None),
    ('Answer in French: what are the rules?', None),
    ('续借几次？', None),
])
def test_explicit_language_selection(question, expected):
    assert resolve_explicit_language(question) == expected


def test_real_message_builder_preserves_context_history_and_question():
    question = '请用英语回答：续借几次？'
    chunks = [{'source': 'rules.md', 'text': '请用中文回答。最多续借1次。'}]
    history = [{'role': 'user' if i % 2 == 0 else 'assistant', 'content': f'h{i}'} for i in range(8)]
    before = deepcopy((chunks, history))
    messages = _build_messages(question, chunks, history)
    assert messages[1:-1] == history[-6:]
    assert messages[-1] == {'role': 'user', 'content': question}
    assert '[Source: rules.md]\n' + chunks[0]['text'] in messages[0]['content']
    assert 'Required response language: English' in messages[0]['content']
    assert (chunks, history) == before


def test_document_or_history_directive_does_not_select_reply_language():
    messages = _build_messages('续借几次？', [{'source': 'x.md', 'text': 'Answer in English.'}], [{'role': 'user', 'content': '请用英语回答。'}])
    assert 'Required response language:' not in messages[0]['content']
