import ollama

MODEL = "llama3.2"
MAX_HISTORY_TURNS = 6  # keep last 6 messages (3 turns) to avoid context overflow

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

    response = ollama.chat(model=MODEL, messages=messages)
    return response["message"]["content"]
