import os
from datetime import datetime
from flask import Flask, jsonify, request, render_template

app = Flask(__name__)

# Lista de mercados profesionales con opciones, pozos y fechas
eventos = [
    {
        "id": 1,
        "titulo": "¿Ganará el equipo local el próximo partido?",
        "fecha_inicio": "2026-06-01T00:00",
        "fecha_cierre": "2026-06-15T23:59",
        "estado": "activo", 
        "opciones": [
            {"id": 0, "nombre": "Sí", "pozo": 50.0},
            {"id": 1, "nombre": "No", "pozo": 50.0}
        ],
        "pozo_total": 100.0,
        "comision_casa": 2.0,
        "participantes": []
    }
]

@app.route('/')
def index():
    try:
        return render_template('index.html')
    except Exception:
        return "¡P2Ppredict Backend con Dividendos y Fechas Funcionando! 🔮"

@app.route('/validation-key.txt')
def validation_key():
    try:
        return app.send_static_file('validation-key.txt')
    except Exception:
        return "332ef1d8b17e8789cb1385717cceaecf6eb79"

@app.route('/api/eventos', methods=['GET'])
def obtener_eventos():
    # Actualizar estados automáticamente según la fecha actual
    ahora = datetime.now()
    for ev in eventos:
        try:
            cierre = datetime.strptime(ev["fecha_cierre"], "%Y-%m-%dT%H:%M")
            if ahora > cierre and ev["estado"] == "activo":
                ev["estado"] = "cerrado"
        except Exception:
            pass
    return jsonify(eventos)

@app.route('/api/crear-evento', methods=['POST'])
def crear_evento():
    data = request.json or {}
    titulo = data.get('titulo')
    opcion1 = data.get('opcion1', 'Sí')
    opcion2 = data.get('opcion2', 'No')
    fecha_inicio = data.get('fecha_inicio', datetime.now().strftime("%Y-%m-%dT%H:%M"))
    fecha_cierre = data.get('fecha_cierre')
    
    if not titulo or not fecha_cierre:
        return jsonify({"success": False, "error": "El título y la fecha de cierre son obligatorios"}), 400
    
    nuevo_evento = {
        "id": len(eventos) + 1,
        "titulo": titulo,
        "fecha_inicio": fecha_inicio,
        "fecha_cierre": fecha_cierre,
        "estado": "activo",
        "opciones": [
            {"id": 0, "nombre": opcion1, "pozo": 0.0},
            {"id": 1, "nombre": opcion2, "pozo": 0.0}
        ],
        "pozo_total": 0.0,
        "comision_casa": 0.0,
        "participantes": []
    }
    eventos.append(nuevo_evento)
    return jsonify({"success": True, "mensaje": "Mercado creado con éxito", "evento": nuevo_evento})

@app.route('/api/participar', methods=['POST'])
def participar():
    data = request.json or {}
    evento_id = int(data.get('evento_id', 1))
    opcion_id = int(data.get('opcion_id', 0))
    monto_pagado = float(data.get('monto', 1.0))
    usuario = data.get('username', 'Pionero')
    
    evento = next((ev for ev in eventos if ev["id"] == evento_id), None)
    if not evento:
        return jsonify({"success": False, "error": "Mercado no encontrado"}), 404
        
    # Verificar si el mercado ya cerró por fecha
    ahora = datetime.now()
    try:
        cierre = datetime.strptime(evento["fecha_cierre"], "%Y-%m-%dT%H:%M")
        if ahora > cierre:
            evento["estado"] = "cerrado"
            return jsonify({"success": False, "error": "Este mercado ya ha caducado y no acepta más apuestas."}), 400
    except Exception:
        pass

    if evento["estado"] != "activo":
        return jsonify({"success": False, "error": "El mercado no está activo."}), 400

    opcion = next((op for op in evento["opciones"] if op["id"] == opcion_id), None)
    if not opcion:
        return jsonify({"success": False, "error": "Opción inválida"}), 404

    # Retención automática del 2% de comisión para la casa
    comision = monto_pagado * 0.02
    monto_para_pozo = monto_pagado * 0.98

    evento["comision_casa"] += comision
    evento["pozo_total"] += monto_pagado
    opcion["pozo"] += monto_para_pozo
    
    evento["participantes"].append({
        "usuario": usuario,
        "opcion": opcion["nombre"],
        "monto": monto_pagado
    })
    
    return jsonify({
        "success": True,
        "mensaje": f"¡Apuesta registrada en '{opcion['nombre']}'!",
        "evento": evento
    })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
