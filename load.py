import json
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv


def get_conninfo():
    load_dotenv()
    return (
        f"host=localhost port=5433 "
        f"dbname={os.environ['POSTGRES_DB']} "
        f"user={os.environ['POSTGRES_USER']} "
        f"password={os.environ['POSTGRES_PASSWORD']}"
    )


def load_matches(cur):
    rows = []
    for path in Path("processed").glob("match_*.json"):
        with open(path, encoding="utf-8") as f:
            m = json.load(f)
        rows.append((m["match_id"], m["game_mode"], m["map_name"], m["created_at"]))
    cur.executemany(
        """
        INSERT INTO matches (match_id, game_mode, map_name, created_at)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (match_id) DO UPDATE SET
            game_mode = EXCLUDED.game_mode,
            map_name = EXCLUDED.map_name,
            created_at = EXCLUDED.created_at
        """,
        rows,
    )
    return len(rows)


def load_participants(cur):
    rows = []
    for path in Path("processed").glob("participants_*.jsonl"):
        with open(path, encoding="utf-8") as f:
            for line in f:
                p = json.loads(line)
                rows.append(
                    (
                        p["match_id"],
                        p["account_id"],
                        p["player_name"],
                        p["kills"],
                        p["headshot_kills"],
                        p["damage_dealt"],
                        p["longest_kill"],
                        p["time_survived"],
                        p["win_place"],
                    )
                )
    cur.executemany(
        """
        INSERT INTO participants (match_id, account_id, player_name, kills, headshot_kills,
                                  damage_dealt, longest_kill_m, time_survived_s, win_place)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (match_id, account_id) DO UPDATE SET
            player_name = EXCLUDED.player_name,
            kills = EXCLUDED.kills,
            headshot_kills = EXCLUDED.headshot_kills,
            damage_dealt = EXCLUDED.damage_dealt,
            longest_kill_m = EXCLUDED.longest_kill_m,
            time_survived_s = EXCLUDED.time_survived_s,
            win_place = EXCLUDED.win_place
        """,
        rows,
    )
    return len(rows)


def load_kills(cur):
    rows = []
    for path in Path("processed").glob("kills_*.jsonl"):
        with open(path, encoding="utf-8") as f:
            for line in f:
                k = json.loads(line)
                rows.append(
                    (
                        k["match_id"],
                        k["time"],
                        k["killer"],
                        k["victim"],
                        k["weapon"],
                        k["distance"],
                        k["is_headshot"],
                        k["knocker"],
                        k["finisher"],
                    )
                )
    cur.executemany(
        """
        INSERT INTO kills (match_id, event_time, killer, victim, weapon, distance_m, is_headshot,
                   knocker, finisher)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (match_id, victim, event_time) DO UPDATE SET
        killer = EXCLUDED.killer,
        weapon = EXCLUDED.weapon,
        distance_m = EXCLUDED.distance_m,
        is_headshot = EXCLUDED.is_headshot,
        knocker = EXCLUDED.knocker,
        finisher = EXCLUDED.finisher
        """,
        rows,
    )
    return len(rows)


def run_load():
    with psycopg.connect(get_conninfo()) as conn:
        with conn.cursor() as cur:
            n_matches = load_matches(cur)
            n_participants = load_participants(cur)
            n_kills = load_kills(cur)
    rows = {"matches": n_matches, "participants": n_participants, "kills": n_kills}
    return rows


if __name__ == "__main__":
    with psycopg.connect(get_conninfo()) as conn:
        with conn.cursor() as cur:
            n_matches = load_matches(cur)
            n_participants = load_participants(cur)
            n_kills = load_kills(cur)
    print({"matches": n_matches, "participants": n_participants, "kills": n_kills})
