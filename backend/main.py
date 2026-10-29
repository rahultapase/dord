"""FastAPI app. Local only: run with

    uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend import ollama_client as oc
from backend.game import Engine, GameError

engine = Engine()


@asynccontextmanager
async def lifespan(_: FastAPI):
    engine.warm_up()
    yield


app = FastAPI(title="Ghost Words", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan)

DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


@app.exception_handler(GameError)
async def _game_error(_: Request, exc: GameError) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content={"detail": exc.message})


class NewGame(BaseModel):
    mode: Literal["real-or-ghost", "three-defs"] = "real-or-ghost"
    rounds: int = Field(20, ge=1, le=40)
    vsGemma: bool = True


class Answer(BaseModel):
    n: int = Field(ge=1)
    choice: str | int


@app.get("/api/health")
def health() -> dict:
    status = oc.health()
    return {**status, "ok": bool(status.get("ok")), "headwords": len(engine.dictionary),
            "reals": len(engine.reals), "ghosts": len(engine.ghosts), "threeDefsWords": len(engine.bluffs)}


@app.post("/api/game")
def new_game(body: NewGame) -> dict:
    return engine.new_game(body.mode, body.rounds, body.vsGemma)


@app.get("/api/game/{game_id}/card/{n}")
def card(game_id: str, n: int) -> dict:
    return engine.card(game_id, n)


@app.post("/api/game/{game_id}/answer")
def answer(game_id: str, body: Answer) -> dict:
    return engine.answer(game_id, body.n, body.choice)


@app.get("/api/game/{game_id}/summary")
def summary(game_id: str) -> dict:
    return engine.summary(game_id)


@app.post("/api/ghosts/summon")
def summon() -> dict:
    return engine.summon()


@app.get("/api/seance")
def seance() -> dict:
    data = engine.seance()
    if data is None:
        raise HTTPException(404, "the seance has not been held yet (scripts/run_seance.py)")
    return data


# The built front end (frontend/dist), so one command serves the whole game. In development
# Vite serves the UI on :5173 and proxies /api here.
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        target = DIST / path
        if path and target.is_file() and DIST in target.resolve().parents:
            return FileResponse(target)
        return FileResponse(DIST / "index.html")
