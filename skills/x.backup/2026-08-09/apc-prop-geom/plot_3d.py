import pandas as pd
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import numpy as np
import os
import sys

def plot_propeller_3d_meters(csv_path):
    if not os.path.exists(csv_path):
        print(f"Error: CSV file not found at {csv_path}")
        return

    df = pd.read_csv(csv_path)
    
    fig = plt.figure(figsize=(12, 10))
    ax = fig.add_subplot(111, projection='3d')
    
    stations = df['r_over_R'].unique()
    stations.sort()
    
    colors = plt.cm.viridis(np.linspace(0, 1, len(stations)))
    
    for i, r_val in enumerate(stations):
        section = df[df['r_over_R'] == r_val]
        ax.plot(section['x'], section['y'], section['z'], 
                color=colors[i], linewidth=1, alpha=0.7)
    
    key_indices = [0, len(stations)//2, len(stations)-1]
    for idx in key_indices:
        r_val = stations[idx]
        section = df[df['r_over_R'] == r_val]
        ax.plot(section['x'], section['y'], section['z'], 
                color='red', linewidth=2, label=f'r/R = {r_val:.2f}')
    
    ax.set_title(f"3D Propeller Blade Geometry (Unit: Meters)\nFile: {os.path.basename(csv_path)}", fontsize=14)
    ax.set_xlabel("X [m]")
    ax.set_ylabel("Y [m]")
    ax.set_zlabel("Z [m]")
    ax.legend()
    
    ax.view_init(elev=20, azim=30)
    
    # Dynamic equal aspect ratio based on meters
    all_coords = df[['x', 'y', 'z']].values
    max_range = (all_coords.max(axis=0) - all_coords.min(axis=0)).max() / 2.0
    mid = (all_coords.max(axis=0) + all_coords.min(axis=0)) / 2.0
    ax.set_xlim(mid[0] - max_range, mid[0] + max_range)
    ax.set_ylim(mid[1] - max_range, mid[1] + max_range)
    ax.set_zlim(mid[2] - max_range, mid[2] + max_range)
    
    output_path = "skills/apc-prop-geom/test/prop_3d_meters.png"
    plt.savefig(output_path, dpi=300)
    plt.close()
    print(f"3D Plot in meters saved to {output_path}")

if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "skills/apc-prop-geom/test/10x4M-LH-PERF.csv"
    plot_propeller_3d_meters(csv_path)
