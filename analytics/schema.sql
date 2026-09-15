CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK(kind IN ('installation','pet_generation')),
  received_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS events_kind ON events(kind);
