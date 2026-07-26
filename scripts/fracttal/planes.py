#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Crea los planes de mantenimiento por horómetro y su punto de partida.

Los tractores cambian aceite e hidráulico cada N horas. Odoo lleva un plan
por intervalo (`maintenance.task.plan.interval` es único), así que los dos
planes del negocio se materializan en cuatro:

    Aceite      200 h  → todos los tractores menos el JD 6603
    Hidráulico 1200 h  → todos los tractores menos el JD 6603
    Aceite      250 h  → JD 6603
    Hidráulico 1200 h  → JD 6603

Para que el "próximo cambio" salga bien hay que sembrar a qué horas se hizo
el último. Eso NO se pide a mano: se deduce cruzando la fecha de la última OT
de cada tipo (en OT-RECURSOS.xlsx) con la lectura de horómetro más cercana
anterior a esa fecha.

    python3 planes.py --db=odoo_prueba_4              # simulacro
    python3 planes.py --db=odoo_prueba_4 --aplicar
"""
import glob
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comun
import mapeo
from comun import Odoo, leer_export, a_fecha, lectura_horometro

APLICAR = '--aplicar' in sys.argv
DB = next((a.split('=', 1)[1] for a in sys.argv if a.startswith('--db=')),
          comun.DB_POR_DEFECTO)

# Tractor con intervalo de aceite propio.
JD_6603 = 'TRACT JOHN DEERE 6603 JV 1'

PLANES = [
    {'clave': 'aceite_general', 'tarea': 'ACEITE', 'intervalo': 200.0,
     'name': 'Cambio de aceite de motor (200 h)',
     'descripcion': 'Cambio de aceite de motor y filtros cada 200 horas.',
     'excluye': {JD_6603}},
    {'clave': 'hidraulico_general', 'tarea': 'HIDRAULICO', 'intervalo': 1200.0,
     'name': 'Cambio de hidráulico (1200 h)',
     'descripcion': 'Cambio de aceite hidráulico y filtros cada 1200 horas.',
     'excluye': {JD_6603}},
    {'clave': 'aceite_jd', 'tarea': 'ACEITE', 'intervalo': 250.0,
     'name': 'Cambio de aceite de motor - JD 6603 (250 h)',
     'descripcion': 'Cambio de aceite de motor y filtros cada 250 horas.',
     'solo': {JD_6603}},
    {'clave': 'hidraulico_jd', 'tarea': 'HIDRAULICO', 'intervalo': 1200.0,
     'name': 'Cambio de hidráulico - JD 6603 (1200 h)',
     'descripcion': 'Cambio de aceite hidráulico y filtros cada 1200 horas.',
     'solo': {JD_6603}},
]


def titulo(txt):
    print(f'\n{"=" * 72}\n{txt}\n{"=" * 72}')


def tipo_de_tarea(texto):
    """Clasifica la tarea de una OT como cambio de aceite o de hidráulico."""
    t = (texto or '').upper()
    if 'HIDRAULIC' in t or 'HIDRÁULIC' in t:
        return 'HIDRAULICO'
    if 'ACEITE' in t or 'LUBRICANT' in t:
        return 'ACEITE'
    return None


def leer_horometros():
    """{equipo normalizado: [(fecha, lectura), …]} ordenado por fecha."""
    carpeta = os.path.join(comun.RUTA_EXPORT, 'Horómetros')
    lecturas = {}
    for archivo in glob.glob(os.path.join(carpeta, '*.xlsx')):
        nombre = os.path.splitext(os.path.basename(archivo))[0].strip()
        nombre = mapeo.ALIAS_ACTIVO.get(nombre, nombre)
        filas = []
        for fila in comun.leer_excel(archivo):
            fecha = a_fecha(fila.get('Fecha de Lectura')
                            or fila.get('Fecha de Ingreso'))
            valor = lectura_horometro(fila.get('Lectura'))
            if fecha and valor > 0:
                filas.append((fecha, valor))
        if filas:
            lecturas[mapeo.normalizar(nombre)] = sorted(filas)
    return lecturas


def ultimos_cambios():
    """{(equipo, tipo): fecha} del último cambio registrado en las OT."""
    ultimo = defaultdict(dict)
    for fila in leer_export('OT-RECURSOS.xlsx'):
        activo = (fila.get('Activo') or '').strip()
        if not activo:
            continue
        activo = mapeo.ALIAS_ACTIVO.get(activo, activo)
        tipo = tipo_de_tarea(fila.get('Tarea'))
        fecha = a_fecha(fila.get('Fecha de creación de la OT'))
        if not tipo or not fecha:
            continue
        if fecha > ultimo[activo].get(tipo, ''):
            ultimo[activo][tipo] = fecha
    return ultimo


def horas_en(lecturas, fecha):
    """Lectura del horómetro vigente en esa fecha (la última anterior o igual)."""
    previas = [valor for f, valor in lecturas if f <= fecha]
    if previas:
        return previas[-1]
    return lecturas[0][1] if lecturas else 0.0


def _punto_de_partida(plan, nombre_equipo, lecturas, cambios):
    """(último cambio, lectura actual, ¿se dedujo del histórico?).

    Sin registro previo se arranca desde la lectura actual: es preferible a
    dar el cambio por vencido desde la primera hora de la máquina.
    """
    actual = lecturas[-1][1] if lecturas else 0.0
    fecha = cambios.get(nombre_equipo, {}).get(plan['tarea'])
    if fecha:
        return horas_en(lecturas, fecha), actual, True
    return actual, actual, False


def main():
    o = Odoo(db=DB)
    print(f'Base: {DB} | Modo: {"APLICAR" if APLICAR else "SIMULACRO"}')
    print(f'Conectado (uid={o.uid})')

    # ---------- Datos de origen ----------
    horometros = leer_horometros()
    cambios = ultimos_cambios()

    # ---------- Equipos con horómetro en Odoo ----------
    equipos = {}
    for eq in o.buscar_leer('maintenance.equipment', [], ['name', 'company_id']):
        equipos[mapeo.normalizar(eq['name'])] = eq
    con_horometro = [n for n in horometros if n in equipos]
    print(f'\nTractores con horómetro: {len(con_horometro)}')

    # ---------- Tipo de contador ----------
    contador = o.buscar('maintenance.counter.type',
                        [('unit', '=ilike', 'h%')], limit=1)
    if not contador:
        contador = o.buscar('maintenance.counter.type', [], limit=1)
    if not contador:
        raise SystemExit('No hay ningún tipo de contador configurado.')
    id_contador = contador[0]
    print('Tipo de contador:',
          o.buscar_leer('maintenance.counter.type', [('id', '=', id_contador)],
                        ['name', 'unit'])[0])

    titulo('PLANES')
    resumen = []
    for plan in PLANES:
        # Equipos que le corresponden
        objetivo = []
        for norm in con_horometro:
            nombre = equipos[norm]['name']
            if plan.get('solo') and nombre not in plan['solo']:
                continue
            if plan.get('excluye') and nombre in plan['excluye']:
                continue
            objetivo.append(norm)

        existente = o.buscar('maintenance.task.plan',
                             [('name', '=', plan['name'])], limit=1)
        print(f'\n{plan["name"]}  →  {len(objetivo)} equipos'
              f'{"  (ya existe, se actualiza)" if existente else ""}')

        if not APLICAR:
            sin_registro = 0
            for norm in sorted(objetivo):
                horas, actual, deducido = _punto_de_partida(
                    plan, equipos[norm]['name'], horometros[norm], cambios)
                if not deducido:
                    sin_registro += 1
                if sorted(objetivo).index(norm) < 3:
                    print(f'      {equipos[norm]["name"][:32]:32} último '
                          f'{horas:>8,.0f} h  → próximo '
                          f'{horas + plan["intervalo"]:>8,.0f} h'
                          f'  (actual {actual:,.0f} h)'
                          f'{"" if deducido else "  [sin registro previo]"}')
            if len(objetivo) > 3:
                print(f'      … y {len(objetivo) - 3} más')
            if sin_registro:
                print(f'      AVISO: {sin_registro} sin cambio previo en el '
                      f'histórico → arrancan desde su lectura actual')
            resumen.append((plan['name'], len(objetivo)))
            continue

        # ---------- Crear / actualizar el plan ----------
        vals = {
            'name': plan['name'],
            'description': plan['descripcion'],
            'counter_type_id': id_contador,
            'interval': plan['intervalo'],
            'equipment_ids': [(6, 0, [equipos[n]['id'] for n in objetivo])],
        }
        if existente:
            id_plan = existente[0]
            o.escribir('maintenance.task.plan', [id_plan], vals)
        else:
            id_plan = o.crear('maintenance.task.plan', vals)

        # ---------- Sembrar el último cambio en cada línea ----------
        lineas = {
            l['equipment_id'][0]: l['id']
            for l in o.buscar_leer('maintenance.task.plan.line',
                                   [('plan_id', '=', id_plan)],
                                   ['equipment_id'])
            if l['equipment_id']
        }
        sembradas = 0
        for norm in objetivo:
            id_linea = lineas.get(equipos[norm]['id'])
            if not id_linea:
                continue
            ultimo, actual, _deducido = _punto_de_partida(
                plan, equipos[norm]['name'], horometros[norm], cambios)
            o.escribir('maintenance.task.plan.line', [id_linea], {
                'last_counter_reading': ultimo,
                'current_counter_reading': actual,
            })
            sembradas += 1
        print(f'      líneas sembradas: {sembradas}')
        resumen.append((plan['name'], len(objetivo)))

    titulo('RESUMEN')
    for nombre, n in resumen:
        print(f'   {nombre:48} {n:>3} equipos')
    if APLICAR:
        print(f'\n   Planes en la base: '
              f'{o.contar("maintenance.task.plan", [])}')
        print(f'   Líneas de seguimiento: '
              f'{o.contar("maintenance.task.plan.line", [])}')
        for estado, etiqueta in [('overdue', 'Vencidas'), ('warning', 'Próximas'),
                                 ('ok', 'Al día')]:
            print(f'   {etiqueta:22} '
                  f'{o.contar("maintenance.task.plan.line", [("state", "=", estado)])}')
    else:
        print('\n   *** SIMULACRO: no se escribió nada. ***')


if __name__ == '__main__':
    main()
