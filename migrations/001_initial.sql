-- Kaworai-watcher migration
-- Kaworai_bot DB-ga ishga tushirilsin.
--
-- Izoh: `animes` va `series` jadvallari kaworai_bot tomonidan yaratilgan deb
-- taxmin qilinadi. Biz faqat `series` ga yangi ustun qo'shamiz va ikki yangi
-- watcher jadvalini yaratamiz.

BEGIN;

ALTER TABLE series ADD COLUMN IF NOT EXISTS file_unique_id VARCHAR(64);
CREATE INDEX IF NOT EXISTS idx_series_file_unique_id ON series (file_unique_id);

CREATE TABLE IF NOT EXISTS watcher_channel_links (
    id SERIAL PRIMARY KEY,
    channel_id BIGINT NOT NULL,
    channel_title VARCHAR(255),
    anime_id INTEGER NOT NULL REFERENCES animes(id) ON DELETE CASCADE,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    created_by BIGINT NOT NULL,
    CONSTRAINT uq_channel_anime_link UNIQUE (channel_id, anime_id)
);
CREATE INDEX IF NOT EXISTS idx_watcher_channel_links_channel_id ON watcher_channel_links (channel_id);

CREATE TABLE IF NOT EXISTS watcher_processed_files (
    id SERIAL PRIMARY KEY,
    file_unique_id VARCHAR(64) NOT NULL UNIQUE,
    anime_id INTEGER,
    episode INTEGER,
    series_id INTEGER,
    source_channel_id BIGINT,
    processed_at TIMESTAMP NOT NULL DEFAULT now()
);

COMMIT;
