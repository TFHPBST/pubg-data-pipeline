import json
from datetime import datetime
from pathlib import Path

MARGIN_SEC = 60  # 기록 오차를 감안한 여유

total_matches = 0
bad_matches = []
total_bad_rows = 0
offsets = []
for path in Path("processed").glob("match_*.json"):
    match_id = path.stem.replace("match_", "")
    total_matches += 1

    with open(f"raw/match_{match_id}.json", encoding="utf-8") as f:
        attrs = json.load(f)["data"]["attributes"]

    with open(f"raw/telemetry_{match_id}.json", encoding="utf-8") as f:
        telemetry = json.load(f)
    marks = {}
    for e in telemetry:
        if e["_T"] in ("LogMatchStart", "LogMatchEnd") and e["_T"] not in marks:
            marks[e["_T"]] = datetime.fromisoformat(e["_D"])
    match_sec = (marks["LogMatchEnd"] - marks["LogMatchStart"]).total_seconds()

    max_offset = None  # (최대 생존 시간 - 경기 시간), 초
    bad = {}  # 계정 종류 -> 초과한 초 목록
    with open(f"processed/participants_{match_id}.jsonl", encoding="utf-8") as f:
        for line in f:
            p = json.loads(line)
            offset = p["time_survived"] - match_sec
            if max_offset is None or offset > max_offset:
                max_offset = offset
            if offset > MARGIN_SEC:
                kind = p["account_id"].split(".")[0]
                bad.setdefault(kind, []).append(offset)

    offsets.append((max_offset, match_id[:8]))
    if bad:
        print(f"\n{match_id[:8]} {attrs['mapName']} 실제 {match_sec / 60:.1f}분")
        for kind, values in bad.items():
            print(f"  {kind}: {len(values)}명, 초과 {min(values) / 60:.1f}~{max(values) / 60:.1f}분")

print("\n매치별 (최대 생존 시간 - 경기 시간), 작은 순:")
for offset, mid in sorted(offsets):
    print(f"  {mid}: {offset:+.0f}초")
