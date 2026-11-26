from collect import read_json, save_json
from migrate_telemetry import migrate


def test_migrate_converts_and_removes_original(tmp_path):
    data = [{"_T": "LogMatchStart"}]
    save_json(tmp_path / "telemetry_m1.json", data)
    save_json(tmp_path / "match_m1.json", {"id": "m1"})
    assert migrate(tmp_path) == 1
    assert sorted(p.name for p in tmp_path.iterdir()) == ["match_m1.json", "telemetry_m1.json.gz"]  # (F)
    assert read_json(tmp_path / "telemetry_m1.json.gz") == data


def test_migrate_twice_does_nothing(tmp_path):
    save_json(tmp_path / "telemetry_m1.json", [1])
    migrate(tmp_path)
    assert migrate(tmp_path) == 0  # (G)
