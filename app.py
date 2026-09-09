import os
from datetime import datetime
from flask import Flask, jsonify, request, render_template

app = Flask(__name__)

eventos = [
    {
        "id": 1,
        "titulo": "¿Ganará el equipo local el próximo partido?",
        "categoria": "Deportes",
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
        "ordenes_pendientes": [],     # Cola FIFO de órdenes esperando contraparte P2P
        "apuestas_emparejadas": []    # Registro de matches exitosos entre usuarios
    }
]

saldos_pendientes = {}
historial_apuestas = []

@app.route('/')
def index():
    try:
        return render_template('index.html')
    except Exception:
        return "¡P2Ppredict Admin Backend Funcionando (Con Leaderboard P2P)! 🔮"

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

# Endpoint de métricas financieras para el administrador
@app.route('/api/admin/metricas', methods=['GET'])
def admin_metricas():
    volumen_total_historico = sum(ev["pozo_total"] for ev in eventos)
    comision_total_casa = sum(ev["comision_casa"] for ev in eventos)
    poi_activos = sum(ev["pozo_total"] for ev in eventos if ev["estado"] != "resuelto")
    total_premios_pendientes = sum(saldos_pendientes.values())

    return jsonify({
        "success": True,
        "volumen_total": round(volumen_total_historico, 4),
        "comision_casa": round(comision_total_casa, 4),
        "fondos_en_juego": round(poi_activos, 4),
        "premios_por_reclamar": round(total_premios_pendientes, 4),
        "total_mercados": len(eventos)
    })

@app.route('/api/admin/pendientes', methods=['GET'])
def admin_pendientes():
    pendientes = [ev for ev in eventos if ev["estado"] != "resuelto"]
    return jsonify({"success": True, "mercados": pendientes})

@app.route('/api/saldo/<username>', methods=['GET'])
def obtener_saldo(username):
    saldo = saldos_pendientes.get(username, 0.0)
    mis_apuestas = [h for h in historial_apuestas if h["usuario"] == username]
    return jsonify({
        "success": True, 
        "username": username, 
        "saldo_disponible": round(saldo, 4),
        "historial": mis_apuestas
    })

# NUEVO ENDPOINT: Leaderboard (Ranking de Mejores Usuarios)
@app.route('/api/leaderboard', methods=['GET'])
def obtener_leaderboard():
    estadisticas_usuarios = {}

    # Procesar historial de apuestas para calcular métricas
    for h in historial_apuestas:
        usr = h["usuario"]
        if usr not in estadisticas_usuarios:
            estadisticas_usuarios[usr] = {
                "username": usr,
                "apuestas_totales": 0,
                "volumen_apostado": 0.0,
                "ganancias_netas": 0.0,
                "apuestas_ganadas": 0
            }
        estadisticas_usuarios[usr]["apuestas_totales"] += 1
        estadisticas_usuarios[usr]["volumen_apostado"] += h["monto"]

    # Calcular ganancias reales basadas en mercados resueltos y emparejamientos
    for ev in eventos:
        if ev["estado"] == "resuelto":
            ganador_id = ev["ganador_id"]
            for match in ev["apuestas_emparejadas"]:
                # Revisar usuario A
                ua = match["usuario_a"]
                if ua in estadisticas_usuarios:
                    if match["opcion_a"] == ganador_id:
                        estadisticas_usuarios[ua]["apuestas_ganadas"] += 1
                        premio = match["monto_original"] * 2
                        ganancia_neta = premio - match["monto_original"]
                        estadisticas_usuarios[ua]["ganancias_netas"] += ganancia_neta

                # Revisar usuario B
                ub = match["usuario_b"]
                if ub in estadisticas_usuarios:
                    if match["opcion_b"] == ganador_id:
                        estadisticas_usuarios[ub]["apuestas_ganadas"] += 1
                        premio = match["monto_original"] * 2
                        ganancia_neta = premio - match["monto_original"]
                        estadisticas_usuarios[ub]["ganancias_netas"] += ganancia_neta

    # Convertir a lista y ordenar por mayores ganancias netas o volumen
    ranking = list(estadisticas_usuarios.values())
    ranking.sort(key=lambda x: (x["ganancias_netas"], x["volumen_apostado"]), reverse=True)

    return jsonify({
        "success": True,
        "leaderboard": ranking[:10]  # Top 10 mejores usuarios
    })

@app.route('/api/crear-evento', methods=['POST'])
def crear_evento():
    data = request.json or {}
    titulo = data.get('titulo')
    categoria = data.get('categoria', 'General')
    opcion1 = data.get('opcion1', 'Sí')
    opcion2 = data.get('opcion2', 'No')
    fecha_inicio = data.get('fecha_inicio', datetime.now().strftime("%Y-%m-%dT%H:%M"))
    fecha_cierre = data.get('fecha_cierre')
    
    if not titulo or not fecha_cierre:
        return jsonify({"success": False, "error": "El título y la fecha de cierre son obligatorios"}), 400
    
    nuevo_evento = {
        "id": len(eventos) + 1,
        "titulo": titulo,
        "categoria": categoria,
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
        "ordenes_pendientes": [],
        "apuestas_emparejadas": []
    }
    eventos.append(nuevo_evento)
    return jsonify({"success": True, "mensaje": "Mercado P2P creado con éxito", "evento": nuevo_evento})

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

    # REGLA: Evitar duplicar orden activa en el mismo bando por el mismo usuario
    for orden in evento["ordenes_pendientes"]:
        if orden["usuario"] == usuario and orden["opcion_id"] == opcion_id:
            return jsonify({
                "success": False, 
                "error": "Ya tienes una orden activa en esta misma opción. Si deseas apostar más, crea tu propia predicción o espera a que tu orden actual sea tomada."
            }), 400

    comision = monto_pagado * 0.02
    monto_neto = monto_pagado * 0.98
    
    evento["comision_casa"] += comision
    evento["pozo_total"] += monto_pagado
    opcion["pozo"] += monto_neto

    monto_restante = monto_neto

    # Buscar contrapartes en la cola (FIFO)
    ordenes_contrarias = [o for o in evento["ordenes_pendientes"] if o["opcion_id"] != opcion_id]

    for orden_c in ordenes_contrarias:
        if monto_restante <= 0:
            break
        
        necesario = orden_c["monto_disponible"]
        
        if monto_restante >= necesario:
            monto_match = necesario
            monto_restante -= necesario
            evento["ordenes_pendientes"].remove(orden_c)
        else:
            monto_match = monto_restante
            orden_c["monto_disponible"] -= monto_restante
            monto_restante = 0.0

        # Registrar match exitoso P2P
        evento["apuestas_emparejadas"].append({
            "usuario_a": orden_c["usuario"],
            "usuario_b": usuario,
            "opcion_a": orden_c["opcion_id"],
            "opcion_b": opcion_id,
            "monto_original": monto_match,
            "premio_potencial": monto_match * 2
        })

    # Si sobra monto neto sin contraparte, se queda en la cola
    if monto_restante > 0:
        evento["ordenes_pendientes"].append({
            "usuario": usuario,
            "opcion_id": opcion_id,
            "monto_disponible": monto_restante,
            "monto_original": monto_restante,
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M")
        })

    estado_apuesta = "Emparejado" if monto_restante == 0 else "Parcial / En Cola"
    historial_apuestas.append({
        "evento_id": evento_id,
        "titulo_evento": evento["titulo"],
        "usuario": usuario,
        "opcion_elegida": opcion["nombre"],
        "monto": monto_pagado,
        "estado": estado_apuesta,
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M")
    })
    
    mensaje_resp = f"¡Apuesta registrada en '{opcion['nombre']}' y emparejada con éxito!" if monto_restante == 0 else f"¡Apuesta registrada! Parte de tu monto quedó en cola esperando contraparte."
    return jsonify({"success": True, "mensaje": mensaje_resp})

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
    
    # 1. LIQUIDACIÓN DE EMPAREJAMIENTOS P2P: Solo ganan los que hicieron match real
    for match in evento["apuestas_emparejadas"]:
        if match["opcion_a"] == ganador_id:
            ganador = match["usuario_a"]
            premio = match["monto_original"] * 2
            saldos_pendientes[ganador] = saldos_pendientes.get(ganador, 0.0) + premio
        elif match["opcion_b"] == ganador_id:
            ganador = match["usuario_b"]
            premio = match["monto_original"] * 2
            saldos_pendientes[ganador] = saldos_pendientes.get(ganador, 0.0) + premio

    # 2. REEMBOLSO AUTOMÁTICO: Las órdenes netas que se quedaron en la cola sin contraparte se devuelven
    for orden_q in evento["ordenes_pendientes"]:
        usuario_q = orden_q["usuario"]
        reintegro = orden_q["monto_disponible"]
        saldos_pendientes[usuario_q] = saldos_pendientes.get(usuario_q, 0.0) + reintegro

    return jsonify({
        "success": True,
        "mensaje": f"¡Mercado resuelto! Ganó: {opcion_ganadora['nombre']}. Premios acreditados a emparejamientos y fondos en cola devueltos."
    })

@app.route('/api/reclamar', methods=['POST'])
def reclamar_premio():
    data = request.json or {}
    usuario = data.get('username', 'Pionero')
    
    saldo_actual = saldos_pendientes.get(usuario, 0.0)
    if saldo_actual <= 0:
        return jsonify({"success": False, "error": "No tienes saldo disponible para reclamar."}), 400
    
    saldos_pendientes[usuario] = 0.0
    return jsonify({"success": True, "mensaje": f"¡Reclamo exitoso! Se han transferido {round(saldo_actual, 4)} Pi."})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
