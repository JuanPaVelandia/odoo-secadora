"""Cliente mínimo de Evolution API para enviar mensajes de WhatsApp.

Reutiliza la instancia que ya existe (jpv_bot). Solo enviamos texto: la
recepción llega por webhook, no por polling.
"""

from __future__ import annotations

import logging
import os

import httpx

log = logging.getLogger(__name__)

# WhatsApp corta los mensajes largos; partimos antes para no perder texto.
LIMITE_MENSAJE = 3500


class EvolutionError(RuntimeError):
    """Fallo al hablar con la Evolution API."""


class EvolutionClient:
    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        instancia: str | None = None,
    ) -> None:
        # Los .env copiados a mano suelen traer espacios y \r al final.
        self.url = (url or os.environ.get("EVOLUTION_API_URL", "")).strip().rstrip("/")
        self.api_key = (api_key or os.environ.get("EVOLUTION_API_KEY", "")).strip()
        self.instancia = (
            instancia or os.environ.get("WHATSAPP_INSTANCE", "")
        ).strip()

        faltantes = [
            n
            for n, v in (
                ("EVOLUTION_API_URL", self.url),
                ("EVOLUTION_API_KEY", self.api_key),
                ("WHATSAPP_INSTANCE", self.instancia),
            )
            if not v
        ]
        if faltantes:
            raise EvolutionError("Faltan variables: " + ", ".join(faltantes))

    def _headers(self) -> dict[str, str]:
        return {"apikey": self.api_key, "Content-Type": "application/json"}

    def enviar(self, destino: str, texto: str) -> None:
        """Envía texto, partiéndolo si excede el límite de WhatsApp."""
        for trozo in _partir(texto, LIMITE_MENSAJE):
            self._enviar_uno(destino, trozo)

    def _enviar_uno(self, destino: str, texto: str) -> None:
        try:
            r = httpx.post(
                f"{self.url}/message/sendText/{self.instancia}",
                headers=self._headers(),
                json={"number": destino, "text": texto},
                timeout=30,
            )
        except httpx.HTTPError as exc:
            raise EvolutionError(f"No se pudo enviar el mensaje: {exc}") from exc

        if r.status_code >= 400:
            raise EvolutionError(
                f"Evolution API devolvió {r.status_code}: {r.text[:300]}"
            )

    def presencia(self, destino: str, estado: str = "composing") -> None:
        """Marca 'escribiendo…' en el chat. Silencioso si falla.

        Es cosmético: si la Evolution API no lo soporta o falla, la consulta
        debe continuar igualmente.
        """
        try:
            httpx.post(
                f"{self.url}/chat/sendPresence/{self.instancia}",
                headers=self._headers(),
                # delay = cuánto mantener el indicador. Con 0 se apaga al
                # instante y el usuario no llega a verlo.
                json={"number": destino, "presence": estado, "delay": 20000},
                timeout=10,
            )
        except httpx.HTTPError as exc:
            log.debug("no se pudo marcar presencia: %s", exc)

    def estado(self) -> dict:
        """Comprueba que la instancia sigue conectada a WhatsApp."""
        try:
            r = httpx.get(
                f"{self.url}/instance/connectionState/{self.instancia}",
                headers=self._headers(),
                timeout=20,
            )
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as exc:
            raise EvolutionError(f"No se pudo consultar el estado: {exc}") from exc


def _partir(texto: str, limite: int) -> list[str]:
    """Parte por líneas para no cortar una tabla o un número por la mitad."""
    if len(texto) <= limite:
        return [texto]

    trozos: list[str] = []
    actual = ""
    for linea in texto.splitlines(keepends=True):
        # Una sola línea más larga que el límite: hay que cortarla igual.
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


def normalizar_numero(jid: str) -> str:
    """Convierte un JID de WhatsApp ('573...@s.whatsapp.net') en solo dígitos."""
    return jid.split("@")[0].split(":")[0].strip()
