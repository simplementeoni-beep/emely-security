"""
ui/hud.py — Fachada Neural de E.M.E.L.Y (v2.2)
Sistema EMELY de Seguridad.
Desarrollador: ONI (https://github.com/simplementeoni-beep)

Interfaz animada estilo JARVIS que NO revela operaciones de seguridad.
El intruso solo ve una pantalla bonita con partículas y un orbe.
La cámara, detección y Telegram corren invisiblemente en segundo plano.
"""

import math
import os
import random
import subprocess
import threading
import time
from datetime import datetime

import cv2
import numpy as np
from PIL import Image, ImageTk
import tkinter as tk

import config
from config import (
    CAMARA_INDEX, CARPETA_CAPTURAS,
    MENSAJE_ALERTA_VOZ, VOZ_ACTIVADA, VOZ_VELOCIDAD,
)
from detector import DetectorMovimiento
import stream
import tunnel

# ── Colores internos de la fachada ──────────────────────────────────
_BG         = "#06000f"
_VIOLET     = "#b04dff"
_VIOLET_DIM = "#3a0f66"
_ORANGE     = "#ff9100"
_WHITE_DIM  = "#7788aa"
_FONT       = "Courier"

# ── Dot-matrices 5×7 para formación de letras ───────────────────────
_GRIDS = {
    "E": [[1,1,1,1,1],[1,0,0,0,0],[1,1,1,1,0],[1,0,0,0,0],[1,0,0,0,0],[1,0,0,0,0],[1,1,1,1,1]],
    "M": [[1,0,0,0,1],[1,1,0,1,1],[1,0,1,0,1],[1,0,0,0,1],[1,0,0,0,1],[1,0,0,0,1],[1,0,0,0,1]],
    "L": [[1,0,0,0,0],[1,0,0,0,0],[1,0,0,0,0],[1,0,0,0,0],[1,0,0,0,0],[1,0,0,0,0],[1,1,1,1,1]],
    "Y": [[1,0,0,0,1],[1,0,0,0,1],[0,1,0,1,0],[0,0,1,0,0],[0,0,1,0,0],[0,0,1,0,0],[0,0,1,0,0]],
    # Símbolo de pausa: dos barras verticales
    "PAUSA": [[1,0,1],[1,0,1],[1,0,1],[1,0,1],[1,0,1],[1,0,1],[1,0,1]],
}

def _puntos_de_grid(grid, off_c=0, sc=13, sr=13):
    pts = []
    for r, row in enumerate(grid):
        for c, v in enumerate(row):
            if v:
                pts.append((off_c + c * sc, r * sr))
    return pts

def _calcular_plantilla(nombre):
    """Devuelve lista de (x, y) crudos para el nombre dado."""
    if nombre == "EMELY":
        pts, off = [], 0
        for letra in "EMELY":
            pts.extend(_puntos_de_grid(_GRIDS[letra], off))
            off += (5 + 2) * 13
        return pts
    elif nombre == "PAUSA":
        return _puntos_de_grid(_GRIDS["PAUSA"], 0, 18, 18)
    return []  # LIBRE: sin targets

# Precalcular
_PTS_EMELY = _calcular_plantilla("EMELY")
_PTS_PAUSA = _calcular_plantilla("PAUSA")

NUM_PART   = 85
RADIO_ORB  = 58
DIST_CONN  = 125
VEL        = 0.45

# RGB del orbe en cada estado
_ORB_STATES = {
    "STANDBY":    (176, 77,  255),   # violeta
    "CONFIRMANDO":(255, 145, 0),     # naranja
    "ALERTA":     (204, 34,  34),    # rojo
    "PAUSADO":    (60,  60,  160),   # azul tenue
}


class EmelyApp:
    def __init__(self, root):
        self.root = root
        # ── Forzar pantalla completa sin decoraciones ────────────────
        # 1. Asegurarse que la ventana esté lista antes de medir
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        # 2. Posicionar y dimensionar exactamente en toda la pantalla
        self.root.geometry(f"{sw}x{sh}+0+0")
        # 3. Forzar modo fullscreen nativo
        self.root.attributes("-fullscreen", True)
        # 4. Quitar barra de título y bordes
        self.root.overrideredirect(True)
        # 5. Siempre encima de todo
        self.root.attributes("-topmost", True)
        self.root.configure(bg=_BG)
        # Tecla secreta del dueño: ESC para cerrar
        self.root.bind("<Escape>", lambda e: self._cerrar())
        self.root.bind("<F12>",    lambda e: self._cerrar())

        # ── Estado ──────────────────────────────────────────────────
        self.corriendo     = True
        self.frame_actual  = None
        self.alerta_activa = False
        self.estado        = "STANDBY"
        self.total_alertas = 0
        self.total_capturas= 0
        self._sw = sw
        self._sh = sh

        # ── Color orbe (floats R,G,B interpolados) ──────────────────
        r, g, b = _ORB_STATES["STANDBY"]
        self._or = float(r); self._og = float(g); self._ob = float(b)
        self._tr = float(r); self._tg = float(g); self._tb = float(b)
        self._pulso = 0.0

        # ── Detector ────────────────────────────────────────────────
        self.detector = DetectorMovimiento(
            on_confirmando=self._cb_confirmando,
            on_alerta=self._cb_alerta,
            on_standby=self._cb_standby,
        )

        self._construir_ui()
        self._iniciar_camara()
        self._loop_video()
        self._anim_loop()

        # Registrar callbacks para la API web
        import state
        state.registrar("pausar", self._api_pausar)
        state.registrar("reanudar", self._api_reanudar)
        state.registrar("foto", self._api_foto)
        state.registrar("apagar", lambda: self.root.after(0, self._cerrar))

        # Telegram
        try:
            if config.TELEGRAM_ACTIVADO and config.TELEGRAM_TOKEN:
                from notifier import iniciar_escucha_comandos
                iniciar_escucha_comandos(self._procesar_comando)
        except Exception:
            pass

        self.root.protocol("WM_DELETE_WINDOW", self._cerrar)

    # ════════════════════════════════════════════════════════════════
    #  UI — CANVAS Y TEXTOS
    # ════════════════════════════════════════════════════════════════
    def _construir_ui(self):
        self.cv = tk.Canvas(self.root, bg=_BG,
                            highlightthickness=0, cursor="none")
        self.cv.pack(fill="both", expand=True)
        
        # Cargar imagen emely.jpg como fondo
        try:
            ruta_img = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "emely.jpg")
            if os.path.exists(ruta_img):
                img = Image.open(ruta_img)
                # Redimensionar al tamaño de la pantalla
                img = img.resize((self._sw, self._sh), Image.Resampling.LANCZOS)
                self._img_fondo = ImageTk.PhotoImage(img)
            else:
                self._img_fondo = None
        except Exception as e:
            print(f"[EMELY] Error al cargar emely.jpg: {e}")
            self._img_fondo = None

        self._init_particulas()
        self.root.after(300, self._crear_labels)

    def _crear_labels(self):
        cx = self._sw // 2
        cy = self._sh // 2
        
        # Textos en el canvas para que tengan fondo transparente
        self._reloj_id = self.cv.create_text(
            cx, self._sh * 0.85,
            text="00 : 00 : 00",
            fill=_VIOLET,
            font=(_FONT, 18, "bold")
        )
        self.cv.create_text(
            cx, self._sh * 0.89,
            text="SECURITY INTERFACE  ·  ACTIVE",
            fill=_WHITE_DIM,
            font=(_FONT, 10, "bold")
        )
        self.cv.create_text(
            cx, self._sh * 0.92,
            text="DEVELOPED BY ONI",
            fill=_VIOLET_DIM,
            font=(_FONT, 8, "bold")
        )
        self._reloj_tick()

    def _reloj_tick(self):
        if hasattr(self, '_reloj_id'):
            self.cv.itemconfig(self._reloj_id, text=time.strftime("%H : %M : %S"))
        self.root.after(1000, self._reloj_tick)

    # ════════════════════════════════════════════════════════════════
    #  PARTÍCULAS
    # ════════════════════════════════════════════════════════════════
    def _init_particulas(self):
        sw, sh = self._sw, self._sh
        self._parts = []
        for _ in range(NUM_PART):
            vx = random.choice([-1, 1]) * random.uniform(0.2, VEL)
            vy = random.choice([-1, 1]) * random.uniform(0.2, VEL)
            self._parts.append({
                'x': random.uniform(0, sw), 'y': random.uniform(0, sh),
                'vx': vx, 'vy': vy,
                'tx': random.uniform(0, sw), 'ty': random.uniform(0, sh),
                'libre': True,
                'sz': random.uniform(1.5, 3.0),
            })
        self.root.after(600, lambda: self._aplicar_plantilla("LIBRE"))

    def _aplicar_plantilla(self, nombre):
        sw, sh = self._sw, self._sh
        cx = sw // 2
        # Centro de la zona de letras (debajo del orbe)
        cy_letras = sh // 2 + RADIO_ORB + 55

        if nombre == "EMELY":
            raw = _PTS_EMELY
        elif nombre == "PAUSA":
            raw = _PTS_PAUSA
        else:
            raw = []

        # Centrar los puntos
        if raw:
            max_x = max(p[0] for p in raw)
            max_y = max(p[1] for p in raw)
            puntos = [(cx - max_x // 2 + px, cy_letras - max_y // 2 + py)
                      for px, py in raw]
        else:
            puntos = []

        # Liberar todas
        for p in self._parts:
            p['libre'] = True
            p['tx'] = random.uniform(0, sw)
            p['ty'] = random.uniform(0, sh)

        # Asignar partículas a los puntos
        random.shuffle(self._parts)
        for i, (px, py) in enumerate(puntos[:len(self._parts)]):
            p = self._parts[i]
            p['libre'] = False
            p['tx'] = px + random.uniform(-2, 2)
            p['ty'] = py + random.uniform(-2, 2)

    def _mover_particulas(self):
        sw, sh = self._sw, self._sh
        for p in self._parts:
            if p['libre']:
                p['x'] += p['vx']
                p['y'] += p['vy']
                if p['x'] <= 0 or p['x'] >= sw: p['vx'] *= -1
                if p['y'] <= 0 or p['y'] >= sh: p['vy'] *= -1
                p['x'] = max(0, min(sw, p['x']))
                p['y'] = max(0, min(sh, p['y']))
            else:
                dx = p['tx'] - p['x']
                dy = p['ty'] - p['y']
                d = math.hypot(dx, dy)
                if d > 1.2:
                    spd = min(d * 0.06, 5.0)
                    p['x'] += dx / d * spd
                    p['y'] += dy / d * spd

    def _color_part(self):
        if self.estado == "ALERTA":      return "#aa2222"
        if self.estado == "CONFIRMANDO": return "#995500"
        if self.estado == "PAUSADO":     return "#334488"
        return _VIOLET_DIM

    def _dibujar_red(self):
        ps = self._parts
        n  = len(ps)
        c_part = self._color_part()
        for i in range(n):
            for j in range(i + 1, n):
                dx = ps[i]['x'] - ps[j]['x']
                dy = ps[i]['y'] - ps[j]['y']
                d  = math.hypot(dx, dy)
                if d < DIST_CONN:
                    alpha = 1.0 - d / DIST_CONN
                    # Simular opacidad con tonos oscuros del color base
                    v = int(55 * alpha)
                    if self.estado == "ALERTA":
                        col = f"#{v:02x}{max(0,v//5):02x}{max(0,v//5):02x}"
                    elif self.estado == "PAUSADO":
                        col = f"#{max(0,v//5):02x}{max(0,v//5):02x}{v:02x}"
                    else:
                        col = f"#{max(0,v//5):02x}{max(0,v//6):02x}{v:02x}"
                    self.cv.create_line(ps[i]['x'], ps[i]['y'],
                                       ps[j]['x'], ps[j]['y'],
                                       fill=col, width=1)
        # Puntos
        for p in ps:
            s = p['sz']
            self.cv.create_oval(p['x']-s, p['y']-s, p['x']+s, p['y']+s,
                                fill=c_part, outline="")

    # ════════════════════════════════════════════════════════════════
    #  ORBE CENTRAL (Lógica de color conservada para las partículas)
    # ════════════════════════════════════════════════════════════════
    def _lerp_orbe(self):
        self._or += (self._tr - self._or) * 0.018
        self._og += (self._tg - self._og) * 0.018
        self._ob += (self._tb - self._ob) * 0.018

    def _hex_orbe(self, brillo=1.0):
        r = min(255, max(0, int(self._or * brillo)))
        g = min(255, max(0, int(self._og * brillo)))
        b = min(255, max(0, int(self._ob * brillo)))
        return f"#{r:02x}{g:02x}{b:02x}"

    # (El orbe ya no se dibuja, usamos el fondo, pero conservamos _lerp_orbe para sincronizar colores)

    # ════════════════════════════════════════════════════════════════
    #  LOOP DE ANIMACIÓN
    # ════════════════════════════════════════════════════════════════
    def _anim_loop(self):
        if not self.corriendo:
            return
        self.cv.delete("all")
        
        # 1. Dibujar imagen de fondo
        if hasattr(self, '_img_fondo') and self._img_fondo:
            self.cv.create_image(self._sw//2, self._sh//2, image=self._img_fondo)
            
        self._lerp_orbe()
        self._mover_particulas()
        self._dibujar_red()
        
        # Dibujar mensaje entrante (efecto máquina de escribir)
        if hasattr(self, 'mensaje_hud_full') and self.mensaje_hud_full:
            if time.time() < self.mensaje_hud_hasta:
                # 30 fps = ~0.6 a 1 caracter por frame
                if self.mensaje_hud_index < len(self.mensaje_hud_full):
                    self.mensaje_hud_index += 1.5 
                
                texto_mostrar = self.mensaje_hud_full[:int(self.mensaje_hud_index)]
                self.cv.create_text(
                    self._sw // 2, self._sh * 0.75,
                    text=texto_mostrar,
                    fill="#00ff88", font=("Courier", 24, "bold"), justify="center"
                )
            else:
                self.mensaje_hud_full = "" # Limpiar tras expirar
        
        self.root.after(33, self._anim_loop)   # ~30 FPS

    # ════════════════════════════════════════════════════════════════
    #  CALLBACKS DEL DETECTOR
    # ════════════════════════════════════════════════════════════════
    def _cb_confirmando(self, actual, total):
        self.root.after(0, self._ui_confirmando, actual, total)

    def _cb_alerta(self, fotos):
        self.root.after(0, self._ui_alerta, fotos)

    def _cb_standby(self):
        self.root.after(0, self._ui_standby)

    def _set_orb_target(self, estado):
        r, g, b = _ORB_STATES.get(estado, _ORB_STATES["STANDBY"])
        self._tr, self._tg, self._tb = float(r), float(g), float(b)

    def _ui_confirmando(self, actual, total):
        self.estado = "CONFIRMANDO"
        self._set_orb_target("CONFIRMANDO")

    def _ui_alerta(self, fotos):
        self.alerta_activa = True
        self.total_alertas += 1
        self.total_capturas += len(fotos)
        self.estado = "ALERTA"
        self._set_orb_target("ALERTA")
        self._aplicar_plantilla("LIBRE")   # partículas se dispersan
        self._sonar_alarma()
        self.root.after(3000, self._bloquear_sesion)

    def _ui_standby(self):
        self.alerta_activa = False
        self.estado = "STANDBY"
        self._set_orb_target("STANDBY")
        self._aplicar_plantilla("LIBRE")

    def _bloquear_sesion(self):
        try:
            subprocess.run(["loginctl", "lock-session"], timeout=3)
        except Exception:
            pass

    # ════════════════════════════════════════════════════════════════
    #  SONIDO / VOZ
    # ════════════════════════════════════════════════════════════════
    def _sonar_alarma(self):
        def _play():
            try:
                subprocess.run(
                    ["paplay", "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga"],
                    capture_output=True, timeout=5)
            except Exception:
                try:
                    subprocess.run(["aplay", "-q", "/usr/share/sounds/alsa/Front_Left.wav"],
                                   capture_output=True, timeout=3)
                except Exception:
                    pass
        threading.Thread(target=_play, daemon=True).start()
        if VOZ_ACTIVADA:
            def _voz():
                try:
                    subprocess.run(["espeak-ng", "-s", str(VOZ_VELOCIDAD), "-v", "es",
                                    MENSAJE_ALERTA_VOZ], capture_output=True, timeout=10)
                except Exception:
                    try:
                        subprocess.run(["espeak", "-s", str(VOZ_VELOCIDAD), "-v", "es",
                                        MENSAJE_ALERTA_VOZ], capture_output=True, timeout=10)
                    except Exception:
                        pass
            threading.Thread(target=_voz, daemon=True).start()

    # ════════════════════════════════════════════════════════════════
    #  LLAMADAS DESDE LA API WEB (PANEL)
    # ════════════════════════════════════════════════════════════════
    def _api_pausar(self):
        self._procesar_comando("/pausar", None)

    def _api_reanudar(self):
        self._procesar_comando("/reanudar", None)

    def _api_foto(self):
        self._procesar_comando("/foto", None)

    # ════════════════════════════════════════════════════════════════
    #  COMANDOS TELEGRAM
    # ════════════════════════════════════════════════════════════════
    def _procesar_comando(self, texto_original, chat_id):
        texto = texto_original.lower().strip()
        from notifier import _enviar_foto, responder_comando

        if texto == "/estado":
            modo = "Vigilando 🟢"
            if self.estado == "PAUSADO":  modo = "Pausado ⏸️"
            if self.detector.alarma_activa: modo = "¡ALERTA! 🔴"
            en_silencio = time.time() < self.detector.silencio_hasta
            sil_txt = f"🔇 Sí (quedan {int((self.detector.silencio_hasta - time.time())/60)} min)" if en_silencio else "No"
            
            hw_str = ""
            try:
                import psutil
                cpu = psutil.cpu_percent()
                ram = psutil.virtual_memory().percent
                disk = psutil.disk_usage('/').percent
                hw_str = (f"\n🖥️ <b>Hardware:</b>\n"
                          f"  • CPU: {cpu}%\n"
                          f"  • RAM: {ram}%\n"
                          f"  • Disco: {disk}%\n")
            except ImportError:
                pass
                
            msg = (f"🛡️ <b>ESTADO DE E.M.E.L.Y</b>\n\n"
                   f"🤖 <b>Modo:</b> {modo}\n"
                   f"🚨 <b>Alertas:</b> {self.total_alertas}\n"
                   f"📸 <b>Capturas:</b> {self.total_capturas}\n"
                   f"🔇 <b>Silencio:</b> {sil_txt}\n\n"
                   f"⚙️ <b>Reglas activas:</b>\n"
                   f"  • Personas para alarmar: {config.MINIMO_PERSONAS_ALARMA}\n"
                   f"  • Capturas de confirmación: {config.CAPTURAS_ANTES_DE_ALARMA}\n"
                   f"  • Cooldown: {config.COOLDOWN_ALARMA}s\n"
                   f"{hw_str}")
            if config.STREAM_URL:
                import stream as _stream
                url_panel = f"{config.STREAM_URL}/panel?t={_stream.STREAM_TOKEN}"
                msg += f"\n💻 <b>Panel Web:</b> <a href='{url_panel}'>Abrir Panel</a>"
            responder_comando(chat_id, msg)

        elif texto == "/foto":
            responder_comando(chat_id, "📸 Capturando...")
            if self.frame_actual is not None:
                from config import CARPETA_CAPTURAS, FORMATO_FOTO
                ts  = datetime.now().strftime(FORMATO_FOTO)
                ruta = os.path.join(CARPETA_CAPTURAS, f"manual_{ts}.jpg")
                cv2.imwrite(ruta, self.frame_actual)
                self.total_capturas += 1
                _enviar_foto(ruta, "📍 <b>Captura Manual</b>")
            else:
                responder_comando(chat_id, "❌ Cámara no disponible.")

        elif texto == "/mapa":
            import state
            state.toggle_mapa_calor()
            if state.get().get("mapa_calor"):
                responder_comando(chat_id, "🔥 Mapa térmico ACTIVADO.")
            else:
                responder_comando(chat_id, "❄️ Mapa térmico DESACTIVADO.")

        elif texto in ("/pausar", "/pausa"):
            self.estado = "PAUSADO"
            self.detector.estado = "PAUSADO"
            self._set_orb_target("PAUSADO")
            self.root.after(0, lambda: self._aplicar_plantilla("PAUSA"))
            responder_comando(chat_id, "⏸️ <b>Sistema Pausado</b>")

        elif texto == "/reanudar":
            self.estado = "STANDBY"
            self.detector.estado = "STANDBY"
            self._set_orb_target("STANDBY")
            self.root.after(0, lambda: self._aplicar_plantilla("LIBRE"))
            responder_comando(chat_id, "▶️ <b>Sistema Reanudado</b>")

        elif texto == "/vivo":
            if config.STREAM_URL:
                import stream as _stream
                url_protegida = f"{config.STREAM_URL}/video?t={_stream.STREAM_TOKEN}"
                url_panel = f"{config.STREAM_URL}/panel?t={_stream.STREAM_TOKEN}"
                msg = (
                    f"🔴 <b>Stream activo</b>\n"
                    f"<a href='{url_protegida}'>Ver cámara en vivo</a>\n\n"
                    f"💻 <b>Panel Táctico:</b>\n"
                    f"<a href='{url_panel}'>Abrir Panel Web</a>"
                )
            else:
                msg = "❌ Túnel no disponible aún."
            responder_comando(chat_id, msg)

        elif texto.startswith("/silencio"):
            partes = texto.split()
            horas = 1.0
            if len(partes) > 1:
                try:
                    horas = float(partes[1].replace('h', ''))
                except ValueError:
                    pass
            
            # Pasamos la orden al detector
            self.detector.silencio_hasta = time.time() + (horas * 3600)
            responder_comando(chat_id, f"🔇 <b>Modo Silencioso Temporal</b>\nEMELY ignorará detecciones durante {horas} hora(s).")

        elif texto == "/apagar":
            # Confirmación inmediata — el aviso de apagado lo envía _cerrar()
            self.root.after(0, self._cerrar)

        elif texto.startswith("/zona"):
            # /zona X1 Y1 X2 Y2  (porcentajes 0-100 del frame 640x480)
            # /zona off          → vigilar toda la camara
            # /zona ver          → foto con zona dibujada
            partes = texto.split()
            if len(partes) == 1 or partes[1] == "off":
                config.ZONA_VIGILANCIA = []
                responder_comando(chat_id, "✅ <b>Zona eliminada.</b> EMELY vigila <b>toda</b> la cámara.")

            elif partes[1] == "ver":
                if self.frame_actual is not None:
                    import cv2 as _cv2
                    from config import CARPETA_CAPTURAS, FORMATO_FOTO
                    tmp = self.frame_actual.copy()
                    if config.ZONA_VIGILANCIA:
                        pts = np.array(config.ZONA_VIGILANCIA, np.int32).reshape((-1, 1, 2))
                        _cv2.polylines(tmp, [pts], True, (255, 150, 0), 3)
                        _cv2.putText(tmp, "ZONA ACTIVA", (config.ZONA_VIGILANCIA[0][0], config.ZONA_VIGILANCIA[0][1] - 8),
                                     _cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 150, 0), 2)
                    else:
                        _cv2.putText(tmp, "Sin zona — toda la camara", (10, 30),
                                     _cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 229, 255), 2)
                    ts   = datetime.now().strftime(FORMATO_FOTO)
                    ruta = os.path.join(CARPETA_CAPTURAS, f"zona_{ts}.jpg")
                    _cv2.imwrite(ruta, tmp)
                    _enviar_foto(ruta, "📍 <b>Vista de zona de vigilancia</b>")
                else:
                    responder_comando(chat_id, "❌ Cámara no disponible.")

            elif len(partes) == 5:
                try:
                    x1p, y1p, x2p, y2p = [float(p) for p in partes[1:5]]
                    if not all(0 <= v <= 100 for v in [x1p, y1p, x2p, y2p]):
                        raise ValueError
                    W, H = 640, 480
                    x1 = int(W * x1p / 100); y1 = int(H * y1p / 100)
                    x2 = int(W * x2p / 100); y2 = int(H * y2p / 100)
                    config.ZONA_VIGILANCIA = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
                    responder_comando(chat_id,
                        f"✅ <b>Zona definida:</b> ({x1p:.0f}%, {y1p:.0f}%) → ({x2p:.0f}%, {y2p:.0f}%)\n"
                        "Usa /zona ver para confirmar el encuadre.")
                except (ValueError, IndexError):
                    responder_comando(chat_id,
                        "❌ Formato incorrecto.\n"
                        "Uso: <code>/zona X1 Y1 X2 Y2</code> (porcentajes 0-100)\n"
                        "Ejemplo: <code>/zona 20 10 80 90</code>\n"
                        "O usa /zona off para vigilar toda la cámara.")
            else:
                responder_comando(chat_id,
                    "📍 <b>Comando de zona:</b>\n"
                    "/zona X1 Y1 X2 Y2 — Definir rectángulo (% del frame)\n"
                    "/zona ver — Foto con zona actual\n"
                    "/zona off — Vigilar toda la cámara")

        elif texto.startswith("/mensaje ") or texto.startswith("/mensajes "):
            # Extraer el texto quitando el comando
            if texto.startswith("/mensajes "):
                contenido = texto[len("/mensajes "):].strip()
            else:
                contenido = texto[len("/mensaje "):].strip()

            if contenido:
                import stream as _stream
                _stream.set_mensaje_overlay(f"📨 {contenido}", duracion=15)
                
                # Mostrar en el HUD local con efecto máquina de escribir
                self.mensaje_hud_full = f"MENSAJE ENTRANTE:\n{contenido.upper()}"
                self.mensaje_hud_index = 0
                self.mensaje_hud_hasta = time.time() + 10  # Visible 10 segundos
                    
                responder_comando(chat_id, f"✅ Mensaje en pantalla: <i>{contenido}</i>")
            else:
                responder_comando(chat_id, "❌ Escribe algo: <code>/mensaje Hola desde el teléfono</code>")

        elif texto_original.startswith("__voz__:"):
            file_id = texto_original.split(":", 1)[1]  # Preservar mayúsculas del file_id
            responder_comando(chat_id, "🎤 Reproduciendo tu mensaje de voz...")
            import stream as _stream
            _stream.set_mensaje_overlay("🎤 MENSAJE DE VOZ ENTRANTE", duracion=10)
            
            # Mostrar en el HUD local con efecto máquina de escribir
            self.mensaje_hud_full = "🎤 REPRODUCIENDO NOTA DE VOZ..."
            self.mensaje_hud_index = 0
            self.mensaje_hud_hasta = time.time() + 10  # Visible 10 segundos
            def _reproducir_voz():
                from notifier import descargar_voz
                ruta = descargar_voz(file_id)
                if ruta:
                    try:
                        subprocess.run(["paplay", ruta], timeout=60)
                    except Exception:
                        try:
                            subprocess.run(["ffplay", "-nodisp", "-autoexit", ruta],
                                           capture_output=True, timeout=60)
                        except Exception:
                            pass
            threading.Thread(target=_reproducir_voz, daemon=True).start()

        else:
            responder_comando(chat_id,
                "🤖 <b>Comandos E.M.E.L.Y</b>\n\n"
                "📊 /estado\n📸 /foto\n🔴 /vivo\n⏸ /pausa\n▶️ /reanudar\n"
                "🔇 /silencio [horas]\n⚙️ /regla [nombre] [valor]\n"
                "📍 /zona [X1 Y1 X2 Y2 | ver | off]\n"
                "💬 /mensaje [texto]\n🎤 Nota de voz → se reproduce en los altavoces\n"
                "🛑 /apagar")

    # ════════════════════════════════════════════════════════════════
    #  CÁMARA (corre invisible en background)
    # ════════════════════════════════════════════════════════════════
    def _iniciar_camara(self):
        self.camara = cv2.VideoCapture(CAMARA_INDEX)
        self.camara.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
        self.camara.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.camara.set(cv2.CAP_PROP_FPS, 20)

    def _loop_video(self):
        if not self.corriendo:
            return
            
        import state
        
        # Sincronizar estado para el panel web
        state.set_modo(self.estado)
        # Actualizar contadores si cambiaron (hacemos un sync directo a _estado para no complicar el lock de incrementos)
        with state._lock:
            state._estado["total_alertas"] = self.total_alertas
            state._estado["total_capturas"] = self.total_capturas
            state._estado["silencio_hasta"] = self.detector.silencio_hasta

        if self.camara and self.camara.isOpened():
            ret, frame = self.camara.read()
            if ret:
                self.frame_actual = frame.copy()
                # Procesar detección solo si no está pausado
                if self.estado != "PAUSADO":
                    frame, _ = self.detector.procesar_frame(frame)
                # Compartir frame para stream web (Pinggy)
                stream.set_frame(frame)  # Thread-safe: usa _frame_lock
        self.root.after(40, self._loop_video)   # ~25 FPS

    # ════════════════════════════════════════════════════════════════
    #  CIERRE
    # ════════════════════════════════════════════════════════════════
    def _cerrar(self):
        self.corriendo = False
        if self.camara:
            self.camara.release()
        if tunnel.global_proceso_pinggy:
            try:
                tunnel.global_proceso_pinggy.terminate()
            except Exception:
                pass
        # Enviar aviso de apagado ANTES de destruir la ventana (responde rápido al /apagar)
        try:
            if config.TELEGRAM_ACTIVADO and config.TELEGRAM_TOKEN:
                from notifier import notificar_apagado
                notificar_apagado()
        except Exception:
            pass
        self.root.destroy()
