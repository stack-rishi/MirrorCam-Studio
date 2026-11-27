"""
Standalone script to launch OBS Studio and automatically activate DroidCam Virtual Output.
Can be run directly or triggered by MirrorCam.
"""

import ctypes
from ctypes import wintypes
import os
import subprocess
import sys
import time


def automate_obs_droidcam():
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
            print("Launching OBS Studio in background...")
            subprocess.Popen([obs_exe], cwd=obs_dir)
            time.sleep(3.5)
        except Exception as e:
            return False, f"Failed to launch OBS: {e}"
    else:
        print("OBS Studio is already running.")

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


if __name__ == "__main__":
    ok, msg = automate_obs_droidcam()
    print("Result:", ok, "-", msg)

