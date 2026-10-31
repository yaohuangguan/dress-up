"""A template for an API test: real handlers and schema on in-memory SQLite, with a
strict fake at the network boundary. Run with: python -m unittest"""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import unittest

from app import App, ProviderError

OWNER, INTRUDER = "owner-session", "intruder-session"
SECRET = "canary-private-credential"


class DeviceApiTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.addCleanup(self.db.close)
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(Path(__file__).with_name("schema.sql").read_text())
        for user in ("owner", "intruder"):
            self.db.execute("INSERT INTO users(id) VALUES(?)", (user,))
            self.db.execute("INSERT INTO sessions(token,user_id) VALUES(?,?)", (user + "-session", user))
        self.db.execute("INSERT INTO devices VALUES('laptop','owner','Laptop',?)", (SECRET,))
        self.db.commit()
        self.events = {
            "evt_paid": {"status": "paid", "user_id": "owner", "credits": 500},
            "evt_open": {"status": "open", "user_id": "owner", "credits": 500},
        }
        self.provider_down = False
        self.app = App(self.db, self.fetch_event)

    def fetch_event(self, event_id):
        if self.provider_down:
            raise ProviderError("provider unavailable")
        self.assertIn(event_id, self.events, "Unexpected provider call")
        return self.events[event_id]

    def rename(self, name, session=None):
        return self.app.handle("POST", "/devices/laptop/rename", {"name": name}, session)

    def deliver(self, event_id="evt_paid"):
        return self.app.handle("POST", "/webhooks/payment", {"id": event_id})

    def device(self):
        return self.db.execute("SELECT * FROM devices WHERE id='laptop'").fetchone()

    def audits(self):
        return [row[0] for row in self.db.execute("SELECT event_type FROM audit_events")]

    def credits(self):
        return self.db.execute("SELECT credits FROM users WHERE id='owner'").fetchone()[0]

    def test_denied_callers_change_nothing(self):
        before = self.device()
        cases = [
            (None, 401, "unauthorized"),
            ("forged", 401, "unauthorized"),
            (INTRUDER, 404, "device not found"),
        ]
        for session, status, error in cases:
            with self.subTest(session=session):
                self.assertEqual(self.rename("Mine", session), (status, {"error": error}))
        self.assertEqual(self.device(), before, "Denied calls change nothing")
        self.assertEqual(self.audits(), [], "Denied calls are not recorded as changes")

    def test_name_must_have_content(self):
        for name in ("", "   ", 7, None):
            with self.subTest(name=name):
                self.assertEqual(self.rename(name, OWNER), (400, {"error": "name is required"}))

    def test_name_limit_on_both_sides(self):
        self.assertEqual(self.rename("  " + "M" * 80 + "  ", OWNER)[1]["name"], "M" * 80)
        self.assertEqual(self.rename("M" * 81, OWNER)[1]["name"], "M" * 80)
        self.assertEqual(self.device()[2], "M" * 80, "The stored name is bounded, not only the response")

    def test_each_change_is_audited_once(self):
        self.rename("Desk", OWNER)
        self.rename("Office", OWNER)
        self.assertEqual(self.audits(), ["device.renamed", "device.renamed"])

    def test_credential_never_leaves_the_server(self):
        status, body = self.rename("Desk", OWNER)
        self.assertEqual(status, 200)
        self.assertNotIn(SECRET, json.dumps(body), "The device credential never leaves the server")

    def test_unpaid_event_grants_nothing(self):
        self.assertEqual(self.deliver("evt_open"), (409, {"error": "payment not verified"}))
        self.assertEqual(self.credits(), 0, "An unpaid event grants nothing")

    def test_provider_outage_grants_nothing(self):
        self.provider_down = True
        self.assertEqual(self.deliver(), (502, {"error": "payment not verified"}))
        self.assertEqual(self.credits(), 0, "An outage grants nothing")

    def test_replay_and_concurrent_delivery_grant_once(self):
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _: self.deliver(), range(6)))
        self.assertTrue(all(status == 200 for status, _ in results))
        self.assertEqual(self.credits(), 500, "Concurrent deliveries grant the credit once")
        self.assertEqual(self.deliver()[0], 200)
        self.assertEqual(self.credits(), 500, "A later replay grants nothing")


if __name__ == "__main__":
    unittest.main()
