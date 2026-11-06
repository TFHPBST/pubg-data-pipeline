import pytest
import requests

import collect
from collect import ApiError, RetryExhausted, fetch_with_retry


class FakeResponse:
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self._body = body if body is not None else {}

    def json(self):
        return self._body


def use_fake_server(monkeypatch, outcomes):
    """outcomes를 순서대로 돌려주는 가짜 requests.get과, 기다리지 않는 가짜 sleep"""
    calls = []
    sleeps = []
    queue = list(outcomes)

    def fake_get(url, **kwargs):
        calls.append(kwargs)
        outcome = queue.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(collect.requests, "get", fake_get)
    monkeypatch.setattr(collect.time, "sleep", sleeps.append)
    return calls, sleeps


def test_success_on_first_try(monkeypatch):
    calls, sleeps = use_fake_server(monkeypatch, [FakeResponse(200, {"ok": 1})])
    assert fetch_with_retry("u") == {"ok": 1}
    assert len(calls) == 1
    assert sleeps == []


def test_server_error_is_retried_with_backoff(monkeypatch):
    # 13일차: 5xx는 재시도, 대기 시간은 1, 2, 4초...
    calls, sleeps = use_fake_server(
        monkeypatch,
        [
            FakeResponse(503),
            FakeResponse(503),
            FakeResponse(200, {"ok": 1}),
        ],
    )
    assert fetch_with_retry("u") == {"ok": 1}
    assert len(calls) == 3
    assert sleeps == [1, 2]


def test_rate_limit_is_retried(monkeypatch):
    # 플레이어 조회는 분당 10회 제한. 429는 재시도해야 함
    calls, sleeps = use_fake_server(monkeypatch, [FakeResponse(429), FakeResponse(200)])
    fetch_with_retry("u")
    assert sleeps == [1]


def test_not_found_is_not_retried(monkeypatch):
    # 4xx는 다시 보내도 같은 결과이므로 바로 멈춤
    calls, sleeps = use_fake_server(monkeypatch, [FakeResponse(404)])
    with pytest.raises(ApiError) as excinfo:
        fetch_with_retry("u")
    assert excinfo.value.status_code == 404
    assert len(calls) == 1
    assert sleeps == []


def test_gives_up_after_max_retries(monkeypatch):
    # 마지막 시도 뒤에는 기다리지 않고 바로 포기
    calls, sleeps = use_fake_server(monkeypatch, [FakeResponse(503)] * 4)
    with pytest.raises(RetryExhausted):
        fetch_with_retry("u", max_retries=3)
    assert len(calls) == 4
    assert sleeps == [1, 2, 4]


def test_timeout_is_retried(monkeypatch):
    calls, sleeps = use_fake_server(
        monkeypatch,
        [
            requests.exceptions.Timeout(),
            FakeResponse(200, {"ok": 1}),
        ],
    )
    assert fetch_with_retry("u") == {"ok": 1}
    assert sleeps == [1]


def test_params_and_timeout_are_passed(monkeypatch):
    # 13일차: 요청에는 항상 timeout이 있어야 함
    calls, _ = use_fake_server(monkeypatch, [FakeResponse(200)])
    fetch_with_retry("u", params={"filter[playerNames]": "x"})
    assert calls[0]["params"] == {"filter[playerNames]": "x"}
    assert calls[0]["timeout"] > 0


def test_fetch_player_explains_404(monkeypatch):
    # 28일차: 404는 무엇을 확인해야 하는지 알려주는 메시지로
    monkeypatch.setenv("PUBG_API_KEY", "dummy")
    use_fake_server(monkeypatch, [FakeResponse(404)])
    with pytest.raises(RuntimeError, match="PUBG_PLAYER_NAME"):
        collect.fetch_player("no_such_player")


def test_candidates_404_has_clear_message(monkeypatch):
    monkeypatch.setenv("PUBG_API_KEY", "dummy")
    use_fake_server(monkeypatch, [FakeResponse(404)])
    with pytest.raises(RuntimeError, match="candidates.json"):
        collect.fetch_players_by_ids(["account.a", "account.b"])


def test_candidates_partial_result_is_reported(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("PUBG_API_KEY", "dummy")
    monkeypatch.chdir(tmp_path)
    use_fake_server(monkeypatch, [FakeResponse(200, {"data": [{"id": "account.a"}]})])
    players = collect.fetch_players_by_ids(["account.a", "account.b"])
    assert len(players) == 1
    assert "2명 중 1명" in capsys.readouterr().out
