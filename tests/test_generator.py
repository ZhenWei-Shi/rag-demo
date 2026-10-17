import pytest
import ollama
from rag.generator import generate_answer,stream_answer


@pytest.mark.parametrize('stream',[False,True])
def test_both_ollama_answer_routes_preserve_context_history_and_model(monkeypatch,stream):
    captured=[]
    def fake_chat(**kwargs):
        captured.append(kwargs)
        value={'message':{'content':'fixture response'}}
        return iter([value]) if kwargs.get('stream') else value
    monkeypatch.setattr(ollama,'chat',fake_chat)
    monkeypatch.setenv('LLM_PROVIDER','ollama');monkeypatch.setenv('OLLAMA_MODEL','test-model')
    history=[{'role':'user' if i%2==0 else 'assistant','content':str(i)} for i in range(8)]
    chunks=[{'source':'source.md','text':'Exact supporting evidence.'}]
    response=''.join(stream_answer('current question',chunks,history)) if stream else generate_answer('current question',chunks,history)
    assert response=='fixture response'
    call=captured[0];assert call['model']=='test-model'
    assert call['messages'][1:-1]==history[-6:]
    assert call['messages'][-1]=={'role':'user','content':'current question'}
    assert '[Source: source.md]\nExact supporting evidence.' in call['messages'][0]['content']
    assert history[0]['content']=='0'
