-- Only infrastructure belongs to T01; sample schemas follow after T00 validation.
CREATE TABLE app_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
INSERT INTO app_metadata (key, value) VALUES ('schema_scope', 'foundation');
