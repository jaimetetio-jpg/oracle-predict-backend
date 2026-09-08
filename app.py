import os
import requests
from flask import Flask, jsonify, request, send_from_directory


app = Flask(__name__)

# Tu API Key secreta de la Testnet de Pi Network
PI_API_KEY = "uqfzqzchavl17hjejdeo2ou59siqreh8sdqisqxu6ladkngqlrh56dpgr1stz3nl"
PI_SERVER_URL = "https://api.minepi.com/v2"

# Base de datos simulada en memoria para el primer evento de prueba
eventos_activos = {
    1: {
        "titulo": "¿El oro (XAU/USD) cerrará al alza esta semana?",
        "estado": "abierto",
        "pool_total": 0.0,
        "predicciones": {},
    }
}


@app.route("/", methods=["GET"])
def home():
  return jsonify({
      "estado": "activo",
      "mensaje": "Bienvenido al backend de Oracle Predict",
  })


@app.route("/api/evento/<int:evento_id>", methods=["GET"])
def obtener_evento(evento_id):
  evento = eventos_activos.get(evento_id)
  if not evento:
    return jsonify({"error": "Evento no encontrado"}), 404
  return jsonify(evento)


@app.route("/api/pagos/aprobar", methods=["POST"])
def aprobar_pago():
  datos = request.json
  payment_id = datos.get("paymentId")

  headers = {"Authorization": f"Key {PI_API_KEY}"}
  response = requests.get(
      f"{PI_SERVER_URL}/payments/{payment_id}", headers=headers
  )

  if response.status_code != 200:
    return jsonify({"error": "No se pudo verificar el pago con Pi"}), 400

  pago_info = response.json()

  if pago_info.get("status", {}).get("developer_approved") == False:
    approval_response = requests.post(
        f"{PI_SERVER_URL}/payments/{payment_id}/approve", headers=headers
    )
    if approval_response.status_code != 200:
      return jsonify({"error": "Falló la aprobación del pago"}), 500

  return jsonify({"status": "aprobado"})


@app.route("/api/pagos/completar", methods=["POST"])
def completar_pago():
  datos = request.json
  payment_id = datos.get("paymentId")
  txid = datos.get("txid")
  username = datos.get("username")
  evento_id = datos.get("evento_id")
  eleccion = datos.get("eleccion")

  headers = {"Authorization": f"Key {PI_API_KEY}"}

  complete_response = requests.post(
      f"{PI_SERVER_URL}/payments/{payment_id}/complete",
      headers=headers,
      json={"txid": txid},
  )

  if complete_response.status_code != 200:
    return jsonify({"error": "No se pudo completar el pago en la red"}), 500

  evento = eventos_activos.get(evento_id)
  if evento and evento["estado"] == "abierto":
    evento["predicciones"][username] = {
        "eleccion": eleccion,
        "paymentId": payment_id,
    }
    evento["pool_total"] += 1.0  # Suma 1 Pi al pozo por cada participación

  return jsonify(
      {
          "mensaje": "¡Pago completado y predicción registrada!",
          "pool_actual": evento["pool_total"],
      }
  )

@app.route('/validation-key.txt')
def serve_validation_key():
    return send_from_directory('static', 'validation-key.txt')

if __name__ == "__main__":
  port = int(os.environ.get("PORT", 5000))
  app.run(host="0.0.0.0", port=port)
    

