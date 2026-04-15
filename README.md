# MFGNet-Gear
A Synthetic 3D Point Cloud Dataset for Geometric Defect Detection in Gears

[![DOI](https://zenodo.org/badge/DOI/YOUR_ZENODO_DOI.svg)](https://doi.org/YOUR_ZENODO_DOI)
[![Dataset on IEEE DataPort](https://img.shields.io/badge/Dataset-IEEE%20DataPort-blue)](https://YOUR_DATAPORT_LINK)
[![Dataset on HuggingFace](https://img.shields.io/badge/Dataset-HuggingFace-yellow)](https://huggingface.co/datasets/YOUR_HF_REPO)

This repository contains the data generation code and metadata for the **MFGNet-Gear** dataset, 
a synthetic 3D point cloud benchmark dataset for geometric defect detection in gears.

## Dataset Overview

| Property | Value |
|---|---|
| Total parts | 24,000 |
| Gear designs | 12 |
| Quality classes | 4 (G0, P0, W0, R0) |
| Points per part | 100,000 |
| Total size | ~168 GB |
| File format | .txt (x, y, z coordinates) |

**Quality classes:**
- `G0` — Standard (no defect)
- `P0` — Pitting
- `W0` — Tooth wear
- `R0` — Tooth root breakage

**Gear designs** vary by tooth count (20, 30, 40) and inner diameter. 
See `metadata/design_table.csv` for full specifications.

## Dataset Access

| Location | Contents | Link |
|---|---|---|
| IEEE DataPort | T20ID15 sample subset (2,000 parts) | YOUR_DATAPORT_LINK |
| HuggingFace | Full dataset (24,000 parts, ~168 GB) | YOUR_HF_LINK |

## Repository Structure
```
mfgnet-gear/
data_generation/
solidworks/       ← Design tables and SolidWorks macros
sampling/         ← Open3D point cloud sampling script
defect_generation/← Defect parameter configuration
metadata/
design_table.csv
defect_parameters_randomized.csv
defect_parameters_fixed.csv
README.md
```

## Quick Start

**1. Generate gear CAD models**
See `data_generation/solidworks/README.md` for instructions on 
running the SolidWorks macro with the design tables.

**2. Sample point clouds from CAD files**
```bash
pip install -r data_generation/sampling/requirements.txt
python data_generation/sampling/sample_point_cloud.py \
  --input_dir /path/to/ply_files \
  --output_dir /path/to/output \
  --n_points 100000
```

**3. Download the dataset**
```python
from huggingface_hub import snapshot_download
snapshot_download(repo_id="YOUR_HF_REPO", repo_type="dataset")
```

## Related Publication

If you use this dataset, please cite:

```bibtex
@article{mei2024mfgnet,
  title={Deep Learning of 3D Point Clouds for Detecting Geometric Defects in Gears},
  author={Mei, Ruo-Syuan and Conway, Christopher H. and Bimrose, Miles V. 
          and King, William P. and Shao, Chenhui},
  journal={Manufacturing Letters},
  volume={41},
  pages={1324--1333},
  year={2024},
  publisher={Elsevier}
}
```

> A dataset descriptor paper is under preparation. 
> Citation will be updated upon publication.
```
```

## License

The code in this repository is licensed under the MIT License.  
The dataset is licensed under CC BY 4.0.

## Contact

Ruo-Syuan Mei — rsmei@umich.edu  
Chenhui Shao — chshao@umich.edu  
Department of Mechanical Engineering, University of Michigan
