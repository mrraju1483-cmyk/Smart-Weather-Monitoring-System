#include <Wire.h>
#include <DHT.h>
#include <LiquidCrystal_I2C.h>

#define DHT_PIN 4
#define DHT_TYPE DHT11
#define MQ135_PIN A0
#define RAIN_PIN A1

// Most 16x2 I2C LCD backpacks use address 0x27. Some use 0x3F.
LiquidCrystal_I2C lcd(0x27, 16, 2);
DHT dht(DHT_PIN, DHT_TYPE);

void setup() {
  Serial.begin(9600);
  dht.begin();
  lcd.init();
  lcd.backlight();
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Env Monitor");
  lcd.setCursor(0, 1);
  lcd.print("Starting...");
  delay(1200);
}

void loop() {
  float humidity = dht.readHumidity();
  float temperature = dht.readTemperature();
  int airQuality = analogRead(MQ135_PIN);
  int rainValue = analogRead(RAIN_PIN);

  lcd.clear();
  lcd.setCursor(0, 0);
  if (isnan(temperature) || isnan(humidity)) {
    lcd.print("DHT11 error");
  } else {
    lcd.print("T:");
    lcd.print(temperature, 1);
    lcd.print((char)223);
    lcd.print("C H:");
    lcd.print(humidity, 0);
    lcd.print("%");
  }
  lcd.setCursor(0, 1);
  lcd.print("A:");
  lcd.print(airQuality);
  lcd.print(" R:");
  lcd.print(rainValue);

  Serial.print("{\"temperature\":");
  if (isnan(temperature)) {
    Serial.print("null");
  } else {
    Serial.print(temperature, 1);
  }
  Serial.print(",\"humidity\":");
  if (isnan(humidity)) {
    Serial.print("null");
  } else {
    Serial.print(humidity, 1);
  }
  Serial.print(",\"air_quality\":");
  Serial.print(airQuality);
  Serial.print(",\"rain_value\":");
  Serial.print(rainValue);
  Serial.println("}");

  delay(2000);
}
