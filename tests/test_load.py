import os
from pathlib import Path

import psycopg
import pytest

from collect import save_json, save_jsonl
from load import load_kills, load_matches, load_participants

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
            cur.execute("DROP TABLE IF EXISTS kills, participants, matches CASCADE")
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
