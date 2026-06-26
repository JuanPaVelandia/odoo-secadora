#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para crear impuestos ICA y ReteICA para las principales ciudades de Colombia.

Ciudades incluidas:
- Bogotá
- Medellín
- Barranquilla
- Cartagena
- Cali

Basado en normativa vigente 2024:
- Bogotá: Resolución SDH-000265, Acuerdo 780/2020
- Barranquilla: Decreto 0119/2019, Resolución DSH 001/2024
- Medellín: Acuerdo 066/2017, Acuerdo 040/2021
- Cartagena: Decreto 0810/2023
- Cali: Acuerdo 0439/2017
"""
import sys
import os
from datetime import datetime

# Agregar path de Odoo
sys.path.insert(0, '/var/odoo/bohio/src')
os.chdir('/var/odoo/bohio')

import odoo
from odoo import api, SUPERUSER_ID

# Configuración
DB_NAME = 'bohio'
CONFIG_FILE = '/var/odoo/bohio/odoo.conf'

# ============================================================================
# TARIFAS ICA POR CIUDAD - Actividades más comunes
# ============================================================================

# BOGOTA - Resolución SDH-000265, Acuerdo 780/2020
BOGOTA_ICA = {
    'code': 'BOG',
    'name': 'Bogotá D.C.',
    'base_min_services': 4,  # UVT
    'base_min_purchases': 27,  # UVT
    'activities': [
        # Industrial
        {'code': '101', 'name': 'Industria - Alimentos', 'rate': 4.14, 'type': 'industrial'},
        {'code': '102', 'name': 'Industria - Textiles/Confección', 'rate': 6.90, 'type': 'industrial'},
        {'code': '103', 'name': 'Industria - Bebidas', 'rate': 6.90, 'type': 'industrial'},
        {'code': '104', 'name': 'Industria - Construcción', 'rate': 6.90, 'type': 'industrial'},
        {'code': '105', 'name': 'Industria - General', 'rate': 11.04, 'type': 'industrial'},
        # Comercial
        {'code': '201', 'name': 'Comercio - Alimentos/Víveres', 'rate': 4.14, 'type': 'commercial'},
        {'code': '202', 'name': 'Comercio - Combustibles', 'rate': 4.14, 'type': 'commercial'},
        {'code': '203', 'name': 'Comercio - Drogas/Medicamentos', 'rate': 4.14, 'type': 'commercial'},
        {'code': '204', 'name': 'Comercio - Materiales Construcción', 'rate': 6.90, 'type': 'commercial'},
        {'code': '205', 'name': 'Comercio - Vehículos', 'rate': 6.90, 'type': 'commercial'},
        {'code': '206', 'name': 'Comercio - General', 'rate': 11.04, 'type': 'commercial'},
        # Servicios
        {'code': '301', 'name': 'Servicios - Educación', 'rate': 4.14, 'type': 'service'},
        {'code': '302', 'name': 'Servicios - Salud', 'rate': 4.14, 'type': 'service'},
        {'code': '303', 'name': 'Servicios - Transporte', 'rate': 6.90, 'type': 'service'},
        {'code': '304', 'name': 'Servicios - Construcción/Ingeniería', 'rate': 6.90, 'type': 'service'},
        {'code': '305', 'name': 'Servicios - Profesionales', 'rate': 9.66, 'type': 'service'},
        {'code': '306', 'name': 'Servicios - Hoteles/Restaurantes', 'rate': 9.66, 'type': 'service'},
        {'code': '307', 'name': 'Servicios - General', 'rate': 11.04, 'type': 'service'},
        # Financiero
        {'code': '401', 'name': 'Financiero - Bancos/Seguros', 'rate': 11.04, 'type': 'financial'},
        {'code': '402', 'name': 'Financiero - Actividades Bursátiles', 'rate': 14.00, 'type': 'financial'},
    ]
}

# BARRANQUILLA - Resolución DSH 001/2024, Decreto 0119/2019
BARRANQUILLA_ICA = {
    'code': 'BAQ',
    'name': 'Barranquilla',
    'base_min_services': 4,
    'base_min_purchases': 27,
    'activities': [
        # Industrial
        {'code': '101', 'name': 'Industria - Alimentos/Farmacéuticos', 'rate': 7.4, 'type': 'industrial'},
        {'code': '102', 'name': 'Industria - Textiles/Calzado', 'rate': 8.0, 'type': 'industrial'},
        {'code': '103', 'name': 'Industria - Bebidas/Tabaco', 'rate': 11.0, 'type': 'industrial'},
        {'code': '104', 'name': 'Industria - General', 'rate': 11.0, 'type': 'industrial'},
        # Comercial
        {'code': '201', 'name': 'Comercio - Alimentos', 'rate': 5.4, 'type': 'commercial'},
        {'code': '202', 'name': 'Comercio - Combustibles/Vehículos', 'rate': 7.0, 'type': 'commercial'},
        {'code': '203', 'name': 'Comercio - Materiales Construcción', 'rate': 10.0, 'type': 'commercial'},
        {'code': '204', 'name': 'Comercio - Licores/Cigarrillos', 'rate': 12.5, 'type': 'commercial'},
        {'code': '205', 'name': 'Comercio - General', 'rate': 12.5, 'type': 'commercial'},
        # Servicios
        {'code': '301', 'name': 'Servicios - Educación', 'rate': 4.5, 'type': 'service'},
        {'code': '302', 'name': 'Servicios - Transporte/Salud', 'rate': 8.0, 'type': 'service'},
        {'code': '303', 'name': 'Servicios - Hoteles/Restaurantes', 'rate': 10.0, 'type': 'service'},
        {'code': '304', 'name': 'Servicios - Gas/Electricidad/Agua', 'rate': 15.0, 'type': 'service'},
        {'code': '305', 'name': 'Servicios - Telecomunicaciones', 'rate': 20.0, 'type': 'service'},
        {'code': '306', 'name': 'Servicios - General', 'rate': 11.6, 'type': 'service'},
        # Financiero
        {'code': '401', 'name': 'Financiero - Bancos/Seguros', 'rate': 30.0, 'type': 'financial'},
        {'code': '402', 'name': 'Financiero - Cooperativas', 'rate': 12.5, 'type': 'financial'},
    ]
}

# MEDELLIN - Acuerdo 066/2017, Acuerdo 040/2021
MEDELLIN_ICA = {
    'code': 'MDE',
    'name': 'Medellín',
    'base_min_services': 15,
    'base_min_purchases': 15,
    'activities': [
        # Industrial
        {'code': '101', 'name': 'Industria - Tarifa Mínima', 'rate': 2.0, 'type': 'industrial'},
        {'code': '102', 'name': 'Industria - Tarifa Baja', 'rate': 3.0, 'type': 'industrial'},
        {'code': '103', 'name': 'Industria - Tarifa Media', 'rate': 4.0, 'type': 'industrial'},
        {'code': '104', 'name': 'Industria - Tarifa Alta', 'rate': 5.0, 'type': 'industrial'},
        {'code': '105', 'name': 'Industria - Tarifa Máxima', 'rate': 7.0, 'type': 'industrial'},
        # Comercial
        {'code': '201', 'name': 'Comercio - Tarifa Mínima', 'rate': 2.0, 'type': 'commercial'},
        {'code': '202', 'name': 'Comercio - Tarifa Baja', 'rate': 3.0, 'type': 'commercial'},
        {'code': '203', 'name': 'Comercio - Tarifa Media', 'rate': 4.0, 'type': 'commercial'},
        {'code': '204', 'name': 'Comercio - Tarifa Alta', 'rate': 5.0, 'type': 'commercial'},
        {'code': '205', 'name': 'Comercio - Tarifa Máxima', 'rate': 7.0, 'type': 'commercial'},
        {'code': '206', 'name': 'Comercio - Tarifa Especial', 'rate': 10.0, 'type': 'commercial'},
        {'code': '207', 'name': 'Comercio - Tarifa 8', 'rate': 8.0, 'type': 'commercial'},
        # Servicios
        {'code': '301', 'name': 'Servicios - Tarifa Mínima', 'rate': 2.0, 'type': 'service'},
        {'code': '302', 'name': 'Servicios - Tarifa Baja', 'rate': 3.0, 'type': 'service'},
        {'code': '303', 'name': 'Servicios - Tarifa Media', 'rate': 5.0, 'type': 'service'},
        {'code': '304', 'name': 'Servicios - Tarifa Alta', 'rate': 6.0, 'type': 'service'},
        {'code': '305', 'name': 'Servicios - Tarifa Máxima', 'rate': 10.0, 'type': 'service'},
        # Financiero
        {'code': '401', 'name': 'Financiero - Tarifa Baja', 'rate': 3.0, 'type': 'financial'},
        {'code': '402', 'name': 'Financiero - Tarifa Alta', 'rate': 5.0, 'type': 'financial'},
    ]
}

# CARTAGENA - Decreto 0810/2023
CARTAGENA_ICA = {
    'code': 'CTG',
    'name': 'Cartagena',
    'base_min_services': 4,
    'base_min_purchases': 27,
    'activities': [
        # Industrial
        {'code': '101', 'name': 'Industria - Alimentos/Agroindustria', 'rate': 4.0, 'type': 'industrial'},
        {'code': '102', 'name': 'Industria - Química/Petroquímica', 'rate': 7.0, 'type': 'industrial'},
        {'code': '103', 'name': 'Industria - General', 'rate': 10.0, 'type': 'industrial'},
        # Comercial
        {'code': '201', 'name': 'Comercio - Alimentos', 'rate': 4.0, 'type': 'commercial'},
        {'code': '202', 'name': 'Comercio - Combustibles', 'rate': 5.0, 'type': 'commercial'},
        {'code': '203', 'name': 'Comercio - General', 'rate': 10.0, 'type': 'commercial'},
        # Servicios
        {'code': '301', 'name': 'Servicios - Hoteles/Turismo', 'rate': 7.0, 'type': 'service'},
        {'code': '302', 'name': 'Servicios - Vigilancia/Temporales', 'rate': 7.0, 'type': 'service'},
        {'code': '303', 'name': 'Servicios - Transporte', 'rate': 8.0, 'type': 'service'},
        {'code': '304', 'name': 'Servicios - General', 'rate': 10.0, 'type': 'service'},
        # Financiero
        {'code': '401', 'name': 'Financiero - Bancos/Seguros', 'rate': 15.0, 'type': 'financial'},
    ]
}

# CALI - Acuerdo 0439/2017
CALI_ICA = {
    'code': 'CLO',
    'name': 'Cali',
    'base_min_services': 3,
    'base_min_purchases': 15,
    'activities': [
        # Industrial
        {'code': '101', 'name': 'Industria - Tarifa Mínima', 'rate': 2.0, 'type': 'industrial'},
        {'code': '102', 'name': 'Industria - Tarifa Baja', 'rate': 3.5, 'type': 'industrial'},
        {'code': '103', 'name': 'Industria - Tarifa Media', 'rate': 5.0, 'type': 'industrial'},
        {'code': '104', 'name': 'Industria - Tarifa Alta', 'rate': 7.0, 'type': 'industrial'},
        # Comercial
        {'code': '201', 'name': 'Comercio - Tarifa Mínima', 'rate': 3.0, 'type': 'commercial'},
        {'code': '202', 'name': 'Comercio - Tarifa Baja', 'rate': 4.0, 'type': 'commercial'},
        {'code': '203', 'name': 'Comercio - Tarifa Media', 'rate': 6.0, 'type': 'commercial'},
        {'code': '204', 'name': 'Comercio - Tarifa Alta', 'rate': 10.0, 'type': 'commercial'},
        # Servicios
        {'code': '301', 'name': 'Servicios - Tarifa Mínima', 'rate': 3.0, 'type': 'service'},
        {'code': '302', 'name': 'Servicios - Tarifa Baja', 'rate': 5.0, 'type': 'service'},
        {'code': '303', 'name': 'Servicios - Tarifa Media', 'rate': 7.0, 'type': 'service'},
        {'code': '304', 'name': 'Servicios - Tarifa Alta', 'rate': 10.0, 'type': 'service'},
        # Financiero
        {'code': '401', 'name': 'Financiero - Entidades', 'rate': 11.0, 'type': 'financial'},
    ]
}

# Lista de todas las ciudades
ALL_CITIES = [BOGOTA_ICA, BARRANQUILLA_ICA, MEDELLIN_ICA, CARTAGENA_ICA, CALI_ICA]


def get_or_create_tax_group(env, name, sequence=100):
    """Obtener o crear grupo de impuestos."""
    TaxGroup = env['account.tax.group']
    group = TaxGroup.search([('name', '=', name)], limit=1)
    if not group:
        group = TaxGroup.create({
            'name': name,
            'sequence': sequence,
        })
    return group


def get_repartition_lines(env, account_code, is_refund=False):
    """Obtener líneas de repartición con la cuenta especificada."""
    Account = env['account.account']
    account = Account.search([('code', '=', account_code)], limit=1)

    lines = [
        # Línea base
        (0, 0, {
            'repartition_type': 'base',
            'document_type': 'refund' if is_refund else 'invoice',
        }),
        # Línea de impuesto
        (0, 0, {
            'repartition_type': 'tax',
            'document_type': 'refund' if is_refund else 'invoice',
            'account_id': account.id if account else False,
        }),
    ]
    return lines


def create_ica_taxes(env, city_data):
    """Crear impuestos ICA para una ciudad."""
    Tax = env['account.tax']
    company = env.company
    created_taxes = []

    city_code = city_data['code']
    city_name = city_data['name']

    print(f"\n{'─' * 50}")
    print(f"Procesando: {city_name}")
    print(f"{'─' * 50}")

    # Crear grupo de impuestos para la ciudad
    tax_group = get_or_create_tax_group(env, f"ICA {city_name}", sequence=150)

    for activity in city_data['activities']:
        # Nombre del impuesto ICA (positivo - se cobra)
        ica_name = f"[ICA {city_code}] {activity['name']} ({activity['rate']}‰)"

        # Verificar si ya existe
        existing = Tax.search([
            ('name', '=', ica_name),
            ('company_id', '=', company.id),
        ], limit=1)

        if existing:
            print(f"  ✓ Ya existe: {ica_name}")
            continue

        # Crear impuesto ICA (tipo venta - se aplica en ventas locales)
        try:
            tax = Tax.create({
                'name': ica_name,
                'type_tax_use': 'sale',
                'amount_type': 'percent',
                'amount': activity['rate'] / 10,  # Convertir por mil a porcentaje
                'description': f"ICA {city_name} - {activity['name']}",
                'tax_group_id': tax_group.id,
                'l10n_co_tax_type': 'reteica',  # Clasificación para reportes
                'active': True,
                'company_id': company.id,
            })
            created_taxes.append(tax)
            print(f"  + Creado: {ica_name}")
        except Exception as e:
            print(f"  ✗ Error creando {ica_name}: {e}")

    return created_taxes


def create_reteica_taxes(env, city_data):
    """Crear impuestos ReteICA (retención) para una ciudad."""
    Tax = env['account.tax']
    company = env.company
    created_taxes = []

    city_code = city_data['code']
    city_name = city_data['name']

    # Crear grupo de retención ICA
    tax_group = get_or_create_tax_group(env, f"ReteICA {city_name}", sequence=160)

    # Tarifas principales para ReteICA
    # En ciudades como Cali, Barranquilla, Pereira: tarifa = 100% del ICA
    # En Medellín: tarifa única de 2x1000
    # En Bogotá: según actividad

    if city_code == 'MDE':
        # Medellín tiene tarifa única de retención
        reteica_activities = [
            {'code': 'UNICO', 'name': 'Todas las actividades', 'rate': 2.0},
        ]
    else:
        # Para otras ciudades, usamos tarifas representativas
        reteica_activities = [
            {'code': '01', 'name': 'Tarifa Mínima', 'rate': min(a['rate'] for a in city_data['activities'])},
            {'code': '02', 'name': 'Tarifa Media', 'rate': sum(a['rate'] for a in city_data['activities']) / len(city_data['activities'])},
            {'code': '03', 'name': 'Tarifa Máxima', 'rate': max(a['rate'] for a in city_data['activities'])},
        ]

        # También agregamos algunas actividades específicas comunes
        common_activities = [
            {'code': 'COM', 'name': 'Comercio General', 'rate': 10.0},
            {'code': 'SRV', 'name': 'Servicios General', 'rate': 10.0},
            {'code': 'FIN', 'name': 'Sector Financiero', 'rate': 11.0},
        ]
        reteica_activities.extend(common_activities)

    for activity in reteica_activities:
        # Nombre del impuesto ReteICA (negativo - se retiene)
        reteica_name = f"[R.ICA {city_code}] {activity['name']} ({activity['rate']:.2f}‰)"

        # Verificar si ya existe
        existing = Tax.search([
            ('name', '=', reteica_name),
            ('company_id', '=', company.id),
        ], limit=1)

        if existing:
            print(f"  ✓ Ya existe: {reteica_name}")
            continue

        # Crear impuesto ReteICA (tipo compra - se retiene en compras)
        try:
            tax = Tax.create({
                'name': reteica_name,
                'type_tax_use': 'purchase',
                'amount_type': 'percent',
                'amount': -activity['rate'] / 10,  # Negativo porque es retención, dividido 10 para %
                'description': f"Retención ICA {city_name} - {activity['name']}",
                'tax_group_id': tax_group.id,
                'l10n_co_tax_type': 'reteica',
                'active': True,
                'company_id': company.id,
            })
            created_taxes.append(tax)
            print(f"  + Creado ReteICA: {reteica_name}")
        except Exception as e:
            print(f"  ✗ Error creando {reteica_name}: {e}")

    return created_taxes


def create_common_taxes(env):
    """Crear impuestos comunes adicionales para todas las ciudades."""
    Tax = env['account.tax']
    company = env.company
    created_taxes = []

    print(f"\n{'=' * 50}")
    print("IMPUESTOS COMUNES ICA/ReteICA")
    print(f"{'=' * 50}")

    # Grupo genérico de ICA
    tax_group = get_or_create_tax_group(env, "ICA General", sequence=145)

    # Tarifas genéricas más usadas
    common_rates = [
        {'name': 'ICA General Comercio', 'rate': 10.0, 'type': 'sale'},
        {'name': 'ICA General Servicios', 'rate': 10.0, 'type': 'sale'},
        {'name': 'ICA General Industria', 'rate': 7.0, 'type': 'sale'},
        {'name': 'ReteICA General 10‰', 'rate': -1.0, 'type': 'purchase'},  # 10/1000 = 1%
        {'name': 'ReteICA General 7‰', 'rate': -0.7, 'type': 'purchase'},
        {'name': 'ReteICA General 5‰', 'rate': -0.5, 'type': 'purchase'},
    ]

    for rate_info in common_rates:
        tax_name = f"[ICA] {rate_info['name']}"

        existing = Tax.search([
            ('name', '=', tax_name),
            ('company_id', '=', company.id),
        ], limit=1)

        if existing:
            print(f"  ✓ Ya existe: {tax_name}")
            continue

        try:
            tax = Tax.create({
                'name': tax_name,
                'type_tax_use': rate_info['type'],
                'amount_type': 'percent',
                'amount': rate_info['rate'],
                'description': rate_info['name'],
                'tax_group_id': tax_group.id,
                'l10n_co_tax_type': 'reteica',
                'active': True,
                'company_id': company.id,
            })
            created_taxes.append(tax)
            print(f"  + Creado: {tax_name}")
        except Exception as e:
            print(f"  ✗ Error: {e}")

    return created_taxes


def print_summary(env):
    """Imprimir resumen de impuestos ICA/ReteICA existentes."""
    Tax = env['account.tax']

    print(f"\n{'=' * 70}")
    print("RESUMEN DE IMPUESTOS ICA/RETEICA EN EL SISTEMA")
    print(f"{'=' * 70}")

    # Buscar todos los impuestos ICA/ReteICA
    ica_taxes = Tax.search([
        '|',
        ('name', 'ilike', 'ICA'),
        ('l10n_co_tax_type', '=', 'reteica'),
    ], order='name')

    print(f"\nTotal impuestos ICA/ReteICA: {len(ica_taxes)}")

    # Agrupar por ciudad
    cities = {}
    for tax in ica_taxes:
        # Extraer código de ciudad del nombre
        if '[ICA ' in tax.name or '[R.ICA ' in tax.name:
            parts = tax.name.split(']')[0].replace('[ICA ', '').replace('[R.ICA ', '')
            city = parts.strip()
        else:
            city = 'General'

        if city not in cities:
            cities[city] = {'ica': [], 'reteica': []}

        if tax.amount < 0:
            cities[city]['reteica'].append(tax)
        else:
            cities[city]['ica'].append(tax)

    for city, taxes in sorted(cities.items()):
        print(f"\n{city}:")
        print(f"  ICA (venta): {len(taxes['ica'])} impuestos")
        print(f"  ReteICA (compra): {len(taxes['reteica'])} impuestos")

        # Mostrar algunos ejemplos
        if taxes['ica'][:3]:
            print("  Ejemplos ICA:")
            for t in taxes['ica'][:3]:
                print(f"    - {t.name}: {t.amount:.4f}%")
        if taxes['reteica'][:3]:
            print("  Ejemplos ReteICA:")
            for t in taxes['reteica'][:3]:
                print(f"    - {t.name}: {t.amount:.4f}%")


def main():
    # Inicializar Odoo
    odoo.tools.config.parse_config(['--config', CONFIG_FILE])

    with odoo.registry(DB_NAME).cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})

        print("=" * 70)
        print("CREACIÓN DE IMPUESTOS ICA Y RETEICA - CIUDADES PRINCIPALES COLOMBIA")
        print("=" * 70)
        print(f"\nFecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Empresa: {env.company.name}")

        total_created = 0

        # Crear impuestos comunes primero
        common = create_common_taxes(env)
        total_created += len(common)

        # Crear impuestos por ciudad
        for city_data in ALL_CITIES:
            print(f"\n{'=' * 50}")
            print(f"CIUDAD: {city_data['name'].upper()}")
            print(f"{'=' * 50}")

            # ICA (ventas locales)
            ica_taxes = create_ica_taxes(env, city_data)
            total_created += len(ica_taxes)

            # ReteICA (retención en compras)
            reteica_taxes = create_reteica_taxes(env, city_data)
            total_created += len(reteica_taxes)

            print(f"\nSubtotal {city_data['name']}: {len(ica_taxes) + len(reteica_taxes)} impuestos")

        # Confirmar cambios
        cr.commit()

        # Imprimir resumen
        print_summary(env)

        print(f"\n{'=' * 70}")
        print(f"PROCESO COMPLETADO")
        print(f"Total impuestos creados: {total_created}")
        print(f"{'=' * 70}")

        print("\nPara ver los impuestos en Odoo:")
        print("  → Contabilidad > Configuración > Impuestos")
        print("  → Filtrar por 'ICA' o 'ReteICA'")


if __name__ == '__main__':
    main()
