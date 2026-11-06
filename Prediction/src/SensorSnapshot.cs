namespace SensorPositionPredictor;

/// <summary>
/// Mirrors the Unity SensorSnapshot JSON structure, so the same JSON files
/// your Unity app produces can be read directly by this tool.
/// Only trueHeading and accelZ are actually used by this program, but the
/// rest is kept so the class matches the full file for future reuse.
/// </summary>
public class SensorSnapshot
{
    public string? photoFileName { get; set; }
    public string? timestampUtc { get; set; }
    public long unixTimeMs { get; set; }

    public bool gpsAvailable { get; set; }
    public double latitude { get; set; }
    public double longitude { get; set; }
    public double altitude { get; set; }
    public float gpsHorizontalAccuracy { get; set; }
    public double gpsTimestamp { get; set; }

    public bool compassAvailable { get; set; }
    public float trueHeading { get; set; }
    public float magneticHeading { get; set; }
    public float headingAccuracy { get; set; }
    public float compassRawX { get; set; }
    public float compassRawY { get; set; }
    public float compassRawZ { get; set; }

    public bool accelerometerAvailable { get; set; }
    public float accelX { get; set; }
    public float accelY { get; set; }
    public float accelZ { get; set; }

    public bool gyroscopeAvailable { get; set; }
    public float gyroX { get; set; }
    public float gyroY { get; set; }
    public float gyroZ { get; set; }

    public bool magnetometerAvailable { get; set; }
    public float magX { get; set; }
    public float magY { get; set; }
    public float magZ { get; set; }

    public bool attitudeAvailable { get; set; }
    public float attitudeX { get; set; }
    public float attitudeY { get; set; }
    public float attitudeZ { get; set; }
    public float attitudeW { get; set; }

    public float derivedPitch { get; set; }
    public float derivedYaw { get; set; }
    public float derivedRoll { get; set; }

    public string? deviceOrientation { get; set; }
}
