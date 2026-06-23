"use strict";

// Frente 4 (Solucao D, SAFE variant per handoff decision §6): membership in
// CASEHUB_AUTOSTART_ORGS = operator intent to keep an org warm, but a tenant
// admin's deliberate disconnect (intentional-down marker) MUST survive restart.
// So autostart does NOT override the marker globally. Only orgs explicitly listed
// in CASEHUB_AUTOSTART_FORCE are re-warmed with { explicit: true } (which clears
// the stale short-circuit). When an autostart org is skipped because it is
// intentionally down, the boot must LOG LOUDLY (never a silent dark state).

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");

// Pure, dependency-free module: unit-testable without Express/Puppeteer.
const { parseOrgList, bootOptionsFor } = require("../autostart-options");

test("bootOptionsFor forces explicit re-warm ONLY for force-listed orgs", () => {
  assert.deepStrictEqual(bootOptionsFor(4, { forceList: [4] }), { explicit: true });
  assert.deepStrictEqual(bootOptionsFor(2, { forceList: [4] }), {});
  assert.deepStrictEqual(bootOptionsFor(4, { forceList: [] }), {});
  assert.deepStrictEqual(bootOptionsFor(4), {}, "missing opts must default to implicit boot");
});

test("parseOrgList turns a CSV into positive ints, dropping junk/zero/negatives", () => {
  assert.deepStrictEqual(parseOrgList("1,4"), [1, 4]);
  assert.deepStrictEqual(parseOrgList(" 1 , 4 , x, 0, -2, 7 "), [1, 4, 7]);
  assert.deepStrictEqual(parseOrgList(""), []);
  assert.deepStrictEqual(parseOrgList(undefined), []);
});

test("server-lite autostart wires bootOptionsFor and loud-logs an intentional-down skip", () => {
  const src = fs.readFileSync(path.join(__dirname, "..", "server-lite.js"), "utf8");
  assert.match(src, /CASEHUB_AUTOSTART_FORCE/, "boot must read the force list");
  assert.match(src, /bootOptionsFor\(\s*orgId\s*,/, "boot loop must derive options via bootOptionsFor");
  assert.match(src, /ensureInitialized\(\s*orgId\s*,\s*null\s*,/, "ensureInitialized must receive the boot options");
  assert.match(src, /_isIntentionalDown\(\)/, "boot must detect an intentional-down skip");
  assert.match(src, /\.intentional-down-org-/, "the loud-log must name the marker file");
});
