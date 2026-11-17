#!/usr/bin/env python3
"""Build data/korean_words.json from the open Korean Basic Dictionary.

Source checkout (not committed):
  git clone --depth 1 https://github.com/basickorean/basickorean-vocab.git

That repository redistributes 국립국어원 한국어기초사전 under CC BY-SA 2.0 KR.
This script keeps beginner headwords tagged 1급 (국제 통용 한국어 표준 교육과정),
their short Chinese glosses, and original simple example sentences written for
this app. Dictionary example sentences are not copied.

Usage:
  KOREAN_SRC=/tmp/basickorean-vocab python3 scripts/build_korean_bank.py
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = Path(os.environ.get("KOREAN_SRC", "/tmp/basickorean-vocab"))
OUT = ROOT / "data" / "korean_words.json"

# Revised Romanization onset / vowel / coda. Coda ㅇ is not resyllabified.
CHO = ["g", "kk", "n", "d", "tt", "r", "m", "b", "pp", "s", "ss", "", "j", "jj", "ch", "k", "t", "p", "h"]
JUNG = [
    "a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa", "wae", "oe",
    "yo", "u", "wo", "we", "wi", "yu", "eu", "ui", "i",
]
JONG = [
    "", "k", "k", "k", "n", "n", "n", "t", "l", "k", "m", "l", "l", "l", "p", "l",
    "m", "p", "p", "t", "t", "ng", "t", "t", "k", "t", "p", "t",
]
# When a coda is followed by a vowel-initial syllable, it moves to the next onset.
JONG_AS_CHO = {
    1: 0, 2: 1, 3: 0, 4: 2, 5: 2, 6: 2, 7: 3, 8: 5, 9: 0, 10: 6, 11: 5, 12: 5,
    13: 5, 14: 5, 15: 5, 16: 6, 17: 7, 18: 7, 19: 9, 20: 10, 22: 12, 23: 14,
    24: 15, 25: 16, 26: 17, 27: 18,
}

GLOSS_FIX = {
    ("계시다", "동사"): "在（敬语）",
    ("못", "부사"): "不能",
    ("씨", "의존 명사"): "先生／女士（跟在名字后面）",
}

# Natural sentences where a template would be awkward or ungrammatical.
# Keyed by (headword, part of speech). Values are (korean, chinese).
OVERRIDES = {
    ("안녕", "감탄사"): ("안녕! 오늘 뭐 해?", "你好！今天做什么？"),
    ("네", "감탄사"): ("네, 알겠어요.", "好的，我知道了。"),
    ("예", "감탄사"): ("예, 맞아요.", "是的，对。"),
    ("아니요", "감탄사"): ("아니요, 학생이 아니에요.", "不，我不是学生。"),
    ("그래", "감탄사"): ("그래, 같이 가자.", "好吧，一起去吧。"),
    ("그럼", "감탄사"): ("그럼, 내일 봐요.", "那明天见。"),
    ("글쎄요", "감탄사"): ("글쎄요, 잘 모르겠어요.", "嗯……我不太知道。"),
    ("아", "감탄사"): ("아, 그렇군요.", "啊，原来是这样。"),
    ("와", "감탄사"): ("와, 정말 커요!", "哇，真大！"),
    ("음", "감탄사"): ("음, 잠깐 생각할게요.", "嗯，我先想一下。"),
    ("여보세요", "감탄사"): ("여보세요, 지금 집에 있어요?", "喂，你现在在家吗？"),
    ("저", "감탄사"): ("저, 질문 있어요.", "那个，我有个问题。"),
    ("나", "대명사"): ("나는 학생이에요.", "我是学生。"),
    ("저", "대명사"): ("저는 물을 마셔요.", "我喝水。"),
    ("내", "대명사"): ("내 이름이에요.", "这是我的名字。"),
    ("제", "대명사"): ("제 친구예요.", "是我的朋友。"),
    ("너", "대명사"): ("너는 어디에 가?", "你去哪儿？"),
    ("우리", "대명사"): ("우리 집에 와요.", "来我们家吧。"),
    ("그", "대명사"): ("그는 선생님이에요.", "他是老师。"),
    ("그것", "대명사"): ("그것은 물이에요.", "那是水。"),
    ("이것", "대명사"): ("이것은 책이에요.", "这是书。"),
    ("저것", "대명사"): ("저것은 뭐예요?", "那个是什么？"),
    ("여기", "대명사"): ("여기가 학교예요.", "这里是学校。"),
    ("거기", "대명사"): ("거기는 집이에요.", "那里是家。"),
    ("저기", "대명사"): ("저기에 사람이 있어요.", "那里有人。"),
    ("이쪽", "대명사"): ("이쪽으로 오세요.", "请到这边来。"),
    ("그쪽", "대명사"): ("그쪽은 누구예요?", "那边那位是谁？"),
    ("저쪽", "대명사"): ("저쪽에 앉아요.", "坐到那边去。"),
    ("어디", "대명사"): ("학교가 어디예요?", "学校在哪里？"),
    ("언제", "대명사"): ("수업이 언제예요?", "课在什么时候？"),
    ("누구", "대명사"): ("이 사람이 누구예요?", "这个人是谁？"),
    ("무엇", "대명사"): ("이것이 무엇이에요?", "这是什么？"),
    ("뭐", "대명사"): ("뭐 먹어요?", "吃什么？"),
    ("여러분", "대명사"): ("여러분, 안녕하세요.", "各位，你们好。"),
    ("이", "대명사"): ("이 책이 좋아요.", "这本书很好。"),
    ("저", "관형사"): ("저 사람이 선생님이에요.", "那个人是老师。"),
    ("이", "관형사"): ("이 물이 차가워요.", "这水是凉的。"),
    ("그", "관형사"): ("그 집이 학교 앞이에요.", "那所房子在学校前面。"),
    ("다른", "관형사"): ("다른 책을 읽어요.", "读别的书。"),
    ("무슨", "관형사"): ("무슨 음식을 좋아해요?", "你喜欢什么食物？"),
    ("어떤", "관형사"): ("어떤 영화를 봐요?", "看什么样的电影？"),
    ("어느", "관형사"): ("어느 학교에 다녀요?", "你上哪所学校？"),
    ("여러", "관형사"): ("여러 사람이 왔어요.", "来了好几个人。"),
    ("약", "관형사"): ("약 열 명이 있어요.", "大约有十个人。"),
    ("전", "관형사"): ("전 페이지를 봐요.", "看前一页。"),
    ("네", "관형사"): ("네 명이에요.", "是四个人。"),
    ("그리고", "부사"): ("물을 마셔요. 그리고 밥도 먹어요.", "我喝水。而且也吃饭。"),
    ("그래서", "부사"): ("배가 고파요. 그래서 밥을 먹어요.", "肚子饿了。所以吃饭。"),
    ("그러나", "부사"): ("비싸요. 그러나 사고 싶어요.", "很贵。但是我想买。"),
    ("하지만", "부사"): ("어려워요. 하지만 재미있어요.", "很难。但是很有意思。"),
    ("그런데", "부사"): ("학생이에요. 그런데 오늘 쉬어요.", "我是学生。不过今天休息。"),
    ("그렇지만", "부사"): ("작아요. 그렇지만 좋아요.", "很小。不过很好。"),
    ("그러면", "부사"): ("시간이 없어요. 그러면 내일 해요.", "没有时间。那么明天再做。"),
    ("그럼", "부사"): ("배가 고파요. 그럼 밥을 먹어요.", "肚子饿了。那吃饭吧。"),
    ("그러니까", "부사"): ("비가 와요. 그러니까 집에 있어요.", "下雨了。所以待在家里。"),
    ("못", "부사"): ("오늘은 학교에 못 가요.", "今天不能去学校。"),
    ("안", "부사"): ("오늘은 안 먹어요.", "今天不吃。"),
    ("왜", "부사"): ("왜 늦었어요?", "为什么迟到了？"),
    ("언제", "부사"): ("언제 집에 가요?", "什么时候回家？"),
    ("얼마나", "부사"): ("얼마나 커요?", "有多大？"),
    ("어디", "부사"): ("어디 가요?", "去哪里？"),
    ("가장", "부사"): ("이 책이 가장 좋아요.", "这本书最好。"),
    ("제일", "부사"): ("커피를 제일 좋아해요.", "我最喜欢咖啡。"),
    ("너무", "부사"): ("너무 커요.", "太大了。"),
    ("아주", "부사"): ("아주 재미있어요.", "非常有意思。"),
    ("정말", "부사"): ("정말 고마워요.", "真的很感谢。"),
    ("참", "부사"): ("참 예뻐요.", "真漂亮。"),
    ("빨리", "부사"): ("빨리 오세요.", "请快来。"),
    ("천천히", "부사"): ("천천히 말해요.", "请慢慢说。"),
    ("많이", "부사"): ("물을 많이 마셔요.", "多喝水。"),
    ("잘", "부사"): ("한국어를 잘하고 싶어요.", "我想把韩语学好。"),
    ("잘못", "부사"): ("이름을 잘못 썼어요.", "名字写错了。"),
    ("다시", "부사"): ("다시 읽어 주세요.", "请再读一遍。"),
    ("또", "부사"): ("또 만나요.", "再见面吧。"),
    ("더", "부사"): ("물을 더 주세요.", "请再给我一些水。"),
    ("같이", "부사"): ("같이 밥 먹어요.", "一起吃饭吧。"),
    ("함께", "부사"): ("함께 공부해요.", "一起学习吧。"),
    ("혼자", "부사"): ("혼자 집에 있어요.", "一个人待在家里。"),
    ("먼저", "부사"): ("제가 먼저 갈게요.", "我先走了。"),
    ("아직", "부사"): ("아직 학생이에요.", "我还是学生。"),
    ("벌써", "부사"): ("벌써 세 시예요.", "已经三点了。"),
    ("보통", "부사"): ("보통 집에 있어요.", "我通常在家。"),
    ("주로", "부사"): ("주로 물을 마셔요.", "我主要喝水。"),
    ("계속", "부사"): ("계속 공부해요.", "继续学习。"),
    ("꼭", "부사"): ("내일 꼭 오세요.", "明天一定要来。"),
    ("바로", "부사"): ("학교에서 바로 집에 가요.", "从学校直接回家。"),
    ("특히", "부사"): ("커피를 특히 좋아해요.", "我特别喜欢咖啡。"),
    ("열심히", "부사"): ("열심히 공부해요.", "认真学习。"),
    ("자주", "부사"): ("친구를 자주 만나요.", "经常见朋友。"),
    ("매일", "부사"): ("매일 학교에 가요.", "每天去学校。"),
    ("오늘", "부사"): ("오늘 뭐 해요?", "今天做什么？"),
    ("내일", "부사"): ("내일 다시 와요.", "明天再来。"),
    ("어제", "부사"): ("어제 집에 있었어요.", "昨天在家。"),
    ("그저께", "부사"): ("그저께 친구를 만났어요.", "前天见了朋友。"),
    ("모레", "부사"): ("모레 시험이 있어요.", "后天有考试。"),
    ("지금", "부사"): ("지금 공부해요.", "现在学习。"),
    ("이따가", "부사"): ("이따가 밥 먹어요.", "待会儿吃饭。"),
    ("잠시", "부사"): ("잠시 쉬어요.", "休息一会儿。"),
    ("잠깐", "부사"): ("잠깐 기다릴게요.", "我等一下。"),
    ("일찍", "부사"): ("일찍 일어나요.", "早起。"),
    ("어서", "부사"): ("어서 오세요.", "快请进。"),
    ("별로", "부사"): ("별로 안 추워요.", "不怎么冷。"),
    ("보다", "부사"): ("어제보다 더워요.", "比昨天热。"),
    ("다", "부사"): ("숙제를 다 했어요.", "作业都做完了。"),
    ("모두", "부사"): ("모두 학생이에요.", "大家都是学生。"),
    ("안녕히", "부사"): ("안녕히 가세요.", "请慢走。"),
    ("조금", "부사"): ("물을 조금 주세요.", "请给我一点水。"),
    ("좀", "부사"): ("좀 도와주세요.", "请帮帮我。"),
    ("있다", "형용사"): ("시간이 있어요.", "有时间。"),
    ("있다", "동사"): ("지금 집에 있어요.", "现在在家。"),
    ("없다", "형용사"): ("시간이 없어요.", "没有时间。"),
    ("아니다", "형용사"): ("저는 선생님이 아니에요.", "我不是老师。"),
    ("같다", "형용사"): ("이거와 같아요.", "和这个一样。"),
    ("그렇다", "형용사"): ("네, 그래요.", "是的，是那样。"),
    ("어떻다", "형용사"): ("오늘 날씨가 어때요?", "今天天气怎么样？"),
    ("고프다", "형용사"): ("배가 고파요.", "肚子饿了。"),
    ("고맙다", "형용사"): ("정말 고마워요.", "真的很感谢。"),
    ("괜찮다", "형용사"): ("네, 괜찮아요.", "嗯，没关系。"),
    ("가볍다", "형용사"): ("이 가방은 가벼워요.", "这个包很轻。"),
    ("가깝다", "형용사"): ("학교가 집과 가까워요.", "学校离家近。"),
    ("덥다", "형용사"): ("오늘 정말 더워요.", "今天真热。"),
    ("춥다", "형용사"): ("오늘 정말 추워요.", "今天真冷。"),
    ("맵다", "형용사"): ("이 음식이 매워요.", "这个菜很辣。"),
    ("쉽다", "형용사"): ("이 문제는 쉬워요.", "这道题很简单。"),
    ("어렵다", "형용사"): ("이 문제는 어려워요.", "这道题很难。"),
    ("무겁다", "형용사"): ("가방이 무거워요.", "包很重。"),
    ("반갑다", "형용사"): ("만나서 반가워요.", "很高兴见到你。"),
    ("아름답다", "형용사"): ("꽃이 아름다워요.", "花很美。"),
    ("싱겁다", "형용사"): ("국이 싱거워요.", "汤太淡了。"),
    ("계시다", "동사"): ("선생님이 교실에 계세요.", "老师在教室里。"),
    ("잡수시다", "동사"): ("맛있게 잡수세요.", "请好好吃。"),
    ("주무시다", "동사"): ("일찍 주무세요.", "请早点睡。"),
    ("맞다", "동사"): ("이 답이 맞아요.", "这个答案是对的。"),
    ("모르다", "동사"): ("저는 그 사람을 몰라요.", "我不认识那个人。"),
    ("못하다", "동사"): ("저는 요리를 못해요.", "我不会做饭。"),
    ("싫다", "형용사"): ("매운 음식은 싫어요.", "我不喜欢辣的食物。"),
    ("싫어하다", "동사"): ("나는 비를 싫어해요.", "我讨厌下雨。"),
    ("좋아하다", "동사"): ("나는 커피를 좋아해요.", "我喜欢咖啡。"),
    ("되다", "동사"): ("친구가 되고 싶어요.", "我想成为朋友。"),
    ("있다", "동사"): ("지금 집에 있어요.", "现在待在家里。"),
    ("가지", "의존 명사"): ("과일이 세 가지 있어요.", "有三种水果。"),
    ("개", "의존 명사"): ("사과가 한 개 있어요.", "有一个苹果。"),
    ("것", "의존 명사"): ("먹는 것을 좋아해요.", "我喜欢吃的东西。"),
    ("권", "의존 명사"): ("책이 두 권 있어요.", "有两本书。"),
    ("날", "의존 명사"): ("좋은 날에 만나요.", "挑个好日子见面。"),
    ("년", "의존 명사"): ("이천이십사 년이에요.", "是二零二四年。"),
    ("달", "의존 명사"): ("한 달 공부했어요.", "学了一个月。"),
    ("마리", "의존 명사"): ("강아지가 한 마리 있어요.", "有一只小狗。"),
    ("명", "의존 명사"): ("학생이 세 명 있어요.", "有三名学生。"),
    ("번", "의존 명사"): ("한 번 더 읽어 주세요.", "请再读一遍。"),
    ("살", "의존 명사"): ("스무 살이에요.", "二十岁。"),
    ("시", "의존 명사"): ("지금 세 시예요.", "现在三点。"),
    ("시간", "의존 명사"): ("한 시간 공부해요.", "学习一个小时。"),
    ("씨", "의존 명사"): ("민수 씨, 안녕하세요.", "民洙，你好。"),
    ("원", "의존 명사"): ("이것은 천 원이에요.", "这个是一千韩元。"),
    ("월", "의존 명사"): ("오늘은 삼 월이에요.", "今天是三月。"),
    ("인분", "의존 명사"): ("불고기 이 인분 주세요.", "请来两份烤肉。"),
    ("일", "의존 명사"): ("오늘은 십 일이에요.", "今天是十号。"),
    ("주일", "의존 명사"): ("일 주일 쉬어요.", "休息一个星期。"),
    ("중", "의존 명사"): ("지금 수업 중이에요.", "现在正在上课。"),
    ("쪽", "의존 명사"): ("이 쪽으로 가세요.", "请往这边走。"),
    ("호", "의존 명사"): ("삼 호 차에 타요.", "坐三路车。"),
}


def _batchim(word: str) -> bool:
    for ch in reversed(word):
        code = ord(ch) - 0xAC00
        if 0 <= code <= 11171:
            return code % 28 != 0
    return False


def romanize(text: str) -> str:
    chars = []
    for ch in unicodedata.normalize("NFC", text or ""):
        code = ord(ch) - 0xAC00
        if 0 <= code <= 11171:
            chars.append(ch)
    if not chars:
        return ""
    syl = []
    for ch in chars:
        code = ord(ch) - 0xAC00
        syl.append([code // 588, (code % 588) // 28, code % 28])
    for i, cur in enumerate(syl[:-1]):
        nxt = syl[i + 1]
        jong = cur[2]
        if jong and nxt[0] == 11 and jong in JONG_AS_CHO:
            nxt[0] = JONG_AS_CHO[jong]
            cur[2] = 0
    parts = []
    for i, (cho, jung, jong) in enumerate(syl):
        ini = CHO[cho]
        if cho == 5:
            prev_jong = syl[i - 1][2] if i else 0
            ini = "l" if prev_jong == 8 else "r"
        parts.append(ini + JUNG[jung] + JONG[jong])
    return "".join(parts)


def short_gloss(gloss: str) -> str:
    g = (gloss or "").strip()
    g = re.sub(r"[（(].*?[）)]", "", g).strip()
    g = re.split(r"[，,；;]", g)[0].strip()
    return g


def sentence_for(word: str, pos: str, gloss: str) -> tuple[str, str]:
    g = short_gloss(gloss) or "这个词"
    hit = OVERRIDES.get((word, pos))
    if isinstance(hit, dict):
        for key, pair in hit.items():
            if g == key or g.startswith(key) or key.startswith(g):
                return pair
    elif hit:
        return hit
    if pos == "명사":
        p = "이" if _batchim(word) else "가"
        if sum(map(ord, word)) % 2 == 0:
            return f"{word}{p} 있어요.", f"有{g}。"
        return f"{word}{p} 좋아요.", f"{g}很好。"
    if pos == "동사" and word.endswith("다"):
        stem = word[:-1]
        return f"저는 {stem}고 싶어요.", f"我想{g}。"
    if pos == "형용사" and word.endswith("다"):
        if word.endswith("하다"):
            return f"정말 {word[:-1]}네요.", f"真的很{g}。"
        stem = word[:-1]
        return f"정말 {stem}네요.", f"真的很{g}。"
    if pos == "수사":
        ending = "이에요" if _batchim(word) else "예요"
        return f"이 숫자는 {word}{ending}.", f"这个数字是{g}。"
    if pos == "관형사":
        return f"여기 {word} 사람이 있어요.", f"这里有{g}个人。"
    if pos == "부사":
        return f"오늘은 {word} 공부해요.", f"今天{g}学习。"
    if pos == "감탄사":
        return f"{word}!", f"{g}！"
    if pos == "대명사":
        top = "은" if _batchim(word) else "는"
        return f"{word}{top} 학생이에요.", f"{g}是学生。"
    if pos == "의존 명사":
        return f"한 {word} 있어요.", f"有一{g}。"
    return f"오늘 '{word}'를 배워요.", f"今天学习「{g}」。"


# Homographs need different sentences. Applied after OVERRIDES so they win.
OVERRIDES[("저", "대명사")] = {
    "我": ("저는 물을 마셔요.", "我喝水。"),
    "那": ("가리키는 것은 저예요.", "指的是那个。"),
}
OVERRIDES[("분", "의존 명사")] = {
    "位": ("선생님이 두 분 계세요.", "有两位老师。"),
    "分": ("오 분 기다려 주세요.", "请等五分钟。"),
}
OVERRIDES[("눈", "명사")] = {
    "雪": ("오늘 눈이 와요.", "今天下雪了。"),
    "眼睛": ("눈이 아파요.", "眼睛疼。"),
}
OVERRIDES[("배", "명사")] = {
    "肚子": ("배가 고파요.", "肚子饿了。"),
    "船": ("배를 타요.", "坐船。"),
    "梨": ("배를 먹어요.", "吃梨。"),
}
OVERRIDES[("병", "명사")] = {
    "病": ("병이 나았어요.", "病好了。"),
    "瓶子": ("물이 병에 있어요.", "水在瓶子里。"),
}
OVERRIDES[("반", "명사")] = {
    "班": ("우리 반이 좋아요.", "我们班很好。"),
    "一半": ("반만 먹었어요.", "只吃了一半。"),
}
OVERRIDES[("일", "명사")] = {
    "一日": ("오늘은 일요일이에요.", "今天是星期日。"),
    "事情": ("오늘 일이 많아요.", "今天事情很多。"),
}
OVERRIDES[("쓰다", "동사")] = {
    "写": ("이름을 써요.", "写下名字。"),
    "用": ("이 펜을 써요.", "用这支笔。"),
}
OVERRIDES[("타다", "동사")] = {
    "乘": ("버스를 타요.", "坐公交车。"),
    "烧": ("불이 타요.", "火在烧。"),
}
OVERRIDES[("들다", "동사")] = {
    "带": ("가방을 들어요.", "拎着包。"),
    "进去": ("물이 안으로 들어요.", "水往里面进去。"),
}
OVERRIDES[("이", "관형사")] = {
    "二": ("이 학년이에요.", "是二年级。"),
    "这": ("이 책이 좋아요.", "这本书很好。"),
}

# 网眼 is a rare homograph tagged 1급; 眼睛 is the beginner sense learners need.
SKIP_IDS = {41542}
INCLUDE_IDS = {72704}


def first_gloss(zh_entries, idx: int) -> str:
    if idx >= len(zh_entries):
        return ""
    block = zh_entries[idx] or []
    if not block or not block[0]:
        return ""
    pair = block[0]
    if not pair or not pair[0]:
        return ""
    return str(pair[0]).strip()


# Everyday words first, so a new Korean plan does not open on a random syllable.
PRIORITY = """
안녕 네 아니요 예 저 나 너 우리 사람 친구 선생님 학생 학교 집 물 밥 커피
오늘 내일 어제 지금 가다 오다 하다 먹다 마시다 보다 듣다 읽다 쓰다 배우다
좋다 있다 없다 많다 크다 작다 고맙다 괜찮다 이름 책 시간 돈 일
""".split()
PRIORITY_INDEX = {w: i for i, w in enumerate(PRIORITY)}
POS_RANK = {
    "감탄사": 0, "대명사": 1, "명사": 2, "수사": 3, "관형사": 4,
    "동사": 5, "형용사": 6, "부사": 7, "의존 명사": 8,
}


def main() -> None:
    core = SRC / "shards" / "core"
    zh_root = SRC / "shards" / "tr" / "zh"
    if not core.is_dir():
        raise SystemExit(f"Korean source not found at {SRC}. Clone basickorean/basickorean-vocab first.")
    rows = []
    for fn in sorted(os.listdir(core)):
        if not fn.endswith(".json"):
            continue
        data = json.loads((core / fn).read_text(encoding="utf-8"))
        zh = json.loads((zh_root / fn).read_text(encoding="utf-8"))
        for word, entries in data.items():
            if not isinstance(entries, list):
                continue
            zentries = zh.get(word) or []
            for idx, entry in enumerate(entries):
                if not isinstance(entry, dict):
                    continue
                iid = entry.get("i")
                if iid in SKIP_IDS:
                    continue
                if entry.get("u") != "단어":
                    continue
                if iid not in INCLUDE_IDS and entry.get("lv") != "1급":
                    continue
                pos = entry.get("p") or ""
                if any(ch.isspace() for ch in word) or not word:
                    continue
                gloss = GLOSS_FIX.get((word, pos)) or first_gloss(zentries, idx)
                gloss = short_gloss(gloss)
                if not gloss or gloss.startswith("无对应"):
                    continue
                # Romanize the written headword (Revised Romanization), not the
                # phonetic spelling, so 학교 stays hakgyo rather than hakkkyo.
                roma = romanize(word)
                ko, zh_s = sentence_for(word, pos, gloss)
                rows.append(
                    {
                        "id": f"ko_{entry.get('i')}",
                        "word": word,
                        "lang": "ko",
                        "pos": pos,
                        "level": "1급",
                        "ipa": roma,
                        "reading": word,
                        "meaning": gloss,
                        "example": ko,
                        "exampleZh": zh_s,
                        "_ord": (PRIORITY_INDEX.get(word, 10000), POS_RANK.get(pos, 9), word, str(entry.get("i"))),
                    }
                )
    rows.sort(key=lambda r: r["_ord"])
    # Stable unique ids. If a source id repeats, keep the first.
    seen = set()
    out = []
    for row in rows:
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        row.pop("_ord")
        out.append(row)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {len(out)} words to {OUT}")
    for sample in ("안녕", "학교", "물", "먹다", "춥다", "눈"):
        hit = next((w for w in out if w["word"] == sample), None)
        if hit:
            print(sample, hit["ipa"], "|", hit["example"], "|", hit["meaning"])


if __name__ == "__main__":
    main()
