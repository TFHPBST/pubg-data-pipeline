import json
from pathlib import Path


def acc(obj):
    # 캐릭터 정보에서 계정 ID를 꺼냄. 비어 있으면 None
    return obj["accountId"] if obj else None


def same_damage(a, b):
    # 두 피해 정보가 같은 공격을 가리키는지
    if not a or not b:
        return False
    keys = ["damageReason", "damageCauserName", "distance"]
    return all(a.get(k) == b.get(k) for k in keys)


counts = {}


def bump(key):
    counts[key] = counts.get(key, 0) + 1


for path in Path("processed").glob("match_*.json"):
    match_id = path.stem.replace("match_", "")
    with open(path, encoding="utf-8") as f:
        mode = json.load(f)["game_mode"].replace("-fpp", "")
    with open(f"raw/telemetry_{match_id}.json", encoding="utf-8") as f:
        telemetry = json.load(f)

    for e in telemetry:
        if e["_T"] != "LogPlayerKillV2":
            continue
        killer = acc(e.get("killer"))
        victim = acc(e.get("victim"))
        if not killer or not killer.startswith("account."):
            continue
        if not victim or not victim.startswith("account."):
            continue

        knocker = acc(e.get("dBNOMaker"))
        finisher = acc(e.get("finisher"))
        kdi = e.get("killerDamageInfo")

        bump(f"{mode} | 사람→사람 킬")
        if knocker is None:
            bump(f"{mode} | 기절 없이 사망")
        else:
            bump(f"{mode} | 기절 후 사망")
            if knocker == killer:
                bump(f"{mode} |   killer = 기절시킨 사람")
            if finisher == killer:
                bump(f"{mode} |   killer = 마무리한 사람")
            if knocker == finisher:
                bump(f"{mode} |   기절시킨 사람 = 마무리한 사람")
            if same_damage(kdi, e.get("dBNODamageInfo")):
                bump(f"{mode} |   killerDamageInfo = 기절 공격")
            if same_damage(kdi, e.get("finishDamageInfo")):
                bump(f"{mode} |   killerDamageInfo = 마무리 공격")

for key in sorted(counts):
    print(f"{key}: {counts[key]}")
