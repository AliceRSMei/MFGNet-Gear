# Dataset validation

Scripts that check the completeness, structural integrity, and geometric quality of
MFGNet-Gear. Results are summarized in the *Validation and Quality* section of the paper.

## What is checked

| # | Check | Reported quantity | Script |
|---|---|---|---|
| 1 | Completeness & balance — 48 design-class folders, 500 files each, matching mesh/point-cloud stems | file counts | `validate_dataset.py` |
| 2 | Point-cloud integrity — loads as `N×3`, exactly 100,000 finite rows, no duplicate or non-numeric values | % passed | `validate_dataset.py` |
| 3 | Mesh integrity — valid PLY, closed surface (no boundary edges), no degenerate (zero-area) faces | % passed | `validate_dataset.py` |
| 4 | Sampling fidelity — mean surface→point coverage distance vs. reference spacing √(area/N) | mm | `validate_dataset.py` |
| 5 | Outer diameter (OD) deviation from the nominal design value, and tooth count | per design | `validate_dataset.py`, `mesh_cloud_agreement.py od` |
| 6 | Mesh–point-cloud agreement — OD of each released point cloud (restored to mm) vs. its mesh; tooth count from the released point clouds | per design | `mesh_cloud_agreement.py od` |
| 7 | Defect agreement — radial material loss (tooth wear), fracture extent (root breakage), pit depth and pit location (pitting) on the mesh vs. the released point cloud | mm | `mesh_cloud_agreement.py defect` |

The OD deviation from nominal includes the intentional dimensional perturbation of each
instance (normal distribution, standard deviation 0.0254/3 mm); it is not a sampling error.

## Run

```bash
pip install -r validation/requirements-validation.txt

# checks 1-5
python validation/validate_dataset.py \
    --mesh_dir  /path/to/data/mesh_ply \
    --pcd_dir   /path/to/data/pointcloud_txt \
    --design_table cad2ply/gear_basemodels.xlsx \
    --out_dir   validation/report \
    --full-geom --workers 12

# checks 5-6 (all 24,000 instances) and check 7 (representative instances)
python validation/mesh_cloud_agreement.py od     --data /path/to/data
python validation/mesh_cloud_agreement.py defect --data /path/to/data
```

`/path/to/data` is the folder that contains `mesh_ply/` and `pointcloud_txt/`.
`validate_dataset.py` samples mm-scale point clouds from each mesh for checks 4–5;
`mesh_cloud_agreement.py` uses the released point clouds, restored to millimeters with
`metadata/normalization_params.csv` (`p_mm = s · p_norm + c`).

### Defect measurements (check 7)

Designs T20ID10, T30ID40, and T40ID60; 10 random instances per defect class (seed 2026). Each
quantity is measured with the same procedure on the mesh and on the point cloud, relative to the
intact geometry of the same instance:

- **Radial material loss** — median tip radius of the intact teeth minus the tip radius of the
  worn tooth.
- **Fracture extent** — maximum span of the fracture region (outer-profile points more than
  0.1 mm from the adjacent intact tooth profile).
- **Pit depth** — maximum depth below the gear face.
- **Pit location** — distance between the mesh and point-cloud centroids of the pit surface
  (surface more than 0.002 mm below the gear face).

Ten good (G0) instances per design are measured as a negative control (apparent material loss).

### Normalization parameters

`metadata/normalization_params.csv` gives, for each point cloud, the centroid `c` of the sampled
points and their farthest-point radius `s`. The values were obtained by registering each released
point cloud to its mesh and can be re-derived with:

```bash
python validation/mesh_cloud_agreement.py normalization --data /path/to/data --out params.csv
```

## Outputs (in `validation/report/`)

Committed (small, human-readable):

- `report.json` — summary of checks 1–5
- `feature_recovery.csv` — per-design OD deviation from nominal (mean absolute and maximum) and
  tooth count, measured on point clouds resampled from each mesh by `validate_dataset.py`
- `mesh_cloud_od_summary.csv` — per-design OD deviation from nominal measured on the mesh
  vertices, mesh–point-cloud OD difference, and tooth count from the released point clouds.
  Its OD deviations agree with `feature_recovery.csv` within 0.0001 mm.
- `defect_agreement.csv` — per-instance defect measurements (check 7)
- `fig-DatasetFileCount.png`, `fig-FeatureRecovery.png`, `fig-PointToSurface.png`

Regenerated on each run and git-ignored (large per-file results):

- `pointcloud_integrity.csv`, `mesh_integrity.csv`, `geometry.csv`, `mesh_cloud_od.csv`

## Morphology reconstruction

`reconstruct_gear.py` walks one instance through the released pipeline and shows that point
sampling preserves the part morphology:

1. the original PLY mesh (physical mm geometry),
2. a point cloud sampled from it with the released routine (`ply2pcd/point_sampling.py`),
3. a surface reconstructed (Poisson) from those points, and
4. the reconstructed and source meshes overlaid.

It is an interactive viewer with screenshot export.

```bash
python validation/reconstruct_gear.py --design T30ID40 --quality P0 --instance 1 \
    --num_points 100000 \
    --data /path/to/data \
    --out  validation/figs_interactive
```

## Note on the sampling-fidelity metric

Because each point cloud is sampled *from* its mesh, the point-to-surface distance is ~0 by
construction. The reported quantity is the complementary **surface→point coverage** — the mean
distance from the mesh surface to the nearest sampled point — compared against the reference
sampling spacing √(area/N). Coverage below the spacing confirms the 100,000-point sampling covers
the surface uniformly.
