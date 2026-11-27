// Visit dates must be the nurse's local date, not UTC: in Cameroon (UTC+1) a visit at
// 00:30 on 27 November is still 26 November in UTC.
import { test } from "node:test";
import assert from "node:assert/strict";

process.env.TZ = "Africa/Douala";
const { localDate } = await import("../js/records.js");

test("a visit at 00:30 in Cameroon keeps its local date", () => {
  const at = Date.parse("2026-11-26T23:30:00Z"); // 00:30 on 27 Nov in Yaoundé
  assert.equal(new Date(at).toISOString().slice(0, 10), "2026-11-26");
  assert.equal(localDate(at), "2026-11-27");
});

test("midday and end of year", () => {
  assert.equal(localDate(Date.parse("2026-11-27T11:00:00Z")), "2026-11-27");
  assert.equal(localDate(Date.parse("2026-12-31T23:30:00Z")), "2027-01-01");
});
