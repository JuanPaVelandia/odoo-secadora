#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para exportar reportes de impuestos colombianos a PDF usando wkhtmltopdf.
Genera un PDF completo con formato profesional.
"""
import sys
import os
import subprocess
from datetime import datetime, date
from io import BytesIO

# Agregar path de Odoo
sys.path.insert(0, '/var/odoo/bohio/src')
os.chdir('/var/odoo/bohio')

import odoo
from odoo import api, SUPERUSER_ID

# Configuración
DB_NAME = 'bohio'
CONFIG_FILE = '/var/odoo/bohio/odoo.conf'
OUTPUT_DIR = '/tmp/tax_reports'


def format_money(value):
    """Formatear valor monetario colombiano"""
    if value is None:
        return ""
    try:
        return f"$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return str(value)


def format_percent(value):
    """Formatear porcentaje"""
    if value is None:
        return ""
    try:
        return f"{value:.2f}%"
    except:
        return str(value)


def generate_html_report(env, report, options, date_from, date_to):
    """Generar HTML del reporte"""
    lines = report._get_lines(options)

    if not lines:
        return None

    # Obtener información de la empresa
    company = env.company

    # Generar HTML
    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{report.name}</title>
    <style>
        @page {{
            size: A4 landscape;
            margin: 1cm;
        }}
        body {{
            font-family: Arial, sans-serif;
            font-size: 10px;
            margin: 0;
            padding: 20px;
        }}
        .header {{
            text-align: center;
            margin-bottom: 20px;
            border-bottom: 2px solid #333;
            padding-bottom: 10px;
        }}
        .header h1 {{
            margin: 0;
            font-size: 18px;
            color: #333;
        }}
        .header h2 {{
            margin: 5px 0;
            font-size: 14px;
            color: #666;
        }}
        .header .company {{
            font-size: 12px;
            color: #333;
            font-weight: bold;
        }}
        .header .period {{
            font-size: 11px;
            color: #666;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }}
        th {{
            background-color: #2c3e50;
            color: white;
            padding: 8px 5px;
            text-align: left;
            font-size: 9px;
            border: 1px solid #1a252f;
        }}
        th.numeric {{
            text-align: right;
        }}
        td {{
            padding: 6px 5px;
            border: 1px solid #ddd;
            font-size: 9px;
        }}
        td.numeric {{
            text-align: right;
            font-family: 'Courier New', monospace;
        }}
        tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}
        tr.level-0 {{
            background-color: #ecf0f1;
            font-weight: bold;
        }}
        tr.level-1 {{
            background-color: #f5f5f5;
        }}
        tr.total {{
            background-color: #2c3e50;
            color: white;
            font-weight: bold;
        }}
        tr.total td {{
            border-color: #1a252f;
        }}
        .footer {{
            margin-top: 20px;
            text-align: center;
            font-size: 8px;
            color: #999;
            border-top: 1px solid #ddd;
            padding-top: 10px;
        }}
        .pj {{
            color: #2980b9;
            font-weight: bold;
        }}
        .pn {{
            color: #27ae60;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="company">{company.name}</div>
        <div>NIT: {company.vat or 'N/A'}</div>
        <h1>{report.name}</h1>
        <div class="period">Período: {date_from.strftime('%d/%m/%Y')} - {date_to.strftime('%d/%m/%Y')}</div>
    </div>

    <table>
        <thead>
            <tr>
                <th style="width: 30%;">Concepto</th>
                <th class="numeric" style="width: 15%;">Base Gravable</th>
                <th class="numeric" style="width: 10%;">Tarifa %</th>
                <th class="numeric" style="width: 15%;">Valor Impuesto</th>
                <th style="width: 15%;">Tercero</th>
                <th style="width: 15%;">NIT/CC</th>
            </tr>
        </thead>
        <tbody>
'''

    # Agregar filas
    for line in lines:
        level = line.get('level', 0)
        name = line.get('name', '')
        columns = line.get('columns', [])

        # Determinar clase CSS
        css_class = f"level-{level}"
        if 'TOTAL' in name.upper():
            css_class = 'total'

        # Extraer valores de columnas
        base = ''
        percentage = ''
        tax = ''
        partner = ''
        vat = ''

        for i, col in enumerate(columns):
            if isinstance(col, dict):
                val = col.get('no_format', col.get('name', ''))
                col_name = options.get('columns', [{}])[i].get('expression_label', '') if i < len(options.get('columns', [])) else ''

                if col_name == 'base':
                    base = format_money(val) if val else ''
                elif col_name == 'percentage':
                    percentage = format_percent(val) if val else ''
                elif col_name == 'tax':
                    tax = format_money(val) if val else ''
                elif col_name == 'partner_name':
                    partner = val or ''
                elif col_name == 'partner_vat':
                    vat = val or ''

        # Si no tenemos valores individuales, usar posiciones
        if not base and len(columns) >= 5:
            base = format_money(columns[4].get('no_format', '')) if isinstance(columns[4], dict) else ''
        if not percentage and len(columns) >= 6:
            percentage = format_percent(columns[5].get('no_format', '')) if isinstance(columns[5], dict) else ''
        if not tax and len(columns) >= 7:
            tax = format_money(columns[6].get('no_format', '')) if isinstance(columns[6], dict) else ''

        html += f'''            <tr class="{css_class}">
                <td>{"&nbsp;" * (level * 4)}{name}</td>
                <td class="numeric">{base}</td>
                <td class="numeric">{percentage}</td>
                <td class="numeric">{tax}</td>
                <td>{partner}</td>
                <td>{vat}</td>
            </tr>
'''

    html += f'''        </tbody>
    </table>

    <div class="footer">
        Generado el {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} | {company.name} | Sistema de Reportes Fiscales Colombia
    </div>
</body>
</html>'''

    return html


def html_to_pdf(html_content, output_path):
    """Convertir HTML a PDF usando wkhtmltopdf"""
    # Guardar HTML temporal
    html_path = output_path.replace('.pdf', '.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    # Ejecutar wkhtmltopdf
    cmd = [
        '/usr/local/bin/wkhtmltopdf',
        '--orientation', 'Landscape',
        '--page-size', 'A4',
        '--margin-top', '10mm',
        '--margin-bottom', '10mm',
        '--margin-left', '10mm',
        '--margin-right', '10mm',
        '--encoding', 'UTF-8',
        '--enable-local-file-access',
        '--quiet',
        html_path,
        output_path
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            # Eliminar HTML temporal
            os.remove(html_path)
            return True, os.path.getsize(output_path)
        else:
            return False, result.stderr
    except Exception as e:
        return False, str(e)


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Inicializar Odoo
    odoo.tools.config.parse_config(['--config', CONFIG_FILE])

    with odoo.registry(DB_NAME).cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})

        print("=" * 70)
        print("EXPORTACIÓN DE REPORTES DE IMPUESTOS A PDF")
        print("=" * 70)

        today = date.today()
        date_from = today.replace(day=1)
        date_to = today

        print(f"\nPeríodo: {date_from.strftime('%d/%m/%Y')} - {date_to.strftime('%d/%m/%Y')}")
        print(f"Directorio: {OUTPUT_DIR}\n")

        # Reportes a generar
        reports = [
            ('libros_contables_colombia.co_tax_report', 'reporte_general_impuestos'),
            ('libros_contables_colombia.co_tax_report_iva', 'reporte_iva'),
            ('libros_contables_colombia.co_tax_report_retefuente', 'reporte_retefuente'),
            ('libros_contables_colombia.co_tax_report_reteiva', 'reporte_reteiva'),
            ('libros_contables_colombia.co_tax_report_reteica', 'reporte_reteica'),
        ]

        generated = 0
        for xmlid, filename in reports:
            print(f"{'─' * 50}")
            report = env.ref(xmlid, raise_if_not_found=False)

            if not report:
                print(f"⚠ No encontrado: {xmlid}")
                continue

            print(f"Procesando: {report.name}")

            options = report.get_options({
                'date': {
                    'date_from': date_from.strftime('%Y-%m-%d'),
                    'date_to': date_to.strftime('%Y-%m-%d'),
                    'mode': 'range',
                    'filter': 'custom',
                }
            })

            # Generar HTML
            html = generate_html_report(env, report, options, date_from, date_to)

            if not html:
                print(f"   ⚠ Sin datos para el período")
                continue

            # Convertir a PDF
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            pdf_path = os.path.join(OUTPUT_DIR, f"{filename}_{timestamp}.pdf")

            success, result = html_to_pdf(html, pdf_path)

            if success:
                print(f"   ✓ PDF: {pdf_path}")
                print(f"     Tamaño: {result:,} bytes")
                generated += 1
            else:
                print(f"   ✗ Error: {result}")

        print(f"\n{'=' * 70}")
        print(f"RESUMEN: {generated} reportes generados en {OUTPUT_DIR}")
        print(f"{'=' * 70}")

        # Listar archivos
        files = [f for f in os.listdir(OUTPUT_DIR) if f.endswith('.pdf')]
        if files:
            print("\nArchivos PDF generados:")
            for f in sorted(files)[-10:]:  # Últimos 10
                size = os.path.getsize(os.path.join(OUTPUT_DIR, f))
                print(f"  - {f} ({size:,} bytes)")


if __name__ == '__main__':
    main()
