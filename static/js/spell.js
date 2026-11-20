/* English spelling check for word practice. Korean cards do not use this. */
(function (root) {
  function trimWord(word) {
    return String(word || "").trim();
  }

  function foldSpell(value) {
    return String(value || "").trim().replace(/\s+/g, "").toLowerCase();
  }

  function hintLength(word) {
    const text = trimWord(word);
    if (!text) return 0;
    return text.length <= 3 ? 1 : 3;
  }

  function hintText(word) {
    const text = trimWord(word);
    return text.slice(0, hintLength(text));
  }

  function isCorrect(word, typed) {
    const target = foldSpell(word);
    const attempt = foldSpell(typed);
    if (!target || !attempt) return false;
    if (attempt === target) return true;
    const hint = foldSpell(hintText(word));
    const rest = target.slice(hint.length);
    return rest.length > 0 && attempt === rest;
  }

  root.JinbuSpell = { foldSpell, hintLength, hintText, isCorrect };
})(typeof globalThis !== "undefined" ? globalThis : this);
