import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import os
import sys

def plot_propeller_sections_offset(csv_path):
    if not os.path.exists(csv_path):
        print(f"Error: CSV file not found at {csv_path}")
        return

    df = pd.read_csv(csv_path)
    stations = df['r_over_R'].unique()
    stations.sort()
    
    fig, ax = plt.subplots(figsize=(15, 6))
    
    colors = plt.cm.viridis(np.linspace(0, 1, len(stations)))
    
    for i, r_val in enumerate(stations):
        section = df[df['r_over_R'] == r_val]
        y_offset = section['y'].iloc[0]
        
        # Plot (Y + X, Z) to show airfoils spread across the span
        ax.plot(section['y'] + section['x'], section['z'], 
                 color=colors[i], linewidth=1, alpha=0.8)
        
        if i % (len(stations)//10 if len(stations)>10 else 1) == 0:
            ax.text(y_offset, section['z'].max() + 5, f'{r_val:.2f}', 
                    ha='center', fontsize=8, color=colors[i])

    ax.set_title(f"Propeller Blade Airfoil Sections Spread Along Span\nFile: {os.path.basename(csv_path)}")
    ax.set_xlabel("Spanwise Position Y + Chordwise X [mm]")
    ax.set_ylabel("Thickness Z [mm]")
    ax.grid(True, linestyle='--', alpha=0.5)
    ax.axis('equal')
    
    sm = plt.cm.ScalarMappable(cmap=plt.cm.viridis, norm=plt.Normalize(vmin=stations[0], vmax=stations[-1]))
    sm.set_array([])
    fig.colorbar(sm, ax=ax, label='r/R (Station)')
    
    output_path = "skills/apc-prop-geom/test/prop_spanwise_profiles.png"
    plt.savefig(output_path, dpi=300)
    plt.close()
    print(f"Spanwise profiles plot saved to {output_path}")

if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "skills/apc-prop-geom/test/10x4M-LH-PERF.csv"
    plot_propeller_sections_offset(csv_path)
