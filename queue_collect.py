# 대기열 기반 수집 (49일차)
from collect import fetch_players_by_ids
from player_queue import mark_done, mark_failed, next_batch


def collect_from_queue(cur, limiter, budget, fetch=fetch_players_by_ids, match_limit=3):
    match_ids = []
    used = 0
    while used < budget:  # (F)
        ids = next_batch(cur, 10)
        if not ids:
            break  # (G)
        limiter.wait()
        used += 1
        try:
            players = fetch(ids)
        except RuntimeError as err:
            for a in ids:
                mark_failed(cur, a, f"{type(err).__name__}: {err}")
            continue  # (H) 다음 묶음으로
        found = {p["id"] for p in players}
        mark_done(cur, [a for a in ids if a in found])
        for a in ids:
            if a not in found:  # (I)
                mark_failed(cur, a, "조회 결과 없음")
        for p in players:
            for m in p["relationships"]["matches"]["data"][:match_limit]:
                if m["id"] not in match_ids:
                    match_ids.append(m["id"])
    return used, match_ids
