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

import adjuntos
from agente import Agente

# Dos canales posibles:
#   meta      -> WhatsApp Business Cloud API (oficial). Automatizar es su
#                proposito, no restringen el numero. No da acceso a grupos.
#   evolution -> Evolution API sobre Baileys. Lee grupos, pero WhatsApp
#                puede restringir el numero por spam (nos pasó).
CANAL = os.environ.get("CANAL", "meta").strip().lower()

if CANAL == "meta":
    from meta_wa import MetaError as ErrorCanal
    from meta_wa import MetaWhatsApp as ClienteCanal
    from meta_wa import normalizar_numero
else:
    from evolution import EvolutionClient as ClienteCanal
    from evolution import EvolutionError as ErrorCanal
    from evolution import normalizar_numero

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("whatsapp-odoo")

app = FastAPI(title="Consultas Odoo por WhatsApp")

agente = Agente()
evolution = ClienteCanal()
log.info("canal de mensajería: %s", CANAL)

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

# Última pregunta de cada número, para descartar reentregas de Evolution que
# llegan con un id distinto (y por tanto burlan _marcar_visto).
_ultima_pregunta: dict[str, tuple[str, float]] = {}

# Formatos de imagen que Claude lee directamente.
MIMES_IMAGEN = {"image/jpeg", "image/png", "image/gif", "image/webp"}

AYUDA = (
    "Consulto los datos de Odoo. Pregúntame en español, por ejemplo:\n\n"
    "- ¿Cuántas órdenes de secado hay abiertas?\n"
    "- Peso total secado este mes por finca\n"
    "- Facturas de compra sin pagar\n"
    "- Los 10 clientes con más volumen este año\n\n"
    "*Cotizaciones*: mándame el PDF o una foto y te digo si los precios "
    "cuadran con lo que hemos pagado antes por esos repuestos.\n\n"
    "*Fotos*: pídeme la foto de un pesaje o de un análisis y te la mando.\n\n"
    "Recuerdo el hilo de la conversación, así que puedes preguntar "
    '"¿y el mes pasado?" sin repetirlo todo.\n'
    'Escribe *nuevo* para empezar de cero.'
)

# Historial por número, para las preguntas de seguimiento. En memoria: se
# pierde al reiniciar el contenedor, y no vale la pena persistirlo.
_historial: dict[str, list[dict]] = {}
_ultimo_uso: dict[str, float] = {}
_historial_lock = threading.Lock()

# Cuántos pares pregunta/respuesta conservar. Más historial = más tokens
# reenviados en cada consulta.
MAX_TURNOS = 10
# Pasado este tiempo sin escribir, el hilo se considera terminado.
EXPIRA_HISTORIAL = 30 * 60


@app.get("/salud")
def salud() -> dict:
    """Comprobación para el proxy y para diagnosticar a mano."""
    estado = {"servicio": "ok", "autorizados": len(AUTORIZADOS)}
    try:
        estado["whatsapp"] = evolution.estado().get("instance", {}).get("state")
    except ErrorCanal as exc:
        estado["whatsapp"] = f"error: {exc}"
    try:
        estado["odoo"] = agente.pg.comprobar().get("base")
    except Exception as exc:
        estado["odoo"] = f"error: {exc}"
    estado["filestore"] = (
        "ok" if adjuntos.filestore_disponible() else "no montado"
    )
    return estado


@app.get("/webhook")
async def verificar_webhook(request: Request):
    """Meta valida la URL con un GET antes de entregar mensajes."""
    from fastapi.responses import PlainTextResponse

    p = request.query_params
    esperado = os.environ.get("META_VERIFY_TOKEN", "")
    if p.get("hub.mode") == "subscribe" and p.get("hub.verify_token") == esperado:
        log.info("webhook verificado por Meta")
        return PlainTextResponse(p.get("hub.challenge", ""))
    log.warning("intento de verificación con token incorrecto")
    return PlainTextResponse("token incorrecto", status_code=403)


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

    if CANAL == "meta":
        return _webhook_meta(cuerpo, tareas)

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
    mensaje = datos.get("message") or {}
    texto = _extraer_texto(mensaje)
    adjunto = _detectar_adjunto(mensaje)

    if not texto and not adjunto:
        return {"status": "sin texto"}

    if numero not in AUTORIZADOS:
        log.warning("mensaje de número no autorizado: %s", numero)
        # No respondemos: quien no está en la lista no debe saber que esto existe.
        return {"status": "no autorizado"}

    tareas.add_task(_atender, numero, texto, adjunto, mensaje_id)
    return {"status": "encolado"}


def _webhook_meta(cuerpo: dict, tareas) -> dict:
    """Procesa el formato de la Cloud API, que anida bastante.

    entry[] -> changes[] -> value -> messages[]
    """
    try:
        valor = cuerpo["entry"][0]["changes"][0]["value"]
    except (KeyError, IndexError, TypeError):
        return {"status": "formato desconocido"}

    mensajes = valor.get("messages") or []
    if not mensajes:
        # Meta también envía acuses de entrega y lectura; no nos interesan.
        return {"status": "sin mensajes"}

    m = mensajes[0]
    mensaje_id = m.get("id") or ""
    if not _marcar_visto(mensaje_id):
        return {"status": "duplicado"}

    numero = normalizar_numero(m.get("from") or "")
    if numero not in AUTORIZADOS:
        log.warning("mensaje de número no autorizado: %s", numero)
        return {"status": "no autorizado"}

    tipo = m.get("type")
    texto = ""
    media_id = None

    if tipo == "text":
        texto = (m.get("text") or {}).get("body", "")
    elif tipo == "image":
        img = m.get("image") or {}
        media_id = img.get("id")
        texto = img.get("caption", "")
    elif tipo == "document":
        doc = m.get("document") or {}
        mime = (doc.get("mime_type") or "").split(";")[0].strip()
        if mime == "application/pdf" or mime in MIMES_IMAGEN:
            media_id = doc.get("id")
            texto = doc.get("caption", "")
        else:
            tareas.add_task(
                _responder,
                numero,
                "Solo puedo leer PDF e imágenes. Si es un Excel o un Word, "
                "mándame una captura o expórtalo a PDF.",
            )
            return {"status": "tipo no soportado"}
    else:
        # Audio, ubicación, contactos, stickers...
        tareas.add_task(
            _responder,
            numero,
            "Por ahora solo entiendo texto, fotos y PDF.",
        )
        return {"status": f"tipo {tipo} ignorado"}

    if not texto and not media_id:
        return {"status": "sin contenido"}

    # El doble check azul: señal barata de que el mensaje llegó.
    try:
        evolution.marcar_leido(mensaje_id)
    except Exception:
        pass

    tareas.add_task(_atender_meta, numero, texto, media_id)
    return {"status": "encolado"}


def _atender_meta(numero: str, texto: str, media_id: str | None) -> None:
    """Descarga el adjunto (si lo hay) y delega en el flujo normal."""
    documento = None
    if media_id:
        try:
            mime, b64 = evolution.descargar_media(media_id)
            documento = (mime, b64)
        except ErrorCanal as exc:
            log.error("no se pudo bajar el adjunto de %s: %s", numero, exc)
            _responder(
                numero,
                "No pude descargar el archivo. Intenta reenviarlo, o mándame "
                "una foto si es un documento.",
            )
            return
    _atender(numero, texto, documento_ya_descargado=documento)


def _atender(
    numero: str,
    texto: str,
    adjunto: str | None = None,
    mensaje_id: str = "",
    documento_ya_descargado: tuple[str, str] | None = None,
) -> None:
    """Consulta y responde. Corre fuera del ciclo de la petición.

    Los dos canales entregan los adjuntos de forma distinta: Meta los baja
    antes de llamar aquí (`documento_ya_descargado`), Evolution los baja
    dentro a partir de `mensaje_id`.
    """
    pregunta = texto.strip()
    if documento_ya_descargado and not adjunto:
        adjunto = documento_ya_descargado[0]

    if adjunto == "no-soportado":
        _responder(
            numero,
            "Solo puedo leer PDF e imágenes. Si es un Excel o un Word, "
            "mándame una captura o expórtalo a PDF.",
        )
        return

    orden = pregunta.lower().strip(" .!¡")

    if orden in ("ayuda", "hola", "/ayuda", "?", "menu", "menú"):
        _responder(numero, AYUDA)
        return

    if orden in ("nuevo", "/nuevo", "limpiar", "reiniciar", "olvida"):
        with _historial_lock:
            _historial.pop(numero, None)
            _ultimo_uso.pop(numero, None)
        _responder(numero, "Listo, empezamos de cero. ¿Qué necesitas?")
        return

    with _ocupados_lock:
        # Segunda barrera contra duplicados: Evolution puede reentregar el
        # mismo texto con otro id de mensaje, y entonces _marcar_visto no lo
        # detecta. Procesarlo dos veces duplica el gasto de API.
        ahora = time.monotonic()
        anterior = _ultima_pregunta.get(numero)
        # Los adjuntos se exceptúan: dos cotizaciones distintas pueden llegar
        # con el mismo texto ("revisa precios") y ambas deben atenderse.
        if (
            not adjunto
            and anterior
            and anterior[0] == pregunta
            and ahora - anterior[1] < 60
        ):
            log.info("descarto repeticion de %s: %r", numero, pregunta[:60])
            return
        _ultima_pregunta[numero] = (pregunta, ahora)

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
        documento = documento_ya_descargado
        if adjunto and mensaje_id and not documento:
            try:
                documento = (adjunto, evolution.descargar_media(mensaje_id))
                log.info("adjunto %s descargado de %s", adjunto, numero)
            except ErrorCanal as exc:
                log.error("no se pudo bajar el adjunto de %s: %s", numero, exc)
                parar_presencia.set()
                with _ocupados_lock:
                    _ocupados.discard(numero)
                _responder(
                    numero,
                    "No pude descargar el archivo. Intenta reenviarlo, o "
                    "mándame una foto si es un documento.",
                )
                return
            if not pregunta:
                # Adjunto sin texto: asumimos la intención más común.
                pregunta = (
                    "Te mando este documento. Analízalo y dime si los precios "
                    "tienen sentido comparados con lo que hemos pagado antes."
                )

        def mandar_archivo(b64, nombre, mime, pie=""):
            evolution.enviar_archivo(numero, b64, nombre, mime, pie)

        respuesta, nuevo_historial = agente.responder(
            pregunta, _leer_historial(numero), documento, mandar_archivo
        )
        _guardar_historial(numero, nuevo_historial)
        log.info(
            "consulta de %s resuelta en %.1fs (%d turnos): %r",
            numero,
            time.monotonic() - inicio,
            len(nuevo_historial) // 2,
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


def _leer_historial(numero: str) -> list[dict]:
    """Historial reciente del número, o vacío si expiró."""
    ahora = time.time()
    with _historial_lock:
        # Purga la conversación de cualquiera que lleve rato sin escribir.
        for n, visto in list(_ultimo_uso.items()):
            if ahora - visto > EXPIRA_HISTORIAL:
                _historial.pop(n, None)
                _ultimo_uso.pop(n, None)
        return list(_historial.get(numero, []))


def _guardar_historial(numero: str, historial: list[dict]) -> None:
    """Guarda recortando a los últimos MAX_TURNOS pares pregunta/respuesta."""
    recortado = historial[-(MAX_TURNOS * 2) :]
    # El historial debe empezar por 'user': si el recorte dejó una respuesta
    # del asistente al inicio, la API rechaza la siguiente petición.
    while recortado and recortado[0].get("role") != "user":
        recortado.pop(0)
    with _historial_lock:
        _historial[numero] = recortado
        _ultimo_uso[numero] = time.time()


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
    except ErrorCanal as exc:
        log.error("no se pudo responder a %s: %s", numero, exc)


def _detectar_adjunto(mensaje: dict) -> str | None:
    """Devuelve el tipo MIME si el mensaje trae PDF o imagen, o None.

    Solo esos dos: son los que Claude puede leer directamente.
    """
    if "imageMessage" in mensaje:
        imagen = mensaje.get("imageMessage") or {}
        mime = (imagen.get("mimetype") or "").split(";")[0].strip()
        # WhatsApp no siempre declara el tipo; jpeg es el caso abrumador.
        return mime if mime in MIMES_IMAGEN else "image/jpeg"

    doc = mensaje.get("documentMessage") or {}
    if not doc:
        # WhatsApp usa este envoltorio cuando el documento lleva pie de foto.
        doc = (mensaje.get("documentWithCaptionMessage") or {}).get(
            "message", {}
        ).get("documentMessage") or {}
    if doc:
        mime = (doc.get("mimetype") or "").split(";")[0].strip()
        if mime == "application/pdf":
            return mime
        if mime in MIMES_IMAGEN:
            return mime
        log.info("adjunto de tipo no soportado: %s", mime)
        return "no-soportado"

    return None


def _extraer_texto(mensaje: dict) -> str:
    """Saca el texto de las variantes que manda WhatsApp."""
    if isinstance(mensaje.get("conversation"), str):
        return mensaje["conversation"]
    extendido = mensaje.get("extendedTextMessage") or {}
    if isinstance(extendido.get("text"), str):
        return extendido["text"]
    # Pie de foto o de documento: casi siempre trae la pregunta real.
    for clave in ("imageMessage", "videoMessage", "documentMessage"):
        sub = mensaje.get(clave) or {}
        if isinstance(sub.get("caption"), str) and sub["caption"].strip():
            return sub["caption"]
    # WhatsApp envuelve así los documentos con pie de foto.
    envuelto = (mensaje.get("documentWithCaptionMessage") or {}).get(
        "message", {}
    ).get("documentMessage") or {}
    if isinstance(envuelto.get("caption"), str):
        return envuelto["caption"]
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
