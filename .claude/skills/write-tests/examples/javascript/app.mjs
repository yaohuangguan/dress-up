// A small API with ownership, input limits, an audit trail, a secret column and a
// replayable payment webhook.
const MAX_NAME = 80;
export const PROVIDER = "https://api.provider.test";

const json = (body, status = 200) => Response.json(body, { status });

function sessionUser(request, sql) {
  const token = request.headers.get("cookie")?.match(/(?:^|;\s*)session=([^;]+)/)?.[1];
  if (!token) return null;
  return sql.prepare("SELECT user_id FROM sessions WHERE token=?").get(token)?.user_id ?? null;
}

async function rename(request, sql, deviceId) {
  const userId = sessionUser(request, sql);
  if (!userId) return json({ error: "unauthorized" }, 401);
  const device = sql.prepare("SELECT * FROM devices WHERE id=? AND user_id=?").get(deviceId, userId);
  if (!device) return json({ error: "device not found" }, 404);
  const { name } = await request.json();
  if (typeof name !== "string" || !name.trim()) return json({ error: "name is required" }, 400);
  const next = name.trim().slice(0, MAX_NAME);
  sql.prepare("UPDATE devices SET name=? WHERE id=?").run(next, deviceId);
  sql.prepare("INSERT INTO audit_events(user_id,device_id,event_type) VALUES(?,?,'device.renamed')").run(userId, deviceId);
  return json({ id: device.id, name: next });
}

// Webhooks can arrive twice, so the provider is asked what happened and the
// stored event id decides whether the credit was already granted.
async function paymentWebhook(request, sql) {
  const { id } = await request.json();
  const response = await fetch(PROVIDER + "/v1/events/" + encodeURIComponent(id));
  if (!response.ok) return json({ error: "payment not verified" }, 502);
  const event = await response.json();
  if (event.status !== "paid") return json({ error: "payment not verified" }, 409);
  const inserted = sql.prepare("INSERT OR IGNORE INTO payment_events(id,user_id) VALUES(?,?)").run(id, event.user_id);
  if (inserted.changes) sql.prepare("UPDATE users SET credits=credits+? WHERE id=?").run(event.credits, event.user_id);
  return json({ ok: true });
}

export function createApp(sql) {
  return async (request) => {
    const { pathname } = new URL(request.url);
    const device = pathname.match(/^\/devices\/([^/]+)\/rename$/);
    if (request.method === "POST" && device) return rename(request, sql, decodeURIComponent(device[1]));
    if (request.method === "POST" && pathname === "/webhooks/payment") return paymentWebhook(request, sql);
    return json({ error: "not found" }, 404);
  };
}
