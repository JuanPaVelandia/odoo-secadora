#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para generar y exportar reportes de impuestos colombianos.
Genera PDF y Excel de los reportes configurados.
"""
import sys
import os
import base64
from datetime import datetime, date
from dateutil.relativedelta import relativedelta

# Agregar path de Odoo
sys.path.insert(0, '/var/odoo/bohio/src')
os.chdir('/var/odoo/bohio')

import odoo
from odoo import api, SUPERUSER_ID

# Configuración
DB_NAME = 'bohio'
CONFIG_FILE = '/var/odoo/bohio/odoo.conf'
OUTPUT_DIR = '/tmp/tax_reports'


def get_report_options(env, report, date_from, date_to):
    """Obtener opciones del reporte con el rango de fechas especificado"""
    # En Odoo 18, get_options requiere previous_options
    previous_options = {
        'date': {
            'date_from': date_from.strftime('%Y-%m-%d'),
            'date_to': date_to.strftime('%Y-%m-%d'),
            'mode': 'range',
            'filter': 'custom',
        }
    }
    options = report.get_options(previous_options)

    # Asegurar que se muestren todos los datos
    options['unfold_all'] = False
    options['unfolded_lines'] = []

    return options


def generate_pdf_report(env, report, options, output_path):
    """Generar reporte en PDF"""
    try:
        # Usar el método de exportación de Odoo
        pdf_content = report.export_to_pdf(options)

        if pdf_content and 'file_content' in pdf_content:
            pdf_data = base64.b64decode(pdf_content['file_content'])
            with open(output_path, 'wb') as f:
                f.write(pdf_data)
            return True, len(pdf_data)
        return False, "No se generó contenido PDF"
    except Exception as e:
        return False, str(e)


def generate_xlsx_report(env, report, options, output_path):
    """Generar reporte en Excel"""
    try:
        xlsx_content = report.export_to_xlsx(options)

        if xlsx_content and 'file_content' in xlsx_content:
            xlsx_data = base64.b64decode(xlsx_content['file_content'])
            with open(output_path, 'wb') as f:
                f.write(xlsx_data)
            return True, len(xlsx_data)
        return False, "No se generó contenido Excel"
    except Exception as e:
        return False, str(e)


def get_report_lines_count(env, report, options):
    """Obtener cantidad de líneas del reporte"""
    try:
        lines = report._get_lines(options)
        return len(lines) if lines else 0
    except Exception as e:
        return 0


def main():
    # Crear directorio de salida
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Inicializar Odoo
    odoo.tools.config.parse_config(['--config', CONFIG_FILE])

    # Conectar a la base de datos
    with odoo.registry(DB_NAME).cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})

        print("=" * 70)
        print("GENERACIÓN DE REPORTES DE IMPUESTOS COLOMBIANOS")
        print("=" * 70)

        # Definir período (último mes)
        today = date.today()
        date_from = today.replace(day=1) - relativedelta(months=1)
        date_to = today.replace(day=1) - relativedelta(days=1)

        # Si no hay datos del mes anterior, usar el mes actual
        date_from = today.replace(day=1)
        date_to = today

        print(f"\nPeríodo: {date_from.strftime('%d/%m/%Y')} - {date_to.strftime('%d/%m/%Y')}")
        print(f"Directorio de salida: {OUTPUT_DIR}")

        # Buscar reportes de impuestos colombianos
        print("\n1. Buscando reportes de impuestos Colombia...")

        # Reportes definidos en all_financial_reports.xml
        report_xmlids = [
            ('libros_contables_colombia.co_tax_report', 'Reporte General de Impuestos'),
            ('libros_contables_colombia.co_tax_report_iva', 'Reporte de IVA'),
            ('libros_contables_colombia.co_tax_report_retefuente', 'Reporte de Retención en la Fuente'),
            ('libros_contables_colombia.co_tax_report_reteiva', 'Reporte de Retención de IVA'),
            ('libros_contables_colombia.co_tax_report_reteica', 'Reporte de Retención ICA'),
        ]

        reports_generated = 0
        reports_failed = 0

        for xmlid, report_name in report_xmlids:
            print(f"\n{'─' * 60}")
            print(f"Procesando: {report_name}")
            print(f"{'─' * 60}")

            try:
                # Buscar el reporte por xmlid
                report = env.ref(xmlid, raise_if_not_found=False)

                if not report:
                    print(f"   ⚠ Reporte no encontrado: {xmlid}")
                    reports_failed += 1
                    continue

                print(f"   ID: {report.id}")
                print(f"   Modelo: {report.name}")

                # Obtener opciones del reporte
                options = get_report_options(env, report, date_from, date_to)

                # Contar líneas del reporte
                lines_count = get_report_lines_count(env, report, options)
                print(f"   Líneas encontradas: {lines_count}")

                if lines_count == 0:
                    print(f"   ⚠ No hay datos para este reporte en el período")
                    continue

                # Nombre base del archivo
                safe_name = xmlid.split('.')[-1]
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

                # Generar PDF
                pdf_path = os.path.join(OUTPUT_DIR, f"{safe_name}_{timestamp}.pdf")
                print(f"\n   Generando PDF...")
                success, result = generate_pdf_report(env, report, options, pdf_path)
                if success:
                    print(f"   ✓ PDF generado: {pdf_path}")
                    print(f"     Tamaño: {result:,} bytes")
                else:
                    print(f"   ✗ Error generando PDF: {result}")

                # Generar Excel
                xlsx_path = os.path.join(OUTPUT_DIR, f"{safe_name}_{timestamp}.xlsx")
                print(f"\n   Generando Excel...")
                success, result = generate_xlsx_report(env, report, options, xlsx_path)
                if success:
                    print(f"   ✓ Excel generado: {xlsx_path}")
                    print(f"     Tamaño: {result:,} bytes")
                    reports_generated += 1
                else:
                    print(f"   ✗ Error generando Excel: {result}")

            except Exception as e:
                print(f"   ✗ Error procesando reporte: {str(e)}")
                reports_failed += 1
                import traceback
                traceback.print_exc()

        # Resumen final
        print("\n" + "=" * 70)
        print("RESUMEN")
        print("=" * 70)
        print(f"   Reportes generados: {reports_generated}")
        print(f"   Reportes fallidos: {reports_failed}")
        print(f"\n   Archivos en: {OUTPUT_DIR}")

        # Listar archivos generados
        files = os.listdir(OUTPUT_DIR)
        if files:
            print("\n   Archivos generados:")
            for f in sorted(files):
                file_path = os.path.join(OUTPUT_DIR, f)
                size = os.path.getsize(file_path)
                print(f"   - {f} ({size:,} bytes)")


if __name__ == '__main__':
    main()
