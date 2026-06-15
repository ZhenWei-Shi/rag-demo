# EN: LLM answer generator. Supports DeepSeek (via OpenAI-compatible API) and Ollama (local).
#     Switch providers by setting the LLM_PROVIDER environment variable.
# ZH: LLM 答案生成器。支持 DeepSeek（OpenAI 兼容接口）和 Ollama（本地）。
#     通过 LLM_PROVIDER 环境变量切换提供商。

import os
from typing import Generator

# EN: Maximum number of previous conversation turns to include in the LLM context.
# ZH: 发送给 LLM 的最大历史对话轮数。
MAX_HISTORY_TURNS = 6


def _build_messages(question: str, context_chunks: list[dict], history: list[dict] | None) -> list[dict]:
    """
    EN: Assemble the messages list for the LLM call.
        Injects retrieved document chunks as the system context,
        then appends conversation history and the current question.
    ZH: 构建发送给 LLM 的消息列表。
        将检索到的文档分块作为系统上下文注入，
        然后追加对话历史和当前问题。
    """
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
        # EN: Trim history to the last N turns to stay within context limits.
        # ZH: 截取最近 N 轮历史，避免超出 LLM 上下文长度限制。
        messages.extend(history[-MAX_HISTORY_TURNS:])
    messages.append({"role": "user", "content": question})
    return messages


def generate_answer(question: str, context_chunks: list[dict], history: list[dict] | None = None) -> str:
    """
    EN: Generate a complete (non-streaming) answer from the LLM.
    ZH: 从 LLM 生成完整（非流式）答案。
    """
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
        # EN: Default to Ollama for local, fully private inference.
        # ZH: 默认使用 Ollama 进行本地全私有推理。
        import ollama
        response = ollama.chat(model=os.getenv("OLLAMA_MODEL", "llama3.2"), messages=messages)
        return response["message"]["content"]


def stream_answer(question: str, context_chunks: list[dict], history: list[dict] | None = None) -> Generator[str, None, None]:
    """
    EN: Stream the LLM answer token by token. Used by the /ask/stream SSE endpoint.
    ZH: 逐 token 流式输出 LLM 答案，供 /ask/stream SSE 接口使用。
    """
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
