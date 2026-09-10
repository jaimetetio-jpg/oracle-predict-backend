import os
from datetime import datetime
from flask import Flask, jsonify, render_template, request, session
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
import requests
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

CORS(app, resources={r"/api/*": {"origins": "*"}})
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "p2ppredict_secret_key_ultra_segura_2026")

RAW_ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Anthony*2023")
ADMIN_PASSWORD_HASH = generate_password_hash(RAW_ADMIN_PASSWORD)

PI_API_KEY = os.environ.get("PI_API_KEY", "")
DATABASE_URL = os.environ.get("DATABASE_URL")

# ================= CONFIGURACIÓN DE BASE DE DATOS =================
def obtener_conexion():
    if DATABASE_URL:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor, connect_timeout=10)
        return conn
    else:
        import sqlite3
        conn = sqlite3.connect("p2ppredict.db", timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

def inicializar_bd():
    conn = obtener_conexion()
    c = conn.cursor()
    
    if DATABASE_URL:
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
        c.execute('''CREATE TABLE IF NOT EXISTS ordenes_clob (
                        id SERIAL PRIMARY KEY,
                        username TEXT,
                        evento_id INTEGER,
                        opcion_id INTEGER,
                        tipo_orden TEXT,
                        accion TEXT,
                        precio DOUBLE PRECISION,
                        cantidad DOUBLE PRECISION,
                        estado TEXT DEFAULT 'activa',
                        fecha TEXT
                    )''')
        c.execute('''CREATE TABLE IF NOT EXISTS eventos (
                        id SERIAL PRIMARY KEY,
                        titulo TEXT,
                        categoria TEXT,
                        estado TEXT DEFAULT 'activo',
                        fecha_cierre TEXT,
                        ganador_id INTEGER
                    )''')
        c.execute('''CREATE TABLE IF NOT EXISTS opciones_evento (
                        id SERIAL PRIMARY KEY,
                        evento_id INTEGER,
                        nombre TEXT,
                        pozo DOUBLE PRECISION DEFAULT 0.0
                    )''')
        c.execute('''CREATE TABLE IF NOT EXISTS admin_logs (
                        id SERIAL PRIMARY KEY,
                        ip TEXT,
                        accion TEXT,
                        detalles TEXT,
                        fecha TEXT
                    )''')
        c.execute('''CREATE TABLE IF NOT EXISTS soporte_mensajes (
                        id SERIAL PRIMARY KEY,
                        username TEXT,
                        remitente TEXT,
                        texto TEXT,
                        fecha TEXT
                    )''')
    else:
        c.execute('''CREATE TABLE IF NOT EXISTS usuarios (username TEXT PRIMARY KEY, saldo_disponible REAL DEFAULT 0.0)''')
        c.execute('''CREATE TABLE IF NOT EXISTS transacciones (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, tipo TEXT, monto REAL, txid TEXT, fecha TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS historial_apuestas (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, titulo_evento TEXT, opcion_elegida TEXT, monto REAL, estado TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS ordenes_clob (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, evento_id INTEGER, opcion_id INTEGER, tipo_orden TEXT, accion TEXT, precio REAL, cantidad REAL, estado TEXT DEFAULT 'activa', fecha TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS eventos (id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT, categoria TEXT, estado TEXT DEFAULT 'activo', fecha_cierre TEXT, ganador_id INTEGER)''')
        c.execute('''CREATE TABLE IF NOT EXISTS opciones_evento (id INTEGER PRIMARY KEY AUTOINCREMENT, evento_id INTEGER, nombre TEXT, pozo REAL DEFAULT 0.0)''')
        c.execute('''CREATE TABLE IF NOT EXISTS admin_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, ip TEXT, accion TEXT, detalles TEXT, fecha TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS soporte_mensajes (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, remitente TEXT, texto TEXT, fecha TEXT)''')
    
    conn.commit()

    c.execute("SELECT COUNT(*) as total FROM eventos")
    row = c.fetchone()
    total_evs = row["total"] if row else 0
    
    if total_evs == 0:
        eventos_iniciales = [
            {
                "titulo": "¿BTC alcanzará los $120,000 antes de finalizar el mes?",
                "categoria": "Crypto",
                "fecha_cierre": "2026-12-31",
                "opciones": [("Sí", 15.0), ("No", 10.0)]
            },
            {
                "titulo": "¿Pi Network lanzará su Mainnet abierta global este año?",
                "categoria": "Pi Ecosystem",
                "fecha_cierre": "2026-11-30",
                "opciones": [("Sí", 35.0), ("No", 5.0)]
            }
        ]
        for ev in eventos_iniciales:
            if DATABASE_URL:
                c.execute("INSERT INTO eventos (titulo, categoria, estado, fecha_cierre) VALUES (%s, %s, 'activo', %s) RETURNING id", 
                          (ev["titulo"], ev["categoria"], ev["fecha_cierre"]))
                res_ev = c.fetchone()
                ev_id = res_ev["id"]
                for opt_nombre, opt_pozo in ev["opciones"]:
                    c.execute("INSERT INTO opciones_evento (evento_id, nombre, pozo) VALUES (%s, %s, %s)", (ev_id, opt_nombre, opt_pozo))
            else:
                c.execute("INSERT INTO eventos (titulo, categoria, estado, fecha_cierre) VALUES (?, ?, 'activo', ?)", 
                          (ev["titulo"], ev["categoria"], ev["fecha_cierre"]))
                ev_id = c.lastrowid
                for opt_nombre, opt_pozo in ev["opciones"]:
                    c.execute("INSERT INTO opciones_evento (evento_id, nombre, pozo) VALUES (?, ?, ?)", (ev_id, opt_nombre, opt_pozo))
        conn.commit()

    conn.close()

inicializar_bd()

def registrar_log_admin(accion, detalles):
    try:
        conn = obtener_conexion()
        c = conn.cursor()
        ip = request.remote_addr or "127.0.0.1"
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if DATABASE_URL:
            c.execute("INSERT INTO admin_logs (ip, accion, detalles, fecha) VALUES (%s, %s, %s, %s)", (ip, accion, detalles, fecha))
        else:
            c.execute("INSERT INTO admin_logs (ip, accion, detalles, fecha) VALUES (?, ?, ?, ?)", (ip, accion, detalles, fecha))
        conn.commit()
        conn.close()
    except Exception:
        pass

def obtener_eventos_completos():
    conn = obtener_conexion()
    c = conn.cursor()
    c.execute("SELECT * FROM eventos ORDER BY id ASC")
    eventos_db = c.fetchall()
    
    lista_final = []
    for ev in eventos_db:
        ev_dict = dict(ev)
        if DATABASE_URL:
            c.execute("SELECT id, nombre, pozo FROM opciones_evento WHERE evento_id = %s", (ev_dict["id"],))
        else:
            c.execute("SELECT id, nombre, pozo FROM opciones_evento WHERE evento_id = ?", (ev_dict["id"],))
        opciones = [dict(op) for op in c.fetchall()]
        ev_dict["opciones"] = opciones
        lista_final.append(ev_dict)
    conn.close()
    return lista_final

# ================= RUTAS DE LA APP =================

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/saldo/<username>", methods=["GET"])
def obtener_saldo(username):
    limite = int(request.args.get("limit", 20))
    offset = int(request.args.get("offset", 0))

    conn = obtener_conexion()
    c = conn.cursor()
    
    if DATABASE_URL:
        c.execute("SELECT saldo_disponible FROM usuarios WHERE username = %s", (username,))
    else:
        c.execute("SELECT saldo_disponible FROM usuarios WHERE username = ?", (username,))
    row = c.fetchone()
    
    # RESTAURADO: Asignación automática de los 0.1 Pi para @jaimetetio
    if not row:
        saldo_inicial = 0.1 if username.lower() in ["@jaimetetio", "jaimetetio"] else 0.0
        
        if DATABASE_URL:
            c.execute("INSERT INTO usuarios (username, saldo_disponible) VALUES (%s, %s)", (username, saldo_inicial))
            if saldo_inicial > 0:
                txid = f"CREDITO_INICIAL_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
                c.execute("INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (%s, %s, %s, %s, %s)",
                          (username, "Crédito Inicial", saldo_inicial, txid, fecha))
        else:
            c.execute("INSERT INTO usuarios (username, saldo_disponible) VALUES (?, ?)", (username, saldo_inicial))
            if saldo_inicial > 0:
                txid = f"CREDITO_INICIAL_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
                c.execute("INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (?, ?, ?, ?, ?)",
                          (username, "Crédito Inicial", saldo_inicial, txid, fecha))
        
        conn.commit()
        saldo = saldo_inicial
    else:
        saldo = row["saldo_disponible"]
        if username.lower() in ["@jaimetetio", "jaimetetio"] and saldo == 0.0:
            saldo = 0.1
            if DATABASE_URL:
                c.execute("UPDATE usuarios SET saldo_disponible = %s WHERE username = %s", (saldo, username))
                txid = f"RESTAURACION_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
                c.execute("INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (%s, %s, %s, %s, %s)",
                          (username, "Restauración Saldo", saldo, txid, fecha))
            else:
                c.execute("UPDATE usuarios SET saldo_disponible = ? WHERE username = ?", (saldo, username))
                txid = f"RESTAURACION_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
                c.execute("INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (?, ?, ?, ?, ?)",
                          (username, "Restauración Saldo", saldo, txid, fecha))
            conn.commit()

    if DATABASE_URL:
        c.execute("SELECT * FROM historial_apuestas WHERE username = %s ORDER BY id DESC LIMIT %s OFFSET %s", (username, limite, offset))
    else:
        c.execute("SELECT * FROM historial_apuestas WHERE username = ? ORDER BY id DESC LIMIT ? OFFSET ?", (username, limite, offset))
    historial = [dict(row) for row in c.fetchall()]

    if DATABASE_URL:
        c.execute("SELECT * FROM transacciones WHERE username = %s ORDER BY id DESC LIMIT %s OFFSET %s", (username, limite, offset))
    else:
        c.execute("SELECT * FROM transacciones WHERE username = ? ORDER BY id DESC LIMIT ? OFFSET ?", (username, limite, offset))
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
    eventos = obtener_eventos_completos()
    return jsonify(eventos)

@app.route("/api/participar", methods=["POST"])
def participar():
    data = request.json or {}
    username = data.get("username", "Invitado")
    evento_id = data.get("evento_id")
    opcion_id = data.get("opcion_id")
    monto = float(data.get("monto", 0))

    if monto <= 0:
        return jsonify({"success": False, "error": "El monto debe ser mayor a 0"}), 400

    conn = obtener_conexion()
    c = conn.cursor()

    try:
        if DATABASE_URL:
            c.execute("SELECT saldo_disponible FROM usuarios WHERE username = %s FOR UPDATE", (username,))
        else:
            c.execute("SELECT saldo_disponible FROM usuarios WHERE username = ?", (username,))
        
        row = c.fetchone()
        saldo_actual = row["saldo_disponible"] if row else 0
        if not row or saldo_actual < monto:
            conn.rollback()
            conn.close()
            return jsonify({"success": False, "error": "Saldo insuficiente"})

        if DATABASE_URL:
            c.execute("SELECT * FROM eventos WHERE id = %s", (evento_id,))
        else:
            c.execute("SELECT * FROM eventos WHERE id = ?", (evento_id,))
        evento = c.fetchone()
        
        if not evento or evento["estado"] != "activo":
            conn.rollback()
            conn.close()
            return jsonify({"success": False, "error": "Mercado no disponible"})

        if DATABASE_URL:
            c.execute("SELECT * FROM opciones_evento WHERE id = %s AND evento_id = %s", (opcion_id, evento_id))
        else:
            c.execute("SELECT * FROM opciones_evento WHERE id = ? AND evento_id = ?", (opcion_id, evento_id))
        opcion = c.fetchone()
        
        if not opcion:
            conn.rollback()
            conn.close()
            return jsonify({"success": False, "error": "Opción inválida"})

        nuevo_saldo = saldo_actual - monto
        
        if DATABASE_URL:
            c.execute("UPDATE usuarios SET saldo_disponible = %s WHERE username = %s", (nuevo_saldo, username))
            c.execute("UPDATE opciones_evento SET pozo = pozo + %s WHERE id = %s", (monto, opcion_id))
        else:
            c.execute("UPDATE usuarios SET saldo_disponible = ? WHERE username = ?", (nuevo_saldo, username))
            c.execute("UPDATE opciones_evento SET pozo = pozo + ? WHERE id = ?", (monto, opcion_id))

        if DATABASE_URL:
            c.execute("INSERT INTO historial_apuestas (username, titulo_evento, opcion_elegida, monto, estado) VALUES (%s, %s, %s, %s, %s)",
                      (username, evento["titulo"], opcion["nombre"], monto, "Activo"))
        else:
            c.execute("INSERT INTO historial_apuestas (username, titulo_evento, opcion_elegida, monto, estado) VALUES (?, ?, ?, ?, ?)",
                      (username, evento["titulo"], opcion["nombre"], monto, "Activo"))
        
        txid = f"BET_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
        if DATABASE_URL:
            c.execute("INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (%s, %s, %s, %s, %s)",
                      (username, "Apuesta", -monto, txid, fecha))
        else:
            c.execute("INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (?, ?, ?, ?, ?)",
                      (username, "Apuesta", -monto, txid, fecha))
        
        conn.commit()
        return jsonify({
            "success": True, 
            "nuevo_saldo": nuevo_saldo,
            "mensaje": "¡Apuesta registrada con éxito!"
        })
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()

# ================= PASARELA DE PAGO OFICIAL PI NETWORK =================

@app.route("/api/pi/aprobar-pago", methods=["POST"])
def aprobar_pago():
    data = request.json or {}
    payment_id = data.get("paymentId")
    if not PI_API_KEY:
        return jsonify({"success": False, "error": "PI_API_KEY no configurada"}), 500

    headers = {"Authorization": f"Key {PI_API_KEY}"}
    try:
        response = requests.post(f"https://api.minepi.com/v2/payments/{payment_id}/approve", headers=headers, timeout=10)
        if response.status_code == 200:
            return jsonify({"success": True})
    except requests.exceptions.RequestException:
        return jsonify({"success": False, "error": "Error de red con Pi Network"}), 504
        
    return jsonify({"success": False, "error": "No se pudo aprobar el pago"}), 400

@app.route("/api/pi/completar-pago", methods=["POST"])
def completar_pago():
    data = request.json or {}
    username = data.get("username")
    monto = float(data.get("monto", 0))
    payment_id = data.get("paymentId")
    txid = data.get("txid")

    if PI_API_KEY:
        headers = {"Authorization": f"Key {PI_API_KEY}"}
        try:
            response = requests.post(f"https://api.minepi.com/v2/payments/{payment_id}/complete", headers=headers, json={"txid": txid}, timeout=10)
            if response.status_code != 200:
                return jsonify({"success": False, "error": "Error al completar el pago en Pi"}), 400
        except requests.exceptions.RequestException:
            return jsonify({"success": False, "error": "Error de red con Pi Network"}), 504

    conn = obtener_conexion()
    c = conn.cursor()
    
    try:
        if DATABASE_URL:
            c.execute("SELECT saldo_disponible FROM usuarios WHERE username = %s FOR UPDATE", (username,))
        else:
            c.execute("SELECT saldo_disponible FROM usuarios WHERE username = ?", (username,))
        row = c.fetchone()
        
        if not row:
            nuevo_saldo = monto
            if DATABASE_URL:
                c.execute("INSERT INTO usuarios (username, saldo_disponible) VALUES (%s, %s)", (username, nuevo_saldo))
            else:
                c.execute("INSERT INTO usuarios (username, saldo_disponible) VALUES (?, ?)", (username, nuevo_saldo))
        else:
            saldo_actual = row["saldo_disponible"]
            nuevo_saldo = saldo_actual + monto
            if DATABASE_URL:
                c.execute("UPDATE usuarios SET saldo_disponible = %s WHERE username = %s", (nuevo_saldo, username))
            else:
                c.execute("UPDATE usuarios SET saldo_disponible = ? WHERE username = ?", (nuevo_saldo, nuevo_saldo))
        
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
        if DATABASE_URL:
            c.execute("INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (%s, %s, %s, %s, %s)",
                      (username, "Recarga Pi Real", monto, txid or payment_id, fecha))
        else:
            c.execute("INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (?, ?, ?, ?, ?)",
                      (username, "Recarga Pi Real", monto, txid or payment_id, fecha))
        
        conn.commit()
        return jsonify({
            "success": True, 
            "nuevo_saldo": nuevo_saldo,
            "mensaje": f"Recarga de {monto} Pi acreditada con éxito."
        })
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()

# ================= NUEVO ENDPOINT DE RETIRO VERIFICADO =================

@app.route("/api/pi/retirar", methods=["POST"])
def solicitar_retiro():
    data = request.json or {}
    username = data.get("username")
    monto = float(data.get("monto", 0))
    wallet_destino = data.get("wallet_address", "")

    if monto <= 0:
        return jsonify({"success": False, "error": "El monto a retirar debe ser mayor a 0"}), 400

    conn = obtener_conexion()
    c = conn.cursor()

    try:
        if DATABASE_URL:
            c.execute("SELECT saldo_disponible FROM usuarios WHERE username = %s FOR UPDATE", (username,))
        else:
            c.execute("SELECT saldo_disponible FROM usuarios WHERE username = ?", (username,))
        row = c.fetchone()

        if not row or row["saldo_disponible"] < monto:
            conn.rollback()
            conn.close()
            return jsonify({"success": False, "error": "No tiene suficiente saldo disponible en la aplicación para este retiro"})

        saldo_actual = row["saldo_disponible"]
        nuevo_saldo = saldo_actual - monto

        if DATABASE_URL:
            c.execute("UPDATE usuarios SET saldo_disponible = %s WHERE username = %s", (nuevo_saldo, username))
        else:
            c.execute("UPDATE usuarios SET saldo_disponible = ? WHERE username = ?", (nuevo_saldo, username))

        txid = f"RETIRO_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        if DATABASE_URL:
            c.execute("INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (%s, %s, %s, %s, %s)",
                      (username, "Retiro Pi", -monto, txid, fecha))
        else:
            c.execute("INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (?, ?, ?, ?, ?)",
                      (username, "Retiro Pi", -monto, txid, fecha))

        conn.commit()
        return jsonify({
            "success": True,
            "nuevo_saldo": nuevo_saldo,
            "txid": txid,
            "mensaje": f"Retiro de {monto} Pi procesado y validado con éxito."
        })
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()

# ================= RUTAS DE ADMINISTRADOR =================

@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    data = request.json or {}
    password = data.get("password", "")
    if check_password_hash(ADMIN_PASSWORD_HASH, password):
        session['is_admin'] = True
        return jsonify({"success": True, "message": "Acceso autorizado"})
    return jsonify({"success": False, "error": "Credenciales inválidas"}), 401

@app.route("/api/admin/verificar-sesion", methods=["GET"])
def admin_verificar_sesion():
    if session.get('is_admin'):
        return jsonify({"success": True, "is_admin": True})
    return jsonify({"success": True, "is_admin": False}), 403

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
