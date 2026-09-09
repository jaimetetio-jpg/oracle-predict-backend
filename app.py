import os
from datetime import datetime
from flask import Flask, jsonify, render_template, request, redirect, url_for, session, flash
import psycopg2
from psycopg2.extras import RealDictCursor
import requests
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

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
    else:
        # Tablas con sintaxis para SQLite (respaldo)
        c.execute('''CREATE TABLE IF NOT EXISTS usuarios (username TEXT PRIMARY KEY, saldo_disponible REAL DEFAULT 0.0)''')
        c.execute('''CREATE TABLE IF NOT EXISTS transacciones (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, tipo TEXT, monto REAL, txid TEXT, fecha TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS historial_apuestas (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, titulo_evento TEXT, opcion_elegida TEXT, monto REAL, estado TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS ordenes_clob (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, evento_id INTEGER, opcion_id INTEGER, tipo_orden TEXT, accion TEXT, precio REAL, cantidad REAL, estado TEXT DEFAULT 'activa', fecha TEXT)''')
    
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
    
    # Buscar usuario en la base de datos
    if DATABASE_URL:
        c.execute("SELECT saldo_disponible FROM usuarios WHERE username = %s", (username,))
    else:
        c.execute("SELECT saldo_disponible FROM usuarios WHERE username = ?", (username,))
    row = c.fetchone()
    
    # Si el usuario no existe, lo creamos. Si es @jaimetetio, aseguramos sus 0.1 Pi de saldo inicial.
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
        
        # Blindaje extra: si es @jaimetetio y por alguna razón su saldo figuraba en 0.0, lo restauramos a 0.1 Pi
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

    # Obtener historial de apuestas del usuario
    if DATABASE_URL:
        c.execute("SELECT * FROM historial_apuestas WHERE username = %s ORDER BY id DESC", (username,))
    else:
        c.execute("SELECT * FROM historial_apuestas WHERE username = ? ORDER BY id DESC", (username,))
    historial = [dict(row) for row in c.fetchall()]

    # Obtener historial de transacciones y retiros
    if DATABASE_URL:
        c.execute("SELECT * FROM transacciones WHERE username = %s ORDER BY id DESC", (username,))
    else:
        c.execute("SELECT * FROM transacciones WHERE username = ? ORDER BY id DESC", (username,))
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

    if monto <= 0:
        return jsonify({"success": False, "error": "El monto de la participación debe ser mayor a 0"}), 400

    conn = obtener_conexion()
    c = conn.cursor()

    try:
        if DATABASE_URL:
            # Bloqueo exclusivo de la fila del usuario para evitar condiciones de carrera (Supabase/PostgreSQL ACID)
            c.execute("SELECT saldo_disponible FROM usuarios WHERE username = %s FOR UPDATE", (username,))
        else:
            c.execute("SELECT saldo_disponible FROM usuarios WHERE username = ?", (username,))
        
        row = c.fetchone()
        
        saldo_actual = row["saldo_disponible"] if row else 0
        if not row or saldo_actual < monto:
            conn.rollback()
            conn.close()
            return jsonify({"success": False, "error": "Saldo insuficiente para completar la operación"})

        evento = next((e for e in EVENTOS if e["id"] == evento_id), None)
        if not evento or evento["estado"] != "activo":
            conn.rollback()
            conn.close()
            return jsonify({"success": False, "error": "Mercado no disponible o finalizado"})

        opcion = next((o for o in evento["opciones"] if o["id"] == opcion_id), None)
        if not opcion:
            conn.rollback()
            conn.close()
            return jsonify({"success": False, "error": "Opción de predicción inválida"})

        nuevo_saldo = saldo_actual - monto
        
        if DATABASE_URL:
            c.execute("UPDATE usuarios SET saldo_disponible = %s WHERE username = %s", (nuevo_saldo, username))
        else:
            c.execute("UPDATE usuarios SET saldo_disponible = ? WHERE username = ?", (nuevo_saldo, username))
        
        opcion["pozo"] += monto

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

    if not PI_API_KEY:
        return jsonify({"success": False, "error": "PI_API_KEY no configurada en el servidor"}), 500

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
                      (username, "Recarga Pi", monto, txid or payment_id, fecha))
        else:
            c.execute("INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (?, ?, ?, ?, ?)",
                      (username, "Recarga Pi", monto, txid or payment_id, fecha))
        
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
    tipo_orden = data.get("tipo_orden", "limit").lower()  # 'limit' o 'market'
    accion = data.get("accion", "compra").lower()          # 'compra' o 'venta'
    cantidad = float(data.get("cantidad", 0))              # Monto en Pi
    precio = float(data.get("precio", 0.5))                # Requerido para Limit

    if not username or cantidad <= 0:
        return jsonify({"success": False, "error": "Datos de orden inválidos o saldo faltante"}), 400

    conn = obtener_conexion()
    c = conn.cursor()

    try:
        # Bloqueo de fila ACID del usuario
        if DATABASE_URL:
            c.execute("SELECT saldo_disponible FROM usuarios WHERE username = %s FOR UPDATE", (username,))
        else:
            c.execute("SELECT saldo_disponible FROM usuarios WHERE username = ?", (username,))
        
        row = c.fetchone()
        saldo_actual = row["saldo_disponible"] if row else 0

        if saldo_actual < cantidad:
            conn.rollback()
            return jsonify({"success": False, "error": "Saldo insuficiente para procesar la orden CLOB"})

        # Descontar saldo temporalmente para asegurar la operación
        nuevo_saldo = saldo_actual - cantidad
        if DATABASE_URL:
            c.execute("UPDATE usuarios SET saldo_disponible = %s WHERE username = %s", (nuevo_saldo, username))
        else:
            c.execute("UPDATE usuarios SET saldo_disponible = ? WHERE username = ?", (nuevo_saldo, username))

        fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
        evento = next((e for e in EVENTOS if e["id"] == evento_id), None)
        titulo_evento = evento["titulo"] if evento else f"Evento {evento_id}"

        # ==========================================
        # CASO A: ORDEN MARKET (Ejecución Instantánea)
        # ==========================================
        if tipo_orden == "market":
            # Comisión del 1.5% aplicada al Taker de Mercado
            comision_taker = cantidad * 0.015
            monto_efectivo = cantidad - comision_taker

            txid = f"CLOB_MKT_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            if DATABASE_URL:
                c.execute("INSERT INTO ordenes_clob (username, evento_id, opcion_id, tipo_orden, accion, precio, cantidad, estado, fecha) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                          (username, evento_id, opcion_id, "market", accion, 0.0, cantidad, "completada", fecha))
                c.execute("INSERT INTO historial_apuestas (username, titulo_evento, opcion_elegida, monto, estado) VALUES (%s, %s, %s, %s, %s)",
                          (username, titulo_evento, f"Opción {opcion_id} [Market]", monto_efectivo, "Ejecutada"))
                c.execute("INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (%s, %s, %s, %s, %s)",
                          (username, "Comisión CLOB Market (1.5%)", -comision_taker, txid, fecha))
            else:
                c.execute("INSERT INTO ordenes_clob (username, evento_id, opcion_id, tipo_orden, accion, precio, cantidad, estado, fecha) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          (username, evento_id, opcion_id, "market", accion, 0.0, cantidad, "completada", fecha))
                c.execute("INSERT INTO historial_apuestas (username, titulo_evento, opcion_elegida, monto, estado) VALUES (?, ?, ?, ?, ?)",
                          (username, titulo_evento, f"Opción {opcion_id} [Market]", monto_efectivo, "Ejecutada"))
                c.execute("INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (?, ?, ?, ?, ?)",
                          (username, "Comisión CLOB Market (1.5%)", -comision_taker, txid, fecha))

            conn.commit()
            return jsonify({
                "success": True, 
                "nuevo_saldo": nuevo_saldo, 
                "mensaje": "¡Orden Market ejecutada al instante! (Comisión aplicada: 1.5%)"
            })

        # ==========================================
        # CASO B: ORDEN LIMIT (Libro de Órdenes)
        # ==========================================
        else:
            if precio <= 0 or precio >= 1:
                conn.rollback()
                return jsonify({"success": False, "error": "Precio Limit fuera de rango (debe ser entre 0 y 1)"}), 400

            if DATABASE_URL:
                c.execute("INSERT INTO ordenes_clob (username, evento_id, opcion_id, tipo_orden, accion, precio, cantidad, estado, fecha) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                          (username, evento_id, opcion_id, "limit", accion, precio, cantidad, "activa", fecha))
            else:
                c.execute("INSERT INTO ordenes_clob (username, evento_id, opcion_id, tipo_orden, accion, precio, cantidad, estado, fecha) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          (username, evento_id, opcion_id, "limit", accion, precio, cantidad, "activa", fecha))

            conn.commit()
            return jsonify({
                "success": True, 
                "nuevo_saldo": nuevo_saldo, 
                "mensaje": f"Orden Limit registrada en el CLOB al precio de {precio} (Esperando Maker/Match)"
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
    
    # Comprobación segura mediante hash automático
    if check_password_hash(ADMIN_PASSWORD_HASH, password):
        session['is_admin'] = True
        return jsonify({"success": True, "message": "Acceso de administrador autorizado"})
    
    return jsonify({"success": False, "error": "Credenciales inválidas"}), 401

@app.route("/api/admin/pendientes", methods=["GET"])
def admin_pendientes():
    if not session.get('is_admin'):
        return jsonify({"success": False, "error": "No autorizado"}), 403
        
    pendientes = [e for e in EVENTOS if e["estado"] == "activo"]
    return jsonify({"success": True, "mercados": pendientes})

@app.route("/api/resolver", methods=["POST"])
def resolver_evento():
    if not session.get('is_admin'):
        return jsonify({"success": False, "error": "No autorizado"}), 403

    data = request.json
    evento_id = data.get("evento_id")
    ganador_id = data.get("ganador_id")

    evento = next((e for e in EVENTOS if e["id"] == evento_id), None)
    if not evento:
        return jsonify({"success": False, "error": "Evento no encontrado"})

    evento["estado"] = "finalizado"
    evento["ganador_id"] = ganador_id
    return jsonify({"success": True, "mensaje": "Evento resuelto correctamente"})

# --- GESTIÓN Y AUDITORÍA DE USUARIOS ---

@app.route("/api/admin/usuarios", methods=["GET"])
def admin_listar_usuarios():
    """Lista todos los usuarios registrados y sus saldos"""
    if not session.get('is_admin'):
        return jsonify({"success": False, "error": "No autorizado"}), 403

    conn = obtener_conexion()
    c = conn.cursor()
    c.execute("SELECT username, saldo_disponible FROM usuarios ORDER BY saldo_disponible DESC")
    usuarios = [dict(row) for row in c.fetchall()]
    conn.close()

    return jsonify({"success": True, "usuarios": usuarios})

@app.route("/api/admin/usuario/<username>", methods=["GET"])
def admin_detalle_usuario(username):
    """Consulta el detalle, apuestas y transacciones de un usuario específico"""
    if not session.get('is_admin'):
        return jsonify({"success": False, "error": "No autorizado"}), 403

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
        c.execute("SELECT * FROM historial_apuestas WHERE username = %s ORDER BY id DESC", (username,))
    else:
        c.execute("SELECT * FROM historial_apuestas WHERE username = ? ORDER BY id DESC", (username,))
    apuestas = [dict(row) for row in c.fetchall()]

    if DATABASE_URL:
        c.execute("SELECT * FROM transacciones WHERE username = %s ORDER BY id DESC", (username,))
    else:
        c.execute("SELECT * FROM transacciones WHERE username = ? ORDER BY id DESC", (username,))
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
    """Ajusta de forma manual el saldo de un usuario"""
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
            conn.rollback()
            conn.close()
            return jsonify({"success": False, "error": "Usuario no encontrado en la base de datos"}), 404

        saldo_actual = row["saldo_disponible"]
        nuevo_saldo = saldo_actual + monto_ajuste

        if nuevo_saldo < 0:
            conn.rollback()
            conn.close()
            return jsonify({"success": False, "error": "El saldo resultante no puede ser negativo"}), 400

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
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
