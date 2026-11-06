import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg

from collect import count_lines, run_collect, run_collect_candidates, run_reprocess
from load import get_conninfo, run_load


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="PUBG 매치 수집 후 DB 적재")
    parser.add_argument("player_name", nargs="?", help="조회할 플레이어 이름")
    parser.add_argument("--limit", type=int, default=3, help="처리할 최근 매치 수 (기본 3)")
    parser.add_argument("--reprocess", action="store_true", help="새로 수집하지 않고 raw에 있는 매치만 다시 처리")
    parser.add_argument("--candidates", metavar="FILE", help="후보 파일의 계정들의 최근 매치를 수집")
    args = parser.parse_args(argv)

    chosen = [bool(args.player_name), args.reprocess, bool(args.candidates)]
    if sum(chosen) != 1:
        parser.error("플레이어 이름, --reprocess, --candidates 중 하나만 지정하세요")
    return args


def append_run_log(record, path="logs/pipeline_runs.jsonl"):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


TABLES = ["matches", "participants", "kills"]


def count_file_rows():
    processed = Path("processed")
    return {
        "matches": len(list(processed.glob("match_*.json"))),
        "participants": sum(count_lines(p) for p in processed.glob("participants_*.jsonl")),
        "kills": sum(count_lines(p) for p in processed.glob("kills_*.jsonl")),
    }


def count_db_rows(conninfo):
    counts = {}
    # 데이터 베이스와 연결
    with psycopg.connect(conninfo) as conn:
        # 값을 넣어서 나온 결과를 cur에 저장
        with conn.cursor() as cur:
            # matches, participants, kills를 각각 넣어서 반복
            for table in TABLES:
                # SQL 실행을 위해 execute() 사용
                cur.execute(f"SELECT count(*) FROM {table}")
                # fetchone()은 (1000,)와 같이 튜플 형태로 받아옴. 그래서 fetchone()[0]이면 1000
                counts[table] = cur.fetchone()[0]
    return counts


def decide_status(failed, checks):
    if not all(c["ok"] for c in checks.values()):
        return "verify_failed"
    if failed:
        return "partial"
    return "ok"


def verify(conninfo):
    file_counts = count_file_rows()
    db_counts = count_db_rows(conninfo)
    result = {}
    for table in TABLES:
        result[table] = {
            "file": file_counts[table],
            "db": db_counts[table],
            "ok": file_counts[table] == db_counts[table],
        }
    return result


def collect_step(args, record):
    if args.reprocess:
        record["mode"] = "reprocess"
        return run_reprocess()
    if args.candidates:
        record["mode"] = "candidates"
        record["limit"] = args.limit
        with open(args.candidates, encoding="utf-8") as f:
            account_ids = [c["account_id"] for c in json.load(f)]
        return run_collect_candidates(account_ids, args.limit)
    record["mode"] = "player"
    record["limit"] = args.limit
    return run_collect(args.player_name, args.limit)


# Get-Content logs/pipeline_runs.jsonl -Tail 1 -Encoding UTF8
# logs 폴더의 pipeline_runs.jsonl의 파일을 마지막 줄을 utf-8 인코딩 후 출력
def main(argv=None):
    args = parse_args(argv)
    started = time.monotonic()
    record = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
    }
    try:
        succeeded, failed, skipped = collect_step(args, record)
        record["collected"] = len(succeeded)
        record["failed"] = failed
        record["skipped"] = skipped
        print({"수집 성공": len(succeeded), "수집 실패": len(failed), "건너뜀": len(skipped)})

        record["loaded"] = run_load()

        checks = verify(get_conninfo())
        record["verify"] = checks
        for table, c in checks.items():
            mark = "OK" if c["ok"] else "불일치"
            print(f"{table}: 파일 {c['file']} / DB {c['db']} → {mark}")

        record["status"] = decide_status(failed, checks)
    except Exception as err:
        record["status"] = "error"
        record["error"] = f"{type(err).__name__}: {err}"
        raise
    finally:
        record["duration_s"] = round(time.monotonic() - started, 1)
        append_run_log(record)

    if record["status"] != "ok":
        print(f"[경고] 실행 상태: {record['status']}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
