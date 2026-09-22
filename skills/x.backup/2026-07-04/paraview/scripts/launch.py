#!/usr/bin/env python3
"""
Launcher: Run pvpython script and open result in ParaView GUI.
Usage: python launch.py <case_dir> <script> [args...]

Examples:
  python launch.py /path/to/case list_patches
  python launch.py /path/to/case plot_patch patch/wall p
  python launch.py /path/to/case plot_slice y 0 Umag
  python launch.py /path/to/case plot_combined patch/wall p y 0 Umag
"""
import os
import sys
import subprocess

PVPYTHON = '/opt/paraview/bin/pvpython'
PARAVIEW = '/opt/paraview/bin/paraview'
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))

# Display environment (can be set via DISPLAY env var)
DISPLAY = os.environ.get('DISPLAY', ':0')

SCRIPTS = {
    'list_patches': 'list_patches.py',
    'plot_patch': 'plot_patch.py',
    'plot_slice': 'plot_slice.py',
    'plot_combined': 'plot_combined.py',
}


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        print("\nAvailable scripts:")
        for name in SCRIPTS:
            print(f"  {name}")
        sys.exit(1)
    
    case_dir = sys.argv[1]
    script_name = sys.argv[2]
    
    if script_name not in SCRIPTS:
        print(f"Error: Unknown script '{script_name}'")
        print(f"Available: {list(SCRIPTS.keys())}")
        sys.exit(1)
    
    script_path = os.path.join(SCRIPTS_DIR, SCRIPTS[script_name])
    
    # Build command
    cmd = [PVPYTHON, script_path, case_dir] + sys.argv[3:]
    
    print(f"Running: {' '.join(cmd)}")
    print(f"Case: {case_dir}")
    print("-" * 50)
    
    # Run pvpython
    result = subprocess.run(cmd, capture_output=False)
    
    if result.returncode != 0:
        print(f"Script failed with code {result.returncode}")
        sys.exit(result.returncode)
    
    # Find generated .pvsm file
    pvsm_files = [f for f in os.listdir(case_dir) if f.endswith('.pvsm')]
    if pvsm_files:
        # Use the most recently modified
        pvsm_files.sort(key=lambda f: os.path.getmtime(os.path.join(case_dir, f)))
        pvsm_path = os.path.join(case_dir, pvsm_files[-1])
        
        print("-" * 50)
        print(f"Launching ParaView with: {pvsm_path}")
        
        # Launch ParaView
        env = os.environ.copy()
        env['DISPLAY'] = DISPLAY
        subprocess.Popen([PARAVIEW, '--state=' + pvsm_path], env=env)
        print(f"ParaView launched on DISPLAY={DISPLAY}")
    else:
        print("No .pvsm file generated")


if __name__ == "__main__":
    main()
