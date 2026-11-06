-- PUBG 매치 데이터 스키마
-- 적재 순서: matches -> participants -> kills

CREATE TABLE IF NOT EXISTS matches (
    match_id    TEXT PRIMARY KEY,
    game_mode   TEXT NOT NULL,
    map_name    TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS participants (
    match_id         TEXT NOT NULL REFERENCES matches (match_id),
    account_id       TEXT NOT NULL,
    player_name      TEXT NOT NULL,
    kills            INTEGER NOT NULL CHECK (kills >= 0),
    headshot_kills   INTEGER NOT NULL CHECK (headshot_kills >= 0),
    damage_dealt     NUMERIC NOT NULL CHECK (damage_dealt >= 0),
    longest_kill_m   NUMERIC NOT NULL CHECK (longest_kill_m >= 0),
    time_survived_s  NUMERIC CHECK (time_survived_s >= 0),
    win_place        INTEGER NOT NULL CHECK (win_place >= 1),
    is_bot           BOOLEAN GENERATED ALWAYS AS (account_id LIKE 'ai.%') STORED,
    PRIMARY KEY (match_id, account_id),
    CHECK (headshot_kills <= kills)
);

CREATE TABLE IF NOT EXISTS kills (
    match_id     TEXT NOT NULL,
    event_time   TIMESTAMPTZ NOT NULL,
    killer       TEXT NOT NULL,
    victim       TEXT NOT NULL,
    weapon       TEXT NOT NULL,
    distance_m   NUMERIC CHECK (distance_m >= 0),
    is_headshot  BOOLEAN NOT NULL,
    knocker      TEXT,
    finisher     TEXT,
    kill_type    TEXT GENERATED ALWAYS AS (
                     CASE
                         WHEN knocker IS NULL THEN 'direct'
                         WHEN knocker = killer THEN 'knocked'
                         ELSE 'finished'
                     END
                 ) STORED,
    PRIMARY KEY (match_id, victim, event_time),
    FOREIGN KEY (match_id, killer) REFERENCES participants (match_id, account_id),
    FOREIGN KEY (match_id, victim) REFERENCES participants (match_id, account_id)
);