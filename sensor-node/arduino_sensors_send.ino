#include <OneWire.h>
#include <DallasTemperature.h>

#define ONE_WIRE_BUS 2

OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

const int condPin = A0;
float knownResistor = 1500.0;

const int phPin = A1;

float intercept = 21.34;
float slope = -5.70;

void setup() {
  Serial.begin(9600);
  sensors.begin();
}

void loop() {
  if (Serial.available() > 0) {
    char incomingCommand = Serial.read();

    if (incomingCommand == 'R') {
      sensors.requestTemperatures();
      float temp = sensors.getTempCByIndex(0);
      float condValue = getConductivity(condPin, knownResistor);
      float phValue = getPH(phPin);

      Serial.print(condValue);
      Serial.print(",");
      Serial.print(phValue);
      Serial.print(",");
      Serial.println((int)temp);
    }
  }

  delay(2000);
}

float getConductivity(int pin, float resistor) {
  int rawValue = analogRead(pin);
  if (rawValue == 0) return 0.0;
  if (rawValue >= 1023) return -1.0;

  float voltage = rawValue * (5.0 / 1024.0);
  float waterResistance = resistor * ((5.0 / voltage) - 1.0);
  float conductivity = 1000000.0 / waterResistance;

  return conductivity;
}

float getPH(int pin) {
  int totalRaw = 0;
  for (int i = 0; i < 10; i++) {
    totalRaw += analogRead(pin);
    delay(10);
  }
  float avgRawValue = totalRaw / 10.0;
  float voltage = avgRawValue * (5.0 / 1024.0);
  float phValue = (slope * voltage) + intercept;

  return phValue;
}
