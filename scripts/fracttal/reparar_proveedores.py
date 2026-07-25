#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Enlaza los costos históricos ya cargados con su proveedor.

La primera carga solo creó como partner los talleres del catálogo de
ubicaciones, y los nombres de las OT no siempre coinciden ("TALLER HELI" vs
"TALLER DON HELI"). Este script crea los proveedores que falten y rellena
`partner_id` en los costos que lo tengan vacío.

    python3 reparar_proveedores.py --db=odoo_prueba_4              # simulacro
    python3 reparar_proveedores.py --db=odoo_prueba_4 --aplicar
"""
import sys
import os
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comun
import mapeo
from comun import Odoo, barra

APLICAR = '--aplicar' in sys.argv
DB = next((a.split('=', 1)[1] for a in sys.argv if a.startswith('--db=')),
          comun.DB_POR_DEFECTO)


def main():
    o = Odoo(db=DB)
    print(f'Base: {DB} | Modo: {"APLICAR" if APLICAR else "SIMULACRO"}\n')

    # Se lee paginado: de una sola vez, XML-RPC llega a truncar la respuesta.
    dominio = [('partner_id', '=', False), ('source_name', '!=', False)]
    total = o.contar('maintenance.historic.cost', dominio)
    costos = []
    for desplazamiento in range(0, total, 1000):
        costos += o.buscar_leer('maintenance.historic.cost', dominio,
                                ['source_name'], offset=desplazamiento,
                                limit=1000, order='id')
    print(f'Costos sin proveedor: {len(costos)}')

    # Fuente → costos. Solo se crea contacto para las fuentes que se repiten:
    # el campo es texto libre y las de una sola aparición suelen ser la
    # descripción del trabajo, no un tercero.
    por_fuente = defaultdict(list)
    for c in costos:
        nombre = mapeo.proveedor_de_fuente(c['source_name'])
        if nombre:
            por_fuente[nombre].append(c['id'])

    descartadas = {n: ids for n, ids in por_fuente.items()
                   if len(ids) < mapeo.MIN_APARICIONES_PROVEEDOR
                   and n not in mapeo.TALLERES}
    for n in descartadas:
        del por_fuente[n]

    almacen = len(costos) - sum(len(v) for v in por_fuente.values()) \
        - sum(len(v) for v in descartadas.values())
    print(f'Proveedores a enlazar: {len(por_fuente)}')
    print(f'Costos de almacén propio (sin proveedor, correcto): {almacen}')
    print(f'Fuentes de una sola aparición que NO se crean como contacto: '
          f'{len(descartadas)} (el texto queda en el costo)\n')

    creados = enlazados = 0
    for nombre, ids in sorted(por_fuente.items(), key=lambda x: -len(x[1])):
        existente = o.buscar('res.partner', [('name', '=ilike', nombre)], limit=1)
        if existente:
            id_partner = existente[0]
        elif APLICAR:
            id_partner = o.crear('res.partner', {
                'name': nombre,
                'company_type': 'company',
                'supplier_rank': 1,
                'comment': 'Proveedor de mantenimiento importado de Fracttal.',
            })
            creados += 1
        else:
            id_partner = None
            creados += 1
        print(f'   {nombre[:46]:46} {len(ids):>5} costos'
              f'{"" if existente else "  (nuevo)"}')
        if APLICAR and id_partner:
            for j in range(0, len(ids), 200):
                o.escribir('maintenance.historic.cost', ids[j:j + 200],
                           {'partner_id': id_partner})
            enlazados += len(ids)

    print(f'\nProveedores creados: {creados}')
    if APLICAR:
        print(f'Costos enlazados   : {enlazados}')
        print(f'Costos con proveedor ahora: '
              f'{o.contar("maintenance.historic.cost", [("partner_id", "!=", False)])}')
    else:
        print('\n*** SIMULACRO: no se escribió nada. ***')


if __name__ == '__main__':
    main()
