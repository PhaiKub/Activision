import platform


RAISE_ERROR = False

if platform.system() == "Windows":
    from source.utils.os_windows_backend import _get_bridge, _bridge_lock
    import source.utils.os_windows_backend as _backend

    try:
        _get_bridge()
    except Exception as e:
        print(e)
        RAISE_ERROR = True

    def retry_bridge(host=None):
        """Reset and retry bridge connection (optionally with a new host)."""
        global RAISE_ERROR
        if host:
            import os
            os.environ["ESP32_HOST"] = host
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