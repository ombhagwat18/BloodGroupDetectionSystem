/*
 * HemoScan ESP32 firmware  (R307 optical fingerprint sensor  ->  WiFi  ->  laptop API)
 *
 * Wiring (R307 is a 3.3-6V UART module):
 *   R307 red   (VCC) -> ESP32 3V3  (5V also works for the sensor, but then use a level shifter on TX->ESP32 RX)
 *   R307 black (GND) -> ESP32 GND
 *   R307 yellow (TX) -> ESP32 GPIO16 (RX2)
 *   R307 white  (RX) -> ESP32 GPIO17 (TX2)
 *
 * Libraries: only the ESP32 Arduino core (WiFi, HTTPClient) + ArduinoJson (Library Manager, v6 or v7).
 * Board: "ESP32 Dev Module".  Serial monitor: 115200.
 *
 * Protocol with the dashboard (see backend/app/main.py):
 *   heartbeat every 5 s -> poll for commands every 1 s -> capture / enroll / delete_slot / cancel
 *   capture: GenImg -> UpImage (36 864 bytes, 4-bit pixels) -> Img2Tz+Search (identify) -> POST /api/device/scan
 *
 * NOTE: written against the R307 datasheet, not yet run on real hardware. Expect to tune timeouts.
 */
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// ---------------------------------------------------------------- CONFIG
const char* WIFI_SSID  = "YOUR_WIFI";
const char* WIFI_PASS  = "YOUR_PASSWORD";
const char* SERVER_URL = "http://192.168.1.50:8000";   // laptop IP (shown on the dashboard "Device & Model" page)
const char* DEVICE_KEY = "hemoscan-dev-key";
const char* DEVICE_ID  = "esp32-01";
const char* FW_VERSION = "1.0";
const uint32_t SENSOR_BAUD = 57600;                     // R307 default
const uint16_t SENSOR_PASSWORD_LO = 0, SENSOR_PASSWORD_HI = 0;  // default password 0x00000000
const int MAX_SLOT = 200;

#define SENSOR_SERIAL Serial2
const int SENSOR_RX = 16, SENSOR_TX = 17;
const size_t IMG_BYTES = 256UL * 288UL / 2;            // 36 864

// ---------------------------------------------------------------- R307 packet layer
const uint8_t PID_CMD = 0x01, PID_DATA = 0x02, PID_ACK = 0x07, PID_END = 0x08;
const uint8_t CMD_GENIMG = 0x01, CMD_IMG2TZ = 0x02, CMD_MATCH = 0x03, CMD_SEARCH = 0x04, CMD_REGMODEL = 0x05,
              CMD_STORE = 0x06, CMD_DELETE = 0x0C, CMD_UPIMAGE = 0x0A, CMD_VFYPWD = 0x13, CMD_TEMPLATENUM = 0x1D;

struct Ack { bool ok = false; uint8_t code = 0xFF; uint8_t data[16]; uint16_t dlen = 0; };

void sendPacket(uint8_t pid, const uint8_t* payload, uint16_t n) {
  uint16_t len = n + 2;
  uint16_t sum = pid + (len >> 8) + (len & 0xFF);
  uint8_t hdr[9] = {0xEF, 0x01, 0xFF, 0xFF, 0xFF, 0xFF, pid, (uint8_t)(len >> 8), (uint8_t)(len & 0xFF)};
  SENSOR_SERIAL.write(hdr, 9);
  for (uint16_t i = 0; i < n; i++) { SENSOR_SERIAL.write(payload[i]); sum += payload[i]; }
  SENSOR_SERIAL.write((uint8_t)(sum >> 8));
  SENSOR_SERIAL.write((uint8_t)(sum & 0xFF));
}

bool readBytes(uint8_t* buf, size_t n, uint32_t timeoutMs) {
  uint32_t t0 = millis();
  size_t got = 0;
  while (got < n) {
    if (SENSOR_SERIAL.available()) { buf[got++] = SENSOR_SERIAL.read(); t0 = millis(); }
    else if (millis() - t0 > timeoutMs) return false;
    else delay(0);
  }
  return true;
}

// Reads one packet. Returns pid (or -1). Payload (without checksum) copied to out, length in outLen.
int readPacket(uint8_t* out, uint16_t maxOut, uint16_t& outLen, uint32_t timeoutMs = 1000) {
  uint8_t h[9];
  if (!readBytes(h, 9, timeoutMs) || h[0] != 0xEF || h[1] != 0x01) return -1;
  uint16_t len = (h[7] << 8) | h[8];
  if (len < 2) return -1;
  uint16_t n = len - 2;
  for (uint16_t i = 0; i < n; i++) {
    uint8_t b;
    if (!readBytes(&b, 1, timeoutMs)) return -1;
    if (i < maxOut) out[i] = b;
  }
  uint8_t cs[2];
  if (!readBytes(cs, 2, timeoutMs)) return -1;
  outLen = n < maxOut ? n : maxOut;
  return h[6];
}

Ack command(const uint8_t* payload, uint16_t n, uint32_t timeoutMs = 2000) {
  while (SENSOR_SERIAL.available()) SENSOR_SERIAL.read();
  sendPacket(PID_CMD, payload, n);
  Ack a;
  uint8_t buf[20]; uint16_t l = 0;
  int pid = readPacket(buf, sizeof(buf), l, timeoutMs);
  if (pid == PID_ACK && l >= 1) {
    a.code = buf[0]; a.ok = (buf[0] == 0x00);
    a.dlen = l - 1; if (a.dlen > sizeof(a.data)) a.dlen = sizeof(a.data);
    memcpy(a.data, buf + 1, a.dlen);
  }
  return a;
}
Ack cmd1(uint8_t c, uint32_t t = 2000) { return command(&c, 1, t); }
Ack cmd2(uint8_t c, uint8_t a, uint32_t t = 2000) { uint8_t p[2] = {c, a}; return command(p, 2, t); }

bool sensorInit() {
  SENSOR_SERIAL.begin(SENSOR_BAUD, SERIAL_8N1, SENSOR_RX, SENSOR_TX);
  delay(300);
  uint8_t p[5] = {CMD_VFYPWD, 0, 0, (uint8_t)SENSOR_PASSWORD_HI, (uint8_t)SENSOR_PASSWORD_LO};
  return command(p, 5).ok;
}

int templateCount() {
  Ack a = cmd1(CMD_TEMPLATENUM);
  return (a.ok && a.dlen >= 2) ? (a.data[0] << 8) | a.data[1] : -1;
}

// Image buffer -> raw 4-bit bytes (as sent by the sensor). Caller frees nothing; buffer is static-allocated once.
uint8_t* imgBuf = nullptr;
bool uploadImage() {
  Ack a = cmd1(CMD_UPIMAGE, 2000);
  if (!a.ok) return false;
  size_t got = 0;
  uint8_t chunk[256];
  while (true) {
    uint16_t l = 0;
    int pid = readPacket(chunk, sizeof(chunk), l, 2000);
    if (pid != PID_DATA && pid != PID_END) return false;
    if (got + l > IMG_BYTES) return false;
    memcpy(imgBuf + got, chunk, l);
    got += l;
    if (pid == PID_END) break;
  }
  return got == IMG_BYTES;
}

// ---------------------------------------------------------------- HTTP helpers
bool connected() { return WiFi.status() == WL_CONNECTED; }

void ensureWifi() {
  if (connected()) return;
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  uint32_t t0 = millis();
  while (!connected() && millis() - t0 < 15000) delay(250);
}

int postJson(const String& path, const String& body, String* resp = nullptr) {
  HTTPClient http;
  http.begin(String(SERVER_URL) + path);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Key", DEVICE_KEY);
  int code = http.POST(body);
  if (resp && code > 0) *resp = http.getString();
  http.end();
  return code;
}

String state = "idle";
bool sensorOk = false;

void heartbeat() {
  JsonDocument d;
  d["device_id"] = DEVICE_ID; d["fw"] = FW_VERSION; d["ip"] = WiFi.localIP().toString();
  d["sensor_ok"] = sensorOk; d["state"] = state;
  int n = sensorOk ? templateCount() : -1;
  if (n >= 0) d["template_count"] = n;
  String s; serializeJson(d, s);
  postJson("/api/device/heartbeat", s);
}

void sendEvent(const char* st, const String& msg, long cmdId) {
  state = st;
  JsonDocument d;
  d["device_id"] = DEVICE_ID; d["state"] = st; d["message"] = msg;
  if (cmdId > 0) d["command_id"] = cmdId;
  String s; serializeJson(d, s);
  postJson("/api/device/event", s);
}

bool pollCommand(JsonDocument& out) {
  HTTPClient http;
  http.begin(String(SERVER_URL) + "/api/device/poll?device_id=" + DEVICE_ID);
  http.addHeader("X-Device-Key", DEVICE_KEY);
  int code = http.GET();
  bool has = false;
  if (code == 200) {
    JsonDocument d;
    if (!deserializeJson(d, http.getString()) && !d["command"].isNull()) { out = d["command"]; has = true; }
  }
  http.end();
  return has;
}

bool cancelRequested() {  // checked while waiting for a finger
  JsonDocument c;
  if (pollCommand(c) && String((const char*)c["type"]) == "cancel") return true;
  return false;
}

// ---------------------------------------------------------------- actions
bool waitForFinger(long cmdId, uint32_t timeoutMs) {
  uint32_t t0 = millis(), lastPoll = millis();
  while (millis() - t0 < timeoutMs) {
    Ack a = cmd1(CMD_GENIMG, 1000);
    if (a.ok) return true;                 // 0x00 = image captured
    if (a.code != 0x02 && a.code != 0xFF) { /* 0x02 = no finger; anything else is a real error */ }
    if (millis() - lastPoll > 1500) { lastPoll = millis(); if (cancelRequested()) { sendEvent("cancelled", "Cancelled", cmdId); return false; } }
    delay(120);
  }
  sendEvent("timeout", "No finger detected", cmdId);
  return false;
}

void doCapture(long cmdId) {
  sendEvent("waiting_finger", "Place finger on the sensor", cmdId);
  if (!waitForFinger(cmdId, 20000)) return;

  sendEvent("reading_image", "Reading image from sensor (about 10 s)", cmdId);
  if (!uploadImage()) { sendEvent("failed", "Could not read image from sensor", cmdId); return; }

  // Identify: image buffer is still valid after UpImage, so convert it and search the on-sensor library.
  int slot = 0, score = 0;
  Ack t = cmd2(CMD_IMG2TZ, 1);
  if (t.ok) {
    uint8_t p[6] = {CMD_SEARCH, 1, 0, 0, (uint8_t)(MAX_SLOT >> 8), (uint8_t)(MAX_SLOT & 0xFF)};
    Ack s = command(p, 6, 2000);
    if (s.ok && s.dlen >= 4) { slot = (s.data[0] << 8) | s.data[1]; score = (s.data[2] << 8) | s.data[3]; }
  }

  HTTPClient http;
  String url = String(SERVER_URL) + "/api/device/scan?device_id=" + DEVICE_ID + "&command_id=" + cmdId +
               "&slot=" + slot + "&score=" + score + "&fmt=raw4";
  http.begin(url);
  http.addHeader("Content-Type", "application/octet-stream");
  http.addHeader("X-Device-Key", DEVICE_KEY);
  http.setTimeout(20000);
  int code = http.POST(imgBuf, IMG_BYTES);
  http.end();
  sendEvent(code == 201 ? "idle" : "failed", code == 201 ? "done" : String("Upload failed, HTTP ") + code, cmdId);
}

bool captureTo(uint8_t buffer, long cmdId, const char* prompt) {
  sendEvent("enrolling", prompt, cmdId);
  if (!waitForFinger(cmdId, 20000)) return false;
  return cmd2(CMD_IMG2TZ, buffer).ok;
}

void doEnroll(long cmdId, int slot) {
  if (!captureTo(1, cmdId, "Place finger (1/2)")) { goto fail; }
  sendEvent("enrolling", "Remove finger", cmdId);
  delay(1500);
  while (cmd1(CMD_GENIMG, 500).code != 0x02) delay(150);   // wait until finger lifted
  if (!captureTo(2, cmdId, "Place the same finger again (2/2)")) { goto fail; }
  if (!cmd1(CMD_REGMODEL).ok) { sendEvent("failed", "Fingers did not match - try again", cmdId); goto fail; }
  {
    uint8_t p[4] = {CMD_STORE, 1, (uint8_t)(slot >> 8), (uint8_t)(slot & 0xFF)};
    if (!command(p, 4).ok) { sendEvent("failed", "Could not store template", cmdId); goto fail; }
  }
  {
    JsonDocument d; d["device_id"] = DEVICE_ID; d["command_id"] = cmdId; d["ok"] = true; d["slot"] = slot;
    String s; serializeJson(d, s); postJson("/api/device/enroll_result", s);
  }
  sendEvent("idle", "Enrolled", cmdId);
  return;
fail: {
    JsonDocument d; d["device_id"] = DEVICE_ID; d["command_id"] = cmdId; d["ok"] = false; d["error"] = "Enrolment failed";
    String s; serializeJson(d, s); postJson("/api/device/enroll_result", s);
    state = "idle";
  }
}

void doDeleteSlot(int slot) {
  uint8_t p[5] = {CMD_DELETE, (uint8_t)(slot >> 8), (uint8_t)(slot & 0xFF), 0, 1};
  command(p, 5);
}

// ---------------------------------------------------------------- main
void setup() {
  Serial.begin(115200);
  imgBuf = (uint8_t*)malloc(IMG_BYTES);
  WiFi.mode(WIFI_STA);
  ensureWifi();
  Serial.printf("WiFi %s  IP %s\n", connected() ? "connected" : "FAILED", WiFi.localIP().toString().c_str());
  sensorOk = sensorInit();
  Serial.printf("R307 sensor: %s\n", sensorOk ? "OK" : "NOT FOUND (check wiring/baud)");
}

uint32_t lastBeat = 0, lastPoll = 0;
void loop() {
  ensureWifi();
  if (!connected()) { delay(1000); return; }

  if (millis() - lastBeat > 5000) {
    lastBeat = millis();
    if (!sensorOk) sensorOk = sensorInit();   // allow hot-plugging the sensor
    heartbeat();
  }
  if (millis() - lastPoll > 1000) {
    lastPoll = millis();
    JsonDocument c;
    if (pollCommand(c)) {
      long id = c["id"];
      String type = c["type"].as<String>();
      Serial.printf("command %ld %s\n", id, type.c_str());
      if (!sensorOk) sendEvent("failed", "R307 sensor not responding", id);
      else if (type == "capture") doCapture(id);
      else if (type == "enroll") doEnroll(id, c["payload"]["slot"] | 1);
      else if (type == "delete_slot") doDeleteSlot(c["payload"]["slot"] | 0);
      state = "idle";
    }
  }
}
