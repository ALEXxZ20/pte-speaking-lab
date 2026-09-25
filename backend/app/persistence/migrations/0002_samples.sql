CREATE TABLE exercises (
 id TEXT PRIMARY KEY, question_type TEXT NOT NULL, title TEXT, source_note TEXT,
 source_question_id TEXT, reference_image_path TEXT, created_at TEXT NOT NULL
);
CREATE TABLE audio_assets (
 id TEXT PRIMARY KEY, relative_path TEXT NOT NULL UNIQUE, sha256 TEXT NOT NULL,
 original_name TEXT, mime_type TEXT, duration_s REAL, sample_rate_hz INTEGER,
 created_at TEXT NOT NULL
);
CREATE TABLE screenshot_assets (
 id TEXT PRIMARY KEY, relative_path TEXT NOT NULL UNIQUE, sha256 TEXT NOT NULL,
 width_px INTEGER NOT NULL, height_px INTEGER NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE response_samples (
 id TEXT PRIMARY KEY, exercise_id TEXT NOT NULL REFERENCES exercises(id),
 role TEXT NOT NULL CHECK(role IN ('user','benchmark')),
 audio_asset_id TEXT REFERENCES audio_assets(id), transcript_raw TEXT,
 transcript_source TEXT, input_payload_json TEXT NOT NULL,
 input_version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
);
CREATE INDEX response_samples_exercise_idx ON response_samples(exercise_id);
CREATE TABLE comparisons (
 id TEXT PRIMARY KEY, exercise_id TEXT NOT NULL REFERENCES exercises(id),
 user_sample_id TEXT NOT NULL REFERENCES response_samples(id),
 benchmark_sample_id TEXT NOT NULL REFERENCES response_samples(id),
 created_at TEXT NOT NULL, CHECK(user_sample_id <> benchmark_sample_id)
);
CREATE TABLE sample_screenshots (
 sample_id TEXT NOT NULL REFERENCES response_samples(id),
 screenshot_id TEXT NOT NULL REFERENCES screenshot_assets(id), display_order INTEGER NOT NULL,
 PRIMARY KEY(sample_id,screenshot_id)
);
CREATE TABLE screenshot_imports (
 id TEXT PRIMARY KEY, sample_id TEXT NOT NULL REFERENCES response_samples(id),
 parser_version TEXT NOT NULL, draft_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE sample_revisions (
 id TEXT PRIMARY KEY, sample_id TEXT NOT NULL REFERENCES response_samples(id),
 version INTEGER NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(sample_id,version)
);
CREATE TABLE external_scores (
 sample_id TEXT NOT NULL REFERENCES response_samples(id),
 dimension TEXT NOT NULL CHECK(dimension IN ('pronunciation','fluency','content')),
 value REAL NOT NULL, max_value REAL,
 source TEXT NOT NULL DEFAULT 'xingji', PRIMARY KEY(sample_id,dimension)
);
CREATE TABLE sample_tokens (
 sample_id TEXT NOT NULL REFERENCES response_samples(id), token_index INTEGER NOT NULL,
 surface TEXT NOT NULL, normalized TEXT NOT NULL,
 color TEXT NOT NULL CHECK(color IN ('red','yellow','green','unknown')),
 color_review_status TEXT NOT NULL CHECK(color_review_status IN ('confirmed','unreviewed')),
 color_source_screenshot_id TEXT REFERENCES screenshot_assets(id),
 PRIMARY KEY(sample_id,token_index)
);
CREATE TABLE pause_labels (
 id TEXT PRIMARY KEY, sample_id TEXT NOT NULL REFERENCES response_samples(id),
 after_token_index INTEGER, raw_label TEXT NOT NULL,
 review_status TEXT NOT NULL CHECK(review_status IN ('confirmed','unreviewed'))
);
