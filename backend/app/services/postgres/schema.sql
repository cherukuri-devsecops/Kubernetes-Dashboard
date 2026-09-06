-- Applied idempotently on every startup; keep every statement IF NOT EXISTS.

CREATE SEQUENCE IF NOT EXISTS incident_number_seq START 1001;

CREATE TABLE IF NOT EXISTS incidents (
    id            TEXT PRIMARY KEY,
    title         TEXT        NOT NULL,
    severity      TEXT        NOT NULL CHECK (severity IN ('sev1', 'sev2', 'sev3')),
    status        TEXT        NOT NULL CHECK (status IN ('open', 'investigating', 'mitigated', 'resolved')),
    service       TEXT        NOT NULL,
    namespace     TEXT        NOT NULL DEFAULT '',
    assignee      TEXT        NOT NULL DEFAULT 'Unassigned',
    opened_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at   TIMESTAMPTZ,
    summary       TEXT        NOT NULL DEFAULT '',
    root_cause    TEXT,
    linked_alerts TEXT[]      NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS incidents_status_idx ON incidents (status);
CREATE INDEX IF NOT EXISTS incidents_opened_at_idx ON incidents (opened_at DESC);

CREATE TABLE IF NOT EXISTS incident_updates (
    id          BIGSERIAL PRIMARY KEY,
    incident_id TEXT        NOT NULL REFERENCES incidents (id) ON DELETE CASCADE,
    at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor       TEXT        NOT NULL,
    body        TEXT        NOT NULL
);

CREATE INDEX IF NOT EXISTS incident_updates_incident_idx ON incident_updates (incident_id, at);
