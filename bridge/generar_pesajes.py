#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generador de pesajes aleatorios para PRUEBAS.

Crea N pesajes en estado borrador directamente en Odoo (vía XML-RPC), con
placas, terceros, lugares, variedades y tipos de operación aleatorios. Deja
los pesajes listos para que tú los gestiones (pesadas, órdenes, despachos).

Los catálogos mínimos (tipos de vehículo/operación, lugares, vehículos,
conductores, terceros, variedades) se crean automáticamente si no existen.

Configuración: lee bridge/.env (mismas variables que el simulador):
    BASCULA_ODOO_URL, BASCULA_ODOO_DB, BASCULA_ODOO_USER, BASCULA_ODOO_PASSWORD

Uso:
    python3 bridge/generar_pesajes.py            # crea 5 pesajes
    python3 bridge/generar_pesajes.py 12         # crea 12 pesajes
    python3 bridge/generar_pesajes.py 8 --seed   # además siembra catálogos extra

NOTA: úsalo solo contra una base de datos de PRUEBAS.
"""

import os
import sys
import random
import xmlrpc.client

try:
    from dotenv import load_dotenv
    load_dotenv()
except ModuleNotFoundError:
    # dotenv es opcional: si no está instalado, cargamos bridge/.env a mano
    # (parser mínimo KEY=VALUE) y también respetamos variables ya exportadas.
    def load_dotenv():
        env_path = os.path.join(os.path.dirname(__file__), '.env')
        if not os.path.exists(env_path):
            return
        with open(env_path, encoding='utf-8') as fh:
            for linea in fh:
                linea = linea.strip()
                if not linea or linea.startswith('#') or '=' not in linea:
                    continue
                clave, _, valor = linea.partition('=')
                os.environ.setdefault(clave.strip(), valor.strip())
    load_dotenv()

ODOO_URL = os.getenv("BASCULA_ODOO_URL", "").rstrip('/')
ODOO_DB = os.getenv("BASCULA_ODOO_DB", "")
ODOO_USER = os.getenv("BASCULA_ODOO_USER", "")
ODOO_PASSWORD = os.getenv("BASCULA_ODOO_PASSWORD", "")

# ---- Datos base para aleatorizar (colombianos/realistas) ----
LETRAS = "ABCDEFGHJKLMNPRSTUVWXYZ"
NOMBRES_TERCEROS = [
    "Agropecuaria El Progreso", "Finca La Esperanza", "Molinos del Llano",
    "Hacienda San José", "Cooperativa Arrocera del Meta", "Inversiones El Triunfo",
    "Agrícola Buenavista", "Distribuidora El Campesino",
]
NOMBRES_CONDUCTORES = [
    "Carlos Ramírez", "José Gutiérrez", "Miguel Torres", "Luis Hernández",
    "Andrés Moreno", "Fernando Díaz", "Javier Rojas", "Óscar Peña",
]
NOMBRES_LUGARES = [
    "Finca La Esperanza", "Bodega Central", "Vereda El Porvenir",
    "Lote 180", "Hacienda San José", "Granja El Diamante",
]
VARIEDADES = ["Fedearroz 67", "Fedearroz 174", "Fedearroz 2000", "IR 1529", "Coprosem"]
TIPOS_VEHICULO = ["Turbo", "Sencillo", "Doble Troque", "Tractomula"]


def conectar():
    faltantes = [n for n, v in [
        ("BASCULA_ODOO_URL", ODOO_URL), ("BASCULA_ODOO_DB", ODOO_DB),
        ("BASCULA_ODOO_USER", ODOO_USER), ("BASCULA_ODOO_PASSWORD", ODOO_PASSWORD),
    ] if not v]
    if faltantes:
        sys.exit("ERROR: faltan variables en bridge/.env: " + ", ".join(faltantes))

    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})
    if not uid:
        sys.exit("ERROR: no se pudo autenticar (revisa usuario/contraseña/DB en .env).")
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
    return uid, models


class Odoo:
    def __init__(self, uid, models):
        self.uid, self.models = uid, models

    def call(self, model, method, *args, **kw):
        return self.models.execute_kw(ODOO_DB, self.uid, ODOO_PASSWORD,
                                      model, method, list(args), kw)

    def search(self, model, domain, limit=None):
        kw = {'limit': limit} if limit else {}
        return self.call(model, 'search', domain, **kw)

    def create(self, model, vals):
        return self.call(model, 'create', vals)

    def get_or_create(self, model, domain, vals):
        ids = self.search(model, domain, limit=1)
        return ids[0] if ids else self.create(model, vals)


def asegurar_catalogos(o, seed_extra=False):
    """Devuelve dicts con ids de catálogos, creándolos si faltan."""
    cat = {}

    # Tipos de vehículo
    tv_ids = []
    for nombre in (TIPOS_VEHICULO if seed_extra else TIPOS_VEHICULO[:2]):
        tv_ids.append(o.get_or_create('secadora.tipo.vehiculo',
                                       [('name', '=', nombre)], {'name': nombre}))
    cat['tipo_vehiculo'] = tv_ids

    # Vehículos (placa única). Aseguramos al menos 4.
    veh_ids = o.search('secadora.vehiculo', [])
    while len(veh_ids) < 4:
        placa = "".join(random.choice(LETRAS) for _ in range(3)) + str(random.randint(100, 999))
        if o.search('secadora.vehiculo', [('placa', '=', placa)], limit=1):
            continue
        veh_ids.append(o.create('secadora.vehiculo', {
            'placa': placa,
            'tipo_vehiculo_id': random.choice(tv_ids),
            'capacidad_kg': random.choice([15000, 20000, 32000, 35000]),
            'tara_promedio': random.choice([6000, 7500, 9000]),
        }))
    cat['vehiculo'] = veh_ids

    # Conductores (cédula única)
    con_ids = o.search('secadora.conductor', [])
    if not con_ids:
        for nombre in NOMBRES_CONDUCTORES[:4]:
            con_ids.append(o.create('secadora.conductor', {
                'name': nombre,
                'cedula': str(random.randint(10_000_000, 99_999_999)),
            }))
    cat['conductor'] = con_ids

    # Terceros (res.partner)
    ter_ids = []
    for nombre in NOMBRES_TERCEROS:
        ter_ids.append(o.get_or_create('res.partner',
                                       [('name', '=', nombre)],
                                       {'name': nombre, 'is_company': True}))
    cat['tercero'] = ter_ids

    # Lugares
    lug_ids = []
    for nombre in NOMBRES_LUGARES:
        lug_ids.append(o.get_or_create('secadora.lugar',
                                       [('name', '=', nombre)],
                                       {'name': nombre, 'tipo': 'finca'}))
    cat['lugar'] = lug_ids

    # Variedades
    var_ids = []
    for nombre in VARIEDADES:
        var_ids.append(o.get_or_create('secadora.variedad.arroz',
                                       [('name', '=', nombre)], {'name': nombre}))
    cat['variedad'] = var_ids

    # Tipos de operación: necesitamos al menos compra/venta/servicio.
    # No se crean con dirección fija si ya existen; se buscan por lo que haya.
    to_ids = o.search('secadora.tipo.operacion', [('active', '=', True)])
    if not to_ids:
        # Semilla mínima si la BD está vacía de tipos.
        to_ids = [
            o.create('secadora.tipo.operacion', {
                'name': 'Compra de Arroz', 'codigo': 'COMPRA',
                'direccion_fija': 'entrada', 'afecta_inventario': True,
                'tipo_inventario': 'entrada',
            }),
            o.create('secadora.tipo.operacion', {
                'name': 'Venta de Arroz', 'codigo': 'VENTA',
                'direccion_fija': 'salida', 'afecta_inventario': True,
                'tipo_inventario': 'salida',
            }),
            o.create('secadora.tipo.operacion', {
                'name': 'Servicio de Secamiento', 'codigo': 'SECAMIENTO',
                'es_servicio': True,
            }),
        ]
    cat['tipo_operacion'] = to_ids
    return cat


def leer_tipos_operacion(o, ids):
    """Devuelve [(id, direccion_fija)] para saber qué dirección poner."""
    recs = o.call('secadora.tipo.operacion', 'read', ids,
                  fields=['id', 'direccion_fija', 'es_servicio'])
    return recs


def generar(o, n, cat):
    tipos = leer_tipos_operacion(o, cat['tipo_operacion'])
    creados = []
    for i in range(n):
        tipo = random.choice(tipos)
        # Dirección: si el tipo tiene dirección fija, respetarla; si no, aleatoria.
        if tipo.get('direccion_fija'):
            direccion = tipo['direccion_fija']
        else:
            direccion = random.choice(['entrada', 'salida'])

        origen = random.choice(cat['lugar'])
        destino = random.choice([l for l in cat['lugar'] if l != origen] or cat['lugar'])

        vals = {
            'tipo_operacion_id': tipo['id'],
            'direccion': direccion,
            'vehiculo_id': random.choice(cat['vehiculo']),
            'conductor_id': random.choice(cat['conductor']),
            'tercero_id': random.choice(cat['tercero']),
            'origen_id': origen,
            'destino_id': destino,
            'variedad_id': random.choice(cat['variedad']),
            'lote_finca': f"Lote {random.randint(1, 300)}",
            'humedad': round(random.uniform(18, 28), 1),
            'grano_partido': round(random.uniform(1, 6), 1),
            'impurezas': round(random.uniform(0.5, 4), 1),
        }
        try:
            pid = o.create('secadora.pesaje', vals)
            rec = o.call('secadora.pesaje', 'read', [pid], fields=['name'])[0]
            creados.append((rec['name'], direccion))
            print(f"  [OK] {rec['name']}  dir={direccion}")
        except Exception as e:
            print(f"  [ERROR] no se pudo crear pesaje {i+1}: {e}")
    return creados


def main():
    n = 5
    seed_extra = '--seed' in sys.argv
    for a in sys.argv[1:]:
        if a.isdigit():
            n = int(a)
    n = max(1, min(n, 100))

    print(f"Conectando a {ODOO_URL} (db={ODOO_DB})...")
    o = Odoo(*conectar())
    print("Asegurando catálogos mínimos...")
    cat = asegurar_catalogos(o, seed_extra=seed_extra)
    print(f"Generando {n} pesajes aleatorios en borrador...")
    creados = generar(o, n, cat)
    print(f"\nListo: {len(creados)} pesajes creados. Ahora gestiónalos desde Odoo.")


if __name__ == "__main__":
    main()
