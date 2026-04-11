"""ESP32 Continuous Ping (WiFi TCP & Bluetooth SPP)"""
import time, os, sys
sys.path.insert(0, ".")
from source.utils.bridge.esp32_bridge import ESP32Bridge

host = os.environ.get("ESP32_HOST", None)
b = ESP32Bridge(host=host, auto_open=True)
print(f"Ctrl+C to stop\n")

i = 0
while True:
    i += 1
    start = time.perf_counter()
    try:
        b._send_raw("P")
        resp = b._read_response(timeout=2.0)
        ms = (time.perf_counter() - start) * 1000
        if resp == "PONG":
            bar = "█" * min(int(ms), 50)
            print(f"  [{i:4d}] {ms:6.1f} ms {bar}")
        else:
            print(f"  [{i:4d}]   FAIL (got: {resp})")
    except Exception as e:
        print(f"  [{i:4d}]   FAIL ❌ {e}")
    time.sleep(0.5)
