import os

MAX_HISTORY_TURNS = 6

def generate_answer(question: str, context_chunks: list[dict], history: list[dict] | None = None) -> str:
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

    provider = os.getenv("LLM_PROVIDER", "ollama")

    if provider == "groq":
        from groq import Groq
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        resp = client.chat.completions.create(
            model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
            messages=messages,
        )
        return resp.choices[0].message.content
    else:
        import ollama
        response = ollama.chat(model=os.getenv("OLLAMA_MODEL", "llama3.2"), messages=messages)
        return response["message"]["content"]
