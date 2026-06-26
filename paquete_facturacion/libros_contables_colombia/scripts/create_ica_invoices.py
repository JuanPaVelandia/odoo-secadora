#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para crear facturas de prueba con impuestos ICA.
Genera facturas de compra y venta para probar los reportes ICA.
"""
import sys
import os
from datetime import datetime, date
from random import choice, randint

# Agregar path de Odoo
sys.path.insert(0, '/var/odoo/bohio/src')
os.chdir('/var/odoo/bohio')

import odoo
from odoo import api, SUPERUSER_ID

# Configuración
DB_NAME = 'bohio'
CONFIG_FILE = '/var/odoo/bohio/odoo.conf'


def get_or_create_partners(env):
    """Obtener o crear terceros para pruebas ICA"""
    Partner = env['res.partner']

    partners_data = [
        # Bogotá
        {'name': 'Servicios Profesionales BOG S.A.S.', 'vat': '900123456-1', 'city': 'Bogotá', 'is_company': True},
        {'name': 'Comercializadora Capital Ltda', 'vat': '900234567-2', 'city': 'Bogotá', 'is_company': True},
        {'name': 'Juan Pérez Consultor', 'vat': '79123456', 'city': 'Bogotá', 'is_company': False},
        # Barranquilla
        {'name': 'Distribuidora Caribe S.A.S.', 'vat': '900345678-3', 'city': 'Barranquilla', 'is_company': True},
        {'name': 'Servicios Costeros Ltda', 'vat': '900456789-4', 'city': 'Barranquilla', 'is_company': True},
        # Medellín
        {'name': 'Industrial Antioquia S.A.', 'vat': '900567890-5', 'city': 'Medellín', 'is_company': True},
        {'name': 'Comercio Paisa Ltda', 'vat': '900678901-6', 'city': 'Medellín', 'is_company': True},
        # Cartagena
        {'name': 'Turismo Amurallado S.A.S.', 'vat': '900789012-7', 'city': 'Cartagena', 'is_company': True},
        # Cali
        {'name': 'Valle Industrial S.A.', 'vat': '900890123-8', 'city': 'Cali', 'is_company': True},
    ]

    partners = []
    for data in partners_data:
        partner = Partner.search([('vat', '=', data['vat'])], limit=1)
        if not partner:
            partner = Partner.create({
                'name': data['name'],
                'vat': data['vat'],
                'city': data.get('city', ''),
                'is_company': data.get('is_company', True),
                'country_id': env.ref('base.co').id,
            })
            print(f"  + Creado: {data['name']}")
        else:
            print(f"  ✓ Existe: {data['name']}")
        partners.append(partner)

    return partners


def get_ica_taxes(env):
    """Obtener impuestos ICA por ciudad"""
    Tax = env['account.tax']
    taxes_by_city = {}

    # Buscar impuestos ICA por ciudad
    for city_code in ['BOG', 'BAQ', 'MDE', 'CTG', 'CLO']:
        # ICA ventas (positivos)
        ica_sale = Tax.search([
            ('name', 'ilike', f'[ICA {city_code}]'),
            ('type_tax_use', '=', 'sale'),
            ('amount', '>', 0),
        ], limit=3)

        # ReteICA compras (negativos)
        reteica_purchase = Tax.search([
            ('name', 'ilike', f'[R.ICA {city_code}]'),
            ('type_tax_use', '=', 'purchase'),
        ], limit=3)

        if ica_sale or reteica_purchase:
            taxes_by_city[city_code] = {
                'sale': ica_sale,
                'purchase': reteica_purchase,
            }
            print(f"  {city_code}: {len(ica_sale)} ICA venta, {len(reteica_purchase)} ReteICA compra")

    return taxes_by_city


def create_sale_invoice(env, partner, taxes, amount):
    """Crear factura de venta con ICA"""
    Move = env['account.move']

    # Buscar cuenta de ingresos
    income_account = env['account.account'].search([
        ('code_store', 'ilike', '%4135%'),  # Comercio
        ('company_id', '=', env.company.id),
    ], limit=1)

    if not income_account:
        income_account = env['account.account'].search([
            ('account_type', '=', 'income'),
            ('company_id', '=', env.company.id),
        ], limit=1)

    # Buscar diario de ventas
    sale_journal = env['account.journal'].search([
        ('type', '=', 'sale'),
        ('company_id', '=', env.company.id),
    ], limit=1)

    invoice = Move.create({
        'move_type': 'out_invoice',
        'partner_id': partner.id,
        'invoice_date': date.today(),
        'journal_id': sale_journal.id,
        'invoice_line_ids': [(0, 0, {
            'name': f'Servicios profesionales - {partner.city or "Colombia"}',
            'quantity': 1,
            'price_unit': amount,
            'account_id': income_account.id if income_account else False,
            'tax_ids': [(6, 0, taxes.ids)] if taxes else [],
        })],
    })

    invoice.action_post()
    return invoice


def create_purchase_invoice(env, partner, taxes, amount):
    """Crear factura de compra con ReteICA"""
    Move = env['account.move']

    # Buscar cuenta de gastos
    expense_account = env['account.account'].search([
        ('code_store', 'ilike', '%5135%'),  # Servicios
        ('company_id', '=', env.company.id),
    ], limit=1)

    if not expense_account:
        expense_account = env['account.account'].search([
            ('account_type', '=', 'expense'),
            ('company_id', '=', env.company.id),
        ], limit=1)

    # Buscar diario de compras
    purchase_journal = env['account.journal'].search([
        ('type', '=', 'purchase'),
        ('company_id', '=', env.company.id),
    ], limit=1)

    invoice = Move.create({
        'move_type': 'in_invoice',
        'partner_id': partner.id,
        'invoice_date': date.today(),
        'journal_id': purchase_journal.id,
        'invoice_line_ids': [(0, 0, {
            'name': f'Compra de servicios - {partner.city or "Colombia"}',
            'quantity': 1,
            'price_unit': amount,
            'account_id': expense_account.id if expense_account else False,
            'tax_ids': [(6, 0, taxes.ids)] if taxes else [],
        })],
    })

    invoice.action_post()
    return invoice


def main():
    odoo.tools.config.parse_config(['--config', CONFIG_FILE])

    with odoo.registry(DB_NAME).cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})

        print("=" * 70)
        print("CREACIÓN DE FACTURAS CON IMPUESTOS ICA")
        print("=" * 70)
        print(f"\nEmpresa: {env.company.name}")
        print(f"Fecha: {date.today()}")

        # Crear/obtener terceros
        print("\n1. Preparando terceros...")
        partners = get_or_create_partners(env)

        # Obtener impuestos ICA
        print("\n2. Buscando impuestos ICA...")
        taxes_by_city = get_ica_taxes(env)

        if not taxes_by_city:
            print("\n⚠ No se encontraron impuestos ICA. Ejecute primero create_ica_taxes.py")
            return

        # Mapeo de terceros a ciudades
        city_map = {
            'Bogotá': 'BOG',
            'Barranquilla': 'BAQ',
            'Medellín': 'MDE',
            'Cartagena': 'CTG',
            'Cali': 'CLO',
        }

        created_invoices = {'sale': [], 'purchase': []}

        # Crear facturas de venta con ICA
        print("\n3. Creando facturas de venta con ICA...")
        for partner in partners[:5]:  # Primeros 5 partners
            city = partner.city or 'Bogotá'
            city_code = city_map.get(city, 'BOG')

            if city_code in taxes_by_city:
                sale_taxes = taxes_by_city[city_code].get('sale')
                if sale_taxes:
                    amount = randint(5, 20) * 1000000  # 5-20 millones
                    try:
                        inv = create_sale_invoice(env, partner, sale_taxes[:1], amount)
                        created_invoices['sale'].append(inv)
                        print(f"   + Venta a {partner.name}: ${amount:,.0f} + ICA {city_code}")
                    except Exception as e:
                        print(f"   ✗ Error venta {partner.name}: {e}")

        # Crear facturas de compra con ReteICA
        print("\n4. Creando facturas de compra con ReteICA...")
        for partner in partners[2:]:  # Desde el tercero
            city = partner.city or 'Bogotá'
            city_code = city_map.get(city, 'BOG')

            if city_code in taxes_by_city:
                purchase_taxes = taxes_by_city[city_code].get('purchase')
                if purchase_taxes:
                    amount = randint(3, 15) * 1000000  # 3-15 millones
                    try:
                        inv = create_purchase_invoice(env, partner, purchase_taxes[:1], amount)
                        created_invoices['purchase'].append(inv)
                        print(f"   + Compra a {partner.name}: ${amount:,.0f} - ReteICA {city_code}")
                    except Exception as e:
                        print(f"   ✗ Error compra {partner.name}: {e}")

        # Confirmar
        cr.commit()

        # Resumen
        print("\n" + "=" * 70)
        print("RESUMEN")
        print("=" * 70)
        print(f"\nFacturas de venta creadas: {len(created_invoices['sale'])}")
        print(f"Facturas de compra creadas: {len(created_invoices['purchase'])}")

        print("\nFacturas de venta:")
        for inv in created_invoices['sale']:
            print(f"  - {inv.name}: {inv.partner_id.name} - ${inv.amount_total:,.0f}")

        print("\nFacturas de compra:")
        for inv in created_invoices['purchase']:
            print(f"  - {inv.name}: {inv.partner_id.name} - ${inv.amount_total:,.0f}")

        print("\n✓ Ahora puede ejecutar generate_ica_forms.py para ver los reportes con datos")


if __name__ == '__main__':
    main()
