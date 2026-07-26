"""Webhook que recibe mensajes de WhatsApp y responde consultando Odoo.

Evolution API entrega aquí los mensajes entrantes; contestamos con el
resultado de consultar la base de Odoo en lenguaje natural.

Arranque:  uvicorn servidor:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import logging
import os
import threading
import time

from fastapi import BackgroundTasks, FastAPI, Request

from agente import Agente
from evolution import EvolutionClient, EvolutionError, normalizar_numero

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("whatsapp-odoo")

app = FastAPI(title="Consultas Odoo por WhatsApp")

agente = Agente()
evolution = EvolutionClient()

# Números autorizados. Sin esto, cualquiera que conozca el número del bot
# podría consultar los datos de la empresa.
AUTORIZADOS = {
    n.strip().lstrip("+")
    for n in os.environ.get("NUMEROS_AUTORIZADOS", "").split(",")
    if n.strip()
}

# Evita procesar dos veces el mismo mensaje: Evolution reintenta si el
# webhook tarda o falla.
_vistos: dict[str, float] = {}
_vistos_lock = threading.Lock()
VENTANA_VISTOS = 600  # segundos

# Una consulta a la vez por número, para que un usuario impaciente que manda
# tres mensajes seguidos no dispare tres cadenas de consultas en paralelo.
_ocupados: set[str] = set()
_ocupados_lock = threading.Lock()

AYUDA = (
    "Consulto los datos de Odoo. Pregúntame en español, por ejemplo:\n\n"
    "- ¿Cuántas órdenes de secado hay abiertas?\n"
    "- Peso total secado este mes por finca\n"
    "- Facturas de compra sin pagar\n"
    "- Los 10 clientes con más volumen este año"
)


@app.get("/salud")
def salud() -> dict:
    """Comprobación para el proxy y para diagnosticar a mano."""
    estado = {"servicio": "ok", "autorizados": len(AUTORIZADOS)}
    try:
        estado["whatsapp"] = evolution.estado().get("instance", {}).get("state")
    except EvolutionError as exc:
        estado["whatsapp"] = f"error: {exc}"
    try:
        estado["odoo"] = agente.pg.comprobar().get("base")
    except Exception as exc:
        estado["odoo"] = f"error: {exc}"
    return estado


@app.post("/webhook")
async def webhook(request: Request, tareas: BackgroundTasks) -> dict:
    """Recibe el mensaje y responde 200 de inmediato.

    El trabajo real va a segundo plano: una consulta puede tardar más de lo
    que Evolution espera antes de reintentar.
    """
    try:
        cuerpo = await request.json()
    except Exception:
        return {"status": "cuerpo ilegible"}

    datos = cuerpo.get("data") or {}
    if cuerpo.get("event") not in (None, "messages.upsert"):
        return {"status": "evento ignorado"}

    clave = datos.get("key") or {}
    if clave.get("fromMe"):
        return {"status": "propio"}

    jid = clave.get("remoteJid") or ""
    if jid.endswith("@g.us"):
        # Grupos fuera: la lista de autorizados es por número.
        return {"status": "grupo ignorado"}

    mensaje_id = clave.get("id") or ""
    if not _marcar_visto(mensaje_id):
        return {"status": "duplicado"}

    numero = normalizar_numero(jid)
    texto = _extraer_texto(datos.get("message") or {})
    if not texto:
        return {"status": "sin texto"}

    if numero not in AUTORIZADOS:
        log.warning("mensaje de número no autorizado: %s", numero)
        # No respondemos: quien no está en la lista no debe saber que esto existe.
        return {"status": "no autorizado"}

    tareas.add_task(_atender, numero, texto)
    return {"status": "encolado"}


def _atender(numero: str, texto: str) -> None:
    """Consulta y responde. Corre fuera del ciclo de la petición."""
    pregunta = texto.strip()

    if pregunta.lower() in ("ayuda", "hola", "/ayuda", "?", "menu", "menú"):
        _responder(numero, AYUDA)
        return

    with _ocupados_lock:
        if numero in _ocupados:
            _responder(
                numero, "Sigo con tu consulta anterior, dame un momento."
            )
            return
        _ocupados.add(numero)

    inicio = time.monotonic()
    # "Escribiendo…" mientras trabajamos, para que se note que hay alguien.
    parar_presencia = _mantener_escribiendo(numero)
    try:
        respuesta = agente.responder(pregunta)
        log.info(
            "consulta de %s resuelta en %.1fs: %r",
            numero,
            time.monotonic() - inicio,
            pregunta[:80],
        )
    except Exception as exc:
        log.exception("fallo atendiendo a %s", numero)
        respuesta = (
            "Se me atravesó un error consultando la base. "
            f"Detalle: {str(exc)[:200]}"
        )
    finally:
        parar_presencia.set()
        with _ocupados_lock:
            _ocupados.discard(numero)

    _responder(numero, respuesta)


def _mantener_escribiendo(numero: str) -> threading.Event:
    """Refresca el indicador hasta que se marque el Event devuelto.

    WhatsApp lo caduca a los ~25s, así que hay que renovarlo o el usuario
    lo ve desaparecer justo cuando la consulta se está alargando.
    """
    parar = threading.Event()

    def bucle() -> None:
        while not parar.is_set():
            evolution.presencia(numero, "composing")
            # Antes de que WhatsApp lo caduque.
            if parar.wait(15):
                break

    threading.Thread(target=bucle, daemon=True).start()
    return parar


def _responder(numero: str, texto: str) -> None:
    try:
        evolution.enviar(numero, texto)
    except EvolutionError as exc:
        log.error("no se pudo responder a %s: %s", numero, exc)


def _extraer_texto(mensaje: dict) -> str:
    """Saca el texto de las variantes que manda WhatsApp."""
    if isinstance(mensaje.get("conversation"), str):
        return mensaje["conversation"]
    extendido = mensaje.get("extendedTextMessage") or {}
    if isinstance(extendido.get("text"), str):
        return extendido["text"]
    # Pie de foto o de video: puede traer la pregunta.
    for clave in ("imageMessage", "videoMessage", "documentMessage"):
        sub = mensaje.get(clave) or {}
        if isinstance(sub.get("caption"), str):
            return sub["caption"]
    return ""


def _marcar_visto(mensaje_id: str) -> bool:
    """True si es la primera vez que vemos este mensaje."""
    if not mensaje_id:
        return True
    ahora = time.time()
    with _vistos_lock:
        # Purga perezosa: sin esto el diccionario crece indefinidamente.
        for k, t in list(_vistos.items()):
            if ahora - t > VENTANA_VISTOS:
                del _vistos[k]
        if mensaje_id in _vistos:
            return False
        _vistos[mensaje_id] = ahora
    return True


if __name__ == "__main__":
    import uvicorn

    if not AUTORIZADOS:
        log.warning(
            "NUMEROS_AUTORIZADOS está vacío: el bot ignorará todos los mensajes."
        )
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PUERTO", "8080")))
