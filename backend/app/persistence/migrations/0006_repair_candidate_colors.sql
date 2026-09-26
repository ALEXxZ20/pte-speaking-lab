-- Some databases recorded 0005 before its sample_tokens constraint was updated.
-- Rebuild the view table once more so screenshot candidates can be persisted.
CREATE TABLE sample_tokens_repaired (
 sample_id TEXT NOT NULL REFERENCES response_samples(id), token_index INTEGER NOT NULL,
 surface TEXT NOT NULL, normalized TEXT NOT NULL,
 color TEXT NOT NULL CHECK(color IN ('red','yellow','green','unknown')),
 color_review_status TEXT NOT NULL CHECK(color_review_status IN ('confirmed','candidate','unreviewed')),
 color_source_screenshot_id TEXT REFERENCES screenshot_assets(id),
 PRIMARY KEY(sample_id,token_index)
);
INSERT INTO sample_tokens_repaired SELECT * FROM sample_tokens;
DROP TABLE sample_tokens;
ALTER TABLE sample_tokens_repaired RENAME TO sample_tokens;
