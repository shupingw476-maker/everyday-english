const fs = require("fs");
const vm = require("vm");
const path = require("path");

const context = {};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(
  fs.readFileSync(path.join(__dirname, "../static/js/spell.js"), "utf8"),
  context
);
const spell = context.JinbuSpell;

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

function patterns(word) {
  const chars = [...word.trim()];
  return spell.masksFor(chars).map((_, i) => spell.hintFor(word, i).pattern);
}

function hiddenCount(pattern) {
  return [...pattern].filter((ch) => ch === spell.DASH).length;
}

for (const word of ["more", "accept", "appear", "one", "cat", "be"]) {
  const all = patterns(word);
  assert(all.length > 1 || word.length <= 1, word + " should vary when long enough: " + all.join(" | "));
  const unique = new Set(all);
  if (word.length > 3) assert(unique.size > 1, word + " hints collapsed: " + all.join(" | "));
  for (const pattern of all) {
    assert(pattern.length === [...word].length, word + " pattern length " + pattern);
    assert(!pattern.includes(word), word + " pattern revealed the word: " + pattern);
    assert(hiddenCount(pattern) >= 1, word + " hid nothing: " + pattern);
    const hint = spell.hintFor(word, all.indexOf(pattern));
    assert(spell.isCorrect(word, word, hint.missing), "full " + word);
    assert(spell.isCorrect(word, "  " + word.toUpperCase() + "  ", hint.missing), "case and trim " + word);
    assert(spell.isCorrect(word, word.split("").join(" "), hint.missing), "spaces " + word);
    if (hint.missing) assert(spell.isCorrect(word, hint.missing, hint.missing), "missing letters " + pattern);
    assert(!spell.isCorrect(word, "", hint.missing), "empty");
    assert(!spell.isCorrect(word, "zzz", hint.missing), "wrong " + word);
  }
}

const more = patterns("more");
assert(more.some((p) => p.includes(spell.DASH) && p !== "mor—"), "more is not only a prefix: " + more.join(" | "));
assert(more.includes("m—r—"), "more cloze m—r— missing from " + more.join(" | "));

const accept = patterns("accept");
assert(accept.some((p) => p.startsWith("acc")), "accept prefix: " + accept.join(" | "));
assert(accept.includes("a—c—pt"), "accept cloze: " + accept.join(" | "));

const appear = patterns("appear");
assert(appear.includes("—ppe—r"), "appear cloze: " + appear.join(" | "));

const five = patterns("apple");
assert(five.includes("a—p——"), "five-letter cloze: " + five.join(" | "));

for (const word of ["one", "cat", "be"]) {
  for (const pattern of patterns(word)) {
    const shown = [...pattern].filter((ch) => ch !== spell.DASH).length;
    assert(shown === 1, word + " should reveal one letter, got " + pattern);
  }
}

const single = spell.hintFor("a", 0);
assert(single.pattern === "—", "one letter stays hidden");
assert(spell.isCorrect("a", "A", single.missing), "type the single letter");

console.log("spell checks ok");
console.log("more", more.join(" "));
console.log("accept", accept.join(" "));
console.log("appear", appear.join(" "));
