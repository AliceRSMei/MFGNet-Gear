import open3d as o3d
import numpy as np
import argparse
import os
from pathlib import Path


def sample_ply_to_txt(ply_path, output_path, num_points):
    mesh = o3d.io.read_triangle_mesh(str(ply_path))
    if not mesh.has_triangles():
        print(f"  [SKIP] No triangles found in {ply_path.name}")
        return

    pcd = mesh.sample_points_uniformly(number_of_points=num_points)

    points = np.asarray(pcd.points)

    lines = []
    for row in points:
        line = ",".join(f"{v:.9f}" for v in row)
        lines.append(line)

    with open(output_path, "w") as f:
        f.write("\n".join(lines))

    print(f"  [SAVED] {output_path.name} ({len(lines)} points)")


def main():
    parser = argparse.ArgumentParser(
        description="Sample points from PLY mesh files and save as comma-delimited TXT point clouds."
    )
    parser.add_argument(
        "--input_dir", "-i",
        type=str,
        default="data/ply",
        help="Input folder containing .ply files (default: data/ply)"
    )
    parser.add_argument(
        "--output_dir", "-o",
        type=str,
        default="data/txt",
        help="Output folder to save .txt point cloud files (default: data/txt)"
    )
    parser.add_argument(
        "--num_points", "-n",
        type=int,
        default=2048,
        help="Number of points to sample from each mesh (default: 2048)"
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    if not input_dir.exists():
        print(f"[ERROR] Input folder does not exist: {input_dir}")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    ply_files = sorted(
        f for f in input_dir.rglob("*")
        if f.suffix.lower() == ".ply" and f.is_file()
    )
    if not ply_files:
        print(f"[WARNING] No .ply files found in {input_dir}")
        return

    print(f"Found {len(ply_files)} PLY file(s) in '{input_dir}'")
    print(f"Sampling {args.num_points} points per mesh")
    print(f"Output folder: '{output_dir}'\n")

    for ply_path in ply_files:
        relative = ply_path.relative_to(input_dir)
        output_path = output_dir / relative.parent / (ply_path.stem + ".txt")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"Processing: {relative}")
        sample_ply_to_txt(ply_path, output_path, args.num_points)

    print("\nDone.")


if __name__ == "__main__":
    main()
