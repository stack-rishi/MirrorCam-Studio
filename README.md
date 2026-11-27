<div align="center">

<img src="app_icon.png" alt="MirrorCam Studio Logo" width="130" style="border-radius: 24px;" />

# MirrorCam Studio

### *More Than Just a Webcam.*

**One Webcam. Multiple Possibilities. Complete Control.**

Customise what people see on your Windows video calls — mirror your live webcam, display a favourite photo, loop a video clip, or bring animated GIFs into **WhatsApp Desktop**, **Discord**, **Zoom**, **Google Meet**, and **Microsoft Teams**.

[![Download MirrorCam.exe](https://img.shields.io/badge/Download-MirrorCam.exe%20(v1.0.0)-2563eb?style=for-the-badge&logo=windows)](https://github.com/stack-rishi/MirrorCam-Studio/releases/download/v1.0.0/MirrorCam.exe)
[![Platform](https://img.shields.io/badge/Windows-10%20%2F%2011-0078D6?style=for-the-badge&logo=windows11)](https://github.com/stack-rishi/MirrorCam-Studio/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-10b981?style=for-the-badge)](LICENSE)

</div>

---

> **Your webcam doesn't have to show only your face. Show what you want, the way you want.**

Ever jumped onto a video call and felt thrown off because your camera wasn't mirrored — or wished you could show a photo, play a looping clip, or drop an animated GIF straight through your camera feed instead of sitting in front of the lens?

**MirrorCam Studio** gives you complete control over your outgoing webcam on Windows. Pick a source, hit **Start Stream**, and choose the virtual camera in your calling app. No complicated video-editing setup required.

---

## ✨ What You Can Do With MirrorCam Studio

| What You Want | How MirrorCam Helps |
|---|---|
| **Mirror your live camera** | Horizontally flip your physical webcam so people see the natural reflection you're used to — great for reading notes, holding up objects, or just feeling comfortable on camera. |
| **Use any photo as your webcam** | Turn a `.png`, `.jpg`, `.jpeg`, `.webp`, or `.bmp` image into a clean live feed — ideal for "Be Right Back" cards, profile artwork, or study slides. |
| **Loop videos automatically** | Select any `.mp4`, `.mkv`, `.avi`, `.mov`, `.wmv`, `.webm`, or `.flv` video and MirrorCam replays it smoothly in an endless loop. |
| **Send animated GIFs in calls** | Pick any `.gif` and let it animate frame-by-frame inside your Discord, Zoom, or WhatsApp call. |
| **Keep everything sharp & proportional** | Automatic Per-Monitor High-DPI support and screen-matching resolution (`1920×1080`, `1280×720`, etc.) with clean letterboxing so nothing gets stretched or blurry. |
| **Connect to WhatsApp Desktop effortlessly** | Includes a pop-out **Clean Feed** and **1-click hands-free OBS automation** that handles the DroidCam Virtual Output bridge for Windows WhatsApp automatically. |

---

## 👥 Who Is This For?

- **College Students** — Customise your camera feed during online classes, study sessions, and club calls.
- **Remote Teams & Presenters** — Keep a polished, mirrored view or show clean visual placeholders between meetings.
- **Creators & Gamers** — Experiment with looping intros, reaction GIFs, and creative camera feeds on Discord.
- **Anyone on Video Calls** — Take control of how you show up on WhatsApp, Meet, Zoom, and Teams.

---

## 🚀 Quick Start (No Coding Required)

### Step 1: Install OBS Studio
MirrorCam uses the virtual camera driver included with **[OBS Studio](https://obsproject.com/)**.  
Download and install OBS Studio once. *(If you use Discord, Zoom, Meet, or Teams, you don't even have to open OBS manually — just having it installed gives Windows the virtual camera driver.)*

### Step 2: Download & Run MirrorCam Studio
1. Download **[MirrorCam.exe](https://github.com/stack-rishi/MirrorCam-Studio/releases/download/v1.0.0/MirrorCam.exe)** from the [Releases](https://github.com/stack-rishi/MirrorCam-Studio/releases/latest) page.
2. Double-click `MirrorCam.exe` to open the studio.
3. Choose your input source:
   - **📷 Physical Webcam** (select Camera Index `0`, `1`, etc.), or
   - **📁 Media File** (browse for any photo, video, or `.gif`).
4. Toggle **Mirror output (Flip horizontally)** or **Match Screen** resolution if needed.
5. Click **▶ Start Stream**.

---

## 📱 Connecting to Your Calling App

### Discord, Zoom, Google Meet & Microsoft Teams
These apps work right out of the box:
1. Click **▶ Start Stream** in MirrorCam Studio.
2. Open Video Settings in your calling app and pick **`OBS Virtual Camera`**.
3. *(Tip)* If your app has its own "Mirror my video" preview toggle, turn that off so you don't accidentally flip the video twice.

---

### Windows WhatsApp Desktop (Microsoft Store App)
> **Why does WhatsApp Desktop need an extra step?**  
> Unlike Discord or Chrome, the Windows Store version of WhatsApp runs inside an AppContainer sandbox and only recognises kernel-level Windows camera drivers — it hides standard virtual cameras like OBS Virtual Camera. MirrorCam solves this cleanly with a built-in **Clean Feed + OBS + DroidCam** bridge.

#### One-Time Setup (Takes ~2 minutes):
1. Download and install the free **DroidCam OBS Virtual Output** plugin & drivers from [dev47apps releases](https://github.com/dev47apps/droidcam-obs-virtual-output/releases) (install both `DroidCam.Drivers` and `DroidCam.OBSVirtualOut.Plugin`, then restart your PC once).
2. Open **OBS Studio**, click **`+`** under **Sources** ➔ **Window Capture**, and select **`MirrorCam Clean Feed`**. Right-click the source ➔ **Transform** ➔ **Fit to Screen**. *(OBS saves this permanently — you never have to set this up again!)*

#### Everyday Hands-Free Usage:
1. Open **MirrorCam Studio** and leave **⚡ Auto-connect OBS (hands-free)** checked.
2. Click **▶ Start Stream** — MirrorCam pops out the Clean Feed, launches OBS in the background, activates DroidCam Virtual Output automatically, and minimises OBS out of your way.
3. In **WhatsApp Desktop**, pick **`DroidCam Video`** as your camera.

> **💡 Zero-Setup Alternative:** Opening **[web.whatsapp.com](https://web.whatsapp.com)** in Chrome or Edge detects **`OBS Virtual Camera`** directly with no extra plugins needed.

---

## 💻 Running From Source & Command-Line (CLI)

Prefer running from Python or automating streams from the terminal?

### Setup
```powershell
git clone https://github.com/stack-rishi/MirrorCam-Studio.git
cd MirrorCam-Studio
pip install -r requirements.txt
```

### Launch the GUI
```powershell
python mirrorcam_gui.py
```

### Use the CLI (`camera.py`)
```powershell
# Stream your webcam matching your native screen resolution & aspect ratio
python camera.py --match-screen

# Stream webcam at 1080p @ 30 FPS
python camera.py --camera 0 --width 1920 --height 1080 --fps 30

# Stream a looping video, photo, or animated GIF
python camera.py --file path/to/clip.mp4
python camera.py --file path/to/photo.png
python camera.py --file path/to/reaction.gif

# Passthrough without horizontal flip or without preview window
python camera.py --file path/to/clip.mp4 --no-mirror --no-preview
```

### Build Your Own `MirrorCam.exe`
```powershell
pip install pyinstaller
pyinstaller MirrorCam.spec --noconfirm
```
The compiled executable will appear in `dist/MirrorCam.exe`.

---

## 📁 What's Inside the Repo

```text
MirrorCam-Studio/
├── mirrorcam_gui.py     # Main Windows GUI (High-DPI aware, Clean Feed & OBS automation)
├── camera.py            # Lightweight CLI streamer for webcams, photos, videos & GIFs
├── activate_obs.py      # Standalone script to auto-launch OBS & enable DroidCam output
├── activate_obs.bat     # Double-click shortcut for standalone OBS activation
├── MirrorCam.spec       # PyInstaller configuration to build MirrorCam.exe
├── app_icon.ico         # Windows executable & window icon
├── app_icon.png         # Studio brand logo
├── requirements.txt     # Python dependencies (opencv-python, pyvirtualcam, pillow)
├── LICENSE              # MIT License
└── README.md            # Project guide
```

---

## ❓ Troubleshooting

- **My calling app doesn't list `OBS Virtual Camera`:**  
  Make sure OBS Studio is installed, click **Start Stream** in MirrorCam first, and then restart your calling app so it refreshes available video devices.
- **WhatsApp Desktop still only shows my built-in webcam:**  
  Verify the **DroidCam Virtual Output** drivers are installed and that you restarted Windows afterwards. In MirrorCam, click **📱 WhatsApp Setup** for the quick 4-step checklist.
- **`Could not open camera index 0`:**  
  Another app (Windows Camera, Zoom, Discord) currently owns your physical webcam. Close the other app or switch **Camera Index** to `1`.
- **My video looks flipped the wrong way:**  
  Check **Mirror output (Flip horizontally)** in MirrorCam and disable any built-in mirror toggle inside Discord/Zoom/Meet.

---

<div align="center">

**"Don't just join the call. Make your camera yours."**

If MirrorCam Studio saved you time or made your calls more fun, feel free to star the repo!

</div>
