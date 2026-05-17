import platform


RAISE_ERROR = False
_initialized = False


def init_bridge():
    """Initialize the ESP32-S3 USB HID bridge connection."""
    global RAISE_ERROR, _initialized
    if _initialized:
        return
    _initialized = True

    if platform.system() != "Windows":
        return

    from source.utils.os_windows_backend import _get_bridge

    try:
        _get_bridge()
    except Exception as e:
        print(e)
        RAISE_ERROR = True


def retry_bridge(port=None):
    """Reset and retry the ESP32-S3 USB bridge connection.

    Pass port=<COMx> to override the COM port detection.
    """
    global RAISE_ERROR

    if platform.system() != "Windows":
        return False

    from source.utils.os_windows_backend import _get_bridge, _bridge_lock
    import source.utils.os_windows_backend as _backend

    if port:
        import os
        os.environ["ESP32S3_PORT"] = port

    with _bridge_lock:
        _backend._bridge = None
        _backend._bridge_init_error = None

    try:
        _get_bridge()
        RAISE_ERROR = False
        return True
    except Exception as e:
        print(e)
        RAISE_ERROR = True
        return False
