CREATE TABLE month_settings (
    id SERIAL PRIMARY KEY,
    month TIMESTAMPTZ NOT NULL UNIQUE,
    submission_limit INTEGER,
    spotify_owner_id VARCHAR(120),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION update_month_settings_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_month_settings_updated
BEFORE UPDATE ON month_settings
FOR EACH ROW
EXECUTE FUNCTION update_month_settings_timestamp();
