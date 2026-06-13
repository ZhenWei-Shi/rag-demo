"""
最小 RAG Demo（Ollama 本地版）
流程：文本 → 切块 → 向量化 → 存入 ChromaDB → 查询时检索 → Ollama 生成答案
"""

import ollama
import chromadb
from sentence_transformers import SentenceTransformer

# ─── 初始化 ────────────────────────────────────────────────────────────────────

OLLAMA_MODEL = "llama3.2"  # 可改成 mistral、phi3 等

embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
chroma_client = chromadb.Client()
collection = chroma_client.create_collection("my_docs")


# ─── 索引文档 ─────────────────────────────────────────────────────────────────

def index_text(text: str, doc_id: str = "doc"):
    chunk_size = 200
    overlap = 40

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap

    embeddings = embedding_model.encode(chunks).tolist()
    collection.add(
        documents=chunks,
        embeddings=embeddings,
        ids=[f"{doc_id}_chunk_{i}" for i in range(len(chunks))]
    )
    print(f"[索引完成] 共 {len(chunks)} 个文本块")


# ─── 检索 + 生成 ──────────────────────────────────────────────────────────────

def ask(question: str) -> str:
    q_embedding = embedding_model.encode([question]).tolist()
    results = collection.query(query_embeddings=q_embedding, n_results=3)
    retrieved_chunks = results["documents"][0]

    context = "\n\n---\n\n".join(retrieved_chunks)

    response = ollama.chat(
        model=OLLAMA_MODEL,
        messages=[{
            "role": "user",
            "content": (
                f"请根据以下资料回答问题。如果资料中没有相关信息，请明确说明。\n\n"
                f"【资料】\n{context}\n\n"
                f"【问题】{question}"
            )
        }]
    )
    return response["message"]["content"]


# ─── 示例知识库 ───────────────────────────────────────────────────────────────

SAMPLE_TEXT = """
RAG（Retrieval-Augmented Generation）是一种结合检索和生成的 AI 架构。
它的核心思路是：在 LLM 生成答案之前，先从外部知识库检索相关信息，
再把检索结果作为上下文一起发给模型，让模型基于真实资料回答。

RAG 解决了 LLM 的两个主要局限：知识截止日期和无法访问私有数据。
企业可以用 RAG 构建内部文档问答系统，而无需对模型进行微调。

向量数据库是 RAG 的核心组件之一。常用的有 ChromaDB（本地）、
Pinecone（云端）、Weaviate 和 FAISS。它们都支持基于语义相似度的检索，
而不是传统的关键词匹配。

Embedding（向量化）是把文本转换为高维向量的过程。语义相近的文本，
对应的向量在空间中距离较近。常用的 Embedding 模型有 OpenAI 的
text-embedding-3-small 和开源的 sentence-transformers。

Chunking（文本切块）是 RAG 中影响效果最大的环节之一。
块太大会引入噪音，块太小会丢失上下文。
常见策略包括：固定大小切割、递归字符切割、语义切割。
实际项目中通常在 256~512 token 之间，并加上 50 token 的重叠。
"""


# ─── 主程序 ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print(f"RAG Demo 启动 (模型: {OLLAMA_MODEL})")
    print("=" * 50)

    index_text(SAMPLE_TEXT, doc_id="rag_intro")

    questions = [
        "RAG 是什么？它解决了什么问题？",
        "常用的向量数据库有哪些？",
        "Chunking 应该切多大？",
        "Python 的发明者是谁？",
    ]

    print()
    for q in questions:
        print(f"问：{q}")
        print(f"答：{ask(q)}")
        print("-" * 50)
