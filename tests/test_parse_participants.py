from collect import parse_participants


def participant(player_id, time_survived=1200.0, kills=2):
    # 매치 응답의 included 중 participant 항목
    return {
        "type": "participant",
        "attributes": {
            "stats": {
                "playerId": player_id,
                "name": "player_x",
                "kills": kills,
                "headshotKills": 1,
                "damageDealt": 250.0,
                "longestKill": 30.5,
                "timeSurvived": time_survived,
                "winPlace": 5,
            }
        },
    }


def match_data(*items):
    # 매치 응답에서 parse_participants가 읽는 부분
    return {"data": {"id": "m1"}, "included": list(items)}


def test_human_values_are_copied():
    rows = parse_participants(match_data(participant("account.a", time_survived=1500.0, kills=3)))
    assert len(rows) == 1
    row = rows[0]
    assert row["match_id"] == "m1"
    assert row["account_id"] == "account.a"
    assert row["kills"] == 3
    assert row["headshot_kills"] == 1
    assert row["longest_kill"] == 30.5
    assert row["time_survived"] == 1500.0
    assert row["win_place"] == 5


def test_ai_time_survived_is_none():
    # 23일차: AI의 생존 시간은 경기 시간보다 길게 기록되는 경우가 있어 쓰지 않음
    rows = parse_participants(match_data(participant("ai.1", time_survived=29000.0)))
    assert rows[0]["account_id"] == "ai.1"
    assert rows[0]["time_survived"] is None


def test_non_participant_items_are_ignored():
    # 실제 응답의 included에는 roster, asset 같은 다른 종류도 섞여 있음
    data = match_data(
        {"type": "roster"},
        participant("account.a"),
        {"type": "asset"},
        participant("ai.1"),
    )
    rows = parse_participants(data)
    assert len(rows) == 2
    assert [r["account_id"] for r in rows] == ["account.a", "ai.1"]
