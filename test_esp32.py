"""Test ESP32 BLE keyboard & mouse"""
import time, os, sys
sys.path.insert(0, ".")
from source.utils.bridge.esp32_bridge import ESP32Bridge

b = ESP32Bridge(auto_open=True)
print(f"Connected: {b.is_open()} (mode: {b._mode})")

print("Pressing 'd' in 3s ... switch to game/notepad!")
time.sleep(3)

print("key_press('d')...")
b.key_press("d")
time.sleep(0.1)
print("key_release_all()...")
b.key_release_all()
time.sleep(0.5)

print("key_press('space')...")
b.key_press("space")
time.sleep(0.1)
b.key_release_all()
time.sleep(0.5)

print("Done! Did keys register?")
b.close()
