@app.route("/api/pi/retirar", methods=["POST"])
def solicitar_retiro():
    data = request.json or {}
    username = data.get("username")
    monto = float(data.get("monto", 0))
    wallet_destino = data.get("wallet_address", "")

    if monto <= 0:
        return jsonify({"success": False, "error": "El monto a retirar debe ser mayor a 0"}), 400

    if not PI_API_KEY:
        return jsonify({"success": False, "error": "PI_API_KEY no configurada en el servidor"}), 500

    conn = obtener_conexion()
    c = conn.cursor()

    try:
        # 1. Validación de saldo atómica con bloqueo de fila
        if DATABASE_URL:
            c.execute("SELECT saldo_disponible FROM usuarios WHERE username = %s FOR UPDATE", (username,))
        else:
            c.execute("SELECT saldo_disponible FROM usuarios WHERE username = ?", (username,))
        row = c.fetchone()

        if not row or row["saldo_disponible"] < monto:
            conn.rollback()
            conn.close()
            return jsonify({"success": False, "error": "Saldo insuficiente para procesar el retiro"})

        saldo_actual = row["saldo_disponible"]
        nuevo_saldo = saldo_actual - monto

        # 2. Descuento temporal en base de datos local
        if DATABASE_URL:
            c.execute("UPDATE usuarios SET saldo_disponible = %s WHERE username = %s", (nuevo_saldo, username))
        else:
            c.execute("UPDATE usuarios SET saldo_disponible = ? WHERE username = ?", (nuevo_saldo, username))

        # 3. Petición A2U (App-to-User) al servidor de Pi Network para el pago saliente
        headers = {"Authorization": f"Key {PI_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "amount": monto,
            "uid": username, # O el UID de Pi del usuario si lo almacenas
            "memo": f"Retiro automático desde P2PPredict hacia {wallet_destino}",
            "metadata": {"wallet": wallet_destino}
        }
        
        pi_response = requests.post("https://api.minepi.com/v2/payments", json=payload, headers=headers, timeout=10)
        
        if pi_response.status_code not in [200, 201]:
            # Si Pi Network rechaza el pago, revertimos la transacción localmente
            conn.rollback()
            conn.close()
            return jsonify({"success": False, "error": "La pasarela de Pi Network rechazó el desembolso"}), 400

        pi_data = pi_response.json()
        txid = pi_data.get("txid", f"RETIRO_{datetime.now().strftime('%Y%m%d%H%M%S')}")
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        if DATABASE_URL:
            c.execute("INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (%s, %s, %s, %s, %s)",
                      (username, "Retiro Pi Blockchain", -monto, txid, fecha))
        else:
            c.execute("INSERT INTO transacciones (username, tipo, monto, txid, fecha) VALUES (?, ?, ?, ?, ?)",
                      (username, "Retiro Pi Blockchain", -monto, txid, fecha))

        conn.commit()
        return jsonify({
            "success": True,
            "nuevo_saldo": nuevo_saldo,
            "txid": txid,
            "mensaje": f"Retiro de {monto} Pi procesado y enviado a la red con éxito."
        })
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()
