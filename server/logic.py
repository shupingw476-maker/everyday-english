"""Study, check-in, punishment, and room logic. All calendar days use Asia/Shanghai."""
from __future__ import annotations

import json
import secrets
import string
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import db, words as wordbank

TZ = ZoneInfo("Asia/Shanghai")
DEFAULT_PUNISHMENT = "昨天没打卡的人，要被催，并且下一天要多做一份惩罚任务"
# Ebbinghaus-style curve in Asia/Shanghai calendar days.
# A new word's three same-day recalls are the learning round; the first spaced
# review is the next day. After 30 days the interval stays at 30.
REVIEW_CURVE = (1, 2, 4, 7, 15, 30)
ROUND_NEED = 3
# One-time migration: rounds already at 3 or 4 under the old rule of 5 count as passed.
ROUND_NEED_META = "round_need_v3"
MEMORY_TEXT = (
    "每个词要在本轮答对 3 次才算过关。不认识会把这 3 次清零，模糊会减掉 1 次，所以不能点一下就算学完。"
    "过关之后按 1、2、4、7、15、30 天复习（北京时间的自然日）。复习没记住，间隔退回上一级，不会继续变长。"
    "打卡要先做完今天到期的复习，再完成当天的新词。"
    "练英语时先看开头几个字母再拼写，拼对记为认识，同一次只记一遍。韩语不用英文字母拼写。"
)
CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
POINTS = {"again": 1, "hard": 3, "know": 8, "quiz_ok": 10, "quiz_miss": 0, "checkin": 30}
QUIZ_CORRECT_BONUS = 5
STREAK_BONUS = {3: 15, 7: 30, 14: 50}
PUNISH_EXTRA_NEW = 20
PUNISH_EXTRA_QUIZ = 1
KO_DAILY_NEW = 8
KO_REVIEW_CAP = 24
KO_QUIZ_SIZE = 6
KO_PUNISH_EXTRA_NEW = 8
KO_PUNISH_EXTRA_QUIZ = 1
QUIZ_CORRECT_POINTS = POINTS["quiz_ok"] + QUIZ_CORRECT_BONUS


def normalize_plan(value: str | None) -> str:
    text = (value or "").strip().lower()
    if text in {"korean", "ko", "kr", "hangul"}:
        return "korean"
    if text in {"both", "all", "cet4+korean", "en+ko", "english+korean"}:
        return "both"
    return "cet4"


def active_tracks(member: dict) -> list[str]:
    plan = normalize_plan(member.get("study_plan"))
    if plan == "both":
        return ["cet4", "korean"]
    if plan == "korean":
        return ["korean"]
    return ["cet4"]


def plan_label(member: dict) -> str:
    tracks = active_tracks(member)
    if tracks == ["cet4", "korean"]:
        return "四级英语 + 韩语"
    if tracks == ["korean"]:
        return "韩语入门"
    return "四级英语"


def word_track(word: dict | None, word_id: str = "") -> str:
    wid = word_id or (word or {}).get("id") or ""
    lang = (word or {}).get("lang")
    if lang == "ko" or str(wid).startswith("ko_"):
        return "korean"
    return "cet4"


def now() -> datetime:
    return datetime.now(TZ)


def today_str(dt: datetime | None = None) -> str:
    return (dt or now()).strftime("%Y-%m-%d")


def add_days(date_str: str, days: int) -> str:
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    return (d + timedelta(days=days)).strftime("%Y-%m-%d")


def start_of_day_ts(date_str: str) -> int:
    d = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=TZ)
    return int(d.timestamp() * 1000)


def greeting(dt: datetime | None = None) -> str:
    h = (dt or now()).hour
    if 5 <= h < 11:
        return "早上好"
    if 11 <= h < 13:
        return "中午好"
    if 13 <= h < 18:
        return "下午好"
    if 18 <= h < 22:
        return "晚上好"
    return "夜深了"


def format_cn_date(dt: datetime | None = None) -> str:
    d = dt or now()
    weeks = "星期一 星期二 星期三 星期四 星期五 星期六 星期日".split()
    return f"{d.month}月{d.day}日 {weeks[d.weekday()]}"


def new_code() -> str:
    for _ in range(20):
        code = "".join(secrets.choice(CODE_CHARS) for _ in range(6))
        if not db.fetchone("SELECT id FROM rooms WHERE code=?", (code,)):
            return code
    raise RuntimeError("无法生成邀请码")


def new_token() -> str:
    return secrets.token_urlsafe(24)


def _loads(s, default):
    try:
        return json.loads(s) if s else default
    except Exception:
        return default


def ensure_quiz_stats(member_id: int) -> dict:
    row = db.fetchone("SELECT * FROM quiz_stats WHERE member_id=?", (member_id,))
    if not row:
        db.execute(
            "INSERT INTO quiz_stats (member_id) VALUES (?)",
            (member_id,),
            commit=True,
        )
        row = db.fetchone("SELECT * FROM quiz_stats WHERE member_id=?", (member_id,))
    return row


def get_member_by_token(token: str) -> dict | None:
    return db.fetchone("SELECT * FROM members WHERE token=?", (token,))


def get_room(room_id: int) -> dict | None:
    return db.fetchone("SELECT * FROM rooms WHERE id=?", (room_id,))


def room_members(room_id: int) -> list[dict]:
    return db.fetchall("SELECT * FROM members WHERE room_id=? ORDER BY id", (room_id,))


def custom_words(member_id: int) -> list[dict]:
    rows = db.fetchall(
        "SELECT * FROM custom_words WHERE member_id=? ORDER BY created_at DESC",
        (member_id,),
    )
    out = []
    for r in rows:
        out.append(
            {
                "id": r["id"],
                "word": r["word"],
                "ipa": r["ipa"],
                "meaning": r["meaning"],
                "example": r["example"],
                "exampleZh": r["example_zh"],
                "custom": True,
            }
        )
    return out


def all_member_words(member_id: int) -> list[dict]:
    return words_for_track(member_id, "cet4")


def words_for_track(member_id: int, track: str) -> list[dict]:
    if track == "korean":
        return list(wordbank.korean_words())
    customs = custom_words(member_id)
    seen = {w["word"].lower() for w in customs}
    bank = [w for w in wordbank.all_words() if w["word"].lower() not in seen]
    return customs + bank


def word_by_id(member_id: int, word_id: str) -> dict | None:
    if word_id.startswith("c_"):
        row = db.fetchone(
            "SELECT * FROM custom_words WHERE id=? AND member_id=?",
            (word_id, member_id),
        )
        if not row:
            return None
        return {
            "id": row["id"],
            "word": row["word"],
            "ipa": row["ipa"],
            "meaning": row["meaning"],
            "example": row["example"],
            "exampleZh": row["example_zh"],
            "custom": True,
            "lang": "en",
        }
    if str(word_id).startswith("ko_"):
        return wordbank.get_korean(word_id)
    return wordbank.get_word(word_id)


def get_progress_map(member_id: int) -> dict[str, dict]:
    rows = db.fetchall("SELECT * FROM word_progress WHERE member_id=?", (member_id,))
    return {r["word_id"]: r for r in rows}


def status_of(rec: dict | None) -> str:
    if not rec or not rec.get("reps"):
        return "新词"
    if rec.get("status") == "mastered" or (rec.get("interval_days") or 0) >= 15:
        return "已掌握"
    return "学习中"


def process_misses(room_id: int) -> None:
    """After 00:00, mark members who missed yesterday and assign punishment."""
    today = today_str()
    yesterday = add_days(today, -1)
    for m in room_members(room_id):
        if m["joined_date"] > yesterday:
            # Joined today — cannot have missed yesterday.
            if m["missed_yesterday"] or m["punishment_pending"]:
                if m["last_checkin"] == today:
                    db.execute(
                        "UPDATE members SET missed_yesterday=0, punishment_pending=0 WHERE id=?",
                        (m["id"],),
                        commit=True,
                    )
            continue
        checked_yesterday = m["last_checkin"] == yesterday
        checked_today = m["last_checkin"] == today
        if checked_yesterday or checked_today:
            if m["missed_yesterday"] and checked_today:
                # Already made up today; leave flags until we clear on check-in (already cleared).
                pass
            if checked_yesterday and not checked_today:
                if m["missed_yesterday"] or m["punishment_pending"]:
                    db.execute(
                        "UPDATE members SET missed_yesterday=0, punishment_pending=0, miss_processed_on=? WHERE id=?",
                        (today, m["id"]),
                        commit=True,
                    )
            continue
        # Missed yesterday (and has not checked in today).
        if m["miss_processed_on"] == today:
            continue
        db.execute(
            """UPDATE members
               SET streak=0, punishment_pending=1, missed_yesterday=1, miss_processed_on=?
               WHERE id=?""",
            (today, m["id"]),
            commit=True,
        )


def _quiz_target_for(track: str, punishment: int) -> int:
    if track == "korean":
        return 1 + (KO_PUNISH_EXTRA_QUIZ if punishment else 0)
    if track == "cet4":
        return 1 + (PUNISH_EXTRA_QUIZ if punishment else 0)
    return 0


def ensure_daily(member: dict) -> dict:
    today = today_str()
    tracks = active_tracks(member)
    punishment = 1 if member.get("punishment_pending") or member.get("missed_yesterday") else 0
    en_quiz = _quiz_target_for("cet4", punishment) if "cet4" in tracks else 0
    ko_quiz = _quiz_target_for("korean", punishment) if "korean" in tracks else 0
    row = db.fetchone(
        "SELECT * FROM daily WHERE member_id=? AND date=?",
        (member["id"], today),
    )
    if not row:
        db.execute(
            """INSERT INTO daily (member_id, date, punishment, quiz_target, ko_quiz_target)
               VALUES (?, ?, ?, ?, ?)""",
            (member["id"], today, punishment, en_quiz, ko_quiz),
            commit=True,
        )
        row = db.fetchone(
            "SELECT * FROM daily WHERE member_id=? AND date=?",
            (member["id"], today),
        )
    elif punishment and not row["punishment"] and not row["checkin"]:
        # Miss processing happened after the daily row was created (e.g. right after midnight).
        db.execute(
            """UPDATE daily
               SET punishment=1, quiz_target=?, ko_quiz_target=?, new_target=NULL, ko_new_target=NULL
               WHERE member_id=? AND date=?""",
            (en_quiz, ko_quiz, member["id"], today),
            commit=True,
        )
        row = db.fetchone(
            "SELECT * FROM daily WHERE member_id=? AND date=?",
            (member["id"], today),
        )
    else:
        # A plan can gain Korean after today's row already exists (migration or settings).
        # Only fill a track that has not started, so in-progress English totals stay put.
        updates = []
        params: list = []
        if "korean" in tracks and not row["checkin"] and not (row.get("ko_quizzes_done") or 0):
            if (row.get("ko_quiz_target") or 0) == 0:
                updates.append("ko_quiz_target=?")
                params.append(ko_quiz)
        if "cet4" not in tracks and not row["checkin"] and not (row.get("quizzes_done") or 0):
            if (row.get("quiz_target") or 0) != 0:
                updates.append("quiz_target=?")
                params.append(0)
        if updates:
            params.extend([member["id"], today])
            db.execute(
                f"UPDATE daily SET {', '.join(updates)} WHERE member_id=? AND date=?",
                params,
                commit=True,
            )
            row = db.fetchone(
                "SELECT * FROM daily WHERE member_id=? AND date=?",
                (member["id"], today),
            )
    return row


def due_and_new(member: dict, track: str = "cet4", now_ms: int | None = None):
    now_ms = now_ms or int(now().timestamp() * 1000)
    progress = get_progress_map(member["id"])
    allw = words_for_track(member["id"], track)
    due = []
    fresh = []
    for w in allw:
        rec = progress.get(w["id"])
        if rec and rec["reps"] and rec["due_ts"] and rec["due_ts"] <= now_ms:
            due.append((w, rec))
        if not rec or not rec["reps"]:
            fresh.append(w)
    due.sort(key=lambda x: x[1]["due_ts"] or 0)
    return due, fresh, progress


def _freeze_pair(member: dict, daily: dict, track: str) -> tuple[int, int]:
    punish = 1 if daily["punishment"] else 0
    if track not in active_tracks(member):
        return 0, 0
    due, fresh, _ = due_and_new(member, track)
    if track == "korean":
        review_target = min(len(due), KO_REVIEW_CAP)
        new_goal = KO_DAILY_NEW + (KO_PUNISH_EXTRA_NEW if punish else 0)
    else:
        cap = max(5, int(member["review_cap"] or 40))
        daily_new = max(1, int(member["daily_new"] or 20))
        review_target = min(len(due), cap)
        new_goal = daily_new + (PUNISH_EXTRA_NEW if punish else 0)
    return review_target, min(len(fresh), new_goal)


def freeze_targets(member: dict, daily: dict) -> dict:
    """Freeze today's review/new targets the first time each track is computed."""
    sets = []
    params: list = []
    if daily["review_target"] is None or daily["new_target"] is None:
        review_target, new_target = _freeze_pair(member, daily, "cet4")
        sets.extend(["review_target=?", "new_target=?"])
        params.extend([review_target, new_target])
    if daily.get("ko_review_target") is None or daily.get("ko_new_target") is None:
        review_target, new_target = _freeze_pair(member, daily, "korean")
        sets.extend(["ko_review_target=?", "ko_new_target=?"])
        params.extend([review_target, new_target])
    if not sets:
        return daily
    params.extend([member["id"], daily["date"]])
    db.execute(
        f"UPDATE daily SET {', '.join(sets)} WHERE member_id=? AND date=?",
        params,
        commit=True,
    )
    return db.fetchone(
        "SELECT * FROM daily WHERE member_id=? AND date=?",
        (member["id"], daily["date"]),
    )


def _track_columns(track: str) -> dict:
    if track == "korean":
        return {
            "id": "korean",
            "label": "韩语",
            "quiz_size": KO_QUIZ_SIZE,
            "review": "ko_review_target",
            "new": "ko_new_target",
            "due_json": "ko_reviewed_due_json",
            "new_json": "ko_new_introduced_json",
            "all_json": "ko_reviewed_all_json",
            "vocab": "ko_vocab_done",
            "quizzes": "ko_quizzes_done",
            "quiz_target": "ko_quiz_target",
        }
    return {
        "id": "cet4",
        "label": "四级英语",
        "quiz_size": 10,
        "review": "review_target",
        "new": "new_target",
        "due_json": "reviewed_due_json",
        "new_json": "new_introduced_json",
        "all_json": "reviewed_all_json",
        "vocab": "vocab_done",
        "quizzes": "quizzes_done",
        "quiz_target": "quiz_target",
    }


def _track_status(member: dict, daily: dict, track: str) -> dict:
    cols = _track_columns(track)
    review_target = daily[cols["review"]] or 0
    new_target = daily[cols["new"]] or 0
    reviewed_due = _loads(daily[cols["due_json"]], [])
    new_intro = _loads(daily[cols["new_json"]], [])
    due_done = min(len(reviewed_due), review_target)
    new_done = min(len(new_intro), new_target)
    due_left = max(0, review_target - due_done)
    new_left = max(0, new_target - new_done)
    due, fresh, _ = due_and_new(member, track)
    seen = set(reviewed_due)
    remaining_due = [w for w, _ in due if w["id"] not in seen][:due_left]
    remaining_new = fresh[:new_left]
    vocab_done = bool(daily[cols["vocab"]] or (due_left == 0 and new_left == 0))
    if review_target == 0 and new_target == 0:
        vocab_done = True
    quizzes_done = daily[cols["quizzes"]] or 0
    quiz_target = daily[cols["quiz_target"]] or 0
    quiz_done = quizzes_done >= quiz_target if quiz_target else True
    return {
        "id": cols["id"],
        "label": cols["label"],
        "dueTotal": review_target,
        "dueDone": due_done,
        "dueLeft": due_left,
        "newTotal": new_target,
        "newDone": new_done,
        "newLeft": new_left,
        "quizDone": quizzes_done,
        "quizTarget": quiz_target,
        "quizSize": cols["quiz_size"],
        "vocabDone": vocab_done,
        "quizComplete": quiz_done,
        "required": True,
        "remainingDue": remaining_due,
        "remainingNew": remaining_new,
    }


def punishment_text_for(member: dict) -> str:
    tracks = active_tracks(member)
    if tracks == ["cet4"]:
        return "今天需要先完成惩罚任务（额外 20 个单词 + 多做一组题），再加上平时的任务，才能打卡。"
    parts = []
    if "cet4" in tracks:
        parts.append(f"英语额外 {PUNISH_EXTRA_NEW} 个新词，并多做一组题")
    if "korean" in tracks:
        parts.append(f"韩语额外 {KO_PUNISH_EXTRA_NEW} 个新词，并多做一组小测")
    return "今天需要先完成惩罚任务（" + "；".join(parts) + "），再加上平时的任务，才能打卡。"


def requirement_text(tracks: list[dict], punishment: bool) -> str:
    bits = []
    for track in tracks:
        if track["id"] == "korean":
            bits.append(
                f"韩语：复习 {track['dueDone']}/{track['dueTotal']}，新词 {track['newDone']}/{track['newTotal']}，"
                f"小测 {track['quizDone']}/{track['quizTarget']} 组（每组 {track['quizSize']} 题）"
            )
        else:
            bits.append(
                f"四级英语：复习 {track['dueDone']}/{track['dueTotal']}，新词 {track['newDone']}/{track['newTotal']}，"
                f"做题 {track['quizDone']}/{track['quizTarget']} 组（每组 {track['quizSize']} 题）"
            )
    head = "昨天没打卡，今天的新词和题组里已经包含惩罚任务。" if punishment else ""
    if len(tracks) > 1:
        tail = "上面每一门都做完，今天才算打卡。韩语只计入韩语进度，不会算进英语任务。"
    elif tracks and tracks[0]["id"] == "korean":
        tail = "韩语的复习、新词和小测都做完，才算打卡。"
    else:
        tail = "英语的复习、新词和做题都完成，才算打卡。"
    return head + "打卡要求：" + "；".join(bits) + "。" + tail


def plan_for(member: dict) -> dict:
    daily = freeze_targets(member, ensure_daily(member))
    full_tracks = [_track_status(member, daily, track) for track in active_tracks(member)]
    public_tracks = [
        {k: v for k, v in track.items() if k not in ("remainingDue", "remainingNew")}
        for track in full_tracks
    ]
    vocab_done = all(track["vocabDone"] for track in full_tracks) if full_tracks else True
    quiz_done = all(track["quizComplete"] for track in full_tracks) if full_tracks else True

    def total(key: str) -> int:
        return sum(track[key] for track in full_tracks)

    return {
        "date": daily["date"],
        "studyPlan": normalize_plan(member.get("study_plan")),
        "studyPlanLabel": plan_label(member),
        "tracks": public_tracks,
        "requirementText": requirement_text(public_tracks, bool(daily["punishment"])),
        "dueTotal": total("dueTotal"),
        "dueDone": total("dueDone"),
        "dueLeft": total("dueLeft"),
        "newTotal": total("newTotal"),
        "newDone": total("newDone"),
        "newLeft": total("newLeft"),
        "quizDone": total("quizDone"),
        "quizTarget": total("quizTarget"),
        "vocabDone": vocab_done,
        "quizComplete": quiz_done,
        "punishment": bool(daily["punishment"]),
        "checkin": bool(daily["checkin"]),
        "canCheckin": bool(vocab_done and quiz_done and not daily["checkin"]),
        "memoryText": MEMORY_TEXT,
        "roundNeed": ROUND_NEED,
        "reviewCurve": list(REVIEW_CURVE),
        "_tracks": full_tracks,
        "daily": daily,
    }


def build_session(member: dict, track: str | None = None) -> list[dict]:
    plan = plan_for(member)
    tracks = plan.get("_tracks") or []
    if not tracks:
        return []
    if track:
        chosen = next((item for item in tracks if item["id"] == track), None)
        if not chosen:
            raise ValueError("当前学习计划里没有这一门")
    else:
        chosen = next((item for item in tracks if item["dueLeft"] or item["newLeft"]), tracks[0])
    progress = get_progress_map(member["id"])

    def pack(word: dict, kind: str, punishment: bool = False) -> dict:
        rec = progress.get(word["id"]) or {}
        item = {
            "word": wordbank.public_word(word),
            "kind": kind,
            "track": chosen["id"],
            "roundCorrect": int(rec.get("round_correct") or 0),
            "roundNeed": ROUND_NEED,
        }
        if punishment:
            item["punishment"] = True
        return item

    items = []
    for w in chosen["remainingDue"]:
        items.append(pack(w, "review"))
    for w in chosen["remainingNew"]:
        items.append(pack(w, "new", punishment=bool(plan["punishment"])))
    return items


def completed_round_update(interval_days: int, today: str | None = None) -> dict:
    """Schedule the next review after a round that has already reached the threshold."""
    today = today or today_str()
    interval = advance_interval(curve_interval(interval_days or 0))
    return {
        "interval_days": interval,
        "due_ts": start_of_day_ts(add_days(today, interval)),
        "status": "mastered" if interval >= 15 else "learning",
        "round_correct": 0,
    }


def _credit_passed_today(con, member_id: int, word_id: str, was_new: bool, today: str) -> None:
    """Count an already-passed word toward today's frozen quota so the day can still finish."""
    row = con.execute(
        "SELECT * FROM daily WHERE member_id=? AND date=?",
        (member_id, today),
    ).fetchone()
    if row is None:
        return
    daily = {k: row[k] for k in row.keys()}
    if daily.get("checkin"):
        return
    track = "korean" if str(word_id).startswith("ko_") else "cet4"
    cols = _track_columns(track)
    target_key = cols["new"] if was_new else cols["review"]
    if daily.get(target_key) is None:
        return
    list_key = cols["new_json"] if was_new else cols["due_json"]
    ids = _loads(daily.get(list_key), [])
    all_ids = _loads(daily.get(cols["all_json"]), [])
    changed = False
    if word_id not in ids:
        ids.append(word_id)
        changed = True
    if word_id not in all_ids:
        all_ids.append(word_id)
        changed = True
    if not changed:
        return
    con.execute(
        f"UPDATE daily SET {list_key}=?, {cols['all_json']}=? WHERE member_id=? AND date=?",
        (json.dumps(ids), json.dumps(all_ids), member_id, today),
    )


def apply_round_need_migration(con) -> None:
    """Pass words that already have 3 or 4 successful recalls from when the bar was 5.

    Uses the same completion as a passing round: one interval step, reps + 1,
    round progress cleared. 「不认识」and「模糊」are not loosened. Points already
    earned for those recalls stay as they are.
    """
    done = con.execute("SELECT value FROM app_meta WHERE key=?", (ROUND_NEED_META,)).fetchone()
    if done is not None:
        return
    today = today_str()
    now_ms = int(now().timestamp() * 1000)
    rows = con.execute(
        "SELECT * FROM word_progress WHERE round_correct >= ?",
        (ROUND_NEED,),
    ).fetchall()
    for row in rows:
        rec = {k: row[k] for k in row.keys()}
        reps = int(rec.get("reps") or 0)
        was_new = reps <= 0
        due_ts = int(rec.get("due_ts") or 0)
        was_due = (not was_new) and due_ts > 0 and due_ts <= now_ms
        settled = completed_round_update(rec.get("interval_days") or 0, today)
        con.execute(
            """UPDATE word_progress
               SET interval_days=?, due_ts=?, reps=reps+1, status=?, round_correct=0,
                   introduced_on=COALESCE(introduced_on, ?)
               WHERE member_id=? AND word_id=? AND round_correct >= ?""",
            (
                settled["interval_days"],
                settled["due_ts"],
                settled["status"],
                today,
                rec["member_id"],
                rec["word_id"],
                ROUND_NEED,
            ),
        )
        if was_new or was_due:
            _credit_passed_today(con, rec["member_id"], rec["word_id"], was_new, today)
    con.execute(
        "INSERT OR IGNORE INTO app_meta (key, value) VALUES (?, ?)",
        (ROUND_NEED_META, str(ROUND_NEED)),
    )
    con.commit()


def curve_interval(days: int) -> int:
    """Snap a stored interval onto the review curve without moving it forward."""
    days = int(days or 0)
    if days <= 0:
        return 0
    snapped = 0
    for step in REVIEW_CURVE:
        if step <= days:
            snapped = step
        else:
            break
    return snapped


def advance_interval(days: int) -> int:
    current = curve_interval(days)
    for step in REVIEW_CURVE:
        if step > current:
            return step
    return REVIEW_CURVE[-1]


def regress_interval(days: int) -> int:
    current = curve_interval(days)
    if current <= 0:
        return 0
    previous = REVIEW_CURVE[0]
    for step in REVIEW_CURVE:
        if step >= current:
            return previous if previous < current else REVIEW_CURVE[0]
        previous = step
    return REVIEW_CURVE[0]


def add_points(member: dict, daily: dict, amount: int) -> None:
    if not amount:
        return
    db.execute(
        "UPDATE members SET points_total=points_total+? WHERE id=?",
        (amount, member["id"]),
    )
    db.execute(
        "UPDATE daily SET points=points+? WHERE member_id=? AND date=?",
        (amount, member["id"], daily["date"]),
    )
    db.connect().commit()
    member["points_total"] = (member["points_total"] or 0) + amount
    daily["points"] = (daily["points"] or 0) + amount


def maybe_streak_bonuses(member: dict, daily: dict) -> list[dict]:
    bonuses = _loads(member["streak_bonuses"], {"3": False, "7": False, "14": False})
    extras = []
    for day, pts in STREAK_BONUS.items():
        key = str(day)
        if member["streak"] >= day and not bonuses.get(key):
            bonuses[key] = True
            add_points(member, daily, pts)
            extras.append({"day": day, "points": pts})
    if extras:
        db.execute(
            "UPDATE members SET streak_bonuses=? WHERE id=?",
            (json.dumps(bonuses, ensure_ascii=False), member["id"]),
            commit=True,
        )
        member["streak_bonuses"] = json.dumps(bonuses)
    return extras


def try_checkin(member: dict) -> dict:
    plan = plan_for(member)
    daily = plan["daily"]
    if daily["checkin"]:
        return {"ok": True, "already": True, "bonus": 0, "streakBonuses": [], "streak": member["streak"]}
    if not plan["vocabDone"] or not plan["quizComplete"]:
        return {"ok": False, "already": False, "error": plan.get("requirementText") or "还没完成今天的打卡任务"}
    today = today_str()
    yesterday = add_days(today, -1)
    last = member["last_checkin"]
    if last == yesterday:
        streak = (member["streak"] or 0) + 1
    else:
        streak = 1
    db.execute(
        """UPDATE members
           SET last_checkin=?, streak=?, missed_yesterday=0, punishment_pending=0
           WHERE id=?""",
        (today, streak, member["id"]),
        commit=True,
    )
    member["last_checkin"] = today
    member["streak"] = streak
    member["missed_yesterday"] = 0
    member["punishment_pending"] = 0
    add_points(member, daily, POINTS["checkin"])
    db.execute(
        "UPDATE daily SET checkin=1, vocab_done=1 WHERE member_id=? AND date=?",
        (member["id"], today),
        commit=True,
    )
    extras = maybe_streak_bonuses(member, daily)
    return {"ok": True, "already": False, "bonus": POINTS["checkin"], "streakBonuses": extras, "streak": streak}


def rate_word(member: dict, word_id: str, rating: str) -> dict:
    if rating not in ("again", "hard", "know"):
        raise ValueError("无效的评分")
    word = word_by_id(member["id"], word_id)
    if not word:
        raise ValueError("找不到这个单词")
    today = today_str()
    daily = freeze_targets(member, ensure_daily(member))
    rec = db.fetchone(
        "SELECT * FROM word_progress WHERE member_id=? AND word_id=?",
        (member["id"], word_id),
    )
    was_new = not rec or not rec["reps"]
    now_ms = int(now().timestamp() * 1000)
    if not rec:
        rec = {
            "member_id": member["id"],
            "word_id": word_id,
            "interval_days": 0,
            "due_ts": 0,
            "reps": 0,
            "lapses": 0,
            "status": "new",
            "last_rating": None,
            "last_reviewed": None,
            "introduced_on": None,
            "round_correct": 0,
        }
        db.execute(
            """INSERT INTO word_progress (member_id, word_id, interval_days, due_ts, reps, lapses, status, round_correct)
               VALUES (?, ?, 0, 0, 0, 0, 'new', 0)""",
            (member["id"], word_id),
            commit=True,
        )
    interval = curve_interval(rec["interval_days"] or 0)
    lapses = rec["lapses"] or 0
    due_ts = rec["due_ts"] or 0
    round_correct = int(rec.get("round_correct") or 0)
    on_curve = (rec.get("reps") or 0) > 0
    complete = False
    # Already at the pass line (including 3 or 4 left over from when the line was 5).
    # Do not let 「不认识」or「模糊」erase a round that has already been earned.
    if round_correct >= ROUND_NEED:
        rating = "know"
    if rating == "again":
        round_correct = 0
        lapses += 1
        if on_curve:
            interval = regress_interval(interval)
        status = "learning" if on_curve else "new"
    elif rating == "hard":
        round_correct = max(0, round_correct - 1)
        status = "learning" if on_curve else (rec.get("status") or "new")
    else:
        round_correct += 1
        status = "learning" if on_curve else (rec.get("status") or "new")
        if round_correct >= ROUND_NEED:
            complete = True
            interval = advance_interval(interval)
            due_ts = start_of_day_ts(add_days(today, interval))
            status = "mastered" if interval >= 15 else "learning"
            round_correct = 0
    introduced = rec["introduced_on"] or (today if was_new else rec["introduced_on"])
    db.execute(
        """UPDATE word_progress
           SET interval_days=?, due_ts=?, reps=reps+?, lapses=?, status=?, last_rating=?, last_reviewed=?, introduced_on=?, round_correct=?
           WHERE member_id=? AND word_id=?""",
        (
            interval,
            due_ts,
            1 if complete else 0,
            lapses,
            status,
            rating,
            now_ms,
            introduced,
            round_correct,
            member["id"],
            word_id,
        ),
        commit=True,
    )

    track = word_track(word, word_id)
    cols = _track_columns(track)
    # Only a finished round counts toward today's review or new-word quota.
    # Korean cards only move the Korean quota, and English cards only move English.
    if complete and track in active_tracks(member):
        due_ids = _loads(daily[cols["due_json"]], [])
        new_ids = _loads(daily[cols["new_json"]], [])
        all_ids = _loads(daily[cols["all_json"]], [])
        if was_new:
            if word_id not in new_ids:
                new_ids.append(word_id)
        else:
            if word_id not in due_ids:
                due_ids.append(word_id)
        if word_id not in all_ids:
            all_ids.append(word_id)
        db.execute(
            f"""UPDATE daily SET {cols['due_json']}=?, {cols['new_json']}=?, {cols['all_json']}=?
               WHERE member_id=? AND date=?""",
            (json.dumps(due_ids), json.dumps(new_ids), json.dumps(all_ids), member["id"], today),
            commit=True,
        )
        daily[cols["due_json"]] = json.dumps(due_ids)
        daily[cols["new_json"]] = json.dumps(new_ids)
        daily[cols["all_json"]] = json.dumps(all_ids)
    gained = POINTS[rating]
    add_points(member, daily, gained)

    plan = plan_for(member)
    track_state = next((item for item in plan["tracks"] if item["id"] == track), None)
    if track_state and track_state["vocabDone"] and not daily[cols["vocab"]]:
        db.execute(
            f"UPDATE daily SET {cols['vocab']}=1 WHERE member_id=? AND date=?",
            (member["id"], today),
            commit=True,
        )
    check = try_checkin(member) if plan["vocabDone"] and plan["quizComplete"] else {"ok": False, "bonus": 0, "streakBonuses": []}
    return {
        "gained": gained,
        "wasNew": was_new,
        "status": status,
        "interval": interval,
        "roundCorrect": ROUND_NEED if complete else round_correct,
        "roundNeed": ROUND_NEED,
        "roundComplete": complete,
        "checkin": check,
        "plan": {k: v for k, v in plan_for(member).items() if k not in ("_tracks", "daily")},
    }


def complete_vocab_session(member: dict, track: str | None = None) -> dict:
    plan = plan_for(member)
    today = today_str()
    for item in plan["tracks"]:
        if track and item["id"] != track:
            continue
        if item["dueLeft"] == 0 and item["newLeft"] == 0:
            col = _track_columns(item["id"])["vocab"]
            db.execute(
                f"UPDATE daily SET {col}=1 WHERE member_id=? AND date=?",
                (member["id"], today),
                commit=True,
            )
    check = try_checkin(member)
    fresh = plan_for(member)
    return {"plan": {k: v for k, v in fresh.items() if k not in ("_tracks", "daily")}, "checkin": check}


def _quiz_track(track: str | None, answers: list[dict]) -> str:
    if track in ("cet4", "korean"):
        return track
    for answer in answers:
        qid = str(answer.get("id") or "")
        if qid.startswith(("ko2zh", "zh2ko", "kocloze")):
            return "korean"
    return "cet4"


def submit_quiz(member: dict, answers: list[dict], mode: str = "normal", track: str | None = None) -> dict:
    daily = freeze_targets(member, ensure_daily(member))
    today = today_str()
    track = _quiz_track(track, answers)
    stats = ensure_quiz_stats(member["id"])
    wrong = _loads(stats["wrong_book_json"], {})
    recent = _loads(stats["recent_json"], [])
    correct_n = 0
    points = 0
    rewards = []
    for a in answers:
        qid = a.get("id")
        ok = bool(a.get("correct"))
        snap = a.get("snapshot") or {}
        if ok:
            correct_n += 1
            gained = QUIZ_CORRECT_POINTS
            points += gained
            rewards.append({"id": qid, "points": gained})
            if qid in wrong:
                wrong[qid]["correctStreak"] = (wrong[qid].get("correctStreak") or 0) + 1
                if wrong[qid]["correctStreak"] >= 2:
                    del wrong[qid]
        else:
            prev = wrong.get(qid) or {"misses": 0, "correctStreak": 0}
            wrong[qid] = {
                "id": qid,
                "misses": (prev.get("misses") or 0) + 1,
                "correctStreak": 0,
                "lastWrong": int(now().timestamp() * 1000),
                "snapshot": snap,
            }
        if qid:
            recent.append(qid)
    recent = recent[-80:]
    db.execute(
        """UPDATE quiz_stats
           SET taken=taken+1, correct=correct+?, answered=answered+?, recent_json=?, wrong_book_json=?
           WHERE member_id=?""",
        (
            correct_n,
            len(answers),
            json.dumps(recent),
            json.dumps(wrong, ensure_ascii=False),
            member["id"],
        ),
        commit=True,
    )
    add_points(member, daily, points)
    if track in active_tracks(member):
        col = _track_columns(track)["quizzes"]
        db.execute(
            f"UPDATE daily SET {col}={col}+1 WHERE member_id=? AND date=?",
            (member["id"], today),
            commit=True,
        )
    check = try_checkin(member)
    fresh = plan_for(member)
    return {
        "correct": correct_n,
        "total": len(answers),
        "gained": points,
        "rewardPoints": QUIZ_CORRECT_POINTS,
        "rewards": rewards,
        "track": track,
        "checkin": check,
        "plan": {k: v for k, v in fresh.items() if k not in ("_tracks", "daily")},
        "wrongCount": len(wrong),
    }


def wrong_book_questions(member: dict, n: int = 10) -> list[dict]:
    stats = ensure_quiz_stats(member["id"])
    wrong = _loads(stats["wrong_book_json"], {})
    items = []
    for rec in sorted(wrong.values(), key=lambda x: x.get("lastWrong") or 0, reverse=True):
        snap = rec.get("snapshot")
        if snap and snap.get("choices"):
            items.append(wordbank.enrich_question_speech(snap, custom_words(member["id"])))
    return items[:n]


def week_history(member_id: int) -> list[dict]:
    today = today_str()
    days = []
    for i in range(6, -1, -1):
        date = add_days(today, -i)
        row = db.fetchone(
            "SELECT checkin FROM daily WHERE member_id=? AND date=?",
            (member_id, date),
        )
        # also consider last_checkin if daily missing
        dt = datetime.strptime(date, "%Y-%m-%d")
        label = "一二三四五六日"[dt.weekday()]
        days.append(
            {
                "date": date,
                "studied": bool(row and row["checkin"]),
                "isToday": date == today,
                "label": label,
            }
        )
    return days


def stats_for(member: dict) -> dict:
    progress = get_progress_map(member["id"])
    started = sum(1 for r in progress.values() if r.get("reps"))
    mastered = sum(
        1
        for r in progress.values()
        if r.get("reps") and (r.get("status") == "mastered" or (r.get("interval_days") or 0) >= 15)
    )
    q = ensure_quiz_stats(member["id"])
    answered = q["answered"] or 0
    accuracy = round(q["correct"] * 100 / answered) if answered else None
    total = member["points_total"] or 0
    level = total // 100 + 1
    into = total % 100
    to_next = 100 if (into == 0 and total > 0) else (100 - into)
    into_bar = 0 if (into == 0 and total > 0) else into
    today = today_str()
    daily = db.fetchone(
        "SELECT * FROM daily WHERE member_id=? AND date=?",
        (member["id"], today),
    )
    wrong = _loads(q["wrong_book_json"], {})
    return {
        "started": started,
        "mastered": mastered,
        "quizzes": q["taken"] or 0,
        "accuracy": accuracy,
        "todayPoints": (daily["points"] if daily else 0) or 0,
        "totalPoints": total,
        "level": level,
        "toNext": to_next,
        "intoBar": into_bar,
        "streak": member["streak"] or 0,
        "wrongCount": len(wrong),
    }


def member_public(member: dict, include_plan: bool = False) -> dict:
    st = stats_for(member)
    today = today_str()
    daily = db.fetchone(
        "SELECT * FROM daily WHERE member_id=? AND date=?",
        (member["id"], today),
    )
    checked = bool(daily and daily["checkin"])
    out = {
        "id": member["id"],
        "name": member["name"],
        "points": st["totalPoints"],
        "level": st["level"],
        "streak": st["streak"],
        "checkinToday": checked,
        "missedYesterday": bool(member.get("missed_yesterday")),
        "punishmentPending": bool(member.get("punishment_pending")) and not checked,
        "week": week_history(member["id"]),
        "stats": st,
        "settings": {"dailyNew": member["daily_new"], "reviewCap": member["review_cap"]},
        "studyPlan": normalize_plan(member.get("study_plan")),
        "studyPlanLabel": plan_label(member),
        "joinedDate": member["joined_date"],
    }
    if include_plan:
        plan = plan_for(member)
        out["plan"] = {k: v for k, v in plan.items() if k not in ("remainingDue", "remainingNew", "daily", "_tracks")}
    return out


def room_state(member: dict) -> dict:
    process_misses(member["room_id"])
    # reload after miss processing
    member = db.fetchone("SELECT * FROM members WHERE id=?", (member["id"],))
    room = get_room(member["room_id"])
    people = room_members(member["room_id"])
    me = next(p for p in people if p["id"] == member["id"])
    partner = next((p for p in people if p["id"] != member["id"]), None)
    me_pub = member_public(me, include_plan=True)
    partner_pub = member_public(partner, include_plan=False) if partner else None
    banners = []
    if partner_pub and partner_pub["missedYesterday"]:
        banners.append(
            {
                "type": "partner-missed",
                "title": f"{partner_pub['name']}昨天没打卡了，按约定去催一下！",
                "text": room["punishment_text"],
            }
        )
    if me_pub["missedYesterday"] and not me_pub["checkinToday"]:
        banners.append(
            {
                "type": "self-missed",
                "title": "你昨天没打卡",
                "text": punishment_text_for(me),
            }
        )
    return {
        "today": today_str(),
        "greeting": greeting(),
        "dateLabel": format_cn_date(),
        "room": {
            "code": room["code"],
            "punishmentText": room["punishment_text"],
            "friendPlaceholder": room["friend_placeholder"],
        },
        "me": me_pub,
        "partner": partner_pub,
        "banners": banners,
        "wordCount": wordbank.word_count(),
        "koreanCount": wordbank.korean_count(),
        "grammarCount": wordbank.grammar_count(),
    }


def create_room(name: str, friend_placeholder: str | None, punishment_text: str | None, study_plan: str | None = None) -> dict:
    name = (name or "").strip()
    if not name or len(name) > 16:
        raise ValueError("请填写 1–16 个字的昵称")
    text = (punishment_text or "").strip() or DEFAULT_PUNISHMENT
    if len(text) > 200:
        raise ValueError("惩罚约定请控制在 200 字以内")
    placeholder = (friend_placeholder or "").strip() or None
    if placeholder and len(placeholder) > 16:
        raise ValueError("朋友的名字请控制在 16 个字以内")
    today = today_str()
    code = new_code()
    token = new_token()
    ts = now().isoformat(timespec="seconds")
    cur = db.execute(
        "INSERT INTO rooms (code, punishment_text, friend_placeholder, created_at) VALUES (?, ?, ?, ?)",
        (code, text, placeholder, ts),
        commit=True,
    )
    room_id = cur.lastrowid
    cur = db.execute(
        """INSERT INTO members (room_id, name, token, joined_date, created_at, study_plan)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (room_id, name, token, today, ts, normalize_plan(study_plan)),
        commit=True,
    )
    db.execute("INSERT INTO quiz_stats (member_id) VALUES (?)", (cur.lastrowid,), commit=True)
    member = db.fetchone("SELECT * FROM members WHERE token=?", (token,))
    return {"token": token, "state": room_state(member)}


def join_room(code: str, name: str, study_plan: str | None = None) -> dict:
    name = (name or "").strip()
    code = (code or "").strip().upper()
    if not name or len(name) > 16:
        raise ValueError("请填写 1–16 个字的昵称")
    if len(code) != 6:
        raise ValueError("邀请码应是 6 位")
    room = db.fetchone("SELECT * FROM rooms WHERE code=?", (code,))
    if not room:
        raise ValueError("找不到这个邀请码，请检查后再试")
    people = room_members(room["id"])
    existing = next((p for p in people if p["name"] == name), None)
    token = new_token()
    today = today_str()
    ts = now().isoformat(timespec="seconds")
    if existing:
        # Reclaim this name in the room (same person, new browser).
        db.execute("UPDATE members SET token=? WHERE id=?", (token, existing["id"]), commit=True)
        member = db.fetchone("SELECT * FROM members WHERE id=?", (existing["id"],))
        return {"token": token, "state": room_state(member), "reclaimed": True}
    if len(people) >= 2:
        raise ValueError("这个房间已经有两个人了。如果是你本人，请填写当时用的同一个昵称。")
    cur = db.execute(
        """INSERT INTO members (room_id, name, token, joined_date, created_at, study_plan)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (room["id"], name, token, today, ts, normalize_plan(study_plan)),
        commit=True,
    )
    db.execute("INSERT INTO quiz_stats (member_id) VALUES (?)", (cur.lastrowid,), commit=True)
    member = db.fetchone("SELECT * FROM members WHERE token=?", (token,))
    return {"token": token, "state": room_state(member), "reclaimed": False}


def _retarget_today(member: dict) -> None:
    """Recompute today's quota only for a track that has not been started."""
    today = today_str()
    daily = db.fetchone("SELECT * FROM daily WHERE member_id=? AND date=?", (member["id"], today))
    if not daily or daily["checkin"]:
        return
    tracks = active_tracks(member)
    punish = 1 if daily["punishment"] else 0
    sets: list[str] = []
    params: list = []
    if "cet4" in tracks:
        if not _loads(daily["reviewed_all_json"], []) and not (daily["quizzes_done"] or 0):
            sets.extend(["review_target=NULL", "new_target=NULL", "quiz_target=?"])
            params.append(_quiz_target_for("cet4", punish))
    elif not (daily["quizzes_done"] or 0):
        sets.append("quiz_target=?")
        params.append(0)
    if "korean" in tracks:
        started = _loads(daily.get("ko_reviewed_all_json") or "[]", []) or (daily.get("ko_quizzes_done") or 0)
        if not started:
            sets.extend(["ko_review_target=NULL", "ko_new_target=NULL", "ko_quiz_target=?"])
            params.append(_quiz_target_for("korean", punish))
    elif not (daily.get("ko_quizzes_done") or 0):
        sets.append("ko_quiz_target=?")
        params.append(0)
    if not sets:
        return
    params.extend([member["id"], today])
    db.execute(
        f"UPDATE daily SET {', '.join(sets)} WHERE member_id=? AND date=?",
        params,
        commit=True,
    )


def update_settings(member: dict, data: dict) -> dict:
    fields = []
    params = []
    if "name" in data and data["name"] is not None:
        name = str(data["name"]).strip()
        if not name or len(name) > 16:
            raise ValueError("昵称请控制在 1–16 个字")
        # unique in room
        clash = db.fetchone(
            "SELECT id FROM members WHERE room_id=? AND name=? AND id!=?",
            (member["room_id"], name, member["id"]),
        )
        if clash:
            raise ValueError("房间里已经有人用这个昵称了")
        fields.append("name=?")
        params.append(name)
    if "dailyNew" in data and data["dailyNew"] is not None:
        n = int(data["dailyNew"])
        n = min(40, max(5, n))
        fields.append("daily_new=?")
        params.append(n)
    if "reviewCap" in data and data["reviewCap"] is not None:
        n = int(data["reviewCap"])
        n = min(80, max(5, n))
        fields.append("review_cap=?")
        params.append(n)
    plan_changed = False
    if data.get("studyPlan") is not None:
        raw = str(data["studyPlan"]).strip().lower()
        if raw not in {"cet4", "korean", "both"}:
            raise ValueError("请选择四级英语、韩语入门，或两门一起学")
        fields.append("study_plan=?")
        params.append(raw)
        plan_changed = True
    if fields:
        params.append(member["id"])
        db.execute(f"UPDATE members SET {', '.join(fields)} WHERE id=?", params, commit=True)
        member = db.fetchone("SELECT * FROM members WHERE id=?", (member["id"],))
        if plan_changed or data.get("dailyNew") is not None or data.get("reviewCap") is not None:
            _retarget_today(member)
    if "punishmentText" in data and data["punishmentText"] is not None:
        text = str(data["punishmentText"]).strip() or DEFAULT_PUNISHMENT
        if len(text) > 200:
            raise ValueError("惩罚约定请控制在 200 字以内")
        db.execute("UPDATE rooms SET punishment_text=? WHERE id=?", (text, member["room_id"]), commit=True)
    member = db.fetchone("SELECT * FROM members WHERE id=?", (member["id"],))
    return room_state(member)


def list_words(member: dict, q: str, status: str, page: int, page_size: int, lang: str = "") -> dict:
    progress = get_progress_map(member["id"])
    tracks = active_tracks(member)
    wanted = (lang or "").strip().lower()
    if wanted in {"ko", "korean"}:
        allw = words_for_track(member["id"], "korean") if "korean" in tracks else []
    elif wanted in {"en", "cet4", "english"}:
        allw = words_for_track(member["id"], "cet4") if "cet4" in tracks else []
    else:
        allw = []
        for track in tracks:
            allw.extend(words_for_track(member["id"], track))
    q = (q or "").strip().lower()
    items = []
    for w in allw:
        rec = progress.get(w["id"])
        st = status_of(rec)
        if status and status != "全部" and st != status:
            continue
        if q:
            blob = " ".join([
                w["word"],
                w.get("meaning") or "",
                w.get("ipa") or "",
                w.get("reading") or "",
            ]).lower()
            if q not in blob:
                continue
        items.append(
            {
                **wordbank.public_word(w),
                "status": st,
            }
        )
    total = len(items)
    page = max(1, int(page or 1))
    page_size = min(100, max(10, int(page_size or 40)))
    start = (page - 1) * page_size
    return {"total": total, "page": page, "pageSize": page_size, "items": items[start : start + page_size]}


def add_custom_word(member: dict, data: dict) -> dict:
    word = (data.get("word") or "").strip()
    meaning = (data.get("meaning") or "").strip()
    if not word or not meaning:
        raise ValueError("请填写英文单词和中文意思")
    allw = all_member_words(member["id"])
    if any(w["word"].lower() == word.lower() for w in allw):
        raise ValueError("词库里已经有这个单词了")
    wid = "c_" + secrets.token_hex(5)
    db.execute(
        """INSERT INTO custom_words (id, member_id, word, ipa, meaning, example, example_zh, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            wid,
            member["id"],
            word,
            (data.get("ipa") or "").strip(),
            meaning,
            (data.get("example") or "").strip(),
            (data.get("exampleZh") or data.get("example_zh") or "").strip(),
            now().isoformat(timespec="seconds"),
        ),
        commit=True,
    )
    return {"ok": True, "word": word_by_id(member["id"], wid)}


def update_custom_word(member: dict, word_id: str, data: dict) -> dict:
    row = db.fetchone(
        "SELECT * FROM custom_words WHERE id=? AND member_id=?",
        (word_id, member["id"]),
    )
    if not row:
        raise ValueError("找不到这个自定义单词")
    word = (data.get("word") or "").strip()
    meaning = (data.get("meaning") or "").strip()
    if not word or not meaning:
        raise ValueError("请填写英文单词和中文意思")
    clash = next(
        (w for w in all_member_words(member["id"]) if w["id"] != word_id and w["word"].lower() == word.lower()),
        None,
    )
    if clash:
        raise ValueError("词库里已经有这个单词了")
    db.execute(
        """UPDATE custom_words SET word=?, ipa=?, meaning=?, example=?, example_zh=?
           WHERE id=? AND member_id=?""",
        (
            word,
            (data.get("ipa") or "").strip(),
            meaning,
            (data.get("example") or "").strip(),
            (data.get("exampleZh") or data.get("example_zh") or "").strip(),
            word_id,
            member["id"],
        ),
        commit=True,
    )
    return {"ok": True, "word": word_by_id(member["id"], word_id)}


def delete_custom_word(member: dict, word_id: str) -> dict:
    db.execute(
        "DELETE FROM custom_words WHERE id=? AND member_id=?",
        (word_id, member["id"]),
        commit=True,
    )
    db.execute(
        "DELETE FROM word_progress WHERE member_id=? AND word_id=?",
        (member["id"], word_id),
        commit=True,
    )
    return {"ok": True}


def export_member(member: dict) -> dict:
    progress = db.fetchall("SELECT * FROM word_progress WHERE member_id=?", (member["id"],))
    customs = db.fetchall("SELECT * FROM custom_words WHERE member_id=?", (member["id"],))
    daily = db.fetchall("SELECT * FROM daily WHERE member_id=?", (member["id"],))
    quiz = ensure_quiz_stats(member["id"])
    return {
        "app": "请叫我学习",
        "exportedAt": now().isoformat(timespec="seconds"),
        "member": {
            "name": member["name"],
            "token": member["token"],
            "studyPlan": normalize_plan(member.get("study_plan")),
            "dailyNew": member["daily_new"],
            "reviewCap": member["review_cap"],
            "pointsTotal": member["points_total"],
            "streak": member["streak"],
            "lastCheckin": member["last_checkin"],
            "streakBonuses": member["streak_bonuses"],
        },
        "room": {"code": get_room(member["room_id"])["code"]},
        "progress": progress,
        "customWords": customs,
        "daily": daily,
        "quiz": quiz,
    }


def import_member(member: dict, payload: dict) -> dict:
    data = payload.get("data") if isinstance(payload, dict) and "data" in payload else payload
    if not isinstance(data, dict) or "member" not in data:
        raise ValueError("文件内容不像是「请叫我学习」的备份")
    mid = member["id"]
    # Replace this member's study data, keep identity/room.
    m = data["member"]
    db.execute(
        """UPDATE members SET daily_new=?, review_cap=?, points_total=?, streak=?, last_checkin=?, streak_bonuses=?
           WHERE id=?""",
        (
            int(m.get("dailyNew") or member["daily_new"]),
            int(m.get("reviewCap") or member["review_cap"]),
            int(m.get("pointsTotal") or 0),
            int(m.get("streak") or 0),
            m.get("lastCheckin"),
            m.get("streakBonuses") or member["streak_bonuses"],
            mid,
        ),
    )
    imported_plan = m.get("studyPlan") or m.get("study_plan")
    if imported_plan:
        db.execute(
            "UPDATE members SET study_plan=? WHERE id=?",
            (normalize_plan(str(imported_plan)), mid),
        )
    db.execute("DELETE FROM word_progress WHERE member_id=?", (mid,))
    db.execute("DELETE FROM custom_words WHERE member_id=?", (mid,))
    db.execute("DELETE FROM daily WHERE member_id=?", (mid,))
    today = today_str()
    for rec in data.get("progress") or []:
        interval = curve_interval(rec.get("interval_days") or 0)
        due_ts = rec.get("due_ts") or 0
        reps = int(rec.get("reps") or 0)
        status = rec.get("status") or "learning"
        round_correct = int(rec.get("round_correct") or 0)
        if round_correct >= ROUND_NEED:
            settled = completed_round_update(interval, today)
            interval = settled["interval_days"]
            due_ts = settled["due_ts"]
            status = settled["status"]
            round_correct = 0
            reps += 1
        db.execute(
            """INSERT INTO word_progress (member_id, word_id, interval_days, due_ts, reps, lapses, status, last_rating, last_reviewed, introduced_on, round_correct)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                mid,
                rec["word_id"],
                interval,
                due_ts,
                reps,
                rec.get("lapses") or 0,
                status,
                rec.get("last_rating"),
                rec.get("last_reviewed"),
                rec.get("introduced_on"),
                round_correct,
            ),
        )
    for rec in data.get("customWords") or []:
        db.execute(
            """INSERT OR REPLACE INTO custom_words (id, member_id, word, ipa, meaning, example, example_zh, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                rec["id"] if str(rec.get("id", "")).startswith("c_") else "c_" + secrets.token_hex(5),
                mid,
                rec["word"],
                rec.get("ipa") or "",
                rec["meaning"],
                rec.get("example") or "",
                rec.get("example_zh") or rec.get("exampleZh") or "",
                rec.get("created_at") or now().isoformat(timespec="seconds"),
            ),
        )
    for rec in data.get("daily") or []:
        db.execute(
            """INSERT OR REPLACE INTO daily (
                 member_id, date, review_target, new_target, quiz_target, reviewed_due_json,
                 new_introduced_json, reviewed_all_json, vocab_done, quizzes_done, checkin, punishment, points,
                 ko_review_target, ko_new_target, ko_quiz_target, ko_reviewed_due_json, ko_new_introduced_json,
                 ko_reviewed_all_json, ko_vocab_done, ko_quizzes_done)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                mid,
                rec["date"],
                rec.get("review_target"),
                rec.get("new_target"),
                rec.get("quiz_target") if rec.get("quiz_target") is not None else 1,
                rec.get("reviewed_due_json") or "[]",
                rec.get("new_introduced_json") or "[]",
                rec.get("reviewed_all_json") or "[]",
                rec.get("vocab_done") or 0,
                rec.get("quizzes_done") or 0,
                rec.get("checkin") or 0,
                rec.get("punishment") or 0,
                rec.get("points") or 0,
                rec.get("ko_review_target"),
                rec.get("ko_new_target"),
                rec.get("ko_quiz_target") or 0,
                rec.get("ko_reviewed_due_json") or "[]",
                rec.get("ko_new_introduced_json") or "[]",
                rec.get("ko_reviewed_all_json") or "[]",
                rec.get("ko_vocab_done") or 0,
                rec.get("ko_quizzes_done") or 0,
            ),
        )
    quiz = data.get("quiz") or {}
    db.execute(
        """INSERT OR REPLACE INTO quiz_stats (member_id, taken, correct, answered, recent_json, wrong_book_json)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            mid,
            quiz.get("taken") or 0,
            quiz.get("correct") or 0,
            quiz.get("answered") or 0,
            quiz.get("recent_json") or "[]",
            quiz.get("wrong_book_json") or "{}",
        ),
    )
    db.connect().commit()
    return room_state(db.fetchone("SELECT * FROM members WHERE id=?", (mid,)))


def reset_member(member: dict) -> dict:
    mid = member["id"]
    db.execute("DELETE FROM word_progress WHERE member_id=?", (mid,))
    db.execute("DELETE FROM custom_words WHERE member_id=?", (mid,))
    db.execute("DELETE FROM daily WHERE member_id=?", (mid,))
    db.execute(
        "UPDATE quiz_stats SET taken=0, correct=0, answered=0, recent_json='[]', wrong_book_json='{}' WHERE member_id=?",
        (mid,),
    )
    db.execute(
        """UPDATE members
           SET points_total=0, streak=0, last_checkin=NULL,
               streak_bonuses='{"3":false,"7":false,"14":false}',
               punishment_pending=0, missed_yesterday=0, miss_processed_on=NULL
           WHERE id=?""",
        (mid,),
        commit=True,
    )
    return room_state(db.fetchone("SELECT * FROM members WHERE id=?", (mid,)))


def start_quiz(member: dict, mode: str, track: str = "cet4") -> list[dict]:
    stats = ensure_quiz_stats(member["id"])
    track = track if track in ("cet4", "korean") else "cet4"
    if mode == "wrong":
        qs = wrong_book_questions(member, 10 if track != "korean" else KO_QUIZ_SIZE)
        if not qs:
            raise ValueError("错题本是空的")
        return qs
    if track not in active_tracks(member):
        raise ValueError("当前学习计划里没有这一门")
    recent = _loads(stats["recent_json"], [])
    if track == "korean":
        return wordbank.build_korean_quiz(KO_QUIZ_SIZE, recent_ids=recent)
    extras = custom_words(member["id"])
    return wordbank.build_quiz(10, recent_ids=recent, extra_words=extras)
