#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Copia el punto de partida de los planes de una base a otra.

Los últimos cambios de aceite e hidráulico se revisaron y corrigieron a mano
en la base de pruebas. En vez de repetir ese trabajo en producción, se copian
tal cual: la clave es el nombre del equipo y el del plan.

    python3 exportar_planes.py --de=odoo_prueba_4 --a=secadora_2
    python3 exportar_planes.py --de=odoo_prueba_4 --a=secadora_2 --aplicar
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mapeo
from comun import Odoo

APLICAR = '--aplicar' in sys.argv
ORIGEN = next((a.split('=', 1)[1] for a in sys.argv if a.startswith('--de=')),
              'odoo_prueba_4')
DESTINO = next((a.split('=', 1)[1] for a in sys.argv if a.startswith('--a=')),
               'secadora_2')


def leer_lineas(o):
    """{(equipo, plan): (último, actual)}"""
    datos = {}
    for l in o.buscar_leer('maintenance.task.plan.line', [],
                           ['equipment_id', 'plan_id',
                            'last_counter_reading', 'current_counter_reading']):
        if not (l['equipment_id'] and l['plan_id']):
            continue
        clave = (mapeo.normalizar(l['equipment_id'][1]),
                 mapeo.normalizar(l['plan_id'][1]))
        datos[clave] = (l['last_counter_reading'], l['current_counter_reading'])
    return datos


def main():
    origen = Odoo(db=ORIGEN)
    destino = Odoo(db=DESTINO)
    print(f'{ORIGEN} → {DESTINO} | '
          f'{"APLICAR" if APLICAR else "SIMULACRO"}\n')

    de = leer_lineas(origen)
    print(f'Líneas en {ORIGEN}: {len(de)}')

    lineas_destino = destino.buscar_leer(
        'maintenance.task.plan.line', [],
        ['equipment_id', 'plan_id', 'last_counter_reading'])
    print(f'Líneas en {DESTINO}: {len(lineas_destino)}')

    copiadas, sin_par = 0, []
    for l in lineas_destino:
        if not (l['equipment_id'] and l['plan_id']):
            continue
        clave = (mapeo.normalizar(l['equipment_id'][1]),
                 mapeo.normalizar(l['plan_id'][1]))
        if clave not in de:
            sin_par.append(f'{l["equipment_id"][1]} / {l["plan_id"][1]}')
            continue
        ultimo, actual = de[clave]
        if abs(l['last_counter_reading'] - ultimo) < 0.01:
            continue
        if APLICAR:
            destino.escribir('maintenance.task.plan.line', [l['id']], {
                'last_counter_reading': ultimo,
                'current_counter_reading': actual,
            })
        copiadas += 1

    print(f'\nLíneas actualizadas: {copiadas}')
    if sin_par:
        print(f'Sin equivalencia en el origen: {len(sin_par)}')
        for s in sin_par[:6]:
            print(f'   - {s}')
    if not APLICAR:
        print('\n*** SIMULACRO: no se escribió nada. ***')


if __name__ == '__main__':
    main()
