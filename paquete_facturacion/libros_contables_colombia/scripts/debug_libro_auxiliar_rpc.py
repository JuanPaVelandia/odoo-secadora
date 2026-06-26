#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para depurar el Libro Auxiliar usando XML-RPC.
Permite probar el reporte sin necesidad de navegador.
"""
import xmlrpc.client
from datetime import datetime, date
from pprint import pprint

# Configuración
ODOO_URL = "http://localhost:3000"
DATABASE = "bohio"
USERNAME = "admin"
PASSWORD = "123456"

def main():
    print("=" * 80)
    print("DEPURADOR DE LIBRO AUXILIAR - Via XML-RPC")
    print("=" * 80)
    print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"URL: {ODOO_URL}")
    print(f"Base de datos: {DATABASE}")
    print("-" * 80)

    # Conectar
    common = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/common')
    uid = common.authenticate(DATABASE, USERNAME, PASSWORD, {})

    if not uid:
        print("ERROR: No se pudo autenticar")
        return

    print(f"✓ Autenticado como UID: {uid}")

    models = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/object')

    # 1. Buscar el reporte del Libro Auxiliar
    print("\n[1] Buscando reporte 'Libro Auxiliar'...")
    report_ids = models.execute_kw(
        DATABASE, uid, PASSWORD,
        'account.report', 'search',
        [[['name', 'ilike', 'Libro Auxiliar']]]
    )
    print(f"    IDs encontrados: {report_ids}")

    if not report_ids:
        print("    ERROR: No se encontró el reporte")
        # Buscar todos los reportes disponibles
        all_reports = models.execute_kw(
            DATABASE, uid, PASSWORD,
            'account.report', 'search_read',
            [[]],
            {'fields': ['name', 'root_report_id'], 'limit': 50}
        )
        print("\n    Reportes disponibles:")
        for r in all_reports:
            print(f"      - {r['id']}: {r['name']}")
        return

    report_id = report_ids[0]

    # 2. Obtener información del reporte
    print(f"\n[2] Obteniendo información del reporte ID={report_id}...")
    report_info = models.execute_kw(
        DATABASE, uid, PASSWORD,
        'account.report', 'read',
        [report_id],
        {'fields': ['name', 'filter_date_range', 'filter_partner', 'filter_journals',
                   'filter_hide_accounts_no_movement', 'custom_handler_model_id']}
    )
    print("    Información del reporte:")
    pprint(report_info)

    # 3. Verificar el handler personalizado
    print("\n[3] Verificando handler personalizado...")
    handler_model = models.execute_kw(
        DATABASE, uid, PASSWORD,
        'account.report', 'read',
        [report_id],
        {'fields': ['custom_handler_model_id']}
    )
    if handler_model and isinstance(handler_model, list) and handler_model[0].get('custom_handler_model_id'):
        handler_id = handler_model[0]['custom_handler_model_id'][0]
        handler_info = models.execute_kw(
            DATABASE, uid, PASSWORD,
            'ir.model', 'read',
            [handler_id],
            {'fields': ['model', 'name']}
        )
        print(f"    Handler: {handler_info}")
    else:
        print("    No tiene handler personalizado")

    # 4. Obtener las columnas del reporte
    print("\n[4] Obteniendo columnas del reporte...")
    columns = models.execute_kw(
        DATABASE, uid, PASSWORD,
        'account.report.column', 'search_read',
        [[['report_id', '=', report_id]]],
        {'fields': ['name', 'expression_label', 'figure_type', 'sequence'], 'order': 'sequence'}
    )
    print(f"    {len(columns)} columnas encontradas:")
    for col in columns:
        print(f"      [{col['sequence']}] {col['name']} ({col['expression_label']}) - {col['figure_type']}")

    # 5. Verificar el filtro hide_accounts_no_movement
    print("\n[5] Verificando filtro 'hide_accounts_no_movement'...")
    filter_value = models.execute_kw(
        DATABASE, uid, PASSWORD,
        'account.report', 'read',
        [report_id],
        {'fields': ['filter_hide_accounts_no_movement']}
    )
    print(f"    filter_hide_accounts_no_movement: {filter_value}")

    # 6. Probar get_options
    print("\n[6] Probando get_options del reporte...")
    try:
        # Crear opciones básicas
        options = {
            'date': {
                'date_from': '2025-01-01',
                'date_to': '2025-12-31',
                'filter': 'this_year',
                'mode': 'range',
            },
            'hide_accounts_no_movement': False,
        }

        # Llamar a get_options
        report_options = models.execute_kw(
            DATABASE, uid, PASSWORD,
            'account.report', 'get_options',
            [[report_id]],
            {'previous_options': options}
        )
        print("    Opciones obtenidas:")
        # Mostrar solo las claves relevantes
        relevant_keys = ['date', 'hide_accounts_no_movement', 'hide_0_lines',
                        'account_from', 'account_to', 'account_exclude']
        for key in relevant_keys:
            if key in report_options:
                print(f"      {key}: {report_options[key]}")

    except Exception as e:
        print(f"    ERROR al obtener opciones: {e}")

    # 7. Probar la generación de líneas (limitado)
    print("\n[7] Probando generación de líneas del reporte...")
    try:
        options = {
            'date': {
                'date_from': '2025-11-01',
                'date_to': '2025-11-30',
                'filter': 'custom',
                'mode': 'range',
            },
            'unfolded_lines': [],
            'hide_accounts_no_movement': False,
        }

        # Obtener las líneas
        lines_result = models.execute_kw(
            DATABASE, uid, PASSWORD,
            'account.report', 'get_report_information',
            [[report_id]],
            {'options': options}
        )

        if 'lines' in lines_result:
            lines = lines_result['lines']
            print(f"    Total líneas: {len(lines)}")
            print("    Primeras 5 líneas:")
            for i, line in enumerate(lines[:5]):
                name = line.get('name', 'Sin nombre')
                level = line.get('level', 0)
                print(f"      [{i}] Level {level}: {name}")
        else:
            print("    Resultado:")
            pprint(list(lines_result.keys()))

    except Exception as e:
        print(f"    ERROR al generar líneas: {e}")
        import traceback
        traceback.print_exc()

    # 8. Verificar si hay cuentas con movimientos
    print("\n[8] Verificando cuentas con movimientos en el período...")
    try:
        move_lines = models.execute_kw(
            DATABASE, uid, PASSWORD,
            'account.move.line', 'search_count',
            [[
                ['date', '>=', '2025-11-01'],
                ['date', '<=', '2025-11-30'],
                ['parent_state', '=', 'posted']
            ]]
        )
        print(f"    Líneas de asiento en Nov 2025: {move_lines}")

        # Contar por cuenta
        accounts_with_moves = models.execute_kw(
            DATABASE, uid, PASSWORD,
            'account.move.line', 'read_group',
            [[
                ['date', '>=', '2025-11-01'],
                ['date', '<=', '2025-11-30'],
                ['parent_state', '=', 'posted']
            ]],
            {'fields': ['account_id'], 'groupby': ['account_id'], 'limit': 10}
        )
        print(f"    Cuentas con movimientos (primeras 10):")
        for acc in accounts_with_moves:
            print(f"      - {acc['account_id'][1] if acc['account_id'] else 'N/A'}: {acc['account_id_count']} movimientos")

    except Exception as e:
        print(f"    ERROR: {e}")

    print("\n" + "=" * 80)
    print("FIN DEL DIAGNÓSTICO")
    print("=" * 80)


if __name__ == '__main__':
    main()
