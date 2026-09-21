#!/usr/bin/env python3
"""
Parse OpenFOAM simpleFoam log.residual and generate Gnuplot scripts.

Usage:
    python3 residual_gnuplot.py <log_file> [--plot-type all|velocity|pressure]
    
Default log_file:
    ./log.simpleFoam (in the case directory)

Output:
    - residual_velocity.gnuplot   : velocity components (Ux, Uy, Uz)
    - residual_pressure.gnuplot   : pressure, omega, k
    - residual_velocity.png         : velocity plot (semilogy)
    - residual_pressure.png         : pressure plot (semilogy)
    - residual_all.png              : combined velocity + pressure (2x1)
"""
import sys
import os
import re

def parse_residuals(log_file):
    """Parse log.simpleFoam and extract residuals per time step."""
    time_data = {}
    current_time = None
    
    with open(log_file, 'r') as f:
        lines = f.readlines()
    
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
    
    return time_data

def write_gnuplot_velocity(output_dir, sorted_times, data):
    """Write Gnuplot script for velocity components."""
    lines = []
    data_file = os.path.join(output_dir, '_residual_velocity.dat')
    lines.append('set datafile separator " "')
    lines.append('')
    lines.append('set terminal pngcairo size 1200, 800 font "Arial,12"')
    lines.append(f'set output "{os.path.join(output_dir, "residual_velocity.png")}"')
    lines.append('')
    lines.append('set logscale y')
    lines.append('set grid ytics')
    lines.append('set xlabel "Time Step" font ",14"')
    lines.append('set ylabel "Final Residual" font ",14"')
    lines.append('set title "Velocity Components - Final Residual" font ",16"')
    lines.append('set key top right')
    lines.append('set key font ",12"')
    lines.append('set key outside')
    lines.append('set yrange [1e-12:1e0]')
    lines.append('')
    lines.append(f'plot "{data_file}" using 0:2 with lines title "Ux" lc rgb "#1f77b4" lw 2, \\')
    lines.append(f'     "" using 0:3 with lines title "Uy" lc rgb "#d62728" lw 2, \\')
    lines.append(f'     "" using 0:4 with lines title "Uz" lc rgb "#2ca02a" lw 2')
    
    script_path = os.path.join(output_dir, 'residual_velocity.gnuplot')
    with open(script_path, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    return script_path

def write_gnuplot_pressure(output_dir, sorted_times, data):
    """Write Gnuplot script for pressure, omega, k."""
    lines = []
    data_file = os.path.join(output_dir, '_residual_pressure.dat')
    lines.append('set datafile separator " "')
    lines.append('')
    lines.append('set terminal pngcairo size 1200, 800 font "Arial,12"')
    lines.append(f'set output "{os.path.join(output_dir, "residual_pressure.png")}"')
    lines.append('')
    lines.append('set logscale y')
    lines.append('set grid ytics')
    lines.append('set xlabel "Time Step" font ",14"')
    lines.append('set ylabel "Final Residual" font ",14"')
    lines.append('set title "Pressure, omega, k - Final Residual" font ",16"')
    lines.append('set key top right')
    lines.append('set key font ",12"')
    lines.append('set key outside')
    lines.append('set yrange [1e-12:1e0]')
    lines.append('')
    lines.append(f'plot "{data_file}" using 0:2 with lines title "p (GAMG)" lc rgb "#9467bd" lw 2, \\')
    lines.append(f'     "" using 0:3 with lines title "omega" lc rgb "#8c564b" lw 2, \\')
    lines.append(f'     "" using 0:4 with lines title "k" lc rgb "#e377c2" lw 2, \\')
    lines.append(f'     1e-5 with lines title "convergence (1e-5)" lc rgb "black" lw 1 dt 2')
    
    script_path = os.path.join(output_dir, 'residual_pressure.gnuplot')
    with open(script_path, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    return script_path

def write_gnuplot_combined(output_dir, sorted_times, data):
    """Write Gnuplot script for combined velocity + pressure (2 panels)."""
    lines = []
    lines.append('set datafile separator " "')
    lines.append('')
    lines.append('set terminal pngcairo size 1200, 1000 font "Arial,12"')
    lines.append(f'set output "{os.path.join(output_dir, "residual_all.png")}"')
    lines.append('')
    lines.append('set logscale y')
    lines.append('set grid ytics')
    lines.append('set key top right')
    lines.append('set key font ",12"')
    lines.append('set key outside')
    lines.append('set yrange [1e-12:1e0]')
    lines.append('')
    lines.append('set multiplot layout 2,1')
    lines.append('')
    lines.append('# Panel 1: Velocity')
    lines.append('set xlabel "Time Step" font ",14"')
    lines.append('set ylabel "Final Residual" font ",14"')
    lines.append('set title "Velocity Components" font ",16"')
    lines.append(f'plot "_residual_velocity.dat" using 0:2 with lines title "Ux" lc rgb "#1f77b4" lw 2, \\')
    lines.append(f'     "" using 0:3 with lines title "Uy" lc rgb "#d62728" lw 2, \\')
    lines.append(f'     "" using 0:4 with lines title "Uz" lc rgb "#2ca02a" lw 2')
    lines.append('')
    lines.append('# Panel 2: Pressure, omega, k')
    lines.append('set xlabel "Time Step" font ",14"')
    lines.append('set ylabel "Final Residual" font ",14"')
    lines.append('set title "Pressure, omega, k" font ",16"')
    lines.append(f'plot "_residual_pressure.dat" using 0:2 with lines title "p" lc rgb "#9467bd" lw 2, \\')
    lines.append(f'     "" using 0:3 with lines title "omega" lc rgb "#8c564b" lw 2, \\')
    lines.append(f'     "" using 0:4 with lines title "k" lc rgb "#e377c2" lw 2, \\')
    lines.append(f'     1e-5 with lines title "convergence" lc rgb "black" lw 1 dt 2')
    lines.append('')
    lines.append('unset multiplot')
    
    script_path = os.path.join(output_dir, 'residual_all.gnuplot')
    with open(script_path, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    return script_path

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 residual_gnuplot.py <log_file> [--plot-type all|velocity|pressure]")
        sys.exit(1)
    
    log_file = sys.argv[1]
    plot_type = sys.argv[2] if len(sys.argv) > 2 else 'all'
    
    if not os.path.exists(log_file):
        print(f"Error: {log_file} not found")
        sys.exit(1)
    
    # Parse
    time_data = parse_residuals(log_file)
    sorted_times = sorted(time_data.keys())
    
    if not sorted_times:
        print("No residual data found in log file")
        sys.exit(1)
    
    print(f"Parsed {len(sorted_times)} time steps")
    fields = set()
    for t in sorted_times:
        fields.update(time_data[t].keys())
    print(f"Fields: {sorted(fields)}")
    
    # Output directory = same as log file dir
    output_dir = os.path.dirname(log_file) or '.'
    output_dir = os.path.abspath(output_dir)
    
    # Write data files
    vel_data_file = os.path.join(output_dir, '_residual_velocity.dat')
    pres_data_file = os.path.join(output_dir, '_residual_pressure.dat')
    
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
    
    scripts = {}
    
    if plot_type in ('all', 'velocity'):
        scripts['velocity'] = write_gnuplot_velocity(output_dir, sorted_times, time_data)
    
    if plot_type in ('all', 'pressure'):
        scripts['pressure'] = write_gnuplot_pressure(output_dir, sorted_times, time_data)
    
    if plot_type in ('all',):
        scripts['combined'] = write_gnuplot_combined(output_dir, sorted_times, time_data)
    
    # Execute gnuplot
    import subprocess
    results = {}
    for name, script_path in scripts.items():
        print(f"\nRunning Gnuplot: {script_path}")
        png_file = script_path.replace('.gnuplot', '.png')
        cmd = ['gnuplot', script_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            fsize = os.path.getsize(png_file) if os.path.exists(png_file) else 0
            print(f"  -> {png_file} created ({fsize:,} bytes)")
            results[name] = png_file
        else:
            print(f"  ERROR: {result.stderr}")
            results[name] = None
    
    # Summary
    print("\n=== Residual Summary ===")
    for field in ['Ux', 'Uy', 'Uz', 'p', 'omega', 'k']:
        vals = []
        for t in sorted_times:
            v = time_data[t].get(field)
            if v:
                vals.append(v)
        if vals:
            print(f"  {field:>5}: last={vals[-1]:.2e}, min={min(vals):.2e}, max={max(vals):.2e}")
    
    return results

if __name__ == '__main__':
    main()
