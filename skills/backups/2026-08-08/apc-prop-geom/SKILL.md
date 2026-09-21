# apc-prop-geom — APC Propeller Geometry → STEP CAD

## Purpose
Generate STEP CAD files from APC propeller geometry data (453 models).

## Data Source
- **453 APC propeller `.PE0` files** in `data/` directory

## Coordinate System
- **Y axis** = blade span (hub at Y=0, tip at Y=radius)
- **Rotation axis** = +Y (prop spins around Y)
- **Chord direction** = local X in cross-section plane
- **Thickness direction** = local Z in cross-section plane
- **Full propeller** = blade1 + blade2(180° around Y) + hub(Y-axis cylinder)

## PE0 File Structure
Space-delimited text. Column mapping:

| Col | PE0 Name | Unit | Description |
|-----|----------|------|-------------|
| 0 | STATION | in | Radial position (0=hub, R=tip) |
| 1 | CHORD | in | Airfoil chord length |
| 2 | PITCH (QUOTED) | deg | Nominal pitch |
| 3 | PITCH (LE-TE) | deg | LE→TE pitch |
| 4 | PITCH (PRATHER) | deg | Prather gage pitch |
| 5 | SWEEP (Y) | in | LE Y offset |
| 6 | RAKE (Z) | in | LE Z offset |
| 7 | THICKNESS RATIO | — | max_thickness / chord |
| 8 | TWIST | deg | **Local blade twist angle** |
| 9 | MAX-THICK | in | Max thickness position |

## Airfoil Reconstruction
PE0 files provide geometric summary only (no raw airfoil coordinates).
Reconstruction uses **NACA 4-digit camber line + thickness formula**:

1. **Camber line**: NACA 4-digit profile
   - `m = tr × (0.04/0.12)` (scaled from NACA 4412)
   - `p = 0.4` (max camber at 40% chord)
2. **Thickness**: NACA 4-digit thickness distribution
   - `yt = 5 × t × c × (0.2969√t - 0.1260t - 0.3516t² + 0.2843t³ - 0.1015t⁴)`
3. **Blade construction**: Root airfoil swept along LE spine path via OCC `BRepOffsetAPI_MakePipe`
4. **Blade 2**: 180° rotation around Y axis
5. **Hub**: Cylinder, diameter = 8% of prop diameter

## Usage

### Generate exact model
```bash
cd /home/bosung/.openclaw/workspace/skills/apc-prop-geom
python3 apc-prop-geom.py --model 10x6
# Output: 10x6.stp (in skills root)
```

### Interpolate between models
```bash
python3 apc-prop-geom.py --inch 12 --pitch 8
# Output: 12.0x8.0.stp
```

### List all available models
```bash
python3 apc-prop-geom.py --list
```

### Custom output name
```bash
python3 apc-prop-geom.py --model 10x6 --output my_prop.stp
```

## Test Files
Generated test STEP files go in `test/` directory (not skills root).
Example: `test/10x6-reconstructed.stp`

## Dependencies
- **Python 3.12+**
- **OCP (OpenCASCADE)** — OCC Python bindings
