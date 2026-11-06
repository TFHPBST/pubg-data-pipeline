import psycopg

from collect import save_json
from load import get_conninfo

CANDIDATES_PATH = "processed/candidates.json"

QUERY = """
WITH qualified AS (
    SELECT * FROM player_stats WHERE own_kills >= 8
),
ranked AS (
    SELECT account_id,
           percent_rank() OVER (ORDER BY own_hs_ratio) AS hs_rank,
           percent_rank() OVER (ORDER BY kills_per_match) AS kpm_rank
    FROM qualified
)
SELECT account_id, 'p_' || left(md5(account_id), 8) AS player
FROM ranked
WHERE hs_rank >= 0.9 AND kpm_rank >= 0.9
ORDER BY player;
"""


if __name__ == "__main__":
    with psycopg.connect(get_conninfo()) as conn:
        with conn.cursor() as cur:
            cur.execute(QUERY)
            rows = cur.fetchall()

    candidates = [{"account_id": acc, "player": player} for acc, player in rows]
    save_json(CANDIDATES_PATH, candidates)

    print(f"후보 {len(candidates)}명 저장: {CANDIDATES_PATH}")
    for c in candidates:
        print(f"  {c['player']}")
