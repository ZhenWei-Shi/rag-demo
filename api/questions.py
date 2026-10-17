"""Ordinary and streaming Q&A HTTP endpoints; generation stays off the event loop."""
import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from api.schemas import MAX_QUESTION_LENGTH, Question
from rag.embedder import embed
from rag.generator import generate_answer, stream_answer
from rag.store import query

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/ask")
async def ask(body: Question):
    # EN: Non-streaming Q&A endpoint (kept for backward compatibility).
    # ZH: 非流式问答接口（保留以兼容旧版本）。
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    if len(body.question) > MAX_QUESTION_LENGTH:
        raise HTTPException(status_code=400, detail=f"Question too long (max {MAX_QUESTION_LENGTH} chars)")

    q_embedding = (await run_in_threadpool(embed, [body.question]))[0]
    chunks = await run_in_threadpool(query, q_embedding, question=body.question)

    if not chunks:
        return {
            "answer": "No documents have been uploaded yet. Please upload a PDF or text file first.",
            "sources": [],
            "chunks": []
        }

    answer = await run_in_threadpool(generate_answer, body.question, chunks,
                                    [message.model_dump() for message in body.history])
    sources = list(dict.fromkeys(c["source"] for c in chunks))

    return {"answer": answer, "sources": sources, "chunks": chunks}


@router.post("/ask/stream")
async def ask_stream(body: Question):
    # EN: Streaming Q&A endpoint using Server-Sent Events (SSE).
    #     Tokens are pushed to the client as they arrive from the LLM.
    # ZH: 基于 SSE 的流式问答接口，LLM 输出的每个 token 实时推送到客户端。
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    if len(body.question) > MAX_QUESTION_LENGTH:
        raise HTTPException(status_code=400, detail=f"Question too long (max {MAX_QUESTION_LENGTH} chars)")

    q_embedding = (await run_in_threadpool(embed, [body.question]))[0]
    chunks = await run_in_threadpool(query, q_embedding, question=body.question)

    if not chunks:
        msg = "No documents have been uploaded yet. Please upload a PDF or text file first."
        async def _empty():
            yield f"data: {json.dumps({'type': 'token', 'content': msg})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'sources': [], 'chunks': [], 'answer': msg})}\n\n"
        return StreamingResponse(_empty(), media_type="text/event-stream")

    question, history, captured = body.question, [message.model_dump() for message in body.history], chunks

    def _generate():
        # EN: Accumulate the full answer while streaming tokens to the client.
        # ZH: 在向客户端流式推送 token 的同时，累积完整答案以便最终发送 done 事件。
        full = ""
        try:
            for token in stream_answer(question, captured, history):
                full += token
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
        except Exception:
            logger.exception("Answer stream failed")
            yield f"data: {json.dumps({'type': 'error', 'message': 'Answer generation failed. Please retry.'})}\n\n"
            return
        sources = list(dict.fromkeys(c["source"] for c in captured))
        yield f"data: {json.dumps({'type': 'done', 'sources': sources, 'chunks': captured, 'answer': full})}\n\n"

    return StreamingResponse(_generate(), media_type="text/event-stream")
