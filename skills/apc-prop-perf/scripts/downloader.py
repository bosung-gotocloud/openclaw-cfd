"""APC Propeller 웹사이트에서 .dat 성능 데이터 다운로드."""

import os
import sys
import time
import urllib.request
import urllib.error
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

# APC 공식 ZIP 아카이브 URL
APC_ZIP_URL = "https://www.apcprop.com/wp-content/uploads/2026/02/PERFILES_WEB-202602.zipx"


def download_zip_to_zipx(url, dest_path, retries=3, timeout=300):
    """APC 공식 ZIP 아카이브 다운로드."""
    dest = Path(dest_path)
    if dest.exists() and dest.stat().st_size > 0:
        print(f"[downloader] Already exists: {dest} ({dest.stat().st_size} bytes)")
        return str(dest)

    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            with urllib.request.urlopen(req, timeout=timeout) as response:
                data = response.read()
            
            dest.write_bytes(data)
            print(f"[downloader] Downloaded ZIP: {dest} ({len(data)} bytes)")
            return str(dest)
        except (urllib.error.URLError, Exception) as e:
            print(f"[downloader] Retry {attempt+1}/{retries}: {e}")
            time.sleep(3 * (attempt + 1))
    
    return None


def extract_zip(zip_path, out_dir='data/raw/'):
    """ZIP 아카이브에서 .dat 파일 추출."""
    zip_file = Path(zip_path)
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    if not zip_file.exists():
        print(f"[downloader] ZIP not found: {zip_path}")
        return 0

    dat_count = 0
    error_count = 0
    with zipfile.ZipFile(zip_file, 'r') as zf:
        for member in zf.namelist():
            if member.lower().endswith('.dat'):
                try:
                    dest = out_path / os.path.basename(member)
                    # 이미 존재하고 더 최근이면 skip
                    if dest.exists():
                        if dest.stat().st_mtime >= zip_file.stat().st_mtime:
                            dat_count += 1
                            continue
                    zf.extract(member, str(out_path))
                    dat_count += 1
                except Exception as e:
                    error_count += 1
                    print(f"  error extracting {member}: {e}")

    # 중복 제거: 서브폴더에서 flat하게 정리
    for subdir in out_path.rglob('*'):
        if subdir.is_dir() and subdir != out_path:
            for f in subdir.glob('*.dat'):
                dest = out_path / os.path.basename(f)
                if not dest.exists():
                    f.rename(dest)
                else:
                    f.unlink()
            # 빈 디렉토리 제거
            if not any(subdir.iterdir()):
                subdir.rmdir()

    print(f"[downloader] Extracted {dat_count} .dat files ({error_count} errors)")
    return dat_count


def download_all():
    """전체 다운로드: ZIP 다운로드 → 추출 → .dat 정리."""
    base = Path(__file__).resolve().parent.parent
    zip_path = base / 'data' / 'PERFILES_WEB-202602.zipx'
    raw_dir = base / 'data' / 'raw'

    print("[downloader] APC Propeller 데이터 다운로드 시작")

    # 단계 1: ZIP 다운로드
    print("[downloader] Step 1: ZIP 아카이브 다운로드")
    downloaded_zip = download_zip_to_zipx(APC_ZIP_URL, str(zip_path))
    
    if not downloaded_zip:
        print("[downloader] ZIP download failed. Using local backup if available.")
        # 로컬 백업 시도
        backup_zip = base / 'data' / 'perfiles.zipx'
        if backup_zip.exists():
            downloaded_zip = str(backup_zip)
            print(f"[downloader] Using local backup: {backup_zip}")

    # 단계 2: ZIP 추출
    if downloaded_zip:
        print("[downloader] Step 2: ZIP 추출")
        count = extract_zip(downloaded_zip, str(raw_dir))
    else:
        count = 0

    # 단계 3: 결과 요약
    total_dat = len(list(raw_dir.glob('*.dat')))
    print(f"[downloader] 완료: {count} extracted, {total_dat} total .dat in {raw_dir}")
    return total_dat


if __name__ == "__main__":
    download_all()
