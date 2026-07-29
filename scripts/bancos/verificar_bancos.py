#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Comprueba que las cuentas y diarios bancarios quedaron bien. Solo lectura.

Uso:  python3 verificar_bancos.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'fracttal'))
from comun import Odoo, CTX  # noqa: E402

import bancos as B  # noqa: E402

fallos = []


def check(etiqueta, esperado, obtenido):
    ok = esperado == obtenido
    print(f'  {"OK " if ok else "MAL"}  {etiqueta}: {obtenido!r}'
          + ('' if ok else f'  (esperado {esperado!r})'))
    if not ok:
        fallos.append(etiqueta)


def main():
    o = Odoo()
    print(f'Verificando {o.db}\n')

    for cid in sorted(B.COMPANIAS):
        ctx = dict(CTX, allowed_company_ids=[cid])
        print(f'--- cia {cid} · {B.COMPANIAS[cid]} ---')

        filas = o.x('account.account', 'search_read',
                    [('company_ids', 'in', [cid]), ('code', 'like', '112005%')],
                    fields=['code', 'name', 'account_type', 'reconcile'],
                    context=ctx)
        por_code = {f['code']: f for f in filas}

        esperadas = B.plan_cuentas(cid)
        check('cuentas 112005*', len(esperadas), len(filas))
        check(f'{B.CODIGO_VIEJO} ya no existe', False, B.CODIGO_VIEJO in por_code)

        for code, nombre, tipo, reconcile in esperadas:
            f = por_code.get(code)
            if not f:
                check(f'{code} existe', True, False)
                continue
            if f['name'] != nombre:
                check(f'{code} nombre', nombre, f['name'])
            if f['account_type'] != tipo:
                check(f'{code} tipo', tipo, f['account_type'])
            if f['reconcile'] != reconcile:
                check(f'{code} reconcile', reconcile, f['reconcile'])

        diarios = o.buscar_leer('account.journal',
                                [('company_id', '=', cid), ('type', '=', 'bank')],
                                ['code', 'name', 'default_account_id',
                                 'suspense_account_id',
                                 'inbound_payment_method_line_ids',
                                 'outbound_payment_method_line_ids'])
        # BNAL queda fuera del esquema por decision del usuario.
        propios = [d for d in diarios if d['default_account_id']
                   and d['default_account_id'][0] in
                   {por_code[c]['id'] for c in por_code}]
        check('diarios bancarios propios', len(B.BANCOS[cid]), len(propios))

        for i, (banco, tipo_c, _num, corto) in enumerate(B.BANCOS[cid]):
            c0, c1, c2, c3 = (B.codigo(i, d) for d in range(4))
            if c0 not in por_code:
                continue
            js = [d for d in propios
                  if d['default_account_id'][0] == por_code[c0]['id']]
            if not js:
                check(f'diario de {c0}', True, False)
                continue
            j = js[0]
            check(f'{j["code"]} nombre', B.nombre_diario(banco, tipo_c, corto), j['name'])
            susp = j['suspense_account_id'][1].split()[0] if j['suspense_account_id'] else None
            check(f'{j["code"]} transitoria', c1, susp)

            for campo, code_esp, etiqueta in (
                    ('inbound_payment_method_line_ids', c2, 'entrantes'),
                    ('outbound_payment_method_line_ids', c3, 'salientes')):
                lineas = o.x('account.payment.method.line', 'read', j[campo],
                             fields=['payment_account_id'], context=ctx)
                sin_cuenta = [l['id'] for l in lineas if not l['payment_account_id']]
                check(f'{j["code"]} {etiqueta} sin cuenta', [], sin_cuenta)
                distintas = {l['payment_account_id'][0] for l in lineas
                             if l['payment_account_id']}
                if distintas and distintas != {por_code[code_esp]['id']}:
                    check(f'{j["code"]} {etiqueta} apuntan a {code_esp}', True, False)
        print()

    print('=' * 60)
    if fallos:
        print(f'{len(fallos)} comprobacion(es) fallaron:')
        for f in fallos:
            print(f'  - {f}')
        sys.exit(1)
    print('Todo correcto.')


if __name__ == '__main__':
    main()
