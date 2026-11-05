/**
 * =========================================================================================
 * PROJECT: GREEN CORRIDOR SMART EMERGENCY SYSTEM (INDIA)
 * MODULE: VEHICLE GPS TRACKER & SIREN INTERFACE FIRMWARE
 * TARGET: ESP32-WROOM-32 + u-blox NEO-6M GPS + SIM7600 / WiFi
 * =========================================================================================
 * 
 * Description:
 * Transmits real-time vehicle GPS coordinates, speed, bearing, and siren status
 * to the Green Corridor central junction controller.
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <HardwareSerial.h>
#include <TinyGPSPlus.h>

// ======================== VEHICLE CONFIGURATION ========================
const char* VEHICLE_ID        = "AMB-108-MYS-01";
const char* VEHICLE_TYPE      = "AMBULANCE_CRITICAL"; // AMBULANCE_CRITICAL, FIRE_ENGINE, etc.
const int   PRIORITY_LEVEL    = 1;                    // 1: Critical (Ambulance), 2: Fire, 3: Standard
const char* DESTINATION       = "KR Hospital Emergency Trauma, Mysuru";

// ======================== NETWORK SETTINGS =============================
const char* WIFI_SSID         = "Ambulance_Hotspot";  // Or connect via SIM7600 4G LTE
const char* WIFI_PASSWORD     = "Emergency911";
const char* SERVER_ENDPOINT   = "http://192.168.1.100:8000/api/telemetry";

// ======================== HARDWARE PINOUT ===============================
#define GPS_RX_PIN            16   // ESP32 RX2 connects to GPS TX
#define GPS_TX_PIN            17   // ESP32 TX2 connects to GPS RX
#define GPS_BAUD_RATE         9600

#define SIREN_TRIGGER_PIN     4    // Connected to Emergency Siren Switch (Active LOW)
#define STATUS_LED_PIN        2    // Onboard Blue LED indicator
#define BUZZER_PIN            21   // Audio feedback in driver cabin

// ======================== OBJECTS & VARIABLES ===========================
TinyGPSPlus gps;
HardwareSerial gpsSerial(2); // UART2

unsigned long lastBroadcastTime = 0;
const unsigned long BROADCAST_INTERVAL_MS = 1000; // 1Hz telemetry frequency

void setup() {
  Serial.begin(115200);
  Serial.println("\n==============================================");
  Serial.println("  GREEN CORRIDOR EMERGENCY VEHICLE UNIT v1.0   ");
  Serial.println("==============================================");

  pinMode(SIREN_TRIGGER_PIN, INPUT_PULLUP);
  pinMode(STATUS_LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);

  // Initialize GPS Serial
  gpsSerial.begin(GPS_BAUD_RATE, SERIAL_8N1, GPS_RX_PIN, GPS_TX_PIN);
  Serial.println("[GPS] UART2 initialized at 9600 baud.");

  // Connect to Network
  Serial.printf("[WIFI] Connecting to %s...", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    digitalWrite(STATUS_LED_PIN, !digitalRead(STATUS_LED_PIN));
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WIFI] Connected! IP Address: " + WiFi.localIP().toString());
    digitalWrite(STATUS_LED_PIN, HIGH);
  } else {
    Serial.println("\n[WIFI] Fallback: Offline mode or Cellular Modem required.");
  }
}

void loop() {
  // 1. Read incoming NMEA sentences from GPS module
  while (gpsSerial.available() > 0) {
    gps.encode(gpsSerial.read());
  }

  // 2. Check Siren Switch status (Active LOW)
  bool isSirenActive = (digitalRead(SIREN_TRIGGER_PIN) == LOW);

  // 3. Periodic Broadcast
  unsigned long currentMillis = millis();
  if (currentMillis - lastBroadcastTime >= BROADCAST_INTERVAL_MS) {
    lastBroadcastTime = currentMillis;

    double latitude  = 28.5672; // Default mock fallback if no satellite lock
    double longitude = 77.2100;
    double speedKmh  = 60.0;
    double heading   = 180.0;
    bool hasGpsFix   = false;

    if (gps.location.isValid()) {
      latitude  = gps.location.lat();
      longitude = gps.location.lng();
      speedKmh  = gps.speed.kmph();
      heading   = gps.course.deg();
      hasGpsFix = true;
    }

    Serial.printf("[TELEMETRY] Lat: %.6f, Lon: %.6f | Speed: %.1f km/h | Fix: %s | Siren: %s\n",
                  latitude, longitude, speedKmh, hasGpsFix ? "YES" : "NO", isSirenActive ? "ACTIVE" : "OFF");

    if (WiFi.status() == WL_CONNECTED) {
      sendTelemetryPayload(latitude, longitude, speedKmh, heading, isSirenActive);
    }
  }
}

void sendTelemetryPayload(double lat, double lon, double speed, double heading, bool siren) {
  HTTPClient http;
  http.begin(SERVER_ENDPOINT);
  http.addHeader("Content-Type", "application/json");

  // Construct JSON Payload
  String jsonBody = "{";
  jsonBody += "\"vehicle_id\":\"" + String(VEHICLE_ID) + "\",";
  jsonBody += "\"vehicle_type\":\"" + String(VEHICLE_TYPE) + "\",";
  jsonBody += "\"priority_level\":" + String(PRIORITY_LEVEL) + ",";
  jsonBody += "\"location\":{";
  jsonBody += "\"lat\":" + String(lat, 6) + ",";
  jsonBody += "\"lon\":" + String(lon, 6) + ",";
  jsonBody += "\"speed_kmh\":" + String(speed, 1) + ",";
  jsonBody += "\"heading\":" + String(heading, 1);
  jsonBody += "},";
  jsonBody += "\"is_emergency_active\":" + String(siren ? "true" : "false") + ",";
  jsonBody += "\"destination_hospital\":\"" + String(DESTINATION) + "\"";
  jsonBody += "}";

  int httpResponseCode = http.POST(jsonBody);

  if (httpResponseCode > 0) {
    String response = http.getString();
    // Blink LED to indicate successful transmission
    digitalWrite(STATUS_LED_PIN, LOW);
    delay(50);
    digitalWrite(STATUS_LED_PIN, HIGH);
  } else {
    Serial.printf("[HTTP ERROR] Code: %d\n", httpResponseCode);
  }
  http.end();
}
