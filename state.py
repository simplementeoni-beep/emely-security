"""
state.py — Estado compartido de E.M.E.L.Y.
Sistema EMELY de Seguridad.
Desarrollador: ONI (https://github.com/simplementeoni-beep)

Punto central de verdad del sistema.
  · El HUD registra callbacks al arrancar.
  · La API web y Telegram los invocan sin depender del HUD.
  · Cualquier módulo puede leer el estado actual.
"""

import threading
import time
from typing import Callable, Optional

# ── Bloqueo de escritura ─────────────────────────────────────────────
_lock = threading.Lock()

# ── Estado mutable del sistema ───────────────────────────────────────
_estado: dict = {
    "modo":           "STANDBY",   # STANDBY | CONFIRMANDO | ALERTA | PAUSADO
    "total_alertas":  0,
    "total_capturas": 0,
    "silencio_hasta": 0.0,         # timestamp Unix
    "tiempo_inicio":  time.time(), # timestamp Unix al arrancar
    "mapa_calor":     False,       # Para mostrar el mapa térmico
}

# ── Callbacks registrados por el HUD ────────────────────────────────
_CALLBACKS_VALIDOS = {"pausar", "reanudar", "foto", "silencio", "apagar"}
_callbacks: dict[str, Optional[Callable]] = {k: None for k in _CALLBACKS_VALIDOS}


# ════════════════════════════════════════════════════════════════
#  LECTURA DEL ESTADO
# ════════════════════════════════════════════════════════════════

def get() -> dict:
    """Devuelve una copia inmutable del estado actual."""
    with _lock:
        return dict(_estado)


def get_modo() -> str:
    with _lock:
        return _estado["modo"]


def get_silencio_hasta() -> float:
    with _lock:
        return _estado["silencio_hasta"]


def en_silencio() -> bool:
    return time.time() < get_silencio_hasta()


# ════════════════════════════════════════════════════════════════
#  ESCRITURA DEL ESTADO
# ════════════════════════════════════════════════════════════════

def set_modo(modo: str) -> None:
    with _lock:
        _estado["modo"] = modo

def toggle_mapa_calor() -> None:
    with _lock:
        _estado["mapa_calor"] = not _estado.get("mapa_calor", False)


def incrementar_alertas(capturas: int = 0) -> None:
    with _lock:
        _estado["total_alertas"]  += 1
        _estado["total_capturas"] += capturas


def sumar_capturas(n: int) -> None:
    with _lock:
        _estado["total_capturas"] += n


def set_silencio(horas: float) -> None:
    with _lock:
        _estado["silencio_hasta"] = time.time() + horas * 3600


# ════════════════════════════════════════════════════════════════
#  CALLBACKS
# ════════════════════════════════════════════════════════════════

def registrar(nombre: str, fn: Callable) -> None:
    """El HUD llama a esto al iniciar para registrar cada acción."""
    if nombre not in _CALLBACKS_VALIDOS:
        raise ValueError(f"[STATE] Callback desconocido: '{nombre}'")
    _callbacks[nombre] = fn


def invocar(nombre: str, *args, **kwargs) -> None:
    """Invoca un callback registrado. No hace nada si no está registrado."""
    fn = _callbacks.get(nombre)
    if callable(fn):
        fn(*args, **kwargs)
    else:
        print(f"[STATE] ⚠ Callback '{nombre}' no registrado aún.")
