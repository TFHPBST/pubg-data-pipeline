import pytest

from collect import parse_kills


def char(account_id):
    # 텔레메트리의 캐릭터 정보. 계정이 없으면 None
    return {"accountId": account_id} if account_id else None


def kill_event(
    killer="account.k1",
    victim="account.v1",
    distance=5000,
    reason="NonSpecific",
    knocker=None,
    finisher=None,
    damage_type="Damage_Gun",
    is_suicide=False,
    time="2026-10-13T10:00:00.000Z",
):
    # LogPlayerKillV2 중 parse_kills가 읽는 필드만 가진 이벤트
    return {
        "_T": "LogPlayerKillV2",
        "_D": time,
        "killer": char(killer),
        "victim": char(victim),
        "dBNOMaker": char(knocker),
        "finisher": char(finisher),
        "isSuicide": is_suicide,
        "killerDamageInfo": {
            "damageCauserName": "WeapHK416_C",
            "distance": distance,
            "damageReason": reason,
        },
        "finishDamageInfo": {"damageTypeCategory": damage_type},
    }


def test_normal_kill_converts_cm_to_m():
    success, excluded = parse_kills([kill_event(distance=5000)], "m1")
    assert len(success) == 1
    assert excluded == []
    assert success[0]["distance"] == 50.0


def test_headshot_is_detected():
    success, _ = parse_kills([kill_event(reason="HeadShot")], "m1")
    assert success[0]["is_headshot"] is True


def test_ai_distance_minus_one_becomes_none():
    # 21일차: AI의 킬은 거리가 -1로 기록됨
    success, _ = parse_kills([kill_event(killer="ai.1", distance=-1)], "m1")
    assert success[0]["distance"] is None


def test_unknown_negative_distance_raises():
    # -1이 아닌 음수는 의미를 모르므로 멈춰야 함
    with pytest.raises(RuntimeError):
        parse_kills([kill_event(distance=-5)], "m1")


def test_lava_is_environment_death():
    # 16일차: 용암 사망은 killer가 없고 isSuicide도 False
    event = kill_event(killer=None, damage_type="Damage_Lava")
    success, excluded = parse_kills([event], "m1")
    assert success == []
    assert excluded[0]["reason"] == "환경 사망"


def test_suicide_is_excluded():
    event = kill_event(killer=None, is_suicide=True, damage_type="Damage_Explosion_Grenade")
    _, excluded = parse_kills([event], "m1")
    assert excluded[0]["reason"] == "자살"


def test_other_events_are_ignored():
    events = [{"_T": "LogPlayerPosition", "_D": "2026-10-13T10:00:00.000Z"}, kill_event()]
    success, excluded = parse_kills(events, "m1")
    assert len(success) + len(excluded) == 1


def test_knocker_and_finisher_are_recorded():
    # 25일차: 기절시킨 사람과 마무리한 사람
    event = kill_event(killer="account.k1", knocker="account.k2", finisher="account.k1")
    success, _ = parse_kills([event], "m1")
    assert success[0]["knocker"] == "account.k2"
    assert success[0]["finisher"] == "account.k1"


def test_monster_killer_is_excluded():
    # 34일차: 비켄디의 곰처럼 플레이어가 아닌 킬러
    event = kill_event(killer="Monster.Bear-15")
    success, excluded = parse_kills([event], "m1")
    assert success == []
    assert "Monster" in excluded[0]["reason"]


def test_monster_victim_is_excluded():
    event = kill_event(victim="Monster.Bear-15")
    success, excluded = parse_kills([event], "m1")
    assert success == []
    assert "Monster" in excluded[0]["reason"]
