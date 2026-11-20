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

assert(spell.hintText("appect") === "app", "appect hint");
assert(spell.hintText("accept") === "acc", "accept hint");
assert(spell.hintText("appear") === "app", "appear hint");
assert(spell.hintLength("more") === 3, "more length");
assert(spell.hintText("one") === "o", "one hint");
assert(spell.hintText("cat") === "c", "cat hint");
assert(spell.hintText("be") === "b", "be hint");
assert(spell.hintText("a") === "a", "a hint");
assert(spell.hintText("  go ") === "g", "trimmed short hint");

assert(spell.isCorrect("appear", "ear"), "rest of appear");
assert(spell.isCorrect("appear", "appear"), "full appear");
assert(spell.isCorrect("appear", " Appear "), "case and trim");
assert(spell.isCorrect("appear", "app ear"), "accidental spaces");
assert(spell.isCorrect("APPEAR", "ear"), "uppercase target");
assert(!spell.isCorrect("appear", "app"), "hint alone is not enough");
assert(!spell.isCorrect("appear", ""), "empty");
assert(!spell.isCorrect("appear", "   "), "spaces only");
assert(!spell.isCorrect("appear", "apple"), "wrong word");

assert(spell.isCorrect("cat", "at"), "short rest");
assert(spell.isCorrect("cat", "cat"), "short full");
assert(spell.isCorrect("cat", "C AT"), "short spaces");
assert(!spell.isCorrect("cat", "c"), "short hint alone");
assert(spell.isCorrect("be", "e"), "two-letter rest");
assert(spell.isCorrect("be", "be"), "two-letter full");
assert(spell.isCorrect("a", "a"), "one letter is the whole word");
assert(!spell.isCorrect("a", ""), "one letter still needs typing");

assert(spell.isCorrect("well-known", "l-known"), "hyphen rest");
assert(spell.isCorrect("well-known", "Well-Known"), "hyphen full");
assert(!spell.isCorrect("well-known", "wel"), "hyphen hint alone");

console.log("spell checks ok");
