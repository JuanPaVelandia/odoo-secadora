# -*- coding: utf-8 -*-
"""Conexión XML-RPC y lectura de los export de Fracttal."""
import os
import re
import sys
import xmlrpc.client
from datetime import datetime, timedelta

import openpyxl

RUTA_EXPORT = '/mnt/c/Users/Usuario/Desktop/DOCUMENTO5/Odoo/Migración Fracttal - Odooo'
RUTA_ENV = '/mnt/c/Users/Usuario/Desktop/DOCUMENTO5/Odoo/Odoo_SGC/odoo-secadora-main/bridge/.env'
URL_V19 = 'http://187.77.15.196:8069'
DB_POR_DEFECTO = 'secadora_2'

CTX = {'active_test': False}


def _credenciales():
    env = {}
    with open(RUTA_ENV) as f:
        for linea in f:
            linea = linea.strip()
            if '=' in linea and not linea.startswith('#'):
                k, v = linea.split('=', 1)
                env[k] = v
    return env.get('BASCULA_ODOO_USER', 'admin'), env['BASCULA_ODOO_PASSWORD']


class Odoo:
    """Cliente XML-RPC mínimo, con caché de búsquedas por clave natural."""

    def __init__(self, url=URL_V19, db=DB_POR_DEFECTO):
        usuario, clave = _credenciales()
        self.db, self.clave = db, clave
        self.uid = xmlrpc.client.ServerProxy(
            f'{url}/xmlrpc/2/common').authenticate(db, usuario, clave, {})
        if not self.uid:
            raise SystemExit(f'No se pudo autenticar en {db}')
        self.m = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object', allow_none=True)
        self._cache = {}

    def x(self, modelo, metodo, *args, **kw):
        return self.m.execute_kw(self.db, self.uid, self.clave, modelo, metodo,
                                 list(args), kw)

    def buscar_leer(self, modelo, dominio, campos, **kw):
        return self.x(modelo, 'search_read', dominio, fields=campos, context=CTX, **kw)

    def buscar(self, modelo, dominio, **kw):
        return self.x(modelo, 'search', dominio, context=CTX, **kw)

    def contar(self, modelo, dominio):
        return self.x(modelo, 'search_count', dominio, context=CTX)

    def crear(self, modelo, vals):
        return self.x(modelo, 'create', vals, context=CTX)

    def crear_lote(self, modelo, lista_vals):
        """create() con lista → Odoo devuelve los ids en el mismo orden."""
        if not lista_vals:
            return []
        return self.x(modelo, 'create', lista_vals, context=CTX)

    def escribir(self, modelo, ids, vals):
        return self.x(modelo, 'write', ids, vals, context=CTX)

    def id_por_nombre(self, modelo, nombre, campo='name'):
        """Busca un id por clave natural, cacheado. None si no existe."""
        clave = (modelo, campo, nombre)
        if clave not in self._cache:
            res = self.buscar(modelo, [(campo, '=', nombre)], limit=1)
            self._cache[clave] = res[0] if res else None
        return self._cache[clave]

    def olvidar_cache(self):
        self._cache.clear()


# --------------------------------------------------------------------------
# Lectura de los Excel
# --------------------------------------------------------------------------
def leer_excel(ruta):
    """Devuelve una lista de dicts con la primera hoja del archivo."""
    wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    it = ws.iter_rows(values_only=True)
    cabecera = [str(c).strip() if c is not None else '' for c in next(it)]
    filas = [dict(zip(cabecera, fila)) for fila in it]
    wb.close()
    return filas


def leer_export(nombre):
    return leer_excel(os.path.join(RUTA_EXPORT, nombre))


# --------------------------------------------------------------------------
# Utilidades de conversión
# --------------------------------------------------------------------------
def a_fecha(valor):
    """'2026-01-19 10:13' | datetime | date → 'YYYY-MM-DD'. None si vacío."""
    if not valor:
        return None
    if isinstance(valor, datetime):
        return valor.strftime('%Y-%m-%d')
    if hasattr(valor, 'strftime'):
        return valor.strftime('%Y-%m-%d')
    txt = str(valor).strip()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d',
                '%d/%m/%Y %H:%M', '%d/%m/%Y'):
        try:
            return datetime.strptime(txt, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None


def a_datetime(valor):
    """Igual que a_fecha pero conservando la hora, para campos datetime."""
    if not valor:
        return None
    if isinstance(valor, datetime):
        return valor.strftime('%Y-%m-%d %H:%M:%S')
    txt = str(valor).strip()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(txt, fmt).strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            continue
    return None


def a_float(valor):
    if valor in (None, '', '-'):
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    txt = str(valor).strip().replace(',', '')
    try:
        return float(txt)
    except ValueError:
        return 0.0


def a_horas(valor):
    """'1 day, 0:00:00' o timedelta → horas. Usado en horas de uso diario."""
    if valor in (None, ''):
        return 0.0
    if isinstance(valor, timedelta):
        return valor.total_seconds() / 3600.0
    txt = str(valor).strip()
    dias = 0
    m = re.match(r'(\d+)\s*day[s]?,\s*(.*)', txt)
    if m:
        dias, txt = int(m.group(1)), m.group(2)
    partes = txt.split(':')
    try:
        h = int(partes[0]); mi = int(partes[1]); s = int(float(partes[2])) if len(partes) > 2 else 0
    except (ValueError, IndexError):
        return 0.0
    return dias * 24 + h + mi / 60.0 + s / 3600.0


def lectura_horometro(valor):
    """'6832 HR; Valor Base: 0 HR...' o '17668 HR' → 6832.0"""
    if valor in (None, ''):
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    m = re.search(r'(-?[\d.,]+)', str(valor).replace(',', ''))
    return float(m.group(1)) if m else 0.0


def ultimo_nodo(ruta):
    """'// FINCAS/ FINCA CAMELIAS/ ' → 'FINCA CAMELIAS'"""
    if not ruta:
        return ''
    partes = [p.strip() for p in str(ruta).split('/') if p.strip()]
    return partes[-1] if partes else ''


def barra(actual, total, etiqueta=''):
    if total and (actual % 200 == 0 or actual == total):
        pct = 100 * actual / total
        sys.stdout.write(f'\r   {etiqueta} {actual}/{total} ({pct:.0f}%)')
        sys.stdout.flush()
        if actual == total:
            sys.stdout.write('\n')
