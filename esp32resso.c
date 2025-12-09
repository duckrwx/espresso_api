/*
 * ESPRESSO VILARINS v3.5 - FINAL
 * ESP32 como servidor (interface consulta diretamente)
 * Sem dependência do Flask!
 */

#include <WiFi.h>
#include <WebServer.h>
#include <max6675.h>
#include <ArduinoJson.h>

// ========================================
// CONFIGURAÇÃO WIFI
// ========================================
const char* ssid = "VIVOFIBRA-WIFI6-1EF1";
const char* password = "FEb7v74RCawtxXC";

// IP Fixo ESP32
IPAddress local_IP(192, 168, 15, 50);
IPAddress gateway(192, 168, 15, 1);
IPAddress subnet(255, 255, 255, 0);

// ========================================
// HARDWARE
// ========================================
// MAX6675
const int thermoCLK = 18;
const int thermoCS = 5;
const int thermoDO = 19;

// SSR
const int SSR_PIN = 22;

// LED Status
const int LED_PIN = 2;

// ========================================
// CONTROLE TEMPERATURA
// ========================================
const float TARGET_TEMP = 93.0;
const float HYSTERESIS = 2.0;
const float TEMP_MAX = 105.0;

// ========================================
// OBJETOS
// ========================================
MAX6675 thermocouple(thermoCLK, thermoCS, thermoDO);
WebServer server(80);

// ========================================
// VARIÁVEIS
// ========================================
float currentTemp = 0;
bool ssrState = false;
String deviceStatus = "initializing";
unsigned long lastTempRead = 0;

// ========================================
// FUNÇÕES AUXILIARES
// ========================================

void sendCORS() {
    server.sendHeader("Access-Control-Allow-Origin", "*");
    server.sendHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
    server.sendHeader("Access-Control-Allow-Headers", "Content-Type");
}

void blinkLED(int times) {
    for (int i = 0; i < times; i++) {
        digitalWrite(LED_PIN, HIGH);
        delay(100);
        digitalWrite(LED_PIN, LOW);
        delay(100);
    }
}

// ========================================
// WIFI
// ========================================

void connectWiFi() {
    Serial.println("\n[WiFi] Configurando IP fixo...");
    
    if (!WiFi.config(local_IP, gateway, subnet)) {
        Serial.println("[WiFi] Erro ao configurar IP fixo!");
    }
    
    WiFi.begin(ssid, password);
    
    int attempts = 0;
    Serial.print("[WiFi] Conectando");
    while (WiFi.status() != WL_CONNECTED && attempts < 30) {
        delay(500);
        Serial.print(".");
        attempts++;
    }
    
    if (WiFi.status() == WL_CONNECTED) {
        Serial.println(" ✅");
        Serial.print("[WiFi] IP: ");
        Serial.println(WiFi.localIP());
        blinkLED(3);
    } else {
        Serial.println(" ❌");
        Serial.println("[WiFi] Falhou (funcionando offline)");
    }
}

// ========================================
// TEMPERATURA
// ========================================

void readTemperature() {
    currentTemp = thermocouple.readCelsius();
    
    if (isnan(currentTemp) || currentTemp < 0) {
        Serial.println("❌ Erro: Termopar desconectado!");
        currentTemp = -1;
        digitalWrite(SSR_PIN, LOW);
        ssrState = false;
        deviceStatus = "error_sensor";
        return;
    }
    
    if (currentTemp > TEMP_MAX) {
        Serial.println("🚨 ALERTA: Temperatura muito alta!");
        digitalWrite(SSR_PIN, LOW);
        ssrState = false;
        deviceStatus = "overheat";
        return;
    }
    
    deviceStatus = "normal";
}

void controlSSR() {
    if (currentTemp < 0) return;
    
    if (currentTemp < (TARGET_TEMP - HYSTERESIS)) {
        if (!ssrState) {
            digitalWrite(SSR_PIN, HIGH);
            ssrState = true;
            Serial.println("🔥 SSR LIGADO");
        }
    } 
    else if (currentTemp > (TARGET_TEMP + HYSTERESIS)) {
        if (ssrState) {
            digitalWrite(SSR_PIN, LOW);
            ssrState = false;
            Serial.println("❄️  SSR DESLIGADO");
        }
    }
}

void printStatus() {
    Serial.print("🌡️  ");
    Serial.print(currentTemp, 1);
    Serial.print("°C | Alvo: ");
    Serial.print(TARGET_TEMP, 1);
    Serial.print("°C | SSR: ");
    Serial.print(ssrState ? "🔥 ON " : "❄️  OFF");
    Serial.print(" | Δ: ");
    Serial.print(currentTemp - TARGET_TEMP, 1);
    Serial.println("°C");
}

// ========================================
// SERVIDOR WEB
// ========================================

void setupWebServer() {
    
    // Página principal
    server.on("/", HTTP_GET, []() {
        sendCORS();
        String html = "<!DOCTYPE html><html><head>";
        html += "<meta charset='UTF-8'>";
        html += "<meta name='viewport' content='width=device-width, initial-scale=1.0'>";
        html += "<title>Espresso Vilarins</title>";
        html += "<style>";
        html += "body{font-family:Arial;margin:20px;background:#1a1a2e;color:#eee;}";
        html += "h1{color:#16c79a;}";
        html += ".card{background:#16213e;padding:20px;border-radius:10px;margin:10px 0;}";
        html += ".temp{font-size:48px;font-weight:bold;color:#16c79a;}";
        html += ".status{font-size:24px;margin:10px 0;}";
        html += "</style></head><body>";
        html += "<h1>🌡️ Espresso Vilarins - Temperatura</h1>";
        html += "<div class='card'>";
        html += "<div class='status'>Status: " + deviceStatus + "</div>";
        html += "<div class='temp'>" + String(currentTemp, 1) + "°C</div>";
        html += "<div>Alvo: " + String(TARGET_TEMP, 1) + "°C</div>";
        html += "<div>SSR: " + String(ssrState ? "🔥 AQUECENDO" : "❄️ ESTÁVEL") + "</div>";
        html += "</div>";
        html += "<div class='card'>";
        html += "<h3>API Endpoints:</h3>";
        html += "<ul>";
        html += "<li>GET <a href='/api/status' style='color:#16c79a'>/api/status</a></li>";
        html += "<li>GET <a href='/api/temperature' style='color:#16c79a'>/api/temperature</a></li>";
        html += "</ul></div>";
        html += "<script>setInterval(()=>location.reload(),5000);</script>";
        html += "</body></html>";
        server.send(200, "text/html", html);
    });
    
    // OPTIONS (CORS preflight)
    server.on("/api/status", HTTP_OPTIONS, []() {
        sendCORS();
        server.send(204);
    });
    
    server.on("/api/temperature", HTTP_OPTIONS, []() {
        sendCORS();
        server.send(204);
    });
    
    // Status
    server.on("/api/status", HTTP_GET, []() {
        sendCORS();
        
        StaticJsonDocument<200> doc;
        doc["temperature"] = currentTemp;
        doc["target"] = TARGET_TEMP;
        doc["ssr_state"] = ssrState;
        doc["status"] = deviceStatus;
        doc["online"] = true;
        
        String response;
        serializeJson(doc, response);
        server.send(200, "application/json", response);
    });
    
    // Temperature (mesmo que status)
    server.on("/api/temperature", HTTP_GET, []() {
        sendCORS();
        
        StaticJsonDocument<200> doc;
        doc["temperature"] = currentTemp;
        doc["target"] = TARGET_TEMP;
        doc["ssr_state"] = ssrState;
        doc["status"] = deviceStatus;
        doc["online"] = true;
        
        String response;
        serializeJson(doc, response);
        server.send(200, "application/json", response);
    });
    
    server.begin();
    Serial.println("[HTTP] ✅ Servidor rodando na porta 80");
    Serial.println("[CORS] ✅ Habilitado para todas origens");
}

// ========================================
// SETUP
// ========================================

void setup() {
    Serial.begin(115200);
    delay(1000);
    
    Serial.println("\n\n========================================");
    Serial.println("  ESPRESSO VILARINS v3.5");
    Serial.println("  Controle de Temperatura");
    Serial.println("========================================\n");
    
    // Hardware
    pinMode(SSR_PIN, OUTPUT);
    pinMode(LED_PIN, OUTPUT);
    digitalWrite(SSR_PIN, LOW);
    
    delay(500);
    Serial.println("✅ MAX6675 inicializado");
    Serial.println("✅ SSR configurado (GPIO22)");
    
    // WiFi
    connectWiFi();
    
    // Servidor
    setupWebServer();
    
    Serial.println("\n========================================");
    Serial.println("✅ SISTEMA PRONTO!");
    Serial.println("========================================");
    Serial.print("\n🌐 Acesse: http://");
    Serial.println(local_IP);
    Serial.println("\n📡 Endpoints disponíveis:");
    Serial.println("   /api/status");
    Serial.println("   /api/temperature");
    Serial.println("\n========================================\n");
    
    deviceStatus = "ready";
    blinkLED(2);
}

// ========================================
// LOOP
// ========================================

void loop() {
    unsigned long now = millis();
    
    // Servidor HTTP (sempre ativo)
    server.handleClient();
    
    // Ler temperatura a cada 1 segundo
    if (now - lastTempRead >= 1000) {
        lastTempRead = now;
        readTemperature();
        controlSSR();
        printStatus();
    }
    
    delay(10);
}