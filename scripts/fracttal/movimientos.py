#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Carga el historial de movimientos de maquinaria entre ubicaciones.

Cada archivo de `Ubicaciones/` es una máquina, con sus movimientos
(fecha, origen, destino). Se reconstruye la línea de tiempo completa:

    tramo 1: dónde estaba antes del primer movimiento  → hasta esa fecha
    tramo N: destino del movimiento N                  → hasta el siguiente
    tramo actual: destino del último movimiento        → sin fecha de fin

Sustituye al tramo único que creó la importación inicial (la foto de dónde
estaba el equipo al exportar), que no tenía historia.

    python3 movimientos.py --db=odoo_prueba_4              # simulacro
    python3 movimientos.py --db=odoo_prueba_4 --aplicar
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comun
import mapeo
from comun import Odoo, a_fecha, ultimo_nodo, barra

APLICAR = '--aplicar' in sys.argv
DB = next((a.split('=', 1)[1] for a in sys.argv if a.startswith('--db=')),
          comun.DB_POR_DEFECTO)

CARPETA = os.path.join(comun.RUTA_EXPORT, 'Ubicaciones')

# Arranque del histórico: el primer movimiento registrado en Fracttal es de
# abril de 2024, así que se toma el inicio de ese año como origen aproximado
# del primer tramo (es la misma fecha que usó la importación de activos).
FECHA_INICIO = '2024-01-01'


def resolver_lugar(ruta, lugares, areas):
    """Ruta jerárquica de Fracttal → (id de lugar, id de área de proceso)."""
    nodo = ultimo_nodo(ruta)
    if not nodo:
        return None, None
    norm = mapeo.normalizar(nodo)
    # Área interna de planta: el lugar es la secadora.
    for area_fracttal, area_odoo in mapeo.AREA_PLANTA.items():
        if mapeo.normalizar(area_fracttal) == norm:
            lugar = mapeo.LUGAR_EXISTENTE.get(mapeo.LUGAR_DE_PLANTA,
                                              mapeo.LUGAR_DE_PLANTA)
            return (lugares.get(mapeo.normalizar(lugar)),
                    areas.get(mapeo.normalizar(area_odoo)))
    destino = mapeo.LUGAR_EXISTENTE.get(nodo, nodo)
    return lugares.get(mapeo.normalizar(destino)), None


def main():
    o = Odoo(db=DB)
    print(f'Base: {DB} | Modo: {"APLICAR" if APLICAR else "SIMULACRO"}')

    lugares = {mapeo.normalizar(l['name']): l['id']
               for l in o.buscar_leer('secadora.lugar', [], ['name'])}
    areas = {mapeo.normalizar(a['name']): a['id']
             for a in o.buscar_leer('secadora.origen.muestra', [], ['name'])}
    equipos = {mapeo.normalizar(e['name']): e['id']
               for e in o.buscar_leer('maintenance.equipment', [], ['name'])}

    archivos = sorted(glob.glob(os.path.join(CARPETA, '*.xlsx')))
    print(f'Máquinas con movimientos: {len(archivos)}')

    sin_equipo, sin_lugar = [], set()
    tramos_por_equipo = {}
    total_movimientos = 0

    for archivo in archivos:
        nombre = os.path.splitext(os.path.basename(archivo))[0].strip()
        nombre = mapeo.ALIAS_ACTIVO.get(nombre, nombre)
        id_equipo = equipos.get(mapeo.normalizar(nombre))
        if not id_equipo:
            sin_equipo.append(nombre)
            continue

        # Del más antiguo al más reciente.
        movimientos = []
        for fila in comun.leer_excel(archivo):
            fecha = a_fecha(fila.get('Fecha de Movimiento'))
            if not fecha:
                continue
            movimientos.append((fecha, fila.get('Fuente'), fila.get('Destino'),
                                fila.get('Personal')))
        movimientos.sort()
        if not movimientos:
            continue
        total_movimientos += len(movimientos)

        tramos = []
        # Tramo inicial: dónde estaba antes del primer movimiento. No se sabe
        # desde cuándo, así que se abre en la fecha del propio export inicial
        # de activos y se cierra al producirse ese primer movimiento.
        primera_fecha, primer_origen, _d, _p = movimientos[0]
        id_lugar, id_area = resolver_lugar(primer_origen, lugares, areas)
        if id_lugar or id_area:
            tramos.append({
                'lugar_id': id_lugar or False,
                'origen_muestra_id': id_area or False,
                'date_from': min(FECHA_INICIO, primera_fecha),
                'date_to': primera_fecha,
                'notes': f'Ubicación anterior al primer movimiento registrado '
                         f'en Fracttal: {(primer_origen or "").strip()}. '
                         f'La fecha de inicio es aproximada.',
            })
        elif primer_origen:
            sin_lugar.add(ultimo_nodo(primer_origen))

        # Un tramo por destino, hasta el siguiente movimiento.
        for i, (fecha, _o, destino, personal) in enumerate(movimientos):
            id_lugar, id_area = resolver_lugar(destino, lugares, areas)
            if not (id_lugar or id_area):
                sin_lugar.add(ultimo_nodo(destino))
                continue
            hasta = movimientos[i + 1][0] if i + 1 < len(movimientos) else False
            tramos.append({
                'lugar_id': id_lugar or False,
                'origen_muestra_id': id_area or False,
                'date_from': fecha,
                'date_to': hasta,
                'notes': f'Movimiento registrado en Fracttal'
                         f'{f" por {personal}" if personal else ""}.',
            })

        if tramos:
            tramos_por_equipo[id_equipo] = tramos

    print(f'Movimientos leídos: {total_movimientos}')
    print(f'Tramos de historial a crear: '
          f'{sum(len(v) for v in tramos_por_equipo.values())}')
    if sin_equipo:
        print(f'AVISO: {len(sin_equipo)} máquinas sin equipo en Odoo: '
              f'{", ".join(sin_equipo[:5])}')
    if sin_lugar:
        print(f'AVISO: ubicaciones no resueltas: {", ".join(sorted(sin_lugar))}')

    if not APLICAR:
        print('\n*** SIMULACRO: no se escribió nada. ***')
        _muestra(tramos_por_equipo, o)
        return

    # El historial importado de estas máquinas se reemplaza: el tramo único
    # de la carga inicial queda sustituido por la línea de tiempo real.
    Historial = 'maintenance.equipment.location.history'
    viejos = o.buscar(Historial, [
        ('equipment_id', 'in', list(tramos_por_equipo)),
        ('origin', '=', 'Fracttal'),
    ])
    if viejos:
        o.x(Historial, 'unlink', viejos)
        print(f'Tramos iniciales reemplazados: {len(viejos)}')

    lote, creados = [], 0
    for id_equipo, tramos in tramos_por_equipo.items():
        for tramo in tramos:
            lote.append(dict(tramo, equipment_id=id_equipo, origin='Fracttal'))
    for j in range(0, len(lote), 200):
        o.crear_lote(Historial, lote[j:j + 200])
        creados += len(lote[j:j + 200])
        barra(creados, len(lote), 'tramos')
    print(f'Tramos creados: {creados}')

    # La ubicación actual del equipo debe ser la del último tramo abierto.
    actualizados = 0
    for id_equipo, tramos in tramos_por_equipo.items():
        ultimo = tramos[-1]
        vals = {}
        if ultimo['lugar_id']:
            vals['lugar_id'] = ultimo['lugar_id']
        if ultimo['origen_muestra_id']:
            vals['origen_muestra_id'] = ultimo['origen_muestra_id']
        if vals:
            # Sin disparar el registro automático: el historial ya se creó
            # arriba con las fechas reales.
            o.escribir('maintenance.equipment', [id_equipo], vals,
                       {'importando_historico': True})
            actualizados += 1
    print(f'Equipos con su ubicación actual corregida: {actualizados}')
    print(f'\nTotal de tramos en la base: {o.contar(Historial, [])}')


def _muestra(tramos_por_equipo, o):
    """Enseña la línea de tiempo de un par de máquinas."""
    print('\nEjemplo de línea de tiempo reconstruida:')
    for id_equipo, tramos in list(tramos_por_equipo.items())[:2]:
        nombre = o.buscar_leer('maintenance.equipment',
                               [('id', '=', id_equipo)], ['name'])[0]['name']
        print(f'\n   {nombre}')
        for t in tramos:
            lugar = t['lugar_id']
            print(f"      {t['date_from']} → {t['date_to'] or 'actual':10} "
                  f"lugar_id={lugar}")


if __name__ == '__main__':
    main()
