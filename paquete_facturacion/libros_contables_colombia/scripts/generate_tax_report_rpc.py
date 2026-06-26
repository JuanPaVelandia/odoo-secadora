#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para generar y exportar reportes de impuestos colombianos usando XML-RPC.
Requiere que Odoo esté corriendo.
"""
import xmlrpc.client
import base64
import os
from datetime import datetime, date
from dateutil.relativedelta import relativedelta

# Configuración
ODOO_URL = 'http://localhost:3000'
DB_NAME = 'bohio'
USERNAME = 'admin'  # Cambiar si es necesario
PASSWORD = 'admin'  # Cambiar si es necesario
OUTPUT_DIR = '/tmp/tax_reports'


def get_connection():
    """Establecer conexión con Odoo"""
    common = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/common')
    uid = common.authenticate(DB_NAME, USERNAME, PASSWORD, {})

    if not uid:
        raise Exception(f"No se pudo autenticar con usuario {USERNAME}")

    models = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/object')
    return uid, models


def main():
    # Crear directorio de salida
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 70)
    print("GENERACIÓN DE REPORTES DE IMPUESTOS - VIA RPC")
    print("=" * 70)

    try:
        uid, models = get_connection()
        print(f"\n✓ Conectado a Odoo como UID: {uid}")
    except Exception as e:
        print(f"\n✗ Error de conexión: {e}")
        print("\nVerifique que:")
        print("  1. Odoo esté corriendo (sudo systemctl status odona-bohio)")
        print("  2. Las credenciales sean correctas")
        return

    # Definir período
    today = date.today()
    date_from = today.replace(day=1)
    date_to = today

    print(f"\nPeríodo: {date_from.strftime('%d/%m/%Y')} - {date_to.strftime('%d/%m/%Y')}")

    # Reportes a generar
    report_xmlids = [
        ('libros_contables_colombia.co_tax_report', 'Reporte General de Impuestos'),
        ('libros_contables_colombia.co_tax_report_iva', 'Reporte de IVA'),
        ('libros_contables_colombia.co_tax_report_retefuente', 'Reporte ReteFuente'),
        ('libros_contables_colombia.co_tax_report_reteiva', 'Reporte ReteIVA'),
        ('libros_contables_colombia.co_tax_report_reteica', 'Reporte ReteICA'),
    ]

    for xmlid, report_name in report_xmlids:
        print(f"\n{'─' * 60}")
        print(f"Procesando: {report_name}")
        print(f"{'─' * 60}")

        try:
            # Obtener ID del reporte por xmlid
            report_ids = models.execute_kw(DB_NAME, uid, PASSWORD,
                'ir.model.data', 'search_read',
                [[['module', '=', xmlid.split('.')[0]], ['name', '=', xmlid.split('.')[1]]]],
                {'fields': ['res_id'], 'limit': 1}
            )

            if not report_ids:
                print(f"   ⚠ Reporte no encontrado: {xmlid}")
                continue

            report_id = report_ids[0]['res_id']
            print(f"   ID: {report_id}")

            # Obtener información del reporte
            report_info = models.execute_kw(DB_NAME, uid, PASSWORD,
                'account.report', 'read',
                [[report_id]],
                {'fields': ['name']}
            )
            print(f"   Nombre: {report_info[0]['name']}")

            # Generar opciones
            options = {
                'date': {
                    'date_from': date_from.strftime('%Y-%m-%d'),
                    'date_to': date_to.strftime('%Y-%m-%d'),
                    'mode': 'range',
                    'filter': 'custom',
                },
                'unfold_all': False,
                'unfolded_lines': [],
            }

            # Obtener opciones del reporte
            full_options = models.execute_kw(DB_NAME, uid, PASSWORD,
                'account.report', 'get_options',
                [[report_id], options]
            )

            # Obtener líneas del reporte
            lines = models.execute_kw(DB_NAME, uid, PASSWORD,
                'account.report', '_get_lines',
                [[report_id], full_options]
            )
            print(f"   Líneas: {len(lines) if lines else 0}")

            if not lines or len(lines) == 0:
                print(f"   ⚠ No hay datos para el período")
                continue

            # Mostrar resumen de líneas
            for line in lines[:5]:  # Mostrar primeras 5 líneas
                name = line.get('name', 'Sin nombre')
                columns = line.get('columns', [])
                if columns:
                    # Tomar el último valor (usualmente el total)
                    last_val = columns[-1].get('name', columns[-1].get('no_format', ''))
                    print(f"      - {name}: {last_val}")

            if len(lines) > 5:
                print(f"      ... y {len(lines) - 5} líneas más")

        except Exception as e:
            print(f"   ✗ Error: {str(e)}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 70)
    print("RESUMEN")
    print("=" * 70)
    print(f"\nLos reportes están disponibles en Odoo:")
    print(f"  → Contabilidad > Reportes > Impuestos Colombia")
    print(f"\nPara exportar PDF/Excel, acceda a cada reporte desde la interfaz web")
    print(f"  URL: {ODOO_URL}/web")


if __name__ == '__main__':
    main()
