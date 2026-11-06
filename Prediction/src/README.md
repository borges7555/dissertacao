# SensorPositionPredictor

Standalone .NET console app. Given a photo and its matching sensor JSON (from
your Unity app), it asks for the true coordinates of where you stood and of
the target you photographed, works out where the target should appear in the
frame from the phone's measured 3D orientation, and draws a red marker on a
copy of the photo.

Works for any way of holding the phone: portrait, upside-down, landscape left
or right, with a bit of roll.

## Requirements
- .NET 8 SDK
- Windows (uses `System.Drawing.Common`, which needs Windows or libgdiplus elsewhere)

## Build
```
dotnet build -c Release
```

## Run
```
dotnet run -- "C:\path\to\photo.jpg" "C:\path\to\photo.json"
```
or run the compiled exe directly:
```
bin\Release\net8.0\SensorPositionPredictor.exe "C:\path\to\photo.jpg" "C:\path\to\photo.json"
```
## Without the sensor JSON
If you give only the photo (a .jpg), the program asks you to type the sensor
values it would otherwise read from the JSON, then carries on as normal:
```
SensorPositionPredictor "C:\path\to\photo.jpg"
```
It asks for `accelX/Y/Z` (in g, as Unity saves them: gravity direction, so
portrait upright = 0, -1, 0), `magX/Y/Z` (in uT), the magnetic declination
(`trueHeading - magneticHeading` from the JSON; Enter = 0), and how the phone
was held (1-4, or Enter to work it out from gravity). At any number prompt you
can paste a whole line from the JSON, e.g. `"accelX": -0.98,` — only the number
is used.

Give it the ORIGINAL file straight from the app. (If you rotate it yourself,
rotate it clockwise to portrait; a "rotate" that only sets a metadata flag
makes no difference, because the program goes by the pixel dimensions.)

It prints how the phone was held and the camera heading/pitch it computed,
then asks for:
1. Your true latitude/longitude (the known-correct value, not GPS) and the
   device height above the ground, in meters. Asked once.
2. How many spots you want to calculate (1-50).
3. For each spot: its true latitude/longitude and its height above its own
   local ground, in meters.

All spots are drawn on ONE picture as numbered, colour-coded markers (1 = red,
2 = blue, 3 = purple, 4 = orange, 5 = teal, 6 = magenta, then the colours repeat).
A results table is printed at the end with, for every spot: distance, bearing,
elevation, offset from the picture centre, and whether it was drawn, fell
outside the frame (with where it would have been), or is behind the camera.
Spots that don't fall inside the photo are listed but not drawn; if none do,
nothing is saved.

The field of view and the other settings are constants at the top of `Program.cs`.

**Note on heights:** "height above ground" at your spot and at the target is
used as if both local ground levels were at the same elevation. Fine for
nearby targets on flat ground; otherwise enter heights that already include
the elevation difference.

## How it handles different poses
- The saved JPEG is the camera sensor's frame, fixed to the phone's body (1920x1080,
  the upright portrait image turned 90 deg left) no matter how the phone is held.
  The program rotates it 90 deg clockwise to get the "device-upright" frame.
- The target direction is worked out from the full orientation (gravity +
  magnetic field), expressed in the phone's own axes, and projected with a
  pinhole camera model. That is why portrait, landscape, upside-down and roll
  all work with no special cases.
- The `deviceOrientation` field in the JSON (cross-checked against gravity) is
  only used to rotate the FINISHED picture upright, so the output looks the
  way you held the phone. If the field is FaceUp/FaceDown/Unknown, the posture
  is inferred from gravity.
- Unity's own compass heading is NOT used: it follows the phone's top edge
  (off by +/-90 deg in landscape, 180 deg upside-down, and unstable when upright).

## Settings (top of Program.cs)
- `HorizontalFovDeg` / `VerticalFovDeg` — measured for the device-upright frame
  (across the phone's X axis / Y axis).
- `CompassBiasDeg` — how many degrees the sensor heading reads too high compared
  with reality. Default 0. If every dot lands ~9 deg left of its target, set 9.0.
- `ExpectedFieldMicroTesla` / `ExpectedDipDeg` — Earth's field at your location,
  only used to judge magnetometer calibration quality.

Output is saved as `<photoName>_prediction.jpg` next to the compiled executable.

## Files
- `Program.cs` — entry point, prompts, orchestration
- `GeoMath.cs` — bearing/distance/elevation math
- `Vec3.cs` — minimal 3D vector
- `CameraOrientation.cs` — full phone orientation from the raw accelerometer + magnetometer
- `DevicePosture.cs` — how the phone was held; how to rotate the output upright
- `TargetProjector.cs` — target direction -> pixel (pinhole model)
- `SensorSnapshot.cs` — matches your Unity JSON, for `System.Text.Json`
- `SpotResult.cs` — the numbers calculated for one spot
- `ManualSensorInput.cs` — asks for the sensor values when no JSON is given
- `PhotoAnnotator.cs` — draws the numbered markers and saves the JPEG (the only Windows-specific part)

Everything except `PhotoAnnotator.cs` is plain C# with no Unity or image
dependency, so it can be copied into the Unity project unchanged.
