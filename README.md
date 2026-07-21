# MFGNet-Gear: A Synthetic 3D Gear Dataset for Manufacturing Quality Inspection
[![Dataset](https://img.shields.io/badge/Dataset-Deep%20Blue%20Data%202026-blue)](https://doi.org/10.7302/qrdj-n812)
[![HuggingFace](https://img.shields.io/badge/🤗%20HuggingFace-MFGNet--Gear-yellow)](https://huggingface.co/datasets/rsmei/MFGNet-Gear)
[![Paper](https://img.shields.io/badge/Paper-Manufacturing%20Letters%202024-green)](https://doi.org/10.1016/j.mfglet.2024.09.159)

This repository contains the data generation, sampling, and quality-validation
code for **MFGNet-Gear**, a synthetic 3D benchmark dataset for geometric defect
detection in gears.

The dataset is released in two formats: polygon mesh (`.ply`) and 3D point cloud (`.txt`).

## Dataset Overview

| Property             | Value                                      |
|----------------------|--------------------------------------------|
| Total parts          | 24,000                                     |
| Gear designs         | 12 (T20–T40 series)                        |
| Quality classes      | 4 (G0, P0, W0, R0)                         |
| Parts per design-quality class        | 500                                        |
| Points per part      | 100,000                                    |
| Mesh format          | `.ply` (polygon mesh)                      |
| Point cloud format   | `.txt` (x,y,z comma-separated)             |
| Dataset size         | ~11 GB for mesh, ~30 GB for point cloud    |

**Quality classes:**
| Label | Class | Description |
|---|---|---|
| `G0` | Good / nominal | No defect |
| `P0` | Pitting | Surface fatigue damage |
| `W0` | Tooth wear | Material loss due to friction |
| `R0` | Root breakage | Fracture at tooth root |

**Gear designs** span three tooth counts (20, 30, 40) and four inner diameters each.
Full design parameters are in `cad2ply/gear_basemodels.xlsx`.

## Dataset Access

| Location | Contents |
|---|---|
| [Deep Blue Data](https://doi.org/10.7302/qrdj-n812) | Full dataset — all 24,000 parts, both formats (`.ply` and `.txt`) |
| [HuggingFace](https://huggingface.co/datasets/rsmei/MFGNet-Gear) | Mesh files only (`.ply`) — point clouds available on Deep Blue Data |

## File Naming Convention

All files follow the pattern `T{NumberOfTeeth}ID{InnerDiameter}{QualityClass}_{#####}.{ext}`:
```
T20ID10G0_00001.ply   → design T20ID10, good part, index 1, mesh
T20ID10G0_00001.txt   → same part, point cloud format
T30ID30R0_00412.txt   → design T30ID30, tooth root breakage, index 412
```

## Repository Structure

```
mfgnet-gear/
├── cad2ply/          ← SolidWorks master parts, design tables, export macro
├── ply2pcd/          ← Point cloud sampling and visualization scripts
├── validation/       ← Dataset quality-validation script, report, and figures
├── requirements.txt
└── LICENSE
```

## Quick Start

### Step 1 — Generate mesh files (SolidWorks)

Before running the macro, open `cad2ply/saveply.swp` in SolidWorks (**Tools → Macros → Edit**) and replace the two placeholders:

| Placeholder | What to put |
|---|---|
| `<OUTPUT_DIRECTORY>` | Full path to the folder where `.ply` files should be saved (e.g. `C:\data\ply\T20ID10G0`) |
| `<PART_FILE_NAME>` | Name of the open `.SLDPRT` file without extension (e.g. `T20ID10G0`) |

Then:

1. Open a master part file (e.g. `cad2ply/T20ID10G0.SLDPRT`) in SolidWorks
2. Go to **Insert → Tables → Excel Design Table → From File** and select the matching `.xlsx`
3. Go to **Tools → Macros → Run** and select `cad2ply/saveply.swp`
4. Repeat for all four quality classes and all gear designs

### Step 2 — Sample point clouds from meshes

```bash
pip install -r requirements.txt

python ply2pcd/point_sampling.py \
    --input_dir  data/ply \
    --output_dir data/pcd \
    --num_points 100000
```

### Step 3 — Visualize a point cloud

```bash
python ply2pcd/visualize_pcd.py data/pcd/T20ID10G0/T20ID10G0_00001.txt
```

### Step 4 — Validate the dataset (optional)

Verify completeness/class balance, per-file structural integrity, sampling
coverage, and geometric accuracy against the design table:

```bash
pip install -r validation/requirements-validation.txt

python validation/validate_dataset.py \
    --mesh_dir  data/mesh_ply \
    --pcd_dir   data/pointcloud_txt \
    --design_table cad2ply/gear_basemodels.xlsx \
    --out_dir   validation/report \
    --full-geom --workers 12
```

Results (a JSON summary, a per-design table, and figures) are written to
`validation/report/`. See [`validation/README.md`](validation/README.md) for details.

## Citation

If you use MFGNet-Gear, please cite:

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
```

```bibtex
@misc{mei2026synthetic3dgeardataset,
      title={A Synthetic 3D Gear Dataset for Manufacturing Quality Inspection (MFGNet-Gear)}, 
      author={Ruo-Syuan Mei and Chenhui Shao},
      year={2026},
      eprint={2607.16288},
      archivePrefix={arXiv},
      primaryClass={cs.CV},
      url={https://arxiv.org/abs/2607.16288}, 
}
```


## License

Code in this repository: MIT License.\
Dataset: Creative Commons Attribution 4.0 (CC BY 4.0).

## Contact

Alice Mei — [github.com/AliceRSMei](https://github.com/AliceRSMei)
