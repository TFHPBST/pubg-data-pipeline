# PUBG 매치 수집: API → raw 캐시 → 파싱 → processed 저장
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

PLAYER_PREFIXES = ("account.", "ai.")
SUPPORTED_MODES = {"solo", "solo-fpp", "duo", "duo-fpp", "squad", "squad-fpp"}
SUPPORTED_MATCH_TYPES = {"official"}
ENVIRONMENT_DAMAGE = ["Damage_BlueZone", "Damage_Lava"]


def get_headers():
    api_key = os.environ.get("PUBG_API_KEY")
    if api_key is None:
        raise RuntimeError("PUBG_API_KEY 환경변수가 없습니다")
    return {"Authorization": f"Bearer {api_key}", "Accept": "application/vnd.api+json"}


PLATFORM = "steam"
BASE_URL = f"https://api.pubg.com/shards/{PLATFORM}"


class SkippedMatch(Exception):
    """분석 대상이 아니라서 의도적으로 건너뛴 매치"""


class ApiError(RuntimeError):
    """재시도해도 소용없는 응답 (404 등)"""

    def __init__(self, status_code, url):
        super().__init__(f"재시도 불가 오류 {status_code}: {url}")
        self.status_code = status_code


class RetryExhausted(RuntimeError):
    """재시도를 모두 써도 성공하지 못함"""


def check_supported(match_data):
    attrs = match_data["data"]["attributes"]
    game_mode = attrs["gameMode"]
    if game_mode not in SUPPORTED_MODES:
        raise SkippedMatch(f"지원하지 않는 모드: {game_mode}")
    match_type = attrs.get("matchType")
    if match_type not in SUPPORTED_MATCH_TYPES:
        raise SkippedMatch(f"지원하지 않는 매치 종류: {match_type}")


def fetch_player(player_name):
    url = f"{BASE_URL}/players"
    params = {"filter[playerNames]": player_name}
    try:
        player = fetch_with_retry(url=url, headers=get_headers(), params=params)
    except ApiError as err:
        if err.status_code == 404:
            raise RuntimeError("플레이어를 찾을 수 없음: PUBG_PLAYER_NAME 값을 확인하세요") from err
        raise
    save_json(path="raw/player.json", data=player)
    return player


def save_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_with_retry(url, headers=None, params=None, max_retries=3):
    for attempt in range(max_retries + 1):
        wait = 2**attempt
        is_last = attempt == max_retries

        # 1. 요청 보내기
        try:
            response = requests.get(url, headers=headers, params=params, timeout=5)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as err:
            print(f"{attempt + 1}번째 시도 실패, 이유: {type(err).__name__}")
            if not is_last:
                print(f"  {wait}초 대기 후 재시도")
                time.sleep(wait)
            continue

        # 2. 상태 코드 확인
        status_code = response.status_code
        if status_code == 200:
            return response.json()
        elif status_code == 429 or status_code >= 500:
            print(f"{attempt + 1}번째 시도 실패, 이유: {status_code}")
            if not is_last:
                print(f"  {wait}초 대기 후 재시도")
                time.sleep(wait)
            continue
        else:
            raise ApiError(status_code, url)

    # 3. 반복이 끝났다 = 한 번도 200을 받지 못했다
    raise RetryExhausted(f"최대 재시도 횟수 초과 ({max_retries + 1}회 시도): {url}")


# C1
def load_or_fetch(path, url, needs_auth=False):
    if Path(path).exists():
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        print(f"캐시 사용: {path}")
        return data
    headers = get_headers() if needs_auth else None
    data = fetch_with_retry(url=url, headers=headers)
    save_json(path, data)
    print(f"다운로드: {path}")
    return data


# C2
match_id1 = "7a65b168-4a2f-4666-a21f-8be504562e1a"  # 첫 번째 매치
path1 = f"raw/match_{match_id1}.json"
url1 = f"{BASE_URL}/matches/{match_id1}"

match_id2 = "e222fcaa-e557-45ad-87cc-82786c298ff2"  # 두 번째 매치
path2 = f"raw/match_{match_id2}.json"
url2 = f"{BASE_URL}/matches/{match_id2}"


def parse_participants(match_data):
    rows = []
    match_id = match_data["data"]["id"]
    for i in match_data["included"]:
        if i["type"] == "participant":
            s = i["attributes"]["stats"]
            account_id = s["playerId"]
            # AI 참가자의 생존 시간은 실제 경기 시간보다 길게 기록되는 경우가 있어 쓰지 않음 (23일차 조사)
            time_survived = None if account_id.startswith("ai.") else s["timeSurvived"]
            rows.append(
                {
                    "match_id": match_id,
                    "account_id": account_id,
                    "player_name": s["name"],
                    "kills": s["kills"],
                    "headshot_kills": s["headshotKills"],
                    "damage_dealt": s["damageDealt"],
                    "longest_kill": s["longestKill"],
                    "time_survived": time_survived,
                    "win_place": s["winPlace"],
                }
            )
    return rows


# C3
def find_telemetry_url(match_data):
    telemetry_url = None
    for i in match_data["included"]:
        if i["type"] == "asset":
            telemetry_url = i["attributes"]["URL"]
    match_id = match_data["data"]["id"]
    if telemetry_url is None:
        raise RuntimeError(f"텔레메트리 주소가 없습니다: {match_id}")
    return telemetry_url


def account_of(character):
    # 캐릭터 정보에서 계정 ID를 꺼냄. 비어 있으면 None
    return character["accountId"] if character else None


# C4
def parse_kills(telemetry_data, match_id):
    success = []
    excluded = []
    kill_event_count = 0
    for t in telemetry_data:
        if t["_T"] != "LogPlayerKillV2":
            continue
        kill_event_count += 1
        killer = t["killer"]
        damage_info = t["finishDamageInfo"]
        damage_type = damage_info["damageTypeCategory"]
        victim_acc = t["victim"]["accountId"]
        log_time = t["_D"]
        if killer is None:
            if t["isSuicide"]:
                reason = "자살"
            elif damage_type in ENVIRONMENT_DAMAGE:
                reason = "환경 사망"
            else:
                reason = "기타 사망"
            excluded_dict = {
                "match_id": match_id,
                "time": log_time,
                "victim": victim_acc,
                "damage_type": damage_type,
                "reason": reason,
            }
            excluded.append(excluded_dict)
            continue
        killer_acc = killer["accountId"]
        if not killer_acc.startswith(PLAYER_PREFIXES):
            excluded.append(
                {
                    "match_id": match_id,
                    "time": log_time,
                    "victim": victim_acc,
                    "damage_type": damage_type,
                    "reason": f"플레이어가 아닌 킬러: {killer_acc.split('.')[0]}",
                }
            )
            continue
        if not victim_acc.startswith(PLAYER_PREFIXES):
            excluded.append(
                {
                    "match_id": match_id,
                    "time": log_time,
                    "victim": victim_acc,
                    "damage_type": damage_type,
                    "reason": f"플레이어가 아닌 사망자: {victim_acc.split('.')[0]}",
                }
            )
            continue
        killer_acc = t["killer"]["accountId"]
        killer_info = t["killerDamageInfo"]
        weapon = killer_info["damageCauserName"]
        raw_distance = killer_info["distance"]
        if raw_distance == -1:
            distance = None
        elif raw_distance < 0:
            raise RuntimeError(f"알 수 없는 distance 값: {match_id} {log_time} {raw_distance}")
        else:
            distance = round(raw_distance / 100, 2)
        damage_reason = killer_info["damageReason"]
        is_headshot = damage_reason == "HeadShot"
        success.append(
            {
                "match_id": match_id,
                "time": log_time,
                "killer": killer_acc,
                "victim": victim_acc,
                "weapon": weapon,
                "distance": distance,
                "is_headshot": is_headshot,
                "knocker": account_of(t.get("dBNOMaker")),
                "finisher": account_of(t.get("finisher")),
            }
        )
    total = len(success) + len(excluded)
    if total != kill_event_count:
        raise RuntimeError(
            f"처리되지 않은 사망 이벤트: {match_id} "
            f"(사망 {kill_event_count}건, 정상 {len(success)} + 제외 {len(excluded)} = {total})"
        )
    return success, excluded


# C5
def save_jsonl(path, rows):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def process_match(match_id):
    path = f"raw/match_{match_id}.json"
    url = f"{BASE_URL}/matches/{match_id}"
    data = load_or_fetch(path=path, url=url, needs_auth=True)
    check_supported(data)
    game_mode = data["data"]["attributes"]["gameMode"]
    rows = parse_participants(data)
    # 저장
    save_jsonl(path=f"processed/participants_{match_id}.jsonl", rows=rows)
    # 텔레메트리 주소 찾기
    telemetry_url = find_telemetry_url(data)
    # 텔레메트리 받기
    telemetry_data = load_or_fetch(path=f"raw/telemetry_{match_id}.json", url=telemetry_url)
    # 킬 추출
    success, excluded = parse_kills(telemetry_data=telemetry_data, match_id=match_id)
    # 저장
    save_jsonl(path=f"processed/kills_{match_id}.jsonl", rows=success)
    save_json(path=f"processed/excluded_kills_{match_id}.json", data=excluded)
    # 요약 딕셔너리
    map_name = data["data"]["attributes"]["mapName"]
    created_at = data["data"]["attributes"]["createdAt"]
    summary = {
        "match_id": match_id,
        "game_mode": game_mode,
        "map_name": map_name,
        "created_at": created_at,
        "participants": len(rows),
        "kills": len(success),
        "excluded": len(excluded),
    }
    save_json(f"processed/match_{match_id}.json", summary)
    return summary


def count_lines(path):
    with open(path, encoding="utf-8") as f:
        return sum(1 for _ in f)


def run_batch(match_ids):
    succeeded = []
    failed = []
    skipped = []
    for match_id in match_ids:
        try:
            summary = process_match(match_id)
            succeeded.append(summary)
            print(f"성공: {match_id}")
        except SkippedMatch as err:
            skipped.append({"match_id": match_id, "reason": str(err)})
            print(f"건너뜀: {match_id} ({err})")
        except Exception as err:
            failed.append({"match_id": match_id, "error": f"{type(err).__name__}: {err}"})
            print(f"실패: {match_id} ({type(err).__name__})")

    log = {"run_at": datetime.now(timezone.utc).isoformat(), "success": succeeded, "skipped": skipped, "failed": failed}
    save_json(path="processed/collect_log.json", data=log)
    return succeeded, failed, skipped


def run_collect(player_name, limit):
    player = fetch_player(player_name)
    match_refs = player["data"][0]["relationships"]["matches"]["data"]
    match_ids = [m["id"] for m in match_refs[:limit]]
    (
        succeeded,
        skipped,
        failed,
    ) = run_batch(match_ids)
    return succeeded, skipped, failed


def run_reprocess():
    match_ids = sorted(p.stem.replace("match_", "") for p in Path("raw").glob("match_*.json"))
    return run_batch(match_ids)


def fetch_players_by_ids(account_ids):
    if len(account_ids) > 10:
        raise ValueError(f"한 번에 최대 10명까지 조회할 수 있습니다: {len(account_ids)}명")
    url = f"{BASE_URL}/players"
    params = {"filter[playerIds]": ",".join(account_ids)}
    try:
        data = fetch_with_retry(url=url, headers=get_headers(), params=params)
    except ApiError as err:
        if err.status_code == 404:
            raise RuntimeError("후보 계정을 찾을 수 없음: candidates.json을 다시 만드세요") from err
        raise
    save_json("raw/players_candidates.json", data)

    players = data["data"]
    if len(players) != len(account_ids):
        print(f"[주의] 후보 {len(account_ids)}명 중 {len(players)}명만 조회됨")
    return players


def run_collect_candidates(account_ids, limit):
    players = fetch_players_by_ids(account_ids)
    match_ids = []
    for p in players:
        for m in p["relationships"]["matches"]["data"][:limit]:
            if m["id"] not in match_ids:
                match_ids.append(m["id"])
    return run_batch(match_ids)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python collect.py <player_name>")
        sys.exit(1)

    succeeded, failed, skipped = run_collect(sys.argv[1], 3)
    print({"성공": len(succeeded), "실패": len(failed), "건너뜀": len(skipped)})

    # 저장 결과 확인: summary 숫자와 실제 파일 줄 수가 같은지
    for s in succeeded:
        mid = s["match_id"]
        p_lines = count_lines(f"processed/participants_{mid}.jsonl")
        k_lines = count_lines(f"processed/kills_{mid}.jsonl")
        ok = (p_lines == s["participants"]) and (k_lines == s["kills"])
        print(f"{mid[:8]} 참가자 {p_lines}줄 / 킬 {k_lines}줄 / 일치: {ok}")
