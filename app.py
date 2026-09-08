from flask import Flask, jsonify, render_template, request
import os
import requests

app = Flask(__name__)

# Diccionario temporal en memoria para almacenar los eventos P2P
# Evento por defecto para que la app nunca inicie vacía
eventos_activos = {
    1: {
        "titulo": "Prueba de Predicción P2P en Pi Network",
        "creador": "sistema",
        "estado": "abierto",
        "pool_total": 0.0,
        "predicciones": {},
    }
}

PI_SERVER_URL = "https://api.minepi.com/v2"
PI_API_KEY = os.environ.get("PI_API_KEY", "tu_api_key_aqui")


@app.route("/")
def home():
  return render_template("index.html")


# Ruta para consultar los datos de un evento específico
@app.route("/api/evento/<int:evento_id>", methods=["GET"])
def obtener_evento(evento_id):
  evento = eventos_activos.get(evento_id)
  if not evento:
    return jsonify({"error": "Evento no encontrado"}), 404
  return jsonify(evento)


# Ruta para que los usuarios creen un nuevo pronóstico P2P
@app.route("/api/evento/crear", methods=["POST"])
def crear_evento():
  datos = request.json
  titulo = datos.get("titulo")
  creador = datos.get("username")

  if not titulo or not creador:
    return jsonify({"error": "Faltan datos obligatorios"}), 400

  nuevo_id = len(eventos_activos) + 1
  eventos_activos[nuevo_id] = {
      "titulo": titulo,
      "creador": creador,
      "estado": "abierto",
      "pool_total": 0.0,
      "predicciones": {},
  }

  return jsonify(
      {"mensaje": "¡Predicción P2P creada con éxito!", "evento_id": nuevo_id}
  )


# Ruta para aprobar el pago en el servidor (Pi Network SDK)
@app.route("/api/pagos/aprobar", methods=["POST"])
def aprobar_pago():
  data = request.json
  payment_id = data.get("paymentId")

  if not payment_id:
    return jsonify({"error": "Falta el paymentId"}), 400

  headers = {"Authorization": f"Key {PI_API_KEY}"}

  try:
    response = requests.post(
        f"{PI_SERVER_URL}/payments/{payment_id}/approve", headers=headers
    )
    if response.status_code == 200:
      return jsonify({"status": "aprobado"})
    else:
      return (
          jsonify(
              {"error": "Error al aprobar en Pi Server", "detalles": response.text}
          ),
          400,
      )
  except Exception as e:
    return jsonify({"error": str(e)}), 500


# Ruta para completar el pago y registrar la participación en el evento P2P
@app.route("/api/pagos/completar", methods=["POST"])
def completar_pago():
  data = request.json
  payment_id = data.get("paymentId")
  txid = data.get("txid")
  username = data.get("username")
  evento_id = data.get("evento_id")
  eleccion = data.get("eleccion", "Sí")

  if not payment_id or not txid or not evento_id:
    return jsonify({"error": "Faltan datos obligatorios para completar"}), 400

  headers = {"Authorization": f"Key {PI_API_KEY}"}

  try:
    complete_response = requests.post(
        f"{PI_SERVER_URL}/payments/{payment_id}/complete",
        headers=headers,
        json={"txid": txid},
    )

    if complete_response.status_code != 200:
      return jsonify({"error": "No se pudo completar el pago en Pi Network"}), 400

    # Buscar el evento y registrar la predicción del usuario
    evento = eventos_activos.get(evento_id)
    if evento and evento["estado"] == "abierto":
      evento["predicciones"][username] = {
          "eleccion": eleccion,
          "paymentId": payment_id,
      }
      evento["pool_total"] += 1.0  # Suma 1 Pi al pozo por la participación

      return jsonify({
          "mensaje": "¡Pago completado y predicción registrada!",
          "pool_actual": evento["pool_total"],
      })
    else:
      return jsonify({"error": "El evento no existe o está cerrado"}), 400

  except Exception as e:
    return jsonify({"error": str(e)}), 500


# Ruta auxiliar opcional por si la necesitas

@app.route('/validation-key.txt')
def validation_key():
    return "8c73ed3c39ffc42821ce971267c7b58d01487"

if __name__ == "__main__":
  port = int(os.environ.get("PORT", 5000))
  app.run(host="0.0.0.0", port=port)
