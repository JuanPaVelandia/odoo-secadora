#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compara lo cargado en Odoo contra los export de Fracttal.

Se corre DESPUÉS de `migrar.py --aplicar` para confirmar que no se perdió
ni se duplicó nada. No escribe: solo lee y compara.

    python3 verificar.py --db=odoo_prueba_4
"""
import sys
import os
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comun
import mapeo
from comun import Odoo, leer_export, a_float

DB = next((a.split('=', 1)[1] for a in sys.argv if a.startswith('--db=')),
          comun.DB_POR_DEFECTO)

fallos = []


def check(etiqueta, esperado, obtenido, tolerancia=0):
    ok = abs(esperado - obtenido) <= tolerancia
    marca = 'OK  ' if ok else 'FALLA'
    if isinstance(esperado, float):
        print(f'   [{marca}] {etiqueta:44} esperado {esperado:>16,.2f} | '
              f'en Odoo {obtenido:>16,.2f}')
    else:
        print(f'   [{marca}] {etiqueta:44} esperado {esperado:>16,} | '
              f'en Odoo {obtenido:>16,}')
    if not ok:
        fallos.append(etiqueta)


def main():
    o = Odoo(db=DB)
    print(f'Verificando {DB} (uid={o.uid})\n')

    # ---------------- Equipos ----------------
    print('EQUIPOS')
    activos = leer_export('ACTIVOS.xlsx')
    nombres = {mapeo.normalizar(r['Nombre']) for r in activos if r.get('Nombre')}
    en_odoo = o.buscar_leer('maintenance.equipment', [], ['name', 'external_ref'])
    en_odoo_norm = {mapeo.normalizar(e['name']) for e in en_odoo}
    faltan = nombres - en_odoo_norm
    check('Activos del export presentes en Odoo', len(nombres),
          len(nombres) - len(faltan))
    if faltan:
        for n in sorted(faltan)[:10]:
            print(f'          falta: {n}')

    # Duplicados por nombre
    cuenta = defaultdict(int)
    for e in en_odoo:
        cuenta[mapeo.normalizar(e['name'])] += 1
    dups = {k: v for k, v in cuenta.items() if v > 1}
    check('Equipos duplicados por nombre', 0, len(dups))
    for k, v in list(dups.items())[:10]:
        print(f'          duplicado x{v}: {k}')

    # ---------------- Órdenes ----------------
    print('\nÓRDENES DE TRABAJO')
    filas = leer_export('OT-RECURSOS.xlsx')
    ots = {str(f['Id OT']).strip() for f in filas if f.get('Id OT')}
    reqs = o.buscar_leer('maintenance.request',
                         [('external_ref', '!=', False)], ['external_ref'])
    refs = {r['external_ref'] for r in reqs}
    check('Órdenes migradas', len(ots), len(refs & ots))
    check('Órdenes duplicadas', len(refs), len(set(refs)))
    if ots - refs:
        for r in sorted(ots - refs)[:10]:
            print(f'          falta OT: {r}')

    # ---------------- Costos ----------------
    print('\nCOSTOS HISTÓRICOS')
    total_origen = sum(a_float(f.get('coste Total')) for f in filas)
    lineas_origen = len([f for f in filas if f.get('Id OT')])
    # Paginado: leer miles de registros de una vez trunca la respuesta XML-RPC.
    dominio = [('origin', '=', 'historic')]
    n_costos = o.contar('maintenance.equipment.cost.line', dominio)
    suma = 0.0
    for desplazamiento in range(0, n_costos, 1000):
        suma += sum(c['amount'] for c in o.buscar_leer(
            'maintenance.equipment.cost.line', dominio, ['amount'],
            offset=desplazamiento, limit=1000, order='id'))
    check('Líneas de costo', lineas_origen, n_costos)
    check('Importe total', round(total_origen, 2), round(suma, 2),
          tolerancia=1.0)

    # El total por equipo es un campo calculado con store: si se cargó por SQL
    # sin recompute, quedaría en cero aunque las líneas estén bien.
    equipos_con_costo = {c['equipment_id'][0]
                         for c in o.buscar_leer(
                             'maintenance.equipment.cost.line',
                             [('equipment_id', '!=', False)], ['equipment_id'],
                             limit=2000) if c['equipment_id']}
    check('Equipos con total calculado', len(equipos_con_costo),
          o.contar('maintenance.equipment',
                   [('id', 'in', list(equipos_con_costo)),
                    ('maintenance_cost_total', '>', 0)]))

    # ---------------- Horómetros ----------------
    print('\nHORÓMETROS')
    carpeta = os.path.join(comun.RUTA_EXPORT, 'Horómetros')
    esperadas = 0
    for archivo in sorted(f for f in os.listdir(carpeta) if f.endswith('.xlsx')):
        for f in comun.leer_excel(os.path.join(carpeta, archivo)):
            fecha = comun.a_fecha(f.get('Fecha de Lectura') or f.get('Fecha de Ingreso'))
            if fecha and comun.lectura_horometro(f.get('Lectura')) > 0:
                esperadas += 1
    check('Lecturas de horómetro', esperadas,
          o.contar('maintenance.horometro.reading', []))
    check('OT preventivas autogeneradas (deben ser 0)', 0,
          o.contar('maintenance.request',
                   [('external_ref', '=', False),
                    ('name', 'like', 'Mant. preventivo')]))

    # ---------------- Ubicaciones ----------------
    print('\nUBICACIONES Y COMPAÑÍAS')
    check('Equipos sin ubicación ni padre', 0,
          o.contar('maintenance.equipment',
                   [('lugar_id', '=', False),
                    ('parent_equipment_id', '=', False),
                    ('external_ref', '!=', False)]))
    check('Equipos sin compañía', 0,
          o.contar('maintenance.equipment',
                   [('company_id', '=', False), ('external_ref', '!=', False)]))
    print('\n   Reparto por compañía:')
    for c in o.buscar_leer('res.company', [], ['name']):
        n = o.contar('maintenance.equipment',
                     [('company_id', '=', c['id']), ('external_ref', '!=', False)])
        if n:
            print(f'      {c["name"]:38} {n:>5} equipos')
    print('\n   Registros de historial de ubicación:',
          o.contar('maintenance.equipment.location.history', []))

    # ---------------- Resultado ----------------
    print('\n' + '=' * 72)
    if fallos:
        print(f'RESULTADO: {len(fallos)} verificación(es) FALLARON')
        for f in fallos:
            print(f'   - {f}')
        sys.exit(1)
    print('RESULTADO: todas las verificaciones pasaron.')


if __name__ == '__main__':
    main()
