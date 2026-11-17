"""FastAPI app: API + static frontend for 请叫我学习."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections import OrderedDict
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db, logic, words as wordbank

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"

app = FastAPI(title="请叫我学习", docs_url=None, redoc_url=None)

# Short same-origin cache so a second tap does not wait on the speech host again.
_TTS_CACHE: OrderedDict[tuple[str, str], bytes] = OrderedDict()
_TTS_CACHE_MAX = 240


class CreateRoomIn(BaseModel):
    name: str
    friendName: str | None = None
    punishmentText: str | None = None
    studyPlan: str | None = None


class JoinRoomIn(BaseModel):
    code: str
    name: str
    studyPlan: str | None = None


class RateIn(BaseModel):
    wordId: str
    rating: str


class QuizSubmitIn(BaseModel):
    mode: str = "normal"
    track: str | None = None
    answers: list[dict] = Field(default_factory=list)


class VocabCompleteIn(BaseModel):
    track: str | None = None


class SettingsIn(BaseModel):
    name: str | None = None
    dailyNew: int | None = None
    reviewCap: int | None = None
    punishmentText: str | None = None
    studyPlan: str | None = None


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
            return logic.create_room(body.name, body.friendName, body.punishmentText, body.studyPlan)
        except ValueError as e:
            raise HTTPException(400, str(e))


@app.post("/api/rooms/join")
def join_room(body: JoinRoomIn):
    with db.lock():
        try:
            return logic.join_room(body.code, body.name, body.studyPlan)
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
def get_session(
    track: str | None = None,
    authorization: str | None = Header(default=None),
    x_token: str | None = Header(default=None, alias="X-Token"),
):
    member = current_member(authorization, x_token)
    with db.lock():
        try:
            items = logic.build_session(member, track)
        except ValueError as e:
            raise HTTPException(400, str(e))
        plan = logic.plan_for(member)
        public = {k: v for k, v in plan.items() if k not in ("remainingDue", "remainingNew", "daily", "_tracks")}
        return {"items": items, "track": track, "plan": public}


@app.post("/api/vocab/rate")
def vocab_rate(body: RateIn, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None, alias="X-Token")):
    member = current_member(authorization, x_token)
    with db.lock():
        try:
            return logic.rate_word(member, body.wordId, body.rating)
        except ValueError as e:
            raise HTTPException(400, str(e))


@app.post("/api/vocab/complete")
def vocab_complete(
    body: VocabCompleteIn | None = None,
    authorization: str | None = Header(default=None),
    x_token: str | None = Header(default=None, alias="X-Token"),
):
    member = current_member(authorization, x_token)
    with db.lock():
        return logic.complete_vocab_session(member, (body.track if body else None))


@app.get("/api/quiz")
def get_quiz(
    mode: str = "normal",
    track: str = "cet4",
    authorization: str | None = Header(default=None),
    x_token: str | None = Header(default=None, alias="X-Token"),
):
    member = current_member(authorization, x_token)
    with db.lock():
        try:
            questions = logic.start_quiz(member, mode, track)
            return {"questions": questions, "mode": mode, "track": track}
        except ValueError as e:
            raise HTTPException(400, str(e))


@app.post("/api/quiz/submit")
def quiz_submit(body: QuizSubmitIn, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None, alias="X-Token")):
    member = current_member(authorization, x_token)
    with db.lock():
        return logic.submit_quiz(member, body.answers, body.mode, body.track)


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
    lang: str = "",
    authorization: str | None = Header(default=None),
    x_token: str | None = Header(default=None, alias="X-Token"),
):
    member = current_member(authorization, x_token)
    with db.lock():
        return logic.list_words(member, q, status, page, pageSize, lang)


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
        "name": "请叫我学习",
        "wordCount": wordbank.word_count(),
        "koreanCount": wordbank.korean_count(),
        "grammarCount": wordbank.grammar_count(),
        "defaultPunishment": logic.DEFAULT_PUNISHMENT,
        "quizCorrectPoints": logic.QUIZ_CORRECT_POINTS,
        "plans": [
            {"id": "cet4", "label": "四级英语"},
            {"id": "korean", "label": "韩语入门"},
            {"id": "both", "label": "四级英语 + 韩语"},
        ],
    }


def _tts_urls(lang: str, text: str) -> list[str]:
    q = urllib.parse.quote(text)
    if lang == "ko":
        return [
            f"https://dict.youdao.com/dictvoice?audio={q}&le=ko",
            f"https://fanyi.baidu.com/gettts?lan=kor&text={q}&spd=3&source=web",
        ]
    return [
        f"https://dict.youdao.com/dictvoice?audio={q}&type=2",
        f"https://fanyi.baidu.com/gettts?lan=en&text={q}&spd=3&source=web",
    ]


def _fetch_tts(lang: str, text: str) -> bytes | None:
    key = (lang, text)
    cached = _TTS_CACHE.get(key)
    if cached:
        _TTS_CACHE.move_to_end(key)
        return cached
    for url in _tts_urls(lang, text):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = resp.read()
                ctype = (resp.headers.get("Content-Type") or "").lower()
            if data and ("audio" in ctype or "octet-stream" in ctype or data[:3] == b"ID3" or data[:1] == b"\xff"):
                _TTS_CACHE[key] = data
                while len(_TTS_CACHE) > _TTS_CACHE_MAX:
                    _TTS_CACHE.popitem(last=False)
                return data
        except Exception:
            continue
    return None


@app.get("/api/tts")
def tts(lang: str = Query("en"), q: str = Query("")):
    """Pronunciation audio for one word. Web Speech is preferred in the browser; this is the fallback."""
    language = "ko" if lang in {"ko", "korean", "kor"} else "en"
    text = " ".join((q or "").split())
    if not text or len(text) > 40:
        raise HTTPException(400, "请朗读一个单词")
    audio = _fetch_tts(language, text)
    if not audio:
        raise HTTPException(502, "暂时读不出来，可以先看读音")
    return Response(content=audio, media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=86400"})


# Static site. API routes above take precedence.
@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/", StaticFiles(directory=str(STATIC), html=True), name="static")
