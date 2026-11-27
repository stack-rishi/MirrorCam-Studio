"""
MirrorCam CLI - flips your outgoing webcam feed or streams photos, looping
videos, and animated GIFs to the OBS Virtual Camera, so WhatsApp/Discord/Meet
receive the mirrored (or normal) version.

Supports automatic screen resolution and aspect ratio detection with `--match-screen`.

Usage:
    python camera.py
    python camera.py --match-screen                # Stream in native screen resolution & aspect ratio
    python camera.py --camera 0 --width 1920 --height 1080 --fps 30
    python camera.py --file path/to/video.mp4      # Looping video
    python camera.py --file path/to/image.png      # Photo
    python camera.py --file path/to/animation.gif  # Looping GIF
    python camera.py --no-mirror                   # Passthrough (no horizontal flip)

Requirements:
    - OBS Studio installed (provides the "OBS Virtual Camera" driver)
    - pip install opencv-python pyvirtualcam pillow
"""

import argparse
import math
import os
import sys
import time

import cv2
import numpy as np
from PIL import Image, ImageSequence
import pyvirtualcam
from pyvirtualcam import PixelFormat

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".flv", ".m4v"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}
GIF_EXTS = {".gif"}


def get_screen_info():
    """Detects primary monitor width, height, and simplified aspect ratio string."""
    sw, sh = 1920, 1080
    if sys.platform == "win32":
        try:
            import ctypes
            try:
                ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
            except Exception:
                try:
                    ctypes.windll.shcore.SetProcessDpiAwareness(2)
                except Exception:
                    ctypes.windll.user32.SetProcessDPIAware()

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
    pil_img = Image.open(filepath)
    frames = []
    for frame in ImageSequence.Iterator(pil_img):
        duration = frame.info.get("duration", 100) / 1000.0
        if duration <= 0.01:
            duration = 0.08
        frame_rgb = frame.convert("RGB")
        frame_np = np.array(frame_rgb)
        frame_bgr = cv2.cvtColor(frame_np, cv2.COLOR_RGB2BGR)
        frames.append((frame_bgr, duration))
    if not frames:
        raise ValueError("No frames found in GIF")
    return frames


def load_static_image(filepath: str) -> np.ndarray:
    pil_img = Image.open(filepath).convert("RGB")
    frame_np = np.array(pil_img)
    return cv2.cvtColor(frame_np, cv2.COLOR_RGB2BGR)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MirrorCam - Stream webcam or media files to OBS Virtual Camera")
    parser.add_argument("--file", "-f", type=str, default="", help="Path to photo, video, or GIF to stream")
    parser.add_argument("--camera", type=int, default=0, help="Physical camera index (default: 0)")
    parser.add_argument("--match-screen", action="store_true", help="Match capture resolution and aspect ratio to primary screen")
    parser.add_argument("--width", type=int, default=1920, help="Capture width (default: 1920)")
    parser.add_argument("--height", type=int, default=1080, help="Capture height (default: 1080)")
    parser.add_argument("--fps", type=int, default=30, help="Target FPS (default: 30)")
    parser.add_argument(
        "--no-mirror",
        action="store_true",
        help="Disable the horizontal flip (useful to sanity-check the pipeline)",
    )
    parser.add_argument(
        "--no-letterbox",
        action="store_true",
        help="Stretch image to fit target resolution instead of preserving aspect ratio",
    )
    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="Skip the local preview window (headless/background use)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    mirror = not args.no_mirror
    letterbox = not args.no_letterbox

    sw, sh, s_ratio = get_screen_info()
    if args.match_screen:
        width, height = sw, sh
        print(f"Detected screen: {sw}x{sh} ({s_ratio}) - using screen native quality.")
    else:
        width, height = args.width, args.height

    # Source setup
    cap = None
    gif_frames = None
    static_img = None
    fps = args.fps

    if args.file:
        if not os.path.isfile(args.file):
            print(f"Error: File not found: {args.file}", file=sys.stderr)
            return 1

        ext = os.path.splitext(args.file)[1].lower()
        if ext in GIF_EXTS:
            try:
                gif_frames = load_gif_frames(args.file)
                print(f"Loaded animated GIF: {os.path.basename(args.file)} ({len(gif_frames)} frames)")
            except Exception as e:
                print(f"Failed to load GIF: {e}", file=sys.stderr)
                return 1
        elif ext in IMAGE_EXTS:
            try:
                static_img = load_static_image(args.file)
                print(f"Loaded static photo: {os.path.basename(args.file)}")
            except Exception as e:
                print(f"Failed to load image: {e}", file=sys.stderr)
                return 1
        else:
            cap = cv2.VideoCapture(args.file)
            if not cap.isOpened():
                print(f"Failed to open video file: {args.file}", file=sys.stderr)
                return 1
            vid_fps = cap.get(cv2.CAP_PROP_FPS)
            if vid_fps and 1.0 <= vid_fps <= 120.0:
                fps = int(round(vid_fps))
            print(f"Loaded looping video: {os.path.basename(args.file)} ({fps} FPS)")
    else:
        cap = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)
        if not cap.isOpened():
            print(f"Could not open camera index {args.camera}.", file=sys.stderr)
            return 1
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_FPS, args.fps)

    try:
        with pyvirtualcam.Camera(
            width=width,
            height=height,
            fps=fps,
            fmt=PixelFormat.BGR,
            backend="obs",
        ) as cam:
            print(f"Virtual camera: {cam.device} ({width}x{height} @ {fps}fps)")
            print(f"Mirror: {'ON' if mirror else 'OFF'}")
            print("In WhatsApp/Discord/Meet/Zoom, select 'OBS Virtual Camera'.")
            print("Press Q (with the preview window focused) or Ctrl+C to quit.")

            gif_idx = 0

            while True:
                custom_delay = None

                if gif_frames is not None:
                    raw_frame, custom_delay = gif_frames[gif_idx]
                    gif_idx = (gif_idx + 1) % len(gif_frames)
                elif static_img is not None:
                    raw_frame = static_img
                else:
                    ret, raw_frame = cap.read()
                    if not ret or raw_frame is None:
                        if args.file:
                            # Loop video
                            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                            ret, raw_frame = cap.read()
                            if not ret or raw_frame is None:
                                time.sleep(0.04)
                                continue
                        else:
                            print("Failed to read a frame from the camera.", file=sys.stderr)
                            break

                if mirror:
                    raw_frame = cv2.flip(raw_frame, 1)

                if letterbox:
                    out_frame = fit_frame_to_target(raw_frame, width, height)
                else:
                    fh, fw = raw_frame.shape[:2]
                    if fw != width or fh != height:
                        interp = cv2.INTER_AREA if (width < fw or height < fh) else cv2.INTER_CUBIC
                        out_frame = cv2.resize(raw_frame, (width, height), interpolation=interp)
                    else:
                        out_frame = raw_frame

                cam.send(out_frame)
                if custom_delay is not None:
                    time.sleep(custom_delay)
                else:
                    cam.sleep_until_next_frame()

                if not args.no_preview:
                    preview_w, preview_h = 480, int(480 * height / width)
                    preview_resized = cv2.resize(out_frame, (preview_w, preview_h), interpolation=cv2.INTER_AREA)
                    try:
                        cv2.imshow("MirrorCam Preview (press Q to quit)", preview_resized)
                        if cv2.waitKey(1) & 0xFF == ord("q"):
                            break
                    except cv2.error:
                        pass
    except KeyboardInterrupt:
        pass
    finally:
        if cap is not None:
            cap.release()
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
