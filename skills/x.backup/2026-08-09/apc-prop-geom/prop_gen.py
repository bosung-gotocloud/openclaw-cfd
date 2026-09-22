import os
import numpy as np
import cadquery as cq
import pandas as pd
import re

# Unit conversion constant (Inch -> Meter)
INCH_TO_METER = 0.0254

# CLARK-Y airfoil coordinates (from UIUC Airfoil Database)
# Format: (x_chord, y_thickness) non-dimensional
# x_chord: chordwise [0=LE, 1=TE]
# y_thickness: thickness direction (upper > 0, lower < 0)
CLARKY_UPPER = [
    (0.0000000, 0.0000000),
    (0.0005000, 0.0023390),
    (0.0010000, 0.0037271),
    (0.0020000, 0.0058025),
    (0.0040000, 0.0089238),
    (0.0080000, 0.0137350),
    (0.0120000, 0.0178581),
    (0.0200000, 0.0253735),
    (0.0300000, 0.0330215),
    (0.0400000, 0.0391283),
    (0.0500000, 0.0442753),
    (0.0600000, 0.0487571),
    (0.0800000, 0.0564308),
    (0.1000000, 0.0629981),
    (0.1200000, 0.0686204),
    (0.1400000, 0.0734360),
    (0.1600000, 0.0775707),
    (0.1800000, 0.0810687),
    (0.2000000, 0.0839202),
    (0.2200000, 0.0861433),
    (0.2400000, 0.0878308),
    (0.2600000, 0.0890840),
    (0.2800000, 0.0900016),
    (0.3000000, 0.0906804),
    (0.3200000, 0.0911857),
    (0.3400000, 0.0915079),
    (0.3600000, 0.0916266),
    (0.3800000, 0.0915212),
    (0.4000000, 0.0911712),
    (0.4200000, 0.0905657),
    (0.4400000, 0.0897175),
    (0.4600000, 0.0886427),
    (0.4800000, 0.0873572),
    (0.5000000, 0.0858772),
    (0.5200000, 0.0842145),
    (0.5400000, 0.0823712),
    (0.5600000, 0.0803480),
    (0.5800000, 0.0781451),
    (0.6000000, 0.0757633),
    (0.6200000, 0.0732055),
    (0.6400000, 0.0704822),
    (0.6600000, 0.0676046),
    (0.6800000, 0.0645843),
    (0.7000000, 0.0614329),
    (0.7200000, 0.0581599),
    (0.7400000, 0.0547675),
    (0.7600000, 0.0512565),
    (0.7800000, 0.0476281),
    (0.8000000, 0.0438836),
    (0.8200000, 0.0400245),
    (0.8400000, 0.0360536),
    (0.8600000, 0.0319740),
    (0.8800000, 0.0277891),
    (0.9000000, 0.0235025),
    (0.9200000, 0.0191156),
    (0.9400000, 0.0146239),
    (0.9600000, 0.0100232),
    (0.9700000, 0.0076868),
    (0.9800000, 0.0053335),
    (0.9900000, 0.0029690),
    (1.0000000, 0.0005993),
]

CLARKY_LOWER = [
    (0.0000000, 0.0000000),
    (0.0005000, -0.0046700),
    (0.0010000, -0.0059418),
    (0.0020000, -0.0078113),
    (0.0040000, -0.0105126),
    (0.0080000, -0.0142862),
    (0.0120000, -0.0169733),
    (0.0200000, -0.0202723),
    (0.0300000, -0.0226056),
    (0.0400000, -0.0245211),
    (0.0500000, -0.0260452),
    (0.0600000, -0.0271277),
    (0.0800000, -0.0284595),
    (0.1000000, -0.0293786),
    (0.1200000, -0.0299633),
    (0.1400000, -0.0302404),
    (0.1600000, -0.0302546),
    (0.1800000, -0.0300490),
    (0.2000000, -0.0296656),
    (0.2200000, -0.0291445),
    (0.2400000, -0.0285181),
    (0.2600000, -0.0278164),
    (0.2800000, -0.0270696),
    (0.3000000, -0.0263079),
    (0.3200000, -0.0255565),
    (0.3400000, -0.0248176),
    (0.3600000, -0.0240870),
    (0.3800000, -0.0233606),
    (0.4000000, -0.0226341),
    (0.4200000, -0.0219042),
    (0.4400000, -0.0211708),
    (0.4600000, -0.0204353),
    (0.4800000, -0.0196986),
    (0.5000000, -0.0189619),
    (0.5200000, -0.0182262),
    (0.5400000, -0.0174914),
    (0.5600000, -0.0167572),
    (0.5800000, -0.0160232),
    (0.6000000, -0.0152893),
    (0.6200000, -0.0145551),
    (0.6400000, -0.0138207),
    (0.6600000, -0.0130862),
    (0.6800000, -0.0123515),
    (0.7000000, -0.0116169),
    (0.7200000, -0.0108823),
    (0.7400000, -0.0101478),
    (0.7600000, -0.0094133),
    (0.7800000, -0.0086788),
    (0.8000000, -0.0079443),
    (0.8200000, -0.0072098),
    (0.8400000, -0.0064753),
    (0.8600000, -0.0057408),
    (0.8800000, -0.0050063),
    (0.9000000, -0.0042718),
    (0.9200000, -0.0035373),
    (0.9400000, -0.0028028),
    (0.9600000, -0.0020683),
    (0.9700000, -0.0017011),
    (0.9800000, -0.0013339),
    (0.9900000, -0.0009666),
    (1.0000000, -0.0005993),
]


class APCPropellerGeometry:
    def __init__(self, data_dir="skills/apc-prop-geom/data"):
        self.data_dir = data_dir
        self.pe0_files = [f for f in os.listdir(data_dir) if f.endswith(".PE0")]

    def parse_pe0(self, filename):
        path = os.path.join(self.data_dir, filename)
        with open(path, 'r') as f:
            content = f.read()
        
        lines = content.strip().split('\n')
        metadata = {}
        
        for line in lines:
            if 'RADIUS:' in line:
                m = re.search(r'RADIUS:\s*([\d\.]+)', line)
                if m: metadata['R_in'] = float(m.group(1))
            elif 'HUBRAD:' in line:
                m = re.search(r'HUBRAD:\s*([\d\.]+)', line)
                if m: metadata['r_hub_in'] = float(m.group(1))
            elif 'HUBTRA:' in line:
                m = re.search(r'HUBTRA:\s*([\d\.]+)', line)
                if m: metadata['r_trans_in'] = float(m.group(1))
            elif 'BLADES:' in line:
                m = re.search(r'BLADES:\s*(\d+)', line)
                if m: metadata['N_blades'] = int(m.group(1))
        
        metadata['R'] = metadata.get('R_in', 0.0) * INCH_TO_METER
        metadata['r_hub'] = metadata.get('r_hub_in', 0.0) * INCH_TO_METER
        metadata['r_trans'] = metadata.get('r_trans_in', 0.0) * INCH_TO_METER
        
        if metadata['R'] > 0:
            metadata['eta_hub'] = metadata['r_hub'] / metadata['R']
            metadata['eta_trans'] = metadata['r_trans'] / metadata['R']
        
        stations = []
        in_table = False
        
        for line in lines:
            line_str = line.strip()
            if line_str.startswith("STATION") and "CHORD" in line_str:
                in_table = True
                continue
            if in_table and ("(IN)" in line_str or "(QUOTED)" in line_str or "(DEG)" in line_str):
                continue
            if in_table and ("RADIUS:" in line_str or "AIRFOIL SUMMARY" in line_str):
                in_table = False
                break
            
            if in_table and line_str:
                tokens = line_str.split()
                if len(tokens) >= 14:
                    try:
                        vals = [float(t) for t in tokens]
                        stations.append({
                            'y_span': vals[0] * INCH_TO_METER,    # STATION [m] (+Y Spanwise)
                            'c_i': vals[1] * INCH_TO_METER,        # CHORD [m]
                            'S_i': vals[5] * INCH_TO_METER,        # SWEEP/SKEW [m] (Z Offset)
                            'K_i': vals[6] * INCH_TO_METER,        # RAKE [m] (X Offset)
                            't_ratio_i': vals[7],                  # THICKNESS RATIO (t/c, unitless)
                            'beta_i': vals[8],                     # TWIST [deg]
                        })
                    except ValueError:
                        continue
        
        return metadata, pd.DataFrame(stations)

    def find_best_prop(self, prop_name):
        exact_filename = f"{prop_name}-PERF.PE0"
        if exact_filename in self.pe0_files:
            return exact_filename, False
        
        match = re.match(r"(\d+\.?\d*)x(\d+\.?\d*)", prop_name)
        if not match:
            raise ValueError("Invalid propeller name format. Use 'DiameterxPitch'")
        
        target_d = float(match.group(1))
        target_p = float(match.group(2))
        best_file = None
        min_dist = float('inf')
        
        for f in self.pe0_files:
            f_match = re.match(r"(\d+\.?\d*)x(\d+\.?\d*)", f)
            if f_match:
                d = float(f_match.group(1))
                p = float(f_match.group(2))
                dist = np.sqrt((d - target_d)**2 + (p - target_p)**2)
                if dist < min_dist:
                    min_dist = dist
                    best_file = f
        return best_file, True

    def _get_clark_y_base(self):
        """
        CLARK-Y airfoil from UIUC actual coordinates.
        Non-dimensional: chord=1, max thickness ~0.117 at 28% chord.
        Returns: [chord_frac, thick_frac] array, closed loop
        
        Coordinate mapping for 3D:
        - X: thickness direction (from y_thickness)
        - Z: chord direction (from x_chord)
        """
        upper = np.array(CLARKY_UPPER[::-1])    # TE→LE (chord_frac, thick_frac)
        lower = np.array(CLARKY_LOWER)           # LE→TE (chord_frac, thick_frac)
        
        # Close the loop
        x_coords = np.concatenate([upper[:, 0], lower[:, 0], [upper[0, 0]]])
        z_coords = np.concatenate([upper[:, 1], lower[:, 1], [upper[0, 1]]])
        
        return np.column_stack((x_coords, z_coords))

    def _get_clark_y_max_thickness_ratio(self):
        """CLARK-Y max thickness / chord = ~0.117 (11.7% at 28% chord)"""
        return 0.117

    def generate_geometry(self, prop_name, eta_start_override=None, is_lh=True):
        """
        Coordinate system:
        - X: shaft axis (rotation axis)
        - Y: span (hub=0 → tip=R)
        - Z: chord (LE=0 → TE=c)
        Airfoil section: X-Z plane (perpendicular to Y axis).
        - X = thickness direction (from CLARK-Y y_thickness)
        - Z = chord direction (from CLARK-Y x_chord)
        
        TWIST rotates around Y axis: pitch + means LE moves in +X direction.
        
        Single blade only (no rotation).
        """
        filename, is_interpolated = self.find_best_prop(prop_name)
        if not filename:
            raise FileNotFoundError(f"No suitable PE0 data found for {prop_name}")
        
        metadata, df_stations = self.parse_pe0(filename)
        
        if df_stations.empty:
            raise ValueError("No station data found in PE0 file.")
        
        R_val = metadata['R']
        eta_start = eta_start_override if eta_start_override is not None else metadata['eta_trans']
        
        r_min = df_stations['y_span'].min()
        r_max = df_stations['y_span'].max()
        
        skew_sign = -1.0 if is_lh else 1.0
        
        records = []
        
        for idx, row in df_stations.iterrows():
            y_span = row['y_span']          # +Y Span [m]
            c_i = row['c_i']                # Chord [m]
            S_i = row['S_i']                # Skew [m] (Z offset)
            K_i = row['K_i']                # Rake [m] (X offset)
            t_ratio_i = row['t_ratio_i']    # t/c (unitless)
            beta_rad_i = np.radians(row['beta_i'])
            
            # Step 1: CLARK-Y airfoil (non-dimensional: chord=1, max thick ~0.117)
            # Scale by actual chord c_i, then adjust thickness by PE0 t_ratio
            airfoil_base = self._get_clark_y_base()
            # airfoil_base: [chord_frac, thick_frac]
            # Scale chord_frac by c_i → Z (chord direction in meters)
            # Scale thick_frac by PE0 t_ratio → X (thickness in meters)
            # thick_frac is non-dimensional (max ~0.0916), CLARK-Y max thick ratio ~0.117
            # PE0 t_ratio overrides CLARK-Y's default 11.7% thickness
            max_clarky_thick = self._get_clark_y_max_thickness_ratio()
            scale_factor = t_ratio_i / max_clarky_thick  # relative to CLARK-Y default
            x_airfoil = airfoil_base[:, 1] * scale_factor * c_i   # X: thickness [m]
            z_airfoil = airfoil_base[:, 0] * c_i                  # Z: chord [m]
            
            # Step 2: LE(0,0) twist rotation around Y axis (pitch + → LE up in +X)
            # Rotation in X-Z plane around Y axis
            x_rot = x_airfoil * np.cos(beta_rad_i) - z_airfoil * np.sin(beta_rad_i)
            z_rot = x_airfoil * np.sin(beta_rad_i) + z_airfoil * np.cos(beta_rad_i)
            
            # Step 3: 3D coordinates (single blade, no rotation)
            X_3d = x_rot + K_i       # +X: Axial (shaft) with RAKE offset
            Y_3d = np.full_like(X_3d, y_span)   # +Y: Span
            Z_3d = z_rot + (skew_sign * S_i)    # +Z: Chord with SWEEP offset
            
            # Step 4-A: filter
            eta_i = y_span / R_val
            is_aero = (eta_i >= eta_start)
            
            # Step 4-B: span re-mapping
            u_i = (y_span - r_min) / (r_max - r_min) if r_max != r_min else 1.0
            y_remapped = (eta_start + (1.0 - eta_start) * u_i) * R_val
            
            for p_idx in range(len(X_3d)):
                records.append({
                    'station_idx': idx,
                    'r_over_R': y_span / R_val,
                    'X': X_3d[p_idx],
                    'Y': y_remapped,
                    'Z': Z_3d[p_idx],
                    'is_aero': is_aero,
                })
        
        df_out = pd.DataFrame(records)
        df_aero = df_out[df_out['is_aero']].copy()
        
        return df_aero, filename, metadata

    def save_to_csv(self, df, filename):
        csv_name = filename.replace(".PE0", ".csv")
        output_path = os.path.join("skills/apc-prop-geom/test", csv_name)
        df[['r_over_R', 'X', 'Y', 'Z']].to_csv(output_path, index=False)
        return output_path

    def save_to_step(self, df, filename):
        step_name = filename.replace(".PE0", ".step")
        output_path = os.path.join("skills/apc-prop-geom/test", step_name)
        
        try:
            grouped = df.groupby('station_idx')
            stations = []
            for idx, group in grouped:
                pts = group[['X', 'Z']].values
                stations.append(pts)
            
            if len(stations) < 2:
                raise ValueError("Need at least 2 stations for lofting")
            
            first_gy = stations[0][0][1]
            result = cq.Workplane("XY").workplane(offset=first_gy)
            result = result.spline([(p[0], p[1]) for p in stations[0]]).close()
            
            for i in range(1, len(stations)):
                gy = stations[i][0][1]
                relative_offset = gy - first_gy
                result = result.workplane(offset=relative_offset).spline([(p[0], p[1]) for p in stations[i]]).close()
            
            final_prop = result.loft()
            cq.exporters.export(final_prop, output_path)
        except Exception as e:
            with open(output_path, 'w') as f:
                f.write(f"STEP generation failed: {e}")
        return output_path

if __name__ == "__main__":
    geom = APCPropellerGeometry()
    try:
        df, fname, metadata = geom.generate_geometry("10x4M-LH")
        print(f"Generated geometry for {fname}")
        
        print(f"\n=== Parsed Metadata (SI Meters) ===")
        print(f"Radius (R)       : {metadata['R']:.4f} m ({metadata['R_in']} in)")
        print(f"Hub Rad (r_hub)  : {metadata['r_hub']:.4f} m (eta_hub = {metadata.get('eta_hub', 'N/A')})")
        print(f"Trans (r_trans)  : {metadata['r_trans']:.4f} m (eta_trans = {metadata.get('eta_trans', 'N/A')})")
        print(f"Number of blades : {metadata.get('N_blades', 2)}")
        print(f"Total points     : {len(df)}")
        print(f"Y range (Span)   : {df.Y.min():.4f} ~ {df.Y.max():.4f} m")
        print(f"X range (Axial)  : {df.X.min():.6f} ~ {df.X.max():.6f} m")
        print(f"Z range (Chord)  : {df.Z.min():.6f} ~ {df.Z.max():.6f} m")
        
        geom.save_to_csv(df, fname)
        geom.save_to_step(df, fname)
        print(f"\nFiles saved in skills/apc-prop-geom/test")
    except Exception as e:
        import traceback
        traceback.print_exc()
