/**
 * =========================================================================================
 * PROJECT: GREEN CORRIDOR SMART EMERGENCY SYSTEM (INDIA)
 * MODULE: TRAFFIC SIGNAL INTERSECTION CONTROLLER FIRMWARE
 * TARGET: ESP32-WROOM-32 + 12-Channel Relay Board / High-Power LED Drivers
 * =========================================================================================
 * 
 * Pinout Allocation (4-Way 12-Lamp Junction):
 * NORTH: Red: 13, Yellow: 12, Green: 14
 * EAST:  Red: 27, Yellow: 26, Green: 25
 * SOUTH: Red: 33, Yellow: 32, Green: 15
 * WEST:  Red: 19, Yellow: 18, Green: 5
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// ======================== NETWORK SETTINGS =============================
const char* WIFI_SSID       = "Traffic_Police_Junc_Net";
const char* WIFI_PASSWORD   = "SmartMysuruTraffic2026";
const char* STATUS_ENDPOINT = "http://192.168.1.100:8000/api/hardware/signals";

// ======================== HARDWARE RELAY PINS ===========================
// Relay logic: Many industrial relay boards are Active LOW (0 = ON, 1 = OFF)
#define RELAY_ACTIVE_STATE LOW
#define RELAY_INACTIVE_STATE HIGH

// North Approach
#define PIN_N_RED     13
#define PIN_N_YEL     12
#define PIN_N_GRN     14

// East Approach
#define PIN_E_RED     27
#define PIN_E_YEL     26
#define PIN_E_GRN     25

// South Approach
#define PIN_S_RED     33
#define PIN_S_YEL     32
#define PIN_S_GRN     15

// West Approach
#define PIN_W_RED     19
#define PIN_W_YEL     18
#define PIN_W_GRN     5

#define BUZZER_PIN    4

unsigned long lastPollTime = 0;
const unsigned long POLL_INTERVAL_MS = 250; // 4Hz update rate for responsive preemption
unsigned long lastValidPacketTime = 0;
const unsigned long WATCHDOG_TIMEOUT_MS = 10000; // 10s watchdog fallback

void setArmLight(int pinRed, int pinYel, int pinGrn, const char* color) {
  if (strcmp(color, "GREEN") == 0) {
    digitalWrite(pinRed, RELAY_INACTIVE_STATE);
    digitalWrite(pinYel, RELAY_INACTIVE_STATE);
    digitalWrite(pinGrn, RELAY_ACTIVE_STATE);
  } else if (strcmp(color, "YELLOW") == 0) {
    digitalWrite(pinRed, RELAY_INACTIVE_STATE);
    digitalWrite(pinYel, RELAY_ACTIVE_STATE);
    digitalWrite(pinGrn, RELAY_INACTIVE_STATE);
  } else { // RED (Default)
    digitalWrite(pinRed, RELAY_ACTIVE_STATE);
    digitalWrite(pinYel, RELAY_INACTIVE_STATE);
    digitalWrite(pinGrn, RELAY_INACTIVE_STATE);
  }
}

void setup() {
  Serial.begin(115200);
  Serial.println("\n[TRAFFIC CONTROLLER] Initializing Green Corridor Junction hardware...");

  // Setup pin modes
  int outputPins[] = {
    PIN_N_RED, PIN_N_YEL, PIN_N_GRN,
    PIN_E_RED, PIN_E_YEL, PIN_E_GRN,
    PIN_S_RED, PIN_S_YEL, PIN_S_GRN,
    PIN_W_RED, PIN_W_YEL, PIN_W_GRN,
    BUZZER_PIN
  };

  for (int p : outputPins) {
    pinMode(p, OUTPUT);
    digitalWrite(p, RELAY_INACTIVE_STATE);
  }

  // Initial State: All RED for safety boot
  digitalWrite(PIN_N_RED, RELAY_ACTIVE_STATE);
  digitalWrite(PIN_E_RED, RELAY_ACTIVE_STATE);
  digitalWrite(PIN_S_RED, RELAY_ACTIVE_STATE);
  digitalWrite(PIN_W_RED, RELAY_ACTIVE_STATE);

  // Connect to WiFi
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  int tries = 0;
  while (WiFi.status() != WL_CONNECTED && tries < 15) {
    delay(400);
    Serial.print(".");
    tries++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WIFI] Connected! Ready for pre-emption signals.");
    lastValidPacketTime = millis();
  } else {
    Serial.println("\n[WIFI] Network not available. Autonomous safe fallback will operate.");
  }
}

void loop() {
  unsigned long now = millis();

  if (now - lastPollTime >= POLL_INTERVAL_MS) {
    lastPollTime = now;

    if (WiFi.status() == WL_CONNECTED) {
      pollServerForSignals();
    }
  }

  // WATCHDOG CHECK: If no valid packet received for > 10 seconds, activate standalone fail-safe
  if (now - lastValidPacketTime > WATCHDOG_TIMEOUT_MS) {
    runAutonomousFailsafeCycle(now);
  }
}

void pollServerForSignals() {
  HTTPClient http;
  http.begin(STATUS_ENDPOINT);
  http.setTimeout(800);

  int httpCode = http.GET();
  if (httpCode == HTTP_CODE_OK) {
    String payload = http.getString();
    
    // Parse JSON
    StaticJsonDocument<512> doc;
    DeserializationError error = deserializeJson(doc, payload);

    if (!error) {
      lastValidPacketTime = millis();

      const char* northLight = doc["signals"]["NORTH"];
      const char* eastLight  = doc["signals"]["EAST"];
      const char* southLight = doc["signals"]["SOUTH"];
      const char* westLight  = doc["signals"]["WEST"];
      const char* mode       = doc["mode"];

      setArmLight(PIN_N_RED, PIN_N_YEL, PIN_N_GRN, northLight);
      setArmLight(PIN_E_RED, PIN_E_YEL, PIN_E_GRN, eastLight);
      setArmLight(PIN_S_RED, PIN_S_YEL, PIN_S_GRN, southLight);
      setArmLight(PIN_W_RED, PIN_W_YEL, PIN_W_GRN, westLight);

      // Sound buzzer alert if in active emergency mode
      if (strcmp(mode, "EMERGENCY_CORRIDOR") == 0) {
        digitalWrite(BUZZER_PIN, HIGH);
      } else {
        digitalWrite(BUZZER_PIN, LOW);
      }
    }
  }
  http.end();
}

void runAutonomousFailsafeCycle(unsigned long now) {
  // Safe default 15-second timer cycle between North-South and East-West
  unsigned long cycleTime = (now / 15000) % 2;
  if (cycleTime == 0) {
    // North-South GREEN, East-West RED
    setArmLight(PIN_N_RED, PIN_N_YEL, PIN_N_GRN, "GREEN");
    setArmLight(PIN_S_RED, PIN_S_YEL, PIN_S_GRN, "GREEN");
    setArmLight(PIN_E_RED, PIN_E_YEL, PIN_E_GRN, "RED");
    setArmLight(PIN_W_RED, PIN_W_YEL, PIN_W_GRN, "RED");
  } else {
    // East-West GREEN, North-South RED
    setArmLight(PIN_N_RED, PIN_N_YEL, PIN_N_GRN, "RED");
    setArmLight(PIN_S_RED, PIN_S_YEL, PIN_S_GRN, "RED");
    setArmLight(PIN_E_RED, PIN_E_YEL, PIN_E_GRN, "GREEN");
    setArmLight(PIN_W_RED, PIN_W_YEL, PIN_W_GRN, "GREEN");
  }
}
