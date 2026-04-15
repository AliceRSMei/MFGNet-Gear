# Point Cloud Sampling

This folder contains the script that samples 3D point clouds 
from gear CAD (.PLY) files using the Open3D library.

## Requirements

```bash
pip install -r requirements.txt
```

**requirements.txt contents:**
open3d==YOUR_VERSION   ← fill in your actual version
numpy>=1.21.0
tqdm>=4.62.0

Find your Open3D version: `python -c "import open3d; print(open3d.__version__)"`

## Usage

```bash
python sample_point_cloud.py \
  --input_dir /path/to/ply_files \
  --output_dir /path/to/txt_output \
  --n_points 100000
```

**Arguments:**

| Argument | Default | Description |
|---|---|---|
| `--input_dir` | required | Directory containing .PLY files |
| `--output_dir` | required | Where to save .txt point cloud files |
| `--n_points` | 100000 | Number of points to sample per part |

## Output Format

Each output `.txt` file contains one point per line with three 
space-separated columns:
x y z
-12.3451 4.8823 0.1204
...

No header row. Units are millimeters.

## Sampling Method

Points are sampled **uniformly across the surface area** of each mesh 
using Open3D's `sample_points_uniformly()` function. This ensures 
consistent point density regardless of local surface curvature.

## Example

```python
import open3d as o3d

mesh = o3d.io.read_triangle_mesh("T20ID15_G0_0001.PLY")
pcd = mesh.sample_points_uniformly(number_of_points=100000)
o3d.io.write_point_cloud("T20ID15_G0_0001.txt", pcd)
```