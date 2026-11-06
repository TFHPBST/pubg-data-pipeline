import json
from pathlib import Path


def headshot_ratio(kills, headshot_kills):
    if kills == 0:
        return None
    return headshot_kills / kills


def validate_participant(p):
    errors = []
    if p["kills"] < 0:
        errors.append("kills가 0보다 작음")
    if p["headshot_kills"] > p["kills"]:
        errors.append("headshot_kills가 kills보다 큼")
    return errors


def load_matches(folder):
    matches = []
    for path in sorted(Path(folder).glob("*.json")):
        print("읽는 중:", path)
        with open(path, encoding="utf-8") as f:
            matches.append(json.load(f))
    return matches


def load_matches_safe(folder):
    matches = []
    failed = []
    for path in sorted(Path(folder).glob("*.json")):
        try:
            with open(path, encoding="utf-8") as f:
                matches.append(json.load(f))
        except json.JSONDecodeError as e:
            failed.append({"file": path.name, "error": str(e)})
    return matches, failed


def validate_match(match):
    errors = []
    # 1. participants 키가 없으면 더 검사할 수 없으므로 바로 끝냄
    if "participants" not in match:
        errors.append("participants 키 없음")
        return errors
    # 2. 모든 참가자에게 필요한 키가 있는지 확인
    required_keys = ["account_id", "kills", "headshot_kills"]
    for i, p in enumerate(match["participants"]):
        for key in required_keys:
            if key not in p:
                errors.append(f"{i}번째 참가자: {key} 키 없음")
    return errors


def validate_event_structure(event):
    errors = []
    required_keys = ["match_id", "killer", "victim", "weapon", "distance", "is_headshot"]
    for key in required_keys:
        if key not in event:
            errors.append(f"{key} 키 없음")
    return errors


def validate_data(e):
    errors = []
    if e["distance"] < 0:
        errors.append("거리가 0보다 작음")
    if e["killer"] == e["victim"]:
        errors.append("킬러와 희생자가 같음")
    return errors
