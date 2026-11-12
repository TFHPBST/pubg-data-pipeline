import collect


def test_second_call_uses_cache(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    calls = []

    def fake_fetch(url, headers=None):
        calls.append(url)
        return {"n": 1}

    monkeypatch.setattr(collect, "fetch_with_retry", fake_fetch)

    first = collect.load_or_fetch("raw/x.json", "u")
    second = collect.load_or_fetch("raw/x.json", "u")

    assert first == {"n": 1}
    assert second == {"n": 1}
    assert len(calls) == 1
