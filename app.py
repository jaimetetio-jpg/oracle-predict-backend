from datetime import datetime
import os
from flask import Flask, jsonify, render_template, request
import requests

app = Flask(__name__)

# Base de datos en memoria para el MVP (puedes migrar a PostgreSQL/SQLite luego)
BASE_DATOS = {
    "usuarios": {
        "PioneroDemo": {
            "saldo_disponible": 50.0,
            "historial": [],
            "transacciones": [],
        }
    },
    "eventos": [
        {
            "id": 1,
            "titulo": "BTC alcanzará los $120,000 antes de finalizar el mes?",
            "categoria": "Crypto",
            "estado": "activo",
            "fecha_cierre": "2026-12-31",
            "opciones": [
                {"id": 1, "nombre": "Sí", "pozo": 15.0},
                {"id": 2, "nombre": "No", "pozo": 10.0},
            ],
        },
        {
            "id": 2,
            "titulo": "Pi Network lanzará su Mainnet abierta global este año?",
            "categoria": "Pi Ecosystem",
            "estado": "activo",
            "fecha_cierre": "2026-11-30",
            "opciones": [
                {"id": 3, "nombre": "Sí", "pozo": 35.0},
                {"id": 4, "nombre": "No", "pozo": 5.0},
            ],
        },
    ],
    "leaderboard": [
        {"username": "CryptoKing", "ganancias_netas": 142.50},
        {"username": "PioneroVzla", "ganancias_netas": 98.20},
        {"username": "SMC_Trader", "ganancias_netas": 65.00},
    ],
}

ADMIN_PASSWORD = os.environ.get("ADMIN_PASS", "admin123")


@app.route("/")
def home():
  return render_template("index.html")


@app.route("/api/saldo/<username>", methods=["GET"])
def obtener_saldo(username):
  if username not in BASE_DATOS["usuarios"]:
    BASE_DATOS["usuarios"][username] = {
        "saldo_disponible": 10.0,  # Bono de bienvenida para testnet
        "historial": [],
        "transacciones": [],
    }
  user_data = BASE_DATOS["usuarios"][username]
  return jsonify(
      {
          "success": True,
          "saldo_disponible": user_data["saldo_disponible"],
          "historial": user_data["historial"],
          "transacciones": user_data["transacciones"],
      }
  )


@app.route("/api/eventos", methods=["GET"])
def obtener_eventos():
  return jsonify(BASE_DATOS["eventos"])


@app.route("/api/participar", methods=["POST"])
def participar():
  data = request.json
  username = data.get("username", "Invitado")
  evento_id = data.get("evento_id")
  opcion_id = data.get("opcion_id")
  monto = float(data.get("monto", 0))

  if username not in BASE_DATOS["usuarios"]:
    BASE_DATOS["usuarios"][username] = {
        "saldo_disponible": 10.0,
        "historial": [],
        "transacciones": [],
    }

  user_data = BASE_DATOS["usuarios"][username]
  if user_data["saldo_disponible"] < monto:
    return jsonify({"success": False, "error": "Saldo insuficiente"})

  # Buscar evento y opción
  evento = next((e for e in BASE_DATOS["eventos"] if e["id"] == evento_id), None)
  if not evento or evento["estado"] != "activo":
    return jsonify({"success": False, "error": "Mercado no disponible"})

  opcion = next(
      (o for o in evento["opciones"] if o["id"] == opcion_id), None
  )
  if not opcion:
    return jsonify({"success": False, "error": "Opción inválida"})

  # Descontar saldo y sumar al pozo
  user_data["saldo_disponible"] -= monto
  opcion["pozo"] += monto

  # Registrar en historial del usuario
  user_data["historial"].append({
      "titulo_evento": evento["titulo"],
      "opcion_elegida": opcion["nombre"],
      "monto": monto,
      "estado": "Activo",
  })

  return jsonify({"success": True, "nuevo_saldo": user_data["saldo_disponible"]})


@app.route("/api/pi/aprobar-pago", methods=["POST"])
def aprobar_pago():
  # Endpoint simulado para SDK de Pi (Server-to-Server Approval)
  return jsonify({"success": True})


@app.route("/api/pi/completar-pago", methods=["POST"])
def completar_pago():
  data = request.json
  username = data.get("username")
  monto = float(data.get("monto", 0))
  payment_id = data.get("paymentId")
  txid = data.get("txid")

  if username not in BASE_DATOS["usuarios"]:
    BASE_DATOS["usuarios"][username] = {
        "saldo_disponible": 0.0,
        "historial": [],
        "transacciones": [],
    }

  BASE_DATOS["usuarios"][username]["saldo_disponible"] += monto
  BASE_DATOS["usuarios"][username]["transacciones"].append({
      "tipo": "Recarga Pi",
      "monto": monto,
      "txid": txid or payment_id,
      "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
  })

  return jsonify({"success": True})


@app.route("/api/leaderboard", methods=["GET"])
def leaderboard():
  # Ordenar de mayor a menor ganancia
  sorted_lb = sorted(
      BASE_DATOS["leaderboard"],
      key=lambda x: x["ganancias_netas"],
      reverse=True,
  )
  return jsonify({"success": True, "leaderboard": sorted_lb})


@app.route("/api/admin/login", methods=["POST"])
def admin_login():
  data = request.json
  if data.get("password") == ADMIN_PASSWORD:
    return jsonify({"success": True})
  return jsonify({"success": False}), 401


@app.route("/api/admin/pendientes", methods=["GET"])
def admin_pendientes():
  # Retorna eventos que estén listos para resolución
  pendientes = [e for e in BASE_DATOS["eventos"] if e["estado"] == "activo"]
  return jsonify({"success": True, "mercados": pendientes})


@app.route("/api/resolver", methods=["POST"])
def resolver_evento():
  data = request.json
  evento_id = data.get("evento_id")
  ganador_id = data.get("ganador_id")

  evento = next((e for e in BASE_DATOS["eventos"] if e["id"] == evento_id), None)
  if not evento:
    return jsonify({"success": False, "error": "Evento no encontrado"})

  evento["estado"] = "finalizado"
  evento["ganador_id"] = ganador_id
  return jsonify({"success": True})


if __name__ == "__main__":
  app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
