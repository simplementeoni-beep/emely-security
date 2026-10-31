"""
detector.py — Detección de movimiento + verificación IA de personas.
Sistema EMELY de Seguridad — Versión Desktop.

Solo dispara alarma si confirma que hay una PERSONA real en el frame.
Usa MobileNetSSD (modelos/) con fallback a HOG de OpenCV.
"""

import os
import threading
import time
from datetime import datetime

import cv2
import numpy as np

import stream  # Para leer global_frame_compartido durante la grabación

import config
from config import (
    CARPETA_CAPTURAS,
    CLIP_DURACION,
    CLIP_ENVIAR_TELEGRAM,
    CLIP_ACTIVADO,
    FORMATO_FOTO,
    TELEGRAM_ACTIVADO,
    HORARIO_ACTIVO,
)

os.makedirs(CARPETA_CAPTURAS, exist_ok=True)

# ── Rutas de modelos ─────────────────────────────────────────────
_DIR    = os.path.dirname(os.path.abspath(__file__))
_MODEL  = os.path.join(_DIR, "modelos", "yolov8n.onnx")
CONFIANZA_MINIMA = 0.50 # 50% de confianza mínima

# ── Parámetros heurísticos (fallback sin IA) ──────────────────────
# Un contorno se considera "persona" si:
#   - Su área es > HEUR_MIN_AREA_PCT % del frame total
#   - Su altura es mayor que su ancho (proporciones verticales)
#   - Su relación alto/ancho está en rango humano razonable
HEUR_MIN_AREA_PCT  = 0.03   # 3% del frame
HEUR_MIN_RATIO     = 1.0    # alto/ancho mínimo (personas son verticales)
HEUR_MAX_RATIO     = 6.0    # alto/ancho máximo (evita líneas finas)


def _cargar_detector_ia():
    """
    Intenta cargar YOLOv8 (formato ONNX).
    Compatible de forma nativa con OpenCV 4.8+ y OpenCV 5.
    """
    try:
        if not os.path.exists(_MODEL):
            return None
        # readNet soporta ONNX nativamente
        net = cv2.dnn.readNet(_MODEL)
        # El nuevo motor de OpenCV 5 configura el backend automáticamente
        print("[EMELY] ✅ Detector IA YOLOv8 (ONNX) cargado — Alta precisión habilitada.")
        return net
    except Exception as e:
        print(f"[EMELY] ⚠ YOLOv8 (ONNX) no disponible ({e}), usando heurística.")
    return None


# Inicializar detectores al importar
_red_ssd = _cargar_detector_ia()

if not _red_ssd:
    print("[EMELY] ℹ Modo heurístico activo — Filtra por tamaño y forma de los contornos.")


def _es_horario_activo():
    if not HORARIO_ACTIVO or not HORARIO_ACTIVO[0]:
        return True
    inicio, fin = HORARIO_ACTIVO
    hora_actual = datetime.now().strftime("%H:%M")
    if inicio <= fin:
        return inicio <= hora_actual <= fin
    else:
        # Cruza la medianoche (ej. 22:00 a 07:00)
        return hora_actual >= inicio or hora_actual <= fin

def _punto_en_zona(cx, cy):
    if not config.ZONA_VIGILANCIA:
        return True
    pto = (float(cx), float(cy))
    poly = np.array(config.ZONA_VIGILANCIA, np.int32)
    return cv2.pointPolygonTest(poly, pto, False) >= 0

def _analizar_postura(w, h):
    ratio = h / max(w, 1)
    if ratio > 1.5: return "DE PIE"
    if ratio < 1.0: return "AGACHADO"
    return "INCLINADO"

def _detectar_personas(frame, contornos_movimiento=None):
    """
    Retorna una lista de diccionarios con info de cada persona detectada:
    [{'x': x, 'y': y, 'w': w, 'h': h, 'postura': str, 'en_zona': bool}]
    """
    h_f, w_f = frame.shape[:2]
    area_frame = h_f * w_f
    personas = []

    # ── 1. YOLOv8 (ONNX) ────────────────────────────────────────
    # Formato de salida YOLOv8: [batch, 84, num_detecciones]
    # Filas 0-3: cx, cy, w, h  | Fila 4: obj_score | Filas 5-84: clases COCO
    # Clase 0 = persona (COCO)
    CLASE_PERSONA  = 0
    NMS_THRESHOLD  = 0.45  # Solapamiento máximo permitido entre cajas

    if _red_ssd is not None:
        try:
            blob = cv2.dnn.blobFromImage(frame, 1/255.0, (320, 320), swapRB=True, crop=False)
            _red_ssd.setInput(blob)
            preds = _red_ssd.forward()

            num_clases = preds.shape[1] - 5  # filas de clase
            if num_clases < 1:
                raise ValueError("Salida ONNX inesperada — revisa el modelo")

            # Score de cada detección = obj_score * max_class_score
            obj_scores   = preds[0][4, :]          # (num_det,)
            class_scores = preds[0][5:, :]         # (num_clases, num_det)
            class_ids    = np.argmax(class_scores, axis=0)
            max_cls_sc   = class_scores[class_ids, np.arange(class_scores.shape[1])]
            final_scores = obj_scores * max_cls_sc

            # Filtrar: solo detecciones de persona con confianza suficiente
            mascara = (class_ids == CLASE_PERSONA) & (final_scores >= CONFIANZA_MINIMA)
            indices_raw = np.where(mascara)[0]

            scale_x = w_f / 320.0
            scale_y = h_f / 320.0

            # Construir listas para NMS (elimina cajas duplicadas sobre la misma persona)
            cajas_nms   = []
            scores_nms  = []
            for i in indices_raw:
                cx, cy, w, h = preds[0][0:4, i]
                cx *= scale_x; cy *= scale_y
                w  *= scale_x; h  *= scale_y
                cajas_nms.append([int(cx - w/2), int(cy - h/2), int(w), int(h)])
                scores_nms.append(float(final_scores[i]))

            # NMS: devuelve solo los índices de las cajas ganadoras
            indices_nms = cv2.dnn.NMSBoxes(
                cajas_nms, scores_nms, CONFIANZA_MINIMA, NMS_THRESHOLD
            )
            if len(indices_nms) > 0:
                for idx in indices_nms.flatten():
                    x, y, w, h = cajas_nms[idx]
                    postura = _analizar_postura(w, h)
                    en_zona = _punto_en_zona(x + w/2, y + h/2)
                    personas.append({'x': x, 'y': y, 'w': w, 'h': h,
                                     'postura': postura, 'en_zona': en_zona})
            if personas:
                return personas
        except Exception as e:
            print(f"[EMELY] ⚠ Error en inferencia YOLOv8: {e}")

    # ── 3. Heurística geométrica (fallback seguro) ─────────────
    if contornos_movimiento and not personas:
        for c in contornos_movimiento:
            area = cv2.contourArea(c)
            if area < area_frame * HEUR_MIN_AREA_PCT:
                continue
            x, y, cw, ch = cv2.boundingRect(c)
            if cw == 0: continue
            ratio = ch / cw
            if HEUR_MIN_RATIO <= ratio <= HEUR_MAX_RATIO:
                cx, cy = x + cw/2, y + ch/2
                postura = _analizar_postura(cw, ch)
                en_zona = _punto_en_zona(cx, cy)
                personas.append({'x': x, 'y': y, 'w': cw, 'h': ch, 
                               'postura': postura, 'en_zona': en_zona})
                
    return personas


class DetectorMovimiento:
    def __init__(self, on_confirmando=None, on_alerta=None, on_standby=None):
        """
        Callbacks:
          on_confirmando(actual, total) → se llama al tomar cada foto silenciosa
          on_alerta(fotos)             → se llama al activar la alarma
          on_standby()                 → se llama al volver a modo normal
        """
        self.on_confirmando = on_confirmando
        self.on_alerta = on_alerta
        self.on_standby = on_standby

        self.frame_anterior = None
        self.en_confirmacion = False
        self.ultima_alarma = 0
        self.alarma_activa = False
        self.estado = "STANDBY"
        self.conteo_capturas = 0
        self.tiempo_ultimo_movimiento = 0
        self.tiempo_ultima_captura = 0
        self.fotos_confirmacion = []
        self.ultimas_amenazas = []
        self.silencio_hasta = 0
        self._lock = threading.Lock()

    def _guardar_foto(self, frame, prefijo="captura", amenazas=None):
        timestamp = datetime.now().strftime(FORMATO_FOTO)
        nombre = f"{prefijo}_{timestamp}.jpg"
        ruta = os.path.join(CARPETA_CAPTURAS, nombre)
        cv2.imwrite(ruta, frame)
        rutas = [ruta]
        
        # Guardar recorte con zoom del intruso en la primera captura
        if amenazas and prefijo == "confirm_1":
            p = amenazas[0]
            x, y, w, h = p['x'], p['y'], p['w'], p['h']
            h_f, w_f = frame.shape[:2]
            pad = int(max(w, h) * 0.4)
            x1 = max(0, x - pad)
            y1 = max(0, y - pad)
            x2 = min(w_f, x + w + pad)
            y2 = min(h_f, y + h + pad)
            
            recorte = frame[y1:y2, x1:x2]
            if recorte.size > 0:
                ruta_zoom = os.path.join(CARPETA_CAPTURAS, f"zoom_{timestamp}.jpg")
                cv2.imwrite(ruta_zoom, recorte)
                rutas.append(ruta_zoom)
                
        return rutas

    def _grabar_clip(self, duracion: int = 20):
        """
        Graba un clip de video de `duracion` segundos usando los frames
        actuales de la cámara. Corre en un hilo separado — no bloquea nada.
        Guarda el archivo .mp4 en CARPETA_CAPTURAS con timestamp.
        Prueba codecs en orden de compatibilidad: mp4v → XVID → MJPG.
        """
        if not CLIP_ACTIVADO:
            return

        timestamp = datetime.now().strftime(FORMATO_FOTO)
        nombre    = f"clip_{timestamp}.mp4"
        ruta      = os.path.join(CARPETA_CAPTURAS, nombre)

        # Obtener dimensiones del frame actual (thread-safe)
        frame_ref = stream.get_frame()
        if frame_ref is None:
            print("[EMELY] ⚠ No hay frame disponible para grabar clip.")
            return

        h, w = frame_ref.shape[:2]

        # Probar codecs en orden de preferencia (compatibilidad Linux)
        writer = None
        for codec in ["mp4v", "XVID", "MJPG"]:
            try:
                fourcc = cv2.VideoWriter_fourcc(*codec)
                writer = cv2.VideoWriter(ruta, fourcc, 20.0, (w, h))
                if writer.isOpened():
                    print(f"[EMELY] 🎬 Grabando clip con codec {codec}: {nombre}")
                    break
                writer.release()
                writer = None
            except Exception:
                writer = None

        if writer is None:
            print("[EMELY] ❌ No se pudo inicializar VideoWriter. Clip no grabado.")
            return

        fin = time.time() + duracion
        frames_grabados = 0
        while time.time() < fin:
            f = stream.get_frame()  # Thread-safe: usa _frame_lock
            if f is not None:
                writer.write(f)
                frames_grabados += 1
            time.sleep(1 / 20.0)  # ~20 fps

        writer.release()
        print(f"[EMELY] ✅ Clip guardado: {nombre} ({frames_grabados} frames, {duracion}s)")

        # Enviar clip por Telegram si está activado
        if CLIP_ENVIAR_TELEGRAM and TELEGRAM_ACTIVADO:
            try:
                from notifier import notificar_clip
                notificar_clip(ruta)
            except Exception as e:
                print(f"[TELEGRAM] Error al enviar clip: {e}")

    def _activar_alarma(self, fotos):
        ahora = time.time()
        if ahora - self.ultima_alarma < config.COOLDOWN_ALARMA:
            return
        self.ultima_alarma = ahora
        self.alarma_activa = True
        self.estado = "ALERTA"
        print("🚨 [EMELY] ¡INTRUSO DETECTADO — ALARMA ACTIVADA!")
        if self.on_alerta:
            self.on_alerta(fotos)

        # Grabar clip de evidencia en hilo separado
        threading.Thread(target=self._grabar_clip, args=(CLIP_DURACION,), daemon=True).start()

        # Notificación por Telegram
        if TELEGRAM_ACTIVADO:
            try:
                from notifier import notificar_intruso
                notificar_intruso(fotos)
            except Exception as e:
                print(f"[TELEGRAM] Error al notificar: {e}")

        def _apagar():
            time.sleep(config.COOLDOWN_ALARMA)
            self.alarma_activa = False
            self.estado = "STANDBY"
            print("[EMELY] Sistema vuelve a modo STANDBY.")
            if self.on_standby:
                self.on_standby()

        threading.Thread(target=_apagar, daemon=True).start()


    def procesar_frame(self, frame):
        """
        Analiza el frame en dos fases:
          1. Detección rápida de movimiento (pixel diff).
          2. Si hay movimiento, verificación IA: ¿hay una PERSONA?
        Solo inicia la secuencia de confirmación si la IA confirma una persona real.
        """
        gris = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gris = cv2.GaussianBlur(gris, (21, 21), 0)

        if self.frame_anterior is None:
            self.frame_anterior = gris
            return frame, False

        delta = cv2.absdiff(self.frame_anterior, gris)
        thresh = cv2.threshold(delta, config.UMBRAL_BINARIO, 255, cv2.THRESH_BINARY)[1]
        thresh = cv2.dilate(thresh, None, iterations=2)
        contornos, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        hay_movimiento_pixeles = False
        for c in contornos:
            if cv2.contourArea(c) >= config.SENSIBILIDAD:
                hay_movimiento_pixeles = True
                x, y, w, h = cv2.boundingRect(c)
                cv2.rectangle(frame, (x, y), (x + w, y + h), (100, 100, 100), 1)

        self.frame_anterior = gris
        ahora = time.time()

        # ── FASE 2: Verificación IA ─────────────────────────────
        movimiento = False
        if hay_movimiento_pixeles:
            contornos_grandes = [c for c in contornos if cv2.contourArea(c) >= config.SENSIBILIDAD]
            personas = _detectar_personas(frame, contornos_grandes)
            
            # Dibujar zona de vigilancia si existe
            if config.ZONA_VIGILANCIA:
                pts = np.array(config.ZONA_VIGILANCIA, np.int32).reshape((-1, 1, 2))
                cv2.polylines(frame, [pts], True, (255, 150, 0), 2)
            
            amenazas = []  # ← inicializar siempre antes de usarlo
            if personas:
                # Comprobar horario y silencio manual
                en_horario = _es_horario_activo()
                en_silencio = ahora < self.silencio_hasta
                
                for p in personas:
                    x, y, w, h = p['x'], p['y'], p['w'], p['h']
                    es_amenaza = p['en_zona'] and en_horario and not en_silencio
                    
                    if es_amenaza:
                        amenazas.append(p)
                        color = (0, 0, 255) if self.estado == "ALERTA" else (0, 229, 255)
                        txt = f"AMENAZA: {p['postura']}"
                    else:
                        color = (0, 255, 0) # Ignorado (fuera de zona u horario)
                        txt = f"IGNORADO: {p['postura']}"
                        
                    cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
                    cv2.putText(frame, txt, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
            else:
                cv2.putText(frame, "Mov. ignorado (sin persona)", (10, 45),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (80, 80, 80), 1)

            # Acumular calor con CUALQUIER movimiento grande, no solo personas confirmadas por IA
            import state as _state_hm
            if _state_hm.get().get("mapa_calor"):
                if not hasattr(self, 'heatmap') or self.heatmap is None or \
                   self.heatmap.shape[:2] != (frame.shape[0], frame.shape[1]):
                    self.heatmap = np.zeros((frame.shape[0], frame.shape[1]), dtype=np.float32)

                if personas:
                    # Personas confirmadas por IA → calor intenso
                    for p in personas:
                        x, y, w, h = p['x'], p['y'], p['w'], p['h']
                        y1, y2 = max(0, y), min(frame.shape[0], y + h)
                        x1, x2 = max(0, x), min(frame.shape[1], x + w)
                        self.heatmap[y1:y2, x1:x2] += 6.0
                else:
                    # Cualquier contorno de movimiento → calor suave
                    for c in contornos_grandes:
                        x, y, w, h = cv2.boundingRect(c)
                        y1, y2 = max(0, y), min(frame.shape[0], y + h)
                        x1, x2 = max(0, x), min(frame.shape[1], x + w)
                        self.heatmap[y1:y2, x1:x2] += 2.0

            if len(amenazas) >= config.MINIMO_PERSONAS_ALARMA:
                movimiento = True
                self.ultimas_amenazas = amenazas

        # ── RENDERIZADO DEL HEATMAP ──────────────────────────────
        # Va FUERA del if hay_movimiento_pixeles para que el rastro
        # acumulado se muestre persistentemente incluso sin movimiento.
        import state as _state_hm2
        if _state_hm2.get().get("mapa_calor"):
            if not hasattr(self, 'heatmap') or self.heatmap is None or \
               self.heatmap.shape[:2] != (frame.shape[0], frame.shape[1]):
                self.heatmap = np.zeros((frame.shape[0], frame.shape[1]), dtype=np.float32)

            # Enfriamiento gradual (una vez por frame, no por movimiento)
            self.heatmap -= 0.08
            self.heatmap = np.clip(self.heatmap, 0, 255)

            hm_norm = np.uint8(self.heatmap)
            if hm_norm.max() > 10:  # Solo renderizar si hay algo que mostrar
                hm_color = cv2.applyColorMap(hm_norm, cv2.COLORMAP_JET)
                mascara_bool = (hm_norm > 10)
                mascara_3d = np.stack([mascara_bool, mascara_bool, mascara_bool], axis=-1)
                mezclado = cv2.addWeighted(frame, 0.45, hm_color, 0.55, 0)
                frame[:] = np.where(mascara_3d, mezclado, frame)

                # Etiqueta discreta en la esquina
                cv2.putText(frame, "HEAT", (frame.shape[1] - 60, 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 100, 255), 1)
        else:
            # Si se desactiva, limpiar rastros para reinicio limpio
            if hasattr(self, 'heatmap') and self.heatmap is not None:
                self.heatmap.fill(0)


        if movimiento:
            self.tiempo_ultimo_movimiento = ahora

        if not self.alarma_activa:
            if movimiento:
                if not self.en_confirmacion:
                    self.en_confirmacion = True
                    self.estado = "CONFIRMANDO"
                    self.conteo_capturas = 1
                    self.fotos_confirmacion = self._guardar_foto(frame, "confirm_1", self.ultimas_amenazas)
                    self.tiempo_ultima_captura = ahora
                    if self.on_confirmando:
                        self.on_confirmando(1, config.CAPTURAS_ANTES_DE_ALARMA)
                else:
                    if ahora - self.tiempo_ultima_captura >= config.TIEMPO_ENTRE_CAPTURAS:
                        self.conteo_capturas += 1
                        self.fotos_confirmacion.extend(
                            self._guardar_foto(frame, f"confirm_{self.conteo_capturas}")
                        )
                        self.tiempo_ultima_captura = ahora
                        if self.on_confirmando:
                            self.on_confirmando(self.conteo_capturas, config.CAPTURAS_ANTES_DE_ALARMA)

                        if self.conteo_capturas >= config.CAPTURAS_ANTES_DE_ALARMA:
                            self._activar_alarma(self.fotos_confirmacion)
                            self.en_confirmacion = False
                            self.conteo_capturas = 0
            else:
                # Cancelar confirmación si pasaron 3 segundos sin persona detectada
                if self.en_confirmacion and (ahora - self.tiempo_ultimo_movimiento > 3.0):
                    print("[EMELY] Confirmación cancelada — no se detectó persona sostenida.")
                    self.en_confirmacion = False
                    self.estado = "STANDBY"
                    self.conteo_capturas = 0
                    self.fotos_confirmacion = []
                    if self.on_standby:
                        self.on_standby()

        return frame, movimiento


