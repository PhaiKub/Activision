import platform


RAISE_ERROR = False

if platform.system() == "Windows":
    from source.utils.os_windows_backend import _get_bridge

    try:
        _get_bridge()
    except Exception as e:
        print(e)
        RAISE_ERROR = True