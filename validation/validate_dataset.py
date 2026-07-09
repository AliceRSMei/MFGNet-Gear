"""
MFGNet-Gear dataset validation.

Produces the numbers, tables, and figures for the "Validation and Quality"
section of the IEEE Data Descriptions manuscript. Runs five checks:

  1. Completeness & balance   -> Fig. dataset-file-count (count heatmap)
  2. Point-cloud integrity    -> [XX]% of point clouds pass
  3. Mesh integrity           -> [XX]% of meshes pass (closed, no degenerate faces)
  4. Sampling fidelity        -> surface-to-nearest-point coverage vs spacing
  5. Global feature recovery  -> recovered outer diameter & tooth count vs design table

Outputs (written to --out_dir, default validation/report/):
  report.json              full machine-readable results
  pointcloud_integrity.csv per-file point-cloud results
  mesh_integrity.csv       per-file mesh results
  geometry.csv             per-file sampling-fidelity + feature recovery
  feature_recovery.csv     per-design summary table
  fig-DatasetFileCount.png
  fig-PointToSurface.png
  fig-FeatureRecovery.png

Cheap checks (1, 2, 3) run on ALL files. Expensive geometry checks (4, 5) run
on a stratified subsample per class (--geom_sample, default 25) unless --full-geom.

Usage:
  python validation/validate_dataset.py \
      --mesh_dir  D:/rsmei/MFGNet-Gear_IEEEDataDescriptions/MFGNet-Gear/data/mesh_ply \
      --pcd_dir   D:/rsmei/MFGNet-Gear_IEEEDataDescriptions/MFGNet-Gear/data/pointcloud_txt \
      --design_table cad2ply/gear_basemodels.xlsx
"""

import argparse
import json
import re
import sys
import time
import warnings

warnings.filterwarnings("ignore", message="The binary mode of fromstring")
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

# ----------------------------------------------------------------------------
# Constants describing the intended dataset
# ----------------------------------------------------------------------------
QUALITY_CLASSES = ["G0", "P0", "W0", "R0"]           # good, pitting, wear, root
EXPECTED_PER_FOLDER = 500
EXPECTED_POINTS = 100_000
# 12 designs x 4 classes = 48 subfolders
EXPECTED_FOLDERS = 48

# design token -> (series prefix). Folder names look like T20ID10G0.
NAME_RE = re.compile(r"^(T\d+ID\d+)(G0|P0|W0|R0)$")


# ----------------------------------------------------------------------------
# Design table (ground-truth geometry)
# ----------------------------------------------------------------------------
def load_design_table(xlsx_path):
    """Return {design_token: {"teeth": int, "outer_dia": float, "inner_dia": float}}.

    Reads gear_basemodels.xlsx. Columns of interest:
      GearOverall@Sketch1 -> outer diameter (mm)
      NumTeeth@CirPattern1 -> tooth count
      ID@Sketch5 -> inner diameter (mm)
    Row labels are design tokens like 'T20ID10'.
    """
    import openpyxl

    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    # header row is the one containing 'GearOverall@Sketch1'
    header_idx = None
    for i, row in enumerate(rows):
        if row and any(isinstance(c, str) and "GearOverall" in c for c in row):
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("Could not find header row in design table")
    header = rows[header_idx]

    def col(substr):
        for j, c in enumerate(header):
            if isinstance(c, str) and substr in c:
                return j
        raise ValueError(f"column {substr} not found")

    j_outer = col("GearOverall")
    j_teeth = col("NumTeeth")
    j_id = col("ID@Sketch5")

    table = {}
    for row in rows[header_idx + 1:]:
        label = row[0]
        if not isinstance(label, str):
            continue
        m = re.match(r"^(T\d+ID\d+)$", label.strip())
        if not m:
            continue
        table[m.group(1)] = {
            "teeth": int(row[j_teeth]),
            "outer_dia": float(row[j_outer]),
            "inner_dia": float(row[j_id]),
        }
    return table


# ----------------------------------------------------------------------------
# Fast point-cloud loading & integrity
# ----------------------------------------------------------------------------
def load_pointcloud_fast(path):
    """Load a comma-separated point cloud as an (N, 3) float array.

    Fast path avoids np.loadtxt overhead. Raises ValueError on non-numeric
    content or a row width that is not a multiple of 3.
    """
    with open(path, "rb") as f:
        raw = f.read()
    text = raw.decode("ascii", errors="strict")
    # tokens separated by comma or newline; ignore trailing whitespace/newlines
    flat = np.fromstring(text.replace("\n", ","), sep=",")
    if flat.size % 3 != 0:
        raise ValueError(f"token count {flat.size} not divisible by 3")
    return flat.reshape(-1, 3)


def check_pointcloud(path):
    """Structural integrity of one point cloud. Returns a result dict."""
    res = {
        "file": path.name,
        "n_points": None,
        "shape_ok": False,
        "count_ok": False,
        "finite_ok": False,
        "unique_ok": False,
        "passed": False,
        "error": None,
    }
    try:
        arr = load_pointcloud_fast(path)
        res["n_points"] = int(arr.shape[0])
        res["shape_ok"] = arr.ndim == 2 and arr.shape[1] == 3
        res["count_ok"] = arr.shape[0] == EXPECTED_POINTS
        res["finite_ok"] = bool(np.isfinite(arr).all())
        # duplicate rows (exact)
        res["unique_ok"] = np.unique(arr, axis=0).shape[0] == arr.shape[0]
        res["passed"] = all(
            [res["shape_ok"], res["count_ok"], res["finite_ok"], res["unique_ok"]]
        )
    except Exception as e:  # noqa: BLE001 - want to record any failure
        res["error"] = f"{type(e).__name__}: {e}"
    return res


# ----------------------------------------------------------------------------
# Mesh integrity
# ----------------------------------------------------------------------------
def count_open_edges(faces):
    """Number of open (boundary) edges: edges used by only one triangle.

    A surface with zero open edges is closed (encloses a solid, no holes/gaps).
    Each edge is a sorted (vi, vj) vertex pair; a closed triangulated surface
    shares every edge between exactly two triangles.
    """
    e = np.sort(np.vstack([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [0, 2]]]),
                axis=1)
    _, counts = np.unique(e, axis=0, return_counts=True)
    return int((counts == 1).sum())


def check_mesh(path):
    """Structural integrity of one PLY mesh. Returns a result dict.

    A mesh passes if it loads with faces, is closed (no open/boundary edges),
    and contains no degenerate (zero-area) faces.
    """
    import open3d as o3d

    res = {
        "file": path.name,
        "n_vertices": None,
        "n_faces": None,
        "loads_ok": False,
        "has_faces": False,
        "n_open_edges": None,
        "is_closed": False,            # no boundary edges (no holes/gaps)
        "n_degenerate_faces": None,
        "degenerate_ok": False,
        "passed": False,               # loads + has faces + closed + no degenerate
        "error": None,
    }
    try:
        mesh = o3d.io.read_triangle_mesh(str(path))
        v = np.asarray(mesh.vertices)
        f = np.asarray(mesh.triangles)
        res["n_vertices"] = int(v.shape[0])
        res["n_faces"] = int(f.shape[0])
        res["loads_ok"] = v.shape[0] > 0
        res["has_faces"] = f.shape[0] > 0
        if res["has_faces"]:
            n_open = count_open_edges(f)
            res["n_open_edges"] = n_open
            res["is_closed"] = n_open == 0
            # degenerate = zero-area triangles
            tris = v[f]
            e1 = tris[:, 1] - tris[:, 0]
            e2 = tris[:, 2] - tris[:, 0]
            areas = 0.5 * np.linalg.norm(np.cross(e1, e2), axis=1)
            n_deg = int((areas <= 1e-12).sum())
            res["n_degenerate_faces"] = n_deg
            res["degenerate_ok"] = n_deg == 0
        res["passed"] = all(
            [res["loads_ok"], res["has_faces"], res["is_closed"], res["degenerate_ok"]]
        )
    except Exception as e:  # noqa: BLE001
        res["error"] = f"{type(e).__name__}: {e}"
    return res


# ----------------------------------------------------------------------------
# Sampling fidelity + feature recovery (expensive)
# ----------------------------------------------------------------------------
def recover_tooth_count(points, max_teeth=60, n_bins=1440):
    """Recover tooth count from the angular radial envelope via FFT.

    Gear axis is Z. Teeth create angular periodicity in the outer radius.
    Returns the dominant angular frequency (cycles per revolution).
    """
    r = np.hypot(points[:, 0], points[:, 1])
    th = np.arctan2(points[:, 1], points[:, 0])
    idx = ((th + np.pi) / (2 * np.pi) * n_bins).astype(int) % n_bins
    # max radius per angular bin (radial envelope)
    env = np.full(n_bins, -np.inf)
    np.maximum.at(env, idx, r)
    empty = ~np.isfinite(env)
    if empty.any():
        env[empty] = np.nanmean(env[np.isfinite(env)])
    env = env - env.mean()
    spectrum = np.abs(np.fft.rfft(env))
    freqs = np.fft.rfftfreq(n_bins, d=1.0 / n_bins)  # integer cycles/rev
    band = (freqs >= 1) & (freqs <= max_teeth)
    peak_freq = freqs[band][np.argmax(spectrum[band])]
    return int(round(peak_freq))


def sampling_spacing(area, n=EXPECTED_POINTS):
    """Reference nearest-neighbour spacing for n points uniform on `area` mm^2."""
    return float(np.sqrt(area / n))


def check_geometry(ply_path, txt_path, design_token, design_row,
                   coverage_samples=50_000, source="mesh"):
    """Sampling fidelity + global feature recovery for one part.

    ``source`` selects the mm-scale point cloud used for the geometry claims:
      "mesh" - sample EXPECTED_POINTS points from the mesh (reproduces the
               point_sampling.py pipeline in the mesh's own mm frame). Use this
               to validate the pipeline independently of any post-hoc
               normalization of the released .txt clouds.
      "txt"  - load the released .txt point cloud as-is (only meaningful if the
               released clouds are in mm and aligned to the mesh).
    """
    import open3d as o3d

    res = {
        "file": txt_path.stem,
        "design": design_token,
        "source": source,
        "surface_area_mm2": None,
        "sampling_spacing_mm": None,
        "surf_to_pt_mean_mm": None,     # coverage
        "surf_to_pt_max_mm": None,
        "recovered_outer_dia_mm": None,
        "design_outer_dia_mm": design_row["outer_dia"],
        "outer_dia_abs_err_mm": None,
        "recovered_teeth": None,
        "design_teeth": design_row["teeth"],
        "teeth_match": None,
        "error": None,
    }
    try:
        mesh = o3d.io.read_triangle_mesh(str(ply_path))
        if source == "mesh":
            sampled = mesh.sample_points_uniformly(number_of_points=EXPECTED_POINTS)
            points = np.asarray(sampled.points).astype(np.float64)
        else:
            points = load_pointcloud_fast(txt_path).astype(np.float64)
        area = float(mesh.get_surface_area())
        res["surface_area_mm2"] = area
        res["sampling_spacing_mm"] = sampling_spacing(area)

        # --- sampling coverage: distance from the mesh surface to the nearest
        #     sampled point (does every surface region have a point nearby?) ---
        from scipy.spatial import cKDTree
        cov = mesh.sample_points_uniformly(number_of_points=coverage_samples)
        cov_pts = np.asarray(cov.points)
        kdt = cKDTree(points)
        d_sp, _ = kdt.query(cov_pts, k=1)
        res["surf_to_pt_mean_mm"] = float(d_sp.mean())
        res["surf_to_pt_max_mm"] = float(d_sp.max())

        # --- global features ---
        r = np.hypot(points[:, 0], points[:, 1])
        rec_od = float(2.0 * r.max())
        res["recovered_outer_dia_mm"] = rec_od
        res["outer_dia_abs_err_mm"] = abs(rec_od - design_row["outer_dia"])
        rec_teeth = recover_tooth_count(points)
        res["recovered_teeth"] = rec_teeth
        res["teeth_match"] = rec_teeth == design_row["teeth"]
    except Exception as e:  # noqa: BLE001
        res["error"] = f"{type(e).__name__}: {e}"
    return res


# ----------------------------------------------------------------------------
# Discovery
# ----------------------------------------------------------------------------
def list_class_folders(root):
    return sorted([p for p in Path(root).iterdir() if p.is_dir()])


def files_in(folder, exts):
    exts = {e.lower() for e in exts}
    return sorted([p for p in Path(folder).iterdir()
                   if p.is_file() and p.suffix.lower() in exts])


# ----------------------------------------------------------------------------
# Worker wrappers (module-level for ProcessPoolExecutor picklability)
# ----------------------------------------------------------------------------
def _pc_worker(path_str):
    return check_pointcloud(Path(path_str))


def _mesh_worker(path_str):
    return check_mesh(Path(path_str))


def _geom_worker(args):
    ply, txt, token, row, source = args
    return check_geometry(Path(ply), Path(txt), token, row, source=source)


def run_pool(fn, items, workers, label):
    """Map fn over items with a process pool, printing progress."""
    results = []
    n = len(items)
    t0 = time.time()
    if workers <= 1:
        for i, it in enumerate(items, 1):
            results.append(fn(it))
            if i % 200 == 0 or i == n:
                _progress(label, i, n, t0)
        return results
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fn, it): it for it in items}
        for i, fut in enumerate(as_completed(futs), 1):
            results.append(fut.result())
            if i % 200 == 0 or i == n:
                _progress(label, i, n, t0)
    return results


def _progress(label, i, n, t0):
    dt = time.time() - t0
    rate = i / dt if dt > 0 else 0
    eta = (n - i) / rate if rate > 0 else 0
    sys.stdout.write(f"\r  {label}: {i}/{n}  ({rate:.0f}/s, ETA {eta:.0f}s)   ")
    sys.stdout.flush()
    if i == n:
        sys.stdout.write("\n")


# ----------------------------------------------------------------------------
# CSV writing (no pandas dependency)
# ----------------------------------------------------------------------------
def write_csv(path, rows):
    import csv
    if not rows:
        Path(path).write_text("")
        return
    keys = list(rows[0].keys())
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mesh_dir", default="data/mesh_ply")
    ap.add_argument("--pcd_dir", default="data/pointcloud_txt")
    ap.add_argument("--design_table", default="cad2ply/gear_basemodels.xlsx")
    ap.add_argument("--out_dir", default="validation/report")
    ap.add_argument("--geom_sample", type=int, default=25,
                    help="per-class subsample size for expensive geometry checks")
    ap.add_argument("--full-geom", action="store_true",
                    help="run geometry checks on ALL files (slow)")
    ap.add_argument("--geom-source", choices=["mesh", "txt"], default="mesh",
                    help="mm-scale cloud for geometry: 'mesh' samples the PLY "
                         "(pipeline, mm frame); 'txt' uses the released .txt as-is")
    ap.add_argument("--workers", type=int, default=1,
                    help="parallel worker processes for cheap checks")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--skip-mesh", action="store_true")
    ap.add_argument("--skip-pointcloud", action="store_true")
    ap.add_argument("--skip-geometry", action="store_true")
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    design_table = load_design_table(args.design_table)
    print(f"Design table: {len(design_table)} designs loaded")

    # merge into an existing report so checks can be re-run independently
    report_path = out / "report.json"
    report = {}
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text())
            print(f"  (merging into existing {report_path.name})")
        except Exception:
            report = {}
    report["config"] = vars(args)

    # ---------------- Check 1: completeness & balance ----------------
    print("\n[1/5] Completeness & balance")
    mesh_folders = list_class_folders(args.mesh_dir)
    pcd_folders = list_class_folders(args.pcd_dir)
    mesh_names = {p.name for p in mesh_folders}
    pcd_names = {p.name for p in pcd_folders}

    counts = {}          # folder -> {"mesh": n, "pcd": n, "stem_match": bool}
    stem_mismatches = []
    for name in sorted(mesh_names | pcd_names):
        mfiles = files_in(Path(args.mesh_dir) / name, [".ply"]) if name in mesh_names else []
        pfiles = files_in(Path(args.pcd_dir) / name, [".txt"]) if name in pcd_names else []
        mstems = {p.stem for p in mfiles}
        pstems = {p.stem for p in pfiles}
        match = mstems == pstems
        counts[name] = {"mesh": len(mfiles), "pcd": len(pfiles), "stem_match": match}
        if not match:
            stem_mismatches.append({
                "folder": name,
                "mesh_only": sorted(mstems - pstems)[:10],
                "pcd_only": sorted(pstems - mstems)[:10],
            })

    all_500 = all(c["mesh"] == EXPECTED_PER_FOLDER and c["pcd"] == EXPECTED_PER_FOLDER
                  for c in counts.values())
    report["completeness"] = {
        "n_folders": len(counts),
        "expected_folders": EXPECTED_FOLDERS,
        "all_folders_500": all_500,
        "total_mesh": sum(c["mesh"] for c in counts.values()),
        "total_pcd": sum(c["pcd"] for c in counts.values()),
        "folders_missing_mesh": sorted(pcd_names - mesh_names),
        "folders_missing_pcd": sorted(mesh_names - pcd_names),
        "stem_mismatches": stem_mismatches,
        "counts": counts,
    }
    print(f"  folders: {len(counts)} (expected {EXPECTED_FOLDERS})")
    print(f"  total mesh files: {report['completeness']['total_mesh']}, "
          f"pcd files: {report['completeness']['total_pcd']}")
    print(f"  all folders have exactly {EXPECTED_PER_FOLDER}: {all_500}")
    print(f"  stem mismatches: {len(stem_mismatches)}")
    make_count_figure(counts, out, design_table)

    # collect the master file list (folders that exist in both)
    common = sorted(mesh_names & pcd_names)

    # ---------------- Check 2: point-cloud integrity ----------------
    if not args.skip_pointcloud:
        print("\n[2/5] Point-cloud integrity (all files)")
        pcd_files = []
        for name in common:
            pcd_files += [str(p) for p in files_in(Path(args.pcd_dir) / name, [".txt"])]
        pc_results = run_pool(_pc_worker, pcd_files, args.workers, "pointclouds")
        n_pass = sum(r["passed"] for r in pc_results)
        report["pointcloud_integrity"] = summarize_pass(pc_results, n_pass)
        report["pointcloud_integrity"]["breakdown"] = {
            k: int(sum(r.get(k) is True for r in pc_results))
            for k in ["shape_ok", "count_ok", "finite_ok", "unique_ok"]
        }
        write_csv(out / "pointcloud_integrity.csv", pc_results)
        print(f"  passed: {n_pass}/{len(pc_results)} "
              f"({100*n_pass/len(pc_results):.3f}%)")

    # ---------------- Check 3: mesh integrity ----------------
    if not args.skip_mesh:
        print("\n[3/5] Mesh integrity (all files)")
        mesh_files = []
        for name in common:
            mesh_files += [str(p) for p in files_in(Path(args.mesh_dir) / name, [".ply"])]
        mesh_results = run_pool(_mesh_worker, mesh_files, args.workers, "meshes")
        n_pass = sum(r["passed"] for r in mesh_results)
        report["mesh_integrity"] = summarize_pass(mesh_results, n_pass)
        report["mesh_integrity"]["breakdown"] = {
            k: int(sum(r.get(k) is True for r in mesh_results))
            for k in ["loads_ok", "has_faces", "is_closed", "degenerate_ok"]
        }
        write_csv(out / "mesh_integrity.csv", mesh_results)
        print(f"  passed (loads+faces+closed+no-degenerate): "
              f"{n_pass}/{len(mesh_results)} ({100*n_pass/len(mesh_results):.3f}%)")
        for k, v in report["mesh_integrity"]["breakdown"].items():
            print(f"    {k}: {v}/{len(mesh_results)} "
                  f"({100*v/len(mesh_results):.2f}%)")

    # ---------------- Checks 4 & 5: geometry ----------------
    if not args.skip_geometry:
        print("\n[4-5/5] Sampling fidelity + feature recovery")
        geom_items = []
        for name in common:
            m = NAME_RE.match(name)
            token = m.group(1) if m else name
            row = design_table.get(token)
            if row is None:
                continue
            pfiles = files_in(Path(args.pcd_dir) / name, [".txt"])
            if args.full_geom or len(pfiles) <= args.geom_sample:
                chosen = pfiles
            else:
                idx = rng.choice(len(pfiles), size=args.geom_sample, replace=False)
                chosen = [pfiles[i] for i in sorted(idx)]
            for pf in chosen:
                ply = Path(args.mesh_dir) / name / (pf.stem + ".PLY")
                if not ply.exists():
                    ply = Path(args.mesh_dir) / name / (pf.stem + ".ply")
                geom_items.append((str(ply), str(pf), token, row, args.geom_source))
        print(f"  geometry parts: {len(geom_items)} "
              f"({'full' if args.full_geom else str(args.geom_sample)+'/class'}), "
              f"source={args.geom_source}")
        geom_results = run_pool(_geom_worker, geom_items, args.workers, "geometry")
        geom_ok = [r for r in geom_results if r["error"] is None]
        write_csv(out / "geometry.csv", geom_results)
        report["geometry"] = summarize_geometry(geom_ok, design_table)
        gr = report["geometry"]
        print(f"  coverage (surface->nearest point) mean: {gr['surf_to_pt_mean_mm']:.4g} mm "
              f"(max {gr['surf_to_pt_max_mm']:.4g})")
        print(f"  mean sampling spacing: {gr['sampling_spacing_mm']:.4g} mm")
        print(f"  outer-dia mean abs err: {gr['outer_dia_abs_err_mm']:.4g} mm")
        print(f"  tooth-count match: {gr['teeth_match_frac']*100:.2f}% "
              f"({gr['n_designs_all_match']}/{gr['n_designs']} designs 100% match)")
        make_feature_figure(geom_ok, out)
        make_distance_figure(geom_ok, out)
        write_feature_recovery_csv(geom_ok, design_table, out)

    # ---------------- write report ----------------
    with open(out / "report.json", "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nDone. Report written to {out.resolve()}")


def summarize_pass(results, n_pass):
    n = len(results)
    errs = [r for r in results if r.get("error")]
    return {
        "n_total": n,
        "n_passed": int(n_pass),
        "pass_pct": round(100 * n_pass / n, 4) if n else None,
        "n_errors": len(errs),
        "example_errors": [{"file": e["file"], "error": e["error"]} for e in errs[:10]],
    }


def summarize_geometry(rows, design_table):
    if not rows:
        return {"n_parts": 0, "note": "no geometry parts succeeded"}

    def arr(key):
        return np.array([r[key] for r in rows if r[key] is not None], dtype=float)

    d_sp = arr("surf_to_pt_mean_mm")
    d_sp_max = arr("surf_to_pt_max_mm")
    spacing = arr("sampling_spacing_mm")
    od_err = arr("outer_dia_abs_err_mm")
    teeth_match = np.array([bool(r["teeth_match"]) for r in rows])

    # per-design all-match for tooth count & OD
    by_design = defaultdict(list)
    for r in rows:
        by_design[r["design"]].append(r)
    n_all_match = sum(
        all(x["teeth_match"] for x in rs) for rs in by_design.values()
    )
    return {
        "n_parts": len(rows),
        "n_designs": len(by_design),
        "surf_to_pt_mean_mm": float(d_sp.mean()),
        "surf_to_pt_max_mm": float(d_sp_max.max()),
        "sampling_spacing_mm": float(spacing.mean()),
        "outer_dia_abs_err_mm": float(od_err.mean()),
        "outer_dia_max_abs_err_mm": float(od_err.max()),
        "teeth_match_frac": float(teeth_match.mean()),
        "n_designs_all_match": int(n_all_match),
    }


def write_feature_recovery_csv(rows, design_table, out):
    by_design = defaultdict(list)
    for r in rows:
        by_design[r["design"]].append(r)
    summary = []
    for token in sorted(by_design):
        rs = by_design[token]
        ods = np.array([r["recovered_outer_dia_mm"] for r in rs])
        teeth = np.array([r["recovered_teeth"] for r in rs])
        dr = design_table[token]
        summary.append({
            "design": token,
            "design_teeth": dr["teeth"],
            "recovered_teeth_mode": int(np.bincount(teeth).argmax()),
            "teeth_match_pct": round(100 * np.mean(teeth == dr["teeth"]), 2),
            "design_outer_dia_mm": dr["outer_dia"],
            "recovered_outer_dia_mean_mm": round(float(ods.mean()), 4),
            "outer_dia_abs_err_mm": round(abs(float(ods.mean()) - dr["outer_dia"]), 4),
            "n_parts": len(rs),
        })
    write_csv(out / "feature_recovery.csv", summary)


# ----------------------------------------------------------------------------
# Figures
# ----------------------------------------------------------------------------
# Publication figure style: Arial, 300 dpi, compact IEEE-column sizing.
COL = 3.5      # single-column width (in)
WIDE = 7.16    # double-column width (in)
GREEN = "#1F7A4D"


def apply_style():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
        "font.size": 7,
        "axes.titlesize": 9,
        "axes.labelsize": 8,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "legend.fontsize": 6.5,
        "axes.linewidth": 0.6,
        "xtick.major.width": 0.5,
        "ytick.major.width": 0.5,
        "lines.linewidth": 1.0,
        "lines.markersize": 3.5,
        "figure.dpi": 300,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.02,
    })


def save_png(fig, path_noext):
    """Save a 300-dpi PNG (only) for `path_noext` (no extension)."""
    fig.savefig(str(path_noext) + ".png", dpi=300)


def make_count_figure(counts, out, design_table):
    apply_style()
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    designs = sorted(design_table.keys(),
                     key=lambda t: (int(re.search(r"T(\d+)", t).group(1)),
                                    int(re.search(r"ID(\d+)", t).group(1))))

    def grid_for(key):
        g = np.zeros((len(designs), len(QUALITY_CLASSES)), dtype=int)
        for i, d in enumerate(designs):
            for j, c in enumerate(QUALITY_CLASSES):
                g[i, j] = counts.get(d + c, {}).get(key, 0)
        return g

    panels = [(grid_for("mesh"), "Mesh", "(a)"),
              (grid_for("pcd"), "3D point clouds", "(b)")]
    nrow, ncol = len(designs), len(QUALITY_CLASSES)

    fig, axes = plt.subplots(1, 2, figsize=(WIDE, 6.6))
    for ax, (grid, title, tag) in zip(axes, panels):
        for i in range(nrow):
            for j in range(ncol):
                ax.add_patch(Rectangle((j + 0.02, i + 0.02), 0.96, 0.96,
                                       facecolor=GREEN, edgecolor="none"))
                ax.text(j + 0.5, i + 0.5, str(grid[i, j]), ha="center",
                        va="center", color="white", fontsize=10)
        ax.set_xlim(0, ncol)
        ax.set_ylim(0, nrow)
        ax.invert_yaxis()
        ax.set_aspect("equal")
        ax.set_xticks(np.arange(ncol) + 0.5)
        ax.set_xticklabels(QUALITY_CLASSES, fontsize=12)
        ax.set_yticks(np.arange(nrow) + 0.5)
        ax.set_yticklabels(designs, fontsize=12)
        ax.set_xlabel("Quality class", fontsize=14)
        ax.set_ylabel("Design ID", fontsize=14)
        ax.set_title(title, pad=10, fontsize=15)
        ax.tick_params(length=0)
        for s in ax.spines.values():
            s.set_visible(False)
        ax.text(-0.32, 1.0, tag, transform=ax.transAxes, fontsize=14,
                va="bottom", ha="left")
    fig.tight_layout()
    save_png(fig, out / "fig-DatasetFileCount")
    plt.close(fig)


def make_distance_figure(rows, out):
    apply_style()
    import matplotlib.pyplot as plt

    d_sp = np.array([r["surf_to_pt_mean_mm"] for r in rows if r["surf_to_pt_mean_mm"]])
    spacing = np.array([r["sampling_spacing_mm"] for r in rows if r["sampling_spacing_mm"]])
    fig, ax = plt.subplots(figsize=(COL, 2.2))
    ax.hist(d_sp, bins=40, alpha=0.85, color=GREEN, edgecolor="none")
    ax.axvline(spacing.mean(), color="crimson", ls="--", lw=1.0,
               label=f"Sampling spacing = {spacing.mean():.3f} mm")
    ax.set_xlabel("Surface-to-point distance (mm)")
    ax.set_ylabel("Parts")
    ax.legend()
    fig.tight_layout()
    save_png(fig, out / "fig-PointToSurface")
    plt.close(fig)


def make_feature_figure(rows, out):
    apply_style()
    import matplotlib.pyplot as plt

    by_design = defaultdict(list)
    for r in rows:
        by_design[r["design"]].append(r)
    designs = sorted(by_design,
                     key=lambda t: (int(re.search(r"T(\d+)", t).group(1)),
                                    int(re.search(r"ID(\d+)", t).group(1))))
    rec = [np.mean([x["recovered_outer_dia_mm"] for x in by_design[d]]) for d in designs]
    des = [by_design[d][0]["design_outer_dia_mm"] for d in designs]

    fig, ax = plt.subplots(figsize=(COL, 2.3))
    x = np.arange(len(designs))
    ax.plot(x, des, "s-", label="Design", ms=4, color="0.3")
    ax.plot(x, rec, "o--", label="Recovered", ms=3, color="crimson")
    ax.set_xticks(x)
    ax.set_xticklabels(designs, rotation=90)
    ax.set_xlabel("Gear design")
    ax.set_ylabel("Outer diameter (mm)")
    ax.set_ylim(50, 110)
    ax.legend()
    fig.tight_layout()
    save_png(fig, out / "fig-FeatureRecovery")
    plt.close(fig)


if __name__ == "__main__":
    main()
