"""Servidor MCP de solo lectura sobre Odoo.

Expone la base de datos de la secadora como herramientas de consulta para
Claude. No puede crear ni modificar nada: ver odoo_client.METODOS_PERMITIDOS.

Arranque:  uv run server.py    (requiere ODOO_URL, ODOO_DB, ODOO_USER, ODOO_PASSWORD)
"""

from __future__ import annotations

import json
import os
import sys

from mcp.server.fastmcp import FastMCP

from odoo_client import OdooError, OdooReadOnlyClient

mcp = FastMCP("odoo-secadora")

# El conector funciona en dos modos:
#   MODO=postgres  -> lee la base directamente. No consume licencia de Odoo.
#   MODO=xmlrpc    -> pasa por la API de Odoo. Respeta permisos, gasta usuario.
MODO = os.environ.get("MODO_CONEXION", "postgres").strip().lower()

_cliente: OdooReadOnlyClient | None = None
_pg = None


def cliente() -> OdooReadOnlyClient:
    """Crea el cliente en la primera consulta, no al importar el módulo."""
    global _cliente
    if _cliente is None:
        _cliente = OdooReadOnlyClient()
    return _cliente


def pg():
    """Cliente Postgres perezoso; psycopg solo se importa si se usa este modo."""
    global _pg
    if _pg is None:
        from pg_client import PgReadOnlyClient

        _pg = PgReadOnlyClient()
    return _pg


def _json(dato) -> str:
    return json.dumps(dato, ensure_ascii=False, indent=2, default=str)


def _responder(fn) -> str:
    """Ejecuta la consulta y convierte los fallos en texto útil para el modelo."""
    try:
        return _json(fn())
    except OdooError as exc:
        return f"ERROR: {exc}"
    except Exception as exc:  # nunca tumbar el servidor por una consulta
        # PgError vive en pg_client, que puede no estar importado en modo xmlrpc.
        if type(exc).__name__ == "PgError":
            return f"ERROR: {exc}"
        print(f"[odoo-mcp] error inesperado: {exc!r}", file=sys.stderr)
        return f"ERROR inesperado: {exc}"


def _parsear(texto: str | None, defecto):
    """Los dominios y listas llegan como texto JSON desde el cliente MCP."""
    if not texto or not texto.strip():
        return defecto
    try:
        return json.loads(texto)
    except json.JSONDecodeError as exc:
        raise OdooError(
            f"No pude interpretar {texto!r} como JSON: {exc}. "
            'Ejemplo de dominio: [["state","=","done"]]'
        ) from exc


def _tuplas(dominio):
    """Odoo espera tuplas; JSON las entrega como listas anidadas."""
    if not isinstance(dominio, list):
        raise OdooError('El dominio debe ser una lista, ej: [["state","=","done"]]')
    return [tuple(c) if isinstance(c, list) and len(c) == 3 else c for c in dominio]


@mcp.tool()
def odoo_listar_modelos(filtro: str = "", limite: int = 60) -> str:
    """Lista los modelos/tablas disponibles, para descubrir dónde vive un dato.

    Úsala primero cuando no sepas qué consultar.

    Args:
        filtro: Texto a buscar en el nombre, ej. "secadora" o "stock".
        limite: Máximo de resultados a devolver.
    """
    if MODO == "postgres":
        return _responder(lambda: pg().listar_tablas(filtro or None)[:limite])
    return _responder(lambda: cliente().listar_modelos(filtro or None, limite))


@mcp.tool()
def odoo_describir_modelo(modelo: str) -> str:
    """Muestra los campos/columnas de un modelo o tabla, con su tipo.

    Úsala antes de consultar algo que no conozcas, para saber qué campos pedir
    y sobre cuáles filtrar.

    Args:
        modelo: En modo postgres, el nombre de la tabla ("res_partner", con
            guión bajo). En modo xmlrpc, el modelo Odoo ("res.partner", con punto).
    """
    if MODO == "postgres":
        # Aceptamos las dos notaciones: la gente escribe indistintamente.
        return _responder(lambda: pg().describir_tabla(modelo.replace(".", "_")))
    return _responder(lambda: cliente().fields_get(modelo))


@mcp.tool()
def odoo_sql(consulta: str, limite: int = 100) -> str:
    """Ejecuta una consulta SELECT sobre la base de datos de Odoo.

    Solo disponible en modo postgres. Es la herramienta más potente: permite
    JOINs, agregados, subconsultas y funciones de fecha en una sola llamada.
    Solo lectura — cualquier cosa que no sea SELECT se rechaza.

    Notas sobre el esquema de Odoo:
    - Las tablas usan guión bajo: el modelo "sale.order" es la tabla "sale_order".
    - Los Many2one son columnas "<campo>_id" que apuntan al id de otra tabla.
    - Los campos traducibles (nombres, descripciones) suelen ser jsonb en v19:
      extrae el idioma con ->>'es_CO' o ->>'en_US'.
    - Casi todas las tablas tienen create_date, write_date, create_uid.
    - Para los usuarios usa la vista v_usuarios_basico (res_users está vetada).

    Args:
        consulta: La sentencia SELECT (o WITH ... SELECT). Una sola, sin ';' intermedios.
        limite: Máximo de filas. Si la consulta ya trae LIMIT, se respeta el suyo.
    """
    if MODO != "postgres":
        return (
            "ERROR: odoo_sql solo funciona en modo postgres. "
            "Usa odoo_buscar, odoo_contar u odoo_agrupar."
        )
    return _responder(lambda: pg().consultar(consulta, limite))


@mcp.tool()
def odoo_buscar(
    modelo: str,
    dominio: str = "[]",
    campos: str = "",
    limite: int = 30,
    orden: str = "",
) -> str:
    """Busca registros en Odoo y devuelve sus campos. Es la consulta principal.

    Args:
        modelo: Modelo a consultar, ej. "res.partner".
        dominio: Filtro en sintaxis Odoo como texto JSON. Ejemplos:
            todos: []
            uno: [["state","=","done"]]
            varios (se combinan con Y): [["state","=","done"],["peso",">",1000]]
            con O: ["|",["state","=","done"],["state","=","draft"]]
            por fecha: [["fecha",">=","2026-07-01"]]
            texto parcial: [["name","ilike","corozo"]]
        campos: Lista JSON de campos a traer, ej. ["name","fecha","peso"].
            Vacío trae todos (más lento, úsalo solo para explorar).
        limite: Máximo de registros. Súbelo si necesitas más, pero prefiere
            odoo_contar u odoo_agrupar para totales.
        orden: Orden SQL, ej. "fecha desc" o "name asc".
    """

    if MODO == "postgres":

        def ejecutar_pg():
            tabla = modelo.replace(".", "_")
            cols = _parsear(campos, None)
            seleccion = ", ".join(cols) if cols else "*"
            sql = f"SELECT {seleccion} FROM {tabla}"
            if orden:
                sql += f" ORDER BY {orden}"
            return pg().consultar(sql, limite)

        aviso = None
        if dominio and dominio.strip() not in ("[]", ""):
            aviso = (
                "El filtro se ignoró: en modo postgres los filtros van en la "
                "cláusula WHERE. Usa odoo_sql para filtrar."
            )
        resultado = _responder(ejecutar_pg)
        return f"AVISO: {aviso}\n\n{resultado}" if aviso else resultado

    def ejecutar():
        return cliente().search_read(
            modelo,
            _tuplas(_parsear(dominio, [])),
            _parsear(campos, None),
            limite=limite,
            orden=orden or None,
        )

    return _responder(ejecutar)


@mcp.tool()
def odoo_contar(modelo: str, dominio: str = "[]") -> str:
    """Cuenta cuántos registros cumplen un filtro, sin traerlos.

    Mucho más eficiente que odoo_buscar cuando solo necesitas el número.

    Args:
        modelo: Modelo a consultar, ej. "sale.order".
        dominio: Filtro en sintaxis Odoo como texto JSON, ej. [["state","=","done"]].
    """
    if MODO == "postgres":
        tabla = modelo.replace(".", "_")
        return _responder(
            lambda: pg().consultar(f"SELECT count(*) AS total FROM {tabla}", 1)
        )
    return _responder(
        lambda: {"total": cliente().search_count(modelo, _tuplas(_parsear(dominio, [])))}
    )


@mcp.tool()
def odoo_agrupar(
    modelo: str,
    agrupar_por: str,
    campos: str = "",
    dominio: str = "[]",
    limite: int = 80,
) -> str:
    """Agrupa registros y suma sus valores: totales por cliente, por mes, por estado.

    Es la herramienta para preguntas de negocio tipo "cuánto se secó por finca"
    o "cuántas órdenes hay en cada estado". Devuelve __count por grupo y la suma
    de los campos numéricos que pidas.

    Args:
        modelo: Modelo a consultar, ej. "secadora.orden.secado".
        agrupar_por: Lista JSON de campos por los que agrupar, ej. ["partner_id"].
            Para fechas puedes usar granularidad: ["fecha:month"] o ["fecha:day"].
        campos: Lista JSON de campos numéricos a sumar, ej. ["peso_neto"].
        dominio: Filtro previo en sintaxis Odoo como texto JSON.
        limite: Máximo de grupos a devolver.
    """

    if MODO == "postgres":

        def agrupar_pg():
            grupos = _parsear(agrupar_por, None)
            if isinstance(grupos, str):
                grupos = [grupos]
            if not grupos:
                raise OdooError('Indica al menos un campo, ej. ["partner_id"]')
            tabla = modelo.replace(".", "_")
            claves = ", ".join(grupos)
            sumas = "".join(
                f", sum({c}) AS suma_{c}" for c in (_parsear(campos, None) or [])
            )
            return pg().consultar(
                f"SELECT {claves}, count(*) AS total{sumas} "
                f"FROM {tabla} GROUP BY {claves} ORDER BY total DESC",
                limite,
            )

        return _responder(agrupar_pg)

    def ejecutar():
        grupos = _parsear(agrupar_por, None)
        if isinstance(grupos, str):
            grupos = [grupos]
        if not grupos:
            raise OdooError('Indica al menos un campo en agrupar_por, ej. ["partner_id"]')
        return cliente().read_group(
            modelo,
            _tuplas(_parsear(dominio, [])),
            _parsear(campos, None),
            grupos,
            limite=limite,
        )

    return _responder(ejecutar)


@mcp.tool()
def odoo_estado_conexion() -> str:
    """Comprueba que la conexión con Odoo funciona y muestra a qué base apunta.

    Úsala si otra herramienta falla, para distinguir un problema de conexión
    de un problema de la consulta.
    """

    if MODO == "postgres":

        def estado_pg():
            info = pg().comprobar()
            info["conexion"] = "postgres directo (no consume licencia de Odoo)"
            info["estado"] = "conectado"
            return info

        return _responder(estado_pg)

    def ejecutar():
        c = cliente()
        return {
            "url": c.url,
            "base_de_datos": c.db,
            "usuario": c.user,
            "uid": c.uid,
            "conexion": "xmlrpc (usa un usuario de Odoo)",
            "modo": "solo lectura",
            "estado": "conectado",
        }

    return _responder(ejecutar)


if __name__ == "__main__":
    requeridas = (
        ("PG_HOST", "PG_DB", "PG_USER", "PG_PASSWORD")
        if MODO == "postgres"
        else ("ODOO_URL", "ODOO_DB", "ODOO_USER", "ODOO_PASSWORD")
    )
    print(f"[odoo-mcp] modo de conexión: {MODO}", file=sys.stderr)
    faltan = [v for v in requeridas if not os.environ.get(v)]
    if faltan:
        print(
            "[odoo-mcp] faltan variables de entorno: " + ", ".join(faltan),
            file=sys.stderr,
        )
    mcp.run(transport="stdio")
