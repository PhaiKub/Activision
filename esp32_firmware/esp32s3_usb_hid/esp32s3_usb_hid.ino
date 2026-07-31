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
 *   🔴 Red fast blink — LOCKED (bot version mismatch — flash firmware!)
 *
 * Board settings in Arduino IDE:
 *   Board:           ESP32-S3 Dev Module
 *   USB Mode:        USB-OTG (TinyUSB)
 *   USB CDC On Boot: Enabled
 *
 * Protocol:
 *   H ver     — handshake (bot sends expected firmware version)
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
 *   V         — query firmware version (returns VER:<version>)
 */

#include "USB.h"
#include "USBHIDKeyboard.h"
#include "USBHIDMouse.h"

// ──── Config ────
#define RGB_PIN 48
#define RGB_BRIGHTNESS 10
#define FIRMWARE_VERSION                                                       \
  "3.5.0" // Update alongside esp32_firmware/firmware_version
#define AUTH_TIMEOUT_MS                                                        \
  10000            // Lock if no handshake within 10s of first serial data
#define MAX_CMD_LEN 64 // Drop the input buffer if no newline arrives by here

USBHIDMouse Mouse;
USBHIDKeyboard Keyboard;

String inputBuffer = "";
bool usbReady = false;

// ──── LED state machine ────
enum LedState {
  LED_BOOTING,
  LED_READY,
  LED_ACTIVE,
  LED_IDLE,
  LED_ERROR,
  LED_LOCKED
};
LedState currentLedState = LED_BOOTING;
unsigned long lastLedUpdate = 0;
unsigned long lastCommandTime = 0;
unsigned long errorFlashStart = 0;
bool blinkOn = false;
bool everConnected = false;
bool authenticated = false; // set true only after successful H handshake
bool hardLocked = false;    // once true, ALL commands blocked (including ping)
unsigned long firstSerialTime = 0; // timestamp of first serial data received
bool serialSeen = false;           // has any serial data been received?

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
      setRGB(blinkOn ? RGB_BRIGHTNESS : 0, blinkOn ? RGB_BRIGHTNESS / 2 : 0, 0);
    }
    break;
  case LED_READY:
    setRGB(RGB_BRIGHTNESS / 2, 0, RGB_BRIGHTNESS);
    break;
  case LED_ACTIVE:
    setRGB(0, 0, RGB_BRIGHTNESS);
    if (now - lastCommandTime > 5000)
      currentLedState = LED_IDLE;
    break;
  case LED_IDLE:
    if (now - lastLedUpdate >= 1000) {
      lastLedUpdate = now;
      blinkOn = !blinkOn;
      setRGB(0, blinkOn ? RGB_BRIGHTNESS : RGB_BRIGHTNESS / 6, 0);
    }
    if (now - lastCommandTime > 30000) {
      currentLedState = LED_READY;
      everConnected = false;
    }
    break;
  case LED_ERROR:
    if (now - errorFlashStart < 150)
      setRGB(RGB_BRIGHTNESS, 0, 0);
    else if (now - errorFlashStart < 300)
      setRGB(0, 0, 0);
    else if (now - errorFlashStart < 450)
      setRGB(RGB_BRIGHTNESS, 0, 0);
    else
      currentLedState = (now - lastCommandTime < 5000) ? LED_ACTIVE
                        : everConnected                ? LED_IDLE
                                                       : LED_READY;
    break;
  case LED_LOCKED:
    // Fast persistent red blink — firmware/bot version mismatch
    if (now - lastLedUpdate >= 150) {
      lastLedUpdate = now;
      blinkOn = !blinkOn;
      setRGB(blinkOn ? RGB_BRIGHTNESS : 0, 0, 0);
    }
    break;
  }
}

void triggerActive() {
  lastCommandTime = millis();
  everConnected = true;
  if (currentLedState != LED_ERROR)
    currentLedState = LED_ACTIVE;
}
void triggerError() {
  errorFlashStart = millis();
  currentLedState = LED_ERROR;
}

// ──── Mouse button mapping ────
uint8_t getBtn(int b) {
  if (b == 2)
    return MOUSE_RIGHT;
  if (b == 3)
    return MOUSE_MIDDLE;
  return MOUSE_LEFT;
}

// ──── Command processor ────
void processCommand(String cmd) {
  cmd.trim();
  if (cmd.length() == 0)
    return;
  char type = cmd.charAt(0);

  // Track first serial activity for auth timeout
  if (!serialSeen) {
    serialSeen = true;
    firstSerialTime = millis();
  }

  // ── Hard-locked: refuse everything except a fresh handshake ───────────────
  // Don't respond — the device appears dead to unauthenticated bots. 'H' is
  // the one exception so a matching-version host can clear the lock itself;
  // without it the only way out is a physical replug.
  if (hardLocked && type != 'H') {
    return;
  }

  // ── Handshake & info commands (available before auth) ─────────────────────
  switch (type) {
  case 'H': {
    // Handshake: bot sends its expected firmware version
    String clientVer = cmd.substring(2);
    clientVer.trim();
    if (clientVer == FIRMWARE_VERSION) {
      authenticated = true;
      hardLocked = false;
      if (currentLedState == LED_LOCKED)
        currentLedState = LED_READY;
      Serial.println("AUTH:OK");
    } else {
      authenticated = false;
      hardLocked = true; // wrong version → hard lock
      currentLedState = LED_LOCKED;
      Serial.println("AUTH:FAIL");
    }
    return;
  }
  case 'V':
    Serial.println("VER:" FIRMWARE_VERSION);
    return;
  case 'P':
    // Only respond PONG if auth hasn't timed out yet
    if (authenticated || !serialSeen ||
        (millis() - firstSerialTime < AUTH_TIMEOUT_MS)) {
      Serial.println("PONG");
    }
    // Silently ignore ping after timeout without auth
    return;
  case 'Q':
    Serial.println(usbReady ? "USB:1" : "USB:0");
    return;
  }

  // ── All other commands require a successful handshake ─────────────────────
  if (!authenticated) {
    currentLedState = LED_LOCKED;
    Serial.println("LOCKED");
    return;
  }

  triggerActive();

  // ── High-frequency, fire-and-forget commands (no OK ACK) ──────────────────
  // Mouse move/scroll are sent in a tight loop by the host; ACKing each one
  // would add a serial round-trip of latency per step. The host does not wait
  // for a reply, so these must NOT print anything.
  switch (type) {
  case 'M': {
    int sp1 = cmd.indexOf(' ', 0);
    int sp2 = cmd.indexOf(' ', sp1 + 1);
    if (sp1 < 0 || sp2 < 0)
      return;
    // Mouse.move deltas are signed 8-bit; clamp defensively.
    long mx = cmd.substring(sp1 + 1, sp2).toInt();
    long my = cmd.substring(sp2 + 1).toInt();
    mx = constrain(mx, -127, 127);
    my = constrain(my, -127, 127);
    Mouse.move((char)mx, (char)my, 0);
    return;
  }
  case 'S':
    Mouse.move(0, 0, constrain(cmd.substring(2).toInt(), -127, 127));
    return;
  }

  // ── Acknowledged commands (reply OK / ERR) ────────────────────────────────
  switch (type) {
  case 'C':
    Mouse.click(getBtn(cmd.substring(2).toInt()));
    break;
  case 'D':
    Mouse.press(getBtn(cmd.substring(2).toInt()));
    break;
  case 'U':
    Mouse.release(getBtn(cmd.substring(2).toInt()));
    break;
  case 'K':
    Keyboard.press((uint8_t)cmd.substring(2).toInt());
    break;
  case 'R':
    Keyboard.release((uint8_t)cmd.substring(2).toInt());
    break;
  case 'A':
    Keyboard.releaseAll();
    break;
  default:
    triggerError();
    Serial.println("ERR");
    return;
  }
  Serial.println("OK");
}

// ──── Setup ────
void setup() {
  setRGB(RGB_BRIGHTNESS, RGB_BRIGHTNESS / 2, 0);

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
      // Guard against unbounded growth from a stream with no line terminator
      // (garbage / framing loss): the longest valid command is well under this.
      if (inputBuffer.length() > MAX_CMD_LEN) {
        inputBuffer = "";
      }
    }
  }

  // ── Auth timeout: hard-lock if serial data seen but no auth within deadline
  if (serialSeen && !authenticated && !hardLocked) {
    if (millis() - firstSerialTime >= AUTH_TIMEOUT_MS) {
      hardLocked = true;
      currentLedState = LED_LOCKED;
    }
  }

  // NOTE: do not gate auth on `!Serial` here. On the S3's native USB the CDC
  // "connected" flag tracks DTR, which the host does not reliably assert, so
  // `!Serial` reads true while data is still flowing. Resetting auth on it
  // wiped `authenticated` one loop after the first accepted command (which is
  // what sets everConnected), so exactly one move ran per handshake and every
  // later command answered LOCKED. A host that never handshakes is already
  // covered by the AUTH_TIMEOUT hard-lock above, and the LED state machine
  // returns to LED_READY on its own once commands stop.

  delay(1);
}
