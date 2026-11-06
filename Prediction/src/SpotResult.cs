namespace SensorPositionPredictor;

public enum SpotStatus
{
    Drawn,          // inside the photo, marker drawn
    OutsideFrame,   // in front of the camera but outside the photo
    BehindCamera    // behind the camera, cannot appear in the photo
}

/// <summary>Everything calculated for one photographed spot.</summary>
public readonly record struct SpotResult(
    int Number,
    double Latitude,
    double Longitude,
    double Height,
    double BearingDeg,
    double DistanceMeters,
    double ElevationDeg,
    double OffsetRightDeg,   // angle from the picture centre, as seen in the SAVED (upright) picture
    double OffsetUpDeg,
    SpotStatus Status,
    double? ShownX,          // position in the SAVED (upright) image, even if outside it
    double? ShownY);
