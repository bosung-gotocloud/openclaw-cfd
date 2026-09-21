---
name: paraview
description: ParaView post-processing for OpenFOAM CFD cases. Use when the user asks to visualize, slice, contour, or analyze OpenFOAM simulation data using ParaView or pvpython. Handles case.foam loading, decomposed cases, patches, and volume operations.
---

# ParaView Post-Processing

## Case Loading

1. User provides directory containing `case.foam`
2. **Decomposed mode:** If `processor*` directories exist, set `CaseType = 'Decomposed Case'`
3. **Cell-to-point filter:** Enable `Createcelltopointfiltereddata = 1` for smooth visualization
4. **Rename source:** Use `RenameSource('OpenFOAMReader1', case_foam)` after loading
5. **Time steps:** Use latest time step by setting `render_view.ViewTime = case_foam.TimestepValues[-1]`

## Naming Conventions

- **Patches:** Prefixed with `patch/` (e.g., `patch/wall`, `patch/surface`)
- **Volume:** `internalMesh` = entire fluid domain

## Mesh Regions Selection

- Select patches via `MeshRegions` property: `case_foam.MeshRegions = ['patch/body_surface']`
- For volume operations: `case_foam.MeshRegions = ['internalMesh']`

## Color Mapping

- Set color array on representation: `rep.ColorArrayName = ['POINTS', 'p']`
- Use POINTS data (cell-to-point interpolated)
- Get representation from Show(): `rep = Show(case_foam, render_view)`

## Scalar Bar (Legend)

- Show legend: `scalar_bar = GetScalarBar(pLUT, render_view); scalar_bar.Visibility = 1`
- Set title: `scalar_bar.Title = 'p'`
- Clear component title: `scalar_bar.ComponentTitle = ''`

## Time Steps

- **Load all time steps:** Scripts load all available time steps automatically
- **Display:** Shows the **last time step** by default
- **Animation:** Use ParaView's play button to animate through all time steps

## Operations

- "show p on patch/wall" → apply field to specific patch
- "slice y=0 plane" → applied to `internalMesh`
- "slice y=0 for patch/wall" → applied to `patch/wall`
- "streamlines at (x,y,z) radius r" → streamlines from sphere seed source

## Streamlines

```bash
# Usage: pvpython plot_streamlines.py <case_dir> [cx] [cy] [cz] [radius]
pvpython plot_streamlines.py /path/to/case 0.696 0.911 0.322 0.1
```

## Execution Workflow

1. Generate Python script for requested operations
2. Save script to case directory (where `case.foam` is located)
3. Run with `/opt/paraview/bin/pvpython`
4. Save result as `.pvsm` state file in case directory
5. Launch ParaView GUI: `/opt/paraview/bin/paraview`
6. Open the `.pvsm` file
7. Keep ParaView GUI open for user inspection

## Paths

- ParaView: `/opt/paraview/bin/paraview`
- pvpython: `/opt/paraview/bin/pvpython`

## Sample Script: Show Value on Patch

```python
from paraview.simple import *

# === USER INPUT ===
case_dir = "/path/to/case"
patch_name = "patch/body_surface"  # Use 'patch/' prefix
field_name = "p"  # Field to visualize

# === LOAD CASE ===
case_foam = OpenFOAMReader(FileName=case_dir + "/case.foam")
RenameSource('OpenFOAMReader1', case_foam)

# Decomposed case detection
if any(d.startswith('processor') for d in os.listdir(case_dir) if os.path.isdir(os.path.join(case_dir, d))):
    case_foam.CaseType = 'Decomposed Case'

# Enable cell-to-point filter
case_foam.Createcelltopointfiltereddata = 1

# Select patch
case_foam.MeshRegions = [patch_name]

# === VIEW AND TIME ===
render_view = GetActiveViewOrCreate('RenderView')
if hasattr(case_foam, 'TimestepValues') and len(case_foam.TimestepValues) > 0:
    render_view.ViewTime = case_foam.TimestepValues[-1]

# === SHOW AND COLOR ===
rep = Show(case_foam, render_view)
rep.ColorArrayName = ['POINTS', field_name]

# === SCALAR BAR ===
fieldLUT = GetColorTransferFunction(field_name)
scalar_bar = GetScalarBar(fieldLUT, render_view)
scalar_bar.Visibility = 1
scalar_bar.Title = field_name
scalar_bar.ComponentTitle = ''

# === RENDER AND SAVE ===
render_view.ResetCamera()
Render()
SaveState(case_dir + "/show_" + field_name + "_on_patch.pvsm")
```

## Patch Distribution

Draw field distribution on a specified patch type in OpenFOAM cases.

**Workflow:**
1. **Identify case location** and confirm case.foam exists
2. **Check for processor\* directories**: If `processor*` dirs exist → set `CaseType = 'Decomposed Case'`
3. **Scan the file**: `UpdatePipelineInformation()`
4. **List available patches** using PatchArrayInfo
5. **Set patch and field**: `MeshRegions = [...]`, `CellArrays = [...]`
6. **Enable cell-to-point** if point data needed (`Createcelltopointfiltereddata = 1`)
7. **Update pipeline** and configure display
8. **Save state** and launch ParaView

**Key Properties:**
- `CaseType = 'Decomposed Case'` - Set explicitly for decomposed cases
- `UpdatePipelineInformation()` - Call after setting CaseType to scan the file
- `MeshRegions` - Select which patch/mesh to display
- Patch names follow format: `patch/patchName`

## Slice Distribution

Create a slice plane and draw field distribution. Supports combined visualizations.

**Workflow:**
1. **Identify case location** and confirm case.foam exists
2. **Check for processor\* directories** → set `CaseType = 'Decomposed Case'`
3. **Load case** with `OpenFOAMReader`
4. **Enable cell-to-point** (`Createcelltopointfiltereddata = 1`)
5. **Create visualization**:
   - Single: Slice filter + display
   - Combined: Multiple readers/filters in same view
6. **Save state** and launch ParaView

**Slice Filter:**
- `SliceType = 'Plane'`
- `SliceType.Normal = [1,0,0]` (x), `[0,1,0]` (y), `[0,0,1]` (z)

**Combined Visualization:**
```python
# Use separate readers for each visualization
reader1 = OpenFOAMReader(registrationName='case1', FileName=foam_file)
reader2 = OpenFOAMReader(registrationName='case2', FileName=foam_file)

reader1.MeshRegions = ['patch/wall_name']
reader2.MeshRegions = ['internalMesh']

Show(reader1, view, 'GeometryRepresentation')
Show(sliceFilter, view, 'GeometryRepresentation')
```

## Available Scripts

| Script | Description |
|--------|-------------|
| `launch.py` | Launch ParaView GUI |
| `list_patches.py` | List available patches in case |
| `load_case.py` | Load OpenFOAM case |
| `plot_patch.py` | Plot field on patch |
| `plot_pressure_wall.py` | Plot pressure on wall |
| `plot_slice.py` | Plot field on slice plane |
| `slice_plot.py` | Slice visualization |
| `slice_y0_Umag.py` | Slice at y=0 with velocity magnitude |
| `wall_p.py` | Wall pressure visualization |
| `plot_streamlines.py` | Streamlines from sphere seed |
| `combined_plot.py` | Combined patch + slice visualization |
| `plot_combined.py` | Combined visualization |

**Usage:**
```bash
/opt/paraview/bin/pvpython <script.py> <case_dir>
```