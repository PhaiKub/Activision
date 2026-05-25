import platform
import source.utils.params as p


RAISE_ERROR = False

if platform.system() == "Windows":
    if p.INPUT_BACKEND == "ghub":
        # Ghub bridge: probe eagerly at startup
        from source.utils.os_windows_backend import _get_bridge

        try:
            _get_bridge()
        except Exception as e:
            print(e)
            RAISE_ERROR = True
    # ESP32 backend: connection is deferred to the UI scan dialog —
    # no need to probe here.