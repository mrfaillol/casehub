"use strict";

// Pure autostart helpers for server-lite — intentionally dependency-free so the
// boot policy is unit-testable without spinning up Express or Puppeteer.

// Parse a CSV of org ids ("1,4") into a clean list of positive integers.
function parseOrgList(csv) {
  return String(csv == null ? "" : csv)
    .split(",")
    .map((s) => parseInt(s.trim(), 10))
    .filter((n) => Number.isFinite(n) && n > 0);
}

// Decide the ensureInitialized() options for an org at boot.
//
// SAFE variant (handoff decision §6): an org listed in CASEHUB_AUTOSTART_FORCE is
// re-warmed with { explicit: true } — which clears a stale intentional-down
// short-circuit so the session comes back to awaiting_scan/ready. Everything else
// boots implicitly ({}), so a tenant admin's deliberate disconnect still persists
// across a restart instead of being silently re-armed.
function bootOptionsFor(orgId, { forceList = [] } = {}) {
  return forceList.includes(orgId) ? { explicit: true } : {};
}

module.exports = { parseOrgList, bootOptionsFor };
