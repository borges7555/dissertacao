using System;

namespace SensorPositionPredictor;

/// <summary>Result of projecting a direction onto the image plane.</summary>
public readonly record struct PixelProjection(double X, double Y, bool InFrame);

/// <summary>
/// Projects a target of known bearing/elevation into the photo using the
/// phone's full 3D orientation, so ANY pose works: portrait, landscape,
/// upside-down, and small rolls.
///
/// The image used is the "device-upright" frame: the camera sensor image as it
/// looks with the phone's top edge up (portrait, e.g. 1080x1920), whatever the
/// real pose was. X grows right, Y grows down, origin top-left.
/// </summary>
public static class TargetProjector
{
    const double Deg2Rad = Math.PI / 180.0;

    /// <summary>
    /// Direction to the target in DEVICE coordinates (+X right, +Y up the screen,
    /// +Z out of the screen; the camera looks along -Z).
    /// trueBearingDeg is clockwise from TRUE north; trueElevationDeg is above the horizon.
    /// </summary>
    public static Vec3 DirectionInDeviceFrame(CameraOrientation o, double trueBearingDeg, double trueElevationDeg)
    {
        // The sensor frame's north is MAGNETIC north, so convert the bearing.
        double bearing = (trueBearingDeg - o.DeclinationDeg) * Deg2Rad;
        double elevation = trueElevationDeg * Deg2Rad;

        double east = Math.Sin(bearing) * Math.Cos(elevation);
        double north = Math.Cos(bearing) * Math.Cos(elevation);
        double up = Math.Sin(elevation);

        // World vector -> device coordinates: combine the world axes as seen by the device.
        return o.East * east + o.North * north + o.Up * up;
    }

    /// <summary>
    /// Pinhole projection of a device-frame direction onto the image.
    /// Returns null if the target is behind the camera.
    /// </summary>
    public static PixelProjection? Project(Vec3 direction, double hfovDeg, double vfovDeg, int width, int height)
    {
        double depth = -direction.Z; // distance along the camera's viewing axis
        if (depth <= 1e-9)
            return null;

        // Focal lengths in pixels: width spans the horizontal FOV, height the vertical FOV.
        double fx = (width / 2.0) / Math.Tan(hfovDeg * Deg2Rad / 2.0);
        double fy = (height / 2.0) / Math.Tan(vfovDeg * Deg2Rad / 2.0);

        double x = width / 2.0 + fx * direction.X / depth;
        double y = height / 2.0 - fy * direction.Y / depth;

        bool inFrame = x >= 0 && x < width && y >= 0 && y < height;
        return new PixelProjection(x, y, inFrame);
    }
}
