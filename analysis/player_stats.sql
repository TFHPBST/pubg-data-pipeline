CREATE OR REPLACE VIEW player_stats AS
WITH human_kills AS (
    -- 사람이 사람을 죽인 킬만 남김
    SELECT k.*
    FROM kills k
    JOIN participants vp
      ON vp.match_id = k.match_id AND vp.account_id = k.victim
    WHERE NOT vp.is_bot
      AND k.killer LIKE 'account.%'
),
kill_stats AS (
    SELECT killer AS account_id,
           count(*) AS human_kills,
           count(*) FILTER (WHERE is_headshot) AS headshot_kills,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY distance_m) AS median_distance_m,
           max(distance_m) AS max_distance_m,
           count(*) FILTER (WHERE kill_type <> 'finished') AS own_kills,
           count(*) FILTER (WHERE kill_type <> 'finished' AND is_headshot) AS own_headshots,
           count(*) FILTER (WHERE kill_type = 'finished') AS finished_kills
    FROM human_kills
    GROUP BY killer
),
played AS (
    -- 사람별 참가 매치 수 (킬이 0인 사람도 포함)
    SELECT account_id, count(*) AS matches_played
    FROM participants
    WHERE NOT is_bot
    GROUP BY account_id
)
SELECT p.account_id,
       p.matches_played,
       coalesce(s.human_kills, 0) AS human_kills,
       coalesce(s.headshot_kills, 0) AS headshot_kills,
       round(s.headshot_kills::numeric / NULLIF(s.human_kills, 0), 3) AS headshot_ratio,
       round(coalesce(s.human_kills, 0)::numeric / p.matches_played, 2) AS kills_per_match,
       s.median_distance_m,
       s.max_distance_m,
       coalesce(s.own_kills, 0) AS own_kills,
       round(s.own_headshots::numeric / NULLIF(s.own_kills, 0), 3) AS own_hs_ratio,
       round(coalesce(s.finished_kills, 0)::numeric / NULLIF(s.human_kills, 0), 3) AS finished_share
FROM played p
LEFT JOIN kill_stats s ON s.account_id = p.account_id;