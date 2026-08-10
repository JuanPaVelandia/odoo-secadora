#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mapa de las cuentas corrientes a renumerar de 1120xx a 1110xx.

SOLO LECTURA: no escribe nada. Sirve para decidir el plan antes de tocar el PUC.

Cada cuenta bancaria es un bloque de 4 cuentas correlativas (principal,
transitoria, pagos entrantes, pagos salientes), asi que la renumeracion tiene
que mover el bloque entero, no la cuenta suelta.

Uso:
    python3 mapa_corrientes.py [--db=secadora_2]
"""
import sys
import os
import re

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'fracttal'))
from comun import Odoo, CTX  # noqa: E402

DB = next((a.split('=', 1)[1] for a in sys.argv if a.startswith('--db=')), 'secadora_2')

PREFIJO_ORIGEN = '1120'
PREFIJO_DESTINO = '1110'
SUFIJOS = {0: 'principal', 1: 'transitoria', 2: 'pagos entrantes', 3: 'pagos salientes'}


def ctx_cia(cid):
    return dict(CTX, allowed_company_ids=[cid])


def es_corriente(nombre):
    """La cuenta corriente se reconoce por el nombre, no por el codigo."""
    return bool(re.search(r'corriente|cte\b', nombre or '', re.IGNORECASE))


def main():
    o = Odoo(db=DB)
    companias = o.buscar_leer('res.company', [], ['name'])
    print(f'Base {DB} · mapa de cuentas corrientes (SOLO LECTURA)\n')

    total_bloques = total_movs = 0
    conflictos = []

    for cia in sorted(companias, key=lambda c: c['id']):
        cid, nombre_cia = cia['id'], cia['name']
        ctx = ctx_cia(cid)

        cuentas = o.x('account.account', 'search_read',
                      [('company_ids', 'in', [cid]),
                       '|', ('code', '=like', f'{PREFIJO_ORIGEN}%'),
                            ('code', '=like', f'{PREFIJO_DESTINO}%')],
                      fields=['code', 'name'], context=ctx)
        por_codigo = {c['code']: c for c in cuentas}
        ocupados = set(por_codigo)

        # Las principales de banco terminan en 0 (11200510, 11200520...); las
        # otras tres del bloque son esa +1, +2 y +3.
        principales = sorted(
            (c for c in cuentas
             if c['code'].startswith(PREFIJO_ORIGEN) and c['code'].endswith('0')),
            key=lambda c: c['code'])

        corrientes = [c for c in principales if es_corriente(c['name'])]
        ahorros = [c for c in principales if not es_corriente(c['name'])]

        print(f'=== [{cid}] {nombre_cia}')
        if not corrientes:
            print('    sin cuentas corrientes en 1120\n')
            continue

        for cta in corrientes:
            base = cta['code']
            destino_base = PREFIJO_DESTINO + base[len(PREFIJO_ORIGEN):]
            print(f'    {cta["name"]}')
            movs_bloque = 0
            for off, etiqueta in SUFIJOS.items():
                cod = str(int(base) + off)
                if cod not in por_codigo:
                    continue
                cid_cta = por_codigo[cod]['id']
                movs = o.x('account.move.line', 'search_count',
                           [('account_id', '=', cid_cta)], context=ctx)
                movs_bloque += movs
                dest = str(int(destino_base) + off)
                marca = ''
                if dest in ocupados:
                    marca = f'  <-- OCUPADO por "{por_codigo[dest]["name"]}"'
                    conflictos.append((nombre_cia, cod, dest,
                                       por_codigo[dest]['name']))
                print(f'        {cod} -> {dest}  {etiqueta:16} '
                      f'{movs:4} movs{marca}')
            total_bloques += 1
            total_movs += movs_bloque
        if ahorros:
            print('    (se quedan en 1120, son ahorros: '
                  + ', '.join(a['name'] for a in ahorros) + ')')
        print()

    print(f'--- {total_bloques} bloque(s) corriente(s), '
          f'{total_movs} movimiento(s) contable(s) en total')
    if conflictos:
        print(f'\n!! {len(conflictos)} CONFLICTO(S): el codigo destino ya existe.')
        for cia, orig, dest, quien in conflictos:
            print(f'   [{cia}] {orig} -> {dest} lo ocupa "{quien}"')
        print('   Hay que elegir otra numeracion para esos, o mover primero al'
              ' ocupante.')
    else:
        print('\nSin conflictos: todos los codigos destino estan libres.')


if __name__ == '__main__':
    main()
