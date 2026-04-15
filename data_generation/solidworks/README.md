# SolidWorks Gear Generation

This folder contains the design tables and macros used to generate 
gear CAD models in SolidWorks 2021.

## Requirements

- SolidWorks 2021 (or later)
- Basic familiarity with SolidWorks design tables and macros

## Files

| File | Description |
|---|---|
| `design_table.xlsx` | Gear design parameters for all 12 configurations |
| `defect_table_randomized.xlsx` | Defect parameters drawn from distributions |
| `defect_table_fixed.xlsx` | Fixed defect parameters for T20ID15 |
| `gear_macro.swp` | SolidWorks macro to batch-generate CAD files |

## How to Run

1. Open SolidWorks 2021
2. Open the base gear part file (`.SLDPRT`)
3. Go to **Tools → Macros → Run** and select `gear_macro.swp`
4. When prompted, point the macro to `design_table.xlsx`
5. The macro will iterate through all rows in the design table and 
   save each configuration as a `.PLY` file in your specified output directory

## Design Parameters

| Parameter | Symbol | Unit | Description |
|---|---|---|---|
| Outside Diameter | OD | mm | Outer gear diameter |
| Base Circle | BC | mm | Base circle diameter |
| Pitch Circle Diameter | PCD | mm | Pitch circle diameter |
| Mirror Distance | MD | mm | Mirror distance |
| Involute Gap | IG | mm | Gap between involute profiles |
| Dedendum | Den. | mm | Dedendum circle diameter |
| Number of Teeth | NTeeth | — | Tooth count |
| Inner Diameter | ID | mm | Central bore diameter |

## Manufacturing Variability

A variability of ±0.0254 mm is introduced to each design parameter 
to simulate real-world manufacturing tolerances. This is controlled 
in `design_table.xlsx` — see the `variability` column.

## Output

Each run produces one `.PLY` polygon mesh file per gear configuration,
saved as `{design_name}_{class}_{part_id}.PLY`.
These files are then passed to the sampling script.