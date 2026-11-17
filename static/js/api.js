/* 请叫我学习 · API 封装。登录凭证只保存在本机。 */
(function (global) {
  const TOKEN_KEY = "jinbu.room.token";

  function getToken() {
    return localStorage.getItem(TOKEN_KEY) || "";
  }
  function setToken(token) {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  }

  async function api(path, opts) {
    opts = opts || {};
    const headers = Object.assign({ Accept: "application/json" }, opts.headers || {});
    if (opts.body != null && !(opts.body instanceof FormData) && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }
    const token = getToken();
    if (token) headers.Authorization = "Bearer " + token;
    const res = await fetch(path, {
      method: opts.method || "GET",
      headers,
      body: opts.body == null ? undefined : typeof opts.body === "string" ? opts.body : JSON.stringify(opts.body),
    });
    let data = null;
    const text = await res.text();
    if (text) {
      try {
        data = JSON.parse(text);
      } catch (e) {
        data = { error: text };
      }
    }
    if (res.status === 401) {
      setToken("");
      const err = new Error((data && data.error) || "请先加入房间");
      err.auth = true;
      throw err;
    }
    if (!res.ok) {
      const err = new Error((data && data.error) || "请求失败");
      err.status = res.status;
      throw err;
    }
    return data;
  }

  global.API = {
    TOKEN_KEY,
    getToken,
    setToken,
    api,
    meta: () => api("/api/meta"),
    state: () => api("/api/state"),
    createRoom: (body) => api("/api/rooms", { method: "POST", body }),
    joinRoom: (body) => api("/api/rooms/join", { method: "POST", body }),
    saveSettings: (body) => api("/api/settings", { method: "PATCH", body }),
    session: (track) => api("/api/session" + (track ? "?track=" + encodeURIComponent(track) : "")),
    rateWord: (wordId, rating) => api("/api/vocab/rate", { method: "POST", body: { wordId, rating } }),
    completeVocab: (track) => api("/api/vocab/complete", { method: "POST", body: { track: track || null } }),
    quiz: (mode, track) => api("/api/quiz?mode=" + encodeURIComponent(mode || "normal") + "&track=" + encodeURIComponent(track || "cet4")),
    submitQuiz: (mode, answers, track) => api("/api/quiz/submit", { method: "POST", body: { mode, answers, track: track || "cet4" } }),
    checkin: () => api("/api/checkin", { method: "POST", body: {} }),
    words: (params) => {
      const q = new URLSearchParams(params || {}).toString();
      return api("/api/words" + (q ? "?" + q : ""));
    },
    wordDetail: (id) => api("/api/words/" + encodeURIComponent(id)),
    addWord: (body) => api("/api/words", { method: "POST", body }),
    updateWord: (id, body) => api("/api/words/" + encodeURIComponent(id), { method: "PATCH", body }),
    deleteWord: (id) => api("/api/words/" + encodeURIComponent(id), { method: "DELETE" }),
    exportData: () => api("/api/export"),
    importData: (payload) => api("/api/import", { method: "POST", body: payload }),
    reset: () => api("/api/reset", { method: "POST", body: {} }),
  };
})(window);
