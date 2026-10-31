CREATE TABLE users (id TEXT PRIMARY KEY, credits INTEGER NOT NULL DEFAULT 0);
CREATE TABLE sessions (token TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id));
CREATE TABLE devices (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id),
  name TEXT NOT NULL,
  credential TEXT NOT NULL
);
CREATE TABLE audit_events (
  id INTEGER PRIMARY KEY,
  user_id TEXT NOT NULL,
  device_id TEXT NOT NULL,
  event_type TEXT NOT NULL
);
CREATE TABLE payment_events (id TEXT PRIMARY KEY, user_id TEXT NOT NULL);
