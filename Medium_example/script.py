# https://medium.com/@rohith.sunkara/reconstructing-the-real-world-estimating-camera-position-from-images-and-gps-coordinates-6fd79009af28
"""Estimate camera parameters from GPS/image POIs and compare LOO subsets.

Automatic VFOV selection prioritizes Leave-One-Out reprojection error. Every
optimizer-converged, finite LOO prediction is retained for scoring, even when its
camera geometry is suspicious. Each fold is classified as A (good geometry and
low error), B (low error but suspicious geometry), or C (high error / failed
optimization). Physical validity and parameter stability are reported separately
and used as selection tie-breakers / NPZ safety gates.
"""

from pathlib import Path
import math
import warnings

import cv2
import numpy as np
import pandas as pd
from PIL import Image
from scipy.optimize import least_squares

# ---------------------------------------------------------------------------
# 1. FILES, CAMERA ORIGIN, POIS AND SETTINGS
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "Biblioteca"
IMAGE_PATH = OUTPUT_DIR / "faraway.jpg"
# Also accept the image next to script.py, which is convenient for a flat folder.
if not IMAGE_PATH.exists() and (BASE_DIR / "faraway.jpg").exists():
    IMAGE_PATH = BASE_DIR / "faraway.jpg"
OUTPUT_FILE = OUTPUT_DIR / "camera_faraway.npz"

# Tables written by this script.
LOO_RESULTS_CSV = OUTPUT_DIR / "faraway_loo_parameter_results.csv"
VFOV_SUMMARY_CSV = OUTPUT_DIR / "faraway_vfov_stability_summary.csv"
PARAMETER_COMPARISON_CSV = OUTPUT_DIR / "faraway_camera_parameter_comparison.csv"

# Local ENU origin (WGS84 latitude, longitude, altitude in metres).
origin_lat = 40.632175
origin_lon = -8.659642
origin_alt = 5.775875

poi_data = pd.DataFrame({
    "id": [1, 2, 3, 4, 5],
    "img_x": [678, 685, 861, 862, 871],
    "img_y": [680, 417, 674, 419, 817],
    "map_lat": [40.631542, 40.631381, 40.631542,
                40.631381, 40.631944],
    "map_lng": [-8.659981, -8.660189, -8.659981,
                -8.660189, -8.660367],
    "map_altitude": [21.12, 20.06, 3.92, 2.86, 6.37],
})

# Manual VFOV: use this value as the starting guess, but STILL run LOO.
# Set to None to sweep VFOV_MIN_DEG..VFOV_MAX_DEG and select automatically.
MANUAL_VFOV_DEG = None #80.94
VFOV_MIN_DEG = 20.0
VFOV_MAX_DEG = 120.0
VFOV_STEP_DEG = 5.0

# Minimum number of optimizer-completed LOO predictions with finite error
# required to compare a VFOV. Geometry does NOT determine whether a prediction
# contributes to the LOO error mean. Set to None to require all folds.
MIN_SUCCESSFUL_FOLDS_FOR_RANKING = 4

# A fold is classified as Type C when its held-out reprojection error exceeds
# this threshold. The result still contributes to the mean LOO error so that
# poor predictions are not silently discarded. Set to None to disable this flag.
MAX_ACCEPTABLE_LOO_ERROR_PX = 100.0

# Primary selection: minimize mean LOO prediction error across ALL evaluated
# folds (A, B and C-high-error). VFOVs within this tolerance of the minimum are
# treated as practically tied. Among near-ties, prefer more safe-geometry folds,
# then lower parameter instability. Set to 0.0 for strict error-first ranking.
LOO_ERROR_TIE_TOLERANCE_PX = 1.0

# Physical visibility requires positive camera-space depth. A separate safety
# margin rejects nearly degenerate solutions where a landmark is technically
# in front of the camera but almost on its image plane (e.g. 0.001 m away).
MIN_POSITIVE_CAMERA_DEPTH_M = 1e-6
MIN_SAFE_CAMERA_DEPTH_M = 1.0
# Optional location constraints are disabled by default because the actual
# webcam position/height may not be known precisely.
MAX_CAMERA_DISTANCE_FROM_ENU_ORIGIN_M = None  # e.g. 2000.0, if justified
CAMERA_ALTITUDE_RANGE_M = None  # e.g. (0.0, 200.0), if justified

# The final parameter table always contains all-points plus each one-point
# exclusion. "auto_best_valid" prefers all_points when physically valid; if not,
# it chooses the physically valid five-point subset with the lowest corresponding
# LOO held-out reprojection error. You can still force a named case.
NPZ_CALIBRATION_CASE = "auto_best_valid"

MAX_OPTIMIZER_EVALUATIONS = 1200
OPTIMIZER_TOLERANCE = 1e-8

# Camera model assumptions: square pixels, principal point at image centre,
# and zero lens distortion. The optimization estimates one focal length.
ZERO_DISTORTION = np.zeros((5, 1), dtype=np.float64)

# Parameter-stability score normalization. These are comparison scales, not
# claims about acceptable physical accuracy. A lower composite score is better.
POSITION_SPREAD_SCALE_AS_SCENE_FRACTION = 1.0
ROTATION_SPREAD_SCALE_DEG = 5.0
VFOV_STD_SCALE_DEG = 5.0
# Numerical tolerance for treating parameter-stability scores as tied.
STABILITY_SCORE_TIE_TOLERANCE = 1e-3

# ---------------------------------------------------------------------------
# 2. WGS84 / ENU CONVERSIONS
# ---------------------------------------------------------------------------

WGS84_A = 6378137.0
WGS84_F = 1.0 / 298.257223563
WGS84_E2 = WGS84_F * (2.0 - WGS84_F)
WGS84_B = WGS84_A * (1.0 - WGS84_F)
WGS84_EP2 = (WGS84_A**2 - WGS84_B**2) / WGS84_B**2


def geodetic_to_ecef(lat_deg, lon_deg, altitude_m):
    """Convert WGS84 geodetic coordinates to ECEF metres."""
    lat = math.radians(float(lat_deg))
    lon = math.radians(float(lon_deg))
    sin_lat, cos_lat = math.sin(lat), math.cos(lat)
    sin_lon, cos_lon = math.sin(lon), math.cos(lon)
    n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * sin_lat**2)
    return np.array([
        (n + altitude_m) * cos_lat * cos_lon,
        (n + altitude_m) * cos_lat * sin_lon,
        (n * (1.0 - WGS84_E2) + altitude_m) * sin_lat,
    ], dtype=np.float64)


def gps_to_enu(latitudes, longitudes, altitudes, ref_lat, ref_lon, ref_alt):
    """Convert WGS84 coordinates to a local East-North-Up frame in metres."""
    ref_ecef = geodetic_to_ecef(ref_lat, ref_lon, ref_alt)
    points_ecef = np.vstack([
        geodetic_to_ecef(lat, lon, alt)
        for lat, lon, alt in zip(latitudes, longitudes, altitudes)
    ])
    delta = points_ecef - ref_ecef

    lat0 = math.radians(float(ref_lat))
    lon0 = math.radians(float(ref_lon))
    slat, clat = math.sin(lat0), math.cos(lat0)
    slon, clon = math.sin(lon0), math.cos(lon0)
    ecef_to_enu = np.array([
        [-slon, clon, 0.0],
        [-slat * clon, -slat * slon, clat],
        [clat * clon, clat * slon, slat],
    ], dtype=np.float64)
    return (ecef_to_enu @ delta.T).T


def enu_to_ecef(enu_point, ref_lat, ref_lon, ref_alt):
    """Convert one ENU point to ECEF metres."""
    east, north, up = np.asarray(enu_point, dtype=np.float64).reshape(3)
    lat0 = math.radians(float(ref_lat))
    lon0 = math.radians(float(ref_lon))
    slat, clat = math.sin(lat0), math.cos(lat0)
    slon, clon = math.sin(lon0), math.cos(lon0)
    enu_to_ecef_matrix = np.array([
        [-slon, -slat * clon, clat * clon],
        [clon, -slat * slon, clat * slon],
        [0.0, clat, slat],
    ], dtype=np.float64)
    return geodetic_to_ecef(ref_lat, ref_lon, ref_alt) + (
        enu_to_ecef_matrix @ np.array([east, north, up], dtype=np.float64)
    )


def ecef_to_geodetic(ecef_point):
    """Convert ECEF metres to WGS84 latitude, longitude and ellipsoid height."""
    x, y, z = np.asarray(ecef_point, dtype=np.float64).reshape(3)
    p = math.hypot(x, y)
    lon = math.atan2(y, x)
    theta = math.atan2(z * WGS84_A, p * WGS84_B)
    st, ct = math.sin(theta), math.cos(theta)
    lat = math.atan2(
        z + WGS84_EP2 * WGS84_B * st**3,
        p - WGS84_E2 * WGS84_A * ct**3,
    )
    slat = math.sin(lat)
    n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * slat**2)
    altitude = p / max(abs(math.cos(lat)), 1e-15) - n
    return math.degrees(lat), math.degrees(lon), altitude

# ---------------------------------------------------------------------------
# 3. CAMERA MODEL AND CALIBRATION
# ---------------------------------------------------------------------------


def make_camera_matrix(vfov_deg, image_width, image_height):
    """Build K from an initial vertical FOV using a pinhole camera model."""
    if not 0.0 < vfov_deg < 180.0:
        raise ValueError("VFOV must be between 0 and 180 degrees (exclusive).")
    focal_px = 0.5 * image_height / math.tan(math.radians(vfov_deg) / 2.0)
    return np.array([
        [focal_px, 0.0, image_width / 2.0],
        [0.0, focal_px, image_height / 2.0],
        [0.0, 0.0, 1.0],
    ], dtype=np.float64)


def camera_centre_from_extrinsics(rvec, tvec):
    """Return camera centre in world ENU coordinates."""
    rotation, _ = cv2.Rodrigues(rvec)
    return (-rotation.T @ np.asarray(tvec).reshape(3, 1)).reshape(3)


def pixel_errors(projected, observed):
    """Return Euclidean pixel errors, one value per point."""
    projected = np.asarray(projected, dtype=np.float64).reshape(-1, 2)
    observed = np.asarray(observed, dtype=np.float64).reshape(-1, 2)
    return np.linalg.norm(projected - observed, axis=1)


def camera_coordinates(object_points, rvec, tvec):
    """Transform ENU/world points into camera coordinates (OpenCV convention)."""
    rotation, _ = cv2.Rodrigues(np.asarray(rvec, dtype=np.float64).reshape(3, 1))
    points = np.asarray(object_points, dtype=np.float64).reshape(-1, 3)
    translation = np.asarray(tvec, dtype=np.float64).reshape(1, 3)
    return (rotation @ points.T).T + translation


def camera_physical_checks(camera_enu, camera_lat, camera_lon, camera_alt,
                           camera_depths_m):
    """Check finite pose, positive point depths, and optional location limits.

    There is deliberately no built-in geographic radius/altitude assumption:
    callers may set optional bounds above when they know the webcam's location.
    """
    issues = []
    depths = np.asarray(camera_depths_m, dtype=np.float64).reshape(-1)
    centre = np.asarray(camera_enu, dtype=np.float64).reshape(3)

    if not np.all(np.isfinite(centre)) or not np.all(
        np.isfinite([camera_lat, camera_lon, camera_alt])
    ):
        issues.append("non-finite camera position")

    if depths.size == 0 or not np.all(np.isfinite(depths)):
        issues.append("non-finite or missing camera-space point depths")
    elif np.any(depths <= MIN_POSITIVE_CAMERA_DEPTH_M):
        behind_count = int(np.sum(depths <= MIN_POSITIVE_CAMERA_DEPTH_M))
        issues.append(f"{behind_count} point(s) are not in front of the camera")

    distance_from_origin = float(np.linalg.norm(centre))
    if (MAX_CAMERA_DISTANCE_FROM_ENU_ORIGIN_M is not None
            and distance_from_origin > MAX_CAMERA_DISTANCE_FROM_ENU_ORIGIN_M):
        issues.append(
            f"camera is {distance_from_origin:.1f} m from ENU origin; "
            f"limit is {MAX_CAMERA_DISTANCE_FROM_ENU_ORIGIN_M:.1f} m"
        )

    if CAMERA_ALTITUDE_RANGE_M is not None:
        min_alt, max_alt = CAMERA_ALTITUDE_RANGE_M
        if not min_alt <= camera_alt <= max_alt:
            issues.append(
                f"camera altitude {camera_alt:.1f} m is outside "
                f"[{min_alt:.1f}, {max_alt:.1f}] m"
            )

    return len(issues) == 0, "; ".join(issues), distance_from_origin


def rotation_difference_deg(rvec_a, rvec_b):
    """Geodesic angular difference between two camera rotation matrices."""
    rotation_a, _ = cv2.Rodrigues(np.asarray(rvec_a, dtype=np.float64).reshape(3, 1))
    rotation_b, _ = cv2.Rodrigues(np.asarray(rvec_b, dtype=np.float64).reshape(3, 1))
    relative = rotation_a @ rotation_b.T
    cosine = (float(np.trace(relative)) - 1.0) / 2.0
    return math.degrees(math.acos(float(np.clip(cosine, -1.0, 1.0))))


def rotation_rms_spread_deg(rvecs):
    """RMS angular spread around the mean rotation (using an SVD projection)."""
    matrices = [
        cv2.Rodrigues(np.asarray(r, dtype=np.float64).reshape(3, 1))[0]
        for r in rvecs
    ]
    mean_matrix = np.mean(matrices, axis=0)
    u, _, vt = np.linalg.svd(mean_matrix)
    mean_rotation = u @ vt
    if np.linalg.det(mean_rotation) < 0:
        u[:, -1] *= -1.0
        mean_rotation = u @ vt

    deviations = []
    for rotation in matrices:
        relative = rotation @ mean_rotation.T
        cosine = (float(np.trace(relative)) - 1.0) / 2.0
        deviations.append(math.degrees(math.acos(float(np.clip(cosine, -1.0, 1.0)))))
    return float(np.sqrt(np.mean(np.square(deviations))))


def fit_camera(vfov_initial, object_points, image_points,
               image_width, image_height):
    """Fit camera pose plus one focal length, starting from the supplied VFOV."""
    object_points = np.asarray(object_points, dtype=np.float64).reshape(-1, 3)
    image_points = np.asarray(image_points, dtype=np.float64).reshape(-1, 2)

    if len(object_points) < 4:
        raise ValueError("At least four 3D-2D correspondences are required.")
    if len(object_points) != len(image_points):
        raise ValueError("The number of 3D and 2D points must match.")

    initial_k = make_camera_matrix(vfov_initial, image_width, image_height)

    # SQPNP can initialize a pose with a small number of points.
    try:
        ok, rvec0, tvec0 = cv2.solvePnP(
            object_points, image_points, initial_k, ZERO_DISTORTION,
            flags=cv2.SOLVEPNP_SQPNP,
        )
    except cv2.error:
        ok, rvec0, tvec0 = False, None, None

    if not ok:
        ok, rvec0, tvec0 = cv2.solvePnP(
            object_points, image_points, initial_k, ZERO_DISTORTION,
            flags=cv2.SOLVEPNP_EPNP,
        )
    if not ok:
        raise RuntimeError("solvePnP could not initialize the camera pose.")

    initial_focal = float(initial_k[0, 0])
    x0 = np.concatenate([
        np.asarray(rvec0, dtype=np.float64).reshape(3),
        np.asarray(tvec0, dtype=np.float64).reshape(3),
        [math.log(initial_focal)],
    ])

    def camera_matrix_for_focal(focal):
        return np.array([
            [focal, 0.0, image_width / 2.0],
            [0.0, focal, image_height / 2.0],
            [0.0, 0.0, 1.0],
        ], dtype=np.float64)

    def residuals(parameters):
        rvec = parameters[:3].reshape(3, 1)
        tvec = parameters[3:6].reshape(3, 1)
        focal = math.exp(float(parameters[6]))
        k = camera_matrix_for_focal(focal)
        projected, _ = cv2.projectPoints(
            object_points, rvec, tvec, k, ZERO_DISTORTION
        )
        return (projected.reshape(-1, 2) - image_points).reshape(-1)

    optimized = least_squares(
        residuals,
        x0,
        bounds=(
            [-np.inf, -np.inf, -np.inf, -np.inf, -np.inf, -np.inf, math.log(1.0)],
            [np.inf, np.inf, np.inf, np.inf, np.inf, np.inf, math.log(100000.0)],
        ),
        method="trf",
        x_scale="jac",
        loss="linear",
        max_nfev=MAX_OPTIMIZER_EVALUATIONS,
        ftol=OPTIMIZER_TOLERANCE,
        xtol=OPTIMIZER_TOLERANCE,
        gtol=OPTIMIZER_TOLERANCE,
    )

    if not np.all(np.isfinite(optimized.x)):
        raise RuntimeError("Camera optimization returned non-finite values.")

    rvec = optimized.x[:3].reshape(3, 1)
    tvec = optimized.x[3:6].reshape(3, 1)
    focal = math.exp(float(optimized.x[6]))
    final_k = camera_matrix_for_focal(focal)

    projected, _ = cv2.projectPoints(
        object_points, rvec, tvec, final_k, ZERO_DISTORTION
    )
    errors = pixel_errors(projected, image_points)

    camera_enu = camera_centre_from_extrinsics(rvec, tvec)
    camera_ecef = enu_to_ecef(camera_enu, origin_lat, origin_lon, origin_alt)
    camera_lat, camera_lon, camera_alt = ecef_to_geodetic(camera_ecef)
    final_vfov = math.degrees(
        2.0 * math.atan(image_height / (2.0 * focal))
    )

    # Physical visibility check: all points used in this fit must have positive
    # camera-space Z. OpenCV's projectPoints can return pixels for negative Z,
    # but those points are behind the camera and cannot be visible.
    camera_points = camera_coordinates(object_points, rvec, tvec)
    camera_depths = camera_points[:, 2]
    in_front, physical_issues, camera_distance_from_origin = camera_physical_checks(
        camera_enu, camera_lat, camera_lon, camera_alt, camera_depths
    )

    return {
        "camera_matrix": final_k,
        "distortion": ZERO_DISTORTION.copy(),
        "rvec": rvec,
        "tvec": tvec,
        "focal_px": focal,
        "vfov_final_deg": final_vfov,
        "camera_enu": camera_enu,
        "camera_lat": camera_lat,
        "camera_lon": camera_lon,
        "camera_alt_ellipsoid_m": camera_alt,
        "camera_depths_m": camera_depths,
        "min_camera_depth_m": float(np.min(camera_depths)),
        "points_behind_camera": int(np.sum(camera_depths <= MIN_POSITIVE_CAMERA_DEPTH_M)),
        "all_points_in_front": bool(in_front),
        "all_points_have_safe_depth": bool(
            np.all(camera_depths >= MIN_SAFE_CAMERA_DEPTH_M)
        ),
        "physical_issues": physical_issues,
        "camera_distance_from_enu_origin_m": camera_distance_from_origin,
        "train_errors_px": errors,
        "train_rmse_px": float(np.sqrt(np.mean(errors**2))),
        "train_mean_error_px": float(np.mean(errors)),
        "optimizer_success": bool(optimized.success),
        "optimizer_status": int(optimized.status),
        "optimizer_message": str(optimized.message),
        "optimizer_nfev": int(optimized.nfev),
    }


def make_fit_record(case_name, vfov_initial, fitted, used_poi_ids,
                    excluded_poi_id=None):
    """Flatten all camera parameters from one fit into a CSV-friendly record."""
    k = np.asarray(fitted["camera_matrix"], dtype=np.float64)
    d = np.asarray(fitted["distortion"], dtype=np.float64).reshape(-1)
    rvec = np.asarray(fitted["rvec"], dtype=np.float64).reshape(3)
    tvec = np.asarray(fitted["tvec"], dtype=np.float64).reshape(3)
    centre = np.asarray(fitted["camera_enu"], dtype=np.float64).reshape(3)

    row = {
        "calibration_case": case_name,
        "excluded_poi_id": excluded_poi_id,
        "poi_ids_used": ";".join(str(int(x)) for x in used_poi_ids),
        "num_points_used": len(used_poi_ids),
        "vfov_initial_deg": float(vfov_initial),
        "vfov_final_deg": float(fitted["vfov_final_deg"]),
        "focal_length_px": float(fitted["focal_px"]),
        "train_rmse_px": float(fitted["train_rmse_px"]),
        "train_mean_error_px": float(fitted["train_mean_error_px"]),
        "optimizer_success": bool(fitted["optimizer_success"]),
        "optimizer_status": int(fitted["optimizer_status"]),
        "optimizer_nfev": int(fitted["optimizer_nfev"]),
        "optimizer_message": fitted["optimizer_message"],
        "camera_east_m": float(centre[0]),
        "camera_north_m": float(centre[1]),
        "camera_up_m": float(centre[2]),
        "camera_lat": float(fitted["camera_lat"]),
        "camera_lon": float(fitted["camera_lon"]),
        "camera_alt_ellipsoid_m": float(fitted["camera_alt_ellipsoid_m"]),
        "camera_distance_from_enu_origin_m": float(
            fitted["camera_distance_from_enu_origin_m"]
        ),
        "min_camera_depth_m": float(fitted["min_camera_depth_m"]),
        "points_behind_camera": int(fitted["points_behind_camera"]),
        "all_points_in_front": bool(fitted["all_points_in_front"]),
        "all_points_have_safe_depth": bool(fitted["all_points_have_safe_depth"]),
        "physical_issues": fitted["physical_issues"],
        "rvec_x": float(rvec[0]),
        "rvec_y": float(rvec[1]),
        "rvec_z": float(rvec[2]),
        "tvec_x": float(tvec[0]),
        "tvec_y": float(tvec[1]),
        "tvec_z": float(tvec[2]),
    }

    for r in range(3):
        for c in range(3):
            row[f"K_{r}{c}"] = float(k[r, c])
    for index, name in enumerate(("k1", "k2", "p1", "p2", "k3")):
        row[name] = float(d[index]) if index < len(d) else 0.0
    for poi_id, error in zip(used_poi_ids, fitted["train_errors_px"]):
        row[f"reprojection_error_POI_{int(poi_id)}_px"] = float(error)
    return row


def run_loo_fold(vfov_initial, all_enu, all_xy, poi_ids, held_out_index,
                 image_width, image_height):
    """Fit all-but-one POIs, then predict the omitted POI and validate its depth."""
    mask = np.ones(len(all_enu), dtype=bool)
    mask[held_out_index] = False
    used_ids = np.asarray(poi_ids)[mask]

    fitted = fit_camera(
        vfov_initial,
        all_enu[mask],
        all_xy[mask],
        image_width,
        image_height,
    )

    held_out_point = all_enu[held_out_index].reshape(1, 3)
    held_out_camera_xyz = camera_coordinates(
        held_out_point, fitted["rvec"], fitted["tvec"]
    )[0]
    held_out_depth = float(held_out_camera_xyz[2])

    held_out_projected, _ = cv2.projectPoints(
        held_out_point.reshape(1, 1, 3),
        fitted["rvec"],
        fitted["tvec"],
        fitted["camera_matrix"],
        fitted["distortion"],
    )
    held_out_error = float(pixel_errors(
        held_out_projected, all_xy[held_out_index].reshape(1, 2)
    )[0])

    held_out_in_front = (
        math.isfinite(held_out_depth)
        and held_out_depth > MIN_POSITIVE_CAMERA_DEPTH_M
    )
    held_out_safe_depth = (
        math.isfinite(held_out_depth)
        and held_out_depth >= MIN_SAFE_CAMERA_DEPTH_M
    )
    physical_ok = bool(
        fitted["all_points_in_front"]
        and held_out_in_front
        and math.isfinite(held_out_error)
    )
    safe_geometry = bool(
        physical_ok
        and fitted["all_points_have_safe_depth"]
        and held_out_safe_depth
    )
    # Three-way diagnostic classification:
    # A = low LOO error and safe geometry;
    # B = low LOO error but physically invalid / near camera plane;
    # C = optimizer failure, non-finite prediction, or high LOO error.
    # Geometry does not suppress the numeric LOO error: it remains recorded
    # and contributes to VFOV scoring whenever optimization completed.
    if not fitted["optimizer_success"]:
        status = "not_converged"
        classification = "C_unsatisfactory"
    elif not math.isfinite(held_out_error):
        status = "non_finite_loo_error"
        classification = "C_unsatisfactory"
    elif (MAX_ACCEPTABLE_LOO_ERROR_PX is not None
          and held_out_error > MAX_ACCEPTABLE_LOO_ERROR_PX):
        status = "high_loo_error"
        classification = "C_unsatisfactory"
    elif safe_geometry:
        status = "ok"
        classification = "A_valid"
    else:
        status = "geometrically_suspect"
        classification = "B_geometrically_suspect"

    record = make_fit_record(
        case_name=f"exclude_POI_{int(poi_ids[held_out_index])}",
        vfov_initial=vfov_initial,
        fitted=fitted,
        used_poi_ids=used_ids,
        excluded_poi_id=int(poi_ids[held_out_index]),
    )
    record["loo_error_px"] = held_out_error
    record["held_out_depth_m"] = held_out_depth
    record["held_out_point_in_front"] = bool(held_out_in_front)
    record["held_out_point_has_safe_depth"] = bool(held_out_safe_depth)
    record["physically_plausible"] = physical_ok
    record["safe_geometry"] = safe_geometry
    record["classification"] = classification
    record["status"] = status
    if (not physical_ok or not safe_geometry or status == "high_loo_error"
            or status == "not_converged"):
        issue_parts = [fitted["physical_issues"]] if fitted["physical_issues"] else []
        if not held_out_in_front:
            issue_parts.append("held-out point is not in front of the camera")
        if not math.isfinite(held_out_error):
            issue_parts.append("non-finite held-out reprojection error")
        elif (MAX_ACCEPTABLE_LOO_ERROR_PX is not None
              and held_out_error > MAX_ACCEPTABLE_LOO_ERROR_PX):
            issue_parts.append(
                f"LOO error {held_out_error:.2f} px exceeds the "
                f"{MAX_ACCEPTABLE_LOO_ERROR_PX:.2f} px high-error threshold"
            )
        if not fitted["all_points_have_safe_depth"]:
            issue_parts.append(
                f"training minimum depth {fitted['min_camera_depth_m']:.4f} m "
                f"is below the {MIN_SAFE_CAMERA_DEPTH_M:.1f} m safety margin"
            )
        if not held_out_safe_depth:
            issue_parts.append(
                f"held-out depth {held_out_depth:.4f} m is below the "
                f"{MIN_SAFE_CAMERA_DEPTH_M:.1f} m safety margin"
            )
        record["physical_issues"] = "; ".join(issue_parts)
    return record

# ---------------------------------------------------------------------------
# 4. PARAMETER STABILITY AND VFOV SELECTION
# ---------------------------------------------------------------------------


def parameter_stability_summary(group, scene_scale_m, total_folds, all_rows):
    """Summarize parameter spread over all optimizer-completed finite LOO fits.

    The input group intentionally includes geometrically suspicious folds and
    high-error folds: their estimates are still useful for measuring sensitivity.
    """
    centres = group[[
        "camera_east_m", "camera_north_m", "camera_up_m"
    ]].to_numpy(dtype=np.float64)
    centre_mean = centres.mean(axis=0)
    position_deviations = np.linalg.norm(centres - centre_mean, axis=1)
    position_rms = float(np.sqrt(np.mean(position_deviations**2)))

    rvecs = group[["rvec_x", "rvec_y", "rvec_z"]].to_numpy(dtype=np.float64)
    orientation_rms = rotation_rms_spread_deg(rvecs)

    final_vfovs = group["vfov_final_deg"].to_numpy(dtype=np.float64)
    focals = group["focal_length_px"].to_numpy(dtype=np.float64)
    vfov_mean = float(np.mean(final_vfovs))
    vfov_std = float(np.std(final_vfovs, ddof=0))
    vfov_initial = float(group["vfov_initial_deg"].iloc[0])
    initial_to_final_vfov_gap = abs(vfov_initial - vfov_mean)
    focal_mean = float(np.mean(focals))
    focal_std = float(np.std(focals, ddof=0))
    focal_cv_pct = 100.0 * focal_std / max(abs(focal_mean), 1e-12)

    # Secondary stability metric. Position is normalized by the POI scene scale;
    # orientation and final VFOV are normalized by configurable comparison scales.
    components = [
        position_rms / max(scene_scale_m * POSITION_SPREAD_SCALE_AS_SCENE_FRACTION, 1e-9),
        orientation_rms / ROTATION_SPREAD_SCALE_DEG,
        vfov_std / VFOV_STD_SCALE_DEG,
    ]
    stability_score = float(np.sqrt(np.mean(np.square(components))))

    safe_flags = group["safe_geometry"].fillna(False).astype(bool)
    # Count A/B/C over ALL folds, including exceptions and optimizer failures.
    # The stability/error metrics below still use only evaluated finite predictions.
    all_class_values = all_rows.get(
        "classification", pd.Series("C_unsatisfactory", index=all_rows.index)
    ).fillna("C_unsatisfactory").astype(str)
    all_status_values = all_rows.get(
        "status", pd.Series("failed", index=all_rows.index)
    ).fillna("failed").astype(str)
    high_error_flags = all_status_values.eq("high_loo_error")
    failed_or_nonfinite = int(total_folds - len(group))
    return {
        # "successful_folds" is retained as an alias for compatibility. It now
        # means evaluated folds, not physically valid folds.
        "successful_folds": int(len(group)),
        "evaluated_folds": int(len(group)),
        "total_folds": int(total_folds),
        "failed_or_nonfinite_folds": failed_or_nonfinite,
        "class_a_valid_folds": int(all_class_values.eq("A_valid").sum()),
        "class_b_suspect_folds": int(all_class_values.eq("B_geometrically_suspect").sum()),
        "class_c_unsatisfactory_folds": int(all_class_values.eq("C_unsatisfactory").sum()),
        "high_error_folds": int(high_error_flags.sum()),
        "safe_geometry_folds": int(safe_flags.sum()),
        "geometrically_suspect_folds": int((~safe_flags).sum()),
        "physically_valid_folds": int(safe_flags.sum()),
        "parameter_stability_score": stability_score,
        "camera_position_rms_spread_m": position_rms,
        "camera_position_max_deviation_m": float(np.max(position_deviations)),
        "camera_orientation_rms_spread_deg": orientation_rms,
        "vfov_final_mean_deg": vfov_mean,
        "vfov_final_std_deg": vfov_std,
        "initial_to_final_vfov_gap_deg": initial_to_final_vfov_gap,
        "focal_length_mean_px": focal_mean,
        "focal_length_std_px": focal_std,
        "focal_length_cv_pct": focal_cv_pct,
        # Critically, these means include A, B and C-high-error folds whenever
        # optimization completed and a finite held-out error was calculated.
        "loo_mean_error_px": float(group["loo_error_px"].mean()),
        "loo_median_error_px": float(group["loo_error_px"].median()),
        "loo_std_error_px": float(group["loo_error_px"].std(ddof=0)),
        "loo_max_error_px": float(group["loo_error_px"].max()),
        "train_rmse_mean_px": float(group["train_rmse_px"].mean()),
    }


def build_vfov_summaries(loo_results, vfov_values, scene_scale_m, total_folds):
    """Summarize each VFOV using every optimizer-completed finite LOO prediction."""
    summaries = []
    for vfov in vfov_values:
        all_rows = loo_results[
            np.isclose(loo_results["vfov_initial_deg"], float(vfov))
        ].copy()

        optimizer_ok = all_rows.get(
            "optimizer_success", pd.Series(False, index=all_rows.index)
        ).fillna(False).astype(bool)
        loo_error = pd.to_numeric(
            all_rows.get("loo_error_px", pd.Series(np.nan, index=all_rows.index)),
            errors="coerce",
        )
        evaluated = all_rows[optimizer_ok & np.isfinite(loo_error)].copy()
        if not evaluated.empty:
            evaluated["loo_error_px"] = pd.to_numeric(
                evaluated["loo_error_px"], errors="coerce"
            )

        base = {
            "vfov_initial_deg": float(vfov),
            "successful_folds": int(len(evaluated)),
            "evaluated_folds": int(len(evaluated)),
            "total_folds": int(total_folds),
            "failed_or_nonfinite_folds": int(total_folds - len(evaluated)),
        }
        if len(evaluated):
            base.update(
                parameter_stability_summary(
                    evaluated, scene_scale_m, total_folds, all_rows
                )
            )
        else:
            base.update({
                "class_a_valid_folds": 0,
                "class_b_suspect_folds": 0,
                "class_c_unsatisfactory_folds": int(
                    all_rows.get("classification", pd.Series("C_unsatisfactory", index=all_rows.index))
                    .fillna("C_unsatisfactory").astype(str).eq("C_unsatisfactory").sum()
                ),
                "high_error_folds": int(
                    all_rows.get("status", pd.Series("failed", index=all_rows.index))
                    .fillna("failed").astype(str).eq("high_loo_error").sum()
                ),
                "safe_geometry_folds": 0,
                "geometrically_suspect_folds": 0,
                "physically_valid_folds": 0,
                "parameter_stability_score": np.nan,
                "camera_position_rms_spread_m": np.nan,
                "camera_position_max_deviation_m": np.nan,
                "camera_orientation_rms_spread_deg": np.nan,
                "vfov_final_mean_deg": np.nan,
                "vfov_final_std_deg": np.nan,
                "initial_to_final_vfov_gap_deg": np.nan,
                "focal_length_mean_px": np.nan,
                "focal_length_std_px": np.nan,
                "focal_length_cv_pct": np.nan,
                "loo_mean_error_px": np.nan,
                "loo_median_error_px": np.nan,
                "loo_std_error_px": np.nan,
                "loo_max_error_px": np.nan,
                "train_rmse_mean_px": np.nan,
            })
        summaries.append(base)

    return pd.DataFrame(summaries).sort_values(
        "vfov_initial_deg"
    ).reset_index(drop=True)

# ---------------------------------------------------------------------------
# 5. FINAL SET OF SEVEN CALIBRATIONS AND PARAMETER COMPARISON TABLE
# ---------------------------------------------------------------------------


def run_final_parameter_cases(vfov, poi_enu, poi_xy, poi_ids,
                              image_width, image_height):
    """Fit all points and each possible one-point exclusion at the selected VFOV."""
    cases = [("all_points", None)]
    cases.extend(
        (f"exclude_POI_{int(poi_id)}", index)
        for index, poi_id in enumerate(poi_ids)
    )

    records = []
    fitted_by_case = {}
    for case_name, excluded_index in cases:
        mask = np.ones(len(poi_ids), dtype=bool)
        excluded_id = None
        if excluded_index is not None:
            mask[excluded_index] = False
            excluded_id = int(poi_ids[excluded_index])

        used_ids = np.asarray(poi_ids)[mask]
        print(f"Final fit: {case_name} ({len(used_ids)} points)")
        try:
            fitted = fit_camera(
                vfov, poi_enu[mask], poi_xy[mask], image_width, image_height
            )
            record = make_fit_record(
                case_name, vfov, fitted, used_ids, excluded_poi_id=excluded_id
            )
            if not fitted["optimizer_success"]:
                record["status"] = "not_converged"
                record["classification"] = "C_unsatisfactory"
            elif not fitted["all_points_in_front"]:
                record["status"] = "physically_invalid"
                record["classification"] = "B_geometrically_suspect"
            elif not fitted["all_points_have_safe_depth"]:
                record["status"] = "near_camera_plane"
                record["classification"] = "B_geometrically_suspect"
                record["physical_issues"] = (
                    f"minimum camera depth {fitted['min_camera_depth_m']:.4f} m "
                    f"is below the {MIN_SAFE_CAMERA_DEPTH_M:.1f} m safety margin"
                )
            else:
                record["status"] = "ok"
                record["classification"] = "A_valid"
            record["physically_plausible"] = bool(fitted["all_points_in_front"])
            record["safe_geometry"] = bool(fitted["all_points_have_safe_depth"])
            records.append(record)
            fitted_by_case[case_name] = fitted
        except (cv2.error, ValueError, RuntimeError, np.linalg.LinAlgError,
                FloatingPointError) as exc:
            records.append({
                "calibration_case": case_name,
                "excluded_poi_id": excluded_id,
                "poi_ids_used": ";".join(str(int(x)) for x in used_ids),
                "num_points_used": int(len(used_ids)),
                "vfov_initial_deg": float(vfov),
                "status": "failed",
                "classification": "C_unsatisfactory",
                "error_message": str(exc).replace("\n", " ")[:500],
            })

    table = pd.DataFrame(records)

    # Compare every successful five-point fit with the all-points fit when that
    # fit exists. The all-points row may itself be physically invalid; its status
    # remains explicit in the table, so these deltas must then be interpreted
    # only as numerical differences, not as differences from a trusted solution.
    reference = fitted_by_case.get("all_points")
    reference_centre = reference["camera_enu"] if reference is not None else None
    reference_rvec = reference["rvec"] if reference is not None else None
    reference_focal = reference["focal_px"] if reference is not None else None
    reference_vfov = reference["vfov_final_deg"] if reference is not None else None
    table["delta_camera_position_vs_all_m"] = np.nan
    table["delta_camera_orientation_vs_all_deg"] = np.nan
    table["delta_focal_length_vs_all_px"] = np.nan
    table["delta_focal_length_vs_all_pct"] = np.nan
    table["delta_vfov_final_vs_all_deg"] = np.nan

    for row_index, row in table.iterrows():
        case_name = row.get("calibration_case")
        if case_name not in fitted_by_case or reference is None:
            continue
        fitted = fitted_by_case[case_name]
        table.loc[row_index, "delta_camera_position_vs_all_m"] = float(
            np.linalg.norm(fitted["camera_enu"] - reference_centre)
        )
        table.loc[row_index, "delta_camera_orientation_vs_all_deg"] = rotation_difference_deg(
            fitted["rvec"], reference_rvec
        )
        focal_delta = float(fitted["focal_px"] - reference_focal)
        table.loc[row_index, "delta_focal_length_vs_all_px"] = focal_delta
        table.loc[row_index, "delta_focal_length_vs_all_pct"] = (
            100.0 * focal_delta / max(abs(reference_focal), 1e-12)
        )
        table.loc[row_index, "delta_vfov_final_vs_all_deg"] = float(
            fitted["vfov_final_deg"] - reference_vfov
        )

    return table, fitted_by_case

# ---------------------------------------------------------------------------
# 6. MAIN
# ---------------------------------------------------------------------------


def main():
    if not IMAGE_PATH.exists():
        raise FileNotFoundError(
            f"Image not found: {IMAGE_PATH}\n"
            "Put Boston_Harbor.png in the Boston_Harbor subfolder or update IMAGE_PATH."
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    image = Image.open(IMAGE_PATH).convert("RGB")
    image_width, image_height = image.size
    print(f"Image used: {IMAGE_PATH.name} ({image_width} x {image_height} px)")

    if len(poi_data) < 5:
        raise ValueError("At least five POIs are required for Leave-One-Out.")
    if poi_data["id"].duplicated().any():
        raise ValueError("POI IDs must be unique.")

    poi_ids = poi_data["id"].to_numpy(dtype=int)
    poi_xy = poi_data[["img_x", "img_y"]].to_numpy(dtype=np.float64)

    # Reject POIs outside this exact image. Their pixel coordinates must be
    # re-measured on the current screenshot; they must not be silently omitted.
    outside = (
        (poi_xy[:, 0] < 0) | (poi_xy[:, 0] >= image_width)
        | (poi_xy[:, 1] < 0) | (poi_xy[:, 1] >= image_height)
    )
    if np.any(outside):
        bad = poi_data.loc[outside, ["id", "img_x", "img_y"]]
        details = "; ".join(
            f"POI {int(row.id)}=({int(row.img_x)}, {int(row.img_y)})"
            for row in bad.itertuples(index=False)
        )
        raise ValueError(
            "Some POI image coordinates are outside the loaded image: "
            f"{details}.\n"
            f"Image bounds: x=0..{image_width - 1}, y=0..{image_height - 1}.\n"
            "Re-measure img_x/img_y on this exact image before calibrating."
        )

    poi_enu = gps_to_enu(
        poi_data["map_lat"].to_numpy(),
        poi_data["map_lng"].to_numpy(),
        poi_data["map_altitude"].to_numpy(),
        origin_lat, origin_lon, origin_alt,
    )
    scene_centre = poi_enu.mean(axis=0)
    scene_scale_m = float(np.sqrt(np.mean(np.sum((poi_enu - scene_centre) ** 2, axis=1))))
    scene_scale_m = max(scene_scale_m, 1.0)

    # Determine which initial VFOV to use. LOO always runs, even for a manual VFOV.
    if MANUAL_VFOV_DEG is not None:
        vfov_values = np.array([float(MANUAL_VFOV_DEG)], dtype=np.float64)
        if not 0.0 < vfov_values[0] < 180.0:
            raise ValueError("MANUAL_VFOV_DEG must be between 0 and 180 degrees.")
        print(f"Manual initial VFOV: {vfov_values[0]:.3f} degrees")
    else:
        vfov_values = np.arange(
            VFOV_MIN_DEG,
            VFOV_MAX_DEG + VFOV_STEP_DEG * 0.5,
            VFOV_STEP_DEG,
            dtype=np.float64,
        )
        if len(vfov_values) == 0 or np.any((vfov_values <= 0) | (vfov_values >= 180)):
            raise ValueError("Check VFOV_MIN_DEG, VFOV_MAX_DEG and VFOV_STEP_DEG.")
        print(
            f"Automatic VFOV sweep: {len(vfov_values)} values, "
            f"{VFOV_MIN_DEG:.1f} to {VFOV_MAX_DEG:.1f} degrees, "
            f"step {VFOV_STEP_DEG:.1f} degrees"
        )

    loo_rows = []
    total_runs = len(vfov_values) * len(poi_ids)
    run_no = 0
    print(f"Running Leave-One-Out: {len(poi_ids)} folds per VFOV; {total_runs} fits.")

    for vfov in vfov_values:
        for held_out_index, held_out_id in enumerate(poi_ids):
            run_no += 1
            try:
                record = run_loo_fold(
                    float(vfov), poi_enu, poi_xy, poi_ids,
                    held_out_index, image_width, image_height,
                )
                loo_rows.append(record)
            except (cv2.error, ValueError, RuntimeError, np.linalg.LinAlgError,
                    FloatingPointError) as exc:
                loo_rows.append({
                    "calibration_case": f"exclude_POI_{int(held_out_id)}",
                    "excluded_poi_id": int(held_out_id),
                    "num_points_used": int(len(poi_ids) - 1),
                    "vfov_initial_deg": float(vfov),
                    "status": "failed",
                    "classification": "C_unsatisfactory",
                    "optimizer_success": False,
                    "error_message": str(exc).replace("\n", " ")[:500],
                })
            if run_no % 30 == 0 or run_no == total_runs:
                print(f"Completed {run_no}/{total_runs} LOO fits...")

    loo_results = pd.DataFrame(loo_rows)
    loo_results.to_csv(LOO_RESULTS_CSV, index=False)
    print(f"LOO parameter results saved to: {LOO_RESULTS_CSV}")

    vfov_summary = build_vfov_summaries(
        loo_results, vfov_values, scene_scale_m, total_folds=len(poi_ids)
    )
    vfov_summary.to_csv(VFOV_SUMMARY_CSV, index=False)

    required_folds = (
        len(poi_ids)
        if MIN_SUCCESSFUL_FOLDS_FOR_RANKING is None
        else int(MIN_SUCCESSFUL_FOLDS_FOR_RANKING)
    )
    eligible = vfov_summary[
        vfov_summary["evaluated_folds"] >= required_folds
    ].copy()

    best_summary = None
    if MANUAL_VFOV_DEG is None:
        if eligible.empty:
            # The CSVs have already been written. Do not fail silently: show the
            # number of completed predictions and retain all diagnostics.
            best_available = vfov_summary.sort_values(
                ["evaluated_folds", "loo_mean_error_px"],
                ascending=[False, True],
                na_position="last",
            ).head(10)
            print("\nNo VFOV met the minimum number of evaluated LOO folds.")
            print(best_available[[
                "vfov_initial_deg", "evaluated_folds", "safe_geometry_folds",
                "class_b_suspect_folds", "high_error_folds", "loo_mean_error_px",
            ]].to_string(index=False))
            raise RuntimeError(
                f"No VFOV has at least {required_folds} optimizer-completed "
                "LOO predictions with finite reprojection error. The CSV files "
                "contain the available diagnostics."
            )

        # Primary criterion: lowest mean LOO error using ALL evaluated folds,
        # including geometrically suspect folds and folds classified as C due
        # to high reprojection error. No finite error is discarded for geometry.
        minimum_loo_error = float(eligible["loo_mean_error_px"].min())
        near_best = eligible[
            eligible["loo_mean_error_px"]
            <= minimum_loo_error + LOO_ERROR_TIE_TOLERANCE_PX
        ].copy()

        # Secondary criterion 1: among near-equal LOO errors, prefer more folds
        # with safe positive depth. If none are safe, retain the best mathematical
        # candidate but clearly flag it as geometrically unvalidated.
        max_safe_folds = int(near_best["safe_geometry_folds"].max())
        geometry_preferred = near_best[
            near_best["safe_geometry_folds"] == max_safe_folds
        ].copy()

        # Secondary criterion 2: choose the most stable camera parameters.
        min_stability = float(
            geometry_preferred["parameter_stability_score"].min()
        )
        stability_tolerance = STABILITY_SCORE_TIE_TOLERANCE * max(
            1.0, abs(min_stability)
        )
        stable_candidates = geometry_preferred[
            geometry_preferred["parameter_stability_score"]
            <= min_stability + stability_tolerance
        ].copy()
        best_summary = stable_candidates.sort_values(
            [
                "initial_to_final_vfov_gap_deg",
                "parameter_stability_score",
                "loo_mean_error_px",
            ]
        ).iloc[0]
        best_vfov = float(best_summary["vfov_initial_deg"])

        print(
            f"Selected initial VFOV: {best_vfov:.3f} degrees "
            f"(mean LOO error {best_summary['loo_mean_error_px']:.3f} px)"
        )
        if len(near_best) > 1:
            print(
                f"{len(near_best)} VFOV value(s) are within "
                f"{LOO_ERROR_TIE_TOLERANCE_PX:.3f} px of the lowest LOO error; "
                "safe-geometry fold count and then parameter stability were "
                "used as secondary criteria."
            )
        if int(best_summary["safe_geometry_folds"]) == 0:
            warnings.warn(
                "The selected VFOV is the best mathematical candidate by LOO "
                "error, but none of its folds has fully safe geometry. It is "
                "diagnostic only; automatic NPZ saving will require a physically "
                "validated calibration."
            )
        if len(stable_candidates) > 1:
            print(
                "Stability scores are effectively tied. The script used the "
                "initial VFOV closest to the mean converged VFOV as a deterministic "
                "tie-break; this does not prove that the starting VFOV is unique."
            )
        if math.isclose(best_vfov, float(vfov_values.min())) or math.isclose(
            best_vfov, float(vfov_values.max())
        ):
            warnings.warn(
                "The selected VFOV is at the edge of the search interval. "
                "Consider extending VFOV_MIN_DEG/VFOV_MAX_DEG and repeating the sweep."
            )
    else:
        best_vfov = float(MANUAL_VFOV_DEG)
        matching = vfov_summary[
            np.isclose(vfov_summary["vfov_initial_deg"], best_vfov)
        ]
        if not matching.empty:
            best_summary = matching.iloc[0]
            if int(best_summary["evaluated_folds"]) < len(poi_ids):
                warnings.warn(
                    f"Only {int(best_summary['evaluated_folds'])}/{len(poi_ids)} "
                    "LOO folds produced finite errors after optimizer completion. "
                    "Geometric validity is reported separately."
                )
            if int(best_summary["safe_geometry_folds"]) == 0:
                warnings.warn(
                    "None of the manual-VFOV LOO folds has fully safe geometry. "
                    "Their errors remain available for diagnostics, but they do "
                    "not validate an automatic camera-parameter export."
                )
        print(f"Using manual initial VFOV: {best_vfov:.3f} degrees")

    print("\n========== LOO RESULTS: ERROR FIRST, GEOMETRY + STABILITY DIAGNOSTICS ==========")
    report_columns = [
        "vfov_initial_deg", "evaluated_folds", "class_a_valid_folds",
        "class_b_suspect_folds", "class_c_unsatisfactory_folds",
        "high_error_folds", "loo_mean_error_px", "loo_std_error_px",
        "safe_geometry_folds", "parameter_stability_score",
        "camera_position_rms_spread_m", "camera_orientation_rms_spread_deg",
        "vfov_final_std_deg", "focal_length_cv_pct",
    ]
    print(vfov_summary[report_columns].to_string(
        index=False, float_format=lambda value: f"{value:.4f}"
    ))

    # Show each individual fold so it is clear which omitted POI caused an
    # invalid/unstable camera solution and how well it was predicted.
    loo_display_columns = [
        "excluded_poi_id", "loo_error_px", "classification", "held_out_depth_m",
        "min_camera_depth_m", "vfov_final_deg", "focal_length_px",
        "held_out_point_has_safe_depth", "status", "physical_issues",
    ]
    loo_display_columns = [
        column for column in loo_display_columns if column in loo_results.columns
    ]
    print("\n================ INDIVIDUAL LEAVE-ONE-OUT FOLDS ================")
    print(loo_results[loo_display_columns].to_string(
        index=False, float_format=lambda value: f"{value:.4f}"
    ))
    print("\nSelection hierarchy:")
    print("  1. Primary: lowest mean LOO reprojection error across every optimizer-completed finite prediction, regardless of geometry.")
    print("  2. Among VFOV values within the LOO error tolerance, prefer more folds with safe geometry.")
    print("  3. If still tied, prefer lower parameter instability.")
    print("  Fold classes: A = low error + safe geometry; B = low error + suspicious geometry; C = high error / failed optimization.")
    if MAX_ACCEPTABLE_LOO_ERROR_PX is None:
        print("  Type-C high-error flag: disabled.")
    else:
        print(f"  Type-C high-error threshold: {MAX_ACCEPTABLE_LOO_ERROR_PX:.1f} px (high-error folds still contribute to mean LOO).")
    if best_summary is not None:
        print(
            f"Selected VFOV: {best_vfov:.3f} deg | "
            f"mean LOO error: {best_summary['loo_mean_error_px']:.3f} px | "
            f"safe-geometry folds: {int(best_summary['safe_geometry_folds'])}/"
            f"{int(best_summary['total_folds'])} | "
            f"stability score: {best_summary['parameter_stability_score']:.5f}"
        )
    else:
        print(f"Selected manual VFOV: {best_vfov:.3f} deg")

    # With the chosen VFOV, fit the camera in all seven data configurations:
    # all six points, then each of the six possible five-point subsets.
    comparison_table, fitted_by_case = run_final_parameter_cases(
        best_vfov, poi_enu, poi_xy, poi_ids, image_width, image_height
    )
    comparison_table.to_csv(PARAMETER_COMPARISON_CSV, index=False)
    print(f"\nCamera parameter comparison table saved to: {PARAMETER_COMPARISON_CSV}")

    display_columns = [
        "calibration_case", "poi_ids_used", "vfov_final_deg", "focal_length_px",
        "camera_lat", "camera_lon", "camera_alt_ellipsoid_m", "train_rmse_px",
        "min_camera_depth_m", "points_behind_camera", "all_points_in_front",
        "all_points_have_safe_depth", "classification", "physical_issues", "status",
        "camera_distance_from_enu_origin_m",
        "delta_camera_position_vs_all_m",
        "delta_camera_orientation_vs_all_deg",
        "delta_vfov_final_vs_all_deg",
    ]
    available_columns = [column for column in display_columns if column in comparison_table.columns]
    print("\n======= CAMERA PARAMETERS: ALL POINTS VS EACH EXCLUSION =======")
    print(comparison_table[available_columns].to_string(
        index=False, float_format=lambda value: f"{value:.4f}"
    ))

    # Select which calibrated parameter set is written to the NPZ.
    # LOO scoring includes suspicious folds, but an automatic export is only
    # allowed when there is at least one Type-A (fully safe) validation fold.
    selected_case = None
    if NPZ_CALIBRATION_CASE == "auto_best_valid":
        selected_vfov_loo = loo_results[
            np.isclose(loo_results["vfov_initial_deg"], best_vfov)
        ].copy()
        type_a_loo = selected_vfov_loo[
            selected_vfov_loo.get(
                "classification", pd.Series("", index=selected_vfov_loo.index)
            ).astype(str).eq("A_valid")
        ].copy()

        if type_a_loo.empty:
            print(
                "\nWARNING: the selected VFOV has no Type-A LOO validation "
                "folds (low error and safe geometry). No NPZ will be written. "
                "The best mathematical candidate and all CSV diagnostics are "
                "still available for inspection."
            )
        else:
            all_points_row = comparison_table[
                comparison_table["calibration_case"].astype(str).eq("all_points")
            ]
            all_points_safe = (
                not all_points_row.empty
                and str(all_points_row.iloc[0].get("status", "failed")) == "ok"
                and bool(all_points_row.iloc[0].get("safe_geometry", False))
            )
            if all_points_safe:
                selected_case = "all_points"
                print(
                    "\nNPZ auto-selection: all_points is a Type-A final fit and "
                    "the selected VFOV has at least one Type-A LOO validation fold."
                )
            else:
                valid_final_cases = comparison_table[
                    comparison_table["status"].astype(str).eq("ok")
                    & comparison_table["safe_geometry"].fillna(False).astype(bool)
                    & comparison_table["calibration_case"].astype(str).str.startswith("exclude_POI_")
                ].copy()
                type_a_loo = type_a_loo[
                    pd.to_numeric(type_a_loo.get("loo_error_px"), errors="coerce").notna()
                    & (pd.to_numeric(type_a_loo.get("held_out_depth_m"), errors="coerce")
                       >= MIN_SAFE_CAMERA_DEPTH_M)
                    & (pd.to_numeric(type_a_loo.get("min_camera_depth_m"), errors="coerce")
                       >= MIN_SAFE_CAMERA_DEPTH_M)
                ].copy()
                if not valid_final_cases.empty and not type_a_loo.empty:
                    candidates = valid_final_cases.merge(
                        type_a_loo[["calibration_case", "loo_error_px"]],
                        on="calibration_case",
                        how="inner",
                    )
                    if not candidates.empty:
                        candidates = candidates.sort_values(
                            ["loo_error_px", "train_rmse_px"],
                            ascending=[True, True],
                        )
                        selected_case = str(candidates.iloc[0]["calibration_case"])
                        excluded_id = int(candidates.iloc[0]["excluded_poi_id"])
                        selected_loo_error = float(candidates.iloc[0]["loo_error_px"])
                        print(
                            "\nWARNING: the all-points final fit is not Type A. "
                            "The NPZ will use the safest validated five-point subset."
                        )
                        print(
                            f"NPZ auto-selection: {selected_case} "
                            f"(excluded POI {excluded_id}; Type-A LOO error "
                            f"{selected_loo_error:.3f} px)."
                        )
                if selected_case is None:
                    print(
                        "\nWARNING: Type-A LOO folds exist, but no corresponding "
                        "five-point final fit passed the safe-geometry checks. "
                        "No NPZ was written; inspect the CSV tables and POI data."
                    )
    else:
        selected_case = NPZ_CALIBRATION_CASE
        if selected_case not in fitted_by_case:
            available_cases = ", ".join(sorted(fitted_by_case)) or "none"
            print(
                f"\nWARNING: requested NPZ case '{selected_case}' is unavailable. "
                f"Successful optimizer cases: {available_cases}. No NPZ was written."
            )
            selected_case = None
        elif not fitted_by_case[selected_case]["optimizer_success"]:
            print(
                f"\nWARNING: requested NPZ case '{selected_case}' did not converge. "
                "No NPZ was written."
            )
            selected_case = None
        elif not fitted_by_case[selected_case]["all_points_in_front"]:
            issues = fitted_by_case[selected_case]["physical_issues"]
            print(
                f"\nWARNING: requested NPZ case '{selected_case}' is physically "
                f"invalid ({issues}). No NPZ was written. Set "
                "NPZ_CALIBRATION_CASE='auto_best_valid' or choose a Type-A case "
                "from camera_parameter_comparison.csv."
            )
            selected_case = None
        elif not fitted_by_case[selected_case]["all_points_have_safe_depth"]:
            print(
                f"\nWARNING: requested NPZ case '{selected_case}' contains a POI "
                f"closer than {MIN_SAFE_CAMERA_DEPTH_M:.1f} m to the camera plane. "
                "This is a near-degenerate projection, so no NPZ was written."
            )
            selected_case = None

    if selected_case is None:
        print("\nNo camera_boston.npz was written in this run.")
        if OUTPUT_FILE.exists():
            print(
                f"WARNING: an older file already exists at {OUTPUT_FILE}. "
                "It was left untouched and may contain parameters from a previous run. "
                "Do not use it as the result of this calibration."
            )
    else:
        final = fitted_by_case[selected_case]
        selected_record = comparison_table[
            comparison_table["calibration_case"] == selected_case
        ].iloc[0]
        used_poi_ids = np.array(
            [int(value) for value in str(selected_record["poi_ids_used"]).split(";")],
            dtype=np.int32,
        )

        np.savez(
            OUTPUT_FILE,
            intrinsics=np.asarray(final["camera_matrix"], dtype=np.float64),
            distortion=np.asarray(final["distortion"], dtype=np.float64).reshape(1, 5),
            image_size=np.array([image_width, image_height], dtype=np.int32),
            rvec=np.asarray(final["rvec"], dtype=np.float64).reshape(3, 1),
            tvec=np.asarray(final["tvec"], dtype=np.float64).reshape(3, 1),
            origin_lat=np.array(origin_lat, dtype=np.float64),
            origin_lon=np.array(origin_lon, dtype=np.float64),
            origin_alt=np.array(origin_alt, dtype=np.float64),
            camera_center_enu=np.asarray(final["camera_enu"], dtype=np.float64).reshape(3),
            vfov_initial_deg=np.array(best_vfov, dtype=np.float64),
            vfov_final_deg=np.array(final["vfov_final_deg"], dtype=np.float64),
            focal_length_px=np.array(final["focal_px"], dtype=np.float64),
            calibration_case=np.array(selected_case),
            poi_ids_used=used_poi_ids,
        )

        print("\n================ NPZ SAVED ================")
        print(f"Selected calibration case: {selected_case}")
        print(f"Parameters saved to: {OUTPUT_FILE}")
        print("Fields: intrinsics, distortion, image_size, rvec, tvec, ENU origin, "
              "camera centre, VFOV, focal length, calibration case and POI IDs.")
        print("\nOutput tables:")
        print(f"  LOO parameter results:       {LOO_RESULTS_CSV}")
        print(f"  VFOV parameter stability:    {VFOV_SUMMARY_CSV}")
        print(f"  Final parameter comparison:  {PARAMETER_COMPARISON_CSV}")


if __name__ == "__main__":
    main()
