"""
stream.py — Servidor de transmisión web (Flask / MJPEG).
Responsabilidad única: exponer el video de la cámara por HTTP en /video.
"""

import logging
import secrets
import threading
import time

import cv2
from flask import Flask, Response, abort, request, render_template, jsonify

import state
import config

# Variable global que es escrita por ui/hud.py (_loop_video)
# y leída por generar_stream(). Vive aquí para que ambos módulos
# apunten al mismo objeto cuando hacen  import stream.
global_frame_compartido = None
_frame_lock = threading.Lock()  # Protege el acceso concurrente al frame
_conexiones_activas = 0         # Contador de streams activos

# Token de seguridad para el stream — se genera una vez al arrancar.
# La URL completa se arma en tunnel.py al obtener el enlace de Pinggy.
STREAM_TOKEN = secrets.token_urlsafe(12)  # ej: "xK9mPqR2vLsT"

# Overlay de mensajes remotos (aparece en el stream en vivo)
global_overlay = {"texto": "", "hasta": 0.0}

app_web = Flask(__name__, template_folder="web/templates")


def set_mensaje_overlay(texto: str, duracion: float = 12.0):
    """Muestra 'texto' sobreimpreso en el stream en vivo durante 'duracion' segundos."""
    global_overlay["texto"] = texto
    global_overlay["hasta"] = time.time() + duracion


def _dibujar_overlay(frame):
    """Quema el overlay activo en el frame (en la parte inferior visible del stream)."""
    if not global_overlay["texto"] or time.time() > global_overlay["hasta"]:
        return frame
    h, w = frame.shape[:2]
    texto = global_overlay["texto"]
    font       = cv2.FONT_HERSHEY_SIMPLEX
    escala     = 0.65
    grosor     = 2
    (tw, th), _ = cv2.getTextSize(texto, font, escala, grosor)
    # Fondo semitransparente (rectángulo negro)
    x0, y0 = 10, h - 20 - th
    overlay_bg = frame.copy()
    cv2.rectangle(overlay_bg, (x0 - 6, y0 - 8), (x0 + tw + 6, y0 + th + 6), (0, 0, 0), -1)
    cv2.addWeighted(overlay_bg, 0.55, frame, 0.45, 0, frame)
    # Texto con borde para legibilidad
    cv2.putText(frame, texto, (x0, y0 + th), font, escala, (0, 0, 0),   grosor + 2)
    cv2.putText(frame, texto, (x0, y0 + th), font, escala, (0, 229, 255), grosor)
    return frame


def set_frame(frame):
    """Escribe el frame de forma segura desde cualquier hilo."""
    global global_frame_compartido
    with _frame_lock:
        global_frame_compartido = frame


def get_frame():
    """Lee una copia del frame de forma segura desde cualquier hilo."""
    with _frame_lock:
        return global_frame_compartido.copy() if global_frame_compartido is not None else None


def generar_stream():
    global _conexiones_activas
    _conexiones_activas += 1
    try:
        while True:
            frame_out = get_frame()
            if frame_out is None:
                time.sleep(0.15)
                continue

            _dibujar_overlay(frame_out)

            # Calidad adaptativa: si hay muchas conexiones, reducir calidad para no sobrecargar Pinggy
            calidad = 50 if _conexiones_activas > 1 else 60
            ret, buffer = cv2.imencode(
                ".jpg", frame_out, [cv2.IMWRITE_JPEG_QUALITY, calidad]
            )
            if not ret:
                continue

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
            )
            time.sleep(0.067)  # ~15 fps — menos carga en Pinggy
    finally:
        _conexiones_activas -= 1


@app_web.route("/")
def index():
    html = """
    <html>
      <head><title>E.M.E.L.Y Security</title><meta name="viewport" content="width=device-width, initial-scale=1"></head>
      <body style="background: black; color: white; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; font-family: monospace;">
        <h1>E.M.E.L.Y TACTICAL SERVER</h1>
      </body>
    </html>
    """
    return html


def check_token():
    if request.args.get("t") != STREAM_TOKEN:
        abort(403)


@app_web.route("/video")
def video():
    check_token()
    return Response(generar_stream(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app_web.route("/panel")
def panel():
    check_token()
    return render_template("panel.html", token=STREAM_TOKEN)


# --- API ENDPOINTS ---

@app_web.route("/api/estado", methods=["GET"])
def api_estado():
    check_token()
    s = state.get()
    
    cpu = 0.0
    ram = 0.0
    disk = 0.0
    try:
        import psutil
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        disk = psutil.disk_usage('/').percent
    except ImportError:
        pass
        
    return jsonify({
        "modo": s["modo"],
        "total_alertas": s["total_alertas"],
        "total_capturas": s["total_capturas"],
        "en_silencio": state.en_silencio(),
        "silencio_hasta": s["silencio_hasta"],
        "cpu": cpu,
        "ram": ram,
        "disk": disk
    })


@app_web.route("/api/foto", methods=["POST"])
def api_foto():
    check_token()
    state.invocar("foto")
    return jsonify({"status": "ok"})


@app_web.route("/api/pausa", methods=["POST"])
def api_pausa():
    check_token()
    state.invocar("pausar")
    return jsonify({"status": "ok"})


@app_web.route("/api/reanudar", methods=["POST"])
def api_reanudar():
    check_token()
    state.invocar("reanudar")
    return jsonify({"status": "ok"})


@app_web.route("/api/mapa", methods=["POST"])
def api_mapa():
    check_token()
    state.toggle_mapa_calor()
    return jsonify({"status": "ok", "msg": "Mapa de calor alternado"})

@app_web.route("/api/apagar", methods=["POST"])
def api_apagar():
    check_token()
    state.invocar("apagar")
    return jsonify({"status": "ok"})


@app_web.route("/api/zona", methods=["POST"])
def api_zona():
    check_token()
    data = request.json
    if not data:
        return jsonify({"status": "error", "msg": "No data"}), 400
    
    if data.get("zone") == "off":
        config.ZONA_VIGILANCIA = []
        return jsonify({"status": "ok"})
    
    coords = data.get("coords")
    if coords and len(coords) == 4:
        # Se reciben porcentajes
        x1p, y1p, x2p, y2p = coords
        W, H = 640, 480
        x1 = int(W * x1p / 100); y1 = int(H * y1p / 100)
        x2 = int(W * x2p / 100); y2 = int(H * y2p / 100)
        config.ZONA_VIGILANCIA = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
        return jsonify({"status": "ok"})
        
    return jsonify({"status": "error", "msg": "Invalid coords"}), 400


def iniciar_servidor_web():
    """Inicia el servidor Flask en el puerto 5000 sin logs en consola."""
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)
    app_web.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
