"""Project GPS/3D world points into an image using camera_boston.npz.

Run this script in the same folder as:
  - camera_boston.npz  (created by script_calibracao.py)
  - Boston_Harbor.png (the exact image used during calibration)

Edit POINTS_GPS below. The six default points are the calibration POIs and are
included only as a sanity check. Replace them with new GPS points to project
other objects into the image.
"""

from pathlib import Path
import csv
import math

import cv2
import numpy as np


# ---------------------------------------------------------------------------
# FILES AND INPUT POINTS
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
PARAMS_FILE = BASE_DIR / "Boston_Harbor/best_camera_boston.npz"
IMAGE_FILE = BASE_DIR / "Boston_Harbor/Boston_Harbor.png"
OUTPUT_IMAGE = BASE_DIR / "Boston_Harbor/best_reprojected_points.png"
OUTPUT_CSV = BASE_DIR / "Boston_Harbor/best_reprojected_points.csv"

# Points to project, expressed as WGS84 latitude, longitude and altitude (metres).
# These six points are the calibration POIs from script_calibracao.py, useful for
# checking the workflow. Replace/add entries to project new real-world points.
POINTS_GPS = [
    {"id": "POI 1 (check)", "lat": 42.352778, "lon": -71.045000, "alt": 63.0},
    {"id": "POI 2 (check)", "lat": 42.349580, "lon": -71.075236, "alt": 240.0},
    {"id": "POI 3 (check)", "lat": 42.351944, "lon": -71.055833, "alt": 119.0},
    {"id": "POI 4 (check)", "lat": 42.355556, "lon": -71.051667, "alt": 134.0},
    {"id": "POI 5 (check)", "lat": 42.356111, "lon": -71.051389, "alt": 119.0},
    {"id": "POI 6 (check)", "lat": 42.357500, "lon": -71.050278, "alt": 75.0},
]

# Observed / correct image positions of the six calibration POIs (pixels).
# These are drawn as dark-blue crosses, while GPS-projected positions are red circles.
# Keep this list in the same order as POINTS_GPS.
OBSERVED_IMAGE_POINTS = [
    {"id": "POI 1", "x": 357, "y": 734},
    {"id": "POI 2", "x": 568, "y": 635},
    {"id": "POI 3", "x": 630, "y": 666},
    {"id": "POI 4", "x": 1006, "y": 656},
    {"id": "POI 5", "x": 1068, "y": 673},
    {"id": "POI 6", "x": 1245, "y": 729},
]

# Drawing options (OpenCV uses BGR colour order).
PROJECTED_POINT_COLOR = (0, 0, 255)       # red circles: GPS projection
OBSERVED_POINT_COLOR = (100, 0, 0)        # dark-blue crosses: measured image positions
POINT_RADIUS_PX = 7
OBSERVED_CROSS_SIZE_PX = 24
OBSERVED_CROSS_THICKNESS = 3
FONT_SCALE = 0.55
DRAW_LABELS = True
DRAW_OBSERVED_LABELS = True


# ---------------------------------------------------------------------------
# WGS84 GPS -> ECEF -> local ENU
# Must use the exact ENU origin stored in camera_boston.npz.
# ---------------------------------------------------------------------------
WGS84_A = 6378137.0
WGS84_F = 1.0 / 298.257223563
WGS84_E2 = WGS84_F * (2.0 - WGS84_F)


def geodetic_to_ecef(lat_deg: float, lon_deg: float, altitude_m: float) -> np.ndarray:
    lat = math.radians(float(lat_deg))
    lon = math.radians(float(lon_deg))
    sin_lat = math.sin(lat)
    cos_lat = math.cos(lat)
    sin_lon = math.sin(lon)
    cos_lon = math.cos(lon)
    prime_vertical_radius = WGS84_A / math.sqrt(1.0 - WGS84_E2 * sin_lat**2)

    return np.array([
        (prime_vertical_radius + altitude_m) * cos_lat * cos_lon,
        (prime_vertical_radius + altitude_m) * cos_lat * sin_lon,
        (prime_vertical_radius * (1.0 - WGS84_E2) + altitude_m) * sin_lat,
    ], dtype=np.float64)


def gps_to_enu(points_gps, origin_lat: float, origin_lon: float, origin_alt: float) -> np.ndarray:
    """Convert a list of (lat, lon, altitude) points to the calibration ENU frame."""
    origin_ecef = geodetic_to_ecef(origin_lat, origin_lon, origin_alt)
    ecef_points = np.vstack([
        geodetic_to_ecef(point["lat"], point["lon"], point["alt"])
        for point in points_gps
    ])
    delta = ecef_points - origin_ecef

    lat0 = math.radians(float(origin_lat))
    lon0 = math.radians(float(origin_lon))
    sin_lat0, cos_lat0 = math.sin(lat0), math.cos(lat0)
    sin_lon0, cos_lon0 = math.sin(lon0), math.cos(lon0)

    ecef_to_enu = np.array([
        [-sin_lon0, cos_lon0, 0.0],
        [-sin_lat0 * cos_lon0, -sin_lat0 * sin_lon0, cos_lat0],
        [cos_lat0 * cos_lon0, cos_lat0 * sin_lon0, sin_lat0],
    ], dtype=np.float64)

    return (ecef_to_enu @ delta.T).T


def require_npz_key(parameters, key: str):
    if key not in parameters.files:
        required = "intrinsics, distortion, image_size, rvec, tvec, origin_lat, origin_lon, origin_alt"
        raise KeyError(
            f"The file {PARAMS_FILE.name} does not contain '{key}'. "
            "This is probably an older NPZ created before extrinsics and the ENU "
            "origin were saved. Re-run the updated script_calibracao.py to create "
            f"a compatible file. Required fields: {required}."
        )
    return parameters[key]


def main() -> None:
    if not PARAMS_FILE.is_file():
        raise FileNotFoundError(
            f"Camera parameters not found: {PARAMS_FILE}\n"
            "Run script_calibracao.py first, or update PARAMS_FILE."
        )
    if not IMAGE_FILE.is_file():
        raise FileNotFoundError(
            f"Image not found: {IMAGE_FILE}\n"
            "Place the exact calibration image beside this script or update IMAGE_FILE."
        )
    if not POINTS_GPS:
        raise ValueError("POINTS_GPS is empty. Add at least one GPS point to project.")
    # allow_pickle=False is safer and is sufficient for the numeric arrays used here.
    with np.load(PARAMS_FILE, allow_pickle=False) as parameters:
        K = np.asarray(require_npz_key(parameters, "intrinsics"), dtype=np.float64)
        distortion = np.asarray(require_npz_key(parameters, "distortion"), dtype=np.float64)
        saved_size = np.asarray(require_npz_key(parameters, "image_size"), dtype=int).reshape(-1)
        rvec = np.asarray(require_npz_key(parameters, "rvec"), dtype=np.float64).reshape(3, 1)
        tvec = np.asarray(require_npz_key(parameters, "tvec"), dtype=np.float64).reshape(3, 1)
        origin_lat = float(np.asarray(require_npz_key(parameters, "origin_lat")).item())
        origin_lon = float(np.asarray(require_npz_key(parameters, "origin_lon")).item())
        origin_alt = float(np.asarray(require_npz_key(parameters, "origin_alt")).item())

        vfov = None
        if "vfov_final_deg" in parameters.files:
            vfov = float(np.asarray(parameters["vfov_final_deg"]).item())

    image = cv2.imread(str(IMAGE_FILE), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"Could not read image: {IMAGE_FILE}")
    image_height, image_width = image.shape[:2]

    if saved_size.size != 2:
        raise ValueError(f"Invalid image_size in NPZ: {saved_size}")
    saved_width, saved_height = int(saved_size[0]), int(saved_size[1])
    if (image_width, image_height) != (saved_width, saved_height):
        raise ValueError(
            "The image dimensions do not match the calibration image. "
            f"NPZ expects {saved_width}x{saved_height}, but {IMAGE_FILE.name} is "
            f"{image_width}x{image_height}. Use the exact image used for calibration; "
            "do not resize or crop it unless you also adjust the camera matrix."
        )

    if K.shape != (3, 3):
        raise ValueError(f"Expected a 3x3 intrinsic matrix, got shape {K.shape}.")

    points_enu = gps_to_enu(POINTS_GPS, origin_lat, origin_lon, origin_alt)
    object_points = points_enu.reshape(-1, 1, 3).astype(np.float64)

    # projectPoints applies: world ENU -> camera coordinates (rvec/tvec),
    # then perspective projection and lens distortion (K/distortion).
    projected, _ = cv2.projectPoints(object_points, rvec, tvec, K, distortion)
    projected = projected.reshape(-1, 2)

    rotation, _ = cv2.Rodrigues(rvec)
    camera_coordinates = (rotation @ points_enu.T + tvec).T

    rows = []
    for index, point in enumerate(POINTS_GPS):
        u, v = map(float, projected[index])
        x_cam, y_cam, z_cam = map(float, camera_coordinates[index])
        in_front = z_cam > 0.0
        inside = (0.0 <= u < image_width) and (0.0 <= v < image_height)
        rows.append({
            "id": point["id"],
            "latitude": float(point["lat"]),
            "longitude": float(point["lon"]),
            "altitude_m": float(point["alt"]),
            "east_m": float(points_enu[index, 0]),
            "north_m": float(points_enu[index, 1]),
            "up_m": float(points_enu[index, 2]),
            "camera_x_m": x_cam,
            "camera_y_m": y_cam,
            "camera_z_m": z_cam,
            "pixel_x": u,
            "pixel_y": v,
            "in_front_of_camera": in_front,
            "inside_image": inside,
        })

        if not in_front:
            print(f"WARNING: {point['id']} is behind the camera (camera Z={z_cam:.3f} m).")
            continue

        if inside:
            centre = (int(round(u)), int(round(v)))
            cv2.circle(image, centre, POINT_RADIUS_PX, PROJECTED_POINT_COLOR, -1, cv2.LINE_AA)
            cv2.circle(image, centre, POINT_RADIUS_PX + 2, (255, 255, 255), 1, cv2.LINE_AA)
            if DRAW_LABELS:
                label = str(point["id"])
                label_origin = (centre[0] + 9, centre[1] - 8)
                cv2.putText(image, label, label_origin, cv2.FONT_HERSHEY_SIMPLEX,
                            FONT_SCALE, (0, 0, 0), 3, cv2.LINE_AA)
                cv2.putText(image, label, label_origin, cv2.FONT_HERSHEY_SIMPLEX,
                            FONT_SCALE, (255, 255, 255), 1, cv2.LINE_AA)
        else:
            print(
                f"WARNING: {point['id']} projects outside the image at "
                f"({u:.2f}, {v:.2f}) px."
            )

    # Draw the measured image positions last so the dark-blue crosses remain
    # visible even when a projected red point is very close to the measured position.
    for measured in OBSERVED_IMAGE_POINTS:
        x = int(measured["x"])
        y = int(measured["y"])
        if not (0 <= x < image_width and 0 <= y < image_height):
            raise ValueError(
                f"Observed image position {measured['id']}=({x}, {y}) is outside "
                f"the image bounds (0..{image_width - 1}, 0..{image_height - 1})."
            )

        cv2.drawMarker(
            image,
            (x, y),
            OBSERVED_POINT_COLOR,
            markerType=cv2.MARKER_CROSS,
            markerSize=OBSERVED_CROSS_SIZE_PX,
            thickness=OBSERVED_CROSS_THICKNESS,
            line_type=cv2.LINE_AA,
        )
        if DRAW_OBSERVED_LABELS:
            label = f"{measured['id']} real"
            label_origin = (x + 12, y + 20)
            cv2.putText(image, label, label_origin, cv2.FONT_HERSHEY_SIMPLEX,
                        FONT_SCALE, (255, 255, 255), 3, cv2.LINE_AA)
            cv2.putText(image, label, label_origin, cv2.FONT_HERSHEY_SIMPLEX,
                        FONT_SCALE, OBSERVED_POINT_COLOR, 1, cv2.LINE_AA)

    if not cv2.imwrite(str(OUTPUT_IMAGE), image):
        raise RuntimeError(f"Could not save output image: {OUTPUT_IMAGE}")

    fieldnames = list(rows[0].keys())
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print("\n================ PROJECTION RESULTS ================")
    print(f"Camera parameters: {PARAMS_FILE.name}")
    print(f"Image: {IMAGE_FILE.name} ({image_width} x {image_height})")
    if vfov is not None:
        print(f"Calibrated VFOV: {vfov:.3f} deg")
    print("\nProjected pixel coordinates:")
    for row in rows:
        status = "inside image" if row["inside_image"] else "outside image"
        if not row["in_front_of_camera"]:
            status = "behind camera"
        print(
            f"  {row['id']}: x={row['pixel_x']:.2f}, y={row['pixel_y']:.2f} px "
            f"({status}; camera Z={row['camera_z_m']:.2f} m)"
        )

    print(f"\nOverlay image saved to: {OUTPUT_IMAGE}")
    print(f"Coordinates CSV saved to: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
