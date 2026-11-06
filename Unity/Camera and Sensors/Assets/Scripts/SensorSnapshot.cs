using System;

/// <summary>
/// Plain data container for a single, synchronized reading of all sensors.
/// Serialized to JSON alongside each captured photo.
/// </summary>
[Serializable]
public class SensorSnapshot
{
    // Identity / timing
    public string photoFileName;
    public string timestampUtc;      // ISO 8601
    public long unixTimeMs;

    // GPS (Input.location)
    public bool gpsAvailable;
    public double latitude;
    public double longitude;
    public double altitude;
    public float gpsHorizontalAccuracy;
    public double gpsTimestamp;      // seconds since epoch, from LocationInfo

    // Compass (Input.compass)
    public bool compassAvailable;
    public float trueHeading;
    public float magneticHeading;
    public float headingAccuracy;
    public float compassRawX;
    public float compassRawY;
    public float compassRawZ;

    // Accelerometer (UnityEngine.InputSystem.Accelerometer)
    public bool accelerometerAvailable;
    public float accelX, accelY, accelZ;

    // Gyroscope (UnityEngine.InputSystem.Gyroscope) - angular velocity, rad/s
    public bool gyroscopeAvailable;
    public float gyroX, gyroY, gyroZ;

    // Magnetometer (UnityEngine.InputSystem.MagneticFieldSensor)
    public bool magnetometerAvailable;
    public float magX, magY, magZ;

    // Attitude / rotation vector (UnityEngine.InputSystem.AttitudeSensor) - quaternion
    public bool attitudeAvailable;
    public float attitudeX, attitudeY, attitudeZ, attitudeW;

    // Derived Euler angles from the attitude quaternion, for convenience
    public float derivedPitch;
    public float derivedYaw;
    public float derivedRoll;

    // Device orientation as Unity reports it (Portrait, LandscapeLeft, etc.)
    public string deviceOrientation;
}
