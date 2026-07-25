#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Crea el historial de ubicación que falte para equipos ya migrados.

`migrar.py` registra el historial al crear cada equipo. Si una carga se
interrumpió a medias (o los equipos se crearon antes de que existiera el
modelo), este script rellena lo que falte sin duplicar lo que ya está.

    python3 reparar_historial.py --db=odoo_prueba_4              # simulacro
    python3 reparar_historial.py --db=odoo_prueba_4 --aplicar
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comun
import mapeo
from comun import Odoo, leer_export, a_fecha, ultimo_nodo

APLICAR = '--aplicar' in sys.argv
DB = next((a.split('=', 1)[1] for a in sys.argv if a.startswith('--db=')),
          comun.DB_POR_DEFECTO)


def main():
    o = Odoo(db=DB)
    print(f'Base: {DB} | Modo: {"APLICAR" if APLICAR else "SIMULACRO"}\n')

    equipos = {}
    for e in o.buscar_leer('maintenance.equipment',
                           [('external_ref', '!=', False)],
                           ['name', 'lugar_id', 'origen_muestra_id',
                            'parent_equipment_id']):
        equipos[mapeo.normalizar(e['name'])] = e

    con_historial = {h['equipment_id'][0]
                     for h in o.buscar_leer(
                         'maintenance.equipment.location.history', [],
                         ['equipment_id']) if h['equipment_id']}
    print(f'Equipos migrados: {len(equipos)} | '
          f'ya con historial: {len(con_historial)}')

    filas = leer_export('ACTIVOS.xlsx')
    pendientes = []
    for f in filas:
        nombre = (f.get('Nombre') or '').strip()
        eq = equipos.get(mapeo.normalizar(nombre))
        if not eq or eq['id'] in con_historial:
            continue
        if not (eq['lugar_id'] or eq['origen_muestra_id']
                or eq['parent_equipment_id']):
            continue
        pendientes.append({
            'equipment_id': eq['id'],
            'lugar_id': eq['lugar_id'][0] if eq['lugar_id'] else False,
            'origen_muestra_id': (eq['origen_muestra_id'][0]
                                  if eq['origen_muestra_id'] else False),
            'parent_equipment_id': (eq['parent_equipment_id'][0]
                                    if eq['parent_equipment_id'] else False),
            'date_from': a_fecha(f.get('Fecha de Compra')) or '2024-01-01',
            'origin': 'Fracttal',
            'notes': f'Ubicación inicial importada de Fracttal: '
                     f'{(f.get("Ubicado en ó es Parte de") or "").strip()}',
        })

    print(f'Historial a crear: {len(pendientes)}')
    if APLICAR and pendientes:
        for j in range(0, len(pendientes), 200):
            o.crear_lote('maintenance.equipment.location.history',
                         pendientes[j:j + 200])
            comun.barra(min(j + 200, len(pendientes)), len(pendientes),
                        'historial')
        print(f'Creados: {len(pendientes)}')
    elif not APLICAR:
        print('\n*** SIMULACRO: no se escribió nada. ***')

    total = o.contar('maintenance.equipment.location.history', [])
    print(f'Total de registros de historial en {DB}: {total}')


if __name__ == '__main__':
    main()
