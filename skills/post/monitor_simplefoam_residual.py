#!/usr/bin/env python3
"""
Real-time simpleFoam residual monitoring with Gnuplot interactive window.

Monitors log.simpleFoam and regenerates residual PNG graphs at specified interval.
Also generates a Gnuplot script that can be run interactively for x11 display.

Usage:
    python3 monitor_simplefoam_residual.py <case_dir> [--interval 10]
    
Examples:
    python3 monitor_simplefoam_residual.py /path/to/case
    python3 monitor_simplefoam_residual.py /path/to/case --interval 5
    python3 monitor_simplefoam_residual.py . --interval 15

Output (in case_dir):
    - residual_velocity.png   : velocity components
    - residual_pressure.png   : pressure, omega, k
    - residual_all.png         : combined 2-panel
    - residual_velocity.gnuplot
    - residual_pressure.gnuplot
    - residual_all.gnuplot
    - monitor_gnuplot.sh       : auto-run script for x11 display

Note:
    When gnuplot interactive display (x11) is available, it will show live graph
    that auto-updates via replot.
    Press Ctrl+C to stop monitoring.
"""
import sys
import os
import re
import time
import subprocess

def parse_residuals(log_file):
    """Parse log.simpleFoam and extract residuals per time step."""
    time_data = {}
    current_time = None
    
    try:
        with open(log_file, 'r') as f:
            lines = f.readlines()
    except Exception as e:
        return None, str(e)
    
    for line in lines:
        t_match = re.search(r'Time = (\d+)', line)
        if t_match:
            current_time = int(t_match.group(1))
            if current_time not in time_data:
                time_data[current_time] = {}
            continue
        
        if current_time is None:
            continue
        
        residual = None
        f_match = re.search(r'Final residual = ([\d.eE+-]+)', line)
        if f_match:
            residual = float(f_match.group(1))
        
        if residual is None:
            continue
        
        field = None
        if 'Ux' in line and 'Solving for' in line:
            field = 'Ux'
        elif 'Uy' in line and 'Solving for' in line:
            field = 'Uy'
        elif 'Uz' in line and 'Solving for' in line:
            field = 'Uz'
        elif 'p' in line and 'GAMG' in line:
            field = 'p'
        elif 'omega' in line and 'Solving for' in line:
            field = 'omega'
        elif 'k' in line and 'Solving for' in line:
            field = 'k'
        
        if field:
            time_data[current_time][field] = residual
    
    return time_data, None

def write_gnuplot_files(output_dir):
    """Write Gnuplot scripts for all plot types."""
    vel_data_file = os.path.join(output_dir, '_residual_velocity.dat')
    pres_data_file = os.path.join(output_dir, '_residual_pressure.dat')
    
    # Write data files
    with open(vel_data_file, 'w') as f:
        f.write("# time step  Ux         Uy         Uz\n")
        for i, t in enumerate(sorted_times):
            d = time_data[t]
            ux = d.get('Ux', 0)
            uy = d.get('Uy', 0)
            uz = d.get('Uz', 0)
            f.write(f"{i} {ux:.6e} {uy:.6e} {uz:.6e}\n")
    
    with open(pres_data_file, 'w') as f:
        f.write("# time step  p            omega      k\n")
        for i, t in enumerate(sorted_times):
            d = time_data[t]
            p_val = d.get('p', 0)
            om = d.get('omega', 0)
            k_val = d.get('k', 0)
            f.write(f"{i} {p_val:.6e} {om:.6e} {k_val:.6e}\n")
    
    # Write Gnuplot scripts
    scripts = {}
    
    # Velocity
    lines = [
        'set datafile separator " "',
        'set terminal pngcairo size 1200, 800 font "Arial,12"',
        f'set output "{os.path.join(output_dir, "residual_velocity.png")}"',
        'set logscale y',
        'set grid ytics',
        'set xlabel "Time Step" font ",14"',
        'set ylabel "Final Residual" font ",14"',
        'set title "Velocity Components - Final Residual" font ",16"',
        'set key top right',
        'set key font ",12"',
        'set key outside',
        'set yrange [1e-12:1e0]',
        '',
        f'plot "{vel_data_file}" using 0:2 with lines title "Ux" lc rgb "#1f77b4" lw 2, \\',
        f'     "" using 0:3 with lines title "Uy" lc rgb "#d62728" lw 2, \\',
        f'     "" using 0:4 with lines title "Uz" lc rgb "#2ca02a" lw 2',
    ]
    scripts['velocity'] = '\n'.join(lines)
    
    # Pressure
    lines = [
        'set datafile separator " "',
        'set terminal pngcairo size 1200, 800 font "Arial,12"',
        f'set output "{os.path.join(output_dir, "residual_pressure.png")}"',
        'set logscale y',
        'set grid ytics',
        'set xlabel "Time Step" font ",14"',
        'set ylabel "Final Residual" font ",14"',
        'set title "Pressure, omega, k - Final Residual" font ",16"',
        'set key top right',
        'set key font ",12"',
        'set key outside',
        'set yrange [1e-12:1e0]',
        '',
        f'plot "{pres_data_file}" using 0:2 with lines title "p (GAMG)" lc rgb "#9467bd" lw 2, \\',
        f'     "" using 0:3 with lines title "omega" lc rgb "#8c564b" lw 2, \\',
        f'     "" using 0:4 with lines title "k" lc rgb "#e377c2" lw 2, \\',
        f'     1e-5 with lines title "convergence (1e-5)" lc rgb "black" lw 1 dt 2',
    ]
    scripts['pressure'] = '\n'.join(lines)
    
    # Combined
    lines = [
        'set datafile separator " "',
        'set terminal pngcairo size 1200, 1000 font "Arial,12"',
        f'set output "{os.path.join(output_dir, "residual_all.png")}"',
        'set logscale y',
        'set grid ytics',
        'set key top right',
        'set key font ",12"',
        'set key outside',
        'set yrange [1e-12:1e0]',
        'set multiplot layout 2,1',
        '',
        '# Panel 1: Velocity',
        'set xlabel "Time Step" font ",14"',
        'set ylabel "Final Residual" font ",14"',
        'set title "Velocity Components" font ",16"',
        f'plot "{vel_data_file}" using 0:2 with lines title "Ux" lc rgb "#1f77b4" lw 2, \\',
        f'     "" using 0:3 with lines title "Uy" lc rgb "#d62728" lw 2, \\',
        f'     "" using 0:4 with lines title "Uz" lc rgb "#2ca02a" lw 2',
        '',
        '# Panel 2: Pressure, omega, k',
        'set xlabel "Time Step" font ",14"',
        'set ylabel "Final Residual" font ",14"',
        'set title "Pressure, omega, k" font ",16"',
        f'plot "{pres_data_file}" using 0:2 with lines title "p" lc rgb "#9467bd" lw 2, \\',
        f'     "" using 0:3 with lines title "omega" lc rgb "#8c564b" lw 2, \\',
        f'     "" using 0:4 with lines title "k" lc rgb "#e377c2" lw 2, \\',
        f'     1e-5 with lines title "convergence" lc rgb "black" lw 1 dt 2',
        '',
        'unset multiplot',
    ]
    scripts['combined'] = '\n'.join(lines)
    
    for name, content in scripts.items():
        path = os.path.join(output_dir, f'residual_{name}.gnuplot')
        with open(path, 'w') as f:
            f.write(content + '\n')
    
    return scripts

def run_gnuplot(output_dir):
    """Execute all Gnuplot scripts and return generated PNG paths."""
    results = {}
    for name in ['velocity', 'pressure', 'combined']:
        script_path = os.path.join(output_dir, f'residual_{name}.gnuplot')
        png_file = os.path.join(output_dir, f'residual_{name}.png')
        try:
            result = subprocess.run(
                ['gnuplot', script_path],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and os.path.exists(png_file):
                fsize = os.path.getsize(png_file)
                results[name] = (png_file, fsize)
                print(f"  ✅ {png_file} ({fsize:,} bytes)")
            else:
                results[name] = None
        except Exception as e:
            print(f"  ❌ Gnuplot error ({name}): {e}")
            results[name] = None
    return results

def summarize(time_data, sorted_times):
    """Print residual summary."""
    print("\n=== Residual Summary ===")
    for field in ['Ux', 'Uy', 'Uz', 'p', 'omega', 'k']:
        vals = []
        for t in sorted_times:
            v = time_data[t].get(field)
            if v:
                vals.append(v)
        if vals:
            print(f"  {field:>5}: last={vals[-1]:.2e}, min={min(vals):.2e}, max={max(vals):.2e}")

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Monitor simpleFoam residuals in real-time')
    parser.add_argument('case_dir', help='Case directory containing log.simpleFoam')
    parser.add_argument('--interval', type=int, default=10, help='Update interval in seconds (default: 10)')
    args = parser.parse_args()
    
    case_dir = os.path.abspath(args.case_dir)
    log_file = os.path.join(case_dir, 'log.simpleFoam')
    
    if not os.path.exists(log_file):
        print(f"Error: {log_file} not found")
        sys.exit(1)
    
    print(f"🔍 Monitoring: {log_file}")
    print(f"📁 Case dir:  {case_dir}")
    print(f"⏱ Update:     every {args.interval}s")
    print(f"🎯 Ctrl+C to stop")
    print()
    
    prev_count = 0
    
    # Write monitor_gnuplot.sh for interactive x11 use
    sh_path = os.path.join(case_dir, 'monitor_gnuplot.sh')
    with open(sh_path, 'w') as f:
        f.write(f"#!/bin/bash\n")
        f.write(f"# Auto-generate and monitor gnuplot scripts\n")
        f.write(f"cd '{case_dir}'\n")
        f.write(f"while true; do\n")
        f.write(f"  python3 monitor_simplefoam_residual.py . --once\n")
        f.write(f"  gnuplot residual_all.gnuplot  # generates PNG\n")
        f.write(f"  sleep {args.interval}\n")
        f.write(f"done\n")
    os.chmod(sh_path, 0o755)
    
    try:
        while True:
            time_data, err = parse_residuals(log_file)
            if err:
                print(f"⚠️  Parse error: {err}")
                time.sleep(args.interval)
                continue
            
            sorted_times = sorted(time_data.keys())
            count = len(sorted_times)
            
            if count > prev_count:
                new_steps = count - prev_count
                print(f"\n📈 [{time.ctime()}] +{new_steps} steps (total: {count})")
                prev_count = count
            
            if count == 0:
                time.sleep(args.interval)
                continue
            
            # Write Gnuplot scripts and generate graphs
            scripts = write_gnuplot_files(case_dir)
            results = run_gnuplot(case_dir)
            
            # Show latest residual
            if sorted_times:
                latest = sorted_times[-1]
                d = time_data[latest]
                print(f"\n📊 Latest step {latest}:", end=" ")
                vals = []
                for field in ['Ux', 'Uy', 'Uz', 'p', 'omega', 'k']:
                    v = d.get(field, 0)
                    if v:
                        vals.append(f"{field}={v:.2e}")
                print(", ".join(vals) if vals else "(no data)")
            
            summarize(time_data, sorted_times)
            
            time.sleep(args.interval)
            
    except KeyboardInterrupt:
        print(f"\n\n⏹ Stopped. Final graphs generated.")
        sys.exit(0)

if __name__ == '__main__':
    main()
