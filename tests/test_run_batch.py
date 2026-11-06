import collect
from collect import SkippedMatch, run_batch


def fake_process_match(match_id):
    if match_id.startswith("skip"):
        raise SkippedMatch("지원하지 않는 모드: tdm")
    if match_id.startswith("bad"):
        raise RuntimeError("일부러 만든 실패")
    return {"match_id": match_id}


def test_results_are_sorted_into_the_right_lists(monkeypatch, tmp_path):
    monkeypatch.setattr(collect, "process_match", fake_process_match)
    monkeypatch.chdir(tmp_path)

    succeeded, failed, skipped = run_batch(["ok-1", "skip-1", "bad-1", "ok-2"])

    assert [s["match_id"] for s in succeeded] == ["ok-1", "ok-2"]
    assert [f["match_id"] for f in failed] == ["bad-1"]
    assert [s["match_id"] for s in skipped] == ["skip-1"]

    # 26일차: failed와 skipped가 뒤바뀌면 항목의 키가 달라짐
    assert "error" in failed[0] and "RuntimeError" in failed[0]["error"]
    assert "reason" in skipped[0] and "tdm" in skipped[0]["reason"]
