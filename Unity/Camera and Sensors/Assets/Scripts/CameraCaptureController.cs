using System;
using System.IO;
using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// Shows a live WebCamTexture feed on a RawImage and, on Capture(),
/// saves a JPEG plus a JSON sensor snapshot with matching file names
/// into Application.persistentDataPath.
/// Requires a SensorLogger component in the scene.
/// </summary>
[RequireComponent(typeof(AudioSource))] // harmless; some Android camera stacks expect an AudioListener/Source present
public class CameraCaptureController : MonoBehaviour
{
    [Header("References")]
    public RawImage previewImage;      // assign a RawImage on your Canvas
    public SensorLogger sensorLogger;  // assign the SensorLogger in the scene

    [Header("Camera settings")]
    public int requestedWidth = 1920;
    public int requestedHeight = 1080;
    public int requestedFPS = 30;
    [Tooltip("Leave empty to use the first available camera (usually rear-facing).")]
    public string preferredCameraName = "";

    WebCamTexture webCamTexture;

    void Start()
    {
        RequestPermissionsIfNeeded();
        StartCoroutineSafe();
    }

    void RequestPermissionsIfNeeded()
    {
#if UNITY_ANDROID
        if (!UnityEngine.Android.Permission.HasUserAuthorizedPermission(UnityEngine.Android.Permission.Camera))
            UnityEngine.Android.Permission.RequestUserPermission(UnityEngine.Android.Permission.Camera);
        if (!UnityEngine.Android.Permission.HasUserAuthorizedPermission(UnityEngine.Android.Permission.FineLocation))
            UnityEngine.Android.Permission.RequestUserPermission(UnityEngine.Android.Permission.FineLocation);
#endif
    }

    void StartCoroutineSafe()
    {
        StartCoroutine(InitCamera());
    }

    System.Collections.IEnumerator InitCamera()
    {
        // Give the permission dialogs a moment on first run.
        yield return new WaitForSeconds(0.5f);

        WebCamDevice[] devices = WebCamTexture.devices;
        if (devices.Length == 0)
        {
            Debug.LogError("CameraCaptureController: No camera devices found.");
            yield break;
        }

        string deviceName = devices[0].name;
        if (!string.IsNullOrEmpty(preferredCameraName))
        {
            foreach (var d in devices)
                if (d.name == preferredCameraName) deviceName = d.name;
        }

        webCamTexture = new WebCamTexture(deviceName, requestedWidth, requestedHeight, requestedFPS);
        webCamTexture.Play();
        previewImage.rectTransform.localEulerAngles = new Vector3(0f, 0f, -webCamTexture.videoRotationAngle);

        if (previewImage != null)
        {
            previewImage.texture = webCamTexture;
            previewImage.material.mainTexture = webCamTexture;
        }
    }

    /// <summary>
    /// Call this from a UI Button's OnClick, or anywhere else, to take a photo.
    /// </summary>
    public void Capture()
    {
        if (webCamTexture == null || !webCamTexture.isPlaying)
        {
            Debug.LogWarning("CameraCaptureController: Camera not ready yet.");
            return;
        }

        string baseName = DateTime.UtcNow.ToString("yyyyMMdd_HHmmssfff");
        string photoFileName = baseName + ".jpg";
        string jsonFileName = baseName + ".json";

        // 1. Grab the sensor snapshot FIRST, right next to the pixel grab,
        //    so the two are as close in time as possible.
        SensorSnapshot snapshot = sensorLogger != null
            ? sensorLogger.GetSnapshot(photoFileName)
            : null;

        // 2. Grab the frame and encode it.
        Texture2D photo = new Texture2D(webCamTexture.width, webCamTexture.height, TextureFormat.RGB24, false);
        photo.SetPixels32(webCamTexture.GetPixels32());
        photo.Apply();
        byte[] jpgBytes = photo.EncodeToJPG(90);
        Destroy(photo);

        // 3. Save both files.
        string dir = Application.persistentDataPath;
        string photoPath = Path.Combine(dir, photoFileName);
        string jsonPath = Path.Combine(dir, jsonFileName);

        File.WriteAllBytes(photoPath, jpgBytes);

        if (snapshot != null)
        {
            string json = JsonUtility.ToJson(snapshot, true);
            File.WriteAllText(jsonPath, json);
        }

        Debug.Log($"Captured photo + sensor data:\n{photoPath}\n{jsonPath}");
    }

    void OnDestroy()
    {
        if (webCamTexture != null && webCamTexture.isPlaying)
            webCamTexture.Stop();
    }
}
