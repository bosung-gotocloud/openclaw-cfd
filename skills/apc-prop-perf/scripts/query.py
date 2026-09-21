"""APC Propeller CLI 쿼리 인터페이스."""

import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(__file__))
from database import APCDatabase
from interpolator import APCInterpolator


def query_prop(db, diameter, pitch, rpm, speed, interp='nearest'):
    """프로펠러 성능 쿼리."""
    # 먼저 DB에 정확한 프로펠러가 있는지 확인
    props = db.get_all_props()
    exact = props[(props['diameter'] == diameter) & (props['pitch'] == pitch)]

    if not exact.empty:
        prop_df = db.get_propeller_data(diameter, pitch)
        interp_engine = APCInterpolator(prop_df)
        results = interp_engine.query(rpm, speed)
        results['found'] = 'exact'
        results['diameter'] = diameter
        results['pitch'] = pitch
        return results
    else:
        # 교차 보간
        results = APCInterpolator.interpolate_between_props(
            db, diameter, pitch, rpm, speed,
            metrics=['thrust_lbf', 'pwr_hp', 'torque_lbft', 'pe', 'ct', 'cp']
        )
        results['found'] = 'interpolated'
        results['diameter'] = diameter
        results['pitch'] = pitch
        return results


def cmd_query(db_path, diameter, pitch, rpm, speed, json_out=False):
    """CLI 쿼리."""
    db = APCDatabase(str(db_path))

    results = query_prop(db, diameter, pitch, rpm, speed)

    if json_out:
        print(json.dumps(results, indent=2))
    else:
        prop_name = f"{diameter:.1f}x{pitch:.1f}"
        print(f"\n{'='*60}")
        print(f"  APC Propeller Performance Query")
        print(f"{'='*60}")
        print(f"  Propeller:  {prop_name}")
        print(f"  RPM:        {rpm}")
        print(f"  Speed:      {speed:.1f} mph")
        print(f"  Method:     {results.get('found', 'unknown')}")
        print(f"{'='*60}")

        if results.get('confidence', 0) < 1.0 and results.get('found') == 'interpolated':
            print(f"\n  ⚠️  Interpolated (confidence: {results['confidence']:.2%})")

        for label, key, unit in [
            ("Thrust", "thrust_lbf", "lbf"),
            ("Power", "pwr_hp", "hp"),
            ("Torque", "torque_lbft", "in-lbf"),
        ]:
            val = results.get(key)
            if val is not None:
                print(f"  {label:>8}: {val:.4f} {unit}")

        # 추가 metric들
        for label, key in [
            ("Efficiency", "pe"),
            ("Ct", "ct"),
            ("Cp", "cp"),
            ("Thrust (N)", "thrust_n"),
            ("Power (W)", "pwr_w"),
            ("Torque (N-m)", "torque_nm"),
            ("Thr/PWR (g/W)", "thr_pwr"),
            ("Mach (tip)", "mach"),
            ("Reyn (75%)", "reyn"),
            ("FOM", "fom"),
        ]:
            val = results.get(key)
            if val is not None:
                print(f"  {label:>15}: {val:.4f}")

        # J 계산
        n_rps = rpm / 60.0
        D_m = diameter / 39.3701  # inch to meter
        V_ms = speed * 0.44704   # mph to m/s
        j_val = V_ms / (n_rps * D_m) if (n_rps * D_m) > 0 else 0
        print(f"  {'J (advance)':>15}: {j_val:.4f}")
        print()


def cmd_scan(db_path):
    """DB의 모든 프로펠러 스캔."""
    db = APCDatabase(str(db_path))
    props = db.get_all_props()
    print(f"\n{'Diameter':>10} {'Pitch':>8}  {'Count':>6}  {'RPM Range':>15}")
    print("-" * 45)
    for _, row in props.iterrows():
        d, p = row['diameter'], row['pitch']
        df = db.get_propeller_data(d, p)
        rpm_min, rpm_max = df['rpm'].min(), df['rpm'].max()
        print(f"{d:>10.1f} {p:>8.1f}  {len(df):>6}  {rpm_min:.0f}-{rpm_max:.0f}")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='APC Propeller 성능 쿼리')
    parser.add_argument('--db', default='data/apc_prop.db', help='DB 경로')
    parser.add_argument('--diameter', type=float, default=None, help='프로펠러 직경 (inch)')
    parser.add_argument('--pitch', type=float, default=None, help='프로펠러 피치 (inch)')
    parser.add_argument('--rpm', type=float, default=None, help='RPM')
    parser.add_argument('--speed', type=float, default=None, help='속도 (mph)')
    parser.add_argument('--json', action='store_true', help='JSON 출력')
    parser.add_argument('--scan', action='store_true', help='DB에 모든 프로펠러 목록')

    args = parser.parse_args()

    if args.scan:
        cmd_scan(args.db)
    elif args.diameter is not None and args.pitch is not None and args.rpm is not None and args.speed is not None:
        cmd_query(args.db, args.diameter, args.pitch, args.rpm, args.speed, args.json)
    else:
        parser.print_help()
