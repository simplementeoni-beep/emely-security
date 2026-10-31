"""
app.py — Punto de entrada de E.M.E.L.Y Security System.
Ejecuta: python app.py
Orquesta el arranque de módulos; no contiene lógica propia.
"""

import os
import threading
import tkinter as tk
import subprocess

# ── Cargar variables de entorno desde .env ────────────────────
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

import config
from config import CARPETA_CAPTURAS
from stream import iniciar_servidor_web
from tunnel import iniciar_pinggy
from ui.hud import EmelyApp

os.makedirs(CARPETA_CAPTURAS, exist_ok=True)

if __name__ == "__main__":
    print("=" * 55)
    print("  E.M.E.L.Y — SISTEMA DE SEGURIDAD DESKTOP")
    print("=" * 55)

    # Iniciar pinggy para túnel de video
    iniciar_pinggy()

    # Aviso de inicio por Telegram
    try:
        from config import TELEGRAM_ACTIVADO, TELEGRAM_TOKEN
        if TELEGRAM_ACTIVADO and TELEGRAM_TOKEN:
            from notifier import notificar_inicio
            notificar_inicio()
    except Exception:
        pass

    root = tk.Tk()
    # Nota: el HUD usa attributes("-fullscreen", True) internamente

    # Iniciar servidor web en hilo de fondo
    threading.Thread(target=iniciar_servidor_web, daemon=True).start()
    print("  🌐 Servidor web de transmisión activo en http://localhost:5000")

    # === ESCUDO INMORTAL ===
    # Bloquea la suspensión de la PC mientras este script esté corriendo.
    # Al estar atado a 'stdin', si app.py se cierra por cualquier razón,
    # el escudo se destruye automáticamente liberando la PC.
    print("  🛡️  Activando Escudo Inmortal (bloqueo de suspensión)...")
    try:
        escudo_inmortal = subprocess.Popen(
            ["systemd-inhibit", "--what=sleep:idle", "--who=EMELY", "--why=Vigilancia activa", "/bin/bash", "-c", "read"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception as e:
        print(f"  ⚠️  No se pudo activar el escudo: {e}")
        escudo_inmortal = None

    app = EmelyApp(root)
    root.mainloop()

    # Desactivar escudo al cerrar la ventana
    print("  🛑 Desactivando Escudo Inmortal...")
    if escudo_inmortal and escudo_inmortal.poll() is None:
        try:
            escudo_inmortal.stdin.close()
            escudo_inmortal.wait(timeout=2)
        except Exception:
            pass
