"""Load the CET-4 and beginner Korean word banks; build quizzes."""
from __future__ import annotations

import json
import random
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

_WORDS: list[dict] = []
_BY_ID: dict[str, dict] = {}
_KO_WORDS: list[dict] = []
_KO_BY_ID: dict[str, dict] = {}
_GRAMMAR: list[dict] = []

_POS_MARK = re.compile(
    r"(vt\.&vi\.|vi\.&vt\.|vt\.&n\.|n\.&vt\.|n\.&vi\.|vi\.&n\.|aux\.v\.|v\.aux\.|"
    r"vt\.|vi\.|n\.|a\.|ad\.|adj\.|adv\.|prep\.|conj\.|pron\.|num\.|art\.|int\.|aux\.|v\.)"
)


def _gloss(meaning: str) -> str:
    text = _POS_MARK.sub("|", meaning or "")
    parts = [p.strip(" ；;，,。.") for p in text.split("|")]
    parts = [p for p in parts if p]
    gloss = parts[0] if parts else "这个词"
    gloss = re.split(r"[；;，,]", gloss)[0]
    gloss = re.sub(r"[（(].*?[）)]", "", gloss).strip()
    gloss = gloss.strip("的") or "这个词"
    return gloss[:12]


def _pos(meaning: str) -> str:
    m = (meaning or "").strip()
    if m.startswith(("vt", "vi", "v.", "aux")):
        return "v"
    if m.startswith(("a.", "adj")):
        return "a"
    if m.startswith(("ad.", "adv")):
        return "ad"
    if m.startswith("n."):
        return "n"
    return "x"


def _fallback_example(word: str, meaning: str) -> tuple[str, str]:
    """A short original sentence when the CET-4 bank has no example."""
    w = (word or "").strip()
    g = _gloss(meaning)
    kind = _pos(meaning)
    if not w:
        return "We study a new word today.", "我们今天学习一个新词。"
    if kind == "v":
        return f"Students {w} it step by step.", f"学生们一步一步地{g}。"
    if kind == "a":
        return f"The result is {w}.", f"这个结果是{g}的。"
    if kind == "ad":
        return f"She answered {w}.", f"她{g}地回答了。"
    if kind == "n":
        article = "an" if w[:1].lower() in "aeiou" else "a"
        return f"This is {article} {w}.", f"这是一个{g}。"
    return f"We often use {w} in daily English.", f"我们在日常英语里经常用到 {w}（{g}）。"


def load() -> None:
    global _WORDS, _BY_ID, _KO_WORDS, _KO_BY_ID, _GRAMMAR
    _WORDS = json.loads((DATA_DIR / "cet4_words.json").read_text(encoding="utf-8"))
    for w in _WORDS:
        w["lang"] = "en"
        if not (w.get("example") or "").strip():
            en, zh = _fallback_example(w.get("word") or "", w.get("meaning") or "")
            w["example"] = en
            w["exampleZh"] = zh
    _BY_ID = {w["id"]: w for w in _WORDS}
    _KO_WORDS = json.loads((DATA_DIR / "korean_words.json").read_text(encoding="utf-8"))
    for w in _KO_WORDS:
        w["lang"] = "ko"
    _KO_BY_ID = {w["id"]: w for w in _KO_WORDS}
    _GRAMMAR = json.loads((DATA_DIR / "grammar.json").read_text(encoding="utf-8"))


def all_words() -> list[dict]:
    return _WORDS


def word_count() -> int:
    return len(_WORDS)


def grammar_count() -> int:
    return len(_GRAMMAR)


def get_word(word_id: str) -> dict | None:
    return _BY_ID.get(word_id)


def korean_words() -> list[dict]:
    return _KO_WORDS


def korean_count() -> int:
    return len(_KO_WORDS)


def get_korean(word_id: str) -> dict | None:
    return _KO_BY_ID.get(word_id)


def public_word(w: dict) -> dict:
    lang = w.get("lang") or ("ko" if str(w.get("id") or "").startswith("ko_") else "en")
    return {
        "id": w["id"],
        "word": w["word"],
        "lang": lang,
        "ipa": w.get("ipa") or "",
        "reading": w.get("reading") or (w["word"] if lang == "ko" else ""),
        "meaning": w.get("meaning") or "",
        "example": w.get("example") or "",
        "exampleZh": w.get("exampleZh") or w.get("example_zh") or "",
        "custom": bool(w.get("custom")),
    }


def _blank_example(word: str, example: str) -> str | None:
    if not example:
        return None
    pat = re.compile(r"\b" + re.escape(word) + r"\b", re.I)
    if not pat.search(example):
        return None
    return pat.sub("_____", example, count=1)


def _distractors(pool: list[dict], correct: dict, field: str, k: int = 3) -> list[str]:
    correct_val = (correct.get(field) or "").strip()
    seen = {correct_val}
    candidates = []
    for w in pool:
        if w["id"] == correct["id"]:
            continue
        val = (w.get(field) or "").strip()
        if not val or val in seen:
            continue
        seen.add(val)
        candidates.append(val)
    random.shuffle(candidates)
    return candidates[:k]


def _pack(qid: str, typ: str, prompt: str, note: str, choices: list[str], answer: int, explain: str) -> dict:
    return {
        "id": qid,
        "type": typ,
        "prompt": prompt,
        "promptNote": note,
        "choices": choices,
        "answer": answer,
        "explain": explain,
    }


_VOCAB_TYPES = {"en2zh", "zh2en", "cloze", "ko2zh", "zh2ko", "kocloze"}
_WORD_CHOICE_TYPES = {"zh2en", "cloze", "zh2ko", "kocloze"}


def speak_payload(word: dict | None, fallback: str = "", lang: str | None = None) -> dict | None:
    """Pronunciation the quiz can show and play. English uses IPA; Korean uses Hangul plus revised romanization."""
    if word is not None:
        lang = "ko" if (word.get("lang") == "ko" or str(word.get("id") or "").startswith("ko_")) else "en"
        text = (word.get("word") or fallback or "").strip()
        if not text:
            return None
        reading = (word.get("reading") or "").strip()
        if lang == "ko" and not reading:
            reading = text
        return {
            "word": text,
            "lang": lang,
            "ipa": (word.get("ipa") or "").strip(),
            "reading": reading,
        }
    text = (fallback or "").strip()
    if not text:
        return None
    language = "ko" if lang == "ko" else "en"
    return {
        "word": text,
        "lang": language,
        "ipa": "",
        "reading": text if language == "ko" else "",
    }


def _surface_index(pool: list[dict]) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for item in pool:
        key = (item.get("word") or "").strip()
        if key and key not in index:
            index[key] = item
    return index


def _question_word_id(q: dict) -> str:
    parts = str(q.get("id") or "").split(":")
    if len(parts) >= 2 and parts[0] in _VOCAB_TYPES:
        return parts[1]
    return ""


def _lookup_word(word_id: str, extra_words: list[dict] | None) -> dict | None:
    if not word_id:
        return None
    for item in extra_words or []:
        if item.get("id") == word_id:
            found = dict(item)
            found.setdefault("lang", "ko" if word_id.startswith("ko_") else "en")
            return found
    if word_id.startswith("ko_"):
        return get_korean(word_id)
    return get_word(word_id)


def _speech_pool(word: dict | None, extra_words: list[dict] | None, typ: str) -> list[dict]:
    korean = typ in {"ko2zh", "zh2ko", "kocloze"} or (
        word is not None and (word.get("lang") == "ko" or str(word.get("id") or "").startswith("ko_"))
    )
    if korean:
        return list(_KO_WORDS)
    extras = []
    for item in extra_words or []:
        found = dict(item)
        found.setdefault("lang", "en")
        extras.append(found)
    return extras + list(_WORDS)


def _fallback_speak(q: dict) -> dict | None:
    typ = q.get("type") or ""
    choices = q.get("choices") or []
    answer = q.get("answer")
    if typ == "en2zh":
        return speak_payload(None, str(q.get("prompt") or ""), "en")
    if typ == "ko2zh":
        return speak_payload(None, str(q.get("prompt") or ""), "ko")
    if typ in _WORD_CHOICE_TYPES and isinstance(answer, int) and 0 <= answer < len(choices):
        lang = "ko" if typ in {"zh2ko", "kocloze"} else "en"
        return speak_payload(None, str(choices[answer]), lang)
    return None


def _with_speech(q: dict, word: dict, pool: list[dict], choices_are_words: bool) -> dict:
    speak = speak_payload(word)
    if not speak:
        return q
    q["speak"] = speak
    if not choices_are_words:
        return q
    index = _surface_index(pool)
    answer = q.get("answer")
    items = []
    for i, choice in enumerate(q.get("choices") or []):
        if i == answer:
            items.append(speak)
            continue
        hit = index.get(str(choice).strip())
        items.append(speak_payload(hit, fallback=str(choice), lang=speak["lang"]))
    q["choiceSpeak"] = items
    return q


def enrich_question_speech(q: dict, extra_words: list[dict] | None = None) -> dict:
    """Attach IPA / romanization so every vocabulary question can be read aloud.

    Grammar items are left unchanged. Existing wrong-book snapshots are filled in
    from the word id stored in the question id.
    """
    if not isinstance(q, dict):
        return q
    out = dict(q)
    typ = out.get("type") or ""
    if typ not in _VOCAB_TYPES:
        return out
    if out.get("speak") and out.get("speak", {}).get("word") and (
        typ not in _WORD_CHOICE_TYPES or out.get("choiceSpeak")
    ):
        return out
    word = _lookup_word(_question_word_id(out), extra_words)
    if word:
        return _with_speech(out, word, _speech_pool(word, extra_words, typ), typ in _WORD_CHOICE_TYPES)
    speak = _fallback_speak(out)
    if not speak:
        return out
    out["speak"] = speak
    if typ in _WORD_CHOICE_TYPES:
        answer = out.get("answer")
        out["choiceSpeak"] = [
            speak if i == answer else speak_payload(None, str(choice), speak["lang"])
            for i, choice in enumerate(out.get("choices") or [])
        ]
    return out


def make_en2zh(word: dict, pool: list[dict]) -> dict | None:
    meaning = (word.get("meaning") or "").strip()
    if not meaning:
        return None
    wrong = _distractors(pool, word, "meaning", 3)
    if len(wrong) < 3:
        return None
    choices = wrong + [meaning]
    random.shuffle(choices)
    ans = choices.index(meaning)
    explain = f"{word['word']} 的意思是「{meaning}」。"
    return _pack(
        f"en2zh:{word['id']}:{ans}",
        "en2zh",
        word["word"],
        "选择正确的中文意思",
        choices,
        ans,
        explain,
    )


def make_zh2en(word: dict, pool: list[dict]) -> dict | None:
    meaning = (word.get("meaning") or "").strip()
    if not meaning:
        return None
    wrong = _distractors(pool, word, "word", 3)
    if len(wrong) < 3:
        return None
    choices = wrong + [word["word"]]
    random.shuffle(choices)
    ans = choices.index(word["word"])
    explain = f"「{meaning}」对应的英文是 {word['word']}。"
    return _pack(
        f"zh2en:{word['id']}:{ans}",
        "zh2en",
        meaning,
        "选择正确的英文单词",
        choices,
        ans,
        explain,
    )


def make_cloze(word: dict, pool: list[dict]) -> dict | None:
    example = (word.get("example") or "").strip()
    blanked = _blank_example(word["word"], example)
    if not blanked:
        return None
    wrong = _distractors(pool, word, "word", 3)
    if len(wrong) < 3:
        return None
    choices = wrong + [word["word"]]
    random.shuffle(choices)
    ans = choices.index(word["word"])
    explain = f"这里应填 {word['word']}。"
    if word.get("meaning"):
        explain += f" 它的意思是「{word['meaning']}」。"
    note = "选择最合适的词填入空格"
    zh = word.get("exampleZh") or word.get("example_zh") or ""
    if zh:
        note = "选择最合适的词填入空格（句意：" + zh + "）"
    return _pack(
        f"cloze:{word['id']}:{ans}",
        "cloze",
        blanked,
        note,
        choices,
        ans,
        explain,
    )


def build_quiz(n: int = 10, recent_ids: list[str] | None = None, extra_words: list[dict] | None = None) -> list[dict]:
    """Build a mixed 10-question CET-4 quiz (vocab + grammar)."""
    pool = list(_WORDS)
    if extra_words:
        pool = extra_words + pool
    recent = set(recent_ids or [])
    usable = [w for w in pool if (w.get("meaning") or "").strip()]
    cloze_src = [w for w in usable if _blank_example(w["word"], w.get("example") or "")]

    questions: list[dict] = []

    def take(maker, source, count):
        random.shuffle(source)
        got = 0
        for w in source:
            if got >= count:
                break
            q = maker(w, usable)
            if not q:
                continue
            # recent filter uses a stable prefix without the random answer index
            prefix = ":".join(q["id"].split(":")[:2])
            if any(r.startswith(prefix) for r in recent) and len(source) > count * 3:
                continue
            questions.append(q)
            got += 1

    take(make_en2zh, usable, 3)
    take(make_zh2en, usable, 3)
    take(make_cloze, cloze_src, 2)

    grammar = [g for g in _GRAMMAR if g["id"] not in recent]
    if len(grammar) < 8:
        grammar = list(_GRAMMAR)
    random.shuffle(grammar)
    need_g = max(2, n - len(questions))
    for g in grammar[:need_g]:
        questions.append(dict(g))

    # fill if short
    if len(questions) < n:
        take(make_en2zh, usable, n - len(questions))

    random.shuffle(questions)
    return [enrich_question_speech(q, extra_words) for q in questions[:n]]


def rebuild_from_snapshot(snapshot: dict) -> dict:
    return dict(snapshot)


def _blank_korean(word: str, example: str) -> str | None:
    if not example or not word:
        return None
    pat = re.compile(r"(?<![가-힣])" + re.escape(word) + r"(?![가-힣])")
    if not pat.search(example):
        return None
    return pat.sub("_____", example, count=1)


def make_ko2zh(word: dict, pool: list[dict]) -> dict | None:
    meaning = (word.get("meaning") or "").strip()
    if not meaning:
        return None
    wrong = _distractors(pool, word, "meaning", 3)
    if len(wrong) < 3:
        return None
    choices = wrong + [meaning]
    random.shuffle(choices)
    ans = choices.index(meaning)
    roma = word.get("ipa") or ""
    note = "选择正确的中文意思"
    explain = f"{word['word']} 的意思是「{meaning}」。"
    if roma:
        explain = f"{word['word']}（{roma}）的意思是「{meaning}」。"
    return _pack(
        f"ko2zh:{word['id']}:{ans}",
        "ko2zh",
        word["word"],
        note,
        choices,
        ans,
        explain,
    )


def make_zh2ko(word: dict, pool: list[dict]) -> dict | None:
    meaning = (word.get("meaning") or "").strip()
    if not meaning:
        return None
    wrong = _distractors(pool, word, "word", 3)
    if len(wrong) < 3:
        return None
    choices = wrong + [word["word"]]
    random.shuffle(choices)
    ans = choices.index(word["word"])
    explain = f"「{meaning}」对应的韩语是 {word['word']}。"
    roma = word.get("ipa") or ""
    if roma:
        explain += f" 读音是 {roma}。"
    return _pack(
        f"zh2ko:{word['id']}:{ans}",
        "zh2ko",
        meaning,
        "选择正确的韩语单词",
        choices,
        ans,
        explain,
    )


def make_ko_cloze(word: dict, pool: list[dict]) -> dict | None:
    example = (word.get("example") or "").strip()
    blanked = _blank_korean(word["word"], example)
    if not blanked:
        return None
    wrong = _distractors(pool, word, "word", 3)
    if len(wrong) < 3:
        return None
    choices = wrong + [word["word"]]
    random.shuffle(choices)
    ans = choices.index(word["word"])
    explain = f"这里应填 {word['word']}。"
    if word.get("meaning"):
        explain += f" 它的意思是「{word['meaning']}」。"
    note = "选择最合适的词填入空格"
    zh = word.get("exampleZh") or ""
    if zh:
        note = "选择最合适的词填入空格（句意：" + zh + "）"
    return _pack(
        f"kocloze:{word['id']}:{ans}",
        "kocloze",
        blanked,
        note,
        choices,
        ans,
        explain,
    )


def build_korean_quiz(n: int = 6, recent_ids: list[str] | None = None) -> list[dict]:
    """A short beginner-Korean quiz. It never pulls CET-4 items."""
    pool = [w for w in _KO_WORDS if (w.get("meaning") or "").strip()]
    recent = set(recent_ids or [])
    cloze_src = [w for w in pool if _blank_korean(w["word"], w.get("example") or "")]
    questions: list[dict] = []

    def take(maker, source, count):
        random.shuffle(source)
        got = 0
        for w in source:
            if got >= count:
                break
            q = maker(w, pool)
            if not q:
                continue
            prefix = ":".join(q["id"].split(":")[:2])
            if any(r.startswith(prefix) for r in recent) and len(source) > count * 3:
                continue
            questions.append(q)
            got += 1

    take(make_ko2zh, pool, 2)
    take(make_zh2ko, pool, 2)
    take(make_ko_cloze, cloze_src, 2)
    if len(questions) < n:
        take(make_ko2zh, pool, n - len(questions))
    random.shuffle(questions)
    return [enrich_question_speech(q) for q in questions[:n]]
