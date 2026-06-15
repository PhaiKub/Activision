import platform
import source.utils.params as p


RAISE_ERROR = False
BRIDGE_ERROR_MESSAGE = ""

if platform.system() == "Windows":
    if p.INPUT_BACKEND == "ghub":
        # Ghub bridge: probe eagerly at startup
        from source.utils.os_windows_backend import _get_bridge

        try:
            _get_bridge()
        except Exception as e:
            BRIDGE_ERROR_MESSAGE = str(e)
            print(BRIDGE_ERROR_MESSAGE)
            RAISE_ERROR = True
    # ESP32 backend: connection is deferred to the UI scan dialog —
    # no need to probe here.