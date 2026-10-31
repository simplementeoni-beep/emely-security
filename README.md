<div align="center">

# 🛡️ E.M.E.L.Y

### Electronic Monitoring and Emergency Logistics sYstem

**Sistema de seguridad inteligente con IA, control remoto por Telegram y transmisión en vivo.**

**Desarrollado por [ONI](https://github.com/simplementeoni-beep)**

![Python](https://img.shields.io/badge/Python-3.10+-3776ab?style=for-the-badge&logo=python&logoColor=white)
![Developer](https://img.shields.io/badge/Developer-ONI-9d00ff?style=for-the-badge)
![OpenCV](https://img.shields.io/badge/OpenCV-5.x-5C3EE8?style=for-the-badge&logo=opencv&logoColor=white)
![YOLOv8](https://img.shields.io/badge/YOLOv8-ONNX-00FFFF?style=for-the-badge)
![Telegram](https://img.shields.io/badge/Telegram-Bot_API-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-Web_Server-000000?style=for-the-badge&logo=flask&logoColor=white)
![Linux](https://img.shields.io/badge/Linux-Desktop-FCC624?style=for-the-badge&logo=linux&logoColor=black)

</div>

---

## 🎯 ¿Qué es E.M.E.L.Y?

E.M.E.L.Y es un sistema de videovigilancia inteligente construido desde cero en Python. Usa la cámara de tu computadora como sensor, detecta intrusos con inteligencia artificial (YOLOv8), y te notifica en tiempo real a través de Telegram — con fotos, clips de video y transmisión en vivo desde cualquier parte del mundo.

**No es un tutorial. Es un sistema funcional.**

### ✨ Características principales

| Característica | Descripción |
|---|---|
| 🧠 **Detección IA** | YOLOv8 Nano (ONNX) con fallback heurístico — filtra sombras y mascotas |
| 🔐 **Anti-falsas alarmas** | Sistema de confirmación: N capturas antes de activar alarma |
| 📱 **Control remoto** | 12+ comandos Telegram: estado, foto, pausa, zona, silencio, apagar... |
| 🔴 **Stream en vivo** | Transmisión MJPEG accesible desde cualquier lugar vía túnel Pinggy |
| 💻 **Panel web táctico** | Interfaz estilo HUD de videojuego con control táctil |
| 🎬 **Clips de evidencia** | Grabación automática de video al detectar intruso |
| 🗺️ **Geofencing** | Define zonas de vigilancia específicas (puerta, ventana, etc.) |
| 🔥 **Mapa de calor** | Visualización térmica de actividad acumulada |
| 🎤 **Voz bidireccional** | Envía notas de voz que se reproducen en los altavoces de la PC |
| 🛡️ **Fachada JARVIS** | El intruso ve una pantalla animada — no sabe que es una cámara |
| ⏰ **Horarios** | Vigila solo en las horas que configures (ej: 22:00 a 07:00) |
| 📊 **Reportes** | Resumen diario automático y reporte de cierre de sesión |

---

## 🏗️ Arquitectura

```
E.M.E.L.Y/
├── app.py           # Punto de entrada — orquesta el arranque
├── config.py        # Configuración centralizada
├── detector.py      # Detección de movimiento + IA (YOLOv8)
├── notifier.py      # Telegram: alertas, comandos, reportes
├── stream.py        # Servidor Flask + MJPEG + API REST
├── tunnel.py        # Túnel SSH Pinggy con auto-reconexión
├── state.py         # Estado global thread-safe (singleton)
├── ui/
│   └── hud.py       # Interfaz visual animada (Tkinter)
├── web/
│   └── templates/
│       └── panel.html  # Panel web táctico
├── modelos/
│   └── yolov8n.onnx    # Modelo de IA (no incluido, ver instalación)
├── .env.example     # Plantilla de variables de entorno
├── requirements.txt # Dependencias Python
└── capturas/        # Fotos y clips (generado automáticamente)
```

### Pipeline de detección

```
Frame de cámara
      │
      ▼
┌─────────────────┐
│  Diferencia de   │ ← Rápido, detecta cualquier cambio
│  pixeles (BGR→   │
│  Gris→Blur→Diff) │
└───────┬─────────┘
        │ ¿Hay movimiento?
        ▼
┌─────────────────┐
│  YOLOv8 Nano    │ ← ¿Es una PERSONA? (clase 0 COCO)
│  (ONNX + NMS)   │
└───────┬─────────┘
        │ ¿Persona confirmada + en zona + en horario?
        ▼
┌─────────────────┐
│  Confirmación   │ ← N capturas silenciosas antes de alarmar
│  (anti-falsos)  │
└───────┬─────────┘
        │ ¿N capturas consecutivas con persona?
        ▼
   🚨 ALARMA
   ├── 📸 Fotos → Telegram
   ├── 🎬 Clip de video (20s)
   ├── 🔊 Alarma sonora + voz
   └── 🔒 Bloqueo de sesión
```

---

## 🚀 Instalación

### Requisitos previos

- **Linux** (Fedora, Ubuntu, Arch...)
- **Python 3.10+**
- **Cámara web** (integrada o USB)
- **SSH** instalado (para túnel Pinggy)

### 1. Clonar el repositorio

```bash
git clone https://github.com/TU_USUARIO/emely-security.git
cd emely-security
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 3. Descargar el modelo de IA

Descarga [YOLOv8n ONNX](https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8n.onnx) y colócalo en `modelos/`:

```bash
mkdir -p modelos
wget -O modelos/yolov8n.onnx https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8n.onnx
```

> **Sin modelo:** El sistema sigue funcionando con detección heurística (filtra por tamaño y forma), pero con menor precisión.

### 4. Configurar credenciales

```bash
cp .env.example .env
```

Edita `.env` con tu token de Telegram y Chat ID:

```env
TELEGRAM_TOKEN=tu_token_aqui
TELEGRAM_CHAT_ID=tu_chat_id_aqui
```

<details>
<summary><b>¿Cómo obtener el Token y Chat ID?</b></summary>

1. Abre Telegram y busca **@BotFather**
2. Envía `/newbot` y sigue las instrucciones → te dará un **token**
3. Busca **@userinfobot** y envía cualquier mensaje → te dará tu **Chat ID**
4. Pega ambos valores en el archivo `.env`

</details>

### 5. Ejecutar

```bash
python app.py
```

---

## 📱 Comandos Telegram

Una vez activo, E.M.E.L.Y responde a estos comandos desde tu teléfono:

| Comando | Acción |
|---|---|
| `/estado` | Modo actual, alertas, capturas, hardware, reglas |
| `/foto` | Captura y envía una foto al instante |
| `/vivo` | Enlace al stream en vivo y panel web |
| `/pausa` | Pausa la detección |
| `/reanudar` | Reactiva la vigilancia |
| `/silencio [h]` | Ignora detecciones por N horas |
| `/zona X1 Y1 X2 Y2` | Define zona de vigilancia (% del frame) |
| `/zona ver` | Foto con la zona dibujada |
| `/zona off` | Vigilar toda la cámara |
| `/mapa` | Activa/desactiva mapa de calor |
| `/mensaje [texto]` | Muestra texto en el stream y HUD |
| 🎤 *Nota de voz* | Se reproduce en los altavoces de la PC |
| `/apagar` | Cierra el sistema de forma segura |

---

## ⚙️ Configuración

Todos los parámetros se ajustan en [`config.py`](config.py):

```python
# Detección
SENSIBILIDAD = 1500           # Área mínima de movimiento (px²)
CAPTURAS_ANTES_DE_ALARMA = 3  # Confirmaciones antes de alarmar
COOLDOWN_ALARMA = 15          # Segundos entre alertas
MINIMO_PERSONAS_ALARMA = 1    # Personas requeridas para alarma

# Clips
CLIP_ACTIVADO = True          # Grabar video al detectar
CLIP_DURACION = 20            # Duración del clip (segundos)

# Horario (None = 24/7)
HORARIO_ACTIVO = None         # Ej: ("22:00", "07:00")

# Zonas (vacío = toda la cámara)
ZONA_VIGILANCIA = []          # Ej: [(100,100), (500,100), (500,400), (100,400)]
```

---

## 🛣️ Roadmap

- [x] Detección de movimiento + IA (YOLOv8)
- [x] Notificaciones y comandos Telegram
- [x] Stream en vivo con túnel Pinggy
- [x] Panel web táctico
- [x] Geofencing (zonas de vigilancia)
- [x] Grabación de clips de evidencia
- [x] Mapa de calor visual
- [x] Reportes diarios automáticos
- [x] Mensajes de voz bidireccionales
- [ ] Reconocimiento de caras conocidas
- [ ] Análisis de patrones de actividad
- [ ] Historial de eventos en SQLite
- [ ] Integración con luces smart
- [ ] Sistema de disuasión activa
- [ ] Multi-cámara

Ver [`FUTURO.txt`](FUTURO.txt) para el roadmap completo.

---

## 📝 Historial de versiones

Ver [`CHANGELOG.txt`](CHANGELOG.txt) para el historial detallado de cada versión.

**Versión actual: v2.7 — "Percepción Avanzada"**

---

## 🔒 Seguridad

- Las credenciales de Telegram **nunca** se suben al repositorio (`.env` está en `.gitignore`)
- Todas las URLs del stream llevan un **token de seguridad** generado al arrancar
- El bot solo responde al **Chat ID autorizado** (dueño)
- La fachada visual oculta la función de vigilancia al intruso

## 👨‍💻 Programador / Autor

Este proyecto fue diseñado, programado y estructurado por:

- **Programador:** **ONI**
- **GitHub:** [@simplementeoni-beep](https://github.com/simplementeoni-beep)
- **Repositorio:** [emely-security](https://github.com/simplementeoni-beep/emely-security)

---

## 📄 Licencia

Proyecto personal de uso educativo y doméstico.

---

<div align="center">

**Construido con 🧠 y ☕ — inspirado en JARVIS**

*"El objetivo no es vender, es tener tu propia infraestructura."*

</div>
