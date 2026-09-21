import cadquery as cq
import numpy as np

filepath = "/home/bosung/WinD/0.cfd/1.AI-agent/tip_refine_mesh/myShahed-salome/myShahed.stp"

print(f"Reading: {filepath}")
obj = cq.importers.importStep(filepath)
val = obj.val()

print(f"Shape type: {type(val).__name__}")
print(f"Vertices: {len(val.Vertices())}")
print(f"Edges: {len(val.Edges())}")
print(f"Faces: {len(val.Faces())}")

# Check solids
all_solids = val.Solids()
print(f"\nSolids count: {len(all_solids)}")

# Try cleaning - sometimes STEP needs cleanup to form solids
from cadquery.occ_impl.shapetools import fix
print("\nTrying to fix/clean geometry...")
try:
    fixed = val.fix(tolerance=1e-4, minSize=1e-5)
    print(f"Fixed type: {type(fixed).__name__}")
    fixed_solids = fixed.Solids()
    print(f"Fixed solids: {len(fixed_solids)}")
    if len(fixed_solids) > 0:
        solid = fixed_solids[0]
        bb = solid.BoundingBox()
        cx, cy, cz = (bb.xmin+bb.xmax)/2, (bb.ymin+bb.ymax)/2, (bb.zmin+bb.zmax)/2
        verts, polys = solid.tessellate(1e-3)
        verts_arr = np.array([list(v) for v in verts])
        print(f"\nFixed solid:")
        print(f"  Vertices: {len(solid.Vertices())}")
        print(f"  Edges: {len(solid.Edges())}")
        print(f"  Faces: {len(solid.Faces())}")
        print(f"  BBox: x[{bb.xmin:.4f}, {bb.xmax:.4f}] y[{bb.ymin:.4f}, {bb.ymax:.4f}] z[{bb.zmin:.4f}, {bb.zmax:.4f}]")
        print(f"  Center: [{cx:.4f}, {cy:.4f}, {cz:.4f}]")
        print(f"  Mesh: {len(verts)} verts, {len(polys)} faces")
        print(f"  Mesh BBox: x[{verts_arr[:,0].min():.4f}, {verts_arr[:,0].max():.4f}] y[{verts_arr[:,1].min():.4f}, {verts_arr[:,1].max():.4f}] z[{verts_arr[:,2].min():.4f}, {verts_arr[:,2].max():.4f}]")
        print(f"  Volume: {solid.Volume:.6f}")
        print(f"  Area: {solid.Area:.6f}")
    else:
        # Even after fix, no solids - report face/edge info
        print("\nStill no solids. Geometry is surface-only (no volume).")
        print("This means it's a shell/wireframe, not a solid body.")
        print("\nChecking if geometry is valid for CFD (needs to be a closed shell):")
        faces = val.Faces()
        total_area = sum(f.Area for f in faces)
        print(f"Total face area: {total_area:.6f}")
        
        # Check if shell is closed
        wires = val.Wires()
        print(f"Total wires: {len(wires)}")
        
        # Check edges - free edges (edges with only 1 face) indicate open shells
        edge_faces = {}
        for f in faces:
            for e in f.Edges():
                key = (round(e.Center().x, 6), round(e.Center().y, 6), round(e.Center().z, 6))
                edge_faces[key] = edge_faces.get(key, 0) + 1
        
        free_edges = [k for k, v in edge_faces.items() if v < 2]
        print(f"Free edges (open boundary): {len(free_edges)}")
        if len(free_edges) > 0:
            print("  ⚠️  Geometry has open edges - NOT a closed shell!")
            print("  This geometry CANNOT be used directly for volume mesh.")
            print("  Need to check if it's an incomplete STEP or needs repair.")
        else:
            print("  ✓ All edges shared by 2+ faces - shell may be closed but cadquery couldn't form solids")
            
except Exception as e:
    print(f"Fix failed: {e}")

# Overall BBox
bb = val.BoundingBox()
dims = bb.xmax-bb.xmin, bb.ymax-bb.ymin, bb.zmax-bb.zmin
print(f"\n=== Overall BBox: x[{bb.xmin:.4f}, {bb.xmax:.4f}] y[{bb.ymin:.4f}, {bb.ymax:.4f}] z[{bb.zmin:.4f}, {bb.zmax:.4f}] ===")
print(f"Dimensions: x={dims[0]:.4f} y={dims[1]:.4f} z={dims[2]:.4f}")
