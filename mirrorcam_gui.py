"""
MirrorCam GUI - Desktop application to stream flipped or normal video
from physical webcams, static photos, looping videos, or animated GIFs
directly into the OBS Virtual Camera for WhatsApp, Discord, Zoom, and Meet.

Supports Windows High-DPI scaling (Per-Monitor V2) and automatic
screen resolution / aspect ratio detection.

Requirements:
    pip install opencv-python pyvirtualcam pillow

Run:
    python mirrorcam_gui.py
"""

import math
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser

# Enable Per-Monitor V2 DPI awareness on Windows before creating GUI
if sys.platform == "win32":
    try:
        import ctypes
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                import ctypes
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageSequence, ImageTk

try:
    import pyvirtualcam
    from pyvirtualcam import PixelFormat

    VCAM_AVAILABLE = True
except ImportError:
    VCAM_AVAILABLE = False


VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".flv", ".m4v"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}
GIF_EXTS = {".gif"}


def get_screen_info():
    """Detects primary monitor width, height, and simplified aspect ratio string."""
    sw, sh = 1920, 1080
    if sys.platform == "win32":
        try:
            import ctypes
            user32 = ctypes.windll.user32
            sw = user32.GetSystemMetrics(0)
            sh = user32.GetSystemMetrics(1)
        except Exception:
            pass

    g = math.gcd(sw, sh) if sw and sh else 1
    ar_w, ar_h = sw // g, sh // g
    if (ar_w, ar_h) == (8, 5):
        ratio_str = "16:10"
    elif (ar_w, ar_h) == (16, 9):
        ratio_str = "16:9"
    elif (ar_w, ar_h) == (4, 3):
        ratio_str = "4:3"
    elif (ar_w, ar_h) == (64, 27):
        ratio_str = "21:9"
    else:
        ratio_str = f"{ar_w}:{ar_h}"
    return sw, sh, ratio_str


def fit_frame_to_target(frame: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
    """Scales frame to fit target dimensions while preserving aspect ratio (letterboxing).
    Uses INTER_AREA for downscaling and INTER_CUBIC for upscaling to guarantee crisp sharpness."""
    fh, fw = frame.shape[:2]
    if fw == target_w and fh == target_h:
        return frame

    scale = min(target_w / fw, target_h / fh)
    new_w = max(1, int(round(fw * scale)))
    new_h = max(1, int(round(fh * scale)))

    interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
    resized = cv2.resize(frame, (new_w, new_h), interpolation=interp)

    canvas = np.zeros((target_h, target_w, 3), dtype=np.uint8)
    x_offset = (target_w - new_w) // 2
    y_offset = (target_h - new_h) // 2
    canvas[y_offset : y_offset + new_h, x_offset : x_offset + new_w] = resized
    return canvas


def load_gif_frames(filepath: str) -> list[tuple[np.ndarray, float]]:
    """Loads all frames from an animated GIF and their durations in seconds."""
    pil_img = Image.open(filepath)
    frames = []
    for frame in ImageSequence.Iterator(pil_img):
        duration = frame.info.get("duration", 100) / 1000.0
        if duration <= 0.01:
            duration = 0.08  # Default ~12 fps if missing
        frame_rgb = frame.convert("RGB")
        frame_np = np.array(frame_rgb)
        frame_bgr = cv2.cvtColor(frame_np, cv2.COLOR_RGB2BGR)
        frames.append((frame_bgr, duration))
    if not frames:
        raise ValueError("No frames found in GIF")
    return frames


def load_static_image(filepath: str) -> np.ndarray:
    """Loads a static image using Pillow to guarantee support for all formats and alpha channels."""
    pil_img = Image.open(filepath).convert("RGB")
    frame_np = np.array(pil_img)
    return cv2.cvtColor(frame_np, cv2.COLOR_RGB2BGR)


def create_placeholder_image(w: int = 380, h: int = 214, text: str = "Click 'Start Stream' below") -> ImageTk.PhotoImage:
    """Creates a clean, DPI-scaled placeholder graphic for the preview area."""
    img = Image.new("RGB", (w, h), color=(26, 26, 30))
    draw = ImageDraw.Draw(img)

    center_x, center_y = w // 2, h // 2 - 14
    box_w = min(28, w // 14)
    box_h = min(20, h // 11)

    # Camera body outline
    draw.rounded_rectangle(
        [center_x - box_w, center_y - box_h, center_x + box_w, center_y + box_h],
        radius=4,
        outline=(110, 110, 125),
        width=2,
    )
    lens_r = min(11, box_h // 2)
    draw.ellipse(
        [center_x - lens_r, center_y - lens_r, center_x + lens_r, center_y + lens_r],
        outline=(110, 110, 125),
        width=2,
    )
    draw.rounded_rectangle(
        [center_x - 9, center_y - box_h - 5, center_x + 9, center_y - box_h + 1],
        radius=2,
        fill=(90, 90, 105),
    )

    draw.text((w // 2, center_y + box_h + 18), text, fill=(170, 170, 185), anchor="mm")
    return ImageTk.PhotoImage(img)


class CleanFeedWindow:
    """A clean, dedicated high-resolution window displaying ONLY the processed video feed.
    Designed for OBS Window Capture to feed DroidCam Virtual Output -> WhatsApp Desktop."""

    def __init__(self, master, target_w=1280, target_h=720, on_close=None):
        self.top = tk.Toplevel(master)
        self.top.title("MirrorCam Clean Feed")
        self.target_w = target_w
        self.target_h = target_h
        self.on_close = on_close
        self.is_alive = True
        self._busy = False

        # Size window to match target stream resolution or clean 16:9 HD
        win_w = min(1280, target_w)
        win_h = int(win_w * target_h / target_w) if target_w else 720
        self.top.geometry(f"{win_w}x{win_h}")
        self.top.minsize(480, 270)
        self.top.configure(bg="#000000")

        # Set window icon if icon file exists
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_icon.ico")
        if os.path.exists(icon_path):
            try:
                self.top.iconbitmap(icon_path)
            except Exception:
                pass

        self.label = tk.Label(
            self.top,
            text="MirrorCam Clean Feed\n\n(Capture this window in OBS with 'Window Capture')",
            foreground="#888888",
            bg="#000000",
            font=("Segoe UI", 12),
        )
        self.label.pack(fill="both", expand=True)
        self.imgtk = None
        self.top.protocol("WM_DELETE_WINDOW", self._handle_close)

    def _handle_close(self):
        self.is_alive = False
        try:
            self.top.destroy()
        except Exception:
            pass
        if self.on_close:
            self.on_close()

    def update_frame(self, frame_bgr: np.ndarray):
        if not self.is_alive or self._busy:
            return
        self._busy = True
        try:
            cur_w = self.label.winfo_width()
            cur_h = self.label.winfo_height()
            if cur_w <= 10 or cur_h <= 10:
                cur_w, cur_h = self.target_w, self.target_h

            # Fit frame into current window keeping aspect ratio (letterbox on black canvas)
            fitted = fit_frame_to_target(frame_bgr, cur_w, cur_h)
            rgb = cv2.cvtColor(fitted, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb)
            imgtk = ImageTk.PhotoImage(image=img)
            self.imgtk = imgtk
            self.label.configure(image=imgtk, text="")
        except Exception:
            pass
        finally:
            self._busy = False

    def close(self):
        self.is_alive = False
        try:
            self.top.destroy()
        except Exception:
            pass


class WhatsAppGuideDialog:
    """Dialog providing step-by-step instructions to connect MirrorCam to WhatsApp Desktop via DroidCam."""

    def __init__(self, master):
        self.top = tk.Toplevel(master)
        self.top.title("WhatsApp Desktop Setup Guide")
        self.top.geometry("540x540")
        self.top.resizable(True, True)
        self.top.transient(master)
        self.top.grab_set()

        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_icon.ico")
        if os.path.exists(icon_path):
            try:
                self.top.iconbitmap(icon_path)
            except Exception:
                pass

        # Header
        ttk.Label(
            self.top, text="📱 Connect to Windows WhatsApp", font=("Segoe UI", 14, "bold")
        ).pack(pady=(12, 2))
        ttk.Label(
            self.top,
            text="Windows WhatsApp (Store app) requires an AVStream/Media Foundation\ndriver which DroidCam Virtual Output provides.",
            foreground="#555555",
            justify="center",
            font=("Segoe UI", 9),
        ).pack(pady=(0, 8))

        # Steps container
        steps_frame = ttk.LabelFrame(self.top, text=" 4-Step Setup Guide ", padding=10)
        steps_frame.pack(fill="both", expand=True, padx=16, pady=4)

        steps = [
            ("1. Install DroidCam Virtual Output Driver",
             "Download & install the free 'droidcam-obs-virtual-output' plugin/driver. Then restart your PC."),
            ("2. Enable Clean Feed in MirrorCam",
             "Check the 'Pop-out Clean Feed' box in MirrorCam and click 'Start Stream'."),
            ("3. Capture in OBS Studio",
             "Open OBS Studio. Under Sources, click '+' -> 'Window Capture' -> select 'MirrorCam Clean Feed'."),
            ("4. Activate DroidCam & Select in WhatsApp",
             "In OBS top menu: Tools -> DroidCam Virtual Output -> click Active.\nIn WhatsApp Desktop Settings -> Video: select 'DroidCam Video'!")
        ]

        for title, desc in steps:
            row = ttk.Frame(steps_frame)
            row.pack(fill="x", pady=4)
            ttk.Label(row, text=title, font=("Segoe UI", 9, "bold")).pack(anchor="w")
            ttk.Label(row, text=desc, font=("Segoe UI", 9), foreground="#333333", wraplength=480, justify="left").pack(anchor="w", padx=(10, 0))

        # Tip box
        tip_frame = ttk.Frame(self.top)
        tip_frame.pack(fill="x", padx=16, pady=4)
        ttk.Label(
            tip_frame,
            text="💡 Quick Alternative: WhatsApp Web (in Chrome/Edge) directly supports OBS Virtual Camera with zero extra setup!",
            font=("Segoe UI", 8, "italic"),
            foreground="#047857",
            wraplength=490,
            justify="center",
        ).pack()

        # Buttons
        btn_row = ttk.Frame(self.top)
        btn_row.pack(fill="x", padx=16, pady=(8, 12))

        ttk.Button(
            btn_row,
            text="🌐 Download DroidCam Driver",
            command=lambda: webbrowser.open("https://github.com/dev47apps/droidcam-obs-virtual-output/releases"),
        ).pack(side="left")

        ttk.Button(btn_row, text="Close", command=self.top.destroy, width=12).pack(side="right")


def automate_obs_droidcam():
    """Launches OBS Studio (if not running) and activates DroidCam Virtual Output automatically."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32

    obs_exe = r"C:\Program Files\obs-studio\bin\64bit\obs64.exe"
    if not os.path.isfile(obs_exe):
        cand = os.path.expandvars(r"%ProgramFiles%\obs-studio\bin\64bit\obs64.exe")
        if os.path.isfile(cand):
            obs_exe = cand
        else:
            return False, "OBS Studio executable not found at Program Files."

    # Clear sentinel folder so crash prompts don't block
    sentinel_dir = os.path.expandvars(r"%APPDATA%\obs-studio\.sentinel")
    if os.path.isdir(sentinel_dir):
        for f in os.listdir(sentinel_dir):
            try:
                os.remove(os.path.join(sentinel_dir, f))
            except Exception:
                pass

    # Check if OBS is already running
    is_running = False
    try:
        output = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq obs64.exe", "/NH"],
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        is_running = "obs64.exe" in output.lower()
    except Exception:
        pass

    if not is_running:
        obs_dir = os.path.dirname(obs_exe)
        try:
            subprocess.Popen([obs_exe], cwd=obs_dir)
            time.sleep(3.5)
        except Exception as e:
            return False, f"Failed to launch OBS: {e}"

    # Find OBS main window handle
    obs_hwnd = None
    for _ in range(15):
        def enum_cb(hwnd, lparam):
            nonlocal obs_hwnd
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value
                if title.startswith("OBS ") or "OBS Studio" in title:
                    obs_hwnd = hwnd
                    return False
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
        if obs_hwnd:
            break
        time.sleep(0.5)

    if not obs_hwnd:
        return False, "OBS window not ready."

    # Restore and bring OBS to front
    user32.ShowWindow(obs_hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(obs_hwnd)
    time.sleep(0.4)

    # Send menu keystrokes: Alt+T -> d -> d -> Enter -> Space -> Esc
    ps_cmd = """
    $ws = New-Object -ComObject Wscript.Shell
    if ($ws.AppActivate('OBS')) {
        Start-Sleep -Milliseconds 350
        $ws.SendKeys('%t')
        Start-Sleep -Milliseconds 250
        $ws.SendKeys('d')
        Start-Sleep -Milliseconds 150
        $ws.SendKeys('d')
        Start-Sleep -Milliseconds 150
        $ws.SendKeys('~')
        Start-Sleep -Milliseconds 500
        $ws.SendKeys(' ')
        Start-Sleep -Milliseconds 250
        $ws.SendKeys('{ESC}')
    }
    """
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except Exception as e:
        return False, f"Failed to send keystrokes: {e}"

    time.sleep(0.5)
    # Minimize OBS to keep desktop tidy
    user32.ShowWindow(obs_hwnd, 6)  # SW_MINIMIZE

    return True, "OBS Studio launched and DroidCam output activated!"


class MirrorCamApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("MirrorCam - Virtual Camera Studio")

        # DPI Scaling & Sizing
        self.dpi = self.root.winfo_fpixels("1i")
        self.scale = max(1.0, self.dpi / 96.0)

        sw, sh, self.screen_ratio = get_screen_info()
        win_w = max(560, int(460 * self.scale))
        win_h = min(int(620 * self.scale), int(sh * 0.88))
        self.root.geometry(f"{win_w}x{win_h}")
        self.root.minsize(500, 560)
        self.root.resizable(True, True)

        # Preview dimensions scaled to DPI
        self.preview_w = min(460, int(380 * self.scale))
        self.preview_h = int(self.preview_w * 9 / 16)

        # Set window icon if icon file exists
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_icon.ico")
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except Exception:
                pass

        self.running = False
        self.stop_event = threading.Event()
        self.worker_thread = None

        # Clean Feed, OBS Automation & Guides
        self.clean_feed_var = tk.BooleanVar(value=True)
        self.clean_feed_window = None
        self.auto_obs_var = tk.BooleanVar(value=True)

        # State Variables
        self.source_type_var = tk.StringVar(value="webcam")  # "webcam" or "file"
        self.media_file_path = tk.StringVar(value="")
        self.camera_var = tk.StringVar(value="0")

        # Dynamic Resolutions with Screen Native matching
        self.native_res_str = f"{sw}x{sh} (Screen Native {self.screen_ratio})"
        self.res_options = [self.native_res_str]
        standard_list = [
            "1920x1080 (16:9 FHD)",
            "1280x720 (16:9 HD)",
            "2560x1440 (16:9 2K QHD)",
            "1920x1200 (16:10 WUXGA)",
            "1600x900 (16:9 HD+)",
            "1280x960 (4:3)",
            "640x480 (4:3 SD)",
        ]
        for item in standard_list:
            if not item.startswith(f"{sw}x{sh}"):
                self.res_options.append(item)

        self.resolution_var = tk.StringVar(value=self.native_res_str)
        self.fps_var = tk.StringVar(value="30")
        self.mirror_var = tk.BooleanVar(value=True)
        self.letterbox_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Ready (Click 'Start Stream')")

        self._build_ui()

    # ---------- UI ----------

    def _build_ui(self):
        # Header
        header_frame = ttk.Frame(self.root)
        header_frame.pack(fill="x", pady=(10, 4))
        ttk.Label(header_frame, text="MirrorCam Studio", font=("Segoe UI", 16, "bold")).pack()
        ttk.Label(
            header_frame,
            text="Stream Webcam, Photos, Looping Videos & GIFs to OBS Virtual Cam",
            foreground="#555555",
            font=("Segoe UI", 9),
        ).pack()

        # 1. Source Selection Frame
        source_frame = ttk.LabelFrame(self.root, text=" 1. Input Source ", padding=8)
        source_frame.pack(fill="x", padx=16, pady=(4, 6))

        source_btn_row = ttk.Frame(source_frame)
        source_btn_row.pack(fill="x", pady=(0, 4))

        ttk.Radiobutton(
            source_btn_row,
            text="📷 Physical Webcam",
            value="webcam",
            variable=self.source_type_var,
            command=self._on_source_changed,
        ).pack(side="left", padx=(0, 16))

        ttk.Radiobutton(
            source_btn_row,
            text="📁 Media File (Photo / Looping Video / GIF)",
            value="file",
            variable=self.source_type_var,
            command=self._on_source_changed,
        ).pack(side="left")

        # Webcam controls container
        self.webcam_controls = ttk.Frame(source_frame)
        self.webcam_controls.pack(fill="x", pady=2)
        ttk.Label(self.webcam_controls, text="Camera Index:").pack(side="left", padx=(0, 8))
        ttk.Combobox(
            self.webcam_controls,
            textvariable=self.camera_var,
            values=["0", "1", "2", "3"],
            width=8,
            state="readonly",
        ).pack(side="left")

        # Media file controls container
        self.file_controls = ttk.Frame(source_frame)

        file_browse_row = ttk.Frame(self.file_controls)
        file_browse_row.pack(fill="x", pady=2)

        self.browse_btn = ttk.Button(file_browse_row, text="Browse Media...", command=self._browse_file)
        self.browse_btn.pack(side="left", padx=(0, 8))

        self.file_label = ttk.Label(
            file_browse_row,
            text="No file selected",
            foreground="#777777",
            font=("Segoe UI", 9, "italic"),
        )
        self.file_label.pack(side="left", fill="x", expand=True)

        self.clear_file_btn = ttk.Button(self.file_controls, text="Clear", width=8, command=self._clear_file)

        # 2. Output Settings Frame
        settings = ttk.LabelFrame(self.root, text=" 2. Stream & Video Settings ", padding=8)
        settings.pack(fill="x", padx=16, pady=4)

        # Resolution Row with Match Screen button
        res_row = ttk.Frame(settings)
        res_row.pack(fill="x", pady=3)
        ttk.Label(res_row, text="Resolution:").pack(side="left")
        
        ttk.Button(
            res_row,
            text="🖥️ Match Screen",
            command=lambda: self.resolution_var.set(self.native_res_str),
        ).pack(side="right", padx=(6, 0))

        ttk.Combobox(
            res_row,
            textvariable=self.resolution_var,
            values=self.res_options,
            state="readonly",
        ).pack(side="right", fill="x", expand=True, padx=(8, 0))

        # FPS Row
        fps_row = ttk.Frame(settings)
        fps_row.pack(fill="x", pady=3)
        ttk.Label(fps_row, text="Target FPS:").pack(side="left")
        ttk.Combobox(
            fps_row,
            textvariable=self.fps_var,
            values=["24", "30", "60"],
            width=12,
            state="readonly",
        ).pack(side="right")

        toggles_frame = ttk.Frame(self.root)
        toggles_frame.pack(fill="x", padx=18, pady=2)

        ttk.Checkbutton(
            toggles_frame,
            text="Mirror output (Flip horizontally)",
            variable=self.mirror_var,
        ).pack(side="left", padx=(0, 14))

        ttk.Checkbutton(
            toggles_frame,
            text="Preserve aspect ratio (Letterbox)",
            variable=self.letterbox_var,
        ).pack(side="left")

        # WhatsApp / OBS Clean Feed Row
        whatsapp_row = ttk.Frame(self.root)
        whatsapp_row.pack(fill="x", padx=18, pady=(4, 2))

        ttk.Checkbutton(
            whatsapp_row,
            text="📺 Pop-out Clean Feed (for OBS / WhatsApp)",
            variable=self.clean_feed_var,
            command=self._on_clean_feed_toggled,
        ).pack(side="left")

        ttk.Button(
            whatsapp_row,
            text="📱 WhatsApp Setup",
            command=self._show_whatsapp_guide,
        ).pack(side="right")

        # Auto-connect OBS Row
        auto_obs_row = ttk.Frame(self.root)
        auto_obs_row.pack(fill="x", padx=18, pady=(2, 4))

        ttk.Checkbutton(
            auto_obs_row,
            text="⚡ Auto-connect OBS (hands-free)",
            variable=self.auto_obs_var,
        ).pack(side="left")

        ttk.Button(
            auto_obs_row,
            text="⚡ Connect OBS Now",
            command=self._manual_activate_obs,
        ).pack(side="right")

        # 3. Live Preview Container
        preview_frame = ttk.Frame(self.root)
        preview_frame.pack(pady=4)

        self.placeholder_img = create_placeholder_image(self.preview_w, self.preview_h)
        self.preview_label = tk.Label(
            preview_frame,
            image=self.placeholder_img,
            bg="#1a1a1e",
            relief="solid",
            borderwidth=1,
        )
        self.preview_label.pack()

        # 4. Action Buttons & Status
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(pady=4)

        self.toggle_btn = ttk.Button(
            btn_frame, text="▶ Start Stream", command=self.toggle, width=24
        )
        self.toggle_btn.pack()

        status_lbl = ttk.Label(
            self.root,
            textvariable=self.status_var,
            foreground="#1e40af",
            font=("Segoe UI", 9, "bold"),
            wraplength=440,
            justify="center",
        )
        status_lbl.pack(pady=(2, 6))

        if not VCAM_AVAILABLE:
            ttk.Label(
                self.root,
                text="⚠️ pyvirtualcam not installed. Running in preview-only mode.",
                foreground="#b91c1c",
                wraplength=420,
                justify="center",
            ).pack(pady=(0, 4))

        self._on_source_changed()

    def _on_source_changed(self):
        if self.source_type_var.get() == "webcam":
            self.file_controls.pack_forget()
            self.webcam_controls.pack(fill="x", pady=2)
        else:
            self.webcam_controls.pack_forget()
            self.file_controls.pack(fill="x", pady=2)

    def _browse_file(self):
        filetypes = [
            (
                "All Supported Media",
                "*.mp4;*.mkv;*.avi;*.mov;*.wmv;*.webm;*.flv;*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.gif",
            ),
            ("Videos (*.mp4, *.mkv, *.avi, *.mov)", "*.mp4;*.mkv;*.avi;*.mov;*.wmv;*.webm;*.flv"),
            ("Images (*.png, *.jpg, *.webp)", "*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.tiff"),
            ("Animated GIFs (*.gif)", "*.gif"),
            ("All Files", "*.*"),
        ]
        chosen = filedialog.askopenfilename(title="Select Photo, Video, or GIF", filetypes=filetypes)
        if chosen:
            self.media_file_path.set(chosen)
            filename = os.path.basename(chosen)
            display_name = filename if len(filename) <= 30 else filename[:27] + "..."
            self.file_label.config(text=display_name, foreground="#111111", font=("Segoe UI", 9, "bold"))
            self.clear_file_btn.pack(side="right", padx=(4, 0))

    def _clear_file(self):
        self.media_file_path.set("")
        self.file_label.config(
            text="No file selected", foreground="#777777", font=("Segoe UI", 9, "italic")
        )
        self.clear_file_btn.pack_forget()

    def _on_clean_feed_toggled(self):
        if self.clean_feed_var.get():
            if self.clean_feed_window is None or not self.clean_feed_window.is_alive:
                raw_res = self.resolution_var.get().split()[0]
                try:
                    w, h = map(int, raw_res.split("x"))
                except Exception:
                    w, h = 1280, 720
                self.clean_feed_window = CleanFeedWindow(self.root, target_w=w, target_h=h, on_close=self._on_clean_feed_closed)
        else:
            if self.clean_feed_window is not None:
                self.clean_feed_window.close()
                self.clean_feed_window = None

    def _on_clean_feed_closed(self):
        self.clean_feed_var.set(False)
        self.clean_feed_window = None

    def _show_whatsapp_guide(self):
        WhatsAppGuideDialog(self.root)

    def _manual_activate_obs(self):
        threading.Thread(target=self._activate_obs_worker, daemon=True).start()

    def _activate_obs_worker(self):
        self.root.after(0, self.status_var.set, "⚡ Connecting OBS Studio & DroidCam...")
        ok, msg = automate_obs_droidcam()
        if ok:
            self.root.after(0, self.status_var.set, "🟢 OBS & DroidCam Active! Ready for WhatsApp.")
        else:
            self.root.after(0, self.status_var.set, f"⚠️ OBS Automation: {msg}")

    # ---------- Control ----------

    def toggle(self):
        self.stop() if self.running else self.start()

    def start(self):
        raw_res = self.resolution_var.get().split()[0]
        try:
            width, height = map(int, raw_res.split("x"))
            fps = int(self.fps_var.get())
        except ValueError:
            messagebox.showerror("Invalid Settings", "Please check resolution and FPS values.")
            return

        source_type = self.source_type_var.get()
        filepath = self.media_file_path.get().strip()

        if source_type == "file" and (not filepath or not os.path.isfile(filepath)):
            messagebox.showwarning(
                "No File Selected",
                "Please click 'Browse Media...' and choose a photo, video, or GIF file.",
            )
            return

        # Auto-open clean feed and connect OBS if enabled
        if self.auto_obs_var.get():
            if not self.clean_feed_var.get():
                self.clean_feed_var.set(True)
            if self.clean_feed_window is None or not self.clean_feed_window.is_alive:
                self.clean_feed_window = CleanFeedWindow(self.root, target_w=width, target_h=height, on_close=self._on_clean_feed_closed)
            threading.Thread(target=self._activate_obs_worker, daemon=True).start()
        elif self.clean_feed_var.get():
            if self.clean_feed_window is None or not self.clean_feed_window.is_alive:
                self.clean_feed_window = CleanFeedWindow(self.root, target_w=width, target_h=height, on_close=self._on_clean_feed_closed)

        self.stop_event.clear()
        self.running = True
        self.toggle_btn.config(text="⏹ Stop Stream")
        self.status_var.set("Initializing stream...")

        self.worker_thread = threading.Thread(
            target=self._stream_loop, args=(source_type, filepath, width, height, fps), daemon=True
        )
        self.worker_thread.start()

    def stop(self):
        self.stop_event.set()
        self.running = False
        self.toggle_btn.config(text="▶ Start Stream")
        self.status_var.set("Stopped")
        self.preview_label.configure(image=self.placeholder_img)
        if self.clean_feed_window is not None and self.clean_feed_window.is_alive:
            self.clean_feed_window.label.configure(
                image="", text="MirrorCam Clean Feed\n\n(Click 'Start Stream' to broadcast)"
            )

    # ---------- Worker Loop ----------

    def _stream_loop(self, source_type, filepath, target_w, target_h, target_fps):
        vcam = None
        extra = " + Clean Feed" if self.clean_feed_var.get() else ""
        if VCAM_AVAILABLE:
            try:
                vcam = pyvirtualcam.Camera(
                    width=target_w, height=target_h, fps=target_fps, fmt=PixelFormat.BGR, backend="obs"
                )
                self.root.after(0, self.status_var.set, f"🟢 Streaming to: {vcam.device}{extra} ({target_w}x{target_h})")
            except Exception as e:
                if self.clean_feed_var.get():
                    self.root.after(0, self.status_var.set, f"🟢 Streaming to Clean Feed (OBS/WhatsApp)\n(pyvirtualcam: {e})")
                else:
                    self.root.after(0, self.status_var.set, f"⚠️ Virtual camera error: {e}")
        else:
            if self.clean_feed_var.get():
                self.root.after(0, self.status_var.set, "🟢 Streaming to Clean Feed (OBS/WhatsApp)")
            else:
                self.root.after(0, self.status_var.set, "Running (preview only, no virtual camera)")

        if source_type == "webcam":
            self._run_webcam_stream(vcam, target_w, target_h, target_fps)
        else:
            self._run_media_stream(vcam, filepath, target_w, target_h, target_fps)

        if vcam is not None:
            vcam.close()

    def _run_webcam_stream(self, vcam, target_w, target_h, target_fps):
        cam_index = int(self.camera_var.get())
        cap = cv2.VideoCapture(cam_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            self.root.after(
                0,
                lambda: messagebox.showerror(
                    "Camera Error",
                    f"Could not open camera index {cam_index}.\nCheck if another app is using it.",
                ),
            )
            self.root.after(0, self.stop)
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, target_w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, target_h)
        cap.set(cv2.CAP_PROP_FPS, target_fps)

        while not self.stop_event.is_set():
            ret, frame = cap.read()
            if not ret or frame is None:
                time.sleep(0.04)
                continue

            self._process_and_send_frame(frame, vcam, target_w, target_h, target_fps)

        cap.release()

    def _run_media_stream(self, vcam, filepath, target_w, target_h, target_fps):
        ext = os.path.splitext(filepath)[1].lower()
        basename = os.path.basename(filepath)
        vcam_info = f" -> {vcam.device}" if vcam is not None else " (preview only)"

        # 1. Animated GIF
        if ext in GIF_EXTS:
            try:
                frames_data = load_gif_frames(filepath)
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("GIF Error", f"Failed to load GIF:\n{e}"))
                self.root.after(0, self.stop)
                return

            self.root.after(
                0, self.status_var.set, f"🟢 Streaming Looping GIF: {basename}{vcam_info} ({len(frames_data)} frames)"
            )
            frame_idx = 0
            while not self.stop_event.is_set():
                frame, duration = frames_data[frame_idx]
                frame_idx = (frame_idx + 1) % len(frames_data)

                self._process_and_send_frame(frame, vcam, target_w, target_h, target_fps, custom_delay=duration)

        # 2. Static Photo / Image
        elif ext in IMAGE_EXTS:
            try:
                static_frame = load_static_image(filepath)
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Image Error", f"Failed to load image:\n{e}"))
                self.root.after(0, self.stop)
                return

            self.root.after(0, self.status_var.set, f"🟢 Streaming Photo: {basename}{vcam_info}")
            while not self.stop_event.is_set():
                self._process_and_send_frame(static_frame, vcam, target_w, target_h, target_fps)

        # 3. Video File (Looping)
        else:
            cap = cv2.VideoCapture(filepath)
            if not cap.isOpened():
                self.root.after(
                    0, lambda: messagebox.showerror("Video Error", f"Failed to open video file:\n{basename}")
                )
                self.root.after(0, self.stop)
                return

            video_fps = cap.get(cv2.CAP_PROP_FPS)
            fps = video_fps if (video_fps and 1.0 <= video_fps <= 120.0) else target_fps

            self.root.after(0, self.status_var.set, f"🟢 Streaming Looping Video: {basename}{vcam_info}")

            while not self.stop_event.is_set():
                ret, frame = cap.read()
                if not ret or frame is None:
                    # Seamless Loop: rewind video to first frame
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, frame = cap.read()
                    if not ret or frame is None:
                        time.sleep(0.05)
                        continue

                self._process_and_send_frame(frame, vcam, target_w, target_h, fps)

            cap.release()

    def _process_and_send_frame(self, frame, vcam, target_w, target_h, target_fps, custom_delay=None):
        """Processes mirror toggle, fits resolution, sends to vcam, and renders preview."""
        # 1. Mirroring
        if self.mirror_var.get():
            frame = cv2.flip(frame, 1)

        # 2. Resolution Scaling
        if self.letterbox_var.get():
            out_frame = fit_frame_to_target(frame, target_w, target_h)
        else:
            fh, fw = frame.shape[:2]
            if fw != target_w or fh != target_h:
                interp = cv2.INTER_AREA if (target_w < fw or target_h < fh) else cv2.INTER_CUBIC
                out_frame = cv2.resize(frame, (target_w, target_h), interpolation=interp)
            else:
                out_frame = frame

        # 3. Stream to Virtual Camera
        if vcam is not None:
            try:
                vcam.send(out_frame)
                if custom_delay is not None:
                    time.sleep(custom_delay)
                else:
                    vcam.sleep_until_next_frame()
            except Exception:
                pass
        else:
            delay = custom_delay if custom_delay is not None else (1.0 / max(target_fps, 1))
            time.sleep(delay)

        # 4. Preview Render & Clean Feed update
        preview_rgb = cv2.cvtColor(out_frame, cv2.COLOR_BGR2RGB)
        preview_small = cv2.resize(preview_rgb, (self.preview_w, self.preview_h), interpolation=cv2.INTER_AREA)
        img = Image.fromarray(preview_small)
        imgtk = ImageTk.PhotoImage(image=img)
        self.root.after(0, self._update_ui_frames, imgtk, out_frame)

    def _update_ui_frames(self, imgtk, out_frame):
        self.preview_label.imgtk = imgtk
        self.preview_label.configure(image=imgtk)
        if self.clean_feed_window is not None and self.clean_feed_window.is_alive:
            self.clean_feed_window.update_frame(out_frame)

    def on_close(self):
        self.stop_event.set()
        if self.clean_feed_window is not None:
            self.clean_feed_window.close()
            self.clean_feed_window = None
        time.sleep(0.15)
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = MirrorCamApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
