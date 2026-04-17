# SolidWorks Gear Generation

This folder contains the master part file, design tables, and macro
used to generate gear CAD models in SolidWorks 2021.

## Requirements

- SolidWorks 2021 (other versions may work but are untested)
- Basic familiarity with SolidWorks design tables and macros

## Files

| File | Description |
|---|---|
| `master_gear.sldprt` | Master gear part file — base geometry driven by design table |
| `design_tables/G0_standard.xlsx` | Parameters for 500 standard gears (no defect) |
| `design_tables/P0_pitting.xlsx` | Parameters for 500 pitting defect gears |
| `design_tables/W0_wear.xlsx` | Parameters for 500 tooth wear defect gears |
| `design_tables/R0_breakage.xlsx` | Parameters for 500 root breakage defect gears |
| `macros/batch_export.swp` | SolidWorks macro for batch `.ply` export |

## Step-by-Step Instructions

**For each quality class (repeat 4 times):**

1. Open `master_gear.sldprt` in SolidWorks 2021
2. Go to **Insert → Tables → Design Table → From File**
3. Select the appropriate `.xlsx` file for the quality class you want to generate
4. SolidWorks will create one configuration per row in the table
5. Go to **Tools → Macros → Run** and select `macros/batch_export.swp`
6. When prompted, enter:
   - **Input path**: directory of the open part file
   - **Output path**: directory where `.ply` files will be saved
7. The macro will iterate through all configurations and save each as
   `{DesignID}{QualityClass}_{NNNNN}.ply`

Repeat for all four design tables to generate the full mesh dataset.

## Design Parameters

| Parameter | Symbol | Unit | Description |
|---|---|---|---|
| Outside Diameter | OD | mm | Outer gear diameter |
| Base Circle | BC | mm | Base circle diameter |
| Pitch Circle Diameter | PCD | mm | Pitch circle diameter |
| Mirror Distance | MD | mm | Mirror distance |
| Involute Gap | IG | mm | Gap between involute profiles |
| Dedendum | Den. | mm | Dedendum circle diameter |
| Number of Teeth | NTeeth | — | Tooth count (20, 30, or 40) |
| Inner Diameter | ID | mm | Central bore diameter |

Full parameter values for all 12 designs are in `metadata/design_table.csv`.

## Manufacturing Variability

Each design parameter includes ±0.0254 mm variability drawn uniformly
at random across 500 parts per class, simulating real manufacturing tolerances.
This variability is encoded directly in the `.xlsx` design tables.

## Defect Parameters

Three additional parameter sets control defect geometry.
See `metadata/defect_parameters.csv` for all ranges and distributions.

| Defect | Key parameters |
|---|---|
| Pitting (P0) | `dentR`, `pittingR`, `pittingAngle`, `pittingDist` |
| Tooth wear (W0) | `ToothLossDist` |
| Root breakage (R0) | `ToothDepth`, `ToothDist1`, `ToothDist2`, `ToothTail`, `ToothWidth` |

## Output

Each run produces `.ply` polygon mesh files saved as:
`{DesignID}{QualityClass}_{NNNNN}.ply`

Example: `T20ID15P0_00001.ply` through `T20ID15P0_00500.ply`