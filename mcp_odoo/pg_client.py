"""Cliente PostgreSQL de solo lectura sobre la base de Odoo.

No consume licencia de Odoo: habla directamente con la base. A cambio, las
reglas de acceso de Odoo (record rules, permisos por grupo) NO aplican, así
que la restricción vive en tres capas:

  1. El rol de Postgres solo tiene SELECT (ver crear_usuario_lectura.sql).
  2. La sesión es `default_transaction_read_only = on`.
  3. Este módulo rechaza cualquier SQL que no sea un SELECT limpio.

La capa 1 es la que manda; las otras dos atrapan errores antes de la red.
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.rows import dict_row

# Palabras que jamás deben aparecer en una consulta de este conector.
PROHIBIDO = re.compile(
    r"\b(insert|update|delete|truncate|drop|alter|create|grant|revoke|"
    r"copy|vacuum|reindex|cluster|comment|call|do|set|reset|"
    r"listen|notify|lock|prepare|execute|refresh|import|security)\b",
    re.IGNORECASE,
)

# Tablas que no se exponen ni para lectura, por si el GRANT del VPS se relajara.
TABLAS_VETADAS = frozenset({
    "res_users",
    "res_users_apikeys",
    "res_users_apikeys_description",
    "ir_config_parameter",
    "ir_logging",
    "ir_mail_server",
    "fetchmail_server",
    "auth_totp_device",
})
# ir_attachment NO está vetada: el bot necesita consultarla para encontrar
# fotos y documentos. Lo que se controla es qué puede *enviar*, filtrando
# por res_model en adjuntos.MODELOS_PERMITIDOS. Los metadatos (nombre, tipo,
# tamaño) son inocuos; el contenido de los archivos no está en esta tabla.

LIMITE_MAXIMO = 500


class PgError(RuntimeError):
    """Fallo de consulta, ya redactado para mostrar al usuario."""


def _validar_select(sql: str) -> str:
    """Acepta un único SELECT/WITH y rechaza todo lo demás."""
    limpio = sql.strip().rstrip(";").strip()
    if not limpio:
        raise PgError("La consulta está vacía.")

    # Comentarios pueden esconder payloads; fuera antes de analizar.
    sin_comentarios = re.sub(r"--[^\n]*", " ", limpio)
    sin_comentarios = re.sub(r"/\*.*?\*/", " ", sin_comentarios, flags=re.DOTALL)

    # Y fuera también los literales de texto: lo que va entre comillas es un
    # DATO, no SQL ejecutable. Sin esto, buscar '%comment%' o '%CALL%' -algo
    # perfectamente legítimo- se rechaza como si fuera un intento de
    # escritura. Se reemplazan por '' para no alterar la estructura.
    sin_literales = re.sub(r"'(?:[^']|'')*'", "''", sin_comentarios)

    if ";" in sin_literales:
        raise PgError(
            "Solo se admite una consulta por llamada (se encontró ';' intermedio)."
        )

    if not re.match(r"^\s*(select|with)\b", sin_literales, re.IGNORECASE):
        raise PgError("Solo se permiten consultas SELECT: este conector es de solo lectura.")

    prohibida = PROHIBIDO.search(sin_literales)
    if prohibida:
        raise PgError(
            f"La palabra {prohibida.group(0).upper()!r} no está permitida: "
            "este conector solo puede leer."
        )

    for tabla in TABLAS_VETADAS:
        if re.search(rf"\b{tabla}\b", sin_literales, re.IGNORECASE):
            raise PgError(
                f"La tabla {tabla!r} no está disponible por seguridad. "
                "Para datos de usuarios usa la vista 'v_usuarios_basico'."
            )
    return limpio


class PgReadOnlyClient:
    """Conexión perezosa a Postgres, restringida a SELECT."""

    def __init__(
        self,
        host: str | None = None,
        puerto: int | None = None,
        db: str | None = None,
        usuario: str | None = None,
        password: str | None = None,
    ) -> None:
        self.host = host or os.environ.get("PG_HOST", "")
        self.puerto = int(puerto or os.environ.get("PG_PORT", "5432"))
        self.db = db or os.environ.get("PG_DB", "")
        self.usuario = usuario or os.environ.get("PG_USER", "")
        self.password = password or os.environ.get("PG_PASSWORD", "")

        faltantes = [
            n
            for n, v in (
                ("PG_HOST", self.host),
                ("PG_DB", self.db),
                ("PG_USER", self.usuario),
                ("PG_PASSWORD", self.password),
            )
            if not v
        ]
        if faltantes:
            raise PgError("Faltan variables de entorno: " + ", ".join(faltantes))

    def _conectar(self) -> psycopg.Connection:
        try:
            return psycopg.connect(
                host=self.host,
                port=self.puerto,
                dbname=self.db,
                user=self.usuario,
                password=self.password,
                connect_timeout=15,
                # Cuarta red: aunque el rol pudiera escribir, esta sesión no.
                autocommit=False,
                options="-c default_transaction_read_only=on -c statement_timeout=30000",
            )
        except psycopg.OperationalError as exc:
            raise PgError(_mensaje_conexion(exc, self)) from exc

    def consultar(self, sql: str, limite: int = 100) -> list[dict[str, Any]]:
        """Ejecuta un SELECT y devuelve filas como diccionarios."""
        validado = _validar_select(sql)
        limite = max(1, min(limite, LIMITE_MAXIMO))

        # Solo envolvemos si la consulta no trae ya su propio LIMIT.
        if not re.search(r"\blimit\s+\d+\s*$", validado, re.IGNORECASE):
            final = f"SELECT * FROM ({validado}) AS consulta_mcp LIMIT {limite}"
        else:
            final = validado

        try:
            with self._conectar() as con:
                with con.cursor(row_factory=dict_row) as cur:
                    cur.execute(final)  # type: ignore[arg-type]
                    filas = cur.fetchall()
                con.rollback()  # nada que confirmar; cerramos limpio
        except psycopg.errors.InsufficientPrivilege as exc:
            raise PgError(
                f"El usuario {self.usuario!r} no tiene permiso para leer eso. "
                "Revisa los GRANT del script crear_usuario_lectura.sql."
            ) from exc
        except psycopg.errors.ReadOnlySqlTransaction as exc:
            raise PgError("Bloqueado: la sesión es de solo lectura.") from exc
        except psycopg.errors.UndefinedTable as exc:
            raise PgError(
                f"Esa tabla no existe. Usa listar_tablas para ver las disponibles. ({exc})"
            ) from exc
        except psycopg.errors.UndefinedColumn as exc:
            raise PgError(f"Columna inexistente: {exc}") from exc
        except psycopg.errors.QueryCanceled as exc:
            raise PgError(
                "La consulta tardó más de 30 s y se canceló. Acota el rango "
                "de fechas o agrupa en vez de traer filas."
            ) from exc
        except psycopg.Error as exc:
            raise PgError(f"Error de consulta: {str(exc).strip()}") from exc

        return [_limpiar(f) for f in filas]

    def listar_tablas(self, filtro: str | None = None) -> list[dict]:
        sql = """
            SELECT c.relname AS tabla,
                   obj_description(c.oid) AS descripcion,
                   c.reltuples::bigint AS filas_aprox
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relkind IN ('r', 'v', 'm')
              AND has_table_privilege(c.oid, 'SELECT')
        """
        if filtro:
            seguro = re.sub(r"[^\w ]", "", filtro)
            sql += f" AND c.relname ILIKE '%{seguro}%'"
        sql += " ORDER BY c.relname"
        return self.consultar(sql, limite=LIMITE_MAXIMO)

    def describir_tabla(self, tabla: str) -> list[dict]:
        seguro = re.sub(r"[^\w]", "", tabla)
        if seguro in TABLAS_VETADAS:
            raise PgError(f"La tabla {tabla!r} no está disponible por seguridad.")
        return self.consultar(
            f"""
            SELECT a.attname AS columna,
                   format_type(a.atttypid, a.atttypmod) AS tipo,
                   NOT a.attnotnull AS acepta_nulo,
                   col_description(a.attrelid, a.attnum) AS descripcion
            FROM pg_attribute a
            WHERE a.attrelid = 'public.{seguro}'::regclass
              AND a.attnum > 0 AND NOT a.attisdropped
            ORDER BY a.attnum
            """,
            limite=LIMITE_MAXIMO,
        )

    def comprobar(self) -> dict:
        filas = self.consultar(
            "SELECT current_database() AS base, current_user AS usuario, "
            "version() AS version, "
            "current_setting('default_transaction_read_only') AS solo_lectura",
            limite=1,
        )
        info = filas[0] if filas else {}
        info["version"] = str(info.get("version", "")).split(",")[0]
        return info


def _limpiar(fila: dict) -> dict:
    """Normaliza tipos para JSON y recorta valores enormes."""
    salida = {}
    for clave, valor in fila.items():
        if isinstance(valor, (bytes, memoryview)):
            salida[clave] = f"<binario, {len(valor)} bytes>"
        elif isinstance(valor, Decimal):
            # Sin esto se serializan como texto ("3000") y el modelo no puede
            # operar con ellos: los importes y pesos de Odoo son numeric.
            salida[clave] = int(valor) if valor == valor.to_integral_value() else float(valor)
        elif isinstance(valor, (date, datetime)):
            salida[clave] = valor.isoformat()
        elif isinstance(valor, timedelta):
            salida[clave] = str(valor)
        elif isinstance(valor, str) and len(valor) > 2000:
            salida[clave] = valor[:2000] + f"… (recortado, {len(valor)} caracteres)"
        else:
            salida[clave] = valor
    return salida


def _mensaje_conexion(exc: psycopg.OperationalError, cli: PgReadOnlyClient) -> str:
    texto = str(exc).lower()
    if "authentication" in texto or "password" in texto:
        return f"Postgres rechazó la contraseña del usuario {cli.usuario!r}."
    if "does not exist" in texto and "database" in texto:
        return f"La base de datos {cli.db!r} no existe en {cli.host}."
    if "timeout" in texto or "could not connect" in texto or "refused" in texto:
        return (
            f"No se pudo conectar a {cli.host}:{cli.puerto}. "
            "¿Está abierto el túnel SSH? (ver README, paso 3)"
        )
    if "no pg_hba.conf entry" in texto:
        return (
            f"Postgres no acepta conexiones de esta IP para {cli.usuario!r}. "
            "Usa el túnel SSH en vez de exponer el puerto (ver README)."
        )
    return f"No se pudo conectar a Postgres: {str(exc).strip()}"
