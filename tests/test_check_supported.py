import pytest

from collect import SkippedMatch, check_supported


def match(game_mode, match_type="official"):
    attrs = {"gameMode": game_mode}
    if match_type is not None:
        attrs["matchType"] = match_type
    return {"data": {"attributes": attrs}}


@pytest.mark.parametrize("mode", ["solo", "solo-fpp", "duo", "duo-fpp", "squad", "squad-fpp"])
def test_battle_royale_official_is_supported(mode):
    check_supported(match(mode))  # 예외가 나지 않으면 통과


@pytest.mark.parametrize("mode", ["tdm", "zulu-fpp", "normal-squad", "clansolo", "esports-squad", "normal-solo-fpp"])
def test_unsupported_mode_is_skipped(mode):
    with pytest.raises(SkippedMatch, match=mode):
        check_supported(match(mode))


@pytest.mark.parametrize("match_type", ["trainingroom", "airoyale", "custom", None])
def test_unsupported_match_type_is_skipped(match_type):
    # 27일차 훈련장, 28일차 클래식 모드: 모드는 squad라도 공식 매치가 아니면 제외
    with pytest.raises(SkippedMatch):
        check_supported(match("squad", match_type))
