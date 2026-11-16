"""FastAPI app: API + static frontend for 进步."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db, logic, words as wordbank

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"

app = FastAPI(title="进步 Progress", docs_url=None, redoc_url=None)


class CreateRoomIn(BaseModel):
    name: str
    friendName: str | None = None
    punishmentText: str | None = None


class JoinRoomIn(BaseModel):
    code: str
    name: str


class RateIn(BaseModel):
    wordId: str
    rating: str


class QuizSubmitIn(BaseModel):
    mode: str = "normal"
    answers: list[dict] = Field(default_factory=list)


class SettingsIn(BaseModel):
    name: str | None = None
    dailyNew: int | None = None
    reviewCap: int | None = None
    punishmentText: str | None = None


class CustomWordIn(BaseModel):
    word: str
    ipa: str | None = ""
    meaning: str
    example: str | None = ""
    exampleZh: str | None = ""


@app.on_event("startup")
def _startup():
    wordbank.load()
    db.connect()


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    detail = exc.detail
    if isinstance(detail, list):
        detail = "; ".join(str(x) for x in detail)
    return JSONResponse({"error": str(detail)}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def valid_error(request: Request, exc: RequestValidationError):
    return JSONResponse({"error": "提交的内容不完整或格式不对"}, status_code=422)


def current_member(
    authorization: str | None = Header(default=None),
    x_token: str | None = Header(default=None, alias="X-Token"),
) -> dict:
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    elif x_token:
        token = x_token.strip()
    if not token:
        raise HTTPException(401, "请先创建或加入房间")
    with db.lock():
        logic.process_misses  # noqa: B018 - just a reminder; process after lookup
        member = logic.get_member_by_token(token)
        if not member:
            raise HTTPException(401, "登录已失效，请重新加入房间")
        logic.process_misses(member["room_id"])
        member = logic.get_member_by_token(token)
        return member


def guarded(fn):
    # used inline
    return fn


@app.post("/api/rooms")
def create_room(body: CreateRoomIn):
    with db.lock():
        try:
            return logic.create_room(body.name, body.friendName, body.punishmentText)
        except ValueError as e:
            raise HTTPException(400, str(e))


@app.post("/api/rooms/join")
def join_room(body: JoinRoomIn):
    with db.lock():
        try:
            return logic.join_room(body.code, body.name)
        except ValueError as e:
            raise HTTPException(400, str(e))


@app.get("/api/state")
def get_state(authorization: str | None = Header(default=None), x_token: str | None = Header(default=None, alias="X-Token")):
    member = current_member(authorization, x_token)
    with db.lock():
        return logic.room_state(member)


@app.patch("/api/settings")
def patch_settings(body: SettingsIn, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None, alias="X-Token")):
    member = current_member(authorization, x_token)
    with db.lock():
        try:
            return logic.update_settings(member, body.model_dump())
        except ValueError as e:
            raise HTTPException(400, str(e))


@app.get("/api/session")
def get_session(authorization: str | None = Header(default=None), x_token: str | None = Header(default=None, alias="X-Token")):
    member = current_member(authorization, x_token)
    with db.lock():
        items = logic.build_session(member)
        return {"items": items, "plan": logic.plan_for(member) | {"remainingDue": None, "remainingNew": None, "daily": None}}


@app.post("/api/vocab/rate")
def vocab_rate(body: RateIn, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None, alias="X-Token")):
    member = current_member(authorization, x_token)
    with db.lock():
        try:
            return logic.rate_word(member, body.wordId, body.rating)
        except ValueError as e:
            raise HTTPException(400, str(e))


@app.post("/api/vocab/complete")
def vocab_complete(authorization: str | None = Header(default=None), x_token: str | None = Header(default=None, alias="X-Token")):
    member = current_member(authorization, x_token)
    with db.lock():
        return logic.complete_vocab_session(member)


@app.get("/api/quiz")
def get_quiz(mode: str = "normal", authorization: str | None = Header(default=None), x_token: str | None = Header(default=None, alias="X-Token")):
    member = current_member(authorization, x_token)
    with db.lock():
        try:
            questions = logic.start_quiz(member, mode)
            return {"questions": questions, "mode": mode}
        except ValueError as e:
            raise HTTPException(400, str(e))


@app.post("/api/quiz/submit")
def quiz_submit(body: QuizSubmitIn, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None, alias="X-Token")):
    member = current_member(authorization, x_token)
    with db.lock():
        return logic.submit_quiz(member, body.answers, body.mode)


@app.post("/api/checkin")
def checkin(authorization: str | None = Header(default=None), x_token: str | None = Header(default=None, alias="X-Token")):
    member = current_member(authorization, x_token)
    with db.lock():
        result = logic.try_checkin(member)
        if not result["ok"] and not result.get("already"):
            raise HTTPException(400, result.get("error") or "还不能打卡")
        return {"checkin": result, "state": logic.room_state(member)}


@app.get("/api/words")
def get_words(
    q: str = "",
    status: str = "全部",
    page: int = 1,
    pageSize: int = 40,
    authorization: str | None = Header(default=None),
    x_token: str | None = Header(default=None, alias="X-Token"),
):
    member = current_member(authorization, x_token)
    with db.lock():
        return logic.list_words(member, q, status, page, pageSize)


@app.get("/api/words/{word_id}")
def get_word_detail(word_id: str, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None, alias="X-Token")):
    member = current_member(authorization, x_token)
    with db.lock():
        w = logic.word_by_id(member["id"], word_id)
        if not w:
            raise HTTPException(404, "找不到这个单词")
        rec = db.fetchone(
            "SELECT * FROM word_progress WHERE member_id=? AND word_id=?",
            (member["id"], word_id),
        )
        return {"word": wordbank.public_word(w), "progress": rec, "status": logic.status_of(rec)}


@app.post("/api/words")
def post_word(body: CustomWordIn, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None, alias="X-Token")):
    member = current_member(authorization, x_token)
    with db.lock():
        try:
            return logic.add_custom_word(member, body.model_dump())
        except ValueError as e:
            raise HTTPException(400, str(e))


@app.patch("/api/words/{word_id}")
def patch_word(word_id: str, body: CustomWordIn, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None, alias="X-Token")):
    member = current_member(authorization, x_token)
    with db.lock():
        try:
            return logic.update_custom_word(member, word_id, body.model_dump())
        except ValueError as e:
            raise HTTPException(400, str(e))


@app.delete("/api/words/{word_id}")
def delete_word(word_id: str, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None, alias="X-Token")):
    member = current_member(authorization, x_token)
    with db.lock():
        return logic.delete_custom_word(member, word_id)


@app.get("/api/export")
def export_data(authorization: str | None = Header(default=None), x_token: str | None = Header(default=None, alias="X-Token")):
    member = current_member(authorization, x_token)
    with db.lock():
        return logic.export_member(member)


@app.post("/api/import")
async def import_data(request: Request, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None, alias="X-Token")):
    member = current_member(authorization, x_token)
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "这不是有效的 JSON 文件。")
    with db.lock():
        try:
            return logic.import_member(member, payload)
        except ValueError as e:
            raise HTTPException(400, str(e))


@app.post("/api/reset")
def reset_data(authorization: str | None = Header(default=None), x_token: str | None = Header(default=None, alias="X-Token")):
    member = current_member(authorization, x_token)
    with db.lock():
        return logic.reset_member(member)


@app.get("/api/meta")
def meta():
    if not wordbank.all_words():
        wordbank.load()
    return {
        "name": "进步",
        "wordCount": wordbank.word_count(),
        "grammarCount": wordbank.grammar_count(),
        "defaultPunishment": logic.DEFAULT_PUNISHMENT,
    }


# Static site. API routes above take precedence.
@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/", StaticFiles(directory=str(STATIC), html=True), name="static")
