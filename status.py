import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOG_PATH = Path("logs/pipeline_runs.jsonl")


def show_recent(n=10):
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()[-n:]
    for line in lines:
        r = json.loads(line)
        failed = r.get("failed", [])
        skipped = r.get("skipped", [])
        print(
            f"{r['run_at'][:19]}  {r.get('mode', '-'):10}  {r.get('status', '-'):14}  "
            f"수집 {r.get('collected', '-')}  실패 {len(failed)}  건너뜀 {len(skipped)}"
        )
        if r.get("error"):
            print(f"    오류: {r['error'][:120]}")
        for f in failed:
            message = f.get("error") or f.get("reason") or "-"
            print(f"    실패: {f['match_id'][:8]} {message[:80]}")
        for s in skipped:
            print(f"    건너뜀: {s['match_id'][:8]} {s.get('reason', '-')[:80]}")
    last_run = datetime.fromisoformat(json.loads(lines[-1])["run_at"])
    if datetime.now(timezone.utc) - last_run > timedelta(hours=26):
        print(f"\n[경고] 마지막 실행 기록이 {last_run:%Y-%m-%d %H:%M} UTC입니다. run_*.txt를 확인하세요.")


if __name__ == "__main__":
    show_recent()
