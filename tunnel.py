"""
tunnel.py — Gestión del túnel SSH de Pinggy.
Responsabilidad única: abrir / mantener / renovar el túnel con auto-reconexión.
"""

import os
import re
import subprocess
import threading
import time

import config
import stream  # Para leer el STREAM_TOKEN al armar la URL protegida

# Variable global que expone el proceso SSH activo.
# ui/hud.py la usa en _cerrar() para terminar el proceso limpiamente.
global_proceso_pinggy = None


def iniciar_pinggy():
    """
    Lanza el túnel SSH de Pinggy en un hilo separado con reconexión automática.
    Cuando el túnel gratuito caduca (60 min), se reconecta solo y manda el
    nuevo link por Telegram. El comando /vivo siempre devuelve el link vigente.
    """
    global global_proceso_pinggy
    print("  🔗 Iniciando túnel Pinggy con auto-reconexión...")

    # Construir el comando SSH una sola vez
    ssh_cmd = [
        "ssh",
        "-p", "443",
        "-R0:localhost:5000",
        "-o", "StrictHostKeyChecking=no",
        "-o", "PasswordAuthentication=no",
        "-o", "BatchMode=yes",
        "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=3",
    ]
    if hasattr(config, "PINGGY_SSH_KEY") and config.PINGGY_SSH_KEY:
        ssh_cmd += ["-i", os.path.expanduser(config.PINGGY_SSH_KEY)]
    ssh_cmd.append("a.pinggy.io")

    def _ciclo_pinggy():
        """Bucle infinito: conecta → espera que muera → reconecta."""
        global global_proceso_pinggy
        intento = 0

        while True:
            intento += 1
            config.STREAM_URL = ""  # Limpiar URL anterior al reconectar
            env = os.environ.copy()
            env['TERM'] = 'dumb'

            # Matar proceso anterior si existe
            try:
                if global_proceso_pinggy and global_proceso_pinggy.poll() is None:
                    global_proceso_pinggy.terminate()
                subprocess.run(["pkill", "-f", "a.pinggy.io"], capture_output=True)
                time.sleep(1)
            except Exception:
                pass

            print(f"  🔗 [Pinggy] Conectando (intento #{intento})...")

            try:
                global_proceso_pinggy = subprocess.Popen(
                    ssh_cmd,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, env=env, bufsize=1
                )

                url_encontrada = False
                # Leer línea por línea hasta que el proceso termine
                for line in global_proceso_pinggy.stdout:
                    line = line.strip()
                    if line:
                        print(f"  [Pinggy] {line}")

                    # Capturar la URL del túnel
                    if not url_encontrada and "http" in line and "pinggy" in line and "dashboard" not in line:
                        url_match = re.search(r'(https?://[^\s]+)', line)
                        if url_match:
                            config.STREAM_URL = url_match.group(1)
                            url_encontrada = True
                            print(f"  🌐 Enlace activo: {config.STREAM_URL}")

                            # Notificar por Telegram (primero avisa si es renovación)
                            try:
                                if config.TELEGRAM_ACTIVADO and config.TELEGRAM_TOKEN:
                                    from notifier import _enviar_mensaje
                                    import stream as _stream
                                    url_protegida = f"{config.STREAM_URL}/video?t={_stream.STREAM_TOKEN}"
                                    url_panel = f"{config.STREAM_URL}/panel?t={_stream.STREAM_TOKEN}"
                                    prefijo = "🔄 <b>Túnel renovado</b>" if intento > 1 else "📡 <b>Stream de cámara listo</b>"
                                    _enviar_mensaje(
                                        f"{prefijo}\n"
                                        f"🔴 <a href='{url_protegida}'>Ver cámara en vivo</a>\n"
                                        f"💻 <a href='{url_panel}'>Abrir Panel de Control</a>\n"
                                        f"<i>🔐 Enlace encriptado </i>"
                                    )
                            except Exception:
                                pass

                # El proceso terminó (túnel caducó o se cayó)
                codigo = global_proceso_pinggy.wait()
                print(f"  ⚠️ [Pinggy] Túnel terminado (código {codigo}). Reconectando en 5s...")

            except FileNotFoundError:
                print("  ❌ [Pinggy] 'ssh' no encontrado.")
                return  # Sin SSH no tiene sentido seguir intentando
            except Exception as e:
                print(f"  ❌ [Pinggy] Error: {e}")

            # Esperar antes de reconectar para no saturar
            time.sleep(5)

    threading.Thread(target=_ciclo_pinggy, daemon=True).start()
