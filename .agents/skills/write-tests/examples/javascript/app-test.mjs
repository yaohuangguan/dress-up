// A template for an API test: real handlers and schema on in-memory SQLite, with
// a fail-closed stub at the network boundary. Requires Node 24 or later.
import assert from "node:assert/strict";
import fs from "node:fs";
import { DatabaseSync } from "node:sqlite";
import { createApp, PROVIDER } from "./app.mjs";

const sql = new DatabaseSync(":memory:");
sql.exec("PRAGMA foreign_keys=ON");
sql.exec(fs.readFileSync(new URL("./schema.sql", import.meta.url), "utf8"));
for (const user of ["owner", "intruder"]) {
  sql.prepare("INSERT INTO users(id) VALUES(?)").run(user);
  sql.prepare("INSERT INTO sessions(token,user_id) VALUES(?,?)").run(user + "-session", user);
}
sql.prepare("INSERT INTO devices VALUES('laptop','owner','Laptop','canary-private-credential')").run();

const app = createApp(sql);
const post = (path, body, cookie) => app(new Request("https://app.test" + path, {
  method: "POST",
  headers: { "content-type": "application/json", ...(cookie ? { cookie } : {}) },
  body: JSON.stringify(body),
}));
const rename = (name, cookie) => post("/devices/laptop/rename", { name }, cookie);
const owner = "session=owner-session", intruder = "session=intruder-session";
const device = () => ({ ...sql.prepare("SELECT * FROM devices WHERE id='laptop'").get() });
const audits = () => sql.prepare("SELECT event_type FROM audit_events").all().map((row) => row.event_type);
const credits = () => sql.prepare("SELECT credits FROM users WHERE id='owner'").get().credits;
const expectError = async (response, status, error) => {
  const result = await response;
  assert.equal(result.status, status);
  assert.equal((await result.json()).error, error);
};

const events = {
  evt_paid: { status: "paid", user_id: "owner", credits: 500 },
  evt_open: { status: "open", user_id: "owner", credits: 500 },
};
let providerDown = false;
const originalFetch = globalThis.fetch;
globalThis.fetch = async (input, init) => {
  const url = new URL(String(input));
  assert.equal(url.origin, PROVIDER);
  assert.equal(init?.method ?? "GET", "GET", "Unexpected provider mutation " + url.pathname);
  if (providerDown) return Response.json({}, { status: 503 });
  const event = events[url.pathname.split("/").at(-1)];
  assert(event, "Unexpected provider call " + url.pathname);
  return Response.json(event);
};

try {
  // Permissions: nothing changes until the owner calls.
  const untouched = device();
  await expectError(rename("Mine"), 401, "unauthorized");
  await expectError(rename("Mine", "session=forged"), 401, "unauthorized");
  await expectError(rename("Mine", intruder), 404, "device not found");
  assert.deepEqual(device(), untouched, "Denied calls change nothing");
  assert.deepEqual(audits(), [], "Denied calls are not recorded as changes");

  // Input limits, on both sides of the maximum.
  await expectError(rename("   ", owner), 400, "name is required");
  await expectError(rename(7, owner), 400, "name is required");
  let response = await rename("  " + "M".repeat(80) + "  ", owner);
  assert.equal((await response.json()).name, "M".repeat(80));
  response = await rename("M".repeat(81), owner);
  assert.equal(response.status, 200);
  assert.equal(device().name, "M".repeat(80), "The stored name is bounded, not only the response");

  // Side effects: one audit row per change, and no secret in the response.
  assert.deepEqual(audits(), ["device.renamed", "device.renamed"]);
  response = await rename("Desk", owner);
  assert(!(await response.text()).includes("canary-private-credential"), "The device credential never leaves the server");

  // Replays and races: every delivery succeeds, and the credit is granted once.
  await expectError(post("/webhooks/payment", { id: "evt_open" }), 409, "payment not verified");
  assert.equal(credits(), 0, "An unpaid event grants nothing");
  providerDown = true;
  await expectError(post("/webhooks/payment", { id: "evt_paid" }), 502, "payment not verified");
  assert.equal(credits(), 0, "An outage grants nothing");
  providerDown = false;
  const deliveries = await Promise.all(Array.from({ length: 6 }, () => post("/webhooks/payment", { id: "evt_paid" })));
  assert(deliveries.every((delivery) => delivery.status === 200));
  assert.equal(credits(), 500, "Concurrent deliveries grant the credit once");
  assert.equal((await post("/webhooks/payment", { id: "evt_paid" })).status, 200);
  assert.equal(credits(), 500, "A later replay grants nothing");

  console.log("PASS: ownership matrix, input limits, audit trail, secret canary, verified payment, replay and concurrent delivery");
} finally {
  globalThis.fetch = originalFetch;
  sql.close();
}
