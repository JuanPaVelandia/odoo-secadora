#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para verificar el cálculo del balance en el Libro Auxiliar.
"""
import xmlrpc.client
from datetime import datetime
from pprint import pprint

# Configuración
ODOO_URL = "http://localhost:8018"
DATABASE = "odoo18sh"
USERNAME = "admin"
PASSWORD = "123456"

def main():
    print("=" * 80)
    print("VERIFICACIÓN DE CÁLCULO DE BALANCE - Libro Auxiliar")
    print("=" * 80)

    # Conectar
    common = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/common')
    uid = common.authenticate(DATABASE, USERNAME, PASSWORD, {})

    if not uid:
        print("ERROR: No se pudo autenticar")
        return

    print(f"✓ Autenticado como UID: {uid}")

    models = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/object')

    # Parámetros de prueba
    date_from = '2025-11-01'
    date_to = '2025-11-30'

    print(f"\nPeríodo: {date_from} a {date_to}")
    print("-" * 80)

    # 1. Buscar una cuenta con movimientos
    print("\n[1] Buscando cuenta con movimientos...")

    # Obtener cuentas con movimientos en el período
    aml_data = models.execute_kw(
        DATABASE, uid, PASSWORD,
        'account.move.line', 'read_group',
        [[
            ['date', '>=', date_from],
            ['date', '<=', date_to],
            ['parent_state', '=', 'posted']
        ]],
        {'fields': ['account_id', 'debit:sum', 'credit:sum', 'balance:sum'],
         'groupby': ['account_id'],
         'limit': 5,
         'orderby': 'balance:sum desc'}
    )

    if not aml_data:
        print("No hay movimientos en el período")
        return

    # Tomar la primera cuenta
    account_id = aml_data[0]['account_id'][0]
    account_name = aml_data[0]['account_id'][1]

    print(f"\n    Cuenta seleccionada: {account_name} (ID: {account_id})")

    # 2. Calcular manualmente
    print("\n[2] Calculando valores manualmente...")

    # Saldo inicial (antes de date_from)
    initial_balance = models.execute_kw(
        DATABASE, uid, PASSWORD,
        'account.move.line', 'read_group',
        [[
            ['account_id', '=', account_id],
            ['date', '<', date_from],
            ['parent_state', '=', 'posted']
        ]],
        {'fields': ['debit:sum', 'credit:sum', 'balance:sum'],
         'groupby': []}
    )

    init_debit = initial_balance[0]['debit'] if initial_balance else 0
    init_credit = initial_balance[0]['credit'] if initial_balance else 0
    init_balance = initial_balance[0]['balance'] if initial_balance else 0

    print(f"\n    SALDO INICIAL (antes de {date_from}):")
    print(f"      Débito:  {init_debit:>15,.2f}")
    print(f"      Crédito: {init_credit:>15,.2f}")
    print(f"      Balance: {init_balance:>15,.2f}")

    # Movimientos del período
    period_data = models.execute_kw(
        DATABASE, uid, PASSWORD,
        'account.move.line', 'read_group',
        [[
            ['account_id', '=', account_id],
            ['date', '>=', date_from],
            ['date', '<=', date_to],
            ['parent_state', '=', 'posted']
        ]],
        {'fields': ['debit:sum', 'credit:sum', 'balance:sum'],
         'groupby': []}
    )

    period_debit = period_data[0]['debit'] if period_data else 0
    period_credit = period_data[0]['credit'] if period_data else 0
    period_balance = period_data[0]['balance'] if period_data else 0

    print(f"\n    MOVIMIENTOS DEL PERÍODO ({date_from} a {date_to}):")
    print(f"      Débito:  {period_debit:>15,.2f}")
    print(f"      Crédito: {period_credit:>15,.2f}")
    print(f"      Balance: {period_balance:>15,.2f}")

    # Total (desde inicio año fiscal hasta date_to)
    total_data = models.execute_kw(
        DATABASE, uid, PASSWORD,
        'account.move.line', 'read_group',
        [[
            ['account_id', '=', account_id],
            ['date', '<=', date_to],
            ['parent_state', '=', 'posted']
        ]],
        {'fields': ['debit:sum', 'credit:sum', 'balance:sum'],
         'groupby': []}
    )

    total_debit = total_data[0]['debit'] if total_data else 0
    total_credit = total_data[0]['credit'] if total_data else 0
    total_balance = total_data[0]['balance'] if total_data else 0

    print(f"\n    TOTAL (hasta {date_to}):")
    print(f"      Débito:  {total_debit:>15,.2f}")
    print(f"      Crédito: {total_credit:>15,.2f}")
    print(f"      Balance: {total_balance:>15,.2f}")

    # 3. Verificación
    print("\n[3] Verificación de cálculos:")

    # Verificar: total = inicial + período
    calculated_total_balance = init_balance + period_balance
    print(f"\n    Saldo Inicial + Movimientos Período = Total?")
    print(f"      {init_balance:,.2f} + {period_balance:,.2f} = {calculated_total_balance:,.2f}")
    print(f"      Total real: {total_balance:,.2f}")

    if abs(calculated_total_balance - total_balance) < 0.01:
        print("      ✓ CORRECTO")
    else:
        print(f"      ✗ DIFERENCIA: {calculated_total_balance - total_balance:,.2f}")

    # 4. Obtener movimientos individuales
    print("\n[4] Movimientos individuales del período:")

    moves = models.execute_kw(
        DATABASE, uid, PASSWORD,
        'account.move.line', 'search_read',
        [[
            ['account_id', '=', account_id],
            ['date', '>=', date_from],
            ['date', '<=', date_to],
            ['parent_state', '=', 'posted']
        ]],
        {'fields': ['date', 'move_id', 'name', 'debit', 'credit', 'balance'],
         'order': 'date, id',
         'limit': 10}
    )

    running_balance = init_balance
    print(f"\n    {'Fecha':<12} {'Documento':<20} {'Débito':>12} {'Crédito':>12} {'Balance':>15}")
    print("    " + "-" * 75)
    print(f"    {'SALDO INI.':<12} {'':<20} {'':<12} {'':<12} {init_balance:>15,.2f}")

    for move in moves:
        running_balance += (move['debit'] or 0) - (move['credit'] or 0)
        move_name = move['move_id'][1] if move['move_id'] else ''
        print(f"    {str(move['date']):<12} {move_name[:20]:<20} {move['debit'] or 0:>12,.2f} {move['credit'] or 0:>12,.2f} {running_balance:>15,.2f}")

    print("\n    " + "-" * 75)
    print(f"    Balance calculado:  {running_balance:>15,.2f}")
    print(f"    Balance esperado:   {total_balance:>15,.2f}")

    if abs(running_balance - total_balance) < 0.01:
        print("    ✓ Balance acumulado CORRECTO")
    else:
        print(f"    ✗ DIFERENCIA: {running_balance - total_balance:,.2f}")

    print("\n" + "=" * 80)


if __name__ == '__main__':
    main()
