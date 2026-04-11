/*
 * ESP32 BLE HID Bridge — WiFi TCP + BLE Combo
 * ──────────────────────────────────────────────
 * WiFi TCP Server = receives commands from Python (replaces Bluetooth SPP)
 * BLE HID Combo   = mouse + keyboard output to Windows
 * 
 * Library: ESP32-BLE-Combo by blackketter
 * Board:   ESP32 Dev Module, Partition: Huge APP (3MB)
 *
 * WiFi TCP latency: ~10-15ms (vs BT SPP ~20ms)
 */

#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"
#include <BleCombo.h>
#include <WiFi.h>

#define LED_PIN         2
#define BLINK_INTERVAL  1000
#define TCP_PORT        8266

// ──── WiFi Settings ────
// Change to your WiFi credentials
const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";

WiFiServer tcpServer(TCP_PORT);
WiFiClient tcpClient;

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

void sendResponse(const char* msg) {
    if (tcpClient && tcpClient.connected()) {
        tcpClient.println(msg);
    }
    Serial.println(msg);
}

void processCommand(String cmd) {
    cmd.trim();
    if (cmd.length() == 0) return;
    char type = cmd.charAt(0);

    if (!Keyboard.isConnected() && type != 'P' && type != 'Q') {
        sendResponse("NOCONN");
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
            sendResponse("PONG");
            return;
        case 'Q':
            if (tcpClient && tcpClient.connected()) {
                tcpClient.print("COMBO:");
                tcpClient.println(Keyboard.isConnected() ? "1" : "0");
            }
            return;
        default:
            sendResponse("ERR");
            return;
    }
    sendResponse("OK");
}

void setup() {
    WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);

    pinMode(LED_PIN, OUTPUT);
    digitalWrite(LED_PIN, LOW);

    Serial.begin(115200);
    Serial.println("[ESP32] Starting...");

    // ──── WiFi Connect ────
    Serial.printf("[WiFi] Connecting to %s", WIFI_SSID);
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    
    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 30) {
        delay(500);
        Serial.print(".");
        attempts++;
    }
    
    if (WiFi.status() == WL_CONNECTED) {
        Serial.println(" OK!");
        Serial.print("[WiFi] IP: ");
        Serial.println(WiFi.localIP());
    } else {
        Serial.println(" FAILED!");
        Serial.println("[WiFi] Running without WiFi — use Serial only");
    }

    // ──── TCP Server ────
    tcpServer.begin();
    tcpServer.setNoDelay(true);
    Serial.printf("[TCP] Listening on port %d\n", TCP_PORT);

    // ──── BLE HID ────
    Keyboard.begin();
    Mouse.begin();
    Serial.println("[BLE] HID Combo started (Activision)");
    Serial.println("[ESP32] Ready!");
}

void loop() {
    updateStatus();

    // Accept new TCP client
    if (tcpServer.hasClient()) {
        if (tcpClient && tcpClient.connected()) {
            tcpClient.stop();  // disconnect old client
        }
        tcpClient = tcpServer.available();
        tcpClient.setNoDelay(true);
        Serial.println("[TCP] Client connected");
    }

    // Read TCP commands
    if (tcpClient && tcpClient.connected()) {
        while (tcpClient.available()) {
            String cmd = tcpClient.readStringUntil('\n');
            processCommand(cmd);
        }
    }

    // Also accept Serial commands (for debugging)
    if (Serial.available()) {
        String cmd = Serial.readStringUntil('\n');
        processCommand(cmd);
    }

    delay(1);
}
