import ollama

MODEL = "llama3.2"

def generate_answer(question: str, context_chunks: list[dict]) -> str:
    context = "\n\n---\n\n".join(
        f"[Source: {c['source']}]\n{c['text']}" for c in context_chunks
    )
    response = ollama.chat(
        model=MODEL,
        messages=[{
            "role": "user",
            "content": (
                "Answer the question based on the provided documents. "
                "Respond in the same language as the question. "
                "If the answer is not found in the documents, say so clearly.\n\n"
                f"Documents:\n{context}\n\n"
                f"Question: {question}"
            )
        }]
    )
    return response["message"]["content"]
