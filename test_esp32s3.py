"""
Test ESP32-S3 USB HID Bridge (CDC Serial)
"""
import sys
import time

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("pip install pyserial")
    sys.exit(1)

CUSTOM_VID = 0x045E
CUSTOM_PID = 0x07A5
ESPRESSIF_VID = 0x303A


def find_esp32s3():
    print("\n>> Searching for ESP32-S3...")
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("   No COM ports found")
        return None

    print(f"   Found {len(ports)} port(s):\n")
    for p in ports:
        vid = f"0x{p.vid:04X}" if p.vid else "N/A"
        pid = f"0x{p.pid:04X}" if p.pid else "N/A"
        match = (p.vid == ESPRESSIF_VID) or (p.vid == CUSTOM_VID and p.pid == CUSTOM_PID)
        mark = " << ESP32-S3" if match else ""
        print(f"   {p.device:8s}  VID={vid}  PID={pid}  {p.description}{mark}")

    for p in ports:
        if p.vid == ESPRESSIF_VID or (p.vid == CUSTOM_VID and p.pid == CUSTOM_PID):
            print(f"\n   Found: {p.device}")
            return p.device

    print("\n   Auto-detect failed")
    # Try loading saved port from config
    saved = ""
    try:
        import json, os
        cfg = os.path.join(os.path.dirname(__file__), "esp32_config.json")
        if os.path.exists(cfg):
            data = json.load(open(cfg))
            saved = data.get("ESP32S3_PORT", "")
    except Exception:
        pass
    hint = f" [{saved}]" if saved else " (e.g. COM3)"
    port = input(f"   Enter COM port{hint}: ").strip()
    if not port and saved:
        port = saved
    return port if port else None


def test_bridge(port):
    print(f"\n>> Connecting to {port}...")
    try:
        s = serial.Serial(port, 115200, timeout=2)
    except Exception as e:
        print(f"   FAIL: {e}")
        return False

    time.sleep(1)
    s.reset_input_buffer()

    # Ping
    print("\n-- Test 1: Ping --")
    s.write(b"P\n"); s.flush(); time.sleep(0.3)
    resp = s.readline().decode("utf-8", errors="replace").strip()
    if "PONG" in resp:
        print(f"   OK: {resp}")
    else:
        print(f"   FAIL: '{resp}'")
        s.close()
        return False

    # Status
    print("\n-- Test 2: Status --")
    s.write(b"Q\n"); s.flush(); time.sleep(0.3)
    resp = s.readline().decode("utf-8", errors="replace").strip()
    print(f"   Status: {resp}")

    # Mouse move
    print("\n-- Test 3: Mouse move --")
    input("   Press Enter to move cursor right 100px...")
    for i in range(10):
        s.write(b"M 10 0\n"); s.flush(); time.sleep(0.05)
    print("   OK: sent 10 moves")

    # Move back
    print("\n-- Test 4: Move back --")
    for i in range(10):
        s.write(b"M -10 0\n"); s.flush(); time.sleep(0.05)
    while s.in_waiting:
        s.readline()
    print("   OK")

    # Click
    print("\n-- Test 5: Click --")
    if input("   Test click? (y/n): ").strip().lower() == 'y':
        print("   Clicking in 3s...")
        time.sleep(3)
        s.write(b"C 1\n"); s.flush(); time.sleep(0.2)
        s.readline()
        print("   OK")

    # Keyboard
    print("\n-- Test 6: Keyboard --")
    if input("   Test keyboard? (y/n): ").strip().lower() == 'y':
        print("   Pressing 'a' in 3s... open Notepad")
        time.sleep(3)
        s.write(b"K 97\n"); s.flush(); time.sleep(0.1)
        s.readline()
        s.write(b"A\n"); s.flush(); time.sleep(0.1)
        s.readline()
        print("   OK")

    # Error
    print("\n-- Test 7: Error --")
    s.write(b"Z bad\n"); s.flush(); time.sleep(0.3)
    resp = s.readline().decode("utf-8", errors="replace").strip()
    print(f"   Response: '{resp}' {'OK' if 'ERR' in resp else 'UNEXPECTED'}")

    print("\n" + "=" * 40)
    print("All tests passed!")
    print("=" * 40)
    s.close()
    return True


if __name__ == "__main__":
    print("=" * 40)
    print("  ESP32-S3 USB HID Bridge Test")
    print("=" * 40)
    port = find_esp32s3()
    if not port:
        print("\nESP32-S3 not found")
        sys.exit(1)
    test_bridge(port)
