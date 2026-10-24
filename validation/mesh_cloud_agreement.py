"""Geometric agreement between the PLY meshes and the released point clouds.

The released point clouds are restored to millimeters with the per-instance parameters in
metadata/normalization_params.csv (p_mm = s * p_norm + c) and compared with their source meshes.

Subcommands
  od             All instances. Outer diameter (OD = 2 x max radius about the gear z-axis) of the
                 mesh and of the restored point cloud, the mesh OD deviation from the nominal OD,
                 and the tooth count recovered from the released point cloud.
  defect         Representative designs (T20ID10, T30ID40, T40ID60), 10 random instances per
                 defect class (seed 2026), plus 10 good (G0) instances per design as a negative
                 control (apparent material loss). The same measurement is applied to the mesh and to the
                 restored point cloud, relative to the intact geometry of the same instance:
                   W0  radial material loss: median tip radius of the intact teeth minus the
                       tip radius of the worn tooth
                   R0  fracture extent: maximum span of the fracture region (outer-profile points
                       more than 0.1 mm from the adjacent intact tooth profile)
                   P0  pit depth: maximum depth below the gear face
                       pit location: distance between the mesh and point-cloud centroids of the
                       pit surface (surface more than 0.002 mm below the gear face)
  normalization  Re-derive the per-instance center c and scale s by registering each normalized
                 point cloud to its source mesh (scale + translation least squares).

Usage:
    python validation/mesh_cloud_agreement.py od     --data /path/to/data
    python validation/mesh_cloud_agreement.py defect --data /path/to/data
    python validation/mesh_cloud_agreement.py normalization --data /path/to/data --out params.csv
"""
import argparse, csv, glob, os, sys, time
from multiprocessing import Pool
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
NORM = os.path.join(HERE, "..", "metadata", "normalization_params.csv")
OUT = os.path.join(HERE, "report")
NOMINAL_OD = {"T20": 55.0, "T30": 80.0, "T40": 105.0}
DEDENDUM = {"T20": 43.75, "T30": 68.75, "T40": 93.75}
NTEETH = {"T20": 20, "T30": 30, "T40": 40}
REP_DESIGNS = ["T20ID10", "T30ID40", "T40ID60"]
TAU = 0.10        # mm, fracture-region threshold vs. the adjacent intact tooth profile
DELTA = 0.002     # mm, pit-surface threshold below the gear face
STEP = 0.005      # mm, discretization step of the mesh outer profile
DATA = None       # dataset root (contains mesh_ply/ and pointcloud_txt/), set from --data


# ----------------------------------------------------------------------------- io
def mesh_file(stem):
    d = stem.split("_")[0]
    return (glob.glob(os.path.join(DATA, "mesh_ply", d, stem + ".PLY"))
            + glob.glob(os.path.join(DATA, "mesh_ply", d, stem + ".ply")))[0]


def load_cloud(stem):
    d = stem.split("_")[0]
    with open(os.path.join(DATA, "pointcloud_txt", d, stem + ".txt")) as f:
        return np.fromstring(f.read().replace("\n", ","), sep=",").reshape(-1, 3)


def load_norm(path=NORM):
    with open(path) as f:
        return {r["instance_id"]: (float(r["scale_mm"]),
                                   np.array([float(r["center_x_mm"]), float(r["center_y_mm"]),
                                             float(r["center_z_mm"])]))
                for r in csv.DictReader(f)}


def write_csv(path, rows):
    keys = []
    for r in rows:
        keys += [k for k in r if k not in keys]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in keys})


# --------------------------------------------------------------------- od (all)
def recover_tooth_count(points, max_teeth=60, n_bins=1440):
    """Dominant angular period of the outer radial envelope about the z-axis."""
    r = np.hypot(points[:, 0], points[:, 1])
    th = np.arctan2(points[:, 1], points[:, 0])
    idx = ((th + np.pi) / (2 * np.pi) * n_bins).astype(int) % n_bins
    env = np.full(n_bins, -np.inf)
    np.maximum.at(env, idx, r)
    env[~np.isfinite(env)] = np.nanmean(env[np.isfinite(env)])
    spec = np.abs(np.fft.rfft(env - env.mean()))
    freqs = np.fft.rfftfreq(n_bins, d=1.0 / n_bins)
    band = (freqs >= 1) & (freqs <= max_teeth)
    return int(round(freqs[band][np.argmax(spec[band])]))


def od_worker(job):
    stem, s, c = job
    import trimesh
    try:
        V = trimesh.load(mesh_file(stem), process=False).vertices
        P = s * load_cloud(stem) + c
        mesh_od = 2.0 * np.hypot(V[:, 0], V[:, 1]).max()
        cloud_od = 2.0 * np.hypot(P[:, 0], P[:, 1]).max()
        return dict(instance_id=stem, design=stem[:7], quality_class=stem[7:9],
                    nominal_od_mm=NOMINAL_OD[stem[:3]], mesh_od_mm=mesh_od, cloud_od_mm=cloud_od,
                    design_teeth=NTEETH[stem[:3]], recovered_teeth=recover_tooth_count(P), error="")
    except Exception as e:  # noqa: BLE001
        return dict(instance_id=stem, error=f"{type(e).__name__}: {e}")


def run_od(a):
    norm = load_norm(a.norm)
    jobs = [(k, *v) for k, v in sorted(norm.items())]
    if a.limit:
        jobs = jobs[::max(1, len(jobs) // a.limit)]
    rows, t0 = [], time.time()
    with Pool(a.workers, initializer=_set_data, initargs=(DATA,)) as pool:
        for i, r in enumerate(pool.imap_unordered(od_worker, jobs, chunksize=8)):
            rows.append(r)
            if (i + 1) % 1000 == 0:
                print(f"[od] {i + 1}/{len(jobs)}  {time.time() - t0:.0f}s", flush=True)
    rows.sort(key=lambda r: r["instance_id"])
    write_csv(os.path.join(OUT, "mesh_cloud_od.csv"), rows)
    ok = [r for r in rows if not r["error"]]
    print(f"errors: {len(rows) - len(ok)}")
    summary = []
    for d in sorted({r["design"] for r in ok}) + ["All"]:
        rr = [r for r in ok if d in ("All", r["design"])]
        dev = np.array([r["mesh_od_mm"] - r["nominal_od_mm"] for r in rr])
        dif = np.abs([r["cloud_od_mm"] - r["mesh_od_mm"] for r in rr])
        summary.append(dict(design=d, n=len(rr),
                            nominal_od_mm=rr[0]["nominal_od_mm"] if d != "All" else "",
                            mesh_vs_nominal_mae_mm=f"{np.abs(dev).mean():.4f}",
                            mesh_vs_nominal_max_mm=f"{np.abs(dev).max():.4f}",
                            mesh_vs_nominal_sd_mm=f"{dev.std(ddof=1):.4f}",
                            cloud_vs_mesh_mae_mm=f"{dif.mean():.5f}",
                            cloud_vs_mesh_max_mm=f"{dif.max():.5f}",
                            tooth_count_exact=f"{sum(r['recovered_teeth'] == r['design_teeth'] for r in rr)}/{len(rr)}"))
    write_csv(os.path.join(OUT, "mesh_cloud_od_summary.csv"), summary)
    for s in summary:
        print(s)


# ---------------------------------------------------------------- defect metrics
def exact_profile(mesh):
    """Outer boundary of the prismatic top face, discretized at STEP mm (2-D, mm)."""
    from shapely.geometry import Polygon
    V, F = mesh.vertices, mesh.faces
    top = np.all(np.isclose(V[F][:, :, 2], V[:, 2].max(), atol=1e-6), axis=1)
    e = np.sort(np.vstack([F[top][:, [0, 1]], F[top][:, [1, 2]], F[top][:, [2, 0]]]), axis=1)
    u, cnt = np.unique(e, axis=0, return_counts=True)
    adj = {}
    for a, b in u[cnt == 1]:
        adj.setdefault(a, []).append(b); adj.setdefault(b, []).append(a)
    seen, loops = set(), []
    for s in adj:
        if s in seen:
            continue
        loop, prev, cur = [s], None, s
        seen.add(s)
        while True:
            nxt = [v for v in adj[cur] if v != prev and v not in seen]
            if not nxt:
                break
            prev, cur = cur, nxt[0]; loop.append(cur); seen.add(cur)
        loops.append(V[loop][:, :2])
    ring = max(loops, key=lambda L: Polygon(L).area)
    ring = np.vstack([ring, ring[:1]])
    pts = []
    for a, b in zip(ring[:-1], ring[1:]):
        k = max(1, int(np.ceil(np.linalg.norm(b - a) / STEP)))
        pts.append(a + (b - a) * np.arange(k)[:, None] / k)
    return np.vstack(pts)


def cloud_profile(P, inner_d):
    """Side-wall points of the outer profile, projected to 2-D."""
    z = P[:, 2]
    zt = np.median(z[z > z.max() - 0.002]); zb = np.median(z[z < z.min() + 0.002])
    xy = P[(z > zb + 0.01) & (z < zt - 0.01), :2]
    return xy[np.hypot(xy[:, 0], xy[:, 1]) > inner_d / 2 + 0.5]


def tooth_sectors(xy, n):
    """Tooth-sector index of each 2-D point (sectors centered on tooth tips)."""
    r = np.hypot(xy[:, 0], xy[:, 1]); th = np.arctan2(xy[:, 1], xy[:, 0])
    pitch = 2 * np.pi / n
    th0 = th[np.argmax(r)]
    near = (r > r.max() - 0.3) & (np.abs(np.angle(np.exp(1j * (th - th0)))) < pitch / 3)
    th0 = np.angle(np.exp(1j * th[near]).mean())
    return np.round(np.angle(np.exp(1j * (th - th0))) / pitch).astype(int) % n, r


def radial_material_loss(xy, n):
    k, r = tooth_sectors(xy, n)
    tip = np.array([r[k == i].max() for i in range(n)])
    j = int(np.argmin(tip))
    return float(np.median(np.delete(tip, j)) - tip[j])


def fracture_region(xy, n):
    """Profile points farther than TAU from the gear's own profile rotated by +/- one pitch."""
    from scipy.spatial import cKDTree
    a = 2 * np.pi / n
    d = np.full(len(xy), np.inf)
    for sgn in (1, -1):
        R = np.array([[np.cos(sgn * a), -np.sin(sgn * a)], [np.sin(sgn * a), np.cos(sgn * a)]])
        d = np.minimum(d, cKDTree(xy @ R.T).query(xy)[0])
    return xy[d > TAU]


def fracture_extent(xy, n):
    from scipy.spatial.distance import pdist
    D = fracture_region(xy, n)
    return float(pdist(D).max()) if len(D) > 1 else 0.0


def pit_mesh(mesh, inner_d, ded_d):
    V, F = mesh.vertices, mesh.faces
    zb, zt = V[:, 2].min(), V[:, 2].max()
    rv = np.hypot(V[:, 0], V[:, 1])
    body = (rv > inner_d / 2 + 0.3) & (rv < ded_d / 2 - 0.3)
    depth = float(np.minimum(V[:, 2] - zb, zt - V[:, 2])[body].max())
    tri = V[F]; cen = tri.mean(1)
    dep_f = np.minimum(cen[:, 2] - zb, zt - cen[:, 2])
    rf = np.hypot(cen[:, 0], cen[:, 1])
    sel = (dep_f > DELTA) & (rf > inner_d / 2 + 0.3) & (rf < ded_d / 2 - 0.3)
    area = 0.5 * np.linalg.norm(np.cross(tri[sel, 1] - tri[sel, 0], tri[sel, 2] - tri[sel, 0]), axis=1)
    return depth, (cen[sel, :2] * area[:, None]).sum(0) / area.sum()


def pit_cloud(P, inner_d, ded_d):
    z = P[:, 2]
    zt = np.median(z[z > z.max() - 0.002]); zb = np.median(z[z < z.min() + 0.002])
    dep = np.minimum(z - zb, zt - z)
    r = np.hypot(P[:, 0], P[:, 1])
    body = (r > inner_d / 2 + 0.3) & (r < ded_d / 2 - 0.3)
    sel = body & (dep > DELTA) & (dep < 1.0)
    return float(dep[body].max()), P[sel, :2].mean(0)


def defect_worker(job):
    stem, s, c = job
    import trimesh
    try:
        tok, cls = stem[:3], stem[7:9]
        n, inner_d, ded_d = NTEETH[tok], float(stem[5:7]), DEDENDUM[tok]
        mesh = trimesh.load(mesh_file(stem), process=False)
        P = s * load_cloud(stem) + c
        row = dict(instance_id=stem, design=stem[:7], quality_class=cls)
        if cls == "G0":      # negative control: apparent material loss on an intact gear
            row.update(quantity="control_radial_material_loss",
                       mesh_mm=radial_material_loss(exact_profile(mesh), n),
                       cloud_mm=radial_material_loss(cloud_profile(P, inner_d), n))
        elif cls == "W0":
            row.update(quantity="radial_material_loss",
                       mesh_mm=radial_material_loss(exact_profile(mesh), n),
                       cloud_mm=radial_material_loss(cloud_profile(P, inner_d), n))
        elif cls == "R0":
            row.update(quantity="fracture_extent",
                       mesh_mm=fracture_extent(exact_profile(mesh), n),
                       cloud_mm=fracture_extent(cloud_profile(P, inner_d), n))
        else:
            dm, cm = pit_mesh(mesh, inner_d, ded_d)
            dc, cc = pit_cloud(P, inner_d, ded_d)
            row.update(quantity="pit_depth", mesh_mm=dm, cloud_mm=dc,
                       pit_location_diff_mm=float(np.hypot(*(cm - cc))))
        row["abs_diff_mm"] = abs(row["cloud_mm"] - row["mesh_mm"])
        return row
    except Exception as e:  # noqa: BLE001
        return dict(instance_id=stem, error=f"{type(e).__name__}: {e}")


def run_defect(a):
    norm = load_norm(a.norm)
    rng = np.random.default_rng(a.seed)
    jobs = [(f"{d}{q}_{i:05d}", *norm[f"{d}{q}_{i:05d}"])
            for d in REP_DESIGNS for q in ("P0", "W0", "R0", "G0")
            for i in sorted(rng.choice(np.arange(1, 501), a.n, replace=False))]
    with Pool(a.workers, initializer=_set_data, initargs=(DATA,)) as pool:
        rows = pool.map(defect_worker, jobs)
    for r in rows:
        for k in ("mesh_mm", "cloud_mm", "abs_diff_mm", "pit_location_diff_mm"):
            if k in r:
                r[k] = round(r[k], 6)
    write_csv(os.path.join(OUT, "defect_agreement.csv"), rows)
    ok = [r for r in rows if not r.get("error")]
    print(f"errors: {len(rows) - len(ok)}")
    stats = lambda x: f"n={len(x)}  mean {np.mean(x):.4f}  SD {np.std(x, ddof=1):.4f}  max {np.max(x):.4f} mm"
    for q in ("radial_material_loss", "fracture_extent", "pit_depth", "control_radial_material_loss"):
        rr = [r for r in ok if r["quantity"] == q]
        print(f"{q:22s} |diff| {stats([r['abs_diff_mm'] for r in rr])}"
              f"   (mesh range {min(r['mesh_mm'] for r in rr):.3f}-{max(r['mesh_mm'] for r in rr):.3f} mm)")
    print(f"{'pit_location':22s} diff   {stats([r['pit_location_diff_mm'] for r in ok if r['quantity'] == 'pit_depth'])}")


# ------------------------------------------------------------- normalization
def register(Pn, mesh_o3d, s0, c0, iters=100, n_sub=20000, seed=0):
    """Scale s and center c such that s * Pn + c lies on the mesh surface (closed-form ICP)."""
    import open3d as o3d
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh_o3d))
    sub = Pn[np.random.default_rng(seed).choice(len(Pn), min(n_sub, len(Pn)), replace=False)]
    s, c = float(s0), np.asarray(c0, float).copy()
    pm = sub.mean(0); pc = sub - pm
    for _ in range(iters):
        q = scene.compute_closest_points(
            o3d.core.Tensor((s * sub + c).astype(np.float32)))["points"].numpy().astype(np.float64)
        qm = q.mean(0)
        s_new = float((pc * (q - qm)).sum() / (pc * pc).sum())
        c_new = qm - s_new * pm
        done = abs(s_new - s) < 1e-8 and np.abs(c_new - c).max() < 1e-8
        s, c = s_new, c_new
        if done:
            break
    resid = scene.compute_distance(o3d.core.Tensor((s * Pn + c).astype(np.float32))).numpy()
    return s, c, float(resid.mean())


def norm_worker(job):
    stem, s0, c0 = job
    import open3d as o3d
    try:
        s, c, res = register(load_cloud(stem), o3d.io.read_triangle_mesh(mesh_file(stem)), s0, c0)
        return dict(instance_id=stem, design=stem[:7], quality_class=stem[7:9],
                    center_x_mm=f"{c[0]:.6f}", center_y_mm=f"{c[1]:.6f}", center_z_mm=f"{c[2]:.6f}",
                    scale_mm=f"{s:.6f}", residual_mm=res)
    except Exception as e:  # noqa: BLE001
        return dict(instance_id=stem, error=f"{type(e).__name__}: {e}")


def run_normalization(a):
    norm = load_norm(a.norm)                       # initial guess
    jobs = [(k, *v) for k, v in sorted(norm.items())]
    if a.limit:
        jobs = jobs[::max(1, len(jobs) // a.limit)]
    with Pool(a.workers, initializer=_set_data, initargs=(DATA,)) as pool:
        rows = pool.map(norm_worker, jobs, chunksize=4)
    res = [r["residual_mm"] for r in rows if "residual_mm" in r]
    for r in rows:
        r.pop("residual_mm", None)
    write_csv(a.out, rows)
    print(f"[saved] {a.out}  mean point-to-mesh residual {np.mean(res):.6f} mm (max {np.max(res):.6f})")


def _set_data(path):
    global DATA
    DATA = path


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("task", choices=["od", "defect", "normalization"])
    ap.add_argument("--data", required=True, help="dataset root containing mesh_ply/ and pointcloud_txt/")
    ap.add_argument("--norm", default=NORM, help="normalization parameter CSV")
    ap.add_argument("--out", default=os.path.join(OUT, "normalization_params_registered.csv"),
                    help="output CSV for the normalization task")
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    ap.add_argument("--limit", type=int, default=0, help="evaluate an evenly spaced subset (0 = all)")
    ap.add_argument("--n", type=int, default=10, help="instances per design and defect class")
    ap.add_argument("--seed", type=int, default=2026)
    a = ap.parse_args()
    DATA = a.data
    os.makedirs(OUT, exist_ok=True)
    {"od": run_od, "defect": run_defect, "normalization": run_normalization}[a.task](a)
