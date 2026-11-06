import json
from pathlib import Path


def match_info(match_id):
    with open(f"raw/match_{match_id}.json", encoding="utf-8") as f:
        data = json.load(f)
    a = data["data"]["attributes"]
    participants = [i for i in data["included"] if i["type"] == "participant"]
    n_participants = len(participants)
    n_ai = sum(1 for p in participants if p["attributes"]["stats"]["playerId"].startswith("ai."))
    return {
        "game_mode": a["gameMode"],
        "match_type": a.get("matchType"),
        "custom": a.get("isCustomMatch"),
        "map": a["mapName"],
        "duration_min": round(a["duration"] / 60, 1),
        "participants": n_participants,
        "ai": n_ai,
    }


# 마지막 실행 로그에서 건너뛴 매치 ID
with open("logs/pipeline_runs.jsonl", encoding="utf-8") as f:
    last_run = json.loads(f.readlines()[-1])
skipped_ids = [s["match_id"] for s in last_run["skipped"]]

# processed에 있는 수집된 매치 ID
collected_ids = [p.stem.replace("match_", "") for p in Path("processed").glob("match_*.json")]

for title, ids in [("건너뜀", skipped_ids), ("수집됨", collected_ids)]:
    print(f"\n== {title} {len(ids)}개 ==")
    groups = {}
    for mid in ids:
        info = match_info(mid)
        key = (info["game_mode"], info["match_type"], info["custom"], info["map"])
        g = groups.setdefault(key, {"count": 0, "participants": [], "duration": []})
        g.setdefault("ai", []).append(info["ai"])
        g["count"] += 1
        g["participants"].append(info["participants"])
        g["duration"].append(info["duration_min"])
    for key, g in sorted(groups.items(), key=lambda x: -x[1]["count"]):
        mode, mtype, custom, map_name = key
        print(
            f"{mode:14} type={mtype!s:12} custom={custom!s:5} {map_name:14} "
            f"{g['count']}개 | 참가자 {min(g['participants'])}~{max(g['participants'])}명 | "
            f"(AI {min(g['ai'])}~{max(g['ai'])}) |"
            f"시간 {min(g['duration'])}~{max(g['duration'])}분"
        )
