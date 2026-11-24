import os
from pathlib import Path

import psycopg
import pytest

from collect import save_json, save_jsonl
from load import load_kills, load_matches, load_participants
from player_queue import next_batch, seed_queue

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema.sql"


@pytest.fixture
def db():
    conninfo = os.environ.get("TEST_DATABASE_URL")
    if not conninfo:
        pytest.skip("TEST_DATABASE_URL이 없어 DB 테스트를 건너뜁니다")

    with psycopg.connect(conninfo) as conn:
        # 안전장치: 이름이 _test로 끝나는 DB에서만 테이블을 지운다
        if not conn.info.dbname.endswith("_test"):
            raise RuntimeError(f"테스트 DB가 아닙니다: {conn.info.dbname}")

        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS kills, participants, matches, player_queue CASCADE")
            cur.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.commit()
        yield conn


def load_all(conn):
    with conn.cursor() as cur:
        load_matches(cur)
        load_participants(cur)
        load_kills(cur)
    conn.commit()


def counts(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT (SELECT count(*) FROM matches),
                   (SELECT count(*) FROM participants),
                   (SELECT count(*) FROM kills)
        """)
        return cur.fetchone()


def person(account_id, time_survived=1200.0):
    return {
        "match_id": "m1",
        "account_id": account_id,
        "player_name": "player_x",
        "kills": 1,
        "headshot_kills": 1,
        "damage_dealt": 150.0,
        "longest_kill": 50.0,
        "time_survived": time_survived,
        "win_place": 3,
    }


def kill(victim="account.v1", distance=50.0, knocker="account.k1"):
    return {
        "match_id": "m1",
        "time": "2026-10-13T10:10:00.000Z",
        "killer": "account.k1",
        "victim": victim,
        "weapon": "WeapHK416_C",
        "distance": distance,
        "is_headshot": True,
        "knocker": knocker,
        "finisher": "account.k1",
    }


def write_sample(kills=None, k1_time_survived=1200.0):
    save_json(
        "processed/match_m1.json",
        {
            "match_id": "m1",
            "game_mode": "squad",
            "map_name": "Baltic_Main",
            "created_at": "2026-10-13T10:00:00Z",
        },
    )
    save_jsonl(
        "processed/participants_m1.jsonl",
        [
            person("account.k1", k1_time_survived),
            person("account.v1", 600.0),
            person("ai.1", None),
        ],
    )
    save_jsonl("processed/kills_m1.jsonl", kills if kills is not None else [kill()])


def test_load_inserts_expected_rows(db, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    write_sample()
    load_all(db)
    assert counts(db) == (1, 3, 1)


def test_load_twice_does_not_duplicate(db, monkeypatch, tmp_path):
    # 21일차: 같은 데이터를 다시 적재해도 행이 늘지 않아야 함
    monkeypatch.chdir(tmp_path)
    write_sample()
    load_all(db)
    load_all(db)
    assert counts(db) == (1, 3, 1)


def test_reload_updates_changed_values(db, monkeypatch, tmp_path):
    # 23일차: 처리 결과가 바뀌면 다시 적재했을 때 DB 값도 바뀌어야 함 (DO UPDATE)
    monkeypatch.chdir(tmp_path)
    write_sample(k1_time_survived=1200.0)
    load_all(db)
    write_sample(k1_time_survived=900.0)
    load_all(db)
    with db.cursor() as cur:
        cur.execute("SELECT time_survived_s FROM participants WHERE account_id = 'account.k1'")
        assert cur.fetchone()[0] == 900


def test_generated_columns(db, monkeypatch, tmp_path):
    # 23일차 is_bot, 25일차 kill_type
    monkeypatch.chdir(tmp_path)
    write_sample(
        kills=[
            kill(victim="account.v1", knocker="account.k1"),
        ]
    )
    load_all(db)
    with db.cursor() as cur:
        cur.execute("SELECT account_id, is_bot FROM participants ORDER BY account_id")
        assert cur.fetchall() == [("account.k1", False), ("account.v1", False), ("ai.1", True)]
        cur.execute("SELECT kill_type FROM kills")
        assert cur.fetchone()[0] == "knocked"


def test_negative_distance_is_rejected(db, monkeypatch, tmp_path):
    # 21일차: -1을 NULL로 바꾸지 않고 -0.01이 들어오면 CHECK가 막아야 함
    monkeypatch.chdir(tmp_path)
    write_sample(kills=[kill(distance=-0.01)])
    with pytest.raises(psycopg.errors.CheckViolation):
        load_all(db)
    db.rollback()


def test_victim_not_in_participants_is_rejected(db, monkeypatch, tmp_path):
    # 22일차: 참가자 목록에 없는 사람이 죽은 기록은 FK가 막아야 함
    monkeypatch.chdir(tmp_path)
    write_sample(kills=[kill(victim="account.unknown")])
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        load_all(db)
    db.rollback()


def test_null_distance_is_allowed(db, monkeypatch, tmp_path):
    # 21일차: AI 킬의 거리는 NULL로 들어가야 함
    monkeypatch.chdir(tmp_path)
    write_sample(kills=[kill(distance=None)])
    load_all(db)
    assert counts(db) == (1, 3, 1)


def queue_rows(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT account_id, status FROM player_queue ORDER BY account_id")
        return cur.fetchall()


def test_seed_queue_adds_humans_only(db, monkeypatch, tmp_path):
    # 46일차: AI 참가자는 대기열에 들어가지 않음
    monkeypatch.chdir(tmp_path)
    write_sample()  # 참가자: account.k1, account.v1, ai.1
    load_all(db)
    with db.cursor() as cur:
        added = seed_queue(cur)
    db.commit()
    assert added == 2
    assert queue_rows(db) == [("account.k1", "pending"), ("account.v1", "pending")]


def test_seed_queue_twice_adds_nothing(db, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    write_sample()
    load_all(db)
    with db.cursor() as cur:
        seed_queue(cur)
        second = seed_queue(cur)
    db.commit()
    assert second == 0


def test_seed_queue_keeps_collected_players(db, monkeypatch, tmp_path):
    # 37일차 Q1: 다시 채워도 이미 수집한 플레이어의 기록이 지워지면 안 됨 (DO NOTHING)
    monkeypatch.chdir(tmp_path)
    write_sample()
    load_all(db)
    with db.cursor() as cur:
        seed_queue(cur)
        cur.execute(
            "UPDATE player_queue SET status = 'done', last_collected_at = now() WHERE account_id = 'account.k1'"
        )
        seed_queue(cur)
        cur.execute("SELECT status, last_collected_at IS NOT NULL FROM player_queue WHERE account_id = 'account.k1'")
        row = cur.fetchone()
    db.commit()
    assert row == ("done", True)


def add_queue(conn, rows):
    # (account_id, status, last_collected_at, attempts)를 대기열에 직접 넣는 도우미
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO player_queue (account_id, status, last_collected_at, attempts) VALUES (%s, %s, %s, %s)",
            rows,
        )
    conn.commit()


QUEUE_SAMPLE = [
    ("account.a", "pending", None, 0),
    ("account.b", "done", "2026-11-10T00:00:00Z", 0),
    ("account.c", "done", "2026-11-01T00:00:00Z", 0),
    ("account.d", "failed", None, 3),
    ("account.e", "failed", None, 1),
]


def test_next_batch_order(db):
    # 47일차: 수집 안 한 사람 먼저, 그다음 오래전에 수집한 사람, 3번 실패한 사람은 제외
    add_queue(db, QUEUE_SAMPLE)
    with db.cursor() as cur:
        assert next_batch(cur, n=10) == ["account.a", "account.e", "account.c", "account.b"]


def test_next_batch_limit(db):
    add_queue(db, QUEUE_SAMPLE)
    with db.cursor() as cur:
        assert next_batch(cur, n=2) == ["account.a", "account.e"]


def test_next_batch_empty_queue(db):
    with db.cursor() as cur:
        assert next_batch(cur) == []
