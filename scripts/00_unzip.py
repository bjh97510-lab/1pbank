# -*- coding: utf-8 -*-
"""
0단계: 출판사 자료 ZIP 을 source/ 폴더로 풀어줍니다.
한글 파일명이 깨지지 않도록 cp437 -> cp949 재해석을 시도합니다.

사용법:
  python scripts/00_unzip.py                # 프로젝트 루트의 *.zip 모두
  python scripts/00_unzip.py a.zip b.zip    # 지정 파일만
"""
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "source"


def fix_name(name: str) -> str:
    # zip 스펙상 utf-8 플래그가 없으면 cp437 로 해석되어 한글이 깨짐 -> cp949 로 복원
    try:
        return name.encode("cp437").decode("cp949")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name


def extract(zip_path: Path):
    OUT.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = fix_name(info.filename) if not (info.flag_bits & 0x800) else info.filename
            target = OUT / Path(name).name          # 하위 폴더는 평탄화
            if target.exists():
                print(f"  skip (exists): {target.name}")
                continue
            with zf.open(info) as src, open(target, "wb") as dst:
                dst.write(src.read())
            print(f"  -> {target.name}")


def main():
    zips = [Path(a) for a in sys.argv[1:]] or sorted(ROOT.glob("*.zip"))
    if not zips:
        print("ZIP 파일이 없습니다.")
        return
    for z in zips:
        print(f"[unzip] {z.name}")
        extract(z)
    print(f"\n완료. HWP 파일 위치: {OUT}")


if __name__ == "__main__":
    main()
