#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>

const char* ssid = "haqeem";
const char* pass = "0123456";

ESP8266WebServer server(80);

String lastStatus = "No status yet";

void sendToUNO(const String& s) {
  Serial.print(s);
  Serial.print("\n");
}

String htmlPage() {
  return R"(
<!DOCTYPE html><html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Smart Street Light</title>
<style>
  body{font-family:Arial;padding:16px}
  button{padding:14px 18px;margin:6px;font-size:16px}
  input{padding:10px;font-size:16px;width:120px}
  .box{padding:12px;border:1px solid #ddd;border-radius:12px;margin-top:12px}
</style>
</head>
<body>
<h2>Smart Street Light Control</h2>

<div>
  <a href="/on"><button>ON</button></a>
  <a href="/off"><button>OFF</button></a>
  <a href="/auto"><button>AUTO</button></a>
</div>

<div class="box">
  <form action="/bright" method="GET">
    <label>Brightness (0-255):</label><br><br>
    <input name="v" type="number" min="0" max="255" value="220">
    <button type="submit">Set Brightness</button>
  </form>
</div>

<div class="box">
  <form action="/threshold" method="GET">
    <label>LDR Threshold (0-1023):</label><br><br>
    <input name="t" type="number" min="0" max="1023" value="500">
    <button type="submit">Set Threshold</button>
  </form>
</div>

<div class="box">
  <p><b>Status:</b></p>
  <a href="/status">Open /status</a>
</div>

</body></html>
)";
}

void setup() {
  Serial.begin(9600); // to UNO via wires

  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, pass);

  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
  }

  server.on("/", []() { server.send(200, "text/html", htmlPage()); });

  server.on("/on", []() { sendToUNO("ON"); server.send(200, "text/plain", "OK: ON"); });
  server.on("/off", []() { sendToUNO("OFF"); server.send(200, "text/plain", "OK: OFF"); });
  server.on("/auto", []() { sendToUNO("AUTO"); server.send(200, "text/plain", "OK: AUTO"); });

  server.on("/bright", []() {
    if (!server.hasArg("v")) return server.send(400, "text/plain", "Missing v");
    int v = constrain(server.arg("v").toInt(), 0, 255);
    sendToUNO("B:" + String(v));
    server.send(200, "text/plain", "OK: Brightness = " + String(v));
  });

  server.on("/threshold", []() {
    if (!server.hasArg("t")) return server.send(400, "text/plain", "Missing t");
    int t = constrain(server.arg("t").toInt(), 0, 1023);
    sendToUNO("T:" + String(t));
    server.send(200, "text/plain", "OK: Threshold = " + String(t));
  });

  server.on("/status", []() {
    String s = "IP: " + WiFi.localIP().toString() + "\nLast: " + lastStatus;
    server.send(200, "text/plain", s);
  });

  server.begin();
}

void loop() {
  server.handleClient();

  // Read status coming from UNO
  while (Serial.available()) {
    lastStatus = Serial.readStringUntil('\n');
  }
}