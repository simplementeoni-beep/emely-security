# ============================================================
#   E.M.E.L.Y — Configuración del Sistema de Seguridad
#   Desarrollador: ONI (https://github.com/simplementeoni-beep)
# ============================================================

import os

# --- Telegram (notificaciones al celular) ---
# 1. Habla con @BotFather en Telegram → /newbot → copia el token
# 2. Habla con @userinfobot en Telegram → copia tu Chat ID
# 3. Crea un archivo .env en la raíz del proyecto con:
#      TELEGRAM_TOKEN=tu_token_aqui
#      TELEGRAM_CHAT_ID=tu_chat_id_aqui
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TELEGRAM_ACTIVADO = True  # False para desactivar notificaciones sin borrar el token

# --- Cámara ---
CAMARA_INDEX = 0            # 0 = cámara principal, 1 = cámara secundaria

# --- Detección de movimiento ---
SENSIBILIDAD = 1500         # Área mínima de cambio para considerar movimiento (píxeles²)
UMBRAL_BINARIO = 25         # Diferencia de intensidad para detectar cambio

# --- Sistema de confirmación (anti-falsas alarmas) ---
CAPTURAS_ANTES_DE_ALARMA = 3    # Fotos silenciosas antes de activar la alarma
TIEMPO_ENTRE_CAPTURAS = 1.0     # Segundos entre cada captura de confirmación
COOLDOWN_ALARMA = 15            # Segundos de espera antes de una nueva alarma
MINIMO_PERSONAS_ALARMA = 1      # Cantidad de personas (intrusos) requeridas para detonar alerta

# --- Archivos y rutas ---
CARPETA_CAPTURAS = "capturas"
FORMATO_FOTO = "%Y-%m-%d_%H-%M-%S"

# --- Servidor web ---
HOST = "0.0.0.0"
PORT = 5000
DEBUG = False
STREAM_URL = ""  # Se llena automáticamente cuando Pinggy conecta
PINGGY_SSH_KEY = "~/.ssh/id_emely"  # Clave SSH sin contraseña para Pinggy (generada automáticamente)
PANEL_PIN = "0000"  # PIN de 4 dígitos para acceder al panel web

# --- Voz (texto a voz) ---
VOZ_ACTIVADA = True
MENSAJE_ALERTA_VOZ = "Alerta. Intruso detectado. Activando protocolo de seguridad."
VOZ_VELOCIDAD = 150         # palabras por minuto

# --- Grabación de clips ---
CLIP_ACTIVADO        = True  # False para desactivar sin tocar el código
CLIP_DURACION        = 20    # Segundos de video a grabar tras detectar intruso
CLIP_ENVIAR_TELEGRAM = True  # True para enviar el clip por Telegram además de guardarlo

# ============================================================
#   v3.0 Inteligencia Táctica — Ajustes
# ============================================================

# --- Horarios ---
# Formato "HH:MM" (24h). Dejar en None para vigilar 24/7. Ej: ("22:00", "07:00")
HORARIO_ACTIVO = None 

# --- Geofencing (Zonas) ---
# Polígono de seguridad. Coordenadas (x, y) de la zona a vigilar (relativo a 640x480).
# Si está vacío [], vigila toda la pantalla.
# Ej: [(100, 100), (500, 100), (500, 400), (100, 400)] (Un rectángulo al centro)
ZONA_VIGILANCIA = []
