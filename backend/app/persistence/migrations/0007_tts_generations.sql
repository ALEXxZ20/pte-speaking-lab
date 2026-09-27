CREATE TABLE tts_generations (
 id TEXT PRIMARY KEY,
 cache_key TEXT NOT NULL UNIQUE,
 audio_asset_id TEXT NOT NULL UNIQUE REFERENCES audio_assets(id),
 text TEXT NOT NULL,
 voice TEXT NOT NULL,
 rate TEXT NOT NULL,
 segments_json TEXT NOT NULL,
 word_boundaries_json TEXT NOT NULL,
 seam_intervals_json TEXT NOT NULL,
 provider_version TEXT NOT NULL,
 created_at TEXT NOT NULL
);
