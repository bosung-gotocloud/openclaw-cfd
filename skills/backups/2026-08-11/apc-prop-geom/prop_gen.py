import os
import numpy as np
import cadquery as cq
import pandas as pd
import re
from OCP.gp import gp_Pnt, gp_Vec, gp_Ax2, gp_Dir
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeEdge
from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections
from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
from OCP.BRepGProp import BRepGProp_VinertGK
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_ShapeEnum

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
    def __init__(self, data_dir=None):
        if data_dir is None:
            data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
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
                            'y_span': vals[0] * INCH_TO_METER,
                            'c_i': vals[1] * INCH_TO_METER,
                            'S_i': vals[5] * INCH_TO_METER,
                            'K_i': vals[6] * INCH_TO_METER,
                            't_ratio_i': vals[7],
                            'beta_i': vals[8],
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
        IMPORTANT: Removed duplicate LE point at loop closure.
        """
        upper = np.array(CLARKY_UPPER[::-1])
        lower = np.array(CLARKY_LOWER)
        
        # Remove duplicate LE point (upper[-1] == lower[0])
        x_coords = np.concatenate([upper[:, 0], lower[1:, 0]])
        z_coords = np.concatenate([upper[:, 1], lower[1:, 1]])
        
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
        Returns (df_aero, df_all, df_root) where df_root is the root airfoil (Y=0.01R).
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
        all_records = []
        
        for idx, row in df_stations.iterrows():
            y_span = row['y_span']
            c_i = row['c_i']
            S_i = row['S_i']
            K_i = row['K_i']
            t_ratio_i = row['t_ratio_i']
            beta_rad_i = np.radians(row['beta_i'])
            
            # Step 1: CLARK-Y airfoil scaling
            airfoil_base = self._get_clark_y_base()
            max_clarky_thick = self._get_clark_y_max_thickness_ratio()
            scale_factor = t_ratio_i / max_clarky_thick
            x_airfoil = airfoil_base[:, 1] * scale_factor * c_i
            z_airfoil = airfoil_base[:, 0] * c_i
            
            # Step 2: LE pivot twist rotation around Y axis
            x_rot = x_airfoil * np.cos(beta_rad_i) - z_airfoil * np.sin(beta_rad_i)
            z_rot = x_airfoil * np.sin(beta_rad_i) + z_airfoil * np.cos(beta_rad_i)
            
            # Step 3: 3D coordinates
            X_3d = x_rot + K_i
            Y_3d = np.full_like(X_3d, y_span)
            Z_3d = z_rot + (skew_sign * S_i)
            
            # Step 4-A: filter
            eta_i = y_span / R_val
            is_aero = (eta_i >= eta_start)
            
            # Step 4-B: span re-mapping
            u_i = (y_span - r_min) / (r_max - r_min) if r_max != r_min else 1.0
            y_remapped = (eta_start + (1.0 - eta_start) * u_i) * R_val
            
            for p_idx in range(len(X_3d)):
                all_records.append({
                    'station_idx': idx,
                    'r_over_R': y_span / R_val,
                    'X': X_3d[p_idx],
                    'Y': y_remapped,
                    'Z': Z_3d[p_idx],
                    'is_aero': is_aero,
                })
        
        df_out = pd.DataFrame(all_records)
        df_aero = df_out[df_out['is_aero']].copy()
        
        # Step 5: Create root airfoil — copy station_0 (station_idx=0) X,Z at Y=0.01R
        station_0_mask = df_out['station_idx'] == df_out['station_idx'].min()
        station_0_x = df_out.loc[station_0_mask, 'X'].values
        station_0_z = df_out.loc[station_0_mask, 'Z'].values
        y_root = 0.01 * R_val
        root_records = []
        for p_idx in range(len(station_0_x)):
            root_records.append({
                'station_idx': -1,  # root marker
                'r_over_R': 0.01,
                'X': station_0_x[p_idx],
                'Y': y_root,
                'Z': station_0_z[p_idx],
                'is_aero': False,
            })
        df_root = pd.DataFrame(root_records)
        
        # Save metadata for save_to_step
        self._last_metadata = metadata
        
        return df_aero, df_out, df_root, filename, metadata

    def save_to_csv(self, df, filename, output_dir=None):
        if output_dir is None:
            output_dir = os.path.dirname(os.path.abspath(__file__))
        os.makedirs(output_dir, exist_ok=True)
        csv_name = filename.replace(".PE0", ".csv")
        output_path = os.path.join(output_dir, csv_name)
        df[['station_idx', 'r_over_R', 'X', 'Y', 'Z']].to_csv(output_path, index=False)
        return output_path

    def save_to_step(self, df_aero, df_all, df_root, filename, R, output_dir=None):
        """
        Generate solid STEP file with:
        1. Blade 1 (loft from root@0.01R + all aero stations at eta_trans*R to R)
        2. Blade 2 (rotate blade1 180° around +X axis)
        3. Hub cylinder (radius=0.1R, along +X axis from xmin to xmax of station_root)
        All fused into a single solid, exported to STEP.
        Output filename: <pe_name>.step
        """
        import cadquery as cq
        
        if output_dir is None:
            output_dir = os.path.dirname(os.path.abspath(__file__))
        os.makedirs(output_dir, exist_ok=True)
        step_name = filename.replace(".PE0", ".step")
        output_path = os.path.join(output_dir, step_name)
        
        try:
            R_val = R
            eta_trans = getattr(self, '_last_metadata', {}).get('eta_trans', 0.2)
            y_start = eta_trans * R_val  # aerodynamic stations start
            
            # Build wires for blade1: root(Y=0.01R) + all aero stations (eta_trans*R ~ R)
            wires = []
            
            # root airfoil first
            root_pts = df_root[['X', 'Z']].values
            root_y = df_root['Y'].iloc[0]
            root_vertices = [cq.Vector(float(p[0]), float(root_y), float(p[1])) for p in root_pts]
            root_edges = [cq.Edge.makeLine(root_vertices[j], root_vertices[j+1]) for j in range(len(root_vertices)-1)]
            root_edges.append(cq.Edge.makeLine(root_vertices[-1], root_vertices[0]))
            root_wire = cq.Wire.assembleEdges(root_edges)
            wires.append(root_wire)
            
            # aero stations
            df_aero_filtered = df_all[df_all['Y'] >= y_start]
            grouped = df_aero_filtered.groupby('Y', sort=True)
            for y_val, group in grouped:
                pts = group[['X', 'Z']].values
                vertices = [cq.Vector(float(p[0]), float(y_val), float(p[1])) for p in pts]
                edges = [cq.Edge.makeLine(vertices[j], vertices[j+1]) for j in range(len(vertices)-1)]
                edges.append(cq.Edge.makeLine(vertices[-1], vertices[0]))
                wire = cq.Wire.assembleEdges(edges)
                wires.append(wire)
            
            n_sections = len(wires)
            print(f"  [{n_sections}] sections for blade1 (root@{root_y:.4f} + aero @Y={y_start:.4f}~{R_val:.4f})")
            
            # 1. Blade 1: ThruSections (memory efficient)
            from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections
            builder = BRepOffsetAPI_ThruSections(True, 1e-6, True)
            for w in wires:
                builder.AddWire(w.wrapped)
            builder.Build()
            blade1_raw = builder.Shape()
            print("  [1] Blade1 created")
            
            # 2. Blade 2: rotate 180° around +X axis
            from OCP.gp import gp_Trsf, gp_Ax1, gp_Pnt, gp_Dir
            from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
            trsf = gp_Trsf()
            trsf.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0)), np.pi)
            tr = BRepBuilderAPI_Transform(trsf)
            tr.Perform(blade1_raw)
            blade2_raw = tr.Shape()
            print("  [2] Blade2 created")
            
            # 3. Hub cylinder: radius=0.1R, along +X axis from xmin to xmax of station_root (root airfoil)
            root_x_min = df_root['X'].min()
            root_x_max = df_root['X'].max()
            hub_radius = 0.1 * R
            hub_length = root_x_max - root_x_min
            
            # OCC cylinder: origin at (xmin, 0, 0), direction +X
            from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
            from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
            hub_axis = gp_Ax2(gp_Pnt(root_x_min, 0, 0), gp_Dir(1, 0, 0))
            hub_raw = BRepPrimAPI_MakeCylinder(hub_axis, hub_radius, hub_length).Shape()
            print(f"  [3] Hub created: r={hub_radius:.6f}, x=[{root_x_min:.6f}, {root_x_max:.6f}]")
            
            # 4. Fuse: blade1 + blade2 + hub (separate, one by one)
            from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
            fused1 = BRepAlgoAPI_Fuse(blade1_raw, blade2_raw)
            fused1.Build()
            merged = fused1.Shape()
            
            fused2 = BRepAlgoAPI_Fuse(merged, hub_raw)
            fused2.Build()
            final = fused2.Shape()
            
            # Fix degenerate edges
            from OCP.ShapeFix import ShapeFix_Shape
            sf = ShapeFix_Shape(final)
            sf.SetPrecision(1e-6)
            sf.Perform()
            fixed = sf.Shape()
            
            # Export STEP
            from OCP.STEPControl import STEPControl_Writer
            writer = STEPControl_Writer()
            writer.Transfer(fixed, STEPControl_AsIs)
            writer.Write(output_path)
            
            # Verify
            from OCP.BRepCheck import BRepCheck_Analyzer
            analyzer = BRepCheck_Analyzer(fixed)
            vol = cq.Solid(fixed).Volume()
            
            print(f"Saved solid STEP: {output_path}")
            print(f"  Type: {fixed.ShapeType()}, Valid: {analyzer.IsValid()}")
            print(f"  Volume: {vol:.6e} m3")
        except Exception as e:
            import traceback
            traceback.print_exc()
            return None
        return output_path


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="APC Propeller Geometry Generator")
    parser.add_argument("prop_name", type=str, help="Propeller name (e.g. 7x5)")
    parser.add_argument("--output", "-o", type=str, default=None, help="Output directory (default: same as skill dir)")
    args = parser.parse_args()
    
    geom = APCPropellerGeometry()
    try:
        df_aero, df_all, df_root, fname, metadata = geom.generate_geometry(args.prop_name)
        print(f"Generated geometry for {fname}")
        
        output_dir = args.output or os.path.dirname(os.path.abspath(__file__))
        os.makedirs(output_dir, exist_ok=True)
        
        print(f"\n=== Parsed Metadata (SI Meters) ===")
        print(f"Radius (R)       : {metadata['R']:.4f} m ({metadata['R_in']} in)")
        print(f"Hub Rad (r_hub)  : {metadata['r_hub']:.4f} m (eta_hub = {metadata.get('eta_hub', 'N/A')})")
        print(f"Trans (r_trans)  : {metadata['r_trans']:.4f} m (eta_trans = {metadata.get('eta_trans', 'N/A')})")
        print(f"Number of blades : {metadata.get('N_blades', 2)}")
        print(f"Aero points      : {len(df_aero)}")
        print(f"All points       : {len(df_all)}")
        print(f"Root points      : {len(df_root)}")
        print(f"Y range (Span)   : {df_all.Y.min():.4f} ~ {df_all.Y.max():.4f} m")
        print(f"Y range (total)  : {df_root.Y.min():.4f} ~ {df_all.Y.max():.4f} m (incl. root)")
        print(f"X range (Axial)  : {df_all.X.min():.6f} ~ {df_all.X.max():.6f} m")
        print(f"Z range (Chord)  : {df_all.Z.min():.6f} ~ {df_all.Z.max():.6f} m")
        
        root_x_min = df_root['X'].min()
        root_x_max = df_root['X'].max()
        print(f"\n=== Root Airfoil (station_root) ===")
        print(f"Y position       : {df_root.Y.iloc[0]:.4f} m (0.01R)")
        print(f"X min            : {root_x_min:.6f} m")
        print(f"X max            : {root_x_max:.6f} m")
        print(f"X extent         : {root_x_max - root_x_min:.6f} m")
        
        hub_radius = 0.1 * metadata['R']
        print(f"\n=== Hub Cylinder ===")
        print(f"Hub radius       : {hub_radius:.6f} m (0.1R)")
        print(f"Hub axis         : +X direction")
        print(f"Hub center X     : {(root_x_min + root_x_max)/2:.6f} m")
        print(f"Hub height (along X) : {root_x_max - root_x_min:.6f} m")
        
        csv_path = geom.save_to_csv(df_aero, fname, output_dir=output_dir)
        step_path = geom.save_to_step(df_aero, df_all, df_root, fname, metadata['R'], output_dir=output_dir)
        if step_path:
            print(f"\nCSV file: {csv_path}")
            print(f"STEP file: {step_path}")
        else:
            print(f"\nCSV file: {csv_path}")
            print("\nSTEP generation FAILED")
    except Exception as e:
        import traceback
        traceback.print_exc()
