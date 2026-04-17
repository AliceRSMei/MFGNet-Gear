# Point Cloud Sampling

Samples 3D point clouds uniformly from gear mesh files (`.ply`)
and saves them as space-separated coordinate files (`.txt`).

## Requirements

```bash
pip install -r requirements.txt
```

**`requirements.txt`:**
open3d==YOUR_VERSION
numpy>=1.21.0
tqdm>=4.62.0

Find your Open3D version:
```bash
python -c "import open3d; print(open3d.__version__)"
```

## Usage

```bash
python sample_point_cloud.py \
    --input_dir  /path/to/ply_files  \
    --output_dir /path/to/txt_output \
    --n_points   100000
```

| Argument | Required | Default | Description |
|---|---|---|---|
| `--input_dir` | Yes | — | Directory containing `.ply` mesh files |
| `--output_dir` | Yes | — | Directory to write `.txt` point cloud files |
| `--n_points` | No | 100000 | Number of points sampled per part |

The script preserves file names:
`T20ID15G0_00001.ply` → `T20ID15G0_00001.txt`

## Output Format

Each `.txt` file contains 100,000 lines, one point per line,
with three space-separated floating-point values:
x y z
-12.345100 4.882300 0.120400
-11.998700 5.104200 0.089300
...

No header row. Units are millimeters. No color or normal information is stored.

## Sampling Method

Points are sampled **uniformly by surface area** using Open3D's
`sample_points_uniformly()`. This ensures consistent spatial density
regardless of local mesh curvature — important for defect regions
which tend to have finer mesh geometry.

## Runtime

Approximately 2–4 seconds per part on a modern CPU.
For the full 24,000-part dataset, expect 14–24 hours single-threaded.
Consider parallelizing with Python's `multiprocessing` module for large runs.