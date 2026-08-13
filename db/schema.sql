-- BDM Field Tool schema. Postgres only (Supabase or the docker-compose
-- postgres service) -- app data is never written to the local filesystem.

CREATE TABLE IF NOT EXISTS bdms (
    bdm_code     TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    territory    TEXT NOT NULL,
    phone        TEXT,
    joined_date  DATE
);

CREATE TABLE IF NOT EXISTS outlets (
    outlet_code           TEXT PRIMARY KEY,
    outlet_name           TEXT,               -- NULL = 9 source rows had no name
    outlet_type           TEXT,
    town_raw              TEXT,               -- as it appeared in outlets.csv
    territory             TEXT,               -- normalized, joins to bdms.territory
    owner_name            TEXT,
    phone                 TEXT,
    onboarded_date        DATE,
    credit_days           INT,                -- NULL = terms not recorded (13.2% of source)
    latitude              DOUBLE PRECISION,
    longitude             DOUBLE PRECISION,   -- NULL lat/lon = 108 outlets with no location on file
    status                TEXT,               -- NULL = status not recorded (9.4% of source)
    visit_code            TEXT NOT NULL,      -- generated counter-card code, see docs/data-notes.md Phase 3 note
    possible_duplicate_of TEXT REFERENCES outlets(outlet_code)  -- Phase 0 finding: 20 exact-coordinate pairs
);

CREATE TABLE IF NOT EXISTS billing_monthly (
    outlet_code  TEXT NOT NULL REFERENCES outlets(outlet_code),
    month        DATE NOT NULL,   -- first-of-month
    units        INT NOT NULL,
    value        NUMERIC(12, 2) NOT NULL,
    PRIMARY KEY (outlet_code, month)
    -- Deliberately sparse: a missing (outlet_code, month) row means "no
    -- record", which is NOT the same fact as a present row with value = 0
    -- ("billed nothing"). Never pivot this into a dense zero-filled grid.
);

CREATE TABLE IF NOT EXISTS visits (
    visit_id       TEXT PRIMARY KEY,     -- source Visit ID for seeded rows; app-created visits get a generated id
    bdm_code       TEXT REFERENCES bdms(bdm_code),
    outlet_code    TEXT REFERENCES outlets(outlet_code),
    visit_date     DATE,
    check_in_time  TIME,                 -- NULL = not logged (14 source rows)
    duration_mins  INT,                  -- NULL = not logged (13.7% of source)
    purpose        TEXT,                 -- NULL = not logged (9.0% of source)
    remarks        TEXT,                 -- NULL = no outcome recorded (38.3% of source)
    source         TEXT NOT NULL DEFAULT 'historical_log',  -- 'historical_log' | 'app'
    entered_code   TEXT,                 -- code the BDM typed in at the counter (Phase 3)
    code_match     BOOLEAN,              -- entered_code == outlets.visit_code
    photo_taken    BOOLEAN NOT NULL DEFAULT FALSE,
    latitude       DOUBLE PRECISION,     -- device GPS at check-in if captured, else the outlet's registered coordinate
    longitude      DOUBLE PRECISION,
    gps_anomaly    TEXT,                 -- reason string if the pace/location looks impossible, else NULL
    confidence     TEXT,                 -- 'Verified' | 'Partial' | 'Unverified', computed at write time
    is_complete    BOOLEAN NOT NULL DEFAULT FALSE,  -- checklist fully submitted vs partial-saved
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Added after the initial launch: real device GPS capture (see
-- docs/ai-log.md). ALTER ... IF NOT EXISTS so this also applies to
-- already-seeded databases, not just a fresh CREATE TABLE.
ALTER TABLE visits ADD COLUMN IF NOT EXISTS location_accuracy_m DOUBLE PRECISION;  -- device-reported GPS accuracy in metres, NULL if not captured
ALTER TABLE visits ADD COLUMN IF NOT EXISTS location_source TEXT;  -- 'device' | 'outlet_registered' | NULL

CREATE TABLE IF NOT EXISTS visit_checklist_responses (
    id              SERIAL PRIMARY KEY,
    visit_id        TEXT NOT NULL REFERENCES visits(visit_id),
    item_key        TEXT NOT NULL,    -- key from checklists.yaml
    item_label      TEXT NOT NULL,
    response_type   TEXT NOT NULL,    -- 'blocker' | 'note' | 'confirmation'
    response_value  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS orders (
    id           SERIAL PRIMARY KEY,
    visit_id     TEXT REFERENCES visits(visit_id),
    outlet_code  TEXT NOT NULL REFERENCES outlets(outlet_code),
    value        NUMERIC(12, 2) NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS collections (
    id           SERIAL PRIMARY KEY,
    visit_id     TEXT REFERENCES visits(visit_id),
    outlet_code  TEXT NOT NULL REFERENCES outlets(outlet_code),
    amount       NUMERIC(12, 2) NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agreed_actions (
    id           SERIAL PRIMARY KEY,
    visit_id     TEXT REFERENCES visits(visit_id),
    outlet_code  TEXT NOT NULL REFERENCES outlets(outlet_code),
    action_text  TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'open',  -- 'open' | 'done' | 'carried_over'
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_billing_outlet ON billing_monthly(outlet_code);
CREATE INDEX IF NOT EXISTS idx_visits_outlet ON visits(outlet_code);
CREATE INDEX IF NOT EXISTS idx_visits_bdm_date ON visits(bdm_code, visit_date);
CREATE INDEX IF NOT EXISTS idx_outlets_territory ON outlets(territory);
CREATE INDEX IF NOT EXISTS idx_agreed_actions_outlet ON agreed_actions(outlet_code, status);
