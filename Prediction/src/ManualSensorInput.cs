using System.Globalization;
using System.Text.RegularExpressions;

namespace SensorPositionPredictor;

/// <summary>
/// Used when the program is started with only the photo: asks the user to type
/// the sensor values that would normally be read from the JSON file, and
/// returns them as a SensorSnapshot so the rest of the program works unchanged.
///
/// Only the values the program actually uses are asked for:
/// accelerometer (3), magnetometer (3), magnetic declination, and how the phone
/// was held. You can paste a whole line from the JSON at any number prompt
/// (e.g.  "accelX": -0.98,  ) and only the number in it is used.
/// </summary>
public static class ManualSensorInput
{
    // A number such as -0.98, 12, .5 or 1.5e-3.
    static readonly Regex NumberPattern =
        new(@"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", RegexOptions.Compiled);

    /// <summary>Throws EndOfStreamException if the input ends before everything is entered.</summary>
    public static SensorSnapshot Prompt()
    {
        Console.WriteLine("No sensor JSON was given, so please type the sensor values saved by the app.");
        Console.WriteLine("Tip: you can paste a whole line from the JSON, e.g.  \"accelX\": -0.98,  and only the number is used.");
        Console.WriteLine();

        Console.WriteLine("Accelerometer, in g, as Unity saves it. It points toward gravity, so a phone");
        Console.WriteLine("held upright in portrait reads about (0, -1, 0):");
        double ax = ReadNumber("  accelX: ");
        double ay = ReadNumber("  accelY: ");
        double az = ReadNumber("  accelZ: ");
        double gLen = Math.Sqrt(ax * ax + ay * ay + az * az);
        if (gLen < 0.5 || gLen > 1.5)
            Console.WriteLine($"  Note: these add up to {gLen:F2} g; a phone held still should read about 1 g.");

        Console.WriteLine();
        Console.WriteLine("Magnetometer, in microtesla (uT):");
        double mx = ReadNumber("  magX: ");
        double my = ReadNumber("  magY: ");
        double mz = ReadNumber("  magZ: ");
        double mLen = Math.Sqrt(mx * mx + my * my + mz * mz);
        if (mLen < 15 || mLen > 90)
            Console.WriteLine($"  Note: these add up to {mLen:F1} uT; Earth's field is normally about 25-65 uT.");

        Console.WriteLine();
        Console.WriteLine("Magnetic declination at the photo location, in degrees, east positive");
        Console.WriteLine("(= trueHeading minus magneticHeading in the JSON). Press Enter for 0 if unknown:");
        double declination = ReadNumber("  declination: ", defaultValue: 0.0);

        Console.WriteLine();
        Console.WriteLine("How was the phone held when the photo was taken?");
        Console.WriteLine("  1 = Portrait             (top edge up)");
        Console.WriteLine("  2 = PortraitUpsideDown   (top edge down)");
        Console.WriteLine("  3 = LandscapeLeft        (top edge to your left)");
        Console.WriteLine("  4 = LandscapeRight       (top edge to your right)");
        Console.WriteLine("  Enter = work it out from the accelerometer values");
        string posture = ReadPosture();
        Console.WriteLine();

        return new SensorSnapshot
        {
            accelerometerAvailable = true,
            accelX = (float)ax,
            accelY = (float)ay,
            accelZ = (float)az,

            magnetometerAvailable = true,
            magX = (float)mx,
            magY = (float)my,
            magZ = (float)mz,

            // The orientation code takes the declination as trueHeading - magneticHeading.
            // compassAvailable stays false so Unity's compass line is not shown.
            compassAvailable = false,
            magneticHeading = 0f,
            trueHeading = (float)declination,

            deviceOrientation = posture
        };
    }

    static double ReadNumber(string prompt, double? defaultValue = null)
    {
        while (true)
        {
            Console.Write(prompt);
            string? line = Console.ReadLine();
            if (line is null)
                throw new EndOfStreamException("Input ended before all the sensor values were entered.");

            if (string.IsNullOrWhiteSpace(line))
            {
                if (defaultValue.HasValue)
                    return defaultValue.Value;
                Console.WriteLine("  Please enter a number.");
                continue;
            }

            MatchCollection found = NumberPattern.Matches(line);
            if (found.Count == 1 &&
                double.TryParse(found[0].Value, NumberStyles.Float, CultureInfo.InvariantCulture, out double value))
                return value;

            Console.WriteLine(found.Count == 0
                ? "  I couldn't find a number there — please try again."
                : "  I found more than one number — enter one value per prompt, with a dot as the decimal separator.");
        }
    }

    /// <summary>Returns a name DevicePostureDetector understands, or "Unknown" to infer from gravity.</summary>
    static string ReadPosture()
    {
        while (true)
        {
            Console.Write("  held: ");
            string? line = Console.ReadLine();
            if (line is null)
                throw new EndOfStreamException("Input ended before all the sensor values were entered.");

            if (string.IsNullOrWhiteSpace(line))
                return "Unknown";

            string key = line.Trim().ToLowerInvariant()
                .Replace(" ", "").Replace("_", "").Replace("-", "").Replace("\"", "").Replace(",", "");

            string? posture = key switch
            {
                "1" or "portrait" => "Portrait",
                "2" or "portraitupsidedown" or "upsidedown" => "PortraitUpsideDown",
                "3" or "landscapeleft" => "LandscapeLeft",
                "4" or "landscaperight" => "LandscapeRight",
                _ => null
            };

            if (posture != null)
                return posture;

            Console.WriteLine("  Please enter 1, 2, 3 or 4, or press Enter to work it out from gravity.");
        }
    }
}
