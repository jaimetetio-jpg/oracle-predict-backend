import os
from flask import Flask, jsonify, request, render_template

app = Flask(__name__)

# Base de datos en memoria para el evento activo (con el 2% de comisión integrado)
evento_activo = {
    "id": 1,
    "titulo": "¿Ganará el equipo local hoy?",
    "pozo_premios": 0.0,       # 98% para el pozo del ganador
    "comision_casa": 0.0,      # Tu 2% de comisión acumulado
    "pool_total": 0.0,         # Total recaudado
    "participantes": []
}

# Ruta principal que carga tu página web
@app.route('/')
def index():
    # Asegúrate de tener tu archivo index.html dentro de una carpeta llamada 'templates'
    # Si sirves la página de otra forma, puedes ajustar esto o usar render_template
    try:
        return render_template('index.html')
    except Exception:
        return "¡P2Ppredict Backend Funcionando Correctamente! 🔮"

# Ruta obligatoria de Pi Network para la validación del dominio
@app.route('/validation-key.txt')
def validation_key():
    # Si tienes el archivo físico en la raíz, Flask lo lee; si no, devuelve la clave por defecto
    try:
        return app.send_static_file('validation-key.txt')
    except Exception:
        return "332ef1d8b17e8789cb1385717cceaecf6eb79"

# 1. API para que el frontend obtenga el evento y el pozo actual
@app.route('/api/evento', methods=['GET'])
def obtener_evento():
    return jsonify(evento_activo)

# 2. API para crear una nueva predicción desde la interfaz
@app.route('/api/crear-evento', methods=['POST'])
def crear_evento():
    data = request.json or {}
    nuevo_titulo = data.get('titulo')
    
    if nuevo_titulo:
        evento_activo["titulo"] = nuevo_titulo
        evento_activo["pozo_premios"] = 0.0
        evento_activo["comision_casa"] = 0.0
        evento_activo["pool_total"] = 0.0
        evento_activo["participantes"] = []
        return jsonify({"success": True, "mensaje": "Predicción creada con éxito", "evento": evento_activo})
    
    return jsonify({"success": False, "error": "El título es obligatorio"}), 400

# 3. API para registrar la participación (con el cálculo automático del 2% de comisión)
@app.route('/api/participar', methods=['POST'])
def participar():
    data = request.json or {}
    monto_pagado = float(data.get('monto', 1.0)) # Por defecto 1 Pi
    usuario = data.get('username', 'Usuario Pi')
    
    # Calcular el 2% para ti y el 98% para el pozo de premios
    comision = monto_pagado * 0.02
    monto_para_pozo = monto_pagado * 0.98
    
    # Actualizar acumulados
    evento_activo["comision_casa"] += comision
    evento_activo["pozo_premios"] += monto_para_pozo
    evento_activo["pool_total"] += monto_pagado
    
    evento_activo["participantes"].append({
        "usuario": usuario,
        "aporte": monto_pagado
    })
    
    return jsonify({
        "success": True,
        "mensaje": "¡Participación registrada con éxito!",
        "pool_actual": round(evento_activo["pozo_premios"], 4),
        "comision_guardada": round(evento_activo["comision_casa"], 4),
        "pool_total": round(evento_activo["pool_total"], 4)
    })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
