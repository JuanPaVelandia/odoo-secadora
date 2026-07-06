#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configura la API Key de báscula en Odoo vía XML-RPC.

Lee la configuración desde variables de entorno / archivo .env
(NUNCA credenciales hardcodeadas en este archivo).

Variables usadas (ver .env.example):
    BASCULA_ODOO_URL, BASCULA_ODOO_DB, BASCULA_ODOO_USER,
    BASCULA_ODOO_PASSWORD, BASCULA_API_KEY

Si no defines BASCULA_API_KEY, se genera una aleatoria segura.
"""

import os
import sys
import secrets
import xmlrpc.client

from dotenv import load_dotenv

load_dotenv()

ODOO_URL = os.getenv("BASCULA_ODOO_URL", "").rstrip('/')
DB = os.getenv("BASCULA_ODOO_DB", "")
USER = os.getenv("BASCULA_ODOO_USER", "")
PASSWORD = os.getenv("BASCULA_ODOO_PASSWORD", "")
API_KEY = os.getenv("BASCULA_API_KEY", "")


def main():
    faltantes = [
        nombre for nombre, valor in [
            ("BASCULA_ODOO_URL", ODOO_URL),
            ("BASCULA_ODOO_DB", DB),
            ("BASCULA_ODOO_USER", USER),
            ("BASCULA_ODOO_PASSWORD", PASSWORD),
        ] if not valor
    ]
    if faltantes:
        print("ERROR: faltan variables de entorno: " + ", ".join(faltantes))
        print("Copia bridge/.env.example a bridge/.env y complétalo.")
        return 1

    api_key = API_KEY or secrets.token_urlsafe(32)
    if not API_KEY:
        print("No se definió BASCULA_API_KEY; se generó una nueva automáticamente.")

    print("Conectando a Odoo...")
    common = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/common')
    uid = common.authenticate(DB, USER, PASSWORD, {})
    print(f"UID: {uid}")

    if not uid:
        print("Error: no se pudo autenticar (revisa usuario/contraseña/DB).")
        return 1

    models = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/object')
    models.execute_kw(DB, uid, PASSWORD, 'ir.config_parameter', 'set_param',
                      ['bascula.api_key', api_key])
    print("API Key configurada!")

    valor = models.execute_kw(DB, uid, PASSWORD, 'ir.config_parameter', 'get_param',
                              ['bascula.api_key'])
    print(f"Verificacion - API Key guardada: {valor}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
