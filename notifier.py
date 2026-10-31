"""
notifier.py — Módulo de notificaciones por Telegram.
Sistema EMELY de Seguridad.
Desarrollador: ONI (https://github.com/simplementeoni-beep)

Envía un mensaje + foto al detectar un intruso.
"""

import os
import threading
from datetime import datetime

import requests

import config


def _enviar_mensaje(texto: str):
    """Envía un mensaje de texto al chat configurado."""
    if not config.TELEGRAM_TOKEN or not config.TELEGRAM_CHAT_ID:
        print("[TELEGRAM] ⚠ Token o Chat ID no configurados en config.py")
        return False
    try:
        url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
        resp = requests.post(url, data={
            "chat_id": config.TELEGRAM_CHAT_ID,
            "text": texto,
            "parse_mode": "HTML",
        }, timeout=10)
        if resp.status_code == 200:
            print("[TELEGRAM] ✅ Mensaje enviado")
            return True
        else:
            print(f"[TELEGRAM] ❌ Error {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        print(f"[TELEGRAM] ❌ Excepción: {e}")
        return False


def _enviar_foto(ruta_foto: str, caption: str = ""):
    """Envía una foto con caption al chat configurado."""
    if not config.TELEGRAM_TOKEN or not config.TELEGRAM_CHAT_ID:
        return False
    if not os.path.exists(ruta_foto):
        print(f"[TELEGRAM] ⚠ Foto no encontrada: {ruta_foto}")
        return False
    try:
        url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendPhoto"
        with open(ruta_foto, "rb") as foto:
            resp = requests.post(url, data={
                "chat_id": config.TELEGRAM_CHAT_ID,
                "caption": caption,
                "parse_mode": "HTML",
            }, files={"photo": foto}, timeout=15)
        if resp.status_code == 200:
            print(f"[TELEGRAM] ✅ Foto enviada: {os.path.basename(ruta_foto)}")
            return True
        else:
            print(f"[TELEGRAM] ❌ Error {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        print(f"[TELEGRAM] ❌ Excepción al enviar foto: {e}")
        return False


def notificar_intruso(fotos: list):
    """
    Envía alerta completa por Telegram en un hilo separado:
    - Mensaje de alerta con hora
    - Cada foto capturada durante la confirmación
    """
    def _enviar():
        hora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        
        # Construir mensaje con enlace si existe en este instante
        enlace = config.STREAM_URL
        if enlace:
            import stream as _stream
            url_protegida = f"{enlace}/video?t={_stream.STREAM_TOKEN}"
            link_texto = f"\n🔴 <b>Cámara en vivo:</b> <a href='{url_protegida}'>Toca aquí para ver</a>"
        else:
            link_texto = ""
        
        mensaje = (
            "🚨 <b>⚠ INTRUSO DETECTADO</b>\n\n"
            f"🕐 <b>Hora:</b> {hora}\n"
            f"📸 <b>Capturas:</b> {len(fotos)}\n"
            f"📍 <b>Sector:</b> Principal{link_texto}\n\n"
            "<i>E.M.E.L.Y Security Protocol — Alerta automática</i>"
        )
        _enviar_mensaje(mensaje)

        # Enviar cada foto capturada
        for i, ruta in enumerate(fotos, 1):
            caption = f"📸 Captura {i}/{len(fotos)} — {hora}"
            _enviar_foto(ruta, caption)

    threading.Thread(target=_enviar, daemon=True).start()


def notificar_inicio():
    """Avisa por Telegram que el sistema arrancó (un solo mensaje, sin delay)."""
    def _enviar():
        hora    = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        enlace  = config.STREAM_URL
        if enlace:
            import stream as _stream
            url_panel = f"{enlace}/panel?t={_stream.STREAM_TOKEN}"
            link_txt = f"\n💻 <b>Panel Web:</b> <a href='{url_panel}'>Abrir Panel</a>"
        else:
            link_txt = ""

        _enviar_mensaje(
            f"🟢 <b>E.M.E.L.Y activado</b> — {hora}{link_txt}\n"
            "<i>Sistema de seguridad en línea y monitoreando.</i>\n"
            "<i>Desarrollado por ONI</i>\n\n"
            "🤖 <b>Comandos:</b>\n"
            "📊 /estado  📸 /foto  🔴 /vivo\n"
            "⏸ /pausa  ▶️ /reanudar  🔇 /silencio [h]\n"
            "⚙️ /regla [nombre] [valor]\n"
            "📍 /zona [X1 Y1 X2 Y2 | ver | off]\n"
            "💬 /mensaje [texto]  🎤 Nota de voz\n"
            "🔥 /mapa (Activar mapa térmico)\n"
            "🛑 /apagar"
        )
    threading.Thread(target=_enviar, daemon=True).start()


def notificar_apagado():
    """Avisa por Telegram que el sistema se apagó y adjunta el reporte si aplica."""
    import state
    import time
    
    s = state.get()
    tiempo_activo_segundos = time.time() - s["tiempo_inicio"]
    horas_activas = tiempo_activo_segundos / 3600.0
    alertas = s["total_alertas"]
    capturas = s["total_capturas"]
    hora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    
    if horas_activas > 1.0 or alertas > 0:
        mins = int(tiempo_activo_segundos // 60)
        hrs = mins // 60
        mins_restantes = mins % 60
        tiempo_str = f"{hrs}h {mins_restantes}m" if hrs > 0 else f"{mins}m"
        
        _enviar_mensaje(
            f"🔴 <b>E.M.E.L.Y APAGADO — REPORTE DE SESIÓN</b>\n"
            f"🕐 {hora}\n\n"
            f"⏱️ <b>Tiempo activo:</b> {tiempo_str}\n"
            f"🚨 <b>Amenazas detectadas:</b> {alertas}\n"
            f"📸 <b>Capturas tomadas:</b> {capturas}\n\n"
            f"<i>Sistema de seguridad fuera de línea.</i>"
        )
    else:
        _enviar_mensaje(
            f"🔴 <b>E.M.E.L.Y desactivado</b>\n"
            f"🕐 {hora}\n"
            "<i>(Sesión corta sin detecciones relevantes).</i>"
        )

def notificar_clip(ruta_clip: str):
    """
    Envía el clip de video del intruso por Telegram.
    Corre en hilo separado — los clips pueden tardar en subir.
    """
    def _enviar():
        if not config.TELEGRAM_TOKEN or not config.TELEGRAM_CHAT_ID:
            return
        if not os.path.exists(ruta_clip):
            print(f"[TELEGRAM] ⚠ Clip no encontrado: {ruta_clip}")
            return
        try:
            hora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            url  = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendVideo"
            with open(ruta_clip, "rb") as video:
                resp = requests.post(url, data={
                    "chat_id": config.TELEGRAM_CHAT_ID,
                    "caption": (
                        f"🎬 <b>Clip de evidencia</b>\n"
                        f"🕐 {hora}\n"
                        "<i>E.M.E.L.Y Security — Grabación automática</i>"
                    ),
                    "parse_mode": "HTML",
                    "supports_streaming": True,
                }, files={"video": video}, timeout=60)
            if resp.status_code == 200:
                print(f"[TELEGRAM] ✅ Clip enviado: {os.path.basename(ruta_clip)}")
            else:
                print(f"[TELEGRAM] ❌ Error al enviar clip: {resp.status_code}")
        except Exception as e:
            print(f"[TELEGRAM] ❌ Excepción al enviar clip: {e}")

    threading.Thread(target=_enviar, daemon=True).start()

def responder_comando(chat_id, texto):
    """Responde directamente a un usuario en Telegram."""
    if not config.TELEGRAM_TOKEN: return
    try:
        url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": chat_id, "text": texto, "parse_mode": "HTML"}, timeout=10)
    except Exception:
        pass


def descargar_voz(file_id: str) -> str | None:
    """
    Descarga un mensaje de voz de Telegram y devuelve la ruta local del archivo OGG.
    Devuelve None si ocurre cualquier error.
    """
    if not config.TELEGRAM_TOKEN:
        return None
    try:
        # 1. Obtener la ruta interna del archivo
        url_info = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/getFile"
        resp = requests.get(url_info, params={"file_id": file_id}, timeout=10)
        file_path = resp.json()["result"]["file_path"]
        # 2. Descargar el contenido binario
        url_dl = f"https://api.telegram.org/file/bot{config.TELEGRAM_TOKEN}/{file_path}"
        data = requests.get(url_dl, timeout=30).content
        # 3. Guardar en /tmp
        import tempfile
        ruta = os.path.join(tempfile.gettempdir(), "emely_voz.ogg")
        with open(ruta, "wb") as f:
            f.write(data)
        return ruta
    except Exception as e:
        print(f"[TELEGRAM] ⚠ Error descargando voz: {e}")
        return None

def iniciar_escucha_comandos(callback):
    """
    Inicia un hilo en segundo plano que escucha los mensajes que le envías al bot (Long Polling).
    Solo responde si el mensaje viene del TELEGRAM_CHAT_ID autorizado.
    """
    def _poll():
        import time
        offset = None
        es_primer_ciclo = True  # Para ignorar mensajes viejos
        
        while True:
            if not config.TELEGRAM_TOKEN:
                time.sleep(5)
                continue
            
            try:
                url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/getUpdates"
                params = {"timeout": 20}
                if offset: params["offset"] = offset
                
                resp = requests.get(url, params=params, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("ok"):
                        for result in data.get("result", []):
                            offset = result["update_id"] + 1
                            
                            # Si es el primer ciclo, ignoramos el mensaje para no procesar comandos viejos
                            if es_primer_ciclo:
                                continue
                                
                            msg = result.get("message", {})
                            text = msg.get("text", "")
                            chat_id = msg.get("chat", {}).get("id")
                            
                            # Seguridad: Solo procesar del dueño (TELEGRAM_CHAT_ID)
                            if str(chat_id) == str(config.TELEGRAM_CHAT_ID):
                                # Mensaje de texto normal
                                if text:
                                    callback(text, chat_id)
                                # Mensaje de voz — marcador especial __voz__:<file_id>
                                elif msg.get("voice"):
                                    file_id = msg["voice"]["file_id"]
                                    callback(f"__voz__:{file_id}", chat_id)
                                
                        # Terminó de procesar la historia inicial
                        es_primer_ciclo = False
            except Exception:
                pass
            time.sleep(1)
            
    threading.Thread(target=_poll, daemon=True).start()

    def _loop_reporte_diario():
        import time
        import state
        
        ultimo_dia_enviado = -1
        while True:
            time.sleep(60)
            ahora = datetime.now()
            
            # A las 23:55 preparamos el reporte diario
            if ahora.hour == 23 and ahora.minute >= 55 and ahora.day != ultimo_dia_enviado:
                s = state.get()
                tiempo_activo_segundos = time.time() - s["tiempo_inicio"]
                horas_activas = tiempo_activo_segundos / 3600.0
                alertas = s["total_alertas"]
                capturas = s["total_capturas"]
                
                # Solo si lleva más de 1h o hay amenazas
                if horas_activas > 1.0 or alertas > 0:
                    mins = int(tiempo_activo_segundos // 60)
                    hrs = mins // 60
                    mins_restantes = mins % 60
                    tiempo_str = f"{hrs}h {mins_restantes}m" if hrs > 0 else f"{mins}m"
                    
                    _enviar_mensaje(
                        f"📅 <b>REPORTE DIARIO DE E.M.E.L.Y</b>\n\n"
                        f"⏱️ <b>Tiempo activo (continuo):</b> {tiempo_str}\n"
                        f"🚨 <b>Amenazas detectadas hoy:</b> {alertas}\n"
                        f"📸 <b>Capturas tomadas:</b> {capturas}\n\n"
                        f"<i>Terminando el día. Sigo vigilando...</i>"
                    )
                
                ultimo_dia_enviado = ahora.day

    threading.Thread(target=_loop_reporte_diario, daemon=True).start()
