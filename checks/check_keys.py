import json
from pathlib import Path

# 1) participants: PK (match_id, account_id)가 겹치지 않는지
part_total = 0
part_keys = set()
for path in Path("processed").glob("participants_*.jsonl"):
    with open(path, encoding="utf-8") as f:
        for line in f:
            p = json.loads(line)
            part_total += 1
            part_keys.add((p["match_id"], p["account_id"]))
print(f"participants 전체 {part_total}행 / 고유 키 {len(part_keys)}개")

# 2) kills: PK (match_id, victim, time)가 겹치지 않는지
#    + FK: killer와 victim이 그 매치의 참가자인지
kill_total = 0
kill_keys = set()
missing_killer = 0
missing_victim = 0
for path in Path("processed").glob("kills_*.jsonl"):
    with open(path, encoding="utf-8") as f:
        for line in f:
            k = json.loads(line)
            kill_total += 1
            kill_keys.add((k["match_id"], k["victim"], k["time"]))
            if (k["match_id"], k["killer"]) not in part_keys:
                missing_killer += 1
            if (k["match_id"], k["victim"]) not in part_keys:
                missing_victim += 1
print(f"kills 전체 {kill_total}행 / 고유 키 {len(kill_keys)}개")
print(f"참가자 목록에 없는 killer {missing_killer}건 / victim {missing_victim}건")
