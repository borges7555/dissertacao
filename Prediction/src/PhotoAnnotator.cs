using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Drawing.Text;

namespace SensorPositionPredictor;

/// <summary>
/// Draws numbered markers on a bitmap and saves it as JPEG.
/// Uses System.Drawing.Common, which works reliably on Windows.
/// </summary>
public static class PhotoAnnotator
{
    public static readonly (Color Color, string Name)[] Palette =
    {
        (Color.FromArgb(220, 20, 20), "red"),
        (Color.FromArgb(30, 90, 220), "blue"),
        (Color.FromArgb(150, 40, 190), "purple"),
        (Color.FromArgb(235, 120, 0), "orange"),
        (Color.FromArgb(0, 145, 145), "teal"),
        (Color.FromArgb(210, 30, 130), "magenta"),
    };

    /// <summary>Colour (and its name) used for spot number 1, 2, 3, ... (cycles after six).</summary>
    public static (Color Color, string Name) StyleFor(int number) =>
        Palette[(number - 1) % Palette.Length];

    /// <summary>
    /// Draws a coloured disc with a white outline and the spot number inside it,
    /// centred on pixelPos. Call this on the picture in its FINAL orientation so
    /// the digit is always upright.
    /// </summary>
    public static void DrawNumberedMarker(Bitmap bitmap, (double X, double Y) pixelPos, int number, int radius = 12)
    {
        var (color, _) = StyleFor(number);

        using var g = Graphics.FromImage(bitmap);
        g.SmoothingMode = SmoothingMode.AntiAlias;
        g.TextRenderingHint = TextRenderingHint.AntiAliasGridFit;

        float cx = (float)pixelPos.X;
        float cy = (float)pixelPos.Y;
        float left = cx - radius;
        float top = cy - radius;
        float size = radius * 2;

        using var fillBrush = new SolidBrush(color);
        using var outlinePen = new Pen(Color.White, 3);
        g.FillEllipse(fillBrush, left, top, size, size);
        g.DrawEllipse(outlinePen, left, top, size, size);

        using var font = new Font("Arial", radius * 0.95f, FontStyle.Bold, GraphicsUnit.Pixel);
        using var textBrush = new SolidBrush(Color.White);
        using var format = new StringFormat
        {
            Alignment = StringAlignment.Center,
            LineAlignment = StringAlignment.Center
        };
        g.DrawString(number.ToString(), font, textBrush, new RectangleF(left, top, size, size), format);
    }

    public static void SaveJpeg(Bitmap bitmap, string outputPath)
    {
        bitmap.Save(outputPath, ImageFormat.Jpeg);
    }
}
