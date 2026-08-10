#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Crea la cuenta 11050501 'Depositos en Efectivo Bancarizados' y su diario.

Una cuenta y un diario de banco por cada compañia. Es idempotente: empareja
por (compañia, codigo) y por (compañia, codigo de diario), asi que volver a
correrlo no duplica nada.

Uso:
    python3 crear_deposito_bancarizado.py [--aplicar] [--db=secadora_2]

    sin --aplicar = simulacro, no escribe nada (por defecto)
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'fracttal'))
from comun import Odoo, CTX  # noqa: E402

CODIGO = '11050501'
NOMBRE = 'Depositos en Efectivo Bancarizados'
# 'asset_cash' es el tipo de las cuentas de banco y caja: sin el, el diario de
# banco no acepta la cuenta como cuenta por defecto.
TIPO = 'asset_cash'
COD_DIARIO = 'DEB'

APLICAR = '--aplicar' in sys.argv
DB = next((a.split('=', 1)[1] for a in sys.argv if a.startswith('--db=')), 'secadora_2')
MARCA = '' if APLICAR else '[simulacro] '


def ctx_cia(cid):
    """Contexto de compañia. Imprescindible para tocar `code`.

    En Odoo 19 el codigo de cuenta vive en code_store (jsonb con el company_id
    como clave). Un write sin este contexto lo escribe bajo la compañia por
    defecto del usuario y corrompe el PUC de otra compañia.
    """
    return dict(CTX, allowed_company_ids=[cid])


def cuenta_de(o, cid, codigo):
    """(id, nombre) de la cuenta con ese codigo en esa compañia, o (None, None)."""
    filas = o.x('account.account', 'search_read',
                [('company_ids', 'in', [cid]), ('code', '=', codigo)],
                fields=['code', 'name'], context=ctx_cia(cid))
    return (filas[0]['id'], filas[0]['name']) if filas else (None, None)


def diario_de(o, cid, codigo):
    filas = o.x('account.journal', 'search_read',
                [('company_id', '=', cid), ('code', '=', codigo)],
                fields=['name'], context=ctx_cia(cid))
    return filas[0]['id'] if filas else None


def codigo_diario_libre(o, cid):
    """Codigo de diario disponible: DEB, DEB1, DEB2...

    El codigo es unico por compañia y solo admite 5 caracteres, asi que si
    'DEB' ya lo ocupa otro diario hay que variarlo.
    """
    if not diario_de(o, cid, COD_DIARIO):
        return COD_DIARIO
    for n in range(1, 10):
        cand = f'{COD_DIARIO}{n}'
        if not diario_de(o, cid, cand):
            return cand
    raise SystemExit(f'No hay codigo de diario libre para la compañia {cid}')


def main():
    o = Odoo(db=DB)
    companias = o.buscar_leer('res.company', [], ['name'])
    print(f'{MARCA}Base {DB} · {len(companias)} compañias\n')

    creadas = diarios = renombradas = 0
    for cia in companias:
        cid, nombre_cia = cia['id'], cia['name']
        print(f'--- {nombre_cia}')

        cuenta_id, nombre_actual = cuenta_de(o, cid, CODIGO)
        if cuenta_id:
            # El PUC la trae como "CAJA"; se renombra sin tocar los asientos,
            # que cuelgan del id de la cuenta y no de su nombre.
            if nombre_actual != NOMBRE:
                if APLICAR:
                    o.x('account.account', 'write', [cuenta_id],
                        {'name': NOMBRE}, context=ctx_cia(cid))
                    print(f'    cuenta {CODIGO}: "{nombre_actual}" -> "{NOMBRE}"')
                else:
                    print(f'    {MARCA}renombraria {CODIGO}: '
                          f'"{nombre_actual}" -> "{NOMBRE}"')
                renombradas += 1
            else:
                print(f'    cuenta {CODIGO} ya estaba correcta (id {cuenta_id})')
        else:
            if APLICAR:
                cuenta_id = o.crear('account.account', {
                    'code': CODIGO,
                    'name': NOMBRE,
                    'account_type': TIPO,
                    'company_ids': [(6, 0, [cid])],
                }, ctx=ctx_cia(cid))
                print(f'    cuenta {CODIGO} creada (id {cuenta_id})')
            else:
                print(f'    {MARCA}crearia la cuenta {CODIGO} "{NOMBRE}"')
            creadas += 1

        # El diario necesita la cuenta: en simulacro puede no existir todavia.
        if diario_de(o, cid, COD_DIARIO):
            print(f'    diario {COD_DIARIO} ya existe')
            continue
        if not APLICAR:
            print(f'    {MARCA}crearia el diario de banco "{NOMBRE}"')
            diarios += 1
            continue

        vals = {
            'name': NOMBRE,
            'code': codigo_diario_libre(o, cid),
            'type': 'bank',
            'company_id': cid,
        }
        if cuenta_id:
            vals['default_account_id'] = cuenta_id
        did = o.crear('account.journal', vals, ctx=ctx_cia(cid))
        print(f'    diario creado (id {did}, codigo {vals["code"]})')
        diarios += 1

    print(f'\n{MARCA}Cuentas creadas: {creadas} · renombradas: {renombradas} · '
          f'Diarios: {diarios}')
    if not APLICAR:
        print('\nNada se escribio. Repite con --aplicar para hacerlo efectivo.')


if __name__ == '__main__':
    main()
