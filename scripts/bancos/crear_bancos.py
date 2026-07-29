#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Crea las cuentas del PUC y los diarios de las cuentas bancarias.

Por cada cuenta bancaria crea un bloque de 4 cuentas (banco, transitoria, pagos
entrantes, pagos salientes) y su diario. La numeracion y los nombres viven en
bancos.py, que es el archivo a revisar antes de aplicar.

Uso:
    python3 crear_bancos.py --paso=N [--aplicar]

    sin --aplicar  = simulacro, no escribe nada (por defecto)
    --paso=todos   = corre 1..5 seguidos (no recomendado la primera vez)

Pasos:
    1  renumera 11200501 -> 11200510 y renombra la cuenta y el diario BBAN
    2  crea las 52 cuentas restantes
    3  renombra los 4 diarios BBAN y crea los 10 nuevos
    4  enlaza suspense_account_id y las cuentas de las payment method lines
    5  reubica las lineas del asiento de apertura (estan en borrador)

Los pasos son idempotentes: emparejan por (compañía, codigo), asi que volver a
correrlos no duplica nada. Corre un paso, verifica, y solo entonces sigue.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'fracttal'))
from comun import Odoo, CTX  # noqa: E402

import bancos as B  # noqa: E402

APLICAR = '--aplicar' in sys.argv
PASO = next((a.split('=', 1)[1] for a in sys.argv if a.startswith('--paso=')), None)

MARCA = '' if APLICAR else '[simulacro] '


def ctx_cia(cid):
    """Contexto de compañía. Imprescindible para tocar `code`.

    En Odoo 19 el codigo de cuenta vive en code_store (jsonb con el company_id
    como clave). Un write sin este contexto lo escribe bajo la compañía por
    defecto del usuario y corrompe el PUC de otra compañía.
    """
    return dict(CTX, allowed_company_ids=[cid])


def cuentas_de(o, cid, codigos=None):
    """{codigo: id} de las cuentas de una compañía, leidas en su contexto."""
    dom = [('company_ids', 'in', [cid])]
    if codigos:
        dom.append(('code', 'in', list(codigos)))
    filas = o.x('account.account', 'search_read', dom, fields=['code'],
                context=ctx_cia(cid))
    return {f['code']: f['id'] for f in filas}


# --------------------------------------------------------------------------
def paso1_renumerar(o):
    """11200501 -> 11200510, con el nombre real de cada compañía.

    Los apuntes se enlazan por account_id, no por codigo, asi que los pagos ya
    publicados quedan correctos sin tocarlos.
    """
    print(f'\n=== PASO 1 · renumerar {B.CODIGO_VIEJO} -> 11200510 ===')
    for cid in sorted(B.COMPANIAS):
        banco, tipo, _num, corto = B.BANCOS[cid][0]
        nombre = B.nombre_cuenta(banco, tipo, corto, 0)

        actual = cuentas_de(o, cid, [B.CODIGO_VIEJO, '11200510'])
        if '11200510' in actual and B.CODIGO_VIEJO not in actual:
            print(f'  cia {cid}: ya renumerada, se omite')
            continue
        if B.CODIGO_VIEJO not in actual:
            raise SystemExit(f'  cia {cid}: no existe {B.CODIGO_VIEJO}; abortado')
        if '11200510' in actual:
            raise SystemExit(f'  cia {cid}: 11200510 ya ocupada por otra cuenta; abortado')

        acc = actual[B.CODIGO_VIEJO]
        previo = o.x('account.account', 'read', [acc], fields=['code', 'name'],
                     context=ctx_cia(cid))[0]
        print(f'  cia {cid}: id={acc}  {previo["code"]!r} {previo["name"]!r}')
        print(f'          -> \'11200510\' {nombre!r}')
        if APLICAR:
            o.escribir('account.account', [acc],
                       {'code': '11200510', 'name': nombre}, ctx=ctx_cia(cid))
            rel = o.x('account.account', 'read', [acc], fields=['code'],
                      context=ctx_cia(cid))[0]
            if rel['code'] != '11200510':
                raise SystemExit(f'  cia {cid}: el codigo quedo en {rel["code"]!r}; abortado')


# --------------------------------------------------------------------------
def paso2_cuentas(o):
    """Crea las cuentas que falten. La X0 del bloque 1 ya existe (paso 1)."""
    print('\n=== PASO 2 · crear cuentas ===')
    for cid in sorted(B.COMPANIAS):
        if cuentas_de(o, cid, [B.CODIGO_VIEJO]):
            raise SystemExit(f'  cia {cid}: {B.CODIGO_VIEJO} sigue existiendo; '
                             'corre antes el paso 1')

        existentes = cuentas_de(o, cid)
        faltan = [(c, n, t, r) for c, n, t, r in B.plan_cuentas(cid)
                  if c not in existentes]
        print(f'  cia {cid}: {len(faltan)} por crear, '
              f'{len(B.plan_cuentas(cid)) - len(faltan)} ya existen')
        if not faltan:
            continue

        vals = [{'code': c, 'name': n, 'account_type': t,
                 'reconcile': r, 'company_ids': [(4, cid)]}
                for c, n, t, r in faltan]
        for v in vals:
            print(f'    {MARCA}{v["code"]}  {v["name"]}')
        if APLICAR:
            o.x('account.account', 'create', vals, context=ctx_cia(cid))


# --------------------------------------------------------------------------
def paso3_diarios(o):
    """Renombra los BBAN existentes y crea los diarios que falten."""
    print('\n=== PASO 3 · diarios ===')
    for cid in sorted(B.COMPANIAS):
        cuentas = cuentas_de(o, cid)
        diarios = o.buscar_leer('account.journal',
                                [('company_id', '=', cid), ('type', '=', 'bank')],
                                ['code', 'name', 'default_account_id'])
        por_cuenta = {d['default_account_id'][0]: d
                      for d in diarios if d['default_account_id']}
        usados = {d['code'] for d in o.buscar_leer(
            'account.journal', [('company_id', '=', cid)], ['code'])}

        for i, (banco, tipo, _num, corto) in enumerate(B.BANCOS[cid]):
            code_x0 = B.codigo(i, 0)
            if code_x0 not in cuentas:
                raise SystemExit(f'  cia {cid}: falta la cuenta {code_x0}; '
                                 'corre antes el paso 2')
            acc_id = cuentas[code_x0]
            nombre = B.nombre_diario(banco, tipo, corto)

            existente = por_cuenta.get(acc_id)
            if existente:
                if existente['name'] != nombre:
                    print(f'  cia {cid}: diario {existente["code"]} '
                          f'{existente["name"]!r} -> {nombre!r}')
                    if APLICAR:
                        o.escribir('account.journal', [existente['id']],
                                   {'name': nombre}, ctx=ctx_cia(cid))
                else:
                    print(f'  cia {cid}: diario {existente["code"]} ya correcto')
                continue

            code_j = B.codigo_diario(cid, i, usados)
            usados.add(code_j)
            print(f'  {MARCA}cia {cid}: crear diario {code_j}  {nombre}  '
                  f'(cuenta {code_x0})')
            if APLICAR:
                o.crear('account.journal',
                        {'name': nombre, 'code': code_j, 'type': 'bank',
                         'company_id': cid, 'default_account_id': acc_id},
                        ctx=ctx_cia(cid))


# --------------------------------------------------------------------------
def paso4_enlaces(o):
    """suspense_account_id del diario y payment_account_id de sus lineas.

    Odoo crea solo las payment method lines al crear el diario, con la cuenta
    vacia. Aqui solo se les asigna la cuenta del bloque; crearlas a mano
    competiria con el compute y las duplicaria.
    """
    print('\n=== PASO 4 · transitoria y cuentas de pago ===')
    for cid in sorted(B.COMPANIAS):
        cuentas = cuentas_de(o, cid)
        for i, (banco, tipo, _num, corto) in enumerate(B.BANCOS[cid]):
            c0, c1, c2, c3 = (B.codigo(i, d) for d in range(4))
            faltantes = [c for c in (c0, c1, c2, c3) if c not in cuentas]
            if faltantes:
                raise SystemExit(f'  cia {cid}: faltan cuentas {faltantes}; '
                                 'corre antes el paso 2')

            js = o.buscar_leer('account.journal',
                               [('company_id', '=', cid), ('type', '=', 'bank'),
                                ('default_account_id', '=', cuentas[c0])],
                               ['code', 'suspense_account_id',
                                'inbound_payment_method_line_ids',
                                'outbound_payment_method_line_ids'])
            if not js:
                raise SystemExit(f'  cia {cid}: sin diario para {c0}; '
                                 'corre antes el paso 3')
            j = js[0]

            actual = j['suspense_account_id'][0] if j['suspense_account_id'] else None
            if actual != cuentas[c1]:
                print(f'  {MARCA}cia {cid} {j["code"]}: transitoria -> {c1}')
                if APLICAR:
                    o.escribir('account.journal', [j['id']],
                               {'suspense_account_id': cuentas[c1]}, ctx=ctx_cia(cid))

            for campo, code, etiqueta in (
                    ('inbound_payment_method_line_ids', c2, 'entrantes'),
                    ('outbound_payment_method_line_ids', c3, 'salientes')):
                lineas = j[campo]
                if not lineas:
                    continue
                print(f'  {MARCA}cia {cid} {j["code"]}: {len(lineas)} linea(s) '
                      f'{etiqueta} -> {code}')
                if APLICAR:
                    o.escribir('account.payment.method.line', lineas,
                               {'payment_account_id': cuentas[code]}, ctx=ctx_cia(cid))


# --------------------------------------------------------------------------
def paso5_aperturas(o):
    """Reubica las lineas del asiento de apertura segun su concepto.

    Estan en borrador. Se escribe sobre el move padre para que recalcule el
    balance; si alguna estuviera publicada se aborta, nunca se despublica.
    """
    print('\n=== PASO 5 · lineas de apertura ===')
    for cid in sorted(B.COMPANIAS):
        destinos = B.APERTURAS.get(cid) or {}
        if not destinos:
            print(f'  cia {cid}: nada que mover')
            continue

        cuentas = cuentas_de(o, cid)
        origen = cuentas.get('11200510')
        if not origen:
            raise SystemExit(f'  cia {cid}: falta 11200510; corre antes el paso 1')

        lineas = o.buscar_leer(
            'account.move.line',
            [('company_id', '=', cid), ('account_id', '=', origen),
             ('journal_id.code', '=', 'APER')],
            ['name', 'move_id', 'debit', 'credit', 'parent_state', 'account_id'])

        for l in lineas:
            code_dest = destinos.get((l['name'] or '').strip().upper())
            if not code_dest:
                print(f'  cia {cid}: {l["name"]!r} se queda donde esta')
                continue
            if l['parent_state'] != 'draft':
                raise SystemExit(f'  cia {cid}: la linea {l["id"]} esta en '
                                 f'{l["parent_state"]}, no en borrador; abortado')
            if code_dest not in cuentas:
                raise SystemExit(f'  cia {cid}: falta la cuenta {code_dest}')

            print(f'  {MARCA}cia {cid}: {l["name"]!r} ${l["debit"]:,.0f} '
                  f'-> {code_dest}   (linea {l["id"]}, revertir a {origen})')
            if APLICAR:
                o.escribir('account.move', [l['move_id'][0]],
                           {'line_ids': [(1, l['id'],
                                          {'account_id': cuentas[code_dest]})]},
                           ctx=ctx_cia(cid))


# --------------------------------------------------------------------------
PASOS = {'1': paso1_renumerar, '2': paso2_cuentas, '3': paso3_diarios,
         '4': paso4_enlaces, '5': paso5_aperturas}


def main():
    if PASO not in list(PASOS) + ['todos']:
        raise SystemExit(__doc__)

    o = Odoo()
    print(f'Conectado a {o.db} (uid={o.uid})')
    if not APLICAR:
        print('SIMULACRO: no se escribe nada. Añade --aplicar para ejecutar.')

    for clave in (sorted(PASOS) if PASO == 'todos' else [PASO]):
        PASOS[clave](o)

    print('\nListo.' if APLICAR else '\nFin del simulacro.')


if __name__ == '__main__':
    main()
