import os
from datetime import datetime
from flask import Flask, jsonify, render_template, request, session
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
import requests
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# Configuración de CORS para permitir solicitudes del frontend de forma segura
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Configuración de clave secreta para firmar las sesiones de forma segura
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "p2ppredict_secret_key_ultra_segura_2026")

# Generación automática del hash seguro para la contraseña de administrador
RAW_ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Anthony*2023")
ADMIN_PASSWORD_HASH = generate_password_hash(RAW_ADMIN_PASSWORD)

PI_API_KEY = os.environ.get("PI_API_KEY", "")
# URL de conexión a PostgreSQL (Supabase). Si no existe, usa SQLite como respaldo local.
DATABASE_URL = os.environ.get("DATABASE_URL")

# ================= CONFIGURACIÓN DE BASE DE DATOS =================
def obtener_conexion():
    if DATABASE_URL:
        # Conexión profesional a PostgreSQL en la nube (Supabase)
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor, connect_timeout=10)
        return conn
    else:
        # Respaldo local SQLite si la URL externa no estuviera configurada
        import sqlite3
        conn = sqlite3.connect("p2ppredict.db")
        conn.row_factory = sqlite3.Row
        return conn

def inicializar_bd():
    conn = obtener_conexion()
    c = conn.cursor()
    
    if DATABASE_URL:
        # Tablas con sintaxis para PostgreSQL
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
    else:
        # Tablas con sintaxis para SQLite (respaldo)
        c.execute('''CREATE TABLE IF NOT EXISTS usuarios (username TEXT PRIMARY KEY, saldo_disponible REAL DEFAULT 0.0)''')
        c.execute('''CREATE TABLE IF NOT EXISTS transacciones (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, tipo TEXT, monto REAL, txid TEXT, fecha TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS historial_apuestas (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, titulo_evento TEXT, opcion_elegida TEXT, monto REAL, estado TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS ordenes_clob (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, evento_id INTEGER, opcion_id INTEGER, tipo_orden TEXT, accion TEXT, precio REAL, cantidad REAL, estado TEXT DEFAULT 'activa', fecha TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS eventos (id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT, categoria TEXT, estado TEXT DEFAULT 'activo', fecha_cierre TEXT, ganador_id INTEGER)''')
        c.execute('''CREATE TABLE IF NOT EXISTS opciones_evento (id INTEGER PRIMARY KEY AUTOINCREMENT, evento_id INTEGER, nombre TEXT, pozo REAL DEFAULT 0.0)''')
        c.execute('''CREATE TABLE IF NOT EXISTS admin_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, ip TEXT, accion TEXT, detalles TEXT, fecha TEXT)''')
    
    conn.commit()

    # Poblar eventos iniciales si la tabla está vacía
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

# Inicializar la BD al arrancar la app
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
        saldo = row["saldo_disponible"]
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
                txid = f"RESTAURACION_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
                c.execute("INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (?, ?, ?, ?, ?)",
                          (username, "Restauración Saldo Pi", saldo, txid, fecha))
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
    data = request.json
    username = data.get("username", "Invitado")
    evento_id = data.get("evento_id")
    opcion_id = data.get("opcion_id")
    monto = float(data.get("monto", 0))

    if monto <= 0:
        return jsonify({"success": False, "error": "El monto de la participación debe ser mayor a 0"}), 400

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
            return jsonify({"success": False, "error": "Saldo insuficiente para completar la operación"})

        if DATABASE_URL:
            c.execute("SELECT * FROM eventos WHERE id = %s", (evento_id,))
        else:
            c.execute("SELECT * FROM eventos WHERE id = ?", (evento_id,))
        evento = c.fetchone()
        
        if not evento or evento["estado"] != "activo":
            conn.rollback()
            conn.close()
            return jsonify({"success": False, "error": "Mercado no disponible o finalizado"})

        if DATABASE_URL:
            c.execute("SELECT * FROM opciones_evento WHERE id = %s AND evento_id = %s", (opcion_id, evento_id))
        else:
            c.execute("SELECT * FROM opciones_evento WHERE id = ? AND evento_id = ?", (opcion_id, evento_id))
        opcion = c.fetchone()
        
        if not opcion:
            conn.rollback()
            conn.close()
            return jsonify({"success": False, "error": "Opción de predicción inválida"})

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
        return jsonify({"success": False, "error": f"Error interno en la transacción: {str(e)}"}), 500
    finally:
        conn.close()

@app.route("/api/reclamar-premio", methods=["POST"])
def reclamar_premio():
    data = request.json or {}
    username = data.get("username")
    evento_id = data.get("evento_id")

    if not username or not evento_id:
        return jsonify({"success": False, "error": "Datos incompletos para reclamar premio"}), 400

    conn = obtener_conexion()
    c = conn.cursor()

    try:
        if DATABASE_URL:
            c.execute("SELECT * FROM eventos WHERE id = %s", (evento_id,))
        else:
            c.execute("SELECT * FROM eventos WHERE id = ?", (evento_id,))
        evento = c.fetchone()

        if not evento or evento["estado"] != "finalizado":
            conn.rollback()
            conn.close()
            return jsonify({"success": False, "error": "El evento no ha finalizado o no existe"})

        ganador_id = evento["ganador_id"]
        if not ganador_id:
            conn.rollback()
            conn.close()
            return jsonify({"success": False, "error": "Este evento no tiene un ganador registrado"})

        # Verificar si el usuario ya reclamó premio para este evento en el historial
        titulo_evento = evento["titulo"]
        if DATABASE_URL:
            c.execute("SELECT * FROM historial_apuestas WHERE username = %s AND titulo_evento = %s AND estado = 'Reclamado'", (username, titulo_evento))
        else:
            c.execute("SELECT * FROM historial_apuestas WHERE username = ? AND titulo_evento = ? AND estado = 'Reclamado'", (username, titulo_evento))
        if c.fetchone():
            conn.rollback()
            conn.close()
            return jsonify({"success": False, "error": "Ya has reclamado el premio de este evento."})

        # Buscar opciones y pozos
        if DATABASE_URL:
            c.execute("SELECT * FROM opciones_evento WHERE evento_id = %s", (evento_id,))
        else:
            c.execute("SELECT * FROM opciones_evento WHERE evento_id = ?", (evento_id,))
        opciones = c.fetchall()

        pozo_total = sum(op["pozo"] for op in opciones)
        opcion_ganadora = next((op for op in opciones if op["id"] == ganador_id), None)
        
        if not opcion_ganadora or opcion_ganadora["pozo"] <= 0:
            conn.rollback()
            conn.close()
            return jsonify({"success": False, "error": "No hay fondos en la opción ganadora para repartir"})

        pozo_ganador = opcion_ganadora["pozo"]

        # Buscar las apuestas del usuario para este evento y la opción ganadora
        if DATABASE_URL:
            c.execute("SELECT * FROM historial_apuestas WHERE username = %s AND titulo_evento = %s AND opcion_elegida = %s AND estado = 'Activo'", 
                      (username, titulo_evento, opcion_ganadora["nombre"]))
        else:
            c.execute("SELECT * FROM historial_apuestas WHERE username = ? AND titulo_evento = ? AND opcion_elegida = ? AND estado = 'Activo'", 
                      (username, titulo_evento, opcion_ganadora["nombre"]))
        apuestas_usuario = c.fetchall()

        if not apuestas_usuario:
            conn.rollback()
            conn.close()
            return jsonify({"success": False, "error": "No posees apuestas activas en la opción ganadora de este evento"})

        monto_apostado_usuario = sum(ap["monto"] for ap in apuestas_usuario)
        
        # Cálculo proporcional: (monto_apostado_usuario / pozo_ganador) * pozo_total
        premio = (monto_apostado_usuario / pozo_ganador) * pozo_total

        # Actualizar saldo del usuario
        if DATABASE_URL:
            c.execute("SELECT saldo_disponible FROM usuarios WHERE username = %s FOR UPDATE", (username,))
        else:
            c.execute("SELECT saldo_disponible FROM usuarios WHERE username = ?", (username,))
        user_row = c.fetchone()
        nuevo_saldo = user_row["saldo_disponible"] + premio

        if DATABASE_URL:
            c.execute("UPDATE usuarios SET saldo_disponible = %s WHERE username = %s", (nuevo_saldo, username))
            c.execute("UPDATE historial_apuestas SET estado = 'Reclamado' WHERE username = %s AND titulo_evento = %s AND opcion_elegida = %s AND estado = 'Activo'",
                      (username, titulo_evento, opcion_ganadora["nombre"]))
        else:
            c.execute("UPDATE usuarios SET saldo_disponible = ? WHERE username = ?", (nuevo_saldo, username))
            c.execute("UPDATE historial_apuestas SET estado = 'Reclamado' WHERE username = ? AND titulo_evento = ? AND opcion_elegida = ? AND estado = 'Activo'",
                      (username, titulo_evento, opcion_ganadora["nombre"]))

        txid = f"CLAIM_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
        if DATABASE_URL:
            c.execute("INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (%s, %s, %s, %s, %s)",
                      (username, "Premio Reclamado", premio, txid, fecha))
        else:
            c.execute("INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (?, ?, ?, ?, ?)",
                      (username, "Premio Reclamado", premio, txid, fecha))

        conn.commit()
        return jsonify({
            "success": True,
            "nuevo_saldo": nuevo_saldo,
            "premio": premio,
            "mensaje": f"¡Premio reclamado con éxito! Has recibido {premio:.2f} Pi."
        })
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()

@app.route("/api/pi/aprobar-pago", methods=["POST"])
def aprobar_pago():
    data = request.json
    payment_id = data.get("paymentId")
    if not PI_API_KEY:
        return jsonify({"success": False, "error": "PI_API_KEY no configurada en el servidor"}), 500

    headers = {"Authorization": f"Key {PI_API_KEY}"}
    try:
        response = requests.post(f"https://api.minepi.com/v2/payments/{payment_id}/approve", headers=headers, timeout=10)
        if response.status_code == 200:
            return jsonify({"success": True})
    except requests.exceptions.RequestException:
        return jsonify({"success": False, "error": "Error de red al conectar con los servidores de Pi Network"}), 504
        
    return jsonify({"success": False, "error": "No se pudo aprobar el pago en el servidor de Pi"}), 400

@app.route("/api/pi/completar-pago", methods=["POST"])
def completar_pago():
    data = request.json
    username = data.get("username")
    monto = float(data.get("monto", 0))
    payment_id = data.get("paymentId")
    txid = data.get("txid")

    if PI_API_KEY:
        headers = {"Authorization": f"Key {PI_API_KEY}"}
        try:
            response = requests.post(f"https://api.minepi.com/v2/payments/{payment_id}/complete", headers=headers, json={"txid": txid}, timeout=10)
            if response.status_code != 200:
                return jsonify({"success": False, "error": "Error al completar el pago en Pi Network"}), 400
        except requests.exceptions.RequestException:
            return jsonify({"success": False, "error": "Error de red al conectar con los servidores de Pi Network"}), 504

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
                c.execute("UPDATE usuarios SET saldo_disponible = ? WHERE username = ?", (nuevo_saldo, username))
        
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
        if DATABASE_URL:
            c.execute("INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (%s, %s, %s, %s, %s)",
                      (username, "Recarga Pi", monto, txid or payment_id or "SIMULATED_TX", fecha))
        else:
            c.execute("INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (?, ?, ?, ?, ?)",
                      (username, "Recarga Pi", monto, txid or payment_id or "SIMULATED_TX", fecha))
        
        conn.commit()
        return jsonify({
            "success": True, 
            "nuevo_saldo": nuevo_saldo,
            "mensaje": f"Recarga de {monto} Pi acreditada con éxito."
        })
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": f"Error al procesar la base de datos: {str(e)}"}), 500
    finally:
        conn.close()

@app.route("/api/retirar", methods=["POST"])
def solicitar_retiro():
    data = request.json
    username = data.get("username")
    monto = float(data.get("monto", 0))

    if monto <= 0:
        return jsonify({"success": False, "error": "El monto del retiro debe ser mayor a 0"}), 400

    conn = obtener_conexion()
    c = conn.cursor()

    try:
        if DATABASE_URL:
            c.execute("SELECT saldo_disponible FROM usuarios WHERE username = %s FOR UPDATE", (username,))
        else:
            c.execute("SELECT saldo_disponible FROM usuarios WHERE username = ?", (username,))
        row = c.fetchone()

        if not row:
            conn.rollback()
            conn.close()
            return jsonify({"success": False, "error": "Usuario no encontrado"}), 404

        saldo_actual = row["saldo_disponible"]
        if saldo_actual < monto:
            conn.rollback()
            conn.close()
            return jsonify({"success": False, "error": "Saldo insuficiente para procesar el retiro"}), 400

        nuevo_saldo = saldo_actual - monto
        if DATABASE_URL:
            c.execute("UPDATE usuarios SET saldo_disponible = %s WHERE username = %s", (nuevo_saldo, username))
        else:
            c.execute("UPDATE usuarios SET saldo_disponible = ? WHERE username = ?", (nuevo_saldo, username))
        
        txid = f"RET_{datetime.now().strftime('%Y%m%d%H%M%S')}"
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
            "mensaje": f"Retiro de {monto} Pi procesado correctamente."
        })
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()

@app.route("/api/leaderboard", methods=["GET"])
def leaderboard():
    conn = obtener_conexion()
    c = conn.cursor()
    c.execute("SELECT username, saldo_disponible FROM usuarios ORDER BY saldo_disponible DESC LIMIT 10")
    ranking = [{"username": row["username"], "ganancias_netas": row["saldo_disponible"]} for row in c.fetchall()]
    conn.close()
    return jsonify({"success": True, "leaderboard": ranking})

# ================= ENDPOINT CLOB (LIMIT & MARKET) =================

@app.route("/api/clob/orden", methods=["POST"])
def procesar_orden_clob():
    data = request.json or {}
    username = data.get("username")
    evento_id = data.get("evento_id")
    opcion_id = data.get("opcion_id")
    tipo_orden = data.get("tipo_orden", "limit").lower()
    accion = data.get("accion", "compra").lower()
    cantidad = float(data.get("cantidad", 0))
    precio = float(data.get("precio", 0.5))

    if not username or cantidad <= 0:
        return jsonify({"success": False, "error": "Datos de orden inválidos o saldo faltante"}), 400

    conn = obtener_conexion()
    c = conn.cursor()

    try:
        if DATABASE_URL:
            c.execute("SELECT saldo_disponible FROM usuarios WHERE username = %s FOR UPDATE", (username,))
        else:
            c.execute("SELECT saldo_disponible FROM usuarios WHERE username = ?", (username,))
        
        row = c.fetchone()
        saldo_actual = row["saldo_disponible"] if row else 0

        if saldo_actual < cantidad:
            conn.rollback()
            return jsonify({"success": False, "error": "Saldo insuficiente para procesar la orden CLOB"})

        nuevo_saldo = saldo_actual - cantidad
        if DATABASE_URL:
            c.execute("UPDATE usuarios SET saldo_disponible = %s WHERE username = %s", (nuevo_saldo, username))
        else:
            c.execute("UPDATE usuarios SET saldo_disponible = ? WHERE username = ?", (nuevo_saldo, username))

        fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        if DATABASE_URL:
            c.execute("SELECT titulo FROM eventos WHERE id = %s", (evento_id,))
        else:
            c.execute("SELECT titulo FROM eventos WHERE id = ?", (evento_id,))
        ev_row = c.fetchone()
        titulo_evento = ev_row["titulo"] if ev_row else f"Evento {evento_id}"

        if tipo_orden == "market":
            comision_taker = cantidad * 0.015
            monto_efectivo = cantidad - comision_taker
            txid = f"CLOB_MKT_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            if DATABASE_URL:
                c.execute("INSERT INTO ordenes_clob (username, evento_id, opcion_id, tipo_orden, accion, precio, cantidad, estado, fecha) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                          (username, evento_id, opcion_id, "market", accion, 0.0, cantidad, "completada", fecha))
                c.execute("INSERT INTO historial_apuestas (username, titulo_evento, opcion_elegida, monto, estado) VALUES (%s, %s, %s, %s, %s)",
                          (username, titulo_evento, f"Opción {opcion_id} [Market]", monto_efectivo, "Activo"))
                c.execute("INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (%s, %s, %s, %s, %s)",
                          (username, "Comisión CLOB Market (1.5%)", -comision_taker, txid, fecha))
            else:
                c.execute("INSERT INTO ordenes_clob (username, evento_id, opcion_id, tipo_orden, accion, precio, cantidad, estado, fecha) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          (username, evento_id, opcion_id, "market", accion, 0.0, cantidad, "completada", fecha))
                c.execute("INSERT INTO historial_apuestas (username, titulo_evento, opcion_elegida, monto, estado) VALUES (?, ?, ?, ?, ?)",
                          (username, titulo_evento, f"Opción {opcion_id} [Market]", monto_efectivo, "Activo"))
                c.execute("INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (?, ?, ?, ?, ?)",
                          (username, "Comisión CLOB Market (1.5%)", -comision_taker, txid, fecha))

            conn.commit()
            return jsonify({
                "success": True, 
                "nuevo_saldo": nuevo_saldo, 
                "mensaje": "¡Orden Market ejecutada al instante! (Comisión aplicada: 1.5%)"
            })
        else:
            if precio <= 0 or precio >= 1:
                conn.rollback()
                return jsonify({"success": False, "error": "Precio Limit fuera de rango (debe ser entre 0 y 1)"}), 400

            txid = f"CLOB_LMT_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            if DATABASE_URL:
                c.execute("INSERT INTO ordenes_clob (username, evento_id, opcion_id, tipo_orden, accion, precio, cantidad, estado, fecha) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                          (username, evento_id, opcion_id, "limit", accion, precio, cantidad, "activa", fecha))
                c.execute("INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (%s, %s, %s, %s, %s)",
                          (username, "Orden CLOB Limit (Bloqueo)", -cantidad, txid, fecha))
            else:
                c.execute("INSERT INTO ordenes_clob (username, evento_id, opcion_id, tipo_orden, accion, precio, cantidad, estado, fecha) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          (username, evento_id, opcion_id, "limit", accion, precio, cantidad, "activa", fecha))
                c.execute("INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (?, ?, ?, ?, ?)",
                          (username, "Orden CLOB Limit (Bloqueo)", -cantidad, txid, fecha))

            conn.commit()
            return jsonify({
                "success": True, 
                "nuevo_saldo": nuevo_saldo, 
                "mensaje": f"Orden Limit registrada en el CLOB al precio de {precio}"
            })

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()

# ================= RUTAS DE ADMINISTRADOR BLINDADAS Y EXTENDIDAS =================

@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    data = request.json or {}
    password = data.get("password", "")
    
    if check_password_hash(ADMIN_PASSWORD_HASH, password):
        session['is_admin'] = True
        registrar_log_admin("LOGIN_EXITOSO", "Administrador autenticado correctamente")
        return jsonify({"success": True, "message": "Acceso de administrador autorizado"})
    
    registrar_log_admin("LOGIN_FALLIDO", "Intento fallido de acceso al panel de administración")
    return jsonify({"success": False, "error": "Credenciales inválidas"}), 401

@app.route("/api/admin/pendientes", methods=["GET"])
def admin_pendientes():
    if not session.get('is_admin'):
        return jsonify({"success": False, "error": "No autorizado"}), 403
        
    eventos = obtener_eventos_completos()
    pendientes = [e for e in eventos if e["estado"] == "activo"]
    return jsonify({"success": True, "mercados": pendientes})

@app.route("/api/resolver", methods=["POST"])
def resolver_evento():
    if not session.get('is_admin'):
        return jsonify({"success": False, "error": "No autorizado"}), 403

    data = request.json
    evento_id = data.get("evento_id")
    ganador_id = data.get("ganador_id")

    conn = obtener_conexion()
    c = conn.cursor()
    try:
        if DATABASE_URL:
            c.execute("UPDATE eventos SET estado = 'finalizado', ganador_id = %s WHERE id = %s", (ganador_id, evento_id))
        else:
            c.execute("UPDATE eventos SET estado = 'finalizado', ganador_id = ? WHERE id = ?", (ganador_id, evento_id))
        conn.commit()
        registrar_log_admin("RESOLVER_EVENTO", f"Evento #{evento_id} finalizado con ganador ID: {ganador_id}")
        return jsonify({"success": True, "mensaje": "Evento resuelto correctamente"})
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()

@app.route("/api/admin/eliminar-mercado/<int:evento_id>", methods=["DELETE"])
def admin_eliminar_mercado(evento_id):
    if not session.get('is_admin'):
        return jsonify({"success": False, "error": "No autorizado"}), 403

    conn = obtener_conexion()
    c = conn.cursor()
    try:
        if DATABASE_URL:
            c.execute("DELETE FROM opciones_evento WHERE evento_id = %s", (evento_id,))
            c.execute("DELETE FROM eventos WHERE id = %s", (evento_id,))
        else:
            c.execute("DELETE FROM opciones_evento WHERE evento_id = ?", (evento_id,))
            c.execute("DELETE FROM eventos WHERE id = ?", (evento_id,))
        conn.commit()
        registrar_log_admin("ELIMINAR_MERCADO", f"Mercado #{evento_id} eliminado")
        return jsonify({"success": True, "mensaje": f"El mercado #{evento_id} fue eliminado correctamente por moderación."})
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()

@app.route("/api/admin/limpiar-mercados-vacios", methods=["POST"])
def admin_limpiar_mercados_vacios():
    if not session.get('is_admin'):
        return jsonify({"success": False, "error": "No autorizado"}), 403

    eventos = obtener_eventos_completos()
    conn = obtener_conexion()
    c = conn.cursor()
    eliminados = 0
    try:
        for evento in eventos:
            pozo_total = sum(op.get("pozo", 0) for op in evento.get("opciones", []))
            if pozo_total == 0:
                ev_id = evento["id"]
                if DATABASE_URL:
                    c.execute("DELETE FROM opciones_evento WHERE evento_id = %s", (ev_id,))
                    c.execute("DELETE FROM eventos WHERE id = %s", (ev_id,))
                else:
                    c.execute("DELETE FROM opciones_evento WHERE evento_id = ?", (ev_id,))
                    c.execute("DELETE FROM eventos WHERE id = ?", (ev_id,))
                eliminados += 1
        conn.commit()
        registrar_log_admin("LIMPIAR_MERCADOS_VACIOS", f"Se eliminaron {eliminados} mercados sin liquidez")
        
        eventos_restantes = obtener_eventos_completos()
        return jsonify({
            "success": True,
            "mensaje": f"Se han eliminado {eliminados} mercados sin liquidez correctamente.",
            "mercados_restantes": len(eventos_restantes)
        })
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()

# --- GESTIÓN Y AUDITORÍA DE USUARIOS CON PAGINACIÓN Y FILTROS ---

@app.route("/api/admin/usuarios", methods=["GET"])
def admin_listar_usuarios():
    if not session.get('is_admin'):
        return jsonify({"success": False, "error": "No autorizado"}), 403

    limite = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))

    conn = obtener_conexion()
    c = conn.cursor()
    if DATABASE_URL:
        c.execute("SELECT username, saldo_disponible FROM usuarios ORDER BY saldo_disponible DESC LIMIT %s OFFSET %s", (limite, offset))
    else:
        c.execute("SELECT username, saldo_disponible FROM usuarios ORDER BY saldo_disponible DESC LIMIT ? OFFSET ?", (limite, offset))
    usuarios = [dict(row) for row in c.fetchall()]
    conn.close()

    return jsonify({"success": True, "usuarios": usuarios})

@app.route("/api/admin/usuario/<username>", methods=["GET"])
def admin_detalle_usuario(username):
    if not session.get('is_admin'):
        return jsonify({"success": False, "error": "No autorizado"}), 403

    limite = int(request.args.get("limit", 20))
    offset = int(request.args.get("offset", 0))

    conn = obtener_conexion()
    c = conn.cursor()

    if DATABASE_URL:
        c.execute("SELECT * FROM usuarios WHERE username = %s", (username,))
    else:
        c.execute("SELECT * FROM usuarios WHERE username = ?", (username,))
    user_row = c.fetchone()

    if not user_row:
        conn.close()
        return jsonify({"success": False, "error": "Usuario no encontrado"}), 404

    if DATABASE_URL:
        c.execute("SELECT * FROM historial_apuestas WHERE username = %s ORDER BY id DESC LIMIT %s OFFSET %s", (username, limite, offset))
    else:
        c.execute("SELECT * FROM historial_apuestas WHERE username = ? ORDER BY id DESC LIMIT ? OFFSET ?", (username, limite, offset))
    apuestas = [dict(row) for row in c.fetchall()]

    if DATABASE_URL:
        c.execute("SELECT * FROM transacciones WHERE username = %s ORDER BY id DESC LIMIT %s OFFSET %s", (username, limite, offset))
    else:
        c.execute("SELECT * FROM transacciones WHERE username = ? ORDER BY id DESC LIMIT ? OFFSET ?", (username, limite, offset))
    transacciones = [dict(row) for row in c.fetchall()]

    conn.close()

    return jsonify({
        "success": True,
        "usuario": dict(user_row),
        "apuestas": apuestas,
        "transacciones": transacciones
    })

@app.route("/api/admin/ajustar-saldo", methods=["POST"])
def admin_ajustar_saldo():
    if not session.get('is_admin'):
        return jsonify({"success": False, "error": "No autorizado"}), 403

    data = request.json or {}
    username = data.get("username")
    monto_ajuste = float(data.get("monto", 0))
    motivo = data.get("motivo", "Ajuste Administrativo")

    if not username:
        return jsonify({"success": False, "error": "Falta el nombre de usuario"}), 400

    conn = obtener_conexion()
    c = conn.cursor()

    try:
        if DATABASE_URL:
            c.execute("SELECT saldo_disponible FROM usuarios WHERE username = %s FOR UPDATE", (username,))
        else:
            c.execute("SELECT saldo_disponible FROM usuarios WHERE username = ?", (username,))
        row = c.fetchone()

        if not row:
            saldo_actual = 0.0
            nuevo_saldo = max(0.0, saldo_actual + monto_ajuste)
            if DATABASE_URL:
                c.execute("INSERT INTO usuarios (username, saldo_disponible) VALUES (%s, %s)", (username, nuevo_saldo))
            else:
                c.execute("INSERT INTO usuarios (username, saldo_disponible) VALUES (?, ?)", (username, nuevo_saldo))
        else:
            saldo_actual = row["saldo_disponible"]
            nuevo_saldo = max(0.0, saldo_actual + monto_ajuste)
            if DATABASE_URL:
                c.execute("UPDATE usuarios SET saldo_disponible = %s WHERE username = %s", (nuevo_saldo, username))
            else:
                c.execute("UPDATE usuarios SET saldo_disponible = ? WHERE username = ?", (nuevo_saldo, username))

        txid = f"ADMIN_ADJ_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
        if DATABASE_URL:
            c.execute("INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (%s, %s, %s, %s, %s)",
                      (username, motivo, monto_ajuste, txid, fecha))
        else:
            c.execute("INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (?, ?, ?, ?, ?)",
                      (username, motivo, monto_ajuste, txid, fecha))

        conn.commit()
        registrar_log_admin("AJUSTAR_SALDO", f"Usuario {username} ajustado por {monto_ajuste} Pi. Motivo: {motivo}")
        return jsonify({
            "success": True,
            "mensaje": f"Saldo de {username} ajustado correctamente.",
            "nuevo_saldo": nuevo_saldo
        })
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
