using System;

namespace SensorPositionPredictor;

public enum DevicePosture
{
    Portrait,            // top edge up
    PortraitUpsideDown,  // top edge down
    LandscapeLeft,       // top edge to the user's left
    LandscapeRight       // top edge to the user's right
}

/// <summary>
/// How the phone was physically held when the photo was taken.
/// The projection itself does NOT depend on this (it uses the full 3D
/// orientation); the posture is only used to rotate the finished picture so
/// it looks upright.
/// </summary>
public static class DevicePostureDetector
{
    /// <summary>
    /// Uses the "deviceOrientation" field the Unity app saved. If it holds
    /// something else (FaceUp, FaceDown, Unknown, empty) the posture is inferred
    /// from gravity instead. 'note' says where the answer came from and warns
    /// if the field and gravity disagree.
    /// </summary>
    public static DevicePosture Detect(SensorSnapshot s, out string note)
    {
        DevicePosture fromGravity = FromGravity(s);

        DevicePosture? fromField = s.deviceOrientation switch
        {
            "Portrait" => DevicePosture.Portrait,
            "PortraitUpsideDown" => DevicePosture.PortraitUpsideDown,
            "LandscapeLeft" => DevicePosture.LandscapeLeft,
            "LandscapeRight" => DevicePosture.LandscapeRight,
            _ => null
        };

        if (fromField == null)
        {
            note = $"inferred from gravity, because deviceOrientation was \"{s.deviceOrientation}\"";
            return fromGravity;
        }

        note = fromField == fromGravity
            ? "from the deviceOrientation field; gravity agrees"
            : $"from the deviceOrientation field; WARNING: gravity suggests {fromGravity} (phone probably held at an angle)";
        return fromField.Value;
    }

    /// <summary>Whichever screen axis gravity mostly lies along.</summary>
    public static DevicePosture FromGravity(SensorSnapshot s)
    {
        // Unity's accelerometer points toward gravity. Portrait upright => Y = -1.
        if (Math.Abs(s.accelY) >= Math.Abs(s.accelX))
            return s.accelY < 0 ? DevicePosture.Portrait : DevicePosture.PortraitUpsideDown;

        return s.accelX > 0 ? DevicePosture.LandscapeRight : DevicePosture.LandscapeLeft;
    }

    /// <summary>
    /// Clockwise rotation (degrees) that turns the "device-upright" image
    /// (taken with the phone's top edge up) into one that is upright in the world.
    /// LandscapeRight: world-up appears toward the image's left, so turn it 90 CW.
    /// </summary>
    public static int DisplayRotationClockwiseDeg(DevicePosture p) => p switch
    {
        DevicePosture.Portrait => 0,
        DevicePosture.LandscapeRight => 90,
        DevicePosture.PortraitUpsideDown => 180,
        DevicePosture.LandscapeLeft => 270,
        _ => 0
    };

    /// <summary>
    /// Where a point of a width x height image ends up after rotating the image
    /// clockwise by 0/90/180/270 degrees (continuous pixel coordinates).
    /// </summary>
    public static (double X, double Y) RotatePointClockwise(double x, double y, int width, int height, int degrees) => degrees switch
    {
        90 => (height - y, x),
        180 => (width - x, height - y),
        270 => (y, width - x),
        _ => (x, y)
    };

    /// <summary>
    /// Re-expresses an angular offset from the image centre (given along the
    /// phone's own right/up axes) along the right/up directions of the picture
    /// after it has been rotated clockwise by 0/90/180/270 degrees.
    /// </summary>
    public static (double Right, double Up) RotateOffsetClockwise(double right, double up, int degrees) => degrees switch
    {
        90 => (up, -right),
        180 => (-right, -up),
        270 => (-up, right),
        _ => (right, up)
    };
}
