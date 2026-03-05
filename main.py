from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config import DEFAULT_WAKE_WORD, EMBEDDING_MODEL, WHISPER_MODEL
from server.ai.agent import init_agent
from server.ai.knowledge_retriever import load_embedding_model
from server.ai.stt_engine import load_stt_engine
from server.api.ingest_api import router as ingest_router
from server.api.knowledge_api import router as knowledge_router
from server.api.lecture_api import router as lecture_router
from server.api.slide_api import router as slide_router
from server.api.websocket_api import router as websocket_router
from server.db.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    load_stt_engine(WHISPER_MODEL)
    load_embedding_model(EMBEDDING_MODEL)
    init_agent(DEFAULT_WAKE_WORD)
    yield


app = FastAPI(title="Lecture Copilot", lifespan=lifespan)

app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")
app.mount("/chunks", StaticFiles(directory="lecture_data/chunks"), name="chunks")

app.include_router(ingest_router)
app.include_router(lecture_router)
app.include_router(slide_router)
app.include_router(knowledge_router)
app.include_router(websocket_router)


@app.get("/")
def root() -> dict:
    return {"status": "ok", "instructor": "/instructor", "display": "/display"}


@app.get("/instructor")
def instructor() -> FileResponse:
    return FileResponse("frontend/instructor/index.html")


@app.get("/display")
def display() -> FileResponse:
    return FileResponse("frontend/display/index.html")
