# Dataset validation

`validate_dataset.py` verifies the completeness, structural integrity, and
geometric fidelity of MFGNet-Gear, and produces the numbers and figures for the
**Validation and Quality** section of the data descriptor.

## What it checks

| # | Check | Reported quantity | Scope |
|---|---|---|---|
| 1 | Completeness & balance — 48 design-class folders, 500 files each, matching mesh/point-cloud stems | file-count figure | all 24,000 |
| 2 | Point-cloud integrity — loads as `N×3`, exactly 100,000 finite rows, no duplicate or non-numeric values | % passed | all 24,000 |
| 3 | Mesh integrity — valid PLY, closed surface (no boundary edges), no degenerate (zero-area) faces | % passed | all 24,000 |
| 4 | Sampling fidelity — mean surface→point coverage distance vs. reference spacing √(area/N) | mm | subsample |
| 5 | Global feature recovery — outer diameter (2·max radius) and tooth count (angular-envelope FFT) vs. design table | per-design | subsample |

All five checks run on all 24,000 files with `--full-geom`. The geometry checks
(4–5) sample the mm-scale point cloud from each mesh (`--geom-source mesh`,
matching `ply2pcd/point_sampling.py`), since the released `.txt` point clouds are
normalized to the unit sphere. Without `--full-geom`, checks 4–5 use a stratified
subsample per class (`--geom_sample`, default 25) for a fast preview.

## Run

```bash
pip install -r validation/requirements-validation.txt

python validation/validate_dataset.py \
    --mesh_dir  /path/to/data/mesh_ply \
    --pcd_dir   /path/to/data/pointcloud_txt \
    --design_table cad2ply/gear_basemodels.xlsx \
    --out_dir   validation/report \
    --full-geom --workers 12
```

## Outputs (in `--out_dir`)

Committed (small, human-readable):

- `report.json` — machine-readable summary of all checks
- `feature_recovery.csv` — per-design outer-diameter / tooth-count table
- `fig-DatasetFileCount.png`, `fig-FeatureRecovery.png`, `fig-PointToSurface.png`
  — 300-dpi PNG figures (Arial)

Regenerated on each run and git-ignored (large per-file logs):

- `pointcloud_integrity.csv`, `mesh_integrity.csv`, `geometry.csv`

## Morphology reconstruction (Fig. 7)

`reconstruct_gear.py` walks one instance through the released pipeline and shows that
point sampling preserves the part morphology:

1. the original PLY mesh (physical mm geometry),
2. a point cloud sampled from it with the released routine (`ply2pcd/point_sampling.py`),
3. a surface reconstructed (Poisson) from those points, and
4. the reconstructed and source meshes overlaid.

It is an interactive viewer with screenshot export, and produces the panels for **Fig. 7**
of the data descriptor (design T30ID40 across the good, pitting, tooth-wear, and root-breakage
classes).

```bash
python validation/reconstruct_gear.py --design T30ID40 --quality P0 --instance 1 \
    --num_points 100000 \
    --data /path/to/data \
    --out  validation/figs_interactive
```

## Note on the sampling-fidelity metric

Because each point cloud is sampled *from* its mesh, the point-to-surface
distance is ~0 by construction. The reported quantity is the complementary
**surface→point coverage** — the mean distance from the mesh surface to the
nearest sampled point — compared against the reference sampling spacing
√(area/N). Coverage below the spacing confirms the 100,000-point sampling
covers the surface uniformly.
