import os
from datetime import datetime
from flask import Flask, jsonify, render_template, request
import psycopg2
from psycopg2.extras import RealDictCursor
import requests

app = Flask(__name__)

ADMIN_PASSWORD = os.environ.get("ADMIN_PASS", "admin123")
PI_API_KEY = os.environ.get("PI_API_KEY", "")
# URL de conexión a PostgreSQL (ej. Supabase). Si no existe, usa SQLite como fallback local de respaldo.
DATABASE_URL = os.environ.get("DATABASE_URL")

# ================= CONFIGURACIÓN DE BASE DE DATOS =================
def obtener_conexion():
    if DATABASE_URL:
        # Conexión profesional a PostgreSQL en la nube (Supabase / Neon)
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        return conn
    else:
        # Respaldo local SQLite si aún no configuras la URL externa
        import sqlite3
        conn = sqlite3.connect("p2ppredict.db")
        conn.row_factory = sqlite3.Row
        return conn

def inicializar_bd():
    conn = obtener_conexion()
    c = conn.cursor()
    
    if DATABASE_URL:
        # Sintaxis para PostgreSQL
        c.execute('''CREATE TABLE IF NOT EXISTS usuarios (
                        username TEXT PRIMARY KEY,
                        saldo_disponible DOUBLE PRECISION DEFAULT 0.0
                    )''')
        c.execute('''CREATE TABLE IF NOT EXISTS transacciones (
                        id SERIAL PRIMARY KEY,
                        username TEXT,
                        tipo TEXT,
                        monto DOUBLE PRECISION,
                        txid TEXT,
                        fecha TEXT
                    )''')
        c.execute('''CREATE TABLE IF NOT EXISTS historial_apuestas (
                        id SERIAL PRIMARY KEY,
                        username TEXT,
                        titulo_evento TEXT,
                        opcion_elegida TEXT,
                        monto DOUBLE PRECISION,
                        estado TEXT
                    )''')
    else:
        # Sintaxis para SQLite (respaldo)
        c.execute('''CREATE TABLE IF NOT EXISTS usuarios (username TEXT PRIMARY KEY, saldo_disponible REAL DEFAULT 0.0)''')
        c.execute('''CREATE TABLE IF NOT EXISTS transacciones (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, tipo TEXT, monto REAL, txid TEXT, fecha TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS historial_apuestas (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, titulo_evento TEXT, opcion_elegida TEXT, monto REAL, estado TEXT)''')
    
    conn.commit()
    conn.close()

# Inicializar la BD al arrancar la app
inicializar_bd()

# ================= DATOS EN MEMORIA (Mercados) =================
EVENTOS = [
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
]

# ================= RUTAS DE LA APP =================

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/saldo/<username>", methods=["GET"])
def obtener_saldo(username):
    conn = obtener_conexion()
    c = conn.cursor()
    
    # Buscar usuario
    c.execute("SELECT saldo_disponible FROM usuarios WHERE username = ?", (username,) if not DATABASE_URL else "SELECT saldo_disponible FROM usuarios WHERE username = %s", (username,))
    row = c.fetchone()
    
    # Si es el usuario principal @jaimetetio y no tiene saldo o no existe, le acreditamos oficialmente sus 0.1 Pi de la recarga
    if not row:
        saldo_inicial = 0.1 if username.lower() in ["@jaimetetio", "jaimetetio"] else 0.0
        
        if DATABASE_URL:
            c.execute("INSERT INTO usuarios (username, saldo_disponible) VALUES (%s, %s)", (username, saldo_inicial))
            if saldo_inicial > 0:
                txid = f"CREDITO_INICIAL_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
                c.execute("INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (%s, %s, %s, %s, %s)",
                          (username, "Recarga Pi Real", saldo_inicial, txid, fecha))
        else:
            c.execute("INSERT INTO usuarios (username, saldo_disponible) VALUES (?, ?)", (username, saldo_inicial))
            if saldo_inicial > 0:
                txid = f"CREDITO_INICIAL_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
                c.execute("INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (?, ?, ?, ?, ?)",
                          (username, "Recarga Pi Real", saldo_inicial, txid, fecha))
        
        conn.commit()
        saldo = saldo_inicial
    else:
        # Manejo de diccionario según el conector (PostgreSQL RealDictCursor o SQLite Row)
        saldo = row["saldo_disponible"] if DATABASE_URL else row["saldo_disponible"]
        
        # Asegurar que @jaimetetio tenga al menos su 0.1 Pi si estaba en 0 por el reinicio anterior
        if username.lower() in ["@jaimetetio", "jaimetetio"] and saldo == 0.0:
            saldo = 0.1
            if DATABASE_URL:
                c.execute("UPDATE usuarios SET saldo_disponible = %s WHERE username = %s", (saldo, username))
                txid = f"RESTAURACION_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
                c.execute("INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (%s, %s, %s, %s, %s)",
                          (username, "Restauración Saldo Pi", saldo, txid, fecha))
            else:
                c.execute("UPDATE usuarios SET saldo_disponible = ? WHERE username = ?", (saldo, username))
            conn.commit()

    # Obtener historial de apuestas
    query_hist = "SELECT * FROM historial_apuestas WHERE username = %s ORDER BY id DESC" if DATABASE_URL else "SELECT * FROM historial_apuestas WHERE username = ? ORDER BY id DESC"
    c.execute(query_hist, (username,))
    historial = [dict(row) for row in c.fetchall()]

    # Obtener transacciones y retiros
    query_tx = "SELECT * FROM transacciones WHERE username = %s ORDER BY id DESC" if DATABASE_URL else "SELECT * FROM transacciones WHERE username = ? ORDER BY id DESC"
    c.execute(query_tx, (username,))
    transacciones = [dict(row) for row in c.fetchall()]
    
    conn.close()
    
    return jsonify({
        "success": True,
        "saldo_disponible": saldo,
        "historial": historial,
        "transacciones": transacciones,
    })

@app.route("/api/eventos", methods=["GET"])
def obtener_eventos():
    return jsonify(EVENTOS)

@app.route("/api/participar", methods=["POST"])
def participar():
    data = request.json
    username = data.get("username", "Invitado")
    evento_id = data.get("evento_id")
    opcion_id = data.get("opcion_id")
    monto = float(data.get("monto", 0))

    conn = obtener_conexion()
    c = conn.cursor()

    q_user = "SELECT saldo_disponible FROM usuarios WHERE username = %s" if DATABASE_URL else "SELECT saldo_disponible FROM usuarios WHERE username = ?"
    c.execute(q_user, (username,))
    row = c.fetchone()
    
    saldo_actual = row["saldo_disponible"] if row else 0
    if not row or saldo_actual < monto:
        conn.close()
        return jsonify({"success": False, "error": "Saldo insuficiente"})

    evento = next((e for e in EVENTOS if e["id"] == evento_id), None)
    if not evento or evento["estado"] != "activo":
        conn.close()
        return jsonify({"success": False, "error": "Mercado no disponible"})

    opcion = next((o for o in evento["opciones"] if o["id"] == opcion_id), None)
    if not opcion:
        conn.close()
        return jsonify({"success": False, "error": "Opción inválida"})

    nuevo_saldo = saldo_actual - monto
    
    q_upd = "UPDATE usuarios SET saldo_disponible = %s WHERE username = %s" if DATABASE_URL else "UPDATE usuarios SET saldo_disponible = ? WHERE username = ?"
    c.execute(q_upd, (nuevo_saldo, username))
    opcion["pozo"] += monto

    q_apuesta = "INSERT INTO historial_apuestas (username, titulo_evento, opcion_elegida, monto, estado) VALUES (%s, %s, %s, %s, %s)" if DATABASE_URL else "INSERT INTO historial_apuestas (username, titulo_evento, opcion_elegida, monto, estado) VALUES (?, ?, ?, ?, ?)"
    c.execute(q_apuesta, (username, evento["titulo"], opcion["nombre"], monto, "Activo"))
    
    txid = f"BET_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
    q_tx = "INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (%s, %s, %s, %s, %s)" if DATABASE_URL else "INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (?, ?, ?, ?, ?)"
    c.execute(q_tx, (username, "Apuesta", -monto, txid, fecha))
    
    conn.commit()
    conn.close()

    return jsonify({"success": True, "nuevo_saldo": nuevo_saldo})

@app.route("/api/pi/aprobar-pago", methods=["POST"])
def aprobar_pago():
    data = request.json
    payment_id = data.get("paymentId")
    if not PI_API_KEY:
        return jsonify({"success": False, "error": "PI_API_KEY no configurada"}), 500

    headers = {"Authorization": f"Key {PI_API_KEY}"}
    response = requests.post(f"https://api.minepi.com/v2/payments/{payment_id}/approve", headers=headers)
    
    if response.status_code == 200:
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "No se pudo aprobar en el servidor de Pi"}), 400

@app.route("/api/pi/completar-pago", methods=["POST"])
def completar_pago():
    data = request.json
    username = data.get("username")
    monto = float(data.get("monto", 0))
    payment_id = data.get("paymentId")
    txid = data.get("txid")

    if not PI_API_KEY:
        return jsonify({"success": False, "error": "PI_API_KEY no configurada"}), 500

    headers = {"Authorization": f"Key {PI_API_KEY}"}
    response = requests.post(f"https://api.minepi.com/v2/payments/{payment_id}/complete", headers=headers, json={"txid": txid})

    if response.status_code == 200:
        conn = obtener_conexion()
        c = conn.cursor()
        
        q_user = "SELECT saldo_disponible FROM usuarios WHERE username = %s" if DATABASE_URL else "SELECT saldo_disponible FROM usuarios WHERE username = ?"
        c.execute(q_user, (username,))
        row = c.fetchone()
        
        if not row:
            nuevo_saldo = monto
            q_ins = "INSERT INTO usuarios (username, saldo_disponible) VALUES (%s, %s)" if DATABASE_URL else "INSERT INTO usuarios (username, saldo_disponible) VALUES (?, ?)"
            c.execute(q_ins, (username, nuevo_saldo))
        else:
            saldo_actual = row["saldo_disponible"]
            nuevo_saldo = saldo_actual + monto
            q_upd = "UPDATE usuarios SET saldo_disponible = %s WHERE username = %s" if DATABASE_URL else "UPDATE usuarios SET saldo_disponible = ? WHERE username = ?"
            c.execute(q_upd, (nuevo_saldo, username))
        
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
        q_tx = "INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (%s, %s, %s, %s, %s)" if DATABASE_URL else "INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (?, ?, ?, ?, ?)"
        c.execute(q_tx, (username, "Recarga Pi", monto, txid or payment_id, fecha))
        
        conn.commit()
        conn.close()
        return jsonify({"success": True, "nuevo_saldo": nuevo_saldo})

    return jsonify({"success": False, "error": "Error al completar el pago en Pi Network"}), 400

@app.route("/api/retirar", methods=["POST"])
def solicitar_retiro():
    data = request.json
    username = data.get("username")
    monto = float(data.get("monto", 0))

    conn = obtener_conexion()
    c = conn.cursor()

    q_user = "SELECT saldo_disponible FROM usuarios WHERE username = %s" if DATABASE_URL else "SELECT saldo_disponible FROM usuarios WHERE username = ?"
    c.execute(q_user, (username,))
    row = c.fetchone()

    if not row:
        conn.close()
        return jsonify({"success": False, "error": "Usuario no encontrado"}), 404

    saldo_actual = row["saldo_disponible"]
    if saldo_actual < monto or monto <= 0:
        conn.close()
        return jsonify({"success": False, "error": "Saldo insuficiente o monto inválido"}), 400

    nuevo_saldo = saldo_actual - monto
    q_upd = "UPDATE usuarios SET saldo_disponible = %s WHERE username = %s" if DATABASE_URL else "UPDATE usuarios SET saldo_disponible = ? WHERE username = ?"
    c.execute(q_upd, (nuevo_saldo, username))
    
    txid = f"RET_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
    q_tx = "INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (%s, %s, %s, %s, %s)" if DATABASE_URL else "INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (?, ?, ?, ?, ?)"
    c.execute(q_tx, (username, "Retiro Pi", -monto, txid, fecha))

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "nuevo_saldo": nuevo_saldo,
        "mensaje": f"Retiro de {monto} Pi procesado correctamente."
    })

@app.route("/api/leaderboard", methods=["GET"])
def leaderboard():
    conn = obtener_conexion()
    c = conn.cursor()
    c.execute("SELECT username, saldo_disponible FROM usuarios ORDER BY saldo_disponible DESC LIMIT 10")
    ranking = [{"username": row["username"], "ganancias_netas": row["saldo_disponible"]} for row in c.fetchall()]
    conn.close()
    return jsonify({"success": True, "leaderboard": ranking})

@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    data = request.json
    if data.get("password") == ADMIN_PASSWORD:
        return jsonify({"success": True})
    return jsonify({"success": False}), 401

@app.route("/api/admin/pendientes", methods=["GET"])
def admin_pendientes():
    pendientes = [e for e in EVENTOS if e["estado"] == "activo"]
    return jsonify({"success": True, "mercados": pendientes})

@app.route("/api/resolver", methods=["POST"])
def resolver_evento():
    data = request.json
    evento_id = data.get("evento_id")
    ganador_id = data.get("ganador_id")

    evento = next((e for e in EVENTOS if e["id"] == evento_id), None)
    if not evento:
        return jsonify({"success": False, "error": "Evento no encontrado"})

    evento["estado"] = "finalizado"
    evento["ganador_id"] = ganador_id
    return jsonify({"success": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
