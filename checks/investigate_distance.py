import json
from pathlib import Path

missing_total = 0  # distance가 음수인 행 수
missing_killer_type = {}  # 음수 행의 killer 종류별 개수
missing_weapons = {}  # 음수 행의 weapon별 개수
missing_matches = {}  # 음수 행의 매치별 개수
all_killer_type = {}  # 전체 kills의 killer 종류별 개수 (비교용)

for path in Path("processed").glob("kills_*.jsonl"):
    with open(path, encoding="utf-8") as f:
        for line in f:
            k = json.loads(line)
            killer_type = k["killer"].split(".")[0]  # "ai" 또는 "account"
            all_killer_type[killer_type] = all_killer_type.get(killer_type, 0) + 1

            if k["distance"] is None:
                missing_total += 1
                missing_killer_type[killer_type] = missing_killer_type.get(killer_type, 0) + 1
                missing_weapons[k["weapon"]] = missing_weapons.get(k["weapon"], 0) + 1
                mid = k["match_id"][:8]
                missing_matches[mid] = missing_matches.get(mid, 0) + 1

print(f"distance 없음 행: {missing_total}개")
print(f"distance 없음 행의 killer 종류: {missing_killer_type}")
print(f"distance 없음 행의 매치별 개수: {missing_matches}")
print("distance 없음 행의 weapon:")
for weapon, count in sorted(missing_weapons.items(), key=lambda x: (-x[1], x[0])):
    print(f"  {weapon}: {count}")
print(f"전체 kills의 killer 종류: {all_killer_type}")
