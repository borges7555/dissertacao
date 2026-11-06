using System;
using System.Collections;
using UnityEngine;
using UnityEngine.InputSystem;
using Gyroscope = UnityEngine.InputSystem.Gyroscope;

/// <summary>
/// Starts GPS + compass (legacy Input APIs) and enables the relevant
/// UnityEngine.InputSystem sensors, then exposes GetSnapshot() to read
/// everything at once, synchronously, for a given photo file name.
/// </summary>
public class SensorLogger : MonoBehaviour
{
    [Header("GPS settings")]
    [Tooltip("Desired accuracy in meters for the location service.")]
    public float gpsDesiredAccuracy = 5f;
    [Tooltip("Minimum distance in meters before location is updated.")]
    public float gpsUpdateDistance = 1f;
    [Tooltip("Seconds to wait for the GPS fix before giving up.")]
    public int gpsInitTimeoutSeconds = 20;

    public bool GpsReady { get; private set; }
    public bool SensorsReady { get; private set; }

    IEnumerator Start()
    {
        // --- GPS ---
        yield return StartCoroutine(InitGps());

        // --- Compass ---
        Input.compass.enabled = true;

        // --- Input System sensors ---
        EnableIfPresent(Accelerometer.current);
        EnableIfPresent(Gyroscope.current);
        EnableIfPresent(MagneticFieldSensor.current);
        EnableIfPresent(AttitudeSensor.current);

        SensorsReady = true;
    }

    void EnableIfPresent(InputDevice device)
    {
        if (device != null && !device.enabled)
            InputSystem.EnableDevice(device);
    }

    IEnumerator InitGps()
    {
        if (!Input.location.isEnabledByUser)
        {
            Debug.LogWarning("SensorLogger: Location services disabled by user/OS.");
            GpsReady = false;
            yield break;
        }

        Input.location.Start(gpsDesiredAccuracy, gpsUpdateDistance);

        int elapsedMs = 0;
        int stepMs = 250;
        while (Input.location.status == LocationServiceStatus.Initializing
               && elapsedMs < gpsInitTimeoutSeconds * 1000)
        {
            yield return new WaitForSeconds(stepMs / 1000f);
            elapsedMs += stepMs;
        }

        GpsReady = Input.location.status == LocationServiceStatus.Running;

        if (!GpsReady)
            Debug.LogWarning($"SensorLogger: GPS not running, status = {Input.location.status}");
    }

    /// <summary>
    /// Reads every sensor's current value synchronously and returns a
    /// filled-in snapshot. Call this at the exact moment you take the photo.
    /// </summary>
    public SensorSnapshot GetSnapshot(string photoFileName)
    {
        var snap = new SensorSnapshot
        {
            photoFileName = photoFileName,
            timestampUtc = DateTime.UtcNow.ToString("o"),
            unixTimeMs = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
            deviceOrientation = Input.deviceOrientation.ToString()
        };

        // GPS
        snap.gpsAvailable = Input.location.status == LocationServiceStatus.Running;
        if (snap.gpsAvailable)
        {
            var data = Input.location.lastData;
            snap.latitude = data.latitude;
            snap.longitude = data.longitude;
            snap.altitude = data.altitude;
            snap.gpsHorizontalAccuracy = data.horizontalAccuracy;
            snap.gpsTimestamp = data.timestamp;
        }

        // Compass
        snap.compassAvailable = Input.compass.enabled;
        if (snap.compassAvailable)
        {
            snap.trueHeading = Input.compass.trueHeading;
            snap.magneticHeading = Input.compass.magneticHeading;
            snap.headingAccuracy = Input.compass.headingAccuracy;
            var raw = Input.compass.rawVector;
            snap.compassRawX = raw.x;
            snap.compassRawY = raw.y;
            snap.compassRawZ = raw.z;
        }

        // Accelerometer
        var accel = Accelerometer.current;
        snap.accelerometerAvailable = accel != null && accel.enabled;
        if (snap.accelerometerAvailable)
        {
            var v = accel.acceleration.ReadValue();
            snap.accelX = v.x; snap.accelY = v.y; snap.accelZ = v.z;
        }

        // Gyroscope
        var gyro = Gyroscope.current;
        snap.gyroscopeAvailable = gyro != null && gyro.enabled;
        if (snap.gyroscopeAvailable)
        {
            var v = gyro.angularVelocity.ReadValue();
            snap.gyroX = v.x; snap.gyroY = v.y; snap.gyroZ = v.z;
        }

        // Magnetometer
        var mag = MagneticFieldSensor.current;
        snap.magnetometerAvailable = mag != null && mag.enabled;
        if (snap.magnetometerAvailable)
        {
            var v = mag.magneticField.ReadValue();
            snap.magX = v.x; snap.magY = v.y; snap.magZ = v.z;
        }

        // Attitude / rotation vector
        var att = AttitudeSensor.current;
        snap.attitudeAvailable = att != null && att.enabled;
        if (snap.attitudeAvailable)
        {
            var q = att.attitude.ReadValue();
            snap.attitudeX = q.x; snap.attitudeY = q.y; snap.attitudeZ = q.z; snap.attitudeW = q.w;

            var euler = q.eulerAngles;
            snap.derivedPitch = euler.x;
            snap.derivedYaw = euler.y;
            snap.derivedRoll = euler.z;
        }

        return snap;
    }

    void OnDisable()
    {
        if (Input.location.status == LocationServiceStatus.Running)
            Input.location.Stop();
        Input.compass.enabled = false;
    }
}
