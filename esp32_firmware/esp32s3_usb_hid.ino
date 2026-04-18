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
 */

#include "USB.h"
#include "USBHIDKeyboard.h"
#include "USBHIDMouse.h"

// ──── Config ────
#define RGB_PIN        48
#define RGB_BRIGHTNESS 10

USBHIDMouse Mouse;
USBHIDKeyboard Keyboard;

String inputBuffer = "";
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

// ──── Command processor ────
void processCommand(String cmd) {
    cmd.trim();
    if (cmd.length() == 0) return;
    char type = cmd.charAt(0);

    triggerActive();

    switch (type) {
    case 'M': {
        int sp1 = cmd.indexOf(' ', 0);
        int sp2 = cmd.indexOf(' ', sp1 + 1);
        if (sp1 < 0 || sp2 < 0) break;
        Mouse.move(cmd.substring(sp1+1, sp2).toInt(), cmd.substring(sp2+1).toInt(), 0);
        break;
    }
    case 'C': Mouse.click(getBtn(cmd.substring(2).toInt())); break;
    case 'D': Mouse.press(getBtn(cmd.substring(2).toInt())); break;
    case 'U': Mouse.release(getBtn(cmd.substring(2).toInt())); break;
    case 'S': Mouse.move(0, 0, cmd.substring(2).toInt()); break;
    case 'K': Keyboard.press((uint8_t)cmd.substring(2).toInt()); break;
    case 'R': Keyboard.release((uint8_t)cmd.substring(2).toInt()); break;
    case 'A': Keyboard.releaseAll(); break;
    case 'P': Serial.println("PONG"); return;
    case 'Q': Serial.println(usbReady ? "USB:1" : "USB:0"); return;
    default:
        triggerError();
        Serial.println("ERR");
        return;
    }
    Serial.println("OK");
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
            if (inputBuffer.length() > 0) {
                processCommand(inputBuffer);
                inputBuffer = "";
            }
        } else {
            inputBuffer += c;
        }
    }

    // Detect Python disconnect
    if (everConnected && !Serial) {
        currentLedState = LED_READY;
        everConnected = false;
    }

    delay(1);
}
