/*
 * ESP32-S3 USB HID Bridge — USB Only (No WiFi / No BLE)
 * ──────────────────────────────────────────────────────
 * USB CDC Serial = receives commands from Python (appears as COM port)
 * USB HID Combo  = mouse + keyboard output to PC
 *
 * Both run on the same USB cable — just plug in and go.
 *
 * RGB LED Status (WS2812 on GPIO 48):
 *   🟡 Yellow blink  — Booting / initializing USB
 *   🟣 Purple solid  — Ready, waiting for Python
 *   🔵 Blue solid    — Active (receiving commands)
 *   🟢 Green blink   — Idle (was connected, now quiet)
 *   🔴 Red flash     — Error
 *
 * Board settings in Arduino IDE:
 *   Board:           ESP32-S3 Dev Module
 *   USB Mode:        USB-OTG (TinyUSB)
 *   USB CDC On Boot: Enabled
 *
 * Protocol:
 *   M dx dy   — relative mouse move
 *   C btn     — click (1=left, 2=right, 3=middle)
 *   D btn     — mouse button down
 *   U btn     — mouse button up
 *   S wheel   — scroll
 *   K code    — key press
 *   R code    — key release
 *   A         — release all keys
 *   P         — ping (returns PONG)
 *   Q         — query USB HID status
 *
 * Only P and Q return text. All input commands are silent to keep the
 * USB CDC TX buffer from filling up under high-frequency traffic.
 */

#include "USB.h"
#include "USBHIDKeyboard.h"
#include "USBHIDMouse.h"

// ──── Config ────
#define RGB_PIN        48
#define RGB_BRIGHTNESS 10

USBHIDMouse Mouse;
USBHIDKeyboard Keyboard;

// Fixed-size input buffer — avoids Arduino String heap fragmentation
#define INPUT_BUF_SIZE 64
char inputBuffer[INPUT_BUF_SIZE];
uint8_t bufPos = 0;
bool usbReady = false;

// ──── LED state machine ────
enum LedState { LED_BOOTING, LED_READY, LED_ACTIVE, LED_IDLE, LED_ERROR };
LedState currentLedState = LED_BOOTING;
unsigned long lastLedUpdate = 0;
unsigned long lastCommandTime = 0;
unsigned long errorFlashStart = 0;
bool blinkOn = false;
bool everConnected = false;

void setRGB(uint8_t r, uint8_t g, uint8_t b) {
    neopixelWrite(RGB_PIN, r, g, b);
}

void updateLED() {
    unsigned long now = millis();
    switch (currentLedState) {
    case LED_BOOTING:
        if (now - lastLedUpdate >= 500) {
            lastLedUpdate = now;
            blinkOn = !blinkOn;
            setRGB(blinkOn ? RGB_BRIGHTNESS : 0, blinkOn ? RGB_BRIGHTNESS/2 : 0, 0);
        }
        break;
    case LED_READY:
        setRGB(RGB_BRIGHTNESS/2, 0, RGB_BRIGHTNESS);
        break;
    case LED_ACTIVE:
        setRGB(0, 0, RGB_BRIGHTNESS);
        if (now - lastCommandTime > 5000) currentLedState = LED_IDLE;
        break;
    case LED_IDLE:
        if (now - lastLedUpdate >= 1000) {
            lastLedUpdate = now;
            blinkOn = !blinkOn;
            setRGB(0, blinkOn ? RGB_BRIGHTNESS : RGB_BRIGHTNESS/6, 0);
        }
        if (now - lastCommandTime > 30000) {
            currentLedState = LED_READY;
            everConnected = false;
        }
        break;
    case LED_ERROR:
        if      (now - errorFlashStart < 150) setRGB(RGB_BRIGHTNESS, 0, 0);
        else if (now - errorFlashStart < 300) setRGB(0, 0, 0);
        else if (now - errorFlashStart < 450) setRGB(RGB_BRIGHTNESS, 0, 0);
        else currentLedState = (now - lastCommandTime < 5000) ? LED_ACTIVE
                             : everConnected ? LED_IDLE : LED_READY;
        break;
    }
}

void triggerActive() {
    lastCommandTime = millis();
    everConnected = true;
    if (currentLedState != LED_ERROR) currentLedState = LED_ACTIVE;
}
void triggerError() {
    errorFlashStart = millis();
    currentLedState = LED_ERROR;
}

// ──── Mouse button mapping ────
uint8_t getBtn(int b) {
    if (b == 2) return MOUSE_RIGHT;
    if (b == 3) return MOUSE_MIDDLE;
    return MOUSE_LEFT;
}

// ──── Helpers for fixed-size buffer parsing ────
static int parseIntAt(const char *buf, int start) {
    return atoi(buf + start);
}

// ──── Command processor ────
void processCommand(const char *cmd, uint8_t len) {
    if (len == 0) return;
    char type = cmd[0];

    triggerActive();

    switch (type) {
    case 'M': {
        // Parse "M dx dy" — find two spaces
        int sp1 = -1, sp2 = -1;
        for (int i = 1; i < len; i++) {
            if (cmd[i] == ' ') {
                if (sp1 < 0) sp1 = i;
                else { sp2 = i; break; }
            }
        }
        if (sp1 < 0 || sp2 < 0) break;
        Mouse.move(atoi(cmd + sp1 + 1), atoi(cmd + sp2 + 1), 0);
        return;  // No "OK" — mouse moves are too frequent, would overflow output buffer
    }
    case 'C': Mouse.click(getBtn(parseIntAt(cmd, 2))); return;
    case 'D': Mouse.press(getBtn(parseIntAt(cmd, 2))); return;
    case 'U': Mouse.release(getBtn(parseIntAt(cmd, 2))); return;
    case 'S': Mouse.move(0, 0, parseIntAt(cmd, 2)); return;
    // Keyboard commands also stay silent: even slow drains of "OK" responses
    // can saturate the CDC TX buffer when many keys are pressed in a row.
    case 'K': Keyboard.press((uint8_t)parseIntAt(cmd, 2)); return;
    case 'R': Keyboard.release((uint8_t)parseIntAt(cmd, 2)); return;
    case 'A': Keyboard.releaseAll(); return;
    case 'P': Serial.println("PONG"); return;
    case 'Q': Serial.println(usbReady ? "USB:1" : "USB:0"); return;
    default:
        triggerError();
        Serial.println("ERR");
        return;
    }
}

// ──── Setup ────
void setup() {
    setRGB(RGB_BRIGHTNESS, RGB_BRIGHTNESS/2, 0);

    Mouse.begin();
    Keyboard.begin();

    // Custom USB descriptor
    USB.manufacturerName("Microsoft");
    USB.productName("USB Keyboard");
    USB.VID(0x045E);
    USB.PID(0x07A5);
    // No serial number — like real budget keyboards

    USB.begin();

    Serial.begin(115200);

    unsigned long startWait = millis();
    while (!Serial && (millis() - startWait < 3000)) {
        updateLED();
        delay(10);
    }

    usbReady = true;
    currentLedState = LED_READY;

    Serial.println("[ESP32-S3] USB HID Bridge Ready");
}

// ──── Main Loop ────
void loop() {
    updateLED();

    while (Serial.available()) {
        char c = Serial.read();
        if (c == '\n' || c == '\r') {
            if (bufPos > 0) {
                inputBuffer[bufPos] = '\0';  // null-terminate
                processCommand(inputBuffer, bufPos);
                bufPos = 0;
            }
        } else if (bufPos < INPUT_BUF_SIZE - 1) {
            inputBuffer[bufPos++] = c;
        }
        // If bufPos hits max, silently drop characters until newline
    }

    // Detect Python disconnect
    if (everConnected && !Serial) {
        currentLedState = LED_READY;
        everConnected = false;
    }
}
