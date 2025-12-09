import os
from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Configuração via variáveis de ambiente (prioriza env over hardcoded)
NOCODB_URL = os.getenv("NOCODB_URL", "http://nocodb:8080")
API_TOKEN = os.getenv("NOCODB_TOKEN", os.getenv("API_TOKEN", "oq5N9NzQUPSefhQeB6Bhv1mEX5bVMqpLO4nLTQfT"))
TABLE_ID = os.getenv("NOCODB_TABLE_ID", os.getenv("TABLE_ID", "m078xv9skbc4tmu"))

# ESP32 Configuration
ESP32_IP = os.getenv("ESP32_IP", "192.168.15.50")

HEADERS = {"Content-Type": "application/json"}
if API_TOKEN:
    HEADERS["xc-token"] = API_TOKEN

# Variável global para armazenar última temperatura recebida do ESP32
latest_temperature_data = {
    "temperature": 0,
    "target": 90.0,
    "ssr_state": False,
    "status": "waiting",
    "timestamp": None,
    "online": False
}

def get_last_extraction(barista, cafe, moedor):
    """Busca a última extração de um barista específico com um café específico"""
    try:
        # Buscar todos os registros e filtrar em Python (mais simples e confiável)
        url = f"{NOCODB_URL}/api/v2/tables/{TABLE_ID}/records"
        
        print(f"Buscando: Barista={barista}, Café={cafe}, Moedor={moedor}")
        
        params = {
            "limit": 1000,
            "sort": "-Data"
        }
        
        response = requests.get(url, headers=HEADERS, params=params)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            records = data.get("list", [])
            
            print(f"Total de registros: {len(records)}")
            
            # Filtrar manualmente
            matching_records = [
                r for r in records
                if r.get('Barista') == barista 
                and r.get('Café') == cafe 
                and r.get('Moedor') == moedor
            ]
            
            print(f"Registros correspondentes: {len(matching_records)}")
            
            if matching_records:
                print(f"✅ Encontrado registro mais recente")
                return matching_records[0]
            else:
                print("❌ Nenhum registro encontrado")
                
        return None
    except Exception as e:
        print(f"Erro ao buscar última extração: {e}")
        import traceback
        traceback.print_exc()
        return None

def calculate_recommendation(last_extraction, moedor):
    """Calcula recomendação baseada na última extração"""
    
    # Setup padrão se não houver histórico
    default_setup = {
        "3Bomber R3 (Manual)": {
            "regulagem": 45,  # Meio da faixa 35-60 para pressurizado
            "tempo": 26,
            "temperatura_target": 90.0,
            "explicacao": "Setup inicial recomendado para cesto pressurizado"
        },
        "Hamilton Beach Plus (Automático)": {
            "regulagem": 8,  # Ajustar conforme seu moedor
            "tempo": 25,
            "temperatura_target": 90.0,
            "explicacao": "Setup inicial padrão"
        }
    }
    
    # Se não houver histórico, retorna setup padrão
    if not last_extraction:
        return default_setup.get(moedor, default_setup["3Bomber R3 (Manual)"])
    
    # Extrair dados da última extração
    regulagem_atual = last_extraction.get("Regulagem", 45)
    tempo_atual = last_extraction.get("Tempo", 26)
    temperatura_atual = last_extraction.get("Temperatura", 90.0)
    sabor = last_extraction.get("Sabor", "")
    nota = last_extraction.get("Nota", 0)
    
    # Inicializar recomendação
    nova_regulagem = regulagem_atual
    novo_tempo = tempo_atual
    nova_temperatura = temperatura_atual if temperatura_atual else 90.0
    explicacao = ""
    
    # Se a nota foi boa (>= 7) e equilibrado, mantém setup
    if nota >= 7 and sabor == "Equilibrado":
        explicacao = f"Última extração foi excelente (nota {nota})! Mantenha o mesmo setup."
        return {
            "regulagem": regulagem_atual,
            "tempo": tempo_atual,
            "temperatura_target": float(nova_temperatura),
            "explicacao": explicacao,
            "ultima_nota": nota
        }
    
    # Ajustes baseados no sabor
    if sabor == "Amargo":
        # Moagem mais grossa (número maior) e menos tempo
        # Reduzir temperatura para menos amargor
        nova_regulagem = regulagem_atual + 5
        novo_tempo = max(20, tempo_atual - 3)
        nova_temperatura = max(88.0, nova_temperatura - 1.5)
        explicacao = "Última extração estava amarga. Vamos usar moagem mais grossa, menos tempo e temperatura mais baixa."
    
    elif sabor == "Aguado":
        # Moagem mais fina (número menor) e mais tempo
        # Aumentar temperatura para melhor extração
        nova_regulagem = regulagem_atual - 4
        novo_tempo = tempo_atual + 4
        nova_temperatura = min(95.0, nova_temperatura + 1.0)
        explicacao = "Última extração estava aguada. Vamos usar moagem mais fina, mais tempo e temperatura mais alta."
    
    elif sabor == "Ácido":
        # Leve ajuste na moagem e mais tempo
        # Aumentar temperatura para equilibrar acidez
        nova_regulagem = regulagem_atual + 2
        novo_tempo = tempo_atual + 3
        nova_temperatura = min(95.0, nova_temperatura + 1.5)
        explicacao = "Última extração estava ácida. Vamos extrair mais tempo com temperatura mais alta para equilibrar."
    
    elif nota < 6:
        # Se nota baixa mas sem feedback específico
        nova_regulagem = regulagem_atual + 3
        novo_tempo = tempo_atual + 2
        nova_temperatura = min(94.0, nova_temperatura + 0.5)
        explicacao = f"Última nota foi {nota}/10. Vamos ajustar levemente o setup."
    
    # Limites de segurança para 3Bomber R3 com cesto pressurizado
    if moedor == "3Bomber R3 (Manual)":
        nova_regulagem = max(35, min(60, nova_regulagem))
    
    # Limites de tempo
    novo_tempo = max(20, min(35, novo_tempo))
    
    # Limites de temperatura (88°C a 95°C)
    nova_temperatura = max(88.0, min(95.0, nova_temperatura))
    
    return {
        "regulagem": int(nova_regulagem),
        "tempo": int(novo_tempo) if tempo_atual else None,
        "temperatura_target": float(nova_temperatura),
        "explicacao": explicacao,
        "ultima_nota": nota,
        "ultima_regulagem": regulagem_atual,
        "ultimo_tempo": tempo_atual if tempo_atual else "Não registrado",
        "ultima_temperatura": temperatura_atual if temperatura_atual else "Não registrado"
    }

@app.route('/api/recommendation', methods=['POST'])
def get_recommendation():
    """Endpoint para obter recomendação de setup"""
    try:
        data = request.json
        barista = data.get('barista')
        cafe = data.get('cafe')
        moedor = data.get('moedor')
        
        if not all([barista, cafe, moedor]):
            return jsonify({
                "error": "Barista, café e moedor são obrigatórios"
            }), 400
        
        # Buscar última extração
        last_extraction = get_last_extraction(barista, cafe, moedor)
        
        # Calcular recomendação
        recommendation = calculate_recommendation(last_extraction, moedor)
        
        return jsonify({
            "success": True,
            "barista": barista,
            "cafe": cafe,
            "moedor": moedor,
            "tem_historico": last_extraction is not None,
            "recomendacao": recommendation
        })
    
    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500

@app.route('/api/save_extraction', methods=['POST'])
def save_extraction():
    """Salvar dados de extração no NocoDB"""
    try:
        data = request.json
        print(f"\n💾 RECEBENDO DADOS PARA SALVAR:")
        print(f"   Dados recebidos: {data}")
        
        # Validar dados obrigatórios
        required_fields = ['Barista', 'Café', 'Moedor', 'Regulagem', 'Tempo', 'Sabor', 'Nota']
        for field in required_fields:
            if field not in data:
                print(f"   ❌ Campo faltando: {field}")
                return jsonify({"error": f"Campo obrigatório: {field}"}), 400
        
        # Preparar dados para NocoDB
        extraction_data = {
            "Data": datetime.now().isoformat(),
            "Barista": data['Barista'],
            "Café": data['Café'],
            "Moedor": data['Moedor'],
            "Regulagem": data['Regulagem'],
            "Dose_In": 10,  # Fixo
            "Massa_Out": 30,  # Fixo
            "Tempo": data['Tempo'],
            "Temperatura": data.get('Temperatura'),  # Opcional
            "Sabor": data['Sabor'],
            "Nota": data['Nota'],
            "Observação": data.get('Observação', '')
        }
        
        print(f"   Dados preparados para NocoDB: {extraction_data}")
        
        # Salvar no NocoDB
        url = f"{NOCODB_URL}/api/v2/tables/{TABLE_ID}/records"
        print(f"   URL NocoDB: {url}")
        print(f"   Table ID: {TABLE_ID}")
        
        response = requests.post(url, headers=HEADERS, json=extraction_data)
        print(f"   Status Code NocoDB: {response.status_code}")
        print(f"   Resposta NocoDB: {response.text[:200]}...")
        
        if response.status_code == 200:
            print(f"   ✅ Extração salva com sucesso!")
            return jsonify({
                "success": True,
                "message": "Extração salva com sucesso",
                "data": response.json()
            })
        else:
            print(f"   ❌ Erro ao salvar no NocoDB")
            return jsonify({
                "success": False,
                "error": "Erro ao salvar no NocoDB",
                "details": response.text
            }), 500
            
    except Exception as e:
        print(f"❌ Erro ao salvar extração: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Endpoint para verificar se a API está funcionando"""
    return jsonify({
        "status": "online",
        "timestamp": datetime.now().isoformat()
    })

# ========================================
# ENDPOINTS DE TEMPERATURA
# ========================================

@app.route('/api/temperature', methods=['POST'])
def receive_temperature():
    """Receber dados de temperatura do ESP32 (OPCIONAL - ESP32 pode enviar)"""
    global latest_temperature_data
    
    try:
        data = request.json
        
        # Atualizar dados globais
        latest_temperature_data = {
            "temperature": data.get('temperature', 0),
            "target": data.get('target', 90.0),
            "ssr_state": data.get('ssr_state', False),
            "status": data.get('status', 'normal'),
            "timestamp": datetime.now().isoformat(),
            "online": True
        }
        
        print(f"📡 Temp recebida do ESP32: {latest_temperature_data['temperature']}°C | SSR: {'ON' if latest_temperature_data['ssr_state'] else 'OFF'}")
        
        return jsonify({
            "success": True,
            "message": "Dados recebidos"
        })
        
    except Exception as e:
        print(f"Erro ao receber temperatura: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/temperature/status', methods=['GET'])
def get_temperature_status():
    """Interface consulta temperatura - PROXY para ESP32"""
    try:
        # Consultar ESP32 diretamente!
        response = requests.get(f"http://{ESP32_IP}/api/temperature", timeout=2)
        
        if response.status_code == 200:
            data = response.json()
            
            # Atualizar cache local
            latest_temperature_data.update({
                "temperature": data.get('temperature', 0),
                "target": data.get('target', 90.0),
                "ssr_state": data.get('ssr_state', False),
                "status": data.get('status', 'normal'),
                "timestamp": datetime.now().isoformat(),
                "online": True
            })
            
            return jsonify(latest_temperature_data)
        else:
            # ESP32 offline
            return jsonify({
                "temperature": 0,
                "target": 90.0,
                "ssr_state": False,
                "status": "esp32_offline",
                "timestamp": datetime.now().isoformat(),
                "online": False
            })
            
    except Exception as e:
        print(f"Erro ao consultar ESP32: {e}")
        # Retornar dados em cache ou offline
        return jsonify({
            "temperature": latest_temperature_data.get('temperature', 0),
            "target": 90.0,
            "ssr_state": False,
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "online": False,
            "error": str(e)
        })

@app.route('/api/temperature/set', methods=['POST'])
def set_temperature_target():
    """Enviar temperatura target personalizada para o ESP32"""
    try:
        data = request.json
        target_temp = data.get('target')
        
        if not target_temp:
            return jsonify({"error": "Missing 'target' parameter"}), 400
        
        # Validar limites
        if target_temp < 88.0 or target_temp > 95.0:
            return jsonify({"error": "Temperature must be between 88°C and 95°C"}), 400
        
        # Enviar para ESP32
        response = requests.post(
            f"http://{ESP32_IP}/api/temperature/set",
            json={"target": target_temp},
            timeout=5
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"🎯 Temperatura target enviada ao ESP32: {target_temp}°C")
            return jsonify({
                "success": True,
                "target": target_temp,
                "esp32_response": result
            })
        else:
            return jsonify({
                "success": False,
                "error": "ESP32 rejected temperature",
                "details": response.text
            }), 500
            
    except requests.exceptions.RequestException as e:
        print(f"Erro ao enviar temperatura ao ESP32: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to communicate with ESP32",
            "details": str(e)
        }), 500
    except Exception as e:
        print(f"Erro ao processar temperatura: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Allow enabling debug via FLASK_DEBUG env var (useful for local dev)
    debug = os.getenv("FLASK_DEBUG", "False").lower() in ("1", "true", "yes")
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=debug)