from pathlib import Path

import pytest

import collect
from collect import RetryExhausted

# process_match가 읽는 부분만 가진 정상 매치 응답
MATCH = {
    "data": {
        "id": "m1",
        "attributes": {"gameMode": "squad", "matchType": "official", "mapName": "Baltic_Main", "createdAt": "t"},
    },
    "included": [{"type": "asset", "attributes": {"URL": "https://telemetry/m1"}}],
}


def test_no_files_left_when_telemetry_fails(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    def fake_load_or_fetch(path, url, needs_auth=False):
        if "telemetry" in path:
            raise RetryExhausted("텔레메트리 서버 응답 없음")  # 텔레메트리만 실패
        return MATCH

    monkeypatch.setattr(collect, "load_or_fetch", fake_load_or_fetch)

    with pytest.raises(RetryExhausted):
        collect.process_match("m1")

    # 실패한 매치는 processed/에 아무 흔적도 남기지 않아야 함
    assert not Path("processed/participants_m1.jsonl").exists()
