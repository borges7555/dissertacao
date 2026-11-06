using System.Drawing;
using System.Globalization;
using System.Text.Json;
using SensorPositionPredictor;

// ------------------------- Settings -------------------------
// Field of view of YOUR camera, for the DEVICE-UPRIGHT frame:
// horizontal = across the phone's X axis (photo width when held in portrait),
// vertical   = across the phone's Y axis (photo height when held in portrait).
const double HorizontalFovDeg = 45.49;
const double VerticalFovDeg = 73.46;

// How many degrees the sensor heading reads TOO HIGH (clockwise) compared with
// reality. Leave at 0 until a bias repeats across several photos. Example: if
// every dot lands ~9 deg to the LEFT of its target, set 9.0 to move dots right.
const double CompassBiasDeg = 0.0;

// Earth's field at your location (IGRF, Aveiro, Oct 2026). Only used to judge
// how well the magnetometer is calibrated — it does not affect the result.
const double ExpectedFieldMicroTesla = 44.9;
const double ExpectedDipDeg = 55.1;

// Upper limit for the number of spots asked for in one run.
const int MaxSpots = 10;
// ------------------------------------------------------------

if (args.Length < 1)
{
    Console.WriteLine("Usage: SensorPositionPredictor <photo.jpg> [sensorData.json]");
    Console.WriteLine("       Without the JSON file you will be asked to type the sensor values by hand.");
    return 1;
}

string photoPath = args[0];
string? jsonPath = args.Length >= 2 ? args[1] : null;
bool sensorsTypedByHand = jsonPath is null;

if (!File.Exists(photoPath))
{
    Console.WriteLine($"Photo not found: {photoPath}");
    return 1;
}
if (jsonPath is null)
{
    // One-argument mode: the single argument must be the photo.
    string extension = Path.GetExtension(photoPath).ToLowerInvariant();
    if (extension != ".jpg" && extension != ".jpeg")
    {
        Console.WriteLine($"With a single argument it must be the photo (.jpg), but got: {photoPath}");
        Console.WriteLine("Usage: SensorPositionPredictor <photo.jpg> [sensorData.json]");
        return 1;
    }
}
else if (!File.Exists(jsonPath))
{
    Console.WriteLine($"Sensor JSON not found: {jsonPath}");
    return 1;
}

SensorSnapshot snapshot;
if (jsonPath is null)
{
    // No JSON: ask for the sensor values instead.
    try
    {
        snapshot = ManualSensorInput.Prompt();
    }
    catch (EndOfStreamException ex)
    {
        Console.WriteLine(ex.Message);
        return 1;
    }
}
else
{
    try
    {
        string jsonText = File.ReadAllText(jsonPath);
        snapshot = JsonSerializer.Deserialize<SensorSnapshot>(jsonText, new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true
        }) ?? throw new Exception("Deserialized to null.");
    }
    catch (Exception ex)
    {
        Console.WriteLine($"Failed to read sensor JSON: {ex.Message}");
        return 1;
    }
}

// ---- How was the phone held, and what is its full 3D orientation? ----
DevicePosture posture = DevicePostureDetector.Detect(snapshot, out string postureNote);

CameraOrientation orientation;
try
{
    orientation = CameraOrientation.FromSnapshot(snapshot);
}
catch (InvalidOperationException ex)
{
    Console.WriteLine($"Cannot work out the phone's orientation: {ex.Message}");
    return 1;
}

// ---- Load the photo as the DEVICE-UPRIGHT frame ----
// The Unity app saves the camera sensor's frame as a 1920x1080 landscape file,
// fixed to the phone's body, i.e. the upright portrait image turned 90 deg to
// the left — whichever way the phone was actually held. Rotating it 90 deg
// clockwise gives the device-upright frame (1080x1920) that the sensor
// vectors and FOV values refer to. Already-portrait files are left alone.
using var bitmap = new Bitmap(photoPath);
if (bitmap.Width > bitmap.Height)
{
    bitmap.RotateFlip(RotateFlipType.Rotate90FlipNone); // 90 deg clockwise
    Console.WriteLine($"Photo was landscape; rotated 90 deg clockwise -> {bitmap.Width}x{bitmap.Height}.");
}
int frameWidth = bitmap.Width;    // size of the device-upright frame: all projection
int frameHeight = bitmap.Height;  // maths happens in this frame

// ---- Rotate the picture so it looks upright in the world ----
// Done BEFORE drawing, so the spot numbers are always upright and readable.
int rotation = DevicePostureDetector.DisplayRotationClockwiseDeg(posture);
if (rotation != 0)
{
    RotateFlipType flip = rotation switch
    {
        90 => RotateFlipType.Rotate90FlipNone,
        180 => RotateFlipType.Rotate180FlipNone,
        _ => RotateFlipType.Rotate270FlipNone
    };
    bitmap.RotateFlip(flip);
}

Console.WriteLine();
Console.WriteLine("---- Sensor analysis ----");
Console.WriteLine($"Phone held                : {posture}  ({postureNote})");
if (sensorsTypedByHand)
    Console.WriteLine($"Sensor values             : typed in by hand (declination {orientation.DeclinationDeg:+0.00;-0.00} deg)");
else if (snapshot.compassAvailable)
    Console.WriteLine($"Unity compass heading     : {snapshot.trueHeading,7:F2} deg  (follows the phone's top edge — not used)");
Console.WriteLine($"Camera heading (USED)     : {orientation.HeadingTrueDeg,7:F2} deg  (from raw accelerometer + magnetometer)");
Console.WriteLine($"Camera pitch (USED)       : {orientation.PitchDeg,7:F2} deg");
Console.WriteLine($"Magnetic field strength   : {orientation.FieldMicroTesla,7:F1} uT   (expected ~{ExpectedFieldMicroTesla:F1})");
Console.WriteLine($"Magnetic dip angle        : {orientation.DipDeg,7:F1} deg  (expected ~{ExpectedDipDeg:F1})");
if (Math.Abs(orientation.PitchDeg) > 70)
    Console.WriteLine("WARNING: camera is pointing nearly straight up/down; heading is unreliable for this shot.");
Console.WriteLine();

// ---- Where you stood (asked once, shared by every spot) ----
Console.WriteLine("---- Your position ----");
var (myLat, myLon, myHeight) = Console.ReadLine()!.Split(',') is { Length: 3 } p1 ? (double.Parse(p1[0], CultureInfo.InvariantCulture), 
                               double.Parse(p1[1], CultureInfo.InvariantCulture), double.Parse(p1[2], CultureInfo.InvariantCulture)) : 
                               throw new FormatException("Latitude, longitude and height.");

// ---- How many spots? ----
Console.WriteLine();
int spotCount = ReadInt($"How many spots do you want to calculate (1-{MaxSpots})? ", 1, MaxSpots);

var results = new List<SpotResult>();
for (int number = 1; number <= spotCount; number++)
{
    Console.WriteLine();
    Console.WriteLine($"---- Spot {number} of {spotCount} ----");
    var (spotLat, spotLon, spotHeight) = Console.ReadLine()!.Split(',') is { Length: 3 } p2 ? (double.Parse(p2[0], CultureInfo.InvariantCulture), 
                                         double.Parse(p2[1], CultureInfo.InvariantCulture), double.Parse(p2[2], CultureInfo.InvariantCulture)) : 
                                         throw new FormatException("Latitude, longitude and height.");

    // Ground-truth geometry (pure math, no sensor error).
    double bearing = GeoMath.TrueBearingDeg(myLat, myLon, spotLat, spotLon);
    double distance = GeoMath.HaversineDistanceMeters(myLat, myLon, spotLat, spotLon);
    double elevation = GeoMath.ElevationAngleDeg(myHeight, spotHeight, distance);

    // Where does that direction fall in the phone's own frame?
    Vec3 direction = TargetProjector.DirectionInDeviceFrame(orientation, bearing + CompassBiasDeg, elevation);
    double offRight = Math.Atan2(direction.X, -direction.Z) * 180.0 / Math.PI;
    double offUp = Math.Atan2(direction.Y, -direction.Z) * 180.0 / Math.PI;

    PixelProjection? hit = TargetProjector.Project(direction, HorizontalFovDeg, VerticalFovDeg, frameWidth, frameHeight);

    SpotStatus status;
    (double X, double Y)? shown = null;
    if (hit is null)
    {
        status = SpotStatus.BehindCamera;
    }
    else
    {
        // Convert from the device-upright frame to the saved (upright) picture.
        shown = DevicePostureDetector.RotatePointClockwise(hit.Value.X, hit.Value.Y, frameWidth, frameHeight, rotation);
        if (hit.Value.InFrame)
        {
            status = SpotStatus.Drawn;
            PhotoAnnotator.DrawNumberedMarker(bitmap, shown.Value, number);
        }
        else
        {
            status = SpotStatus.OutsideFrame;
        }
    }

    // Offsets as seen in the saved (upright) picture, not in the phone's own axes.
    var (shownRight, shownUp) = DevicePostureDetector.RotateOffsetClockwise(offRight, offUp, rotation);

    results.Add(new SpotResult(
        number, spotLat, spotLon, spotHeight,
        bearing, distance, elevation,
        shownRight, shownUp,
        status, shown?.X, shown?.Y));
}

// ---- Results table ----
Console.WriteLine();
Console.WriteLine("---- Results ----");
Console.WriteLine(
    "#".PadRight(4) + "colour".PadRight(9) + "distance".PadLeft(10) + "bearing".PadLeft(10) +
    "elev".PadLeft(8) + "   " + "off centre (right, up)".PadRight(26) + "result");

foreach (SpotResult r in results)
{
    string colourName = PhotoAnnotator.StyleFor(r.Number).Name;
    string offset = r.Status == SpotStatus.BehindCamera
        ? "n/a"
        : $"{Signed(r.OffsetRightDeg)}, {Signed(r.OffsetUpDeg)} deg";

    string outcome = r.Status switch
    {
        SpotStatus.Drawn => $"marker drawn at ({r.ShownX:F0}, {r.ShownY:F0})",
        SpotStatus.OutsideFrame => $"outside the frame (would be at ({r.ShownX:F0}, {r.ShownY:F0}))",
        _ => "behind the camera"
    };

    Console.WriteLine(
        r.Number.ToString().PadRight(4) +
        colourName.PadRight(9) +
        $"{r.DistanceMeters:F1} m".PadLeft(10) +
        $"{r.BearingDeg:F1} deg".PadLeft(10) +
        $"{r.ElevationDeg:F1}".PadLeft(8) +
        "   " + offset.PadRight(26) + outcome);
}

int drawnCount = results.Count(r => r.Status == SpotStatus.Drawn);
if (drawnCount == 0)
{
    Console.WriteLine();
    Console.WriteLine("None of the spots fall inside the photo — nothing saved.");
    return 0;
}

// Saved next to the program's executable. To save next to the input photo instead:
//   string outDir = Path.GetDirectoryName(Path.GetFullPath(photoPath))!;
string outDir = Path.GetDirectoryName(Path.GetFullPath(photoPath))!;
string outName = Path.GetFileNameWithoutExtension(photoPath) + "_prediction.jpg";
string outputPath = Path.Combine(outDir, outName);

PhotoAnnotator.SaveJpeg(bitmap, outputPath);

Console.WriteLine();
Console.WriteLine($"{drawnCount} of {spotCount} spot(s) drawn on the {bitmap.Width}x{bitmap.Height} picture (rotated {rotation} deg clockwise to look upright).");
Console.WriteLine($"Saved: {outputPath}");

return 0;

static string Signed(double value)
{
    // Avoid "-+0.00" for tiny negative values that round to zero.
    double v = Math.Abs(value) < 0.005 ? 0.0 : value;
    return v.ToString("+0.00;-0.00", CultureInfo.InvariantCulture);
}

static double ReadDouble(string prompt)
{
    while (true)
    {
        Console.Write(prompt);
        string? line = Console.ReadLine();
        if (double.TryParse(line, NumberStyles.Float, CultureInfo.InvariantCulture, out double value))
            return value;
        Console.WriteLine("Please enter a valid number.");
    }
}

static int ReadInt(string prompt, int min, int max)
{
    while (true)
    {
        Console.Write(prompt);
        string? line = Console.ReadLine();
        if (int.TryParse(line, NumberStyles.Integer, CultureInfo.InvariantCulture, out int value)
            && value >= min && value <= max)
            return value;
        Console.WriteLine($"Please enter a whole number from {min} to {max}.");
    }
}
