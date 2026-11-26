# 기존 telemetry .json을 .json.gz로 옮김 (50일차, 한 번만 실행)
import sys
from pathlib import Path

from collect import read_json, save_json_atomic


def migrate(raw="raw"):
    moved = 0
    for src in sorted(Path(raw).glob("telemetry_*.json")):
        dst = src.with_name(src.name + ".gz")
        data = read_json(src)
        save_json_atomic(dst, data, compress=True)
        if read_json(dst) != data:
            raise RuntimeError(f"압축본이 원본과 다릅니다: {src.name}")
        src.unlink()
        moved += 1
    return moved


if __name__ == "__main__":
    print(f"옮긴 파일: {migrate()}개")
    sys.exit(0)
