"""Debug ESP32-S3 HID Vendor communication"""
import sys
import time

try:
    import hid
except ImportError:
    print("pip install hidapi")
    sys.exit(1)

VID = 0x045E
PID = 0x07A5
VENDOR_USAGE = 0xFF00
RSIZE = 64

print("=== HID Debug ===\n")

# 1. List all interfaces
print("1. All interfaces for VID=0x045E PID=0x07A5:")
for d in hid.enumerate(VID, PID):
    print(f"   Path: ...{str(d['path'])[-40:]}")
    print(f"   Usage Page: 0x{d['usage_page']:04X}  Usage: 0x{d['usage']:04X}")
    print(f"   Interface: {d['interface_number']}")
    print()

# 2. Find vendor interface
path = None
for d in hid.enumerate(VID, PID):
    if d['usage_page'] == VENDOR_USAGE:
        path = d['path']
        break

if not path:
    print("X Vendor HID not found")
    sys.exit(1)

print(f"2. Opening vendor HID\n")
dev = hid.device()
dev.open_path(path)

# 3. Try write (output report)
print("3. Writing via OUTPUT report (dev.write)...")
data = b"P\n" + bytes(RSIZE - 2)
report = bytes([0x00]) + data
result = dev.write(report)
print(f"   write() returned: {result}")
if result > 0:
    print("   -> OUTPUT report works!")
    time.sleep(0.5)
    resp = dev.read(RSIZE, 2000)
    if resp:
        text = bytes(resp).decode("utf-8", errors="replace").strip("\x00").strip()
        print(f"   Response: '{text}'")
    else:
        print("   No response")
else:
    print("   -> OUTPUT report FAILED (no output endpoint)")

# 4. Try feature report
print("\n4. Writing via FEATURE report (send_feature_report)...")
try:
    feature = bytes([0x00]) + b"P\n" + bytes(RSIZE - 2)
    result = dev.send_feature_report(feature)
    print(f"   send_feature_report() returned: {result}")
    if result > 0:
        time.sleep(0.5)
        resp = dev.read(RSIZE, 2000)
        if resp:
            text = bytes(resp).decode("utf-8", errors="replace").strip("\x00").strip()
            print(f"   Response: '{text}'")
        else:
            print("   No response via read()")
except Exception as e:
    print(f"   ERROR: {e}")

# 5. Check if maybe the output report size is different
print("\n5. Trying different report sizes for write...")
for size in [8, 16, 32, 64]:
    try:
        data = b"P\n" + bytes(size - 2)
        report = bytes([0x00]) + data
        result = dev.write(report)
        print(f"   size={size+1}: write() returned {result}")
        if result > 0:
            time.sleep(0.3)
            resp = dev.read(RSIZE, 1000)
            if resp:
                text = bytes(resp).decode("utf-8", errors="replace").strip("\x00").strip()
                print(f"   Response: '{text}'")
            break
    except Exception as e:
        print(f"   size={size+1}: ERROR {e}")

dev.close()
print("\n=== Done ===")
