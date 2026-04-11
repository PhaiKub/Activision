/*
 * ESP32 BLE HID Bridge — Combo (Mouse+Keyboard in ONE device)
 * ──────────────────────────────────────────────────────
 * BLE HID Combo   = mouse + keyboard ให้ Windows (single HID device)
 * BT Classic SPP  = รับคำสั่งจาก Python
 * 
 * Library: ESP32-BLE-Combo by blackketter
 * Board:   ESP32 Dev Module, Partition: Huge APP (3MB)
 */

#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"
#include <BleCombo.h>
#include "BluetoothSerial.h"

#define LED_PIN         2
#define BLINK_INTERVAL  1000

// Mouse + Keyboard globals จาก BleCombo.h
// extern BleComboMouse Mouse;
// extern BleComboKeyboard Keyboard;

BluetoothSerial btSerial;

unsigned long lastBlink = 0;
bool ledState = false;
bool wasConnected = false;

void updateStatus() {
    bool connected = Keyboard.isConnected();

    if (connected != wasConnected) {
        wasConnected = connected;
        String msg = connected ? "[OK] BLE connected" 
                               : "[--] BLE disconnected";
        Serial.println(msg);
    }

    if (connected) {
        digitalWrite(LED_PIN, HIGH);
    } else {
        unsigned long now = millis();
        if (now - lastBlink >= BLINK_INTERVAL) {
            lastBlink = now;
            ledState = !ledState;
            digitalWrite(LED_PIN, ledState);
        }
    }
}

uint8_t getBtn(int b) {
    if (b == 2) return MOUSE_RIGHT;
    if (b == 3) return MOUSE_MIDDLE;
    return MOUSE_LEFT;
}

void processCommand(String cmd) {
    cmd.trim();
    if (cmd.length() == 0) return;
    char type = cmd.charAt(0);

    if (!Keyboard.isConnected() && type != 'P' && type != 'Q') {
        btSerial.println("NOCONN");
        Serial.println("NOCONN");
        return;
    }

    switch (type) {
        case 'M': {
            int sp1 = cmd.indexOf(' ', 0);
            int sp2 = cmd.indexOf(' ', sp1 + 1);
            if (sp1 < 0 || sp2 < 0) break;
            Mouse.move(
                cmd.substring(sp1 + 1, sp2).toInt(),
                cmd.substring(sp2 + 1).toInt(), 0);
            break;
        }
        case 'C': Mouse.click(getBtn(cmd.substring(2).toInt())); break;
        case 'D': Mouse.press(getBtn(cmd.substring(2).toInt())); break;
        case 'U': Mouse.release(getBtn(cmd.substring(2).toInt())); break;
        case 'S': Mouse.move(0, 0, cmd.substring(2).toInt()); break;
        case 'K': {
            int code = cmd.substring(2).toInt();
            Keyboard.press((uint8_t)code);
            break;
        }
        case 'R': {
            int code = cmd.substring(2).toInt();
            Keyboard.release((uint8_t)code);
            break;
        }
        case 'A': {
            Keyboard.releaseAll();
            break;
        }
        case 'P':
            btSerial.println("PONG");
            Serial.println("PONG");
            return;
        case 'Q':
            btSerial.print("COMBO:");
            btSerial.println(Keyboard.isConnected() ? "1" : "0");
            return;
        default:
            btSerial.println("ERR");
            return;
    }
    btSerial.println("OK");
    Serial.println("OK");
}

void setup() {
    WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);

    pinMode(LED_PIN, OUTPUT);
    digitalWrite(LED_PIN, LOW);

    Serial.begin(115200);
    Serial.println("[ESP32] Starting...");

    // Bluetooth Classic SPP
    btSerial.begin("Activision");
    Serial.println("[ESP32] BT SPP started");

    // BLE HID Combo (Mouse + Keyboard = 1 device)
    Keyboard.deviceName = "Activision";
    Keyboard.deviceManufacturer = "Activision";
    Keyboard.begin();
    Mouse.begin();
    Serial.println("[ESP32] BLE Combo started");

    Serial.println("[ESP32] Ready!");
    Serial.println("[ESP32] Pair 'Activision' in Windows Bluetooth");
}

void loop() {
    updateStatus();

    if (btSerial.available()) {
        String cmd = btSerial.readStringUntil('\n');
        processCommand(cmd);
    }

    if (Serial.available()) {
        String cmd = Serial.readStringUntil('\n');
        processCommand(cmd);
    }
}
