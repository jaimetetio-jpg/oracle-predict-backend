from datetime import datetime
import os
from flask import Flask, jsonify, request

app = Flask(__name__)

# CONFIGURACIÓN SEGURA DESDE EL ENTORNO DEL MÓVIL/SERVIDOR
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "MiClavePorDefecto123")
PI_API_KEY = os.environ.get("PI_API_KEY", "Key_Tu_Api_Key_De_Pi_Developer")
PI_HEADERS = {
    "Authorization": f"Key {PI_API_KEY}",
    "Content-Type": "application/json",
}

# Base de datos en memoria (Usuarios, Transacciones y Eventos Globales)
USUARIOS = {}  # username -> { saldo, historial, transacciones, ganancias_netas, apuestas_ganadas, apuestas_totales }
EVENTOS = [
    {
        "id": 1,
        "titulo": "¿Bitcoin superará los $100k este mes?",
        "categoria": "Cripto",
        "estado": "activo",
        "fecha_cierre": "2026-12-31T23:59",
        "opciones": [{"id": 101, "nombre": "Sí", "pozo": 15.0}, {"id": 102, "nombre": "No", "pozo": 10.0}],
    }
]


@app.route("/api/admin/login", methods=["POST"])
def admin_login():
  data = request.json
  if data.get("password") == ADMIN_PASSWORD:
    return jsonify({"success": True})
  return jsonify({"success": False, "error": "Contraseña de administrador inválida"}), 401


@app.route("/api/saldo/<username>", methods=["GET"])
def obtener_saldo(username):
  if username not in USUARIOS:
    USUARIOS[username] = {
        "saldo": 0.0,
        "historial": [],
        "transacciones": [],
        "ganancias_netas": 0.0,
        "apuestas_ganadas": 0,
        "apuestas_totales": 0,
    }
  u = USUARIOS[username]
  return jsonify(
      {"success": True, "saldo_disponible": u["saldo"], "historial": u["historial"], "transacciones": u["transacciones"]}
  )


@app.route("/api/pi/aprobar-pago", methods=["POST"])
def aprobar_pago_pi():
  data = request.json
  payment_id = data.get("paymentId")
  url = f"https://api.minepi.com/v2/payments/{payment_id}/approve"
  response = requests.post(url, headers=PI_HEADERS)
  if response.status_code == 200:
    return jsonify({"success": True})
  return jsonify({"success": False, "error": "No se pudo aprobar"}), 400


@app.route("/api/pi/completar-pago", methods=["POST"])
def completar_pago_pi():
  data = request.json
  payment_id = data.get("paymentId")
  txid = data.get("txid")
  username = data.get("username")
  monto = data.get("monto")

  url = f"https://api.minepi.com/v2/payments/{payment_id}/complete"
  response = requests.post(url, headers=PI_HEADERS, json={"txid": txid})

  if response.status_code == 200:
    if username not in USUARIOS:
      USUARIOS[username] = {
          "saldo": 0.0,
          "historial": [],
          "transacciones": [],
          "ganancias_netas": 0.0,
          "apuestas_ganadas": 0,
          "apuestas_totales": 0,
      }
    USUARIOS[username]["saldo"] += monto
    USUARIOS[username]["transacciones"].append(
        {"tipo": "Recarga Pi", "monto": monto, "fecha": datetime.utcnow().strftime("%Y-%m-%d %H:%M"), "txid": txid[:8] + "..."}
    )
    return jsonify({"success": True, "nuevo_saldo": USUARIOS[username]["saldo"]})
  return jsonify({"success": False, "error": "Fallo en blockchain"}), 400


@app.route("/api/eventos", methods=["GET"])
def obtener_eventos():
  eventos_ordenados = sorted(
      EVENTOS, key=lambda ev: sum(op["pozo"] for op in ev["opciones"]), reverse=True
  )
  return jsonify(eventos_ordenados)


@app.route("/api/participar", methods=["POST"])
def participar_evento():
  data = request.json
  username = data.get("username")
  evento_id = data.get("evento_id")
  opcion_id = data.get("opcion_id")
  monto = data.get("monto")

  if username not in USUARIOS or USUARIOS[username]["saldo"] < monto:
    return jsonify({"success": False, "error": "Saldo insuficiente"}), 400

  evento = next((e for e in EVENTOS if e["id"] == evento_id), None)
  if not evento or evento["estado"] != "activo":
    return jsonify({"success": False, "error": "Mercado no disponible"}), 400

  opcion = next((o for o in evento["opciones"] if o["id"] == opcion_id), None)
  if not opcion:
    return jsonify({"success": False, "error": "Opción inválida"}), 400

  USUARIOS[username]["saldo"] -= monto
  opcion["pozo"] += monto

  USUARIOS[username]["historial"].append(
      {
          "evento_id": evento_id,
          "titulo_evento": evento["titulo"],
          "opcion_id": opcion_id,
          "opcion_elegida": opcion["nombre"],
          "monto": monto,
          "estado": "Activa",
          "fecha": datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
      }
  )
  USUARIOS[username]["apuestas_totales"] += 1

  return jsonify({"success": True, "mensaje": "Apuesta registrada con éxito"})


@app.route("/api/admin/pendientes", methods=["GET"])
def obtener_pendientes_admin():
  ahora = datetime.utcnow()
  pendientes = []
  for ev in EVENTOS:
    try:
      cierre_dt = datetime.strptime(ev["fecha_cierre"], "%Y-%m-%dT%H:%M")
      if ev["estado"] == "activo" and ahora >= cierre_dt:
        pendientes.append(ev)
    except Exception:
      if ev["estado"] == "activo":
        pendientes.append(ev)
  return jsonify({"success": True, "mercados": pendientes})


@app.route("/api/resolver", methods=["POST"])
def resolver_evento():
  data = request.json
  evento_id = data.get("evento_id")
  ganador_id = data.get("ganador_id")

  evento = next((e for e in EVENTOS if e["id"] == evento_id), None)
  if not evento or evento["estado"] != "activo":
    return jsonify({"success": False, "error": "Mercado no encontrado o ya resuelto"}), 400

  evento["estado"] = "resuelto"
  evento["ganador_id"] = ganador_id

  # CÁLCULO Y REPARTO AUTOMÁTICO DE PREMIOS A LOS GANADORES
  pozo_total = sum(op["pozo"] for op in evento["opciones"])
  pozo_ganador = next((op["pozo"] for op in evento["opciones"] if op["id"] == ganador_id), 0)

  for uname, udata in USUARIOS.items():
    for ap in udata["historial"]:
      if ap.get("evento_id") == evento_id and ap.get("estado") == "Activa":
        if ap.get("opcion_id") == ganador_id:
          # Si el usuario ganó, se calcula su proporción del pozo total
          proporcion = ap["monto"] / pozo_ganador if pozo_ganador > 0 else 0
          premio = proporcion * pozo_total
          udata["saldo"] += premio
          udata["ganancias_netas"] += premio - ap["monto"]
          udata["apuestas_ganadas"] += 1
          ap["estado"] = f"Ganado (+{premio:.2f} Pi)"
        else:
          ap["estado"] = "Perdido"

  return jsonify({"success": True, "mensaje": "Veredicto emitido y premios repartidos automáticamente"})


@app.route("/api/leaderboard", methods=["GET"])
def leaderboard():
  ranking = []
  for uname, data in USUARIOS.items():
    ranking.append(
        {
            "username": uname,
            "ganancias_netas": data["ganancias_netas"],
            "apuestas_ganadas": data["apuestas_ganadas"],
            "apuestas_totales": data["apuestas_totales"],
        }
    )
  ranking = sorted(ranking, key=lambda x: x["ganancias_netas"], reverse=True)
  return jsonify({"success": True, "leaderboard": ranking[:10]})


if __name__ == "__main__":
  app.run(port=5000, debug=True)
