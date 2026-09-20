"""Interactive sampling-and-reconstruction viewer.

For a chosen gear design, quality class, and instance, this tool walks through the
released CAD-to-point-cloud pipeline and shows that the sampled point cloud preserves
the part morphology:

    Stage 1  original PLY mesh (physical mm geometry)
    Stage 2  point cloud sampled from that mesh with the SAME routine that produced the
             released .txt clouds (ply2pcd/point_sampling.py: uniform sampling, unit-sphere
             normalized by default) -- i.e., exactly the data a user obtains
    Stage 3  surface reconstructed (Poisson) from those sampled points
    Stage 4  original + reconstructed meshes overlaid in two colors (registered by ICP)

Usage:
    python validation/reconstruct_gear.py --design T30ID40 --quality P0 --instance 1 \
        --num_points 100000 \
        --data /path/to/data \
        --out  validation/figs_interactive

Mouse:  left-drag = rotate, scroll = zoom, right-drag = pan.
Keys:
    N / B : next / previous stage (keeps the current camera view)
    O     : toggle the original mesh
    C     : toggle the sampled point cloud
    M     : toggle the reconstructed mesh
    W     : toggle the reconstructed mesh as wireframe (clearer in the overlay)
    P     : save a screenshot (PNG) of the current view
    S     : save the current camera viewpoint to JSON
    Q/Esc : quit
"""
import argparse
import glob
import os
import sys
import numpy as np
import open3d as o3d

# Use the exact sampling routine that produced the released point clouds.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ply2pcd"))
from point_sampling import sample_points

ORIG_COLOR  = [0.55, 0.60, 0.70]   # cool gray-blue: original mesh
RECON_COLOR = [0.90, 0.55, 0.15]   # warm orange: reconstructed mesh
CLOUD_COLOR = [0.03, 0.19, 0.42]   # deep blue: sampled point cloud

STAGES = [
    ("1. Original PLY mesh (mm)",          dict(orig=True,  cloud=False, recon=False)),
    ("2. Sampled point cloud",             dict(orig=False, cloud=True,  recon=False)),
    ("3. Reconstructed surface (Poisson)", dict(orig=False, cloud=False, recon=True)),
    ("4. Original + reconstructed (overlay)", dict(orig=True, cloud=False, recon=True)),
]


def mesh_path(data, design, quality, inst):
    hits = (glob.glob(os.path.join(data, "mesh_ply", f"{design}{quality}", f"{design}{quality}_{inst:05d}.PLY"))
            + glob.glob(os.path.join(data, "mesh_ply", f"{design}{quality}", f"{design}{quality}_{inst:05d}.ply")))
    if not hits:
        raise FileNotFoundError(f"No PLY for {design}{quality}_{inst:05d} under {data}/mesh_ply")
    return hits[0]


def auto_poisson_depth(mesh, num_points, lo=8, hi=11):
    """Choose the Poisson octree depth that best matches the sampling density.

    Poisson can only recover detail the points actually captured, so the finest
    octree cell should be about one point-spacing wide (cell = bbox / 2**depth ~=
    sqrt(area / num_points)). A finer grid would fit sampling noise; a coarser one
    would blur real geometry. Returns depth clamped to [lo, hi]. The bbox/spacing
    ratio is scale-invariant, so the result is the same for mm or normalized points.
    """
    area = float(mesh.get_surface_area())
    bbox = float(np.ptp(np.asarray(mesh.vertices), axis=0).max())
    spacing = np.sqrt(area / num_points)
    depth = int(round(np.log2(bbox / spacing)))
    return max(lo, min(hi, depth))


def _clean_for_poisson(pcd):
    """Drop points with non-finite positions or invalid (NaN / zero-length) normals.
    A few points sampled on near-zero-area triangles get undefined normals, which
    Poisson reports as 'bad data'. Returns a cleaned copy (the input is left intact
    so the displayed point cloud is unchanged)."""
    pts = np.asarray(pcd.points)
    good = np.isfinite(pts).all(axis=1)
    nrm = np.asarray(pcd.normals) if pcd.has_normals() else None
    if nrm is not None and len(nrm) == len(pts):
        good &= np.isfinite(nrm).all(axis=1) & (np.linalg.norm(nrm, axis=1) > 1e-9)
    out = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(pts[good]))
    if nrm is not None and len(nrm) == len(pts):
        out.normals = o3d.utility.Vector3dVector(nrm[good])
    dropped = int((~good).sum())
    if dropped:
        print(f"[reconstruct] dropped {dropped} point(s) with invalid normals before Poisson")
    return out


def poisson_reconstruct(pcd, depth=9, density_quantile=0.0):
    """Poisson surface reconstruction from the sampled points.

    The gear is a closed solid sampled on all surfaces, so Poisson returns a
    watertight surface (the bore remains an open tunnel). With density_quantile=0
    no vertices are trimmed, which avoids punching holes into under-sampled regions;
    a positive quantile trims the lowest-density (extrapolated) vertices at the cost
    of holes. Stray disconnected components are removed either way.
    """
    mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
        _clean_for_poisson(pcd), depth=depth)
    if density_quantile > 0:
        densities = np.asarray(densities)
        mesh.remove_vertices_by_mask(densities < np.quantile(densities, density_quantile))
    # keep only the largest connected component (drop floating fragments)
    labels, ntri, _ = mesh.cluster_connected_triangles()
    labels, ntri = np.asarray(labels), np.asarray(ntri)
    if ntri.size > 1:
        mesh.remove_triangles_by_mask(labels != int(ntri.argmax()))
        mesh.remove_unreferenced_vertices()
    mesh.compute_vertex_normals()
    return mesh


def register_icp(recon_mesh, orig_pts, threshold):
    """Refine alignment of the reconstructed mesh onto the original (near-identity,
    since the points were sampled from the original). Returns fitness/rmse for report."""
    src = recon_mesh.sample_points_uniformly(60000)
    tgt = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(orig_pts))
    reg = o3d.pipelines.registration.registration_icp(
        src, tgt, threshold, np.eye(4),
        o3d.pipelines.registration.TransformationEstimationPointToPoint())
    recon_mesh.transform(reg.transformation)
    return reg.fitness, reg.inlier_rmse


def _camera_vectors(elevation_deg):
    """Camera front/up so the viewing direction makes `elevation_deg` with the z-axis."""
    el = np.radians(elevation_deg)
    front = np.array([np.sin(el), 0.0, np.cos(el)])          # 45 deg from +z by default
    up = np.array([-np.cos(el), 0.0, np.sin(el)])            # perpendicular, keeps z upward
    return front, up


def _apply_camera(vis, lookat, front, up, zoom):
    ctr = vis.get_view_control()
    ctr.set_lookat(lookat)
    ctr.set_front(front)
    ctr.set_up(up)
    ctr.set_zoom(zoom)


def _fit_vertical_lookat(vis, pivot, front, up, zoom, width, height, iters=6):
    """Shift the lookat along `up` so the silhouette is vertically centered.
    The 45-deg tilt otherwise drops the gear low in the frame, wasting the top
    margin and clipping the bottom when zoomed in. cy(k) is nonlinear, so we take
    damped Newton steps with a locally measured slope until the bbox center reaches
    the frame midline."""
    def cy(k):
        _apply_camera(vis, pivot + k * up, front, up, zoom)
        vis.poll_events(); vis.update_renderer()
        img = np.asarray(vis.capture_screen_float_buffer(do_render=True))
        mask = img.reshape(-1, 3).min(1) < 0.92
        if not mask.any():
            return height / 2.0
        ys = np.where(mask)[0] // width
        return (int(ys.min()) + int(ys.max())) / 2.0
    k = 0.0
    for _ in range(iters):
        c0 = cy(k)
        if abs(c0 - height / 2.0) < 4:
            break
        slope = (cy(k + 0.06) - c0) / 0.06        # local pixels-per-unit-k
        if abs(slope) < 1e-6:
            break
        step = float(np.clip((height / 2.0 - c0) / slope, -0.35, 0.35))
        k = float(np.clip(k + step, -1.5, 1.5))
    return pivot + k * up


def render_video(orig, recon, pcd, out_path, fps, stage_seconds, width, height,
                 elevation_deg, zoom, pivot):
    """Offscreen turntable video: original mesh -> point cloud -> reconstruction ->
    reconstruction wireframe -> registration overlay, each rotating once about the
    gear centerline (the z-axis through `pivot`)."""
    import imageio
    frames_per_stage = max(1, int(round(fps * stage_seconds)))
    recon_pts = recon.sample_points_uniformly(200000)
    recon_pts.paint_uniform_color(RECON_COLOR)

    # (label, geometries to show, wireframe?)
    stages = [
        ("original mesh",              [orig],            False),
        ("point cloud",                [pcd],             False),
        ("reconstructed mesh",         [recon],           False),
        ("reconstructed (wireframe)",  [recon],           True),
        ("registration overlay",       [orig, recon_pts], False),
    ]

    vis = o3d.visualization.Visualizer()
    vis.create_window(width=width, height=height, visible=True)
    ro = vis.get_render_option()
    ro.background_color = np.array([1, 1, 1])
    ro.mesh_show_back_face = True
    ro.point_size = 2.0
    center = np.asarray(pivot, dtype=float)       # gear centerline (z-axis through here)

    # One full revolution spread across ALL stages (each stage = 1/len(stages) of a turn),
    # so the spin is continuous and calm rather than a full turn per stage. Every geometry
    # is rotated each frame (even while hidden) so the visible orientation stays continuous
    # as stages switch.
    all_geoms = [orig, pcd, recon, recon_pts]
    total_frames = frames_per_stage * len(stages)
    dtheta = 2 * np.pi / total_frames
    R = orig.get_rotation_matrix_from_axis_angle([0, 0, dtheta])

    # Establish the view scale once with the original mesh, then vertically center.
    front, up = _camera_vectors(elevation_deg)
    vis.add_geometry(orig, reset_bounding_box=True)
    lookat = _fit_vertical_lookat(vis, center, front, up, zoom, width, height)

    writer = imageio.get_writer(out_path, fps=fps, macro_block_size=None, quality=8)
    for label, geoms, wire in stages:
        print(f"[video] stage: {label}")
        vis.clear_geometries()
        ro.mesh_show_wireframe = wire
        for g in geoms:
            vis.add_geometry(g, reset_bounding_box=False)
        _apply_camera(vis, lookat, front, up, zoom)
        for _ in range(frames_per_stage):
            for g in all_geoms:
                g.rotate(R, center=center)
            for g in geoms:
                vis.update_geometry(g)
            vis.poll_events(); vis.update_renderer()
            img = np.asarray(vis.capture_screen_float_buffer(do_render=True))
            writer.append_data((img * 255).astype(np.uint8))
    writer.close()
    vis.destroy_window()
    print(f"[video] saved {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--design", default="T30ID40")
    ap.add_argument("--quality", default="P0", choices=["G0", "P0", "W0", "R0"])
    ap.add_argument("--instance", type=int, default=1)
    ap.add_argument("--num_points", type=int, default=100000)
    ap.add_argument("--data", default="data",
                    help="dataset root containing mesh_ply/ and pointcloud_txt/")
    ap.add_argument("--out", default="validation/figs_interactive")
    ap.add_argument("--poisson_depth", type=int, default=None,
                    help="Poisson octree depth. Default: auto-selected from num_points so "
                         "the cell size matches the point spacing (best faithful reconstruction). "
                         "Override with an integer (e.g. 8-11) to go coarser/finer.")
    ap.add_argument("--no-normalize", dest="normalize", action="store_false",
                    help="Sample raw mm coordinates instead of the released unit-sphere "
                         "normalized ones (default: normalized, matching the released .txt clouds)")
    ap.add_argument("--no-flip-x", dest="flip_x", action="store_false",
                    help="Do not flip the gear 180 deg about x (default: flip, since the PLY "
                         "is stored upside down for this view)")
    ap.add_argument("--density_quantile", type=float, default=0.0,
                    help="Trim this lowest-density fraction of Poisson vertices (default 0 = "
                         "no trim, watertight; raise slightly, e.g. 0.01, only if a mesh balloons)")
    # video mode
    ap.add_argument("--video", action="store_true",
                    help="Render an auto-rotating mp4 (original -> points -> reconstruction -> "
                         "wireframe -> overlay) instead of opening the interactive window")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--stage_seconds", type=float, default=6.0,
                    help="seconds per stage; one full revolution is spread across all stages")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=960)
    ap.add_argument("--elevation", type=float, default=45.0, help="viewing angle from the z-axis, degrees")
    ap.add_argument("--zoom", type=float, default=0.5, help="smaller = more zoomed in (fills the frame)")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    stem = f"{args.design}{args.quality}_{args.instance:05d}"

    print(f"[load] {stem}")
    orig = o3d.io.read_triangle_mesh(mesh_path(args.data, args.design, args.quality, args.instance))
    orig.compute_vertex_normals()
    if args.flip_x:
        # The PLY is stored upside down for this viewpoint; flip 180 deg about x so the
        # gear sits upright. Done before sampling so the point cloud and reconstruction
        # inherit the same orientation.
        orig.rotate(orig.get_rotation_matrix_from_axis_angle([np.pi, 0, 0]), center=orig.get_center())
        orig.compute_vertex_normals()

    # Sample exactly as point_sampling.py does (same routine); normalized by default so
    # the point cloud shown here is identical to the released .txt cloud.
    frame = "unit-sphere normalized" if args.normalize else "millimeter"
    print(f"[sample] {args.num_points} points via point_sampling.sample_points ({frame})")
    pcd, center, scale = sample_points(orig, args.num_points, normalize=args.normalize)
    if args.normalize:
        # Bring the original mesh into the same unit-sphere frame so the overlay aligns.
        orig.translate(-center)
        orig.scale(1.0 / scale, center=(0.0, 0.0, 0.0))
    unit = "" if args.normalize else " mm"
    orig_pts = np.asarray(pcd.points).copy()

    depth = args.poisson_depth if args.poisson_depth is not None else auto_poisson_depth(orig, args.num_points)
    how = "manual" if args.poisson_depth is not None else "auto from num_points"
    print(f"[reconstruct] Poisson depth={depth} ({how})")
    recon = poisson_reconstruct(pcd, depth=depth, density_quantile=args.density_quantile)
    icp_thr = 0.05 if args.normalize else 1.0
    fit, rmse = register_icp(recon, orig_pts, icp_thr)
    print(f"[register] ICP fitness={fit:.3f} inlier_rmse={rmse:.4f}{unit} (near-identity expected)")

    orig.paint_uniform_color(ORIG_COLOR)
    recon.paint_uniform_color(RECON_COLOR)
    pcd.paint_uniform_color(CLOUD_COLOR)

    if args.video:
        out_path = os.path.join(args.out, f"{stem}_n{args.num_points}.mp4")
        pivot = np.asarray(pcd.points).mean(axis=0)   # sampled-point centroid = gear centerline
        render_video(orig, recon, pcd, out_path, args.fps, args.stage_seconds,
                     args.width, args.height, args.elevation, args.zoom, pivot)
        return

    state = {"i": 0, "show": dict(STAGES[0][1]), "wire": False}

    vis = o3d.visualization.VisualizerWithKeyCallback()
    vis.create_window(window_name=f"{stem} - N/B step stages, P save", width=1100, height=900)
    ro = vis.get_render_option()
    ro.background_color = np.array([1, 1, 1])
    ro.mesh_show_back_face = True
    ro.point_size = 2.5

    def refresh(reset_bbox=False):
        vis.clear_geometries()
        ro.mesh_show_wireframe = False
        if state["show"]["orig"]:
            vis.add_geometry(orig, reset_bounding_box=reset_bbox)
        if state["show"]["cloud"]:
            vis.add_geometry(pcd, reset_bounding_box=reset_bbox)
        if state["show"]["recon"]:
            if state["wire"]:
                ro.mesh_show_wireframe = True
            vis.add_geometry(recon, reset_bounding_box=reset_bbox)
        vis.poll_events(); vis.update_renderer()

    def set_stage(i):
        state["i"] = i % len(STAGES)
        state["show"] = dict(STAGES[state["i"]][1])
        print(f"[stage] {STAGES[state['i']][0]}")
        refresh()

    def next_stage(v): set_stage(state["i"] + 1); return False
    def prev_stage(v): set_stage(state["i"] - 1); return False
    def toggle(key):
        def cb(v):
            state["show"][key] = not state["show"][key]; refresh(); return False
        return cb
    def toggle_wire(v):
        state["wire"] = not state["wire"]; refresh(); return False
    def save_png(v):
        tag = "".join(k[0] for k, on in state["show"].items() if on) + ("_wire" if state["wire"] else "")
        path = os.path.join(args.out, f"{stem}_n{args.num_points}_stage{state['i']+1}_{tag}.png")
        vis.capture_screen_image(path, do_render=True); print(f"[saved] {path}"); return False
    def save_view(v):
        params = vis.get_view_control().convert_to_pinhole_camera_parameters()
        path = os.path.join(args.out, f"{args.design}_view.json")
        o3d.io.write_pinhole_camera_parameters(path, params); print(f"[saved view] {path}"); return False

    vis.register_key_callback(ord("N"), next_stage)
    vis.register_key_callback(ord("B"), prev_stage)
    vis.register_key_callback(ord("O"), toggle("orig"))
    vis.register_key_callback(ord("C"), toggle("cloud"))
    vis.register_key_callback(ord("M"), toggle("recon"))
    vis.register_key_callback(ord("W"), toggle_wire)
    vis.register_key_callback(ord("P"), save_png)
    vis.register_key_callback(ord("S"), save_view)

    # initial add with bounding-box reset so the camera frames the part
    vis.add_geometry(orig)
    print(__doc__)
    print(f"[stage] {STAGES[0][0]}")
    vis.run()
    vis.destroy_window()


if __name__ == "__main__":
    main()
