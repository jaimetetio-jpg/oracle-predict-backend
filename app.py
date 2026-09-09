import os
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, render_template

app = Flask(__name__)

# Token de seguridad para las funciones de administración
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "p2ppredict_admin_secret_2026")

eventos = [
    {
        "id": 1,
        "titulo": "¿Ganará el equipo local el próximo partido?",
        "categoria": "Deportes",
        "fecha_inicio": "2026-06-01T00:00",
        "fecha_cierre": "2026-06-15T23:59",
        "estado": "activo",
        "ganador_id": None,
        "opciones": [
            {"id": 0, "nombre": "Sí", "pozo": 50.0},
            {"id": 1, "nombre": "No", "pozo": 50.0}
        ],
        "pozo_total": 100.0,
        "comision_casa": 2.0,
        "ordenes_pendientes": [],
        "apuestas_emparejadas": []
    }
]

saldos_pendientes = {}
historial_apuestas = []

def verificar_admin():
    token = request.headers.get('X-Admin-Token')
    if not token and request.is_json:
        token = (request.json or {}).get('admin_token')
    return token == ADMIN_TOKEN

@app.route('/')
def index():
    try:
        return render_template('index.html')
    except Exception:
        return "¡P2Ppredict Backend Pro (CLOB + Admin Auth) Funcionando! 🔮"

@app.route('/validation-key.txt')
def validation_key():
    try:
        return app.send_static_file('validation-key.txt')
    except Exception:
        return "332ef1d8b17e8789cb1385717cceaecf6eb79"

@app.route('/api/eventos', methods=['GET'])
def obtener_eventos():
    ahora = datetime.now()
    categoria_filtro = request.args.get('categoria')
    busqueda = request.args.get('q', '').lower()

    eventos_procesados = []
    for ev in eventos:
        if ev["estado"] == "activo":
            try:
                cierre = datetime.strptime(ev["fecha_cierre"], "%Y-%m-%dT%H:%M")
                if ahora > (cierre - timedelta(minutes=5)):
                    ev["estado"] = "cerrado"
            except Exception:
                pass
        
        if categoria_filtro and categoria_filtro != "Todos" and ev["categoria"] != categoria_filtro:
            continue
        if busqueda and busqueda not in ev["titulo"].lower():
            continue
            
        eventos_procesados.append(ev)
        
    return jsonify(eventos_procesados)

@app.route('/api/evento/<int:evento_id>/libro', methods=['GET'])
def obtener_libro_ordenes(evento_id):
    evento = next((ev for ev in eventos if ev["id"] == evento_id), None)
    if not evento:
        return jsonify({"success": False, "error": "Mercado no encontrado"}), 404
        
    return jsonify({
        "success": True,
        "evento_id": evento_id,
        "ordenes_pendientes": evento["ordenes_pendientes"],
        "apuestas_emparejadas": evento["apuestas_emparejadas"]
    })

@app.route('/api/admin/metricas', methods=['GET', 'POST'])
def admin_metricas():
    if not verificar_admin():
        return jsonify({"success": False, "error": "Acceso no autorizado. Token de administrador inválido."}), 401

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

@app.route('/api/admin/pendientes', methods=['GET', 'POST'])
def admin_pendientes():
    if not verificar_admin():
        return jsonify({"success": False, "error": "Acceso no autorizado. Token de administrador inválido."}), 401

    pendientes = [ev for ev in eventos if ev["estado"] != "resuelto"]
    return jsonify({"success": True, "mercados": pendientes})

@app.route('/api/saldo/<username>', methods=['GET'])
def obtener_saldo(username):
    saldo = saldos_pendientes.get(username, 0.0)
    mis_apuestas = [h for h in historial_apuestas if h["usuario"] == username]
    
    ordenes_activas_usuario = []
    for ev in eventos:
        for orden in ev["ordenes_pendientes"]:
            if orden["usuario"] == username:
                ordenes_activas_usuario.append({
                    "evento_id": ev["id"],
                    "titulo_evento": ev["titulo"],
                    "orden_id": orden["id"],
                    "opcion_id": orden["opcion_id"],
                    "monto_disponible": orden["monto_disponible"],
                    "fecha": orden["fecha"]
                })

    return jsonify({
        "success": True, 
        "username": username, 
        "saldo_disponible": round(saldo, 4),
        "historial": mis_apuestas,
        "ordenes_en_cola": ordenes_activas_usuario
    })

@app.route('/api/leaderboard', methods=['GET'])
def obtener_leaderboard():
    estadisticas_usuarios = {}

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

    for ev in eventos:
        if ev["estado"] == "resuelto":
            ganador_id = ev["ganador_id"]
            for match in ev["apuestas_emparejadas"]:
                monto_base = match.get("monto_maker", match.get("monto_original", 0))
                ua = match["usuario_a"]
                if ua in estadisticas_usuarios:
                    if match["opcion_a"] == ganador_id:
                        estadisticas_usuarios[ua]["apuestas_ganadas"] += 1
                        premio = monto_base * 2
                        estadisticas_usuarios[ua]["ganancias_netas"] += (premio - monto_base)

                ub = match["usuario_b"]
                if ub in estadisticas_usuarios:
                    if match["opcion_b"] == ganador_id:
                        estadisticas_usuarios[ub]["apuestas_ganadas"] += 1
                        premio = monto_base * 2
                        estadisticas_usuarios[ub]["ganancias_netas"] += (premio - monto_base)

    ranking = list(estadisticas_usuarios.values())
    ranking.sort(key=lambda x: (x["ganancias_netas"], x["volumen_apostado"]), reverse=True)

    return jsonify({
        "success": True,
        "leaderboard": ranking[:10]
    })

@app.route('/api/crear-evento', methods=['POST'])
def crear_evento():
    if not verificar_admin():
        return jsonify({"success": False, "error": "Acceso no autorizado. Token de administrador inválido."}), 401

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
        return jsonify({"success": False, "error": "El mercado ya está cerrado o en período de protección."}), 400

    opcion = next((op for op in evento["opciones"] if op["id"] == opcion_id), None)
    if not opcion:
        return jsonify({"success": False, "error": "Opción inválida"}), 404

    for orden in evento["ordenes_pendientes"]:
        if orden["usuario"] == usuario and orden["opcion_id"] == opcion_id:
            return jsonify({"success": False, "error": "Ya tienes una orden activa en esta opción."}), 400

    monto_restante = monto_pagado
    ordenes_contrarias = [o for o in evento["ordenes_pendientes"] if o["opcion_id"] != opcion_id]
    comision_total_taker = 0.0

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

        comision_match = monto_match * 0.02
        comision_total_taker += comision_match
        monto_neto_match = monto_match * 0.98

        evento["pozo_total"] += monto_match
        opcion["pozo"] += monto_neto_match

        evento["apuestas_emparejadas"].append({
            "usuario_a": orden_c["usuario"],
            "usuario_b": usuario,
            "opcion_a": orden_c["opcion_id"],
            "opcion_b": opcion_id,
            "monto_maker": monto_match,
            "monto_taker_neto": monto_neto_match,
            "premio_potencial": monto_match * 2
        })

    evento["comision_casa"] += comision_total_taker

    if monto_restante > 0:
        orden_id_generado = f"ord_{int(datetime.now().timestamp() * 1000)}"
        evento["ordenes_pendientes"].append({
            "id": orden_id_generado,
            "usuario": usuario,
            "opcion_id": opcion_id,
            "monto_disponible": monto_restante,
            "monto_original": monto_restante,
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M")
        })
        evento["pozo_total"] += monto_restante
        opcion["pozo"] += monto_restante

    estado_apuesta = "Emparejado (Taker)" if monto_restante == 0 else ("Parcial / En Cola (Maker)" if monto_restante < monto_pagado else "En Cola (Maker 0%)")
    
    historial_apuestas.append({
        "evento_id": evento_id,
        "titulo_evento": evento["titulo"],
        "usuario": usuario,
        "opcion_elegida": opcion["nombre"],
        "monto": monto_pagado,
        "estado": estado_apuesta,
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M")
    })
    
    return jsonify({"success": True, "mensaje": f"Orden procesada. Estado: {estado_apuesta}"})

@app.route('/api/orden/cancelar', methods=['POST'])
def cancelar_orden():
    data = request.json or {}
    evento_id = int(data.get('evento_id', 0))
    orden_id = data.get('orden_id')
    usuario = data.get('username')

    evento = next((ev for ev in eventos if ev["id"] == evento_id), None)
    if not evento:
        return jsonify({"success": False, "error": "Mercado no encontrado"}), 404

    orden_a_cancelar = None
    for orden in evento["ordenes_pendientes"]:
        if orden.get("id") == orden_id and orden["usuario"] == usuario:
            orden_a_cancelar = orden
            break

    if not orden_a_cancelar:
        return jsonify({"success": False, "error": "Orden no encontrada o no pertenece al usuario."}), 404

    evento["ordenes_pendientes"].remove(orden_a_cancelar)
    
    monto_a_liberar = orden_a_cancelar["monto_disponible"]
    evento["pozo_total"] -= monto_a_liberar
    for op in evento["opciones"]:
        if op["id"] == orden_a_cancelar["opcion_id"]:
            op["pozo"] -= monto_a_liberar

    saldos_pendientes[usuario] = saldos_pendientes.get(usuario, 0.0) + monto_a_liberar

    return jsonify({
        "success": True, 
        "mensaje": f"¡Orden cancelada con éxito! Se han devuelto {round(monto_a_liberar, 4)} Pi a tu saldo."
    })

@app.route('/api/resolver', methods=['POST'])
def resolver_evento():
    if not verificar_admin():
        return jsonify({"success": False, "error": "Acceso no autorizado. Token de administrador inválido."}), 401

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
    
    for match in evento["apuestas_emparejadas"]:
        monto_base = match.get("monto_maker", match.get("monto_original", 0))
        if match["opcion_a"] == ganador_id:
            ganador = match["usuario_a"]
            saldos_pendientes[ganador] = saldos_pendientes.get(ganador, 0.0) + (monto_base * 2)
        elif match["opcion_b"] == ganador_id:
            ganador = match["usuario_b"]
            saldos_pendientes[ganador] = saldos_pendientes.get(ganador, 0.0) + (monto_base * 2)

    for orden_q in evento["ordenes_pendientes"]:
        usuario_q = orden_q["usuario"]
        reintegro = orden_q["monto_disponible"]
        saldos_pendientes[usuario_q] = saldos_pendientes.get(usuario_q, 0.0) + reintegro

    return jsonify({
        "success": True,
        "mensaje": f"¡Mercado resuelto! Ganó: {opcion_ganadora['nombre']}. Premios y reembolsos al 100% acreditados."
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
