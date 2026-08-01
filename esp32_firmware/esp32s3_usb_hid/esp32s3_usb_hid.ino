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
  "3.5.1" // Update alongside esp32_firmware/firmware_version
#define AUTH_TIMEOUT_MS                                                        \
  10000            // Lock if no handshake within 10s of first serial data
#define MAX_CMD_LEN 64 // Drop the input buffer if no newline arrives by here

USBHIDMouse Mouse;
USBHIDKeyboard Keyboard;

// Fixed command buffer — no Arduino String. The bot streams hundreds of
// commands per second for hours; per-byte String += and per-command
// substring() churned the heap until it fragmented and the firmware fell
// over mid-run (USB dropped off the bus after a few minutes of grinding).
char inputBuffer[MAX_CMD_LEN + 1];
uint8_t inputLen = 0;
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
  // Only touch the LED when the colour actually changes. Several LED states
  // "set" a solid colour every loop pass; unconditional neopixelWrite spammed
  // an RMT transaction every ~1 ms alongside serial + HID load.
  static uint8_t lastR = 255, lastG = 255, lastB = 255;
  if (r == lastR && g == lastG && b == lastB)
    return;
  lastR = r; lastG = g; lastB = b;
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
void processCommand(char *cmd) {
  // In-place trim; parsing below is heap-free (see inputBuffer comment).
  while (*cmd == ' ' || *cmd == '\t')
    cmd++;
  size_t len = strlen(cmd);
  while (len > 0 && (cmd[len - 1] == ' ' || cmd[len - 1] == '\t'))
    cmd[--len] = '\0';
  if (len == 0)
    return;
  char type = cmd[0];
  const char *args = cmd + 1; // strtol skips leading spaces itself

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
    const char *clientVer = args;
    while (*clientVer == ' ')
      clientVer++;
    if (strcmp(clientVer, FIRMWARE_VERSION) == 0) {
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

  // ── Acknowledged commands (every one replies OK) ──────────────────────────
  // M/S are ACK'd again as of 3.5.1. The fire-and-forget variant let the
  // host run ahead of the 256-byte CDC RX buffer (not enlargeable on core
  // 2.0.17), and the resulting overflow corruption / TX backpressure kept
  // wedging the link a few minutes into a run. One-command-one-OK is
  // self-clocking — at most one line is ever in flight — the same protocol
  // the pre-3.4.2 firmware ran overnight without issues.
  switch (type) {
  case 'M': {
    char *end1, *end2;
    long mx = strtol(args, &end1, 10);
    long my = strtol(end1, &end2, 10);
    if (end1 == args || end2 == end1)
      return; // malformed — need two numbers
    // Mouse.move deltas are signed 8-bit; clamp defensively.
    mx = constrain(mx, -127, 127);
    my = constrain(my, -127, 127);
    Mouse.move((char)mx, (char)my, 0);
    break;
  }
  case 'S':
    Mouse.move(0, 0, constrain(strtol(args, nullptr, 10), -127, 127));
    break;
  case 'C':
    Mouse.click(getBtn((int)strtol(args, nullptr, 10)));
    break;
  case 'D':
    Mouse.press(getBtn((int)strtol(args, nullptr, 10)));
    break;
  case 'U':
    Mouse.release(getBtn((int)strtol(args, nullptr, 10)));
    break;
  case 'K':
    Keyboard.press((uint8_t)strtol(args, nullptr, 10));
    break;
  case 'R':
    Keyboard.release((uint8_t)strtol(args, nullptr, 10));
    break;
  case 'A':
    Keyboard.releaseAll();
    break;
  default:
    // Unknown type = line corrupted by RX overflow during a move stream.
    // Stay SILENT: the host is not reading during streams, so replying ERR
    // to every garbage fragment backs up our TX FIFO, println then stalls
    // loop(), RX overflows even harder, and the spiral wedges the USB stack
    // (board drops off the bus until replugged). The host's retry logic
    // already covers the lost command.
    triggerError();
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
  // Never let a reply print stall loop() for long if the host isn't reading
  // (it doesn't read during fire-and-forget move streams). Default is 100 ms
  // per write; a stalled loop() is what lets the RX buffer overflow.
  // NOTE: do NOT call Serial.setRxBufferSize() here — on core 2.0.17 it
  // wedges the CDC (verified: 20-line burst then silence).
  Serial.setTxTimeoutMs(20);

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
      if (inputLen > 0) {
        inputBuffer[inputLen] = '\0';
        processCommand(inputBuffer);
        inputLen = 0;
      }
    } else if (inputLen < MAX_CMD_LEN) {
      inputBuffer[inputLen++] = c;
    } else {
      // Line with no terminator (garbage / framing loss): drop it rather
      // than grow — the longest valid command is well under MAX_CMD_LEN.
      inputLen = 0;
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
