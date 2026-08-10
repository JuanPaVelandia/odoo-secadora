#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Renumera las cuentas corrientes de 1120xx a 1110xx.

Las corrientes pasan al rango 1110; las de ahorros se quedan en 1120. Dentro
de 1110 se numeran correlativas desde 11100510, de diez en diez, en el orden
en que estaban.

Cada cuenta bancaria es un BLOQUE de 4 cuentas correlativas (principal,
transitoria, pagos entrantes, pagos salientes) y se mueve entero.

Los asientos NO se tocan: cuelgan del id de la cuenta, no de su codigo. Lo
unico que cambia es el numero visible en el PUC y los reportes.

Uso:
    python3 renumerar_corrientes.py [--aplicar] [--db=secadora_2]

    sin --aplicar = simulacro, no escribe nada (por defecto)
"""
import sys
import os
import re

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'fracttal'))
from comun import Odoo, CTX  # noqa: E402

DB = next((a.split('=', 1)[1] for a in sys.argv if a.startswith('--db=')), 'secadora_2')
APLICAR = '--aplicar' in sys.argv
MARCA = '' if APLICAR else '[simulacro] '

PREFIJO_ORIGEN = '1120'
BASE_DESTINO = 11100510   # primera corriente de cada compañia
PASO = 10                 # separacion entre bloques
SUFIJOS = {0: 'principal', 1: 'transitoria',
           2: 'pagos entrantes', 3: 'pagos salientes'}


def ctx_cia(cid):
    """Contexto de compañia. Imprescindible para tocar `code`.

    En Odoo 19 el codigo vive en code_store (jsonb indexado por compañia). Un
    write sin este contexto lo escribe bajo la compañia por defecto del
    usuario y corrompe el PUC de otra.
    """
    return dict(CTX, allowed_company_ids=[cid])


def es_corriente(nombre):
    return bool(re.search(r'corriente|cte\b', nombre or '', re.IGNORECASE))


def plan_de_compania(o, cid):
    """[(id, codigo_actual, codigo_nuevo, nombre)] para una compañia."""
    ctx = ctx_cia(cid)
    cuentas = o.x('account.account', 'search_read',
                  [('company_ids', 'in', [cid]),
                   ('code', '=like', f'{PREFIJO_ORIGEN}%')],
                  fields=['code', 'name'], context=ctx)
    por_codigo = {c['code']: c for c in cuentas}

    principales = sorted(
        (c for c in cuentas if c['code'].endswith('0')),
        key=lambda c: c['code'])
    corrientes = [c for c in principales if es_corriente(c['name'])]

    plan = []
    for n, cta in enumerate(corrientes):
        base_orig = int(cta['code'])
        base_dest = BASE_DESTINO + n * PASO
        for off in SUFIJOS:
            cod = str(base_orig + off)
            if cod not in por_codigo:
                continue
            plan.append((por_codigo[cod]['id'], cod, str(base_dest + off),
                         por_codigo[cod]['name']))
    return plan


def codigos_ocupados(o, cid, codigos):
    """Cuales de esos codigos ya existen en la compañia."""
    if not codigos:
        return {}
    filas = o.x('account.account', 'search_read',
                [('company_ids', 'in', [cid]), ('code', 'in', list(codigos))],
                fields=['code', 'name'], context=ctx_cia(cid))
    return {f['code']: f['name'] for f in filas}


def main():
    o = Odoo(db=DB)
    companias = o.buscar_leer('res.company', [], ['name'])
    print(f'{MARCA}Base {DB}\n')

    total = 0
    for cia in sorted(companias, key=lambda c: c['id']):
        cid, nombre_cia = cia['id'], cia['name']
        plan = plan_de_compania(o, cid)
        if not plan:
            continue

        print(f'=== [{cid}] {nombre_cia}')

        # Un destino ocupado abortaria a medio camino y dejaria el PUC
        # inconsistente: se verifica ANTES de escribir nada.
        origenes = {p[1] for p in plan}
        ocupados = codigos_ocupados(o, cid, {p[2] for p in plan} - origenes)
        if ocupados:
            print('    !! ABORTADO: estos codigos destino ya existen:')
            for cod, quien in sorted(ocupados.items()):
                print(f'       {cod} = "{quien}"')
            print()
            continue

        for cta_id, orig, dest, nombre in plan:
            if APLICAR:
                o.x('account.account', 'write', [cta_id], {'code': dest},
                    context=ctx_cia(cid))
            print(f'    {MARCA}{orig} -> {dest}  {nombre}')
            total += 1
        print()

    print(f'{MARCA}{total} cuenta(s) renumerada(s)')
    if not APLICAR:
        print('\nNada se escribio. Repite con --aplicar para hacerlo efectivo.')


if __name__ == '__main__':
    main()
