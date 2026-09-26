ALTER TABLE exercises ADD COLUMN reading_text_source TEXT;
ALTER TABLE exercises ADD COLUMN reading_text_ocr_raw TEXT;
ALTER TABLE exercises ADD COLUMN reading_screenshot_asset_id TEXT REFERENCES screenshot_assets(id);
CREATE TABLE sample_tokens_new (
 sample_id TEXT NOT NULL REFERENCES response_samples(id), token_index INTEGER NOT NULL,
 surface TEXT NOT NULL, normalized TEXT NOT NULL,
 color TEXT NOT NULL CHECK(color IN ('red','yellow','green','unknown')),
 color_review_status TEXT NOT NULL CHECK(color_review_status IN ('confirmed','candidate','unreviewed')),
 color_source_screenshot_id TEXT REFERENCES screenshot_assets(id),
 PRIMARY KEY(sample_id,token_index)
);
INSERT INTO sample_tokens_new SELECT * FROM sample_tokens;
DROP TABLE sample_tokens;
ALTER TABLE sample_tokens_new RENAME TO sample_tokens;
