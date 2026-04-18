import ctypes
from ctypes import wintypes
import numpy as np
import time
import math
import random
import os
import threading
import source.utils.params as p
from source.utils.profiles import get_macro_profile, maybe_rhythm_jitter, randomize_with_profile



_bridge = None
_bridge_lock = threading.RLock()
_bridge_init_error = None


def _get_bridge():
    global _bridge, _bridge_init_error
    with _bridge_lock:
        if _bridge is None:
            try:
                if p.BRIDGE_MODE == "esp32s3":
                    from source.utils.bridge.esp32s3_bridge import ESP32S3Bridge
                    _bridge = ESP32S3Bridge(auto_open=True)
                else:
                    from source.utils.bridge.esp32_bridge import ESP32Bridge
                    _bridge = ESP32Bridge(auto_open=True)
                _bridge_init_error = None
            except Exception as exc:
                _bridge_init_error = RuntimeError(f"Bridge initialization failed: {exc}")
                raise _bridge_init_error
        return _bridge


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD)
    ]

class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", wintypes.DWORD * 3)
    ]

def screenshot(imageFilename=None, region=None, allScreens=False):
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    
    if allScreens:
        width = user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
        height = user32.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN
        x, y = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)  # SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN
    else:
        width = user32.GetSystemMetrics(0)  # SM_CXSCREEN
        height = user32.GetSystemMetrics(1)  # SM_CYSCREEN
        x = y = 0
    
    if region:
        x, y, rwidth, rheight = region
        width, height = rwidth, rheight
    else:
        region = (x, y, width, height)
    
    hdc = user32.GetDC(None)
    mfc_dc = gdi32.CreateCompatibleDC(hdc)
    bitmap = gdi32.CreateCompatibleBitmap(hdc, width, height)
    gdi32.SelectObject(mfc_dc, bitmap)
    
    gdi32.BitBlt(mfc_dc, 0, 0, width, height, hdc, x, y, 0x00CC0020)  # SRCCOPY
    
    try:
        bmpinfo = BITMAPINFO()
        bmpinfo.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmpinfo.bmiHeader.biWidth = width
        bmpinfo.bmiHeader.biHeight = -height
        bmpinfo.bmiHeader.biPlanes = 1
        bmpinfo.bmiHeader.biBitCount = 32
        bmpinfo.bmiHeader.biCompression = 0
        
        buffer_len = width * height * 4
        buffer = ctypes.create_string_buffer(buffer_len)
        gdi32.GetDIBits(mfc_dc, bitmap, 0, height, buffer, ctypes.byref(bmpinfo), 0)
        
        arr = np.frombuffer(buffer, dtype=np.uint8).reshape((height, width, 4))
        arr = arr[:, :, :3]  # Remove alpha channel
        
        if imageFilename:
            import cv2  # Will raise error if not available
            cv2.imwrite(imageFilename, arr)
        return arr

    finally:
        # Cleanup
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mfc_dc)
        user32.ReleaseDC(None, hdc)


user32 = ctypes.windll.user32

# Tweening functions
def linear(t):
    return t

def easeInOutQuad(t):
    return 2*t*t if t < 0.5 else -1 + (4 - 2*t)*t

def easeOutElastic(t):
    c4 = (2 * math.pi) / 3
    if t == 0:
        return 0
    elif t == 1:
        return 1
    return 2**(-10 * t) * math.sin((t * 10 - 0.75) * c4) + 1

# Helper functions
def get_screen_size():
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)

def get_position():
    point = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y

def getActiveWindowTitle():
    hwnd = user32.GetForegroundWindow()
    length = user32.GetWindowTextLengthW(hwnd)
    buff = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buff, length + 1)
    return buff.value

def center(target=None):
    """
    Returns the center coordinates of:
    - A window (if target is a string title)
    - A screen region (if target is a box tuple (left, top, width, height))
    - The primary screen (if no target)
    """
    if isinstance(target, str):  # Window title
        hwnd = user32.FindWindowW(None, target)
        if not hwnd:
            raise ValueError(f"Window not found: {target}")
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        return (
            (rect.left + rect.right) // 2,
            (rect.top + rect.bottom) // 2
        )
    elif isinstance(target, (tuple, list)) and len(target) >= 4:  # Region box
        left, top, width, height = target[:4]
        return (left + width // 2, top + height // 2)
    else:  # Primary screen center
        width, height = get_screen_size()
        return (width // 2, height // 2)

def _human_delay(min_delay=0.01, max_delay=0.03):
    time.sleep(random.uniform(min_delay, max_delay))

def mouseDown(button='left', delay=0.16):
    _fail_safe_check()
    _get_bridge().mouse_press(button=button)
    time.sleep(0.05)
    _fail_safe_check()

def mouseUp(button='left', delay=0.16):
    _fail_safe_check()
    _get_bridge().mouse_release(button=button)
    time.sleep(0.05)
    _fail_safe_check()


class WindowError(Exception): pass
class FailSafeException(Exception): pass
class ImageNotFoundException(Exception): pass
class PauseException(Exception):
    def __init__(self, name):
        super().__init__(name)
        self.window = name

# Global fail-safe settings
FAILSAFE_ENABLED = True


def _apply_macro_rhythm(profile=None):
    return  # Skip — BLE relative move would shift cursor off target

def set_failsafe(state=True):
    """Enable or disable the fail-safe feature"""
    global FAILSAFE_ENABLED
    FAILSAFE_ENABLED = state


def _fail_safe_check():
    """Check if mouse is in fail-safe position and raise exception if needed"""
    if not FAILSAFE_ENABLED:
        return
    
    name = getActiveWindowTitle()
    
    if p.LIMBUS_NAME not in name:
        raise PauseException(name)


def _sync_hid_position(target_x, target_y):
    """Sync HID device with actual cursor position.

    After SetCursorPos, the game may not register the new position because
    it reads from raw HID input. This sends a tiny nudge to generate
    a real HID input event, which forces the game engine to read the
    current absolute cursor position.

    Works for both ESP32 (BLE HID) and ESP32-S3 (USB HID) since both
    are physical HID devices that the game reads raw input from.
    """
    # Send a tiny nudge (+1 then -1) to force a HID report.
    # We must wait for the TCP send to complete, so we use a small sleep.
    # The game intercepts the physical mouse move and syncs its UI cursor.
    _get_bridge().mouse_move_relative(1, 0)
    _get_bridge().mouse_move_relative(-1, 0)
    time.sleep(0.01)
    
    # Ensure the absolute cursor is exactly on target as the final step
    ctypes.windll.user32.SetCursorPos(int(target_x), int(target_y))


def moveTo(x, y, duration=0.0, tween=easeInOutQuad, delay=0.09, humanize=True,
           mouse_velocity=0.65, noise=2.6, offset_x=0, offset_y=0):
    _fail_safe_check()

    start_x, start_y = get_position()
    total_dx = x - start_x
    total_dy = y - start_y
    distance = math.hypot(total_dx, total_dy)

    if distance > 2:
        move_time = max(0.08, distance / 2000)
        steps = max(5, int(distance / 8))
        step_delay = move_time / steps
        for i in range(1, steps + 1):
            t = i / steps
            t = t * t * (3 - 2 * t)  # ease-in-out
            cur_x = int(round(start_x + total_dx * t))
            cur_y = int(round(start_y + total_dy * t))
            ctypes.windll.user32.SetCursorPos(cur_x, cur_y)
            time.sleep(step_delay)

    # Final position set
    ctypes.windll.user32.SetCursorPos(int(x), int(y))
    time.sleep(0.03)

    # Sync BLE HID with actual cursor position so game registers it
    _sync_hid_position(int(x), int(y))

    time.sleep(0.07)  # settle — game needs time to register cursor
    _fail_safe_check()



def click(x=None, y=None, button='left', clicks=1, interval=0.1, duration=0.0, tween=easeInOutQuad, delay=0.03):
    _fail_safe_check()
    profile = get_macro_profile()
    _apply_macro_rhythm(profile)
    delay = randomize_with_profile(delay, profile=profile, key="delay_jitter")
    interval += 0.05
    
    if x is not None and y is not None:
        moveTo(x, y, duration, tween, delay=delay+0.02)
        
    elif duration > 0:
        current_x, current_y = get_position()
        moveTo(current_x, current_y, duration, tween, delay=delay+0.02)
    else:
        time.sleep(0.02)

    for i in range(clicks):
        _fail_safe_check()
        
        mouseDown(button, delay=delay)
        mouseUp(button, delay=delay)
        
        if interval > 0 and i < clicks - 1:
            time.sleep(randomize_with_profile(interval, profile=profile, key="click_interval_jitter"))
            _fail_safe_check()


def dragTo(x, y, duration=0.1, tween=easeInOutQuad, button='left', start_x=None, start_y=None, humanize=False):
    _fail_safe_check()
    _apply_macro_rhythm()
    
    if start_x is not None and start_y is not None:
        moveTo(start_x, start_y)

    mouseDown(button, delay=0.03)
    moveTo(x, y, duration, tween, humanize=humanize)
    mouseUp(button, delay=0.03)
    _fail_safe_check()

def scroll(clicks, x=None, y=None):
    _fail_safe_check()
    _apply_macro_rhythm()
    if x is not None and y is not None:
        moveTo(x, y)

    direction = 1 if clicks > 0 else -1
    count = abs(int(clicks))
    for _ in range(count):
        _fail_safe_check()
        _get_bridge().mouse_scroll(direction)
        time.sleep(0.02)
    _human_delay()


def press(keys, presses=1, interval=0.1, delay=0.09):
    profile = get_macro_profile()
    _apply_macro_rhythm(profile)
    time.sleep(randomize_with_profile(delay, profile=profile, key="delay_jitter"))

    if isinstance(keys, str):
        keys = [keys]

    for _p in range(presses):
        _fail_safe_check()
        if len(keys) > 1:
            _get_bridge().key_multi_press(keys)
            time.sleep(randomize_with_profile(delay, profile=profile, key="delay_jitter"))
            _get_bridge().key_release_all()
        elif len(keys) == 1:
            _get_bridge().key_press(keys[0])
            time.sleep(randomize_with_profile(delay, profile=profile, key="delay_jitter"))
            _get_bridge().key_release_all()

        if interval > 0 and _p < presses - 1:
            time.sleep(randomize_with_profile(interval, profile=profile, key="key_interval_jitter"))
            _fail_safe_check()

def hotkey(*args, **kwargs):
    press(list(args), **kwargs)


def check_window():
    user32 = ctypes.windll.user32

    vx = user32.GetSystemMetrics(76)
    vy = user32.GetSystemMetrics(77)
    vw = user32.GetSystemMetrics(78)
    vh = user32.GetSystemMetrics(79)

    vright = vx + vw
    vbottom = vy + vh

    left, top, width, height = p.WINDOW
    right = left + width
    bottom = top + height

    in_bounds = (
        left >= vx and
        top >= vy and
        right <= vright and
        bottom <= vbottom
    )
    if not in_bounds:
        raise WindowError("Window is partially or completely out of screen bounds!")

def set_window():
    hwnd = ctypes.windll.user32.FindWindowW(None, p.LIMBUS_NAME)

    rect = ctypes.wintypes.RECT()
    ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(rect))

    pt = ctypes.wintypes.POINT(0, 0)
    ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(pt))

    client_width = rect.right - rect.left
    client_height = rect.bottom - rect.top
    left, top = pt.x, pt.y

    target_ratio = 16 / 9
    if client_width / client_height > target_ratio:
        target_height = client_height
        target_width = int(target_height * target_ratio)
    elif client_width / client_height < target_ratio:
        target_width = client_width
        target_height = int(target_width / target_ratio)
    else:
        target_width = client_width
        target_height = client_height

    left += (client_width - target_width) // 2
    top += (client_height - target_height) // 2

    p.WINDOW = (left, top, target_width, target_height)
    check_window()

    if int(client_width / 16) != int(client_height / 9):
        p.WARNING(f"Game window ({client_width} x {client_height}) is not 16:9\nIt is recommended to set the game to either\n1920 x 1080 or 1280 x 720")

    print("WINDOW:", p.WINDOW)