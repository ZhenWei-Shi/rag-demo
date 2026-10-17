"""ASGI entry point: assemble routes, model warmup and static assets."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from api.documents import router as documents_router
from api.questions import router as questions_router
from rag.embedder import warmup


@asynccontextmanager
async def lifespan(app: FastAPI):
    warmup()
    yield


app = FastAPI(title="RAG Document Q&A", lifespan=lifespan)
app.include_router(documents_router)
app.include_router(questions_router)
app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
