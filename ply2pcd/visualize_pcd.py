import open3d as o3d
import numpy as np
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Visualize a comma-delimited TXT point cloud file."
    )
    parser.add_argument(
        "filepath",
        type=str,
        help="Path to the .txt point cloud file (x,y,z per line)"
    )
    args = parser.parse_args()

    path = Path(args.filepath)
    if not path.exists():
        print(f"[ERROR] File not found: {path}")
        return

    points = np.loadtxt(str(path), delimiter=",")
    if points.ndim == 1:
        points = points.reshape(1, -1)
    if points.shape[1] < 3:
        print(f"[ERROR] Expected at least 3 columns (x,y,z), got {points.shape[1]}")
        return

    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points[:, :3])

    print(f"Loaded {len(pcd.points)} points from '{path.name}'")
    o3d.visualization.draw_geometries(
        [pcd],
        window_name=path.stem,
        width=1024,
        height=768,
    )


if __name__ == "__main__":
    main()
