import json
from pathlib import Path

import pytest

import pipeline
from pipeline import decide_status, parse_args, queue_step

OK_CHECKS = {t: {"file": 1, "db": 1, "ok": True} for t in ["matches", "participants", "kills"]}
BAD_CHECKS = dict(OK_CHECKS, kills={"file": 1, "db": 2, "ok": False})
ONE_FAILURE = [{"match_id": "bad-1", "error": "RuntimeError: x"}]
Q_OK_CHECKS = {"matches": {"ok": True}}
Q_BAD_CHECKS = {"matches": {"ok": False}}
BAD_QUALITY = {"human_null_survival": 2, "bot_with_survival": 0, "kills_null_distance_pct": 3.1}


@pytest.mark.parametrize(
    "failed, checks, expected",
    [
        ([], OK_CHECKS, "ok"),
        (ONE_FAILURE, OK_CHECKS, "partial"),
        ([], BAD_CHECKS, "verify_failed"),
        (ONE_FAILURE, BAD_CHECKS, "verify_failed"),  # 둘 다면 더 심각한 쪽
    ],
)
def test_decide_status(failed, checks, expected):
    assert pipeline.decide_status(failed, checks) == expected


def use_fake_steps(monkeypatch, tmp_path, failed=(), checks=OK_CHECKS, load_error=None):
    """수집, 적재, 검증을 가짜로 바꾸고 임시 폴더에서 실행"""
    monkeypatch.chdir(tmp_path)
    result = ([{"match_id": "ok-1"}], list(failed), [])
    monkeypatch.setattr(pipeline, "run_collect", lambda name, limit: result)
    monkeypatch.setattr(pipeline, "run_reprocess", lambda: result)

    def fake_load():
        if load_error is not None:
            raise load_error
        return {"matches": 1, "participants": 1, "kills": 1}

    monkeypatch.setattr(pipeline, "run_load", fake_load)
    monkeypatch.setattr("pipeline.seed_step", lambda: 0)
    monkeypatch.setattr(
        "pipeline.quality_step",
        lambda: {"human_null_survival": 0, "bot_with_survival": 0, "kills_null_distance_pct": 0.0},
    )
    monkeypatch.setattr(pipeline, "get_conninfo", lambda: "fake")
    monkeypatch.setattr(pipeline, "verify", lambda conninfo: checks)


def last_log():
    with open("logs/pipeline_runs.jsonl", encoding="utf-8") as f:
        return json.loads(f.readlines()[-1])


def test_ok_run_returns_0(monkeypatch, tmp_path):
    use_fake_steps(monkeypatch, tmp_path)
    assert pipeline.main(["somebody"]) == 0
    log = last_log()
    assert log["duration_s"] >= 0
    assert log["status"] == "ok"
    assert log["mode"] == "player"
    assert log["limit"] == 3


def test_failed_match_returns_1_as_partial(monkeypatch, tmp_path):
    # 27일차: 실패가 있으면 검증이 통과해도 partial, 종료 코드 1
    use_fake_steps(monkeypatch, tmp_path, failed=ONE_FAILURE)
    assert pipeline.main(["somebody"]) == 1
    assert last_log()["status"] == "partial"


def test_verify_mismatch_returns_1(monkeypatch, tmp_path):
    # 22일차: 파일과 DB의 행 수가 다르면 verify_failed
    use_fake_steps(monkeypatch, tmp_path, checks=BAD_CHECKS)
    assert pipeline.main(["somebody"]) == 1
    assert last_log()["status"] == "verify_failed"


def test_error_is_logged_and_raised(monkeypatch, tmp_path):
    # 22일차: 예외가 나도 로그는 남고, 예외는 숨기지 않음
    use_fake_steps(monkeypatch, tmp_path, load_error=RuntimeError("DB 접속 실패"))
    with pytest.raises(RuntimeError):
        pipeline.main(["somebody"])
    log = last_log()
    assert log["status"] == "error"
    assert "DB 접속 실패" in log["error"]
    assert "collected" in log  # 수집은 끝났고
    assert "loaded" not in log  # 적재에서 멈춤


def test_reprocess_does_not_record_limit(monkeypatch, tmp_path):
    # 27일차: limit을 쓰지 않는 실행에는 limit을 기록하지 않음
    use_fake_steps(monkeypatch, tmp_path)
    assert pipeline.main(["--reprocess"]) == 0
    log = last_log()
    assert log["mode"] == "reprocess"
    assert "limit" not in log


def test_missing_arguments_exit_before_logging(monkeypatch, tmp_path):
    # 28일차: 파이프라인이 시작되기 전의 실패는 실행 로그에 남지 않음
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as excinfo:
        pipeline.main([])
    assert excinfo.value.code == 2
    assert not Path("logs/pipeline_runs.jsonl").exists()


def test_queue_budget_defaults_to_zero():
    assert parse_args(["someone"]).queue_budget == 0


def test_queue_step_does_nothing_when_budget_zero():
    record = {}
    assert queue_step(0, record) == ([], [], [])
    assert "queue" not in record


def test_quality_problem_sets_status():
    assert decide_status([], Q_OK_CHECKS, BAD_QUALITY) == "quality_failed"  # (D)


def test_verify_failure_wins_over_quality():
    assert decide_status([], Q_BAD_CHECKS, BAD_QUALITY) == "verify_failed"


def test_both_quality_problems_set_status():
    quality = {"human_null_survival": 1, "bot_with_survival": 1, "kills_null_distance_pct": 0.0}
    assert decide_status([], Q_OK_CHECKS, quality) == "quality_failed"


def test_queue_match_limit_defaults_to_three():
    assert parse_args(["someone"]).queue_match_limit == 3
