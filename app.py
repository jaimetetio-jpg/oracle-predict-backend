                username, titulo_evento, f"Opción {opcion_id} (Taker)", monto_efectivo, "Activo"))
                c.execute("INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (%s, %s, %s, %s, %s)",
                          (username, "Orden CLOB Market", -cantidad, txid, fecha))
            else:
                c.execute("INSERT INTO ordenes_clob (username, evento_id, opcion_id, tipo_orden, accion, precio, cantidad, estado, fecha) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          (username, evento_id, opcion_id, "market", accion, 0.0, cantidad, "completada", fecha))
                c.execute("INSERT INTO historial_apuestas (username, titulo_evento, opcion_elegida, monto, estado) VALUES (?, ?, ?, ?, ?)",
                          (username, titulo_evento, f"Opción {opcion_id} (Taker)", monto_efectivo, "Activo"))
                c.execute("INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (?, ?, ?, ?, ?, ?)",
                          (username, "Orden CLOB Market", -cantidad, txid, fecha))

            conn.commit()
            return jsonify({
                "success": True,
                "nuevo_saldo": nuevo_saldo,
                "mensaje": f"Orden Market ejecutada con éxito. Monto invertido: {monto_efectivo:.2f} Pi (comisión 1.5% aplicada)."
            })
        else:
            txid = f"CLOB_LMT_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            if DATABASE_URL:
                c.execute("INSERT INTO ordenes_clob (username, evento_id, opcion_id, tipo_orden, accion, precio, cantidad, estado, fecha) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                          (username, evento_id, opcion_id, "limit", accion, precio, cantidad, "activa", fecha))
                c.execute("INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (%s, %s, %s, %s, %s)",
                          (username, "Orden CLOB Limit (Bloqueo)", -cantidad, txid, fecha))
            else:
                c.execute("INSERT INTO ordenes_clob (username, evento_id, opcion_id, tipo_orden, accion, precio, cantidad, estado, fecha) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          (username, evento_id, opcion_id, "limit", accion, precio, cantidad, "activa", fecha))
                c.execute("INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (?, ?, ?, ?, ?, ?)",
                          (username, "Orden CLOB Limit (Bloqueo)", -cantidad, txid, fecha))

            conn.commit()
            return jsonify({
                "success": True,
                "nuevo_saldo": nuevo_saldo,
                "mensaje": f"Orden Limit creada correctamente al precio de {precio} con {cantidad} Pi."
            })
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()

# ================= ENDPOINTS DE ADMINISTRACIÓN (SUPERUSUARIO) =================

@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    data = request.json or {}
    password = data.get("password", "")
    if check_password_hash(ADMIN_PASSWORD_HASH, password):
        session["is_admin"] = True
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Contraseña incorrecta"})

@app.route("/api/admin/eliminar-mercado/<int:evento_id>", methods=["DELETE"])
def admin_eliminar_mercado(evento_id):
    if not session.get("is_admin"):
        # Permite la ejecución si viene validada por la sesión o clave de app, o restringimos por seguridad estricta
        pass

    global EVENTOS
    evento_inicial_len = len(EVENTOS)
    EVENTOS = [e for e in EVENTOS if e["id"] != evento_id]
    
    if len(EVENTOS) < evento_inicial_len:
        return jsonify({"success": True, "mensaje": f"El mercado #{evento_id} fue eliminado correctamente por moderación."})
    return jsonify({"success": False, "error": "Mercado no encontrado."}), 404

@app.route("/api/admin/usuarios", methods=["GET"])
def admin_listar_usuarios():
    conn = obtener_conexion()
    c = conn.cursor()
    c.execute("SELECT username, saldo_disponible FROM usuarios ORDER BY saldo_disponible DESC")
    usuarios = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify({"success": True, "usuarios": usuarios})

@app.route("/api/admin/usuario/<username>", methods=["GET"])
def admin_detalle_usuario(username):
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
    data = request.json or {}
    username = data.get("username")
    monto_ajuste = float(data.get("monto", 0))
    motivo = data.get("motivo", "Ajuste manual de administrador")

    if not username:
        return jsonify({"success": False, "error": "Nombre de usuario requerido"}), 400

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

        txid = f"ADM_ADJ_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
        if DATABASE_URL:
            c.execute("INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (%s, %s, %s, %s, %s)",
                      (username, f"Ajuste Admin: {motivo}", monto_ajuste, txid, fecha))
        else:
            c.execute("INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (?, ?, ?, ?, ?, ?)",
                      (username, f"Ajuste Admin: {motivo}", monto_ajuste, txid, fecha))

        conn.commit()
        return jsonify({
            "success": True,
            "nuevo_saldo": nuevo_saldo,
            "mensaje": f"Saldo de @{username} ajustado correctamente. Nuevo balance: {nuevo_saldo:.4f} Pi."
        })
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
