"""Cliente de la WhatsApp Business Cloud API (Meta).

Alternativa oficial a Evolution API: automatizar es su propósito, así que no
hay riesgo de que restrinjan el número por spam. A cambio no da acceso a
grupos — para eso sigue haciendo falta Evolution.

Requiere: número verificado en Meta, token permanente y Phone Number ID.
"""

from __future__ import annotations

import logging
import os

import httpx

log = logging.getLogger(__name__)

VERSION_API = os.environ.get("META_API_VERSION", "v21.0")

# WhatsApp corta los mensajes largos; partimos antes para no perder texto.
LIMITE_MENSAJE = 3500

# Tipos que la Cloud API acepta como documento o imagen.
MIMES_IMAGEN = {"image/jpeg", "image/png"}


class MetaError(RuntimeError):
    """Fallo al hablar con la Cloud API, ya redactado para el usuario."""


class MetaWhatsApp:
    """Envía y recibe mensajes por la API oficial de WhatsApp."""

    def __init__(
        self,
        token: str | None = None,
        phone_number_id: str | None = None,
    ) -> None:
        self.token = (token or os.environ.get("META_TOKEN", "")).strip()
        self.phone_id = (
            phone_number_id or os.environ.get("META_PHONE_NUMBER_ID", "")
        ).strip()

        faltantes = [
            n
            for n, v in (
                ("META_TOKEN", self.token),
                ("META_PHONE_NUMBER_ID", self.phone_id),
            )
            if not v
        ]
        if faltantes:
            raise MetaError("Faltan variables: " + ", ".join(faltantes))

        self.base = f"https://graph.facebook.com/{VERSION_API}"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    # -- envío -----------------------------------------------------------

    def enviar(self, destino: str, texto: str) -> None:
        """Envía texto, partiéndolo si excede el límite."""
        for trozo in _partir(texto, LIMITE_MENSAJE):
            self._post(
                {
                    "messaging_product": "whatsapp",
                    "to": destino,
                    "type": "text",
                    "text": {"body": trozo, "preview_url": False},
                }
            )

    def enviar_archivo(
        self, destino: str, b64: str, nombre: str, mime: str, pie: str = ""
    ) -> None:
        """Sube el archivo a Meta y lo envía.

        A diferencia de Evolution, la Cloud API no acepta base64 en el envío:
        primero hay que subir el binario y usar el id que devuelve.
        """
        import base64

        try:
            datos = base64.b64decode(b64)
        except Exception as exc:
            raise MetaError(f"El archivo llegó corrupto: {exc}") from exc

        media_id = self._subir(datos, nombre, mime)

        if mime in MIMES_IMAGEN:
            cuerpo = {"type": "image", "image": {"id": media_id}}
            if pie:
                cuerpo["image"]["caption"] = pie[:900]
        else:
            cuerpo = {
                "type": "document",
                "document": {"id": media_id, "filename": nombre},
            }
            if pie:
                cuerpo["document"]["caption"] = pie[:900]

        self._post({"messaging_product": "whatsapp", "to": destino, **cuerpo})

    def _subir(self, datos: bytes, nombre: str, mime: str) -> str:
        """Sube un archivo y devuelve su media id."""
        try:
            r = httpx.post(
                f"{self.base}/{self.phone_id}/media",
                headers={"Authorization": f"Bearer {self.token}"},
                files={"file": (nombre, datos, mime)},
                data={"messaging_product": "whatsapp", "type": mime},
                timeout=120,
            )
        except httpx.HTTPError as exc:
            raise MetaError(f"No se pudo subir el archivo: {exc}") from exc

        if r.status_code >= 400:
            raise MetaError(f"Meta rechazó el archivo: {_error(r)}")

        media_id = r.json().get("id")
        if not media_id:
            raise MetaError("Meta no devolvió el id del archivo.")
        return media_id

    def presencia(self, destino: str, estado: str = "composing") -> None:
        """No existe en la API oficial. Se ignora en silencio.

        Meta no expone el indicador 'escribiendo…'; el código que lo llama
        funciona igual porque esto es un no-op.
        """
        return None

    def marcar_leido(self, mensaje_id: str) -> None:
        """Marca el mensaje como leído (el doble check azul)."""
        try:
            self._post(
                {
                    "messaging_product": "whatsapp",
                    "status": "read",
                    "message_id": mensaje_id,
                }
            )
        except MetaError as exc:
            log.debug("no se pudo marcar leído: %s", exc)

    def _post(self, cuerpo: dict) -> dict:
        try:
            r = httpx.post(
                f"{self.base}/{self.phone_id}/messages",
                headers=self._headers(),
                json=cuerpo,
                timeout=60,
            )
        except httpx.HTTPError as exc:
            raise MetaError(f"No se pudo contactar con Meta: {exc}") from exc

        if r.status_code >= 400:
            raise MetaError(_error(r))
        return r.json()

    # -- descarga de adjuntos entrantes ----------------------------------

    def descargar_media(self, media_id: str) -> tuple[str, str]:
        """Descarga un adjunto recibido. Devuelve (mime, base64).

        Son dos pasos: pedir la URL y luego bajarla con el token.
        """
        import base64

        try:
            r = httpx.get(
                f"{self.base}/{media_id}",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=60,
            )
            r.raise_for_status()
            info = r.json()
            url = info.get("url")
            mime = (info.get("mime_type") or "").split(";")[0].strip()
            if not url:
                raise MetaError("Meta no devolvió la URL del adjunto.")

            # La descarga también requiere el token: la URL no es pública.
            d = httpx.get(
                url,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=120,
            )
            d.raise_for_status()
        except httpx.HTTPError as exc:
            raise MetaError(f"No se pudo descargar el adjunto: {exc}") from exc

        return mime, base64.b64encode(d.content).decode("ascii")

    def estado(self) -> dict:
        """Comprueba que el token y el número siguen siendo válidos."""
        try:
            r = httpx.get(
                f"{self.base}/{self.phone_id}",
                headers={"Authorization": f"Bearer {self.token}"},
                params={"fields": "verified_name,quality_rating,display_phone_number"},
                timeout=30,
            )
        except httpx.HTTPError as exc:
            raise MetaError(f"No se pudo consultar el estado: {exc}") from exc

        if r.status_code >= 400:
            raise MetaError(_error(r))

        d = r.json()
        # Imitamos la forma que devuelve Evolution para que /salud no cambie.
        return {
            "instance": {
                "instanceName": d.get("display_phone_number", self.phone_id),
                "state": "open",
                "calidad": d.get("quality_rating"),
                "nombre": d.get("verified_name"),
            }
        }


def _error(r: httpx.Response) -> str:
    """Extrae el mensaje de error de Meta, que viene anidado."""
    try:
        err = r.json().get("error", {})
        msg = err.get("message") or r.text[:200]
        detalle = err.get("error_data", {}).get("details")
        return f"{msg}{f' ({detalle})' if detalle else ''} [HTTP {r.status_code}]"
    except Exception:
        return f"HTTP {r.status_code}: {r.text[:200]}"


def _partir(texto: str, limite: int) -> list[str]:
    """Parte por líneas para no cortar una tabla o un número por la mitad."""
    if len(texto) <= limite:
        return [texto]

    trozos: list[str] = []
    actual = ""
    for linea in texto.splitlines(keepends=True):
        while len(linea) > limite:
            if actual:
                trozos.append(actual)
                actual = ""
            trozos.append(linea[:limite])
            linea = linea[limite:]
        if len(actual) + len(linea) > limite:
            trozos.append(actual)
            actual = linea
        else:
            actual += linea
    if actual:
        trozos.append(actual)
    return trozos


def normalizar_numero(numero: str) -> str:
    """Meta entrega el número ya limpio, pero por si acaso."""
    return numero.split("@")[0].split(":")[0].strip().lstrip("+")
