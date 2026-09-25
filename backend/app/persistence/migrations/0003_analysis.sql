CREATE TABLE analysis_runs (
 id TEXT PRIMARY KEY, comparison_id TEXT NOT NULL REFERENCES comparisons(id),
 user_revision_id TEXT NOT NULL REFERENCES sample_revisions(id),
 benchmark_revision_id TEXT NOT NULL REFERENCES sample_revisions(id),
 status TEXT NOT NULL, pipeline_version TEXT NOT NULL,
 config_json TEXT NOT NULL, provider_versions_json TEXT NOT NULL,
 error_json TEXT, started_at TEXT NOT NULL, finished_at TEXT
);
CREATE INDEX analysis_runs_comparison_idx ON analysis_runs(comparison_id);
CREATE TABLE timed_tokens (
 run_id TEXT NOT NULL REFERENCES analysis_runs(id), sample_id TEXT NOT NULL,
 token_index INTEGER NOT NULL, start_s REAL, end_s REAL, quality TEXT NOT NULL,
 provider TEXT NOT NULL, PRIMARY KEY(run_id,sample_id,token_index)
);
CREATE TABLE metrics (
 run_id TEXT NOT NULL REFERENCES analysis_runs(id), sample_id TEXT NOT NULL,
 dimension TEXT NOT NULL, metric_key TEXT NOT NULL, value REAL,
 unit TEXT, quality TEXT NOT NULL, details_json TEXT NOT NULL,
 PRIMARY KEY(run_id,sample_id,dimension,metric_key)
);
CREATE TABLE evidence (
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES analysis_runs(id),
 sample_id TEXT NOT NULL, dimension TEXT NOT NULL, kind TEXT NOT NULL,
 token_index INTEGER, start_s REAL, end_s REAL, value REAL, unit TEXT,
 source_type TEXT NOT NULL, source_ref TEXT NOT NULL, quality TEXT NOT NULL,
 algorithm_version TEXT NOT NULL, details_json TEXT NOT NULL
);
CREATE INDEX evidence_run_sample_idx ON evidence(run_id,sample_id);
CREATE TABLE findings (
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES analysis_runs(id),
 kind TEXT NOT NULL, severity TEXT NOT NULL, confidence_level TEXT NOT NULL,
 statement TEXT NOT NULL, limitations_json TEXT NOT NULL,
 recommendation_json TEXT NOT NULL, rule_version TEXT NOT NULL
);
CREATE TABLE finding_evidence (
 finding_id TEXT NOT NULL REFERENCES findings(id), evidence_id TEXT NOT NULL REFERENCES evidence(id),
 PRIMARY KEY(finding_id,evidence_id)
);
CREATE TABLE comparisons_result (
 run_id TEXT PRIMARY KEY REFERENCES analysis_runs(id), result_json TEXT NOT NULL
);
