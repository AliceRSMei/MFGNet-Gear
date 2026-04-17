# MFGNet-Gear: A 3D Point Cloud Dataset for Geometric Defect Detection in Gears

[![DOI](https://zenodo.org/badge/DOI/YOUR_ZENODO_DOI.svg)](https://doi.org/YOUR_ZENODO_DOI)
[![Dataset](https://img.shields.io/badge/Dataset-IEEE%20DataPort-blue)](YOUR_DATAPORT_URL)
[![HuggingFace](https://img.shields.io/badge/Dataset-HuggingFace-yellow)](https://huggingface.co/datasets/YOUR_HF_REPO)
[![Paper](https://img.shields.io/badge/Paper-Manufacturing%20Letters%202024-green)](https://doi.org/10.1016/j.mfglet.2024.09.159)

This repository contains the data generation code and metadata for **MFGNet-Gear**,
a synthetic 3D benchmark dataset for geometric defect detection in gears. 

The dataset is released in two formats: polygon mesh (`.ply`) and 3D point cloud (`.txt`).

## Dataset Overview

| Property             | Value                                      |
|----------------------|--------------------------------------------|
| Total parts          | 24,000                                     |
| Gear designs         | 12 (T20–T40 series)                        |
| Quality classes      | 4 (G0, P0, W0, R0)                         |
| Parts per class      | 500                                        |
| Points per part      | 100,000                                    |
| Mesh format          | `.ply` (polygon mesh)                      |
| Point cloud format   | `.txt` (x y z, comma-separated)            |
| Point cloud size     | ~168 GB                                    |

**Quality classes:**
| Label | Class | Description |
|---|---|---|
| `G0` | Good / nominal | No defect |
| `P0` | Pitting | Surface fatigue damage |
| `W0` | Tooth wear | Material loss due to friction |
| `R0` | Root breakage | Fracture at tooth root |

**Gear designs** span three tooth counts (20, 30, 40) and four inner diameters each.
Full design parameters are in `metadata/gear_basemodels.xlsx`.

## Dataset Access

| Location | Contents |
|---|---|
| [IEEE DataPort](YOUR_DATAPORT_URL) | Sample subset — T20ID15, all 4 classes, both formats |
| [HuggingFace](YOUR_HF_URL) | Full dataset — all 24,000 parts, both formats |

## File Naming Convention

All files follow the pattern `{DesignID}{QualityClass}_{#####}.{ext}`:
```
T20ID10G0_00001.ply   → design T20ID10, good part, index 1, mesh
T20ID10G0_00001.txt   → same part, point cloud format
T30ID30R0_00412.txt   → design T30ID30, root breakage, index 412
```


## Repository Structure

```
mfgnet-gear/
data_generation/
solidworks/     ← SolidWorks master part, design tables, macro
sampling/       ← Open3D point cloud sampling script
metadata/       ← Design parameters, defect params, train/val/test splits
```


## Quick Start

**Step 1 — Generate mesh files (requires SolidWorks 2021)**

See `data_generation/solidworks/README.md`.

**Step 2 — Sample point clouds from meshes**

```bash
pip install -r data_generation/sampling/requirements.txt

python data_generation/sampling/sample_point_cloud.py \
    --input_dir /path/to/ply_files \
    --output_dir /path/to/txt_output \
    --n_points 100000
```

**Step 3 — Download the dataset**

```python
# Full dataset via HuggingFace
from huggingface_hub import snapshot_download
snapshot_download(repo_id="YOUR_HF_REPO", repo_type="dataset")
```

## Citation

If you use MFGNet-Gear, please cite both the dataset descriptor and the original paper:

```bibtex
@article{mei2024deep,
  title={Deep learning of 3D point clouds for detecting geometric defects in gears},
  author={Mei, Ruo-Syuan and Conway, Christopher H and Bimrose, Miles V and King, William P and Shao, Chenhui},
  journal={Manufacturing Letters},
  volume={41},
  pages={1324--1333},
  year={2024},
  publisher={Elsevier}
}

More publications coming up...
```

## License

Code in this repository: MIT License. \
Dataset: Creative Commons Attribution 4.0 (CC BY 4.0).

## Contact

Alice Mei 

