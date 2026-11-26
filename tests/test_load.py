import os
from pathlib import Path

import psycopg
import pytest

from collect import RetryExhausted, save_json, save_jsonl
from load import apply_sql_files, load_kills, load_matches, load_participants
from pipeline import quality_metrics
from player_queue import mark_done, mark_failed, next_batch, seed_queue
from queue_collect import collect_from_queue

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


def test_mark_done_updates_state(db):
    add_queue(db, QUEUE_SAMPLE)
    with db.cursor() as cur:
        changed = mark_done(cur, ["account.a", "account.e"])
        cur.execute(
            "SELECT account_id, status, last_collected_at IS NOT NULL, attempts, last_error "
            "FROM player_queue WHERE account_id IN ('account.a', 'account.e') ORDER BY account_id"
        )
        rows = cur.fetchall()
    db.commit()
    assert changed == 2
    assert rows == [("account.a", "done", True, 0, None), ("account.e", "done", True, 0, None)]


def test_failed_three_times_is_excluded(db):
    add_queue(db, [("account.x", "pending", None, 0)])
    with db.cursor() as cur:
        for _ in range(3):
            mark_failed(cur, "account.x", "ApiError: 404")
        assert next_batch(cur) == []
        cur.execute("SELECT status, attempts, last_error FROM player_queue WHERE account_id = 'account.x'")
        assert cur.fetchone() == ("failed", 3, "ApiError: 404")


def test_done_player_excluded_for_a_day(db):
    add_queue(db, QUEUE_SAMPLE)
    with db.cursor() as cur:
        mark_done(cur, ["account.a"])
        assert next_batch(cur) == ["account.e", "account.c", "account.b"]


@pytest.fixture
def cur(db):
    with db.cursor() as c:
        yield c


class FakeLimiter:
    def __init__(self):
        self.waits = 0

    def wait(self):
        self.waits += 1


def make_fetch(missing=(), error=None):
    calls = []

    def fetch(ids):
        calls.append(list(ids))
        if error is not None:
            raise error
        return [{"id": a, "relationships": {"matches": {"data": []}}} for a in ids if a not in missing]

    return fetch, calls


def add_pending(cur, n):
    for i in range(n):
        cur.execute("INSERT INTO player_queue (account_id) VALUES (%s)", (f"account.p{i:02d}",))


def state_of(cur, account_id):
    cur.execute("SELECT status, attempts FROM player_queue WHERE account_id = %s", (account_id,))
    return cur.fetchone()


def count_status(cur, status):
    cur.execute("SELECT count(*) FROM player_queue WHERE status = %s", (status,))
    return cur.fetchone()[0]


def test_queue_collect_stops_at_budget(cur):
    add_pending(cur, 30)
    fetch, calls = make_fetch()
    used, _ = collect_from_queue(cur, FakeLimiter(), budget=2, fetch=fetch)
    assert used == 2  # (A)
    assert count_status(cur, "done") == 20  # (B)


def test_queue_collect_stops_when_queue_empty(cur):
    add_pending(cur, 5)
    fetch, calls = make_fetch()
    limiter = FakeLimiter()
    used, _ = collect_from_queue(cur, limiter, budget=10, fetch=fetch)
    assert used == 1  # (C)
    assert limiter.waits == used


def test_queue_collect_marks_missing_as_failed(cur):
    add_pending(cur, 10)
    missing = {f"account.p{i:02d}" for i in range(3, 10)}
    fetch, _ = make_fetch(missing=missing)
    collect_from_queue(cur, FakeLimiter(), budget=1, fetch=fetch)
    assert count_status(cur, "done") == 3
    assert state_of(cur, "account.p05") == ("failed", 1)  # (D) (상태, attempts)


def test_queue_collect_request_error_fails_whole_batch(cur):
    add_pending(cur, 10)
    fetch, _ = make_fetch(error=RetryExhausted("테스트"))
    used, _ = collect_from_queue(cur, FakeLimiter(), budget=1, fetch=fetch)
    assert used == 1
    assert count_status(cur, "failed") == 10  # (E)


def test_failed_player_not_retried_in_same_run(cur):
    add_pending(cur, 20)
    fetch, _ = make_fetch(missing={"account.p00"})
    collect_from_queue(cur, FakeLimiter(), budget=2, fetch=fetch)
    assert state_of(cur, "account.p00") == ("failed", 1)


def view_exists(cur, name):
    cur.execute("SELECT count(*) FROM information_schema.views WHERE table_name = %s", (name,))
    return cur.fetchone()[0] == 1


def test_apply_sql_files_creates_view(cur):
    assert view_exists(cur, "player_stats") is False  # (A) fixture는 schema.sql만 적용함
    apply_sql_files(cur)
    assert view_exists(cur, "player_stats") is True


def test_apply_sql_files_twice_is_safe(cur):
    apply_sql_files(cur)
    assert apply_sql_files(cur) == 2  # (B)


def test_apply_sql_files_on_empty_db(cur):
    cur.execute("DROP TABLE IF EXISTS kills, participants, matches, player_queue CASCADE")
    apply_sql_files(cur)
    assert view_exists(cur, "player_stats") is True


def test_quality_metrics_on_empty_db(cur):
    assert quality_metrics(cur) == {
        "human_null_survival": 0,
        "bot_with_survival": 0,
        "kills_null_distance_pct": None,  # (E) 사망 기록이 0건이면?
    }


def test_quality_metrics_counts_human_null_survival(cur):
    cur.execute(
        "INSERT INTO matches (match_id, game_mode, map_name, created_at) "
        "VALUES ('m1', 'squad', 'Erangel', '2026-11-01T00:00:00Z')"
    )
    cur.execute(
        "INSERT INTO participants (match_id, account_id, player_name, kills, headshot_kills, "
        "damage_dealt, longest_kill_m, time_survived_s, win_place) "
        "VALUES ('m1', 'account.a', 'someone', 0, 0, 0, 0, NULL, 1)"
    )
    assert quality_metrics(cur)["human_null_survival"] == 1
