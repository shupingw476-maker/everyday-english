/* 请叫我学习 · 两人互相监督的学习界面 */
(function () {
  const $app = document.getElementById("app");
  const $header = document.getElementById("header");
  const $nav = document.getElementById("nav");
  const $toasts = document.getElementById("toasts");

  const TYPE_LABEL = {
    en2zh: "英选中",
    zh2en: "中选英",
    cloze: "句子填空",
    grammar: "语法",
    ko2zh: "韩选中",
    zh2ko: "中选韩",
    kocloze: "句子填空",
  };

  let state = null;
  let meta = null;
  let session = null;
  let quizRun = null;
  let listState = { query: "", filter: "全部", page: 1, total: 0, items: [] };
  let toastTimer = 0;
  let busy = false;

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v == null || v === false) continue;
        if (k === "class") node.className = v;
        else if (k === "dataset") Object.assign(node.dataset, v);
        else if (k === "style" && typeof v === "object") Object.assign(node.style, v);
        else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2).toLowerCase(), v);
        else if (k === "html") node.innerHTML = v;
        else if (v === true) node.setAttribute(k, "");
        else node.setAttribute(k, String(v));
      }
    }
    const list = children == null ? [] : Array.isArray(children) ? children : [children];
    for (const c of list) {
      if (c == null || c === false) continue;
      node.append(c.nodeType ? c : document.createTextNode(String(c)));
    }
    return node;
  }

  function icon(name) {
    const paths = {
      home: '<path d="M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>',
      book: '<path d="M5 5.5A2.5 2.5 0 0 1 7.5 3H20v16H7.5A2.5 2.5 0 0 0 5 21.5V5.5z" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M5 21.5A2.5 2.5 0 0 1 7.5 19H20" fill="none" stroke="currentColor" stroke-width="1.7"/>',
      quiz: '<path d="M8 7h8M8 12h8M8 17h4" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><rect x="4" y="3.5" width="16" height="17" rx="2.5" fill="none" stroke="currentColor" stroke-width="1.7"/>',
      trend: '<path d="M4 16l5.5-5.5 3.5 3.5L20 7" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/><path d="M15 7h5v5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>',
      gear: '<path d="M12 15.2a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4z" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M19.4 12a7.4 7.4 0 0 0-.1-1.1l2-1.6-1.5-2.6-2.4.6a7.6 7.6 0 0 0-1.9-1.1L15 3.5h-3l-.5 2.7a7.6 7.6 0 0 0-1.9 1.1l-2.4-.6-1.5 2.6 2 1.6a7.4 7.4 0 0 0 0 2.2l-2 1.6 1.5 2.6 2.4-.6c.6.45 1.22.82 1.9 1.1l.5 2.7h3l.5-2.7c.68-.28 1.3-.65 1.9-1.1l2.4.6 1.5-2.6-2-1.6c.07-.36.1-.73.1-1.1z" fill="none" stroke="currentColor" stroke-width="1.4"/>',
      search: '<circle cx="11" cy="11" r="6.5" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M16 16l4 4" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
      back: '<path d="M14 5l-7 7 7 7" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
    };
    return `<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">${paths[name] || ""}</svg>`;
  }

  let speakAudio = null;

  function quizPoints() {
    return (meta && meta.quizCorrectPoints) || 15;
  }

  function playServerAudio(word, language) {
    try {
      if (speakAudio) speakAudio.pause();
      speakAudio = new Audio("/api/tts?lang=" + language + "&q=" + encodeURIComponent(word));
      const played = speakAudio.play();
      if (played && played.catch) played.catch(() => toast("暂时读不出来，可以先看读音"));
    } catch (e) {
      toast("暂时读不出来，可以先看读音");
    }
  }

  function playPronunciation(text, lang, event) {
    if (event) {
      event.stopPropagation();
      event.preventDefault();
    }
    const word = String(text || "").trim();
    if (!word) return;
    const language = lang === "ko" ? "ko" : "en";
    const synth = window.speechSynthesis;
    const wechat = /MicroMessenger/i.test(navigator.userAgent || "");
    const voices = synth && synth.getVoices ? synth.getVoices() : [];
    const prefix = language === "ko" ? "ko" : "en";
    const voice = (voices || []).find((v) => (v.lang || "").toLowerCase().startsWith(prefix));
    const canSpeak = !!(synth && window.SpeechSynthesisUtterance && !wechat && (voice || !(voices || []).length));
    if (canSpeak) {
      try {
        const utter = new SpeechSynthesisUtterance(word);
        utter.lang = language === "ko" ? "ko-KR" : "en-US";
        utter.rate = 0.9;
        if (voice) utter.voice = voice;
        utter.onerror = () => playServerAudio(word, language);
        synth.cancel();
        synth.speak(utter);
        return;
      } catch (e) {}
    }
    playServerAudio(word, language);
  }

  function speakButton(word, lang) {
    return el("button", {
      type: "button",
      class: "speak-btn",
      "data-speak": word || "",
      "aria-label": "朗读 " + (word || ""),
      onClick: (e) => playPronunciation(word, lang, e),
      onKeydown: (e) => e.stopPropagation(),
    }, [
      el("span", {
        class: "speak-ico",
        "aria-hidden": "true",
        html: '<svg viewBox="0 0 24 24" width="16" height="16"><path d="M4 9.5v5h3.5L13 19V5L7.5 9.5H4z" fill="currentColor"/><path d="M16 9.2a3.6 3.6 0 0 1 0 5.6" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><path d="M18.2 7a6.4 6.4 0 0 1 0 10" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>',
      }),
      "朗读",
    ]);
  }

  function pronunciationLine(info, withWord) {
    const lang = info && info.lang === "ko" ? "ko" : "en";
    const ipa = String((info && info.ipa) || "").trim();
    const word = String((info && info.word) || "").trim();
    if (lang === "ko") {
      const script = String((info && info.reading) || word).trim();
      return ipa ? script + "  ·  " + ipa : script;
    }
    if (withWord) return ipa ? word + "  ·  " + ipa : word;
    return ipa || "词库里没有音标，点朗读听读音";
  }

  function readingBlock(w, extraClass, withWord) {
    const lang = w.lang === "ko" ? "ko" : "en";
    const line = pronunciationLine(w, withWord);
    return el("div", { class: "reading" + (extraClass ? " " + extraClass : "") }, [
      el("span", { class: "lab" }, "读音"),
      el("span", { class: "phon", "data-ipa": String(w.ipa || "").trim() }, line),
      speakButton(w.word, lang),
    ]);
  }

  const PROMPT_WORD_TYPES = { en2zh: "en", ko2zh: "ko" };
  const CHOICE_WORD_TYPES = { zh2en: "en", cloze: "en", zh2ko: "ko", kocloze: "ko" };

  function questionSpeak(q) {
    if (q && q.speak && q.speak.word) return q.speak;
    if (!q) return null;
    if (PROMPT_WORD_TYPES[q.type]) {
      const lang = PROMPT_WORD_TYPES[q.type];
      return { word: q.prompt, lang: lang, ipa: "", reading: lang === "ko" ? q.prompt : "" };
    }
    if (CHOICE_WORD_TYPES[q.type]) {
      const word = (q.choices || [])[q.answer] || "";
      if (!word) return null;
      const lang = CHOICE_WORD_TYPES[q.type];
      return { word: word, lang: lang, ipa: "", reading: lang === "ko" ? word : "" };
    }
    return null;
  }

  function choiceSpeakAt(q, i) {
    const listed = q && q.choiceSpeak;
    if (Array.isArray(listed)) {
      const item = listed[i];
      return item && item.word ? item : null;
    }
    const lang = CHOICE_WORD_TYPES[q && q.type];
    const text = (q && q.choices || [])[i];
    if (!lang || !text) return null;
    return { word: text, lang: lang, ipa: "", reading: lang === "ko" ? text : "" };
  }

  function choicePronounce(info) {
    const phon = info.lang === "ko"
      ? pronunciationLine(info, false)
      : String(info.ipa || "").trim();
    return el("div", { class: "choice-speak" }, [
      phon ? el("span", { class: "phon", "data-ipa": String(info.ipa || "").trim() }, phon) : null,
      speakButton(info.word, info.lang),
    ]);
  }

  function exampleBlock(w) {
    return el("div", { class: "example" }, [
      el("div", { class: "lab" }, "造句"),
      el("div", { class: "en-line" }, w.example || "（例句准备中）"),
      w.exampleZh ? el("div", { class: "zh-line" }, w.exampleZh) : null,
    ]);
  }

  function rewardBurst() {
    const spots = [[-36, -16], [32, -20], [-14, -34], [16, -6], [-24, 8], [6, -30]];
    const sparks = spots.map(([x, y], i) => el("span", {
      class: "spark",
      style: { "--dx": x + "px", "--dy": y + "px", animationDelay: (i * 0.03) + "s" },
    }));
    return el("div", { class: "reward-pop", role: "status" }, [
      el("div", { class: "reward-badge" }, "答对了  +" + quizPoints()),
      ...sparks,
    ]);
  }

  function toast(msg) {
    if (!$toasts) return;
    $toasts.innerHTML = "";
    $toasts.append(el("div", { class: "toast", role: "status" }, msg));
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { $toasts.innerHTML = ""; }, 3400);
  }

  function route() {
    const hash = (location.hash || "#/home").replace(/^#/, "");
    const parts = hash.split("?").shift().split("/").filter(Boolean);
    return { name: parts[0] || "home", parts, raw: hash };
  }
  function go(to) {
    location.hash = to.startsWith("#") ? to : "#/" + to.replace(/^#?\/?/, "");
  }

  function announceCheckin(check) {
    if (!check) return;
    if (check.ok && !check.already && check.bonus) {
      toast("今日打卡成功，+" + check.bonus + " 分");
    }
    (check.streakBonuses || []).forEach((b) => toast("连续学习 " + b.day + " 天，额外 +" + b.points + " 分"));
  }

  async function refreshState() {
    state = await API.state();
    maybeNotify(state);
    return state;
  }

  function maybeNotify(st) {
    if (!st || !st.partner || !st.partner.missedYesterday) return;
    const key = "jinbu.notified." + st.today;
    if (localStorage.getItem(key)) return;
    if (!("Notification" in window)) return;
    if (Notification.permission === "granted") {
      try {
        new Notification("请叫我学习", {
          body: st.partner.name + "昨天没打卡了，按约定去催一下！",
          icon: "./icons/icon-192.png",
        });
      } catch (e) {}
      localStorage.setItem(key, "1");
    }
  }

  function requestNotifySoft() {
    if (!("Notification" in window) || Notification.permission !== "default") return;
    Notification.requestPermission().then((p) => {
      if (p === "granted" && state) maybeNotify(state);
    });
  }

  /* ---------- chrome ---------- */
  function renderChrome(active, authed) {
    $header.innerHTML = "";
    const right = !authed
      ? el("span", { style: { width: "40px" } })
      : el("button", {
          class: "icon-btn",
          type: "button",
          "aria-label": "设置",
          onClick: () => go("settings"),
          html: icon("gear"),
        });
    $header.append(
      el("a", { class: "wordmark", href: authed ? "#/home" : "#/gate", "aria-label": "请叫我学习" }, [
        el("span", { class: "cn" }, "请叫我学习"),
      ]),
      right
    );
    if (!authed) {
      $nav.hidden = true;
      $nav.innerHTML = "";
      return;
    }
    $nav.hidden = false;
    const items = [
      ["home", "今日", "home"],
      ["words", "单词", "book"],
      ["quiz", "做题", "quiz"],
      ["progress", "进度", "trend"],
    ];
    $nav.innerHTML = "";
    items.forEach(([id, label, ic]) => {
      const isOn =
        active === id ||
        (id === "words" && active === "session") ||
        (id === "quiz" && active === "play") ||
        (id === "progress" && active === "settings");
      $nav.append(
        el("a", { href: "#/" + id, class: isOn ? "active" : "", "aria-current": isOn ? "page" : null }, [
          el("span", { html: icon(ic) }),
          label,
        ])
      );
    });
  }

  /* ---------- Gate ---------- */
  function viewGate() {
    const wrap = el("div", { class: "gate" });
    const tab = (session && session.gateTab) || "create";
    wrap.append(
      el("h1", {}, "请叫我学习"),
      el("p", { class: "lead" }, "两个人互相监督。一个人建房间，把邀请码发给朋友。默认学四级英语；也可以把其中一个人改成韩语，或英语加韩语。房间还是两个人。")
    );
    wrap.append(
      el("div", { class: "tabs", role: "tablist" }, [
        el("button", { type: "button", class: tab === "create" ? "on" : "", onClick: () => { session = { gateTab: "create" }; render(); } }, "创建房间"),
        el("button", { type: "button", class: tab === "join" ? "on" : "", onClick: () => { session = { gateTab: "join" }; render(); } }, "加入房间"),
      ])
    );
    if (tab === "join") wrap.append(joinForm());
    else wrap.append(createForm());
    return wrap;
  }

  function planField(values, gateTab) {
    const current = values.studyPlan || "cet4";
    const select = el("select", {
      onChange: (e) => {
        values.studyPlan = e.target.value;
        const patch = gateTab === "join"
          ? { gateTab: "join", join: values }
          : { gateTab: "create", create: values };
        session = Object.assign(session || {}, patch);
      },
    });
    [["cet4", "四级英语"], ["korean", "韩语入门"], ["both", "四级英语 + 韩语"]].forEach(([id, label]) => {
      select.append(el("option", { value: id, selected: current === id ? true : null }, label));
    });
    return el("label", { class: "field" }, [
      "我的学习计划",
      select,
      el("p", { class: "tiny muted" }, "默认四级英语。计划记在你自己身上，房间仍然是两个人。"),
    ]);
  }

  function createForm() {
    const values = Object.assign(
      { name: "", friendName: "", studyPlan: "cet4", punishmentText: (meta && meta.defaultPunishment) || "昨天没打卡的人，要被催，并且下一天要多做一份惩罚任务" },
      (session && session.create) || {}
    );
    const form = el("div", { class: "card" });
    const fields = [
      ["name", "你的昵称", "text", "比如：小王"],
      ["friendName", "朋友的昵称（可选，加入前会先显示这个名字）", "text", "比如：小红"],
    ];
    fields.forEach(([key, label, type, ph]) => {
      form.append(
        el("label", { class: "field" }, [
          label,
          el("input", {
            type,
            placeholder: ph,
            value: values[key] || "",
            maxlength: "16",
            onInput: (e) => { values[key] = e.target.value; session = Object.assign(session || {}, { gateTab: "create", create: values }); },
          }),
        ])
      );
    });
    form.append(planField(values, "create"));
    form.append(
      el("label", { class: "field" }, [
        "惩罚约定",
        el("textarea", {
          onInput: (e) => { values.punishmentText = e.target.value; session = Object.assign(session || {}, { gateTab: "create", create: values }); },
        }, values.punishmentText),
      ]),
      el("div", { class: "btn-row" }, [
        el("button", {
          class: "btn btn-primary",
          type: "button",
          onClick: async () => {
            if (busy) return;
            busy = true;
            try {
              const res = await API.createRoom({
                name: values.name,
                friendName: values.friendName,
                punishmentText: values.punishmentText,
                studyPlan: values.studyPlan || "cet4",
              });
              API.setToken(res.token);
              state = res.state;
              session = null;
              toast("房间已创建，把邀请码发给朋友吧");
              go("home");
            } catch (err) {
              toast(err.message || "创建失败");
            } finally {
              busy = false;
            }
          },
        }, "创建房间"),
      ])
    );
    return form;
  }

  function joinForm() {
    const values = Object.assign({ code: "", name: "", studyPlan: "cet4" }, (session && session.join) || {});
    const form = el("div", { class: "card" });
    form.append(
      el("label", { class: "field" }, [
        "邀请码（6 位）",
        el("input", {
          type: "text",
          placeholder: "例如：K7M2PQ",
          value: values.code,
          maxlength: "6",
          style: { letterSpacing: "0.16em", textTransform: "uppercase" },
          onInput: (e) => { values.code = e.target.value.toUpperCase(); session = Object.assign(session || {}, { gateTab: "join", join: values }); },
        }),
      ]),
      el("label", { class: "field" }, [
        "你的昵称",
        el("input", {
          type: "text",
          placeholder: "和朋友好区分就行",
          value: values.name,
          maxlength: "16",
          onInput: (e) => { values.name = e.target.value; session = Object.assign(session || {}, { gateTab: "join", join: values }); },
        }),
      ]),
      planField(values, "join"),
      el("p", { class: "tiny muted" }, "如果这个房间里已经有你用过的同一个昵称，会重新登录到你原来的进度，学习计划也不会被改掉。新加入的人默认学四级英语。"),
      el("div", { class: "btn-row" }, [
        el("button", {
          class: "btn btn-primary",
          type: "button",
          onClick: async () => {
            if (busy) return;
            busy = true;
            try {
              const res = await API.joinRoom({ code: values.code, name: values.name, studyPlan: values.studyPlan || "cet4" });
              API.setToken(res.token);
              state = res.state;
              session = null;
              toast(res.reclaimed ? "已回到原来的房间" : "加入成功，开始学习吧");
              go("home");
            } catch (err) {
              toast(err.message || "加入失败");
            } finally {
              busy = false;
            }
          },
        }, "加入房间"),
      ])
    );
    return form;
  }

  /* ---------- Home ---------- */
  function viewHome() {
    const me = state.me;
    const plan = me.plan || {};
    const wrap = el("div", { class: "view" });
    (state.banners || []).forEach((b) => {
      wrap.append(
        el("div", { class: "banner " + b.type }, [
          el("h2", {}, b.title),
          el("p", {}, b.text),
        ])
      );
    });
    if (me.checkinToday) {
      wrap.append(
        el("div", { class: "checkin-hero" }, [
          el("h2", {}, "今日已打卡"),
          el("p", {}, "连续学习 " + me.streak + " 天。朋友要是还没打卡，记得去催一下。"),
        ])
      );
    }
    wrap.append(
      el("div", { class: "greet" }, [
        el("div", { class: "hello" }, state.greeting),
        el("div", { class: "date" }, state.dateLabel),
      ]),
      duoCards(),
      el("div", { class: "card", style: { marginTop: "14px" } }, [
        el("div", { class: "card-title" }, [
          el("h2", {}, "今日任务"),
          el("span", { class: "side" }, me.checkinToday ? "已打卡" : plan.punishment ? "含惩罚任务" : ((plan.tracks || []).length > 1 ? "每门都完成才能打卡" : "完成才能打卡")),
        ]),
        ...((plan.tracks && plan.tracks.length) ? plan.tracks.map(trackBlock) : [
          taskRow("待复习单词", plan.dueDone, plan.dueTotal, null),
          taskRow("新词", plan.newDone, plan.newTotal, null),
          taskRow("做题", plan.quizDone, plan.quizTarget, null),
        ]),
        el("div", { class: "rule-box" }, plan.requirementText || "打卡规则：完成今天列出的复习、新词和题目，才算打卡。中断一天，连续学习会清零，第二天还要多做一份惩罚任务。"),
        el("div", { class: "rule-box" }, plan.memoryText || "每个词本轮答对 5 次才过关。过关后按 1、2、4、7、15、30 天复习。"),
      ]),
      inviteCard(),
      el("div", { class: "card", style: { marginTop: "14px" } }, [
        el("div", { class: "card-title" }, [el("h2", {}, "本周打卡"), el("span", { class: "side" }, "近 7 天")]),
        weekStrip(me.week || []),
      ])
    );
    return wrap;
  }

  function duoCards() {
    const me = state.me;
    const partner = state.partner;
    const ph = state.room && state.room.friendPlaceholder;
    return el("div", { class: "duo" }, [
      personCard("我", me, true),
      partner
        ? personCard("同伴", partner, false)
        : el("div", { class: "person" }, [
            el("div", { class: "who" }, "同伴"),
            el("div", { class: "nm" }, ph || "等待加入"),
            el("div", { class: "wait" }, "把邀请码发给朋友，两个人就可以互相监督了。"),
          ]),
    ]);
  }

  function personCard(who, p, isMe) {
    return el("div", { class: "person" + (isMe ? " me" : "") }, [
      el("div", { class: "who" }, who),
      el("div", { class: "nm" }, p.name),
      p.studyPlanLabel ? el("div", { class: "plan-line" }, p.studyPlanLabel) : null,
      el("div", { class: "row" }, [el("span", {}, "连续"), el("span", {}, p.streak + " 天")]),
      el("div", { class: "row" }, [el("span", {}, "积分"), el("span", {}, p.points + " · Lv." + p.level)]),
      p.checkinToday
        ? el("span", { class: "stamp yes" }, "今日已打卡")
        : el("span", { class: "stamp no" }, "今天还没打卡"),
      p.missedYesterday && !p.checkinToday ? el("span", { class: "stamp miss", style: { marginLeft: "4px" } }, "欠打卡") : null,
    ]);
  }

  function inviteCard() {
    const code = state.room && state.room.code;
    if (!code) return null;
    if (state.partner) {
      return el("div", { class: "card invite-mini", style: { marginTop: "14px" } }, [
        el("div", { class: "card-title" }, [el("h2", {}, "房间邀请码"), el("span", { class: "code" }, code)]),
        el("p", { class: "tiny muted" }, "两个人已经到齐。如果有人换了手机，用同一个昵称和这个邀请码就能回来。"),
      ]);
    }
    return el("div", { class: "card", style: { marginTop: "14px" } }, [
      el("h2", {}, "邀请朋友加入"),
      el("p", { class: "soft", style: { fontSize: "14px", marginTop: "6px" } }, "把下面这串邀请码发给朋友，让对方在首页选择「加入房间」。"),
      el("div", { class: "code-box" }, [
        el("div", { class: "code" }, code),
        el("button", {
          class: "btn btn-ghost",
          type: "button",
          style: { width: "auto", minHeight: "40px", padding: "8px 12px" },
          onClick: async () => {
            try {
              await navigator.clipboard.writeText(code);
              toast("邀请码已复制");
            } catch (e) {
              toast("复制失败，请手动抄写：" + code);
            }
          },
        }, "复制"),
      ]),
    ]);
  }

  function trackBlock(track) {
    const ko = track.id === "korean";
    const title = ko ? "韩语" : "四级英语";
    const quizName = ko ? "韩语小测" : "英语做题";
    const quizHint = track.quizTarget > 1
      ? track.quizDone + " / " + track.quizTarget + " 组（含惩罚，每组 " + track.quizSize + " 题）"
      : (track.quizComplete ? "今天已完成" : "1 组（" + track.quizSize + " 题）");
    return el("div", { class: "track-block" }, [
      el("h3", { class: "track-name" }, title),
      taskRow(title + "复习", track.dueDone, track.dueTotal, track.dueTotal === 0 ? "今日无需复习" : null),
      taskRow(title + "新词", track.newDone, track.newTotal, track.newTotal === 0 ? "暂无新词" : null),
      taskRow(quizName, track.quizDone, track.quizTarget, quizHint),
      trackActions(track),
    ]);
  }

  function trackActions(track) {
    const ko = track.id === "korean";
    const vocabLeft = (track.dueLeft || 0) + (track.newLeft || 0);
    return el("div", { class: "btn-row", style: { marginTop: "8px" } }, [
      el("button", {
        class: "btn " + (ko ? "btn-ghost" : "btn-primary"),
        type: "button",
        "data-track": track.id,
        onClick: () => startVocab(track.id),
      }, vocabLeft === 0 ? (ko ? "韩语单词已完成" : "英语单词已完成") : (ko ? "记韩语" : "记英语")),
      el("button", {
        class: "btn btn-ghost",
        type: "button",
        "data-track": track.id,
        onClick: () => startQuiz("normal", track.id),
      }, track.quizComplete ? (ko ? "再做一组韩语" : "再做一组英语") : (ko ? "韩语小测" : "做英语题")),
    ]);
  }

  function studyButtons(plan) {
    const tracks = (plan && plan.tracks) || [];
    const row = el("div", { class: "btn-row" });
    if (!tracks.length) {
      row.append(el("button", { class: "btn btn-primary", type: "button", onClick: () => startVocab("cet4") }, "开始记单词"));
      return row;
    }
    tracks.forEach((track) => {
      const ko = track.id === "korean";
      const vocabLeft = (track.dueLeft || 0) + (track.newLeft || 0);
      row.append(el("button", {
        class: "btn " + (ko ? "btn-ghost" : "btn-primary"),
        type: "button",
        onClick: () => startVocab(track.id),
      }, vocabLeft === 0 ? (ko ? "韩语单词已完成" : "英语单词已完成") : (ko ? "记韩语" : "记英语")));
      row.append(el("button", {
        class: "btn btn-ghost",
        type: "button",
        onClick: () => startQuiz("normal", track.id),
      }, track.quizComplete ? (ko ? "再做一组韩语" : "再做一组英语") : (ko ? "韩语小测" : "做英语题")));
    });
    return row;
  }

  function taskRow(name, done, total, extra) {
    total = total || 0;
    done = done || 0;
    const pct = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 100;
    const complete = total === 0 || done >= total;
    return el("div", { class: "task" + (complete ? " done" : "") }, [
      el("div", { class: "name" }, name),
      el("div", { class: "count" }, extra || done + " / " + total),
      el("div", { class: "bar" }, [el("span", { style: { width: pct + "%" } })]),
    ]);
  }

  function weekStrip(week) {
    return el(
      "div",
      { class: "week" },
      (week || []).map((d) =>
        el("div", { class: "day" + (d.isToday ? " today" : "") }, [
          el("div", { class: "label" }, d.label),
          el("div", { class: "dot" + (d.studied ? " on" : ""), title: d.date }),
        ])
      )
    );
  }

  /* ---------- Words ---------- */
  function viewWords() {
    const tab = (session && session.listTab) || "today";
    const wrap = el("div", { class: "view" });
    wrap.append(
      el("div", { class: "tabs", role: "tablist" }, [
        el("button", { type: "button", class: tab === "today" ? "on" : "", onClick: () => { session = Object.assign(session || {}, { listTab: "today" }); render(); } }, "今日学习"),
        el("button", { type: "button", class: tab === "list" ? "on" : "", onClick: () => { session = Object.assign(session || {}, { listTab: "list" }); render(); loadWordPage(true); } }, "词库"),
      ])
    );
    if (tab === "list") wrap.append(wordListPanel());
    else wrap.append(wordTodayPanel());
    return wrap;
  }

  function wordTodayPanel() {
    const plan = (state.me && state.me.plan) || {};
    const box = el("div", {});
    box.append(
      el("div", { class: "card" }, [
        el("div", { class: "card-title" }, [el("h2", {}, "今天的安排"), el("span", { class: "side" }, plan.punishment ? "含惩罚任务" : "复习优先")]),
        ...((plan.tracks && plan.tracks.length) ? plan.tracks.map((track) => el("div", { class: "track-block" }, [
          el("h3", { class: "track-name" }, track.id === "korean" ? "韩语" : "四级英语"),
          taskRow("复习", track.dueDone, track.dueTotal, track.dueTotal === 0 ? "今日无需复习" : null),
          taskRow("新词", track.newDone, track.newTotal, track.newTotal === 0 ? "暂无新词" : null),
          trackActions(track),
        ])) : [
          taskRow("复习", plan.dueDone, plan.dueTotal, null),
          taskRow("新词", plan.newDone, plan.newTotal, null),
          trackActions({ id: "cet4", dueLeft: plan.dueLeft, newLeft: plan.newLeft, quizComplete: plan.quizComplete, quizTarget: plan.quizTarget, quizSize: 10 }),
        ]),
      ]),
    );
    return box;
  }

  function wordListPanel() {
    const box = el("div", {});
    const q = listState.query || "";
    const filter = listState.filter || "全部";
    const langs = (function () {
      const tracks = (state && state.me && state.me.plan && state.me.plan.tracks) || [];
      const out = [];
      if (!tracks.length || tracks.some((t) => t.id === "cet4")) out.push(["en", "英语"]);
      if (tracks.some((t) => t.id === "korean")) out.push(["ko", "韩语"]);
      return out;
    })();
    if (!langs.some(([id]) => id === listState.lang)) listState.lang = (langs[0] && langs[0][0]) || "";
    if (langs.length > 1) {
      box.append(el("div", { class: "chips" }, langs.map(([id, label]) =>
        el("button", {
          type: "button",
          class: "chip" + (listState.lang === id ? " on" : ""),
          onClick: () => { listState.lang = id; listState.page = 1; loadWordPage(true); },
        }, label)
      )));
    }
    box.append(
      el("div", { class: "search" }, [
        el("span", { html: icon("search") }),
        el("input", {
          type: "search",
          placeholder: "搜索单词、读音或中文",
          value: q,
          "aria-label": "搜索单词",
          onChange: (e) => { listState.query = e.target.value; listState.page = 1; loadWordPage(true); },
          onKeydown: (e) => { if (e.key === "Enter") { listState.query = e.target.value; listState.page = 1; loadWordPage(true); } },
        }),
      ]),
      el(
        "div",
        { class: "chips" },
        ["全部", "新词", "学习中", "已掌握"].map((name) =>
          el("button", {
            type: "button",
            class: "chip" + (filter === name ? " on" : ""),
            onClick: () => { listState.filter = name; listState.page = 1; loadWordPage(true); },
          }, name)
        )
      )
    );
    box.append(el("p", { class: "muted tiny", style: { marginBottom: "6px" } }, "共 " + (listState.total || 0) + " 个词"));
    if (!listState.items.length) {
      box.append(el("div", { class: "empty" }, listState.loaded ? "没有找到匹配的单词。" : "正在加载词库…"));
    } else {
      const list = el("div", { class: "card", style: { padding: "4px 12px" } });
      listState.items.forEach((w) => {
        const cls = w.status === "已掌握" ? "mastered" : w.status === "学习中" ? "learning" : "new";
        list.append(
          el("button", { type: "button", class: "word-item", onClick: () => openWordDetail(w.id) }, [
            el("div", { class: "en" }, w.word),
            el("div", { class: "zh" }, w.meaning),
            el("span", { class: "badge " + cls }, w.status),
          ])
        );
      });
      box.append(list);
      const pages = Math.max(1, Math.ceil((listState.total || 0) / (listState.pageSize || 40)));
      box.append(
        el("div", { class: "pager" }, [
          el("button", { class: "btn btn-ghost", type: "button", style: { width: "auto" }, disabled: listState.page <= 1 ? true : null, onClick: () => { listState.page -= 1; loadWordPage(true); } }, "上一页"),
          el("span", {}, listState.page + " / " + pages),
          el("button", { class: "btn btn-ghost", type: "button", style: { width: "auto" }, disabled: listState.page >= pages ? true : null, onClick: () => { listState.page += 1; loadWordPage(true); } }, "下一页"),
        ])
      );
    }
    if (listState.lang !== "ko") {
      box.append(el("div", { class: "btn-row" }, [el("button", { class: "btn btn-ghost", type: "button", onClick: () => openAddWord() }, "添加自定义单词")]));
    }
    return box;
  }

  async function loadWordPage(andRender) {
    try {
      const data = await API.words({
        q: listState.query || "",
        status: listState.filter || "全部",
        page: listState.page || 1,
        pageSize: 40,
        lang: listState.lang || "",
      });
      listState.total = data.total;
      listState.page = data.page;
      listState.pageSize = data.pageSize;
      listState.items = data.items;
      listState.loaded = true;
      if (andRender && route().name === "words") render();
    } catch (err) {
      toast(err.message || "词库加载失败");
    }
  }

  async function startVocab(track) {
    try {
      const data = await API.session(track || "");
      let items = data.items || [];
      if (!items.length) {
        toast("今天这门没有要学的单词了。可以去词库里看，或明天再来。");
        return;
      }
      session = {
        listTab: "today",
        track: (items[0] && items[0].track) || track || "cet4",
        items,
        index: 0,
        flipped: false,
        againCounts: {},
        results: { know: 0, hard: 0, again: 0, points: 0 },
        done: false,
        recap: null,
      };
      go("words/session");
    } catch (err) {
      toast(err.message || "无法开始记单词");
    }
  }

  function currentCard() {
    if (!session || !session.items) return null;
    return session.items[session.index] || null;
  }

  function viewSession() {
    if (!session || !session.items) {
      return el("div", { class: "view" }, [
        el("p", {}, "请从今日任务里选择要学的一门。"),
        el("button", { class: "btn btn-primary", type: "button", onClick: () => go("home") }, "回到今日"),
      ]);
    }
    if (session.done) return viewRecap();
    const item = currentCard();
    if (!item) {
      finishSession();
      return el("div", { class: "view" }, "正在汇总…");
    }
    const total = session.items.length;
    const idx = session.index;
    const pct = Math.round((idx / total) * 100);
    const w = item.word;
    const langLabel = w.lang === "ko" ? "韩语" : "英语";
    const wrap = el("div", { class: "view" });
    wrap.append(
      el("button", { class: "back-link", type: "button", onClick: () => { session.listTab = "today"; go("words"); }, html: icon("back") + " 先离开" }),
        el("div", { class: "session-top" }, [
        el("span", {}, langLabel + "  ·  " + (item.kind === "new" ? "新词" : "复习") + "  ·  " + (idx + 1) + " / " + total),
        el("span", {}, "本轮 " + ((item.roundCorrect || 0) + "/" + (item.roundNeed || 5))),
      ]),
      el("div", { class: "session-bar" }, [el("span", { style: { width: pct + "%" } })])
    );
    const card = el("div", {
      class: "flashcard" + (session.flipped ? " flipped" : ""),
      role: "button",
      tabindex: "0",
      "aria-label": session.flipped ? "已显示释义" : "显示释义",
      onClick: () => flipCard(),
      onKeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); flipCard(); } },
    });
    card.append(
      el("div", { class: "face front" }, [
        el("div", { class: "kind-tag" }, (item.kind === "new" ? "新词" : "复习") + " · " + langLabel),
        el("div", { class: "en-word" + (w.lang === "ko" ? " ko" : "") }, w.word),
        readingBlock(w),
        roundBadge(item),
        el("div", { class: "hint" }, "先试着回忆它的意思，再点开卡片"),
      ]),
      el("div", { class: "face back" }, [
        el("div", { class: "kind-tag" }, (item.kind === "new" ? "新词" : "复习") + " · " + langLabel),
        el("div", { class: "en-word" + (w.lang === "ko" ? " ko" : "") }, w.word),
        readingBlock(w),
        roundBadge(item),
        el("div", { class: "meaning" }, w.meaning),
        exampleBlock(w),
      ])
    );
    wrap.append(el("div", { class: "flash-wrap" }, [card]));
    wrap.append(
      el("div", { class: "rate-row" + (session.flipped ? " show" : "") }, [
        rateBtn("again", "不认识", "计数清零"),
        rateBtn("hard", "模糊", "减 1 次"),
        rateBtn("know", "认识", "+1 次"),
      ])
    );
    return wrap;
  }

  function roundBadge(item) {
    const got = item.roundCorrect || 0;
    const need = item.roundNeed || 5;
    return el("div", { class: "round-badge" }, "本轮 " + got + "/" + need);
  }

  function flipCard() {
    if (!session || session.flipped) return;
    session.flipped = true;
    render();
  }
  function rateBtn(rating, label, sub) {
    return el("button", {
      type: "button",
      class: "rate " + rating,
      onClick: (e) => { e.stopPropagation(); rateCurrent(rating); },
    }, [label, el("small", {}, sub)]);
  }

  async function rateCurrent(rating) {
    const item = currentCard();
    if (!item || !session.flipped || busy) return;
    busy = true;
    try {
      const result = await API.rateWord(item.word.id, rating);
      session.results.points += result.gained || 0;
      if (rating === "know") session.results.know += 1;
      else if (rating === "hard") session.results.hard += 1;
      else session.results.again += 1;
      const id = item.word.id;
      session.items = session.items.filter((card, i) => i <= session.index || card.word.id !== id);
      if (!result.roundComplete) {
        session.items.push({
          word: item.word,
          kind: item.kind,
          track: item.track,
          punishment: item.punishment,
          roundCorrect: result.roundCorrect || 0,
          roundNeed: result.roundNeed || 5,
        });
      } else {
        const days = result.interval || 1;
        toast("过关 " + (result.roundNeed || 5) + "/" + (result.roundNeed || 5) + "，" + (days <= 1 ? "明天再复习" : days + " 天后再复习"));
      }
      announceCheckin(result.checkin);
      session.index += 1;
      session.flipped = false;
      if (session.index >= session.items.length) await finishSession();
      else render();
    } catch (err) {
      toast(err.message || "保存失败");
    } finally {
      busy = false;
    }
  }

  async function finishSession() {
    try {
      const extra = await API.completeVocab(session.track);
      if (extra && extra.plan && state && state.me) state.me.plan = extra.plan;
      if (extra && extra.checkin) announceCheckin(extra.checkin);
      await refreshState().catch(() => {});
    } catch (e) {}
    session.done = true;
    session.recap = { results: session.results };
    render();
  }

  function viewRecap() {
    const r = (session && session.recap && session.recap.results) || { know: 0, hard: 0, again: 0, points: 0 };
    const checked = state && state.me && state.me.checkinToday;
    const wrap = el("div", { class: "view" });
    wrap.append(
      el("div", { class: "recap-hero" }, [
        el("h1", {}, "这组练完了"),
        el("div", { class: "points-chip" }, "本轮 +" + (r.points || 0) + " 分"),
        checked ? el("p", { class: "soft", style: { marginTop: "8px" } }, "今日已打卡") : null,
      ]),
      el("div", { class: "recap-grid" }, [
        recapCell(r.know, "认识"),
        recapCell(r.hard, "模糊"),
        recapCell(r.again, "不认识"),
      ]),
      el("div", { class: "btn-row" }, [
        el("button", { class: "btn btn-primary", type: "button", onClick: () => { session = { listTab: "today" }; go("home"); } }, "回到今日"),
        el("button", { class: "btn btn-ghost", type: "button", onClick: () => startVocab(session.track) }, "再练一组"),
      ])
    );
    return wrap;
  }
  function recapCell(n, l) {
    return el("div", {}, [el("span", { class: "n" }, String(n)), el("span", { class: "l" }, l)]);
  }

  /* ---------- Quiz ---------- */
  function viewQuizHub() {
    const plan = (state.me && state.me.plan) || {};
    const tracks = plan.tracks || [];
    const wrong = (state.me && state.me.stats && state.me.stats.wrongCount) || 0;
    const wrap = el("div", { class: "view" });
    if (!tracks.length || tracks.some((t) => t.id === "cet4")) {
      const en = tracks.find((t) => t.id === "cet4");
      wrap.append(
        el("div", { class: "card" }, [
          el("h2", {}, "做一组四级题"),
          el("p", { class: "soft", style: { margin: "8px 0 0", fontSize: "14px" } }, "每次 10 题，从四级词库出词汇题，再加一些语法题。打卡需要完成 " + ((en && en.quizTarget) || 1) + " 组。答对会有积分奖励。"),
        ]),
        el("div", { class: "btn-row" }, [
          el("button", { class: "btn btn-primary", type: "button", onClick: () => startQuiz("normal", "cet4") }, "开始做英语题"),
        ])
      );
    }
    if (tracks.some((t) => t.id === "korean")) {
      const ko = tracks.find((t) => t.id === "korean");
      wrap.append(
        el("div", { class: "card", style: { marginTop: "14px" } }, [
          el("h2", {}, "韩语小测"),
          el("p", { class: "soft", style: { margin: "8px 0 0", fontSize: "14px" } }, "每次 " + ((ko && ko.quizSize) || 6) + " 题，只从韩语词库出题。它只计入韩语打卡，不会代替英语那一组。答对同样有奖励。"),
        ]),
        el("div", { class: "btn-row" }, [
          el("button", { class: "btn btn-primary", type: "button", onClick: () => startQuiz("normal", "korean") }, "开始韩语小测"),
        ])
      );
    }
    wrap.append(
      el("div", { class: "card", style: { marginTop: "16px" } }, [
        el("div", { class: "card-title" }, [el("h2", {}, "错题本"), el("span", { class: "side" }, wrong ? wrong + " 题" : "空")]),
        el("p", { class: "soft", style: { fontSize: "14px" } }, "同一道错题连续答对两次，就会从错题本里移除。"),
        el("div", { class: "btn-row" }, [
          el("button", { class: "btn btn-ghost", type: "button", disabled: wrong ? null : true, onClick: () => startQuiz("wrong", (tracks[0] && tracks[0].id) || "cet4") }, wrong ? "复习错题" : "暂时没有错题"),
        ]),
      ])
    );
    return wrap;
  }

  async function startQuiz(mode, track) {
    try {
      const data = await API.quiz(mode, track || "cet4");
      quizRun = {
        mode: data.mode || mode,
        track: data.track || track || "cet4",
        questions: data.questions || [],
        index: 0,
        locked: false,
        picked: null,
        answers: [],
        done: false,
        summary: null,
      };
      if (!quizRun.questions.length) {
        toast("暂时没有可以做的题目");
        return;
      }
      go("quiz/play");
    } catch (err) {
      toast(err.message || "无法出题");
    }
  }

  function viewQuizPlay() {
    if (!quizRun) {
      startQuiz("normal", "cet4");
      return el("div", { class: "view" }, "正在出题…");
    }
    if (quizRun.done) return viewQuizResult();
    const q = quizRun.questions[quizRun.index];
    if (!q) return el("div", { class: "view" }, "正在汇总…");
    const speak = questionSpeak(q);
    const promptIsWord = !!(speak && PROMPT_WORD_TYPES[q.type]);
    const wrap = el("div", { class: "view" });
    const head = [
      el("button", { class: "back-link", type: "button", onClick: () => { quizRun = null; go("quiz"); }, html: icon("back") + " 先离开" }),
      el("div", { class: "q-progress" }, (quizRun.mode === "wrong" ? "错题复习  ·  " : "") + (quizRun.index + 1) + " / " + quizRun.questions.length),
      el("div", { class: "session-bar" }, [el("span", { style: { width: Math.round((quizRun.index / quizRun.questions.length) * 100) + "%" } })]),
      el("div", { class: "q-type" }, TYPE_LABEL[q.type] || "练习"),
      el("div", { class: "q-prompt" + (q.type === "en2zh" || q.type === "zh2en" ? " serif" : "") }, q.prompt),
    ];
    if (promptIsWord) head.push(readingBlock(speak, "quiz-reading"));
    if (q.promptNote) head.push(el("div", { class: "q-note" }, q.promptNote));
    wrap.append(...head);
    const choices = el("div", { class: "choices" });
    (q.choices || []).forEach((text, i) => {
      let stateCls = "";
      if (quizRun.locked) {
        if (i === q.answer) stateCls = "correct";
        else if (i === quizRun.picked && i !== q.answer) stateCls = "wrong";
        else stateCls = "dim";
      }
      const btn = el("button", {
        type: "button",
        class: "choice" + (stateCls ? " " + stateCls : ""),
        disabled: quizRun.locked ? true : null,
        onClick: () => pickChoice(i),
      }, text);
      const spoken = choiceSpeakAt(q, i);
      if (spoken) {
        choices.append(el("div", { class: "choice-wrap" + (stateCls ? " " + stateCls : "") }, [
          btn,
          choicePronounce(spoken),
        ]));
      } else {
        choices.append(btn);
      }
    });
    wrap.append(choices);
    if (quizRun.locked) {
      const ok = quizRun.picked === q.answer;
      const feedback = [
        el("div", { class: "feedback " + (ok ? "ok" : "no") }, (ok ? "答对了。" : "还差一点。") + " " + (q.explain || "")),
      ];
      if (speak) feedback.push(readingBlock(speak, "quiz-reading", true));
      if (ok) feedback.push(rewardBurst());
      feedback.push(el("div", { class: "btn-row" }, [
        el("button", { class: "btn btn-primary", type: "button", onClick: nextQuestion }, quizRun.index + 1 >= quizRun.questions.length ? "查看成绩" : "下一题"),
      ]));
      wrap.append(...feedback);
    }
    return wrap;
  }

  function pickChoice(i) {
    if (!quizRun || quizRun.locked) return;
    const q = quizRun.questions[quizRun.index];
    quizRun.locked = true;
    quizRun.picked = i;
    quizRun.answers.push({ id: q.id, correct: i === q.answer, picked: i, snapshot: q });
    render();
  }

  async function nextQuestion() {
    if (!quizRun) return;
    quizRun.index += 1;
    quizRun.locked = false;
    quizRun.picked = null;
    if (quizRun.index >= quizRun.questions.length) await endQuiz();
    else render();
  }

  async function endQuiz() {
    try {
      const summary = await API.submitQuiz(quizRun.mode, quizRun.answers, quizRun.track);
      quizRun.done = true;
      quizRun.summary = summary;
      announceCheckin(summary.checkin);
      await refreshState().catch(() => {});
    } catch (err) {
      toast(err.message || "提交失败");
      quizRun.done = true;
      quizRun.summary = { correct: quizRun.answers.filter((a) => a.correct).length, total: quizRun.answers.length, gained: 0 };
    }
    render();
  }

  function viewQuizResult() {
    const s = quizRun.summary || { correct: 0, total: 0, gained: 0 };
    const misses = quizRun.answers.filter((a) => !a.correct);
    const wrap = el("div", { class: "view" });
    wrap.append(
      el("div", { class: "recap-hero" }, [
        el("h1", {}, s.correct === s.total ? "全部答对了" : "这组做完了"),
        el("p", { class: "soft", style: { marginTop: "8px" } }, "答对 " + s.correct + " / " + s.total),
        el("div", { class: "points-chip" }, "本轮 +" + (s.gained || 0) + " 分"),
        state && state.me && state.me.checkinToday ? el("p", { class: "soft", style: { marginTop: "8px" } }, "今日已打卡") : null,
      ])
    );
    if (misses.length) {
      const list = el("ul", { class: "miss-list" });
      misses.forEach((a) => {
        const q = a.snapshot;
        const speak = questionSpeak(q);
        list.append(
          el("li", {}, [
            el("div", { class: "q" }, q.prompt),
            el("div", { class: "b" }, "你的答案：" + (q.choices[a.picked] ?? "未选")),
            el("div", { class: "a" }, "正确答案：" + q.choices[q.answer]),
            speak ? readingBlock(speak, "quiz-reading", true) : null,
            q.explain ? el("div", { class: "soft", style: { marginTop: "4px" } }, q.explain) : null,
          ])
        );
      });
      wrap.append(el("div", { class: "card", style: { marginTop: "16px" } }, [el("h2", {}, "错过的题"), list]));
    }
    wrap.append(
      el("div", { class: "btn-row", style: { marginTop: "16px" } }, [
        el("button", { class: "btn btn-primary", type: "button", onClick: () => { quizRun = null; go("home"); } }, "回到今日"),
        el("button", { class: "btn btn-ghost", type: "button", onClick: () => startQuiz(quizRun.mode, quizRun.track) }, "再做一组"),
      ])
    );
    return wrap;
  }

  /* ---------- Progress / settings ---------- */
  function viewProgress() {
    const st = (state.me && state.me.stats) || {};
    const wrap = el("div", { class: "view" });
    wrap.append(
      el("div", { class: "card level-card" }, [
        el("div", { class: "lv" }, "Lv. " + (st.level || 1)),
        el("div", { class: "pts" }, "累计 " + (st.totalPoints || 0) + " 分 · 距下一级还差 " + (st.toNext || 100) + " 分"),
        el("div", { class: "bar", style: { height: "8px" } }, [el("span", { style: { width: (st.intoBar || 0) + "%" } })]),
        el("p", { class: "tiny muted", style: { marginTop: "10px" } }, "每 100 分升一级"),
      ]),
      el("div", { class: "card" }, [
        el("div", { class: "card-title" }, [el("h2", {}, "连续打卡"), el("span", { class: "side" }, (st.streak || 0) + " 天")]),
        weekStrip((state.me && state.me.week) || []),
        el("p", { class: "tiny muted", style: { marginTop: "10px" } }, "完成当天的复习、新词和做题并成功打卡，才会记入连续学习。中断一天会重新开始。"),
      ]),
      el("div", { class: "stat-list", style: { margin: "14px 0" } }, [
        statBox("已开始的单词", String(st.started || 0)),
        statBox("已掌握", String(st.mastered || 0)),
        statBox("完成的练习", String(st.quizzes || 0) + " 组"),
        statBox("做题正确率", st.accuracy == null ? "—" : st.accuracy + "%"),
        statBox("今日积分", String(st.todayPoints || 0)),
        statBox("错题本", String(st.wrongCount || 0) + " 题"),
      ]),
      el("div", { class: "card" }, [
        el("h2", {}, "记忆方法"),
        el("p", { class: "soft", style: { fontSize: "14px", marginTop: "8px" } }, (state.me && state.me.plan && state.me.plan.memoryText) || "每个词本轮答对 5 次才过关，之后按 1、2、4、7、15、30 天复习。"),
      ]),
      el("div", { class: "card" }, [
        el("div", { class: "card-title" }, [el("h2", {}, "积分规则")]),
        el("ul", { class: "rules" }, [
          rule("单词评为「认识」", "+8"),
          rule("单词评为「模糊」", "+3"),
          rule("单词评为「不认识」", "+1"),
          rule("做题答对（含奖励）", "+" + quizPoints()),
          rule("做题答错", "不加分"),
          rule("完成打卡（每天一次）", "+30"),
          rule("连续打卡满 3 / 7 / 14 天（各奖励一次）", "+15 / +30 / +50"),
        ]),
      ])
    );
    return wrap;
  }
  function statBox(k, v) { return el("div", { class: "stat-box" }, [el("div", { class: "k" }, k), el("div", { class: "v" }, v)]); }
  function rule(k, v) { return el("li", {}, [el("span", {}, k), el("span", { class: "pts" }, v)]); }

  function viewSettings() {
    const me = state.me;
    const wrap = el("div", { class: "view" });
    wrap.append(
      el("button", { class: "back-link", type: "button", onClick: () => go("progress"), html: icon("back") + " 返回进度" }),
      el("h1", { style: { fontSize: "24px", marginBottom: "12px" } }, "设置"),
      el("div", { class: "card" }, [
        el("h2", {}, "房间"),
        el("p", { class: "soft", style: { fontSize: "14px", margin: "8px 0" } }, "邀请码：" + ((state.room && state.room.code) || "—")),
        fieldText("我的昵称", "name", me.name, 16),
        el("label", { class: "field" }, [
          "惩罚约定",
          el("textarea", {
            onChange: (e) => saveSettings({ punishmentText: e.target.value }),
          }, (state.room && state.room.punishmentText) || ""),
        ]),
      ]),
      el("div", { class: "card" }, [
        el("h2", {}, "学习计划"),
        (function () {
          const current = me.studyPlan || "cet4";
          const select = el("select", { onChange: (e) => saveSettings({ studyPlan: e.target.value }) });
          [["cet4", "四级英语"], ["korean", "韩语入门"], ["both", "四级英语 + 韩语"]].forEach(([id, label]) => {
            select.append(el("option", { value: id, selected: current === id ? true : null }, label));
          });
          return el("label", { class: "field" }, ["当前计划", select]);
        })(),
        el("p", { class: "tiny muted" }, "默认是四级英语。改成韩语或两门一起，只影响你自己，同伴和房间人数不变。今天还没开始的那一门，会按新计划重算。"),
      ]),
      el("div", { class: "card" }, [
        el("h2", {}, "每天的学习量"),
        fieldNum("每日新词数量（四级英语）", "dailyNew", me.settings.dailyNew, 5, 40),
        fieldNum("每日复习上限（四级英语）", "reviewCap", me.settings.reviewCap, 5, 80),
        el("p", { class: "tiny muted" }, "复习排在新词前面，都要做完才能打卡。每个词要在本轮答对 5 次才过关。英语若昨天没打卡，第二天会多 20 个新词、多一组题。韩语每天 8 个新词、复习最多 24 个，小测每组 6 题；没打卡时韩语再加 8 个新词和一组小测。"),
      ]),
      el("div", { class: "card" }, [
        el("h2", {}, "打卡提醒"),
        el("p", { class: "soft", style: { fontSize: "14px", margin: "8px 0 12px" } }, "打开浏览器通知后，打开网站时如果同伴昨天没打卡，会提醒你一次。不会把消息发到房间以外。"),
        el("button", {
          class: "btn btn-ghost",
          type: "button",
          onClick: () => {
            if (!("Notification" in window)) { toast("这个浏览器不支持通知"); return; }
            Notification.requestPermission().then((p) => {
              toast(p === "granted" ? "已打开提醒" : "没有获得通知权限");
              if (p === "granted") maybeNotify(state);
            });
          },
        }, "打开打卡提醒"),
      ]),
      el("div", { class: "card" }, [
        el("h2", {}, "备份与恢复"),
        el("p", { class: "soft", style: { fontSize: "14px", margin: "8px 0 12px" } }, "学习进度保存在这台学习站的服务器里。导出后可以在同一房间里恢复自己的进度。"),
        el("div", { class: "btn-row two" }, [
          el("button", { class: "btn btn-ghost", type: "button", onClick: exportData }, "导出 JSON"),
          el("button", { class: "btn btn-ghost", type: "button", onClick: () => document.getElementById("import-file").click() }, "导入 JSON"),
        ]),
        el("input", { id: "import-file", type: "file", accept: "application/json,.json", style: { display: "none" }, onChange: importFile }),
      ]),
      el("div", { class: "card" }, [
        el("h2", {}, "重置与退出"),
        el("p", { class: "soft", style: { fontSize: "14px", margin: "8px 0 12px" } }, "重置只会清空你自己的单词进度、错题和积分，不会解散房间，也不会影响同伴。"),
        el("div", { class: "btn-row" }, [
          el("button", { class: "btn btn-danger", type: "button", onClick: confirmReset }, "重置我的学习数据"),
          el("button", { class: "btn btn-ghost", type: "button", onClick: logout }, "退出本机登录"),
        ]),
      ])
    );
    return wrap;
  }

  function fieldText(label, key, value, max) {
    return el("label", { class: "field" }, [
      label,
      el("input", {
        type: "text",
        value: value || "",
        maxlength: String(max || 16),
        onChange: (e) => saveSettings({ [key]: e.target.value }),
      }),
    ]);
  }
  function fieldNum(label, key, value, min, max) {
    return el("label", { class: "field" }, [
      label,
      el("input", {
        type: "number",
        min: String(min),
        max: String(max),
        value: String(value),
        onChange: (e) => {
          const n = Number(e.target.value);
          if (!Number.isFinite(n)) return;
          saveSettings({ [key]: n });
        },
      }),
    ]);
  }
  async function saveSettings(partial) {
    try {
      state = await API.saveSettings(partial);
      toast("已保存");
      render();
    } catch (err) {
      toast(err.message || "保存失败");
    }
  }
  async function exportData() {
    try {
      const data = await API.exportData();
      const blob = new Blob([JSON.stringify({ app: "请叫我学习", data }, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "jinbu-progress-" + (state.today || "backup") + ".json";
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
      toast("已导出备份文件");
    } catch (err) {
      toast(err.message || "导出失败");
    }
  }
  function importFile(e) {
    const file = e.target.files && e.target.files[0];
    e.target.value = "";
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async () => {
      try {
        const parsed = JSON.parse(String(reader.result || ""));
        state = await API.importData(parsed);
        toast("已恢复备份");
        render();
      } catch (err) {
        toast(err.message || "导入失败");
      }
    };
    reader.readAsText(file, "utf-8");
  }
  function confirmReset() {
    openSheet("重置我的学习数据？", [
      el("p", { class: "soft", style: { fontSize: "14px" } }, "单词进度、错题本、积分和连续打卡都会清空。房间和同伴不受影响。"),
      el("div", { class: "btn-row", style: { marginTop: "16px" } }, [
        el("button", {
          class: "btn btn-danger",
          type: "button",
          onClick: async () => {
            try {
              state = await API.reset();
              closeSheet();
              session = null;
              quizRun = null;
              toast("已重置");
              go("home");
            } catch (err) {
              toast(err.message || "重置失败");
            }
          },
        }, "确认重置"),
        el("button", { class: "btn btn-ghost", type: "button", onClick: closeSheet }, "取消"),
      ]),
    ]);
  }
  function logout() {
    API.setToken("");
    state = null;
    session = { gateTab: "join" };
    toast("已退出本机登录");
    go("gate");
    render();
  }

  /* sheets */
  function closeSheet() {
    const bg = document.getElementById("sheet-root");
    if (bg) bg.remove();
  }
  function openSheet(title, body) {
    closeSheet();
    const bg = el("div", { id: "sheet-root", class: "sheet-bg", onClick: (e) => { if (e.target.id === "sheet-root") closeSheet(); } });
    const sheet = el("div", { class: "sheet", role: "dialog", "aria-label": title }, [el("div", { class: "grab" }), el("h2", { style: { marginBottom: "10px" } }, title)]);
    body.forEach((n) => sheet.append(n));
    bg.append(sheet);
    document.body.append(bg);
  }

  async function openWordDetail(id) {
    try {
      const data = await API.wordDetail(id);
      const w = data.word;
      const rec = data.progress;
      const kids = [
        el("div", { class: "detail-word" + (w.lang === "ko" ? " ko" : "") }, w.word),
        readingBlock(w),
        el("div", { class: "meaning", style: { marginTop: "10px" } }, w.meaning),
        exampleBlock(w),
        el("p", { class: "muted", style: { marginTop: "14px", fontSize: "13px" } },
          "状态：" + data.status +
          "  ·  本轮 " + ((rec && rec.round_correct) || 0) + "/5" +
          (rec && rec.reps ? "  ·  已过关 " + rec.reps + " 轮" : "  ·  还没有过关") +
          (rec && rec.interval_days ? "  ·  下次间隔 " + rec.interval_days + " 天" : "  ·  过关后从明天开始复习")
        ),
      ];
      if (w.custom) {
        kids.push(
          el("div", { class: "btn-row two", style: { marginTop: "16px" } }, [
            el("button", { class: "btn btn-ghost", type: "button", onClick: () => { closeSheet(); openAddWord(w); } }, "编辑"),
            el("button", { class: "btn btn-danger", type: "button", onClick: async () => {
              if (!confirm("删除这个自定义单词？")) return;
              await API.deleteWord(w.id);
              closeSheet();
              toast("已删除");
              loadWordPage(true);
            } }, "删除"),
          ])
        );
      }
      openSheet("单词详情", kids);
    } catch (err) {
      toast(err.message || "无法打开单词");
    }
  }

  function openAddWord(existing) {
    const values = Object.assign({ word: "", ipa: "", meaning: "", example: "", exampleZh: "" }, existing || {});
    const form = el("div", {});
    [
      ["word", "英文单词", "input"],
      ["ipa", "音标（可选）", "input"],
      ["meaning", "中文意思", "input"],
      ["example", "英文例句（可选）", "textarea"],
      ["exampleZh", "例句翻译（可选）", "textarea"],
    ].forEach(([key, label, typ]) => {
      form.append(
        el("label", { class: "field" }, [
          label,
          typ === "textarea"
            ? el("textarea", { onInput: (e) => { values[key] = e.target.value; } }, values[key] || "")
            : el("input", { type: "text", value: values[key] || "", onInput: (e) => { values[key] = e.target.value; } }),
        ])
      );
    });
    form.append(
      el("div", { class: "btn-row", style: { marginTop: "8px" } }, [
        el("button", {
          class: "btn btn-primary",
          type: "button",
          onClick: async () => {
            try {
              if (existing) await API.updateWord(existing.id, values);
              else await API.addWord(values);
              closeSheet();
              toast(existing ? "已保存" : "已加入词库");
              listState.page = 1;
              loadWordPage(true);
            } catch (err) {
              toast(err.message || "保存失败");
            }
          },
        }, existing ? "保存修改" : "添加单词"),
        el("button", { class: "btn btn-ghost", type: "button", onClick: closeSheet }, "取消"),
      ])
    );
    openSheet(existing ? "编辑单词" : "添加自定义单词", [form]);
  }

  /* ---------- render / boot ---------- */
  async function render() {
    const authed = Boolean(API.getToken() && state);
    const r = route();
    if (!authed) {
      renderChrome("gate", false);
      $app.innerHTML = "";
      $app.append(viewGate());
      return;
    }
    let view;
    let active = r.name;
    if (r.name === "words" && r.parts[1] === "session") {
      active = "session";
      view = viewSession();
    } else if (r.name === "quiz" && r.parts[1] === "play") {
      active = "play";
      view = viewQuizPlay();
    } else if (r.name === "words") {
      view = viewWords();
    } else if (r.name === "quiz") {
      view = viewQuizHub();
    } else if (r.name === "progress") {
      view = viewProgress();
    } else if (r.name === "settings") {
      active = "settings";
      view = viewSettings();
    } else if (r.name === "gate") {
      go("home");
      view = viewHome();
      active = "home";
    } else {
      active = "home";
      view = viewHome();
    }
    renderChrome(active, true);
    $app.innerHTML = "";
    $app.append(view);
    window.scrollTo(0, 0);
  }

  async function boot() {
    try {
      meta = await API.meta();
    } catch (e) {
      meta = { defaultPunishment: "昨天没打卡的人，要被催，并且下一天要多做一份惩罚任务" };
    }
    if (API.getToken()) {
      try {
        await refreshState();
        requestNotifySoft();
      } catch (err) {
        if (err.auth) {
          state = null;
        } else {
          toast(err.message || "无法连接到学习站");
        }
      }
    }
    if (!location.hash) location.hash = API.getToken() && state ? "#/home" : "#/gate";
    await render();
    window.addEventListener("hashchange", () => { render(); });
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible" && API.getToken()) {
        refreshState().then(() => render()).catch(() => {});
      }
    });
    if (window.speechSynthesis && window.speechSynthesis.getVoices) {
      window.speechSynthesis.getVoices();
      window.speechSynthesis.onvoiceschanged = () => window.speechSynthesis.getVoices();
    }
    if ("serviceWorker" in navigator && location.protocol !== "file:") {
      navigator.serviceWorker.register("./sw.js").catch(() => {});
    }
  }

  boot();
})();
