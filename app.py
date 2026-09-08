import os
from datetime import datetime
from flask import Flask, jsonify, request, render_template

app = Flask(__name__)

# Lista de mercados profesionales con opciones, pozos, fechas y ganadores
eventos = [
    {
        "id": 1,
        "titulo": "¿Ganará el equipo local el próximo partido?",
        "fecha_inicio": "2026-06-01T00:00",
        "fecha_cierre": "2026-06-15T23:59",
        "estado": "activo", # activo, cerrado, resuelto
        "ganador_id": None,
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
        return "¡P2Ppredict Backend con Resolución Funcionando! 🔮"

@app.route('/validation-key.txt')
def validation_key():
    try:
        return app.send_static_file('validation-key.txt')
    except Exception:
        return "332ef1d8b17e8789cb1385717cceaecf6eb79"

@app.route('/api/eventos', methods=['GET'])
def obtener_eventos():
    ahora = datetime.now()
    for ev in eventos:
        if ev["estado"] == "activo":
            try:
                cierre = datetime.strptime(ev["fecha_cierre"], "%Y-%m-%dT%H:%M")
                if ahora > cierre:
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
        "ganador_id": None,
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
        
    if evento["estado"] != "activo":
        return jsonify({"success": False, "error": "El mercado ya está cerrado o resuelto."}), 400

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
        "opcion_id": opcion_id,
        "monto": monto_pagado
    })
    
    return jsonify({"success": True, "mensaje": f"¡Apuesta registrada en '{opcion['nombre']}'!"})

# Ruta para resolver el mercado y calcular los pagos a los ganadores
@app.route('/api/resolver', methods=['POST'])
def resolver_evento():
    data = request.json or {}
    evento_id = int(data.get('evento_id', 0))
    ganador_id = int(data.get('ganador_id', 0))
    
    evento = next((ev for ev in eventos if ev["id"] == evento_id), None)
    if not evento:
        return jsonify({"success": False, "error": "Mercado no encontrado"}), 404
        
    if evento["estado"] == "resuelto":
        return jsonify({"success": False, "error": "Este mercado ya fue resuelto."}), 400

    opcion_ganadora = next((op for op in evento["opciones"] if op["id"] == ganador_id), None)
    if not opcion_ganadora:
        return jsonify({"success": False, "error": "Opción ganadora inválida"}), 404

    evento["estado"] = "resuelto"
    evento["ganador_id"] = ganador_id
    
    # Calcular distribución de premios
    pozo_a_repartir = sum(op["pozo"] for op in evento["opciones"]) # Esto ya descuenta la comisión acumulada en `comision_casa`
    pozo_ganador = opcion_ganadora["pozo"]
    
    resultados_pagos = []
    
    if pozo_ganador > 0:
        for p in evento["participantes"]:
            if p["opcion_id"] == ganador_id:
                # Proporción que le toca a cada ganador según su aporte
                proporcion = p["monto"] / pozo_ganador
                premio = proporcion * pozo_a_repartir
                resultados_pagos.append({
                    "usuario": p["usuario"],
                    "premio_a_pagar": round(premio, 4)
                })
    else:
        resultados_pagos.append({"mensaje": "Nadie apostó por la opción ganadora. El pozo pasa a la casa."})

    return jsonify({
        "success": True,
        "mensaje": f"¡Mercado resuelto! Ganó: {opcion_ganadora['nombre']}",
        "pagos": resultados_pagos,
        "comision_retenida_casa": round(evento["comision_casa"], 4)
    })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
