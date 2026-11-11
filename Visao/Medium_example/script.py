# https://medium.com/@rohith.sunkara/reconstructing-the-real-world-estimating-camera-position-from-images-and-gps-coordinates-6fd79009af28

from pathlib import Path
import math
import cv2
import numpy as np
import pandas as pd
from PIL import Image
from scipy.optimize import least_squares

# ---------------------------------------------------------------------------
# 1. FILES, CAMERA ORIGIN, POIS AND SEARCH INTERVAL
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
IMAGE_PATH = BASE_DIR / "Boston_Harbor.png"

# Local ENU origin (WGS84 latitude, longitude, altitude in metres).
origin_lat = 42.35256
origin_lon = -71.0465
origin_alt = 50.0

poi_data = pd.DataFrame({
    "id": [1, 2, 3, 4, 5, 6],
    "img_x": [357, 568, 630, 1006, 1068, 1245],
    "img_y": [734, 635, 666, 656, 673, 729],
    "map_lat": [42.352778, 42.349580, 42.351944,
                42.355556, 42.356111, 42.357500],
    "map_lng": [-71.045000, -71.075236, -71.055833,
                -71.051667, -71.051389, -71.050278],
    "map_altitude": [63, 240, 119, 134, 119, 75],
})

VFOV_MIN_DEG = 20.0
VFOV_MAX_DEG = 120.0
VFOV_STEP_DEG = 5.0

MAX_OPTIMIZER_EVALUATIONS = 1200
OPTIMIZER_TOLERANCE = 1e-8
MIN_SUCCESSFUL_FOLDS_FOR_RANKING = 4

# Camera model assumptions: square pixels, principal point at image centre,
# zero lens distortion. The optimization estimates one focal length (fx = fy).
ZERO_DISTORTION = np.zeros((5, 1), dtype=np.float64)

# ---------------------------------------------------------------------------
# 2. WGS84 / ENU CONVERSIONS
# ---------------------------------------------------------------------------

WGS84_A = 6378137.0
WGS84_F = 1.0 / 298.257223563
WGS84_E2 = WGS84_F * (2.0 - WGS84_F)
WGS84_B = WGS84_A * (1.0 - WGS84_F)
WGS84_EP2 = (WGS84_A**2 - WGS84_B**2) / WGS84_B**2

def geodetic_to_ecef(lat_deg, lon_deg, altitude_m):
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
    if not 0.0 < vfov_deg < 180.0:
        raise ValueError("VFOV must be between 0 and 180 degrees (exclusive).")
    focal_px = 0.5 * image_height / math.tan(math.radians(vfov_deg) / 2.0)
    return np.array([
        [focal_px, 0.0, image_width / 2.0],
        [0.0, focal_px, image_height / 2.0],
        [0.0, 0.0, 1.0],
    ], dtype=np.float64)

def camera_centre_from_extrinsics(rvec, tvec):
    rotation, _ = cv2.Rodrigues(rvec)
    return (-rotation.T @ np.asarray(tvec).reshape(3, 1)).reshape(3)

def pixel_errors(projected, observed):
    projected = np.asarray(projected, dtype=np.float64).reshape(-1, 2)
    observed = np.asarray(observed, dtype=np.float64).reshape(-1, 2)
    return np.linalg.norm(projected - observed, axis=1)

def fit_camera(vfov_initial, object_points, image_points,
               image_width, image_height):
    """Fit pose + one focal length, starting from the supplied initial VFOV."""
    object_points = np.asarray(object_points, dtype=np.float64).reshape(-1, 3)
    image_points = np.asarray(image_points, dtype=np.float64).reshape(-1, 2)

    if len(object_points) < 4:
        raise ValueError("At least four 3D-2D correspondences are required.")

    initial_k = make_camera_matrix(vfov_initial, image_width, image_height)

    # SQPNP supports a small number of points; fall back to EPNP if necessary.
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
        "train_errors_px": errors,
        "train_rmse_px": float(np.sqrt(np.mean(errors**2))),
        "train_mean_error_px": float(np.mean(errors)),
        "optimizer_success": bool(optimized.success),
        "optimizer_message": str(optimized.message),
    }

def run_loo_fold(vfov_initial, all_enu, all_xy, held_out_index,
                 image_width, image_height):
    mask = np.ones(len(all_enu), dtype=bool)
    mask[held_out_index] = False

    fitted = fit_camera(
        vfov_initial,
        all_enu[mask],
        all_xy[mask],
        image_width,
        image_height,
    )

    held_out_projected, _ = cv2.projectPoints(
        all_enu[held_out_index].reshape(1, 1, 3),
        fitted["rvec"],
        fitted["tvec"],
        fitted["camera_matrix"],
        fitted["distortion"],
    )
    held_out_error = float(pixel_errors(
        held_out_projected, all_xy[held_out_index].reshape(1, 2)
    )[0])

    return {
        "loo_error_px": held_out_error,
        "camera_enu": fitted["camera_enu"],
        "vfov_final_deg": fitted["vfov_final_deg"],
        "focal_px": fitted["focal_px"],
        "train_rmse_px": fitted["train_rmse_px"],
        "optimizer_success": fitted["optimizer_success"],
    }

# ---------------------------------------------------------------------------
# 4. MAIN: VALIDATE INPUT, SELECT VFOV, THEN FIT USING ALL POIS
# ---------------------------------------------------------------------------

def main():
    if not IMAGE_PATH.exists():
        raise FileNotFoundError(
            f"Image not found: {IMAGE_PATH}\n"
            "Put Boston_Harbor.png next to script.py or update IMAGE_PATH."
        )

    image = Image.open(IMAGE_PATH).convert("RGB")
    image_width, image_height = image.size
    print(f"Image used: {IMAGE_PATH.name} ({image_width} x {image_height} px)")

    if len(poi_data) < 5:
        raise ValueError("At least five POIs are required for this LOO setup.")

    poi_xy = poi_data[["img_x", "img_y"]].to_numpy(dtype=np.float64)

    # Crucial: do not calibrate with image points outside the actual image.
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
            "Re-measure img_x/img_y on this exact screenshot. The coordinates "
            "from the article cannot be reused blindly on a different frame, "
            "crop, or resolution. Do not simply ignore this warning."
        )

    poi_enu = gps_to_enu(
        poi_data["map_lat"].to_numpy(),
        poi_data["map_lng"].to_numpy(),
        poi_data["map_altitude"].to_numpy(),
        origin_lat,
        origin_lon,
        origin_alt,
    )

    vfov_values = np.arange(
        VFOV_MIN_DEG,
        VFOV_MAX_DEG + VFOV_STEP_DEG * 0.5,
        VFOV_STEP_DEG,
        dtype=np.float64,
    )

    rows = []
    total = len(vfov_values) * len(poi_data)
    run_no = 0
    print(f"Testing {len(vfov_values)} VFOV values; {total} LOO calibrations.")

    for vfov in vfov_values:
        for held_out_index in range(len(poi_data)):
            run_no += 1
            try:
                result = run_loo_fold(
                    float(vfov), poi_enu, poi_xy, held_out_index,
                    image_width, image_height,
                )
                rows.append({
                    "vfov_initial_deg": float(vfov),
                    "held_out_poi_id": int(poi_data.iloc[held_out_index]["id"]),
                    "loo_error_px": result["loo_error_px"],
                    "train_rmse_px": result["train_rmse_px"],
                    "vfov_final_deg": result["vfov_final_deg"],
                    "focal_px": result["focal_px"],
                    "camera_east_m": float(result["camera_enu"][0]),
                    "camera_north_m": float(result["camera_enu"][1]),
                    "camera_up_m": float(result["camera_enu"][2]),
                    "optimizer_success": result["optimizer_success"],
                    "status": "ok" if result["optimizer_success"] else "not_converged",
                })
            except (cv2.error, ValueError, RuntimeError,
                    np.linalg.LinAlgError, FloatingPointError) as exc:
                rows.append({
                    "vfov_initial_deg": float(vfov),
                    "held_out_poi_id": int(poi_data.iloc[held_out_index]["id"]),
                    "status": "failed",
                    "error_message": str(exc).replace("\n", " ")[:400],
                })

            if run_no % 30 == 0 or run_no == total:
                print(f"Completed {run_no}/{total} calibrations...")

    detailed = pd.DataFrame(rows)

    valid = detailed[detailed["status"] == "ok"].copy()
    summary_rows = []
    for vfov, group in valid.groupby("vfov_initial_deg"):
        centres = group[[
            "camera_east_m", "camera_north_m", "camera_up_m"
        ]].to_numpy(dtype=np.float64)
        mean_centre = centres.mean(axis=0)
        deviations = np.linalg.norm(centres - mean_centre, axis=1)
        summary_rows.append({
            "vfov_initial_deg": float(vfov),
            "successful_folds": int(len(group)),
            "loo_mean_error_px": float(group["loo_error_px"].mean()),
            "loo_median_error_px": float(group["loo_error_px"].median()),
            "loo_std_error_px": float(group["loo_error_px"].std(ddof=0)),
            "camera_position_rms_spread_m": float(
                np.sqrt(np.mean(deviations**2))
            ),
            "vfov_final_mean_deg": float(group["vfov_final_deg"].mean()),
            "focal_mean_px": float(group["focal_px"].mean()),
        })

    if not summary_rows:
        raise RuntimeError(
            "No VFOV value produced a successful LOO calibration."
        )

    summary = pd.DataFrame(summary_rows).sort_values(
        "vfov_initial_deg"
    ).reset_index(drop=True)

    eligible = summary[
        summary["successful_folds"] >= MIN_SUCCESSFUL_FOLDS_FOR_RANKING
    ].copy()
    if eligible.empty:
        raise RuntimeError(
            "No tested VFOV has enough successful LOO folds to rank it."
        )

    # Lowest held-out prediction error wins; camera-position spread breaks ties.
    best = eligible.sort_values(
        ["loo_mean_error_px", "camera_position_rms_spread_m"]
    ).iloc[0]
    best_vfov = float(best["vfov_initial_deg"])

    # Refit once using ALL POIs to obtain one definitive set of camera params.
    final = fit_camera(
        best_vfov, poi_enu, poi_xy, image_width, image_height
    )

    print("\n================ BEST INITIAL VFOV ================")
    print(f"Best initial VFOV:             {best_vfov:.3f} deg")
    print(f"Mean LOO prediction error:      {best['loo_mean_error_px']:.3f} px")
    print(f"LOO error standard deviation:  {best['loo_std_error_px']:.3f} px")
    print(f"Camera-position RMS spread:    {best['camera_position_rms_spread_m']:.3f} m")

    print("\n======= FINAL CAMERA FIT (USING ALL POIs) =======")
    print(f"Final calibrated VFOV:         {final['vfov_final_deg']:.3f} deg")
    print(f"Focal length (fx = fy):        {final['focal_px']:.3f} px")
    print(f"Training reprojection RMSE:    {final['train_rmse_px']:.3f} px")
    print("Camera intrinsic matrix K:")
    print(np.array2string(final["camera_matrix"], precision=4, suppress_small=True))
    print("Distortion coefficients (k1, k2, p1, p2, k3):")
    print(np.array2string(final["distortion"].reshape(-1), precision=6))
    print("Rotation vector rvec:")
    print(np.array2string(final["rvec"].reshape(-1), precision=6))
    print("Translation vector tvec (ENU world -> camera):")
    print(np.array2string(final["tvec"].reshape(-1), precision=6))
    print("Camera centre in ENU (east, north, up):")
    print(np.array2string(final["camera_enu"], precision=3))
    print("Camera centre in WGS84:")
    print(f"  Latitude:  {final['camera_lat']:.8f} deg")
    print(f"  Longitude: {final['camera_lon']:.8f} deg")
    print(f"  Altitude:  {final['camera_alt_ellipsoid_m']:.3f} m (ellipsoid)")

if __name__ == "__main__":
    main()
