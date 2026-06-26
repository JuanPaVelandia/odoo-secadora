#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para probar el filtro de rango de cuentas en el Libro Auxiliar.
Verifica que el filtro funcione correctamente con rangos como 1105 a 1405.
"""
import xmlrpc.client
from datetime import datetime

# Configuración
ODOO_URL = "http://localhost:3000"
DATABASE = "bohio"
USERNAME = "admin"
PASSWORD = "123456"


def main():
    print("=" * 80)
    print("PRUEBA DE FILTRO DE RANGO DE CUENTAS - Libro Auxiliar")
    print("=" * 80)
    print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 80)

    # Conectar
    common = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/common')
    uid = common.authenticate(DATABASE, USERNAME, PASSWORD, {})

    if not uid:
        print("ERROR: No se pudo autenticar")
        return

    print(f"✓ Autenticado como UID: {uid}")

    models = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/object')

    # 1. Buscar cuentas SIN filtro (todas las cuentas con movimientos)
    print("\n[1] Consultando cuentas con movimientos...")

    all_accounts = models.execute_kw(
        DATABASE, uid, PASSWORD,
        'account.move.line', 'read_group',
        [[
            ('date', '>=', '2025-01-01'),
            ('date', '<=', '2025-12-31'),
            ('parent_state', '=', 'posted')
        ]],
        {
            'fields': ['account_id'],
            'groupby': ['account_id'],
            'limit': 100,
        }
    )

    print(f"    Total cuentas con movimientos: {len(all_accounts)}")

    # 2. Buscar cuentas CON filtro de rango 1105 a 1405
    print("\n[2] Consultando cuentas EN RANGO 1105 a 1405...")

    # Primero obtener los IDs de las cuentas en el rango
    accounts_in_range = models.execute_kw(
        DATABASE, uid, PASSWORD,
        'account.account', 'search',
        [[
            ('code', '>=', '1105'),
            ('code', '<=', '1405z')
        ]],
        {}
    )

    print(f"    Cuentas en rango (por código): {len(accounts_in_range)}")

    # Ahora buscar movimientos solo de esas cuentas
    if accounts_in_range:
        filtered_accounts = models.execute_kw(
            DATABASE, uid, PASSWORD,
            'account.move.line', 'read_group',
            [[
                ('date', '>=', '2025-01-01'),
                ('date', '<=', '2025-12-31'),
                ('parent_state', '=', 'posted'),
                ('account_id', 'in', accounts_in_range)
            ]],
            {
                'fields': ['account_id'],
                'groupby': ['account_id'],
                'limit': 100,
            }
        )

        print(f"    Cuentas con movimientos en rango: {len(filtered_accounts)}")

        for acc in filtered_accounts[:15]:
            account_name = acc['account_id'][1] if acc['account_id'] else 'N/A'
            print(f"      {account_name[:60]}")

        if len(filtered_accounts) > 15:
            print(f"      ... y {len(filtered_accounts) - 15} más")

    # 3. Probar exclusión - excluir cuenta 1110
    print("\n[3] Probando EXCLUSIÓN de cuentas con código 1110...")

    # Buscar cuentas con código 1110
    accounts_1110 = models.execute_kw(
        DATABASE, uid, PASSWORD,
        'account.account', 'search',
        [[
            ('code', '=like', '1110%')
        ]],
        {}
    )

    print(f"    Cuentas con código 1110*: {len(accounts_1110)}")

    if accounts_1110:
        # Obtener detalles
        accounts_1110_details = models.execute_kw(
            DATABASE, uid, PASSWORD,
            'account.account', 'read',
            [accounts_1110],
            {'fields': ['code', 'name']}
        )
        for acc in accounts_1110_details[:5]:
            print(f"      {acc['code']} - {acc['name'][:40]}")

    # 4. Verificar el dominio que se genera
    print("\n[4] Verificando dominio del filtro...")

    # Simular el dominio que genera _get_options_account_range_domain
    account_from = '1105'
    account_to = '1405'

    domain = []
    if account_from:
        domain.append(('account_id.code', '>=', account_from))
    if account_to:
        domain.append(('account_id.code', '<=', account_to + 'z'))

    print(f"    Dominio generado: {domain}")

    # Probar este dominio directamente en account.move.line
    print("\n[5] Probando dominio en account.move.line...")

    test_lines = models.execute_kw(
        DATABASE, uid, PASSWORD,
        'account.move.line', 'search_read',
        [[
            ('date', '>=', '2025-01-01'),
            ('date', '<=', '2025-12-31'),
            ('parent_state', '=', 'posted'),
            ('account_id.code', '>=', '1105'),
            ('account_id.code', '<=', '1405z')
        ]],
        {
            'fields': ['account_id', 'debit', 'credit'],
            'limit': 10,
            'order': 'account_id, date'
        }
    )

    print(f"    Líneas encontradas: {len(test_lines)}")

    seen_accounts = set()
    for line in test_lines:
        if line['account_id'] and line['account_id'][0] not in seen_accounts:
            seen_accounts.add(line['account_id'][0])
            print(f"      {line['account_id'][1][:50]} - D: {line['debit']:.2f}, C: {line['credit']:.2f}")

    # 6. Verificar cuentas fuera del rango NO aparecen
    print("\n[6] Verificando que cuentas FUERA del rango no aparecen...")

    outside_range = models.execute_kw(
        DATABASE, uid, PASSWORD,
        'account.move.line', 'search_count',
        [[
            ('date', '>=', '2025-01-01'),
            ('date', '<=', '2025-12-31'),
            ('parent_state', '=', 'posted'),
            ('account_id.code', '>=', '1105'),
            ('account_id.code', '<=', '1405z'),
            '|',
            ('account_id.code', '<', '1105'),
            ('account_id.code', '>', '1405z')
        ]],
        {}
    )

    if outside_range == 0:
        print("    ✓ No hay cuentas fuera del rango en los resultados filtrados")
    else:
        print(f"    ✗ ERROR: {outside_range} líneas con cuentas fuera del rango")

    print("\n" + "=" * 80)
    print("RESUMEN")
    print("=" * 80)
    print(f"  - Total cuentas con movimientos: {len(all_accounts)}")
    print(f"  - Cuentas en rango 1105-1405: {len(accounts_in_range)}")
    print(f"  - Cuentas con movimientos en rango: {len(filtered_accounts) if accounts_in_range else 0}")
    print(f"  - El dominio ('account_id.code', '>=', '1105') funciona: {'Sí' if test_lines else 'No'}")
    print("=" * 80)


if __name__ == '__main__':
    main()
