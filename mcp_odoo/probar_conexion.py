"""Comprueba que las credenciales de .env llegan a Odoo y que el usuario lee.

Uso:  uv run probar_conexion.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from odoo_client import OdooError, OdooReadOnlyClient


def cargar_env() -> None:
    """Lee .env sin depender de python-dotenv."""
    ruta = Path(__file__).parent / ".env"
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


def probar_postgres() -> int:
    from pg_client import PgError, PgReadOnlyClient

    try:
        cli = PgReadOnlyClient()
    except PgError as exc:
        print(f"✗ {exc}")
        print("  Copia .env.ejemplo a .env y rellena los valores (ver README).")
        return 1

    print(f"Conectando a postgres://{cli.host}:{cli.puerto}/{cli.db}")
    print(f"  usuario: {cli.usuario}")

    try:
        info = cli.comprobar()
    except PgError as exc:
        print(f"\n✗ {exc}")
        return 1

    print(f"\n✓ Conectado — {info.get('version', '')}")
    if info.get("solo_lectura") != "on":
        print("⚠ La sesión NO está en solo lectura. Revisa el paso 8 del SQL.")

    try:
        tablas = cli.listar_tablas()
    except PgError as exc:
        print(f"\n⚠ Conecta pero no puede listar tablas: {exc}")
        return 1
    print(f"\nPuede leer {len(tablas)} tablas. Algunas:")
    for t in tablas[:8]:
        filas = t.get("filas_aprox")
        # Postgres devuelve -1 si la tabla nunca pasó por ANALYZE.
        conteo = f"~{filas} filas" if filas and filas >= 0 else ""
        print(f"  · {t['tabla']:<38} {conteo}")

    print("\nComprobando que NO puede escribir...")
    import psycopg

    try:
        with cli._conectar() as con:
            con.execute("CREATE TABLE prueba_escritura_mcp (x int)")
            con.commit()
        print("  ✗ PELIGRO: pudo crear una tabla. Revisa los permisos del rol.")
        return 1
    except psycopg.Error:
        print("  ✓ Postgres rechazó la escritura, como debe ser.")

    print("\nTodo listo. Configura Claude Desktop siguiendo el paso 5 del README.")
    return 0


def main() -> int:
    cargar_env()

    modo = os.environ.get("MODO_CONEXION", "postgres").strip().lower()
    print(f"Modo de conexión: {modo}\n")
    if modo == "postgres":
        return probar_postgres()

    try:
        cliente = OdooReadOnlyClient()
    except OdooError as exc:
        print(f"✗ {exc}")
        print("  Copia .env.ejemplo a .env y rellena los valores (ver README).")
        return 1

    print(f"Conectando a {cliente.url}")
    print(f"  base de datos: {cliente.db}")
    print(f"  usuario:       {cliente.user}")

    try:
        uid = cliente.uid
    except OdooError as exc:
        print(f"\n✗ {exc}")
        return 1
    print(f"\n✓ Conectado (uid {uid}, modo solo lectura)")

    try:
        modelos = cliente.listar_modelos(limite=8)
        print(f"\nEl usuario puede leer. Algunos modelos disponibles:")
        for m in modelos:
            print(f"  · {m['model']:<38} {m['name']}")
    except OdooError as exc:
        print(f"\n⚠ Conecta, pero no puede listar modelos: {exc}")
        print("  Revisa los permisos del usuario en Odoo.")
        return 1

    # Una consulta de negocio real, para confirmar permisos más allá de ir.model.
    try:
        total = cliente.search_count("res.partner", [])
        print(f"\nPrueba de consulta: {total} contactos visibles.")
    except OdooError as exc:
        print(f"\n⚠ No puede leer contactos: {exc}")

    print("\nTodo listo. Configura Claude Desktop siguiendo el paso 4 del README.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
