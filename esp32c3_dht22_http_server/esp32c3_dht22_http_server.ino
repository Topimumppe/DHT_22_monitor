#include <WiFi.h>
#include <WebServer.h>
#include <DHT.h>

#define DHTTYPE DHT22

#define DHT1_PIN 3
#define DHT2_PIN 7
#define DHT3_PIN 10

DHT dht1(DHT1_PIN, DHTTYPE);
DHT dht2(DHT2_PIN, DHTTYPE);
DHT dht3(DHT3_PIN, DHTTYPE);

struct Measurement {
  float temperature;
  float humidity;
  bool valid;
};

Measurement lastMeasurements[3];
bool hasMeasurement = false;

unsigned long lastSampleMillis = 0;
const unsigned long MEASURE_INTERVAL_MS = 15000;

WebServer server(80);

void clearMeasurements() {
  for (int i = 0; i < 3; i++) {
    lastMeasurements[i].temperature = NAN;
    lastMeasurements[i].humidity = NAN;
    lastMeasurements[i].valid = false;
  }
  hasMeasurement = false;
}

void sendJson(int code, const String &body) {
  server.send(code, "application/json", body);
}

void handleHealth() {
  sendJson(200, "{\"ok\":true}");
}

void handleData() {

  if (!hasMeasurement) {
    sendJson(404, "{\"ok\":false,\"error\":\"no data\"}");
    return;
  }

  String json = "{\"ok\":true";

  for (int i = 0; i < 3; i++) {

    json += ",\"sensor";
    json += String(i + 1);
    json += "\":";

    if (lastMeasurements[i].valid) {
      json += "{\"temperature\":";
      json += String(lastMeasurements[i].temperature, 1);
      json += ",\"humidity\":";
      json += String(lastMeasurements[i].humidity, 1);
      json += "}";
    } else {
      json += "{\"temperature\":null,\"humidity\":null}";
    }
  }

  json += "}";

  sendJson(200, json);

  clearMeasurements();
}

void measureSensors() {

  if (millis() - lastSampleMillis < MEASURE_INTERVAL_MS)
    return;

  lastSampleMillis = millis();

  bool anyValid = false;

  float t, h;

  // Sensor 1
  t = dht1.readTemperature();
  h = dht1.readHumidity();

  lastMeasurements[0].temperature = t;
  lastMeasurements[0].humidity = h;
  lastMeasurements[0].valid = !(isnan(t) || isnan(h));

  if (lastMeasurements[0].valid) anyValid = true;

  // Sensor 2
  t = dht2.readTemperature();
  h = dht2.readHumidity();

  lastMeasurements[1].temperature = t;
  lastMeasurements[1].humidity = h;
  lastMeasurements[1].valid = !(isnan(t) || isnan(h));

  if (lastMeasurements[1].valid) anyValid = true;

  // Sensor 3
  t = dht3.readTemperature();
  h = dht3.readHumidity();

  lastMeasurements[2].temperature = t;
  lastMeasurements[2].humidity = h;
  lastMeasurements[2].valid = !(isnan(t) || isnan(h));

  if (lastMeasurements[2].valid) anyValid = true;

  hasMeasurement = anyValid;

  if (anyValid) {
    Serial.println("Measurements updated:");
    for (int i = 0; i < 3; i++) {
      if (lastMeasurements[i].valid) {
        Serial.printf("Sensor %d: %.1f C %.1f %%\n",
                      i + 1,
                      lastMeasurements[i].temperature,
                      lastMeasurements[i].humidity);
      } else {
        Serial.printf("Sensor %d: ERROR\n", i + 1);
      }
    }
  } else {
    Serial.println("All DHT22 readings failed.");
  }
}

void setup() {

  Serial.begin(115200);
  delay(1000);

  dht1.begin();
  dht2.begin();
  dht3.begin();

  WiFi.mode(WIFI_AP);

  WiFi.softAP("ESP32C3-DHT22");

  Serial.print("AP IP: ");
  Serial.println(WiFi.softAPIP());

  clearMeasurements();

  server.on("/data", HTTP_GET, handleData);
  server.on("/health", HTTP_GET, handleHealth);

  server.onNotFound([]() {
    sendJson(404, "{\"ok\":false,\"error\":\"not found\"}");
  });

  server.begin();

  Serial.println("HTTP server started.");
}

void loop() {
  server.handleClient();
  measureSensors();
}