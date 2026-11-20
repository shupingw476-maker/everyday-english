/* English spelling hints. Korean cards do not use this. */
(function (root) {
  const DASH = "—";

  function trimWord(word) {
    return String(word || "").trim();
  }

  function foldSpell(value) {
    return String(value || "").trim().replace(/\s+/g, "").toLowerCase();
  }

  function charsOf(word) {
    return [...trimWord(word)];
  }

  function maskToPattern(chars, show) {
    return chars.map((ch, i) => (show[i] ? ch : DASH)).join("");
  }

  function missingFrom(chars, show) {
    return chars.filter((_, i) => !show[i]).join("");
  }

  function usable(show) {
    return show.some(Boolean) && show.some((bit) => !bit);
  }

  function masksFor(chars) {
    const n = chars.length;
    const show = (pred) => chars.map((_, i) => pred(i));
    const found = [];
    const add = (mask) => {
      if (usable(mask) && !found.some((old) => old.every((bit, i) => bit === mask[i]))) found.push(mask);
    };
    if (n <= 1) {
      return [chars.map(() => false)];
    }
    if (n <= 3) {
      for (let i = 0; i < n; i++) add(show((j) => j === i));
      return found;
    }
    add(show((i) => i < 2));
    add(show((i) => i < Math.min(3, n - 1)));
    add(show((i) => i >= n - 2));
    add(show((i) => i === 0 || i === n - 1));
    add(show((i) => i % 2 === 0));
    add(show((i) => i % 2 === 1));
    add(show((i) => i === 0 || i === 2));
    if (n >= 6) {
      add(show((i) => i !== 1 && i !== 3));
      const start = 1;
      const end = Math.min(n - 2, start + 2);
      add(show((i) => (i >= start && i <= end) || i === n - 1));
    }
    return found.length ? found : [show((i) => i === 0)];
  }

  function hintFor(word, salt) {
    const chars = charsOf(word);
    if (!chars.length) return { pattern: "", missing: "" };
    const masks = masksFor(chars);
    const n = Math.abs(Number(salt) || 0) % masks.length;
    const show = masks[n];
    return {
      pattern: maskToPattern(chars, show),
      missing: missingFrom(chars, show),
    };
  }

  function isCorrect(word, typed, missing) {
    const target = foldSpell(word);
    const attempt = foldSpell(typed);
    if (!target || !attempt) return false;
    if (attempt === target) return true;
    const rest = foldSpell(missing);
    return rest.length > 0 && rest !== target && attempt === rest;
  }

  root.JinbuSpell = {
    DASH,
    foldSpell,
    hintFor,
    masksFor,
    isCorrect,
  };
})(typeof globalThis !== "undefined" ? globalThis : this);
