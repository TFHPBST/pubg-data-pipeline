import json
from pathlib import Path

# 1) 참가자 키 모으기
part_keys = set()
for path in Path("processed").glob("participants_*.jsonl"):
    with open(path, encoding="utf-8") as f:
        for line in f:
            p = json.loads(line)
            part_keys.add((p["match_id"], p["account_id"]))

# 2) 참가자 목록에 없는 killer, victim 찾기
missing = {}  # (match_id, account_id) -> {"killer": 횟수, "victim": 횟수}
for path in Path("processed").glob("kills_*.jsonl"):
    with open(path, encoding="utf-8") as f:
        for line in f:
            k = json.loads(line)
            for role in ["killer", "victim"]:
                key = (k["match_id"], k[role])
                if key not in part_keys:
                    roles = missing.setdefault(key, {})
                    roles[role] = roles.get(role, 0) + 1

print(f"참가자 목록에 없는 계정: {len(missing)}개")

# 3) 계정마다 원본에서 흔적 찾기
for i, ((mid, acc), roles) in enumerate(missing.items(), start=1):
    with open(f"processed/match_{mid}.json", encoding="utf-8") as f:
        summary = json.load(f)
    raw_match_text = Path(f"raw/match_{mid}.json").read_text(encoding="utf-8")

    with open(f"raw/telemetry_{mid}.json", encoding="utf-8") as f:
        telemetry = json.load(f)
    event_types = {}
    for e in telemetry:
        if acc in json.dumps(e):
            event_types[e["_T"]] = event_types.get(e["_T"], 0) + 1

    print(f"\n[{i}] 매치 {mid[:8]} ({summary['game_mode']}, {summary['map_name']}) 계정 종류: {acc.split('.')[0]}")
    print(f"    kills에서의 역할: {roles}")
    print(f"    매치 응답 파일에 계정 ID 존재: {acc in raw_match_text}")
    print("    텔레메트리 이벤트:")
    for t, c in sorted(event_types.items(), key=lambda x: (-x[1], x[0])):
        print(f"      {t}: {c}")
