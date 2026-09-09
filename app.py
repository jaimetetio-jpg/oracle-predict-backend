import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

# CONFIGURACIÓN DE TU LLAVE DE ADMIN DE PI (Obtenida en el Portal de Desarrolladores de Pi)
PI_API_KEY = "Key TU_API_KEY_SECRETA_DE_PI_DEVELOPER_PORTAL"
PI_HEADERS = {
    "Authorization": f"Key {PI_API_KEY}",
    "Content-Type": "application/json",
}

# Base de datos simulada en memoria (puedes conectarla a PostgreSQL o SQLite)
USUARIOS = {}  # username -> { saldo, historial, ordenes }
EVENTOS = []


@app.route("/api/pi/aprobar-pago", methods=["POST"])
def aprobar_pago_pi():
  data = request.json
  payment_id = data.get("paymentId")
  # Llamada obligatoria al servidor de Pi para aprobar el pago del usuario
  url = f"https://api.minepi.com/v2/payments/{payment_id}/approve"
  response = requests.post(url, headers=PI_HEADERS)
  if response.status_code == 200:
    return jsonify({"success": True})
  return jsonify({"success": False, "error": "No se pudo aprobar el pago"}), 400


@app.route("/api/pi/completar-pago", methods=["POST"])
def completar_pago_pi():
  data = request.json
  payment_id = data.get("paymentId")
  txid = data.get("txid")
  username = data.get("username")
  monto = data.get("monto")

  # Llamada oficial para completar la transacción en la red Pi
  url = f"https://api.minepi.com/v2/payments/{payment_id}/complete"
  response = requests.post(url, headers=PI_HEADERS, json={"txid": txid})

  if response.status_code == 200:
    # Acreditar saldo automáticamente en la app al Pionero
    if username not in USUARIOS:
      USUARIOS[username] = {"saldo": 0.0, "historial": []}
    USUARIOS[username]["saldo"] += monto
    return jsonify({"success": True, "nuevo_saldo": USUARIOS[username]["saldo"]})

  return jsonify({"success": False, "error": "Fallo al completar en blockchain"}), 400


@app.route("/api/admin/pendientes", methods=["GET"])
def obtener_pendientes_admin():
  # Filtra eventos que ya pasaron su fecha de cierre y siguen activos (Alerta para el admin)
  from datetime import datetime

  ahora = datetime.utcnow()
  pendientes = []
  for ev in EVENTOS:
    # Si la fecha actual supera el cierre y el estado es activo, se marca para resolución
    if ev["estado"] == "activo":
      # (Opcional: puedes comparar fechas string con datetime)
      pendientes.append(ev)
  return jsonify({"success": True, "mercados": pendientes})


if __name__ == "__main__":
  app.run(port=5000, debug=True)
