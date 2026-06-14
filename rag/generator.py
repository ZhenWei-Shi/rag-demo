import os
from typing import Generator

MAX_HISTORY_TURNS = 6

def _build_messages(question: str, context_chunks: list[dict], history: list[dict] | None) -> list[dict]:
    context = "\n\n---\n\n".join(
        f"[Source: {c['source']}]\n{c['text']}" for c in context_chunks
    )
    system = (
        "You are a helpful assistant that answers questions based on the provided documents. "
        "Respond in the same language as the user's question. "
        "If the answer is not found in the documents, say so clearly.\n\n"
        f"Documents:\n{context}"
    )
    messages = [{"role": "system", "content": system}]
    if history:
        messages.extend(history[-MAX_HISTORY_TURNS:])
    messages.append({"role": "user", "content": question})
    return messages

def generate_answer(question: str, context_chunks: list[dict], history: list[dict] | None = None) -> str:
    messages = _build_messages(question, context_chunks, history)
    provider = os.getenv("LLM_PROVIDER", "ollama")

    if provider == "openai_compat":
        from openai import OpenAI
        client = OpenAI(
            api_key=os.getenv("LLM_API_KEY"),
            base_url=os.getenv("LLM_BASE_URL"),
        )
        resp = client.chat.completions.create(
            model=os.getenv("LLM_MODEL"),
            messages=messages,
        )
        return resp.choices[0].message.content
    else:
        import ollama
        response = ollama.chat(model=os.getenv("OLLAMA_MODEL", "llama3.2"), messages=messages)
        return response["message"]["content"]


def stream_answer(question: str, context_chunks: list[dict], history: list[dict] | None = None) -> Generator[str, None, None]:
    messages = _build_messages(question, context_chunks, history)
    provider = os.getenv("LLM_PROVIDER", "ollama")

    if provider == "openai_compat":
        from openai import OpenAI
        client = OpenAI(
            api_key=os.getenv("LLM_API_KEY"),
            base_url=os.getenv("LLM_BASE_URL"),
        )
        stream = client.chat.completions.create(
            model=os.getenv("LLM_MODEL"),
            messages=messages,
            stream=True,
        )
        for chunk in stream:
            content = chunk.choices[0].delta.content
            if content:
                yield content
    else:
        import ollama
        stream = ollama.chat(
            model=os.getenv("OLLAMA_MODEL", "llama3.2"),
            messages=messages,
            stream=True,
        )
        for chunk in stream:
            content = chunk["message"]["content"]
            if content:
                yield content
