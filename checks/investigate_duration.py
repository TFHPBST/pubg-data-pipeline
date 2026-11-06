import json
from datetime import datetime
from pathlib import Path


def to_time(s):
    return datetime.fromisoformat(s)


for path in Path("processed").glob("match_*.json"):
    match_id = path.stem.replace("match_", "")
    with open(f"raw/match_{match_id}.json", encoding="utf-8") as f:
        attrs = json.load(f)["data"]["attributes"]
    duration_min = attrs["duration"] / 60
    if duration_min <= 60:
        continue

    with open(f"raw/telemetry_{match_id}.json", encoding="utf-8") as f:
        telemetry = json.load(f)

    first_time = to_time(telemetry[0]["_D"])
    last_time = to_time(telemetry[-1]["_D"])
    marks = {}
    for e in telemetry:
        if e["_T"] in ("LogMatchStart", "LogMatchEnd") and e["_T"] not in marks:
            marks[e["_T"]] = to_time(e["_D"])

    max_survived = 0
    with open(f"processed/participants_{match_id}.jsonl", encoding="utf-8") as f:
        for line in f:
            max_survived = max(max_survived, json.loads(line)["time_survived"])

    print(f"\n매치 {match_id[:8]} ({attrs['mapName']})")
    print(f"  매치 응답 duration: {duration_min:.1f}분, createdAt: {attrs['createdAt']}")
    print(f"  텔레메트리 첫 이벤트 ~ 마지막 이벤트: {(last_time - first_time).total_seconds() / 60:.1f}분")
    if "LogMatchStart" in marks and "LogMatchEnd" in marks:
        match_min = (marks["LogMatchEnd"] - marks["LogMatchStart"]).total_seconds() / 60
        print(f"  LogMatchStart ~ LogMatchEnd: {match_min:.1f}분")
    else:
        print(f"  시작/종료 이벤트: {list(marks.keys())}")
    print(f"  참가자 최대 생존 시간: {max_survived / 60:.1f}분")
