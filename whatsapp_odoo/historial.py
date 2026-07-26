"""Registra cada consulta del bot en Postgres, para poder auditarlas.

Conexión y rol SEPARADOS de los de consulta: `claude_lectura` debe seguir sin
poder escribir nada. Este rol solo inserta en `bot.consultas`, y ni siquiera
puede modificar o borrar lo ya escrito.

Si el registro falla, la consulta del usuario continúa igualmente: perder una
línea de auditoría es preferible a dejar sin respuesta a quien preguntó.
"""

from __future__ import annotations

import logging
import os
import threading

import psycopg

log = logging.getLogger(__name__)

# Recortes para no llenar la tabla con respuestas gigantes.
MAX_PREGUNTA = 2000
MAX_RESPUESTA = 8000


class Historial:
    """Escribe el registro de consultas. Silencioso ante fallos."""

    def __init__(self) -> None:
        self.dsn = self._construir_dsn()
        self.activo = bool(self.dsn)
        self._lock = threading.Lock()
        if not self.activo:
            log.info("historial desactivado: falta PG_HISTORIAL_PASSWORD")

    def _construir_dsn(self) -> str | None:
        password = os.environ.get("PG_HISTORIAL_PASSWORD", "").strip()
        if not password:
            return None
        return (
            f"host={os.environ.get('PG_HOST', '127.0.0.1')} "
            f"port={os.environ.get('PG_PORT', '5432')} "
            f"dbname={os.environ.get('PG_DB', 'secadora_2')} "
            f"user={os.environ.get('PG_HISTORIAL_USER', 'claude_historial')} "
            f"password={password} "
            f"connect_timeout=10"
        )

    def registrar(
        self,
        numero: str,
        pregunta: str,
        respuesta: str | None = None,
        vueltas: int | None = None,
        segundos: float | None = None,
        coste_usd: float | None = None,
        modelo: str | None = None,
        tokens: dict | None = None,
        con_adjunto: bool = False,
        error: str | None = None,
    ) -> None:
        """Inserta una fila. Nunca lanza excepción hacia arriba."""
        if not self.activo:
            return

        t = tokens or {}
        try:
            # Conexión por escritura: son pocas al día y así no mantenemos
            # una conexión ociosa contra la base de producción.
            with self._lock, psycopg.connect(self.dsn, autocommit=True) as con:
                con.execute(
                    """
                    INSERT INTO bot.consultas
                        (numero, pregunta, respuesta, vueltas, segundos,
                         coste_usd, modelo, tokens_in, tokens_cache,
                         tokens_out, con_adjunto, error)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        numero,
                        pregunta[:MAX_PREGUNTA],
                        (respuesta or "")[:MAX_RESPUESTA] or None,
                        vueltas,
                        round(segundos, 2) if segundos is not None else None,
                        round(coste_usd, 6) if coste_usd is not None else None,
                        modelo,
                        t.get("entrada"),
                        (t.get("cache_lectura") or 0) + (t.get("cache_escritura") or 0),
                        t.get("salida"),
                        con_adjunto,
                        (error or "")[:1000] or None,
                    ),
                )
        except Exception as exc:
            # A propósito no propagamos: el usuario ya tiene su respuesta.
            log.warning("no se pudo registrar la consulta: %s", exc)

    def comprobar(self) -> str:
        """Estado para /salud."""
        if not self.activo:
            return "desactivado"
        try:
            with psycopg.connect(self.dsn, autocommit=True) as con:
                n = con.execute("SELECT count(*) FROM bot.consultas").fetchone()[0]
            return f"ok ({n} consultas)"
        except Exception as exc:
            return f"error: {str(exc)[:100]}"
