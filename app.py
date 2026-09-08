import os
from flask import Flask, jsonify, request, render_template

app = Flask(__name__)

# Lista de eventos activos (múltiples predicciones simultáneas)
eventos = [
    {
        "id": 1,
        "titulo": "¿Ganará el equipo local hoy?",
        "pozo_premios": 0.0,
        "comision_casa": 0.0,
        "pool_total": 0.0,
        "participantes": []
    },
    {
        "id": 2,
        "titulo": "¿Bitcoin subirá de 100k esta semana?",
        "pozo_premios": 0.0,
        "comision_casa": 0.0,
        "pool_total": 0.0,
        "participantes": []
    }
]

@app.route('/')
def index():
    try:
        return render_template('index.html')
    except Exception:
        return "¡P2Ppredict Backend Funcionando Correctamente! 🔮"

@app.route('/validation-key.txt')
def validation_key():
    try:
        return app.send_static_file('validation-key.txt')
    except Exception:
        return "332ef1d8b17e8789cb1385717cceaecf6eb79"

# 1. Obtener TODOS los eventos activos
@app.route('/api/eventos', methods=['GET'])
def obtener_eventos():
    return jsonify(eventos)

# 2. Crear un nuevo evento dinámicamente
@app.route('/api/crear-evento', methods=['POST'])
def crear_evento():
    data = request.json or {}
    nuevo_titulo = data.get('titulo')
    
    if nuevo_titulo:
        nuevo_id = len(eventos) + 1
        nuevo_item = {
            "id": nuevo_id,
            "titulo": nuevo_titulo,
            "pozo_premios": 0.0,
            "comision_casa": 0.0,
            "pool_total": 0.0,
            "participantes": []
        }
        eventos.append(nuevo_item)
        return jsonify({"success": True, "mensaje": "Evento creado con éxito", "evento": nuevo_item})
    
    return jsonify({"success": False, "error": "El título es obligatorio"}), 400

# 3. Participar en un evento específico por su ID (con el 2% de comisión)
@app.route('/api/participar', methods=['POST'])
def participar():
    data = request.json or {}
    evento_id = int(data.get('evento_id', 1))
    monto_pagado = float(data.get('monto', 1.0))
    usuario = data.get('username', 'Usuario Pi')
    
    # Buscar el evento en la lista
    evento_encontrado = None
    for ev in eventos:
        if ev["id"] == evento_id:
            evento_encontrado = ev
            break
            
    if not evento_encontrado:
        return jsonify({"success": False, "error": "Evento no encontrado"}), 404
    
    # Calcular 2% para ti y 98% para el pozo de ese evento
    comision = monto_pagado * 0.02
    monto_para_pozo = monto_pagado * 0.98
    
    # Actualizar los valores de ese evento particular
    evento_encontrado["comision_casa"] += comision
    evento_encontrado["pozo_premios"] += monto_para_pozo
    evento_encontrado["pool_total"] += monto_pagado
    
    evento_encontrado["participantes"].append({
        "usuario": usuario,
        "aporte": monto_pagado
    })
    
    return jsonify({
        "success": True,
        "mensaje": "¡Participación registrada con éxito!",
        "pool_actual": round(evento_encontrado["pozo_premios"], 4),
        "comision_guardada": round(evento_encontrado["comision_casa"], 4)
    })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
