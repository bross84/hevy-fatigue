// Week text helpers shared by the builder and the Log page. Pure functions; no network or storage.
// The notation itself is read on the server (week_text.py); this file only finds the "#" being typed
// and writes a movement's planned sets back in the same notation, for labels.
(function (root) {
  "use strict";
  // A "#" search is open while the caret sits after "#" on the same line and no sets have started yet.
  const SETS_STARTED = /\s(?:(?:ME|RE)\s+)?(?:\d+\s*[x×]\s*\d|myo\b)/i;
  function hashQuery(text, caret) {
    const lineStart = text.lastIndexOf("\n", caret - 1) + 1, before = text.slice(lineStart, caret);
    const hash = before.indexOf("#");
    if (hash < 0 || before.slice(0, hash).trim()) return null;
    const query = before.slice(hash + 1);
    if (SETS_STARTED.test(" " + query)) return null;
    return { start: lineStart + hash, query };
  }
  // Replace "#query" up to the caret with "#Title " and return the new text and caret position.
  function insertMovement(text, caret, found, title) {
    const head = text.slice(0, found.start) + "#" + title + " ";
    return { text: head + text.slice(caret).replace(/^[^\S\n]+/, ""), caret: head.length };
  }

  const num = (v) => String(Number(v));
  const flagsOf = (s) => [s.ts ? "TS" : "", s.backoff ? "BO" : "", s.ddp ? "DDP" : ""].join(" ");
  function groupText(group) {
    const first = group[0], last = group[group.length - 1];
    const rpes = group.map((s) => s.rpe);
    let rpe = "";
    if (rpes.every((r) => r == null)) rpe = "";
    else if (rpes.every((r) => r === rpes[0])) rpe = "@" + num(rpes[0]);
    else rpe = "@" + rpes.map((r) => (r == null ? "?" : num(r))).join(",");
    if (first.myo) return "myo " + first.reps + (first.reps_max ? "-" + first.reps_max : "") + rpe;
    const parts = [group.length + "x" + first.reps + (last.amrap ? "+" : "") + rpe];
    if (first.ts) parts.push("TS");
    if (first.backoff) parts.push("BO");
    if (first.ddp) parts.push("DDP");
    if (last.drops_open) parts.push("DS");
    else if (last.drops) parts.push("DS" + last.drops);
    return parts.join(" ");
  }
  // Consecutive sets with the same reps and callouts form one group; AMRAP and drops end a group.
  function setsText(sets, tmPct) {
    const groups = [];
    for (const s of sets || []) {
      const cur = groups[groups.length - 1], prev = cur && cur[cur.length - 1];
      const same = prev && !prev.myo && !s.myo && !prev.amrap && !prev.drops && !prev.drops_open &&
        prev.reps === s.reps && flagsOf(prev) === flagsOf(s);
      if (same) cur.push(s); else groups.push([s]);
    }
    return groups.map(groupText).join(", ") + (tmPct ? " TM" + tmPct : "");
  }
  function hasCallouts(ex) {
    return !!(ex && (ex.tm_pct || (ex.sets || []).some((s) => s.amrap || s.backoff || s.ddp || s.myo || s.drops || s.drops_open)));
  }
  const api = { hashQuery, insertMovement, setsText, hasCallouts };
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.WeekText = api;
})(typeof window !== "undefined" ? window : this);
