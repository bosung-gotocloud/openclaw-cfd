"""APC Prop 전체 파이프라인: 다운로드 → 파싱 → DB 저장."""

import os
import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from parser import parse_apc_file, parse_per2_summary
from database import APCDatabase
from downloader import download_all


def parse_all_files(raw_dir, db):
    """raw_dir의 모든 .dat 파일을 파싱하여 DB에 저장."""
    raw_path = Path(raw_dir)
    dat_files = sorted(raw_path.glob('*.dat'))

    if not dat_files:
        print(f"[main] No .dat files found in {raw_dir}")
        return 0

    count = 0
    errors = []
    per2_count = 0

    for dat_file in dat_files:
        try:
            # PER2 요약 파일 구분 (PER2_MAXPE.DAT, PER2_N100.DAT 등)
            if dat_file.name.startswith('PER2_'):
                try:
                    per2_data = parse_per2_summary(str(dat_file))
                    per2_count += len(per2_data)
                    print(f"  PER2: {dat_file.name} -> {len(per2_data)} props (unparsed)")
                except Exception as e:
                    print(f"  PER2 parse error: {dat_file.name}: {e}")
                continue

            meta, df = parse_apc_file(str(dat_file))
            if meta['diameter'] is None or meta['pitch'] is None:
                print(f"  SKIP (no meta): {dat_file.name}")
                errors.append(dat_file.name)
                continue
            if df.empty:
                print(f"  SKIP (empty): {dat_file.name}")
                errors.append(dat_file.name)
                continue

            pid = db.save_propeller(meta, df)
            print(f"  OK: {dat_file.name} -> D={meta['diameter']}, P={meta['pitch']}, "
                  f"rows={len(df)}, prop_id={pid}, "
                  f"ver={meta.get('version', 'N/A')}, sim={meta.get('sim_date', 'N/A')}")
            count += 1
        except Exception as e:
            print(f"  ERROR: {dat_file.name}: {e}")
            errors.append(dat_file.name)

    print(f"[main] Parsed {count} PER3 files, {per2_count} PER2 props (unparsed), {len(errors)} errors")
    return count


def get_stats(db):
    """DB 통계 출력."""
    stats = db.get_stats()
    print(f"\n[main] DB: {db.db_path}")
    print(f"[main] Total propellers: {stats['propellers']}")
    print(f"[main] Total data points: {stats['data_points']:,}")
    print(f"[main] Diameter: {stats['diameter_range'][0]:.1f} - {stats['diameter_range'][1]:.1f} inch")
    print(f"[main] Pitch: {stats['pitch_range'][0]:.1f} - {stats['pitch_range'][1]:.1f} inch")
    print(f"[main] RPM: {stats['rpm_range'][0]:.0f} - {stats['rpm_range'][1]:.0f}")
    print(f"[main] Velocity: {stats['velocity_range'][0]:.1f} - {stats['velocity_range'][1]:.1f} mph")
    return stats


def cmd_update(db_path, raw_dir=None, skip_download=False):
    """전체 파이프라인 업데이트."""
    base = Path(__file__).resolve().parent.parent

    if not raw_dir:
        raw_dir = base / 'data' / 'raw'

    # 1. 다운로드
    if not skip_download:
        print("[main] Step 1: Downloading data...")
        download_all()
    else:
        print("[main] Step 1: Skipping download")

    # 2. DB 초기화
    db = APCDatabase(str(db_path))
    print(f"[main] Step 2: DB initialized at {db_path}")

    # 3. 파싱 + 저장
    print("[main] Step 3: Parsing .dat files...")
    count = parse_all_files(raw_dir, db)

    # 4. 상태 확인
    get_stats(db)

    # 5. 요약 JSON
    summary = {
        'updated_at': str(Path(__file__).resolve()),
        'db_path': str(db_path),
        'raw_dir': str(raw_dir),
        'props_count': count,
    }
    print(f"\n[main] Summary: {json.dumps(summary, indent=2)}")
    return summary


def cmd_status(db_path):
    """DB 상태만 확인."""
    db = APCDatabase(str(db_path))
    get_stats(db)
    return db.get_stats()


def cmd_list(db_path):
    """DB에 저장된 프로펠러 목록."""
    db = APCDatabase(str(db_path))
    props = db.get_all_props()
    print(f"\n{'ID':>3} {'Diameter':>10} {'Pitch':>8} {'Version':>12} {'Sim Date':>10} {'Filename':<30}")
    print("-" * 75)
    for _, row in props.iterrows():
        print(f"{row['id']:>3} {row['diameter']:>10.1f} {row['pitch']:>8.1f} "
              f"{str(row['version'] or 'N/A'):>12} {str(row['sim_date'] or 'N/A'):>10} "
              f"{row['filename']:<30}")


def cmd_export_json(db_path):
    """DB를 JSON으로 내보내기."""
    db = APCDatabase(str(db_path))
    print(db.to_json())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='APC Propeller 전체 파이프라인')
    sub = parser.add_subparsers(dest='command')

    # update
    p_upd = sub.add_parser('update', help='데이터 다운로드 + 파싱 + DB 갱신')
    p_upd.add_argument('--db', default='data/apc_prop.db', help='DB 경로')
    p_upd.add_argument('--raw-dir', default=None, help='raw .dat 파일 디렉토리')
    p_upd.add_argument('--skip-download', action='store_true', help='다운로드 건너뛰기')

    # status
    p_stat = sub.add_parser('status', help='DB 상태 확인')
    p_stat.add_argument('--db', default='data/apc_prop.db', help='DB 경로')

    # list
    p_list = sub.add_parser('list', help='저장된 프로펠러 목록')
    p_list.add_argument('--db', default='data/apc_prop.db', help='DB 경로')

    # export-json
    p_exp = sub.add_parser('export-json', help='DB를 JSON으로 내보내기')
    p_exp.add_argument('--db', default='data/apc_prop.db', help='DB 경로')

    args = parser.parse_args()

    if args.command == 'update':
        cmd_update(args.db, args.raw_dir, args.skip_download)
    elif args.command == 'status':
        cmd_status(args.db)
    elif args.command == 'list':
        cmd_list(args.db)
    elif args.command == 'export-json':
        cmd_export_json(args.db)
    else:
        parser.print_help()
