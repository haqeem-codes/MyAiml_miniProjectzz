
const int LDR_PIN = A0;
const int PIR_PIN = 2;
const int LIGHT_PWM = 5;

enum Mode { MODE_AUTO, MODE_ON, MODE_OFF };
Mode mode = MODE_AUTO;

int brightness = 200;          
int ldrThreshold = 500;        
unsigned long motionHoldMs = 15000; 
unsigned long lastMotionTime = 0;

String cmd = "";

void setup() {
  pinMode(PIR_PIN, INPUT);
  pinMode(LIGHT_PWM, OUTPUT);

  Serial.begin(9600); 
  analogWrite(LIGHT_PWM, 0);
}

void handleSerial() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n') {
      cmd.trim();

      if (cmd == "ON") mode = MODE_ON;
      else if (cmd == "OFF") mode = MODE_OFF;
      else if (cmd == "AUTO") mode = MODE_AUTO;
      else if (cmd.startsWith("B:")) {
        int val = cmd.substring(2).toInt();
        if (val < 0) val = 0;
        if (val > 255) val = 255;
        brightness = val;
      }
      cmd = "";
    } else {
      cmd += c;
    }
  }
}

void setLight(int pwm) {
  if (pwm < 0) pwm = 0;
  if (pwm > 255) pwm = 255;
  analogWrite(LIGHT_PWM, pwm);
}

void loop() {
  handleSerial();

  int ldrValue = analogRead(LDR_PIN);      // 0..1023
  int motion = digitalRead(PIR_PIN);       // 0/1

  if (motion == HIGH) lastMotionTime = millis();

  if (mode == MODE_ON) {
    setLight(brightness);
  }
  else if (mode == MODE_OFF) {
    setLight(0);
  }
  else { // MODE_AUTO
    bool isNight = (ldrValue < ldrThreshold);
    bool recentlyMotion = (millis() - lastMotionTime) < motionHoldMs;

    if (isNight) {
      // At night: dim if no motion, bright if motion
      if (recentlyMotion) setLight(brightness);
      else setLight(brightness / 4); // dim mode
    } else {
      // Daytime: off
      setLight(0);
    }
  }

  // Optional: send status to ESP every 1s (simple)
  static unsigned long t = 0;
  if (millis() - t > 1000) {
    t = millis();
    Serial.print("LDR:");
    Serial.print(ldrValue);
    Serial.print(",PIR:");
    Serial.print(motion);
    Serial.print(",MODE:");
    Serial.print((int)mode);
    Serial.print(",B:");
    Serial.println(brightness);
  }

  delay(50);
}