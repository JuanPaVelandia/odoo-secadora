#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para probar la generación de PDF de reportes de impuestos.
Usa la API directa de Odoo 18.
"""
import sys
import os
import base64
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


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Inicializar Odoo
    odoo.tools.config.parse_config(['--config', CONFIG_FILE])

    # Conectar a la base de datos
    with odoo.registry(DB_NAME).cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})

        print("=" * 70)
        print("PRUEBA DE REPORTES DE IMPUESTOS - DETALLE")
        print("=" * 70)

        # Período
        today = date.today()
        date_from = today.replace(day=1)
        date_to = today

        print(f"\nPeríodo: {date_from} - {date_to}")

        # Reporte general
        report = env.ref('libros_contables_colombia.co_tax_report', raise_if_not_found=False)

        if not report:
            print("ERROR: No se encontró el reporte co_tax_report")
            return

        print(f"\nReporte: {report.name} (ID: {report.id})")

        # Obtener opciones
        options = report.get_options({
            'date': {
                'date_from': date_from.strftime('%Y-%m-%d'),
                'date_to': date_to.strftime('%Y-%m-%d'),
                'mode': 'range',
                'filter': 'custom',
            }
        })

        # Obtener líneas
        lines = report._get_lines(options)

        print(f"\n{'=' * 70}")
        print("DATOS DEL REPORTE")
        print(f"{'=' * 70}")

        if not lines:
            print("No hay líneas en el reporte")
            return

        print(f"\nTotal líneas: {len(lines)}")
        print(f"\nColumnas configuradas:")
        for col in options.get('columns', []):
            print(f"  - {col.get('name', col.get('expression_label', 'N/A'))}")

        print(f"\n{'─' * 70}")
        print("CONTENIDO DEL REPORTE:")
        print(f"{'─' * 70}")

        for line in lines:
            level = line.get('level', 0)
            name = line.get('name', 'Sin nombre')
            indent = "  " * level

            columns = line.get('columns', [])
            values = []
            for col in columns:
                if isinstance(col, dict):
                    val = col.get('name', col.get('no_format', ''))
                    if val or val == 0:
                        values.append(str(val))
                else:
                    values.append(str(col))

            if values:
                print(f"{indent}{name}: {' | '.join(values)}")
            else:
                print(f"{indent}{name}")

        # Intentar generar el PDF mediante el action report
        print(f"\n{'=' * 70}")
        print("EXPORTANDO DATOS...")
        print(f"{'=' * 70}")

        # Guardar datos en CSV para verificación
        csv_path = os.path.join(OUTPUT_DIR, f"tax_report_{date_to.strftime('%Y%m%d')}.csv")

        with open(csv_path, 'w', encoding='utf-8') as f:
            # Escribir encabezados
            headers = ['Nivel', 'Nombre']
            for col in options.get('columns', []):
                headers.append(col.get('name', col.get('expression_label', 'Columna')))
            f.write(','.join(f'"{h}"' for h in headers) + '\n')

            # Escribir datos
            for line in lines:
                row = [str(line.get('level', 0)), line.get('name', '')]
                for col in line.get('columns', []):
                    if isinstance(col, dict):
                        val = col.get('no_format', col.get('name', ''))
                        row.append(str(val) if val else '')
                    else:
                        row.append(str(col))
                f.write(','.join(f'"{v}"' for v in row) + '\n')

        print(f"\n✓ CSV exportado: {csv_path}")

        # Verificar tamaño
        csv_size = os.path.getsize(csv_path)
        print(f"  Tamaño: {csv_size:,} bytes")

        # Mostrar contenido del CSV
        print(f"\nContenido del CSV (primeras 20 líneas):")
        with open(csv_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if i < 20:
                    print(f"  {line.rstrip()}")
                else:
                    break


if __name__ == '__main__':
    main()
