import platform


RAISE_ERROR = False
_initialized = False


def init_bridge():
    """Initialize the bridge connection.

    Must be called AFTER params.BRIDGE_MODE is set so that
    _get_bridge() picks the correct backend (ESP32 or ESP32-S3).
    """
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


def retry_bridge(host=None, port=None):
    """Reset and retry bridge connection.

    For ESP32 mode: pass host=<ip>
    For ESP32-S3 mode: pass port=<COMx>
    """
    global RAISE_ERROR

    if platform.system() != "Windows":
        return False

    from source.utils.os_windows_backend import _get_bridge, _bridge_lock
    import source.utils.os_windows_backend as _backend

    if host:
        import os
        os.environ["ESP32_HOST"] = host

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