import pytest

from collect import read_json, save_json_atomic


def test_gz_roundtrip(tmp_path):
    path = tmp_path / "t.json.gz"
    data = [{"_T": "LogPlayerKillV2", "n": 1}]
    save_json_atomic(path, data, compress=True)
    assert read_json(path) == data


def test_gz_file_is_really_compressed(tmp_path):
    path = tmp_path / "t.json.gz"
    save_json_atomic(path, {"a": 1}, compress=True)
    assert path.read_bytes()[:2] == b"\x1f\x8b"  # gzip 파일은 항상 이 2바이트로 시작


def test_no_tmp_left_after_success(tmp_path):
    path = tmp_path / "t.json"
    save_json_atomic(path, {"a": 1})
    assert [p.name for p in tmp_path.iterdir()] == ["t.json"]  # (C)


def test_failed_write_keeps_old_file(tmp_path):
    path = tmp_path / "t.json"
    save_json_atomic(path, {"v": "old"})
    with pytest.raises(TypeError):
        save_json_atomic(path, {"v": object()})  # object()는 JSON으로 바꿀 수 없어 쓰는 도중 실패
    assert read_json(path) == {"v": "old"}  # (D)
    assert [p.name for p in tmp_path.iterdir()] == ["t.json"]
