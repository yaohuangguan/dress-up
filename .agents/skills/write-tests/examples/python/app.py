"""A small API with ownership, input limits, an audit trail, a secret column and a
replayable payment webhook. The provider client is passed in, so tests can replace
the network without patching this module."""
import re
import threading

MAX_NAME = 80


class ProviderError(Exception):
    pass


class App:
    def __init__(self, db, fetch_event):
        self.db = db
        self.fetch_event = fetch_event
        self.lock = threading.Lock()

    def handle(self, method, path, body=None, session=None):
        device = re.fullmatch(r"/devices/([^/]+)/rename", path)
        if method == "POST" and device:
            return self.rename(device.group(1), body or {}, session)
        if method == "POST" and path == "/webhooks/payment":
            return self.payment_webhook(body or {})
        return 404, {"error": "not found"}

    def session_user(self, session):
        row = self.db.execute("SELECT user_id FROM sessions WHERE token=?", (session,)).fetchone()
        return row[0] if row else None

    def rename(self, device_id, body, session):
        with self.lock:
            user_id = self.session_user(session)
            if not user_id:
                return 401, {"error": "unauthorized"}
            device = self.db.execute(
                "SELECT id, credential FROM devices WHERE id=? AND user_id=?", (device_id, user_id)
            ).fetchone()
            if not device:
                return 404, {"error": "device not found"}
            name = body.get("name")
            if not isinstance(name, str) or not name.strip():
                return 400, {"error": "name is required"}
            next_name = name.strip()[:MAX_NAME]
            with self.db:
                self.db.execute("UPDATE devices SET name=? WHERE id=?", (next_name, device_id))
                self.db.execute(
                    "INSERT INTO audit_events(user_id,device_id,event_type) VALUES(?,?,'device.renamed')",
                    (user_id, device_id),
                )
            return 200, {"id": device[0], "name": next_name}

    # Webhooks can arrive twice, so the provider is asked what happened and the
    # stored event id decides whether the credit was already granted.
    def payment_webhook(self, body):
        event_id = body.get("id")
        try:
            event = self.fetch_event(event_id)
        except ProviderError:
            return 502, {"error": "payment not verified"}
        if event["status"] != "paid":
            return 409, {"error": "payment not verified"}
        with self.lock, self.db:
            inserted = self.db.execute(
                "INSERT OR IGNORE INTO payment_events(id,user_id) VALUES(?,?)", (event_id, event["user_id"])
            )
            if inserted.rowcount:
                self.db.execute("UPDATE users SET credits=credits+? WHERE id=?", (event["credits"], event["user_id"]))
        return 200, {"ok": True}
