using System;

namespace SensorPositionPredictor;

/// <summary>
/// Geometry helpers: true bearing, distance, and elevation angle between
/// two known lat/lon/alt points.
/// </summary>
public static class GeoMath
{
    const double EarthRadiusMeters = 6371000.0;
    const double Deg2Rad = Math.PI / 180.0;
    const double Rad2Deg = 180.0 / Math.PI;

    public static double TrueBearingDeg(double lat1, double lon1, double lat2, double lon2)
    {
        double phi1 = lat1 * Deg2Rad, phi2 = lat2 * Deg2Rad;
        double deltaLambda = (lon2 - lon1) * Deg2Rad;

        double y = Math.Sin(deltaLambda) * Math.Cos(phi2);
        double x = Math.Cos(phi1) * Math.Sin(phi2) - Math.Sin(phi1) * Math.Cos(phi2) * Math.Cos(deltaLambda);

        double bearing = Math.Atan2(y, x) * Rad2Deg;
        return (bearing + 360.0) % 360.0;
    }

    public static double HaversineDistanceMeters(double lat1, double lon1, double lat2, double lon2)
    {
        double phi1 = lat1 * Deg2Rad, phi2 = lat2 * Deg2Rad;
        double deltaPhi = (lat2 - lat1) * Deg2Rad;
        double deltaLambda = (lon2 - lon1) * Deg2Rad;

        double a = Math.Sin(deltaPhi / 2) * Math.Sin(deltaPhi / 2) +
                   Math.Cos(phi1) * Math.Cos(phi2) * Math.Sin(deltaLambda / 2) * Math.Sin(deltaLambda / 2);
        return 2 * EarthRadiusMeters * Math.Asin(Math.Sqrt(a));
    }

    public static double ElevationAngleDeg(double myHeight, double targetHeight, double horizontalDistanceMeters)
    {
        return Math.Atan2(targetHeight - myHeight, horizontalDistanceMeters) * Rad2Deg;
    }

    /// <summary>Normalizes an angle difference to the range -180..180.</summary>
    public static double NormalizeDelta(double deg)
    {
        double d = (deg + 180.0) % 360.0;
        if (d < 0) d += 360.0;
        return d - 180.0;
    }
}
