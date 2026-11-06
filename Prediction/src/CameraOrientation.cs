using System;

namespace SensorPositionPredictor;

/// <summary>
/// Full orientation of the phone at capture time, computed from the raw
/// accelerometer and magnetometer vectors stored in the sensor JSON.
///
/// East/North/Up are the world axes expressed in DEVICE coordinates
/// (+X right, +Y up the screen, +Z out of the screen when held in portrait).
/// "North" here is MAGNETIC north; DeclinationDeg converts to true north.
/// The back camera looks along device -Z.
///
/// Why not use Unity's Input.compass heading? It follows the phone's TOP EDGE,
/// not the camera: in landscape it is off by +/-90 deg, upside-down by 180 deg,
/// and when the phone is held upright the top edge points at the sky, so a
/// tiny tilt swings it by tens of degrees. The camera axis has none of those
/// problems.
/// </summary>
public readonly record struct CameraOrientation(
    double HeadingMagneticDeg,
    double HeadingTrueDeg,
    double DeclinationDeg,
    double PitchDeg,
    double FieldMicroTesla,
    double DipDeg,
    Vec3 East,
    Vec3 North,
    Vec3 Up)
{
    const double Rad2Deg = 180.0 / Math.PI;

    public static CameraOrientation FromSnapshot(SensorSnapshot s)
    {
        if (!s.accelerometerAvailable || !s.magnetometerAvailable)
            throw new InvalidOperationException("The accelerometer or magnetometer was not available when this photo was taken.");

        // Unity's accelerometer vector points toward gravity.
        var g = new Vec3(s.accelX, s.accelY, s.accelZ);
        var m = new Vec3(s.magX, s.magY, s.magZ);
        double gLen = g.Length, mLen = m.Length;
        if (gLen < 1e-6 || mLen < 1e-6)
            throw new InvalidOperationException("Accelerometer or magnetometer vector is zero.");

        // "Up" in device coordinates.
        Vec3 up = (-g) * (1.0 / gLen);

        // East = magnetic x up, North = up x East (standard tilt compensation).
        Vec3 eastRaw = Vec3.Cross(m, up);
        if (eastRaw.Length < 1e-6)
            throw new InvalidOperationException("Magnetic field is parallel to gravity; cannot determine direction.");
        Vec3 east = eastRaw.Normalized();
        Vec3 north = Vec3.Cross(up, east);

        // Heading of the back camera (device -Z axis), magnetic.
        double headingMag = Normalize360(Math.Atan2(-east.Z, -north.Z) * Rad2Deg);

        // Declination as already worked out by Unity from the GPS fix
        // (trueHeading - magneticHeading; zero if GPS wasn't available).
        double declination = Normalize180(s.trueHeading - s.magneticHeading);
        double headingTrue = Normalize360(headingMag + declination);

        // Camera elevation above the horizon: +90 = straight up, -90 = straight down.
        double pitch = Math.Asin(Math.Clamp(g.Z / gLen, -1.0, 1.0)) * Rad2Deg;

        // Magnetic dip (angle of the field below horizontal) and field strength:
        // compare with the expected values for your location to judge how well
        // the magnetometer is calibrated.
        double dip = Math.Asin(Math.Clamp(Vec3.Dot(m, g) / (mLen * gLen), -1.0, 1.0)) * Rad2Deg;

        return new CameraOrientation(headingMag, headingTrue, declination, pitch, mLen, dip, east, north, up);
    }

    static double Normalize360(double deg)
    {
        double d = deg % 360.0;
        return d < 0 ? d + 360.0 : d;
    }

    static double Normalize180(double deg)
    {
        double d = (deg + 180.0) % 360.0;
        if (d < 0) d += 360.0;
        return d - 180.0;
    }
}
