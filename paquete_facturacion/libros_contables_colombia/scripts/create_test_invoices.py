#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para crear terceros de prueba con información fiscal colombiana,
facturas de compra y venta, y probar los reportes de impuestos.
"""
import sys
import os
import random
from datetime import datetime, timedelta

# Agregar path de Odoo
sys.path.insert(0, '/var/odoo/bohio/src')
os.chdir('/var/odoo/bohio')

import odoo
from odoo import api, SUPERUSER_ID

# Configuración
DB_NAME = 'bohio'
CONFIG_FILE = '/var/odoo/bohio/odoo.conf'

# Datos de terceros colombianos de prueba
TERCEROS_DATA = [
    # Personas Jurídicas (empresas)
    {
        'name': 'Distribuidora Nacional S.A.S.',
        'vat': '900123456',
        'is_company': True,
        'l10n_latam_identification_type_id': 'nit',  # NIT
        'street': 'Calle 80 # 45-23',
        'city': 'Bogotá',
        'email': 'contacto@distribuidoranacional.co',
        'phone': '601-3456789',
    },
    {
        'name': 'Comercializadora ABC Ltda',
        'vat': '800987654',
        'is_company': True,
        'l10n_latam_identification_type_id': 'nit',
        'street': 'Carrera 15 # 100-50',
        'city': 'Medellín',
        'email': 'ventas@comercializadoraabc.co',
        'phone': '604-2345678',
    },
    {
        'name': 'Servicios Profesionales XYZ S.A.',
        'vat': '830456789',
        'is_company': True,
        'l10n_latam_identification_type_id': 'nit',
        'street': 'Av. El Dorado # 68-51',
        'city': 'Bogotá',
        'email': 'info@serviciosxyz.co',
        'phone': '601-5678901',
    },
    {
        'name': 'Tecnología Avanzada S.A.S.',
        'vat': '901234567',
        'is_company': True,
        'l10n_latam_identification_type_id': 'nit',
        'street': 'Calle 72 # 10-34',
        'city': 'Cali',
        'email': 'soporte@tecnologiaavanzada.co',
        'phone': '602-8901234',
    },
    # Personas Naturales
    {
        'name': 'Carlos Andrés Rodríguez López',
        'vat': '79123456',
        'is_company': False,
        'l10n_latam_identification_type_id': 'cc',  # Cédula
        'street': 'Calle 45 # 12-34 Apto 301',
        'city': 'Bogotá',
        'email': 'carlos.rodriguez@gmail.com',
        'phone': '315-1234567',
    },
    {
        'name': 'María José Gómez Vargas',
        'vat': '52987654',
        'is_company': False,
        'l10n_latam_identification_type_id': 'cc',
        'street': 'Carrera 7 # 156-78',
        'city': 'Bogotá',
        'email': 'mariaj.gomez@outlook.com',
        'phone': '320-9876543',
    },
    {
        'name': 'Juan Pablo Martínez Ruiz',
        'vat': '1098765432',
        'is_company': False,
        'l10n_latam_identification_type_id': 'cc',
        'street': 'Diagonal 85 # 23-45',
        'city': 'Barranquilla',
        'email': 'juanp.martinez@yahoo.com',
        'phone': '318-5432167',
    },
]

# Productos/Servicios de prueba
PRODUCTOS_DATA = [
    {'name': 'Servicio de Consultoría', 'type': 'service', 'list_price': 5000000},
    {'name': 'Servicio de Mantenimiento', 'type': 'service', 'list_price': 2500000},
    {'name': 'Equipos de Cómputo', 'type': 'consu', 'list_price': 3500000},
    {'name': 'Suministros de Oficina', 'type': 'consu', 'list_price': 500000},
    {'name': 'Licencias de Software', 'type': 'service', 'list_price': 8000000},
    {'name': 'Arrendamiento de Local', 'type': 'service', 'list_price': 4000000},
]


def main():
    # Inicializar Odoo
    odoo.tools.config.parse_config(['--config', CONFIG_FILE])

    # Conectar a la base de datos
    with odoo.registry(DB_NAME).cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})

        print("=" * 60)
        print("CREACIÓN DE DATOS DE PRUEBA PARA REPORTES DE IMPUESTOS")
        print("=" * 60)

        # 1. Obtener tipos de identificación
        print("\n1. Buscando tipos de identificación...")
        id_types = {}
        nit_type = env['l10n_latam.identification.type'].search([('name', 'ilike', 'NIT')], limit=1)
        cc_type = env['l10n_latam.identification.type'].search([('name', 'ilike', 'Cédula')], limit=1)

        if not nit_type:
            nit_type = env['l10n_latam.identification.type'].search([('l10n_co_document_code', '=', 'national_citizen_id')], limit=1)
        if not cc_type:
            cc_type = env['l10n_latam.identification.type'].search([('l10n_co_document_code', '=', 'national_citizen_id')], limit=1)

        id_types['nit'] = nit_type.id if nit_type else False
        id_types['cc'] = cc_type.id if cc_type else False

        print(f"   - NIT: {nit_type.name if nit_type else 'No encontrado'}")
        print(f"   - Cédula: {cc_type.name if cc_type else 'No encontrado'}")

        # 2. Obtener país Colombia
        country_co = env['res.country'].search([('code', '=', 'CO')], limit=1)

        # 3. Crear/actualizar terceros
        print("\n2. Creando/actualizando terceros...")
        partners = []

        for tercero in TERCEROS_DATA:
            # Buscar si ya existe
            existing = env['res.partner'].search([('vat', '=', tercero['vat'])], limit=1)

            vals = {
                'name': tercero['name'],
                'vat': tercero['vat'],
                'is_company': tercero['is_company'],
                'street': tercero['street'],
                'city': tercero['city'],
                'email': tercero['email'],
                'phone': tercero['phone'],
                'country_id': country_co.id if country_co else False,
            }

            # Agregar tipo de identificación
            id_type_key = tercero['l10n_latam_identification_type_id']
            if id_types.get(id_type_key):
                vals['l10n_latam_identification_type_id'] = id_types[id_type_key]

            if existing:
                existing.write(vals)
                partners.append(existing)
                print(f"   ✓ Actualizado: {tercero['name']} ({tercero['vat']})")
            else:
                new_partner = env['res.partner'].create(vals)
                partners.append(new_partner)
                print(f"   + Creado: {tercero['name']} ({tercero['vat']})")

        # 4. Buscar/crear productos
        print("\n3. Buscando/creando productos...")
        products = []

        for prod_data in PRODUCTOS_DATA:
            existing = env['product.product'].search([('name', '=', prod_data['name'])], limit=1)

            if existing:
                products.append(existing)
                print(f"   ✓ Encontrado: {prod_data['name']}")
            else:
                product = env['product.product'].create({
                    'name': prod_data['name'],
                    'type': prod_data['type'],
                    'list_price': prod_data['list_price'],
                    'taxes_id': False,  # Se asignarán según factura
                })
                products.append(product)
                print(f"   + Creado: {prod_data['name']}")

        # 5. Obtener impuestos
        print("\n4. Buscando impuestos...")
        company = env.company

        # IVA 19%
        iva_venta = env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('amount', '=', 19),
            ('company_id', '=', company.id)
        ], limit=1)

        iva_compra = env['account.tax'].search([
            ('type_tax_use', '=', 'purchase'),
            ('amount', '=', 19),
            ('company_id', '=', company.id)
        ], limit=1)

        # Retención en la fuente (compras)
        retefuente = env['account.tax'].search([
            ('type_tax_use', '=', 'purchase'),
            ('amount', '<', 0),
            ('name', 'ilike', 'rete'),
            ('company_id', '=', company.id)
        ], limit=1)

        # ReteIVA
        reteiva = env['account.tax'].search([
            ('type_tax_use', '=', 'purchase'),
            ('name', 'ilike', 'reteiva'),
            ('company_id', '=', company.id)
        ], limit=1)

        print(f"   - IVA Venta 19%: {iva_venta.name if iva_venta else 'No encontrado'}")
        print(f"   - IVA Compra 19%: {iva_compra.name if iva_compra else 'No encontrado'}")
        print(f"   - ReteFuente: {retefuente.name if retefuente else 'No encontrado'}")
        print(f"   - ReteIVA: {reteiva.name if reteiva else 'No encontrado'}")

        # 6. Obtener diario de facturas
        print("\n5. Buscando diarios...")
        journal_sale = env['account.journal'].search([
            ('type', '=', 'sale'),
            ('company_id', '=', company.id)
        ], limit=1)

        journal_purchase = env['account.journal'].search([
            ('type', '=', 'purchase'),
            ('company_id', '=', company.id)
        ], limit=1)

        print(f"   - Diario Ventas: {journal_sale.name if journal_sale else 'No encontrado'}")
        print(f"   - Diario Compras: {journal_purchase.name if journal_purchase else 'No encontrado'}")

        if not journal_sale or not journal_purchase:
            print("\nERROR: No se encontraron los diarios necesarios")
            return

        # 7. Crear facturas de venta
        print("\n6. Creando facturas de VENTA...")
        sale_invoices = []

        for i, partner in enumerate(partners[:4]):  # Primeros 4 terceros
            product = products[i % len(products)]

            # Preparar impuestos de venta
            tax_ids = []
            if iva_venta:
                tax_ids.append(iva_venta.id)

            invoice_vals = {
                'move_type': 'out_invoice',
                'partner_id': partner.id,
                'journal_id': journal_sale.id,
                'invoice_date': datetime.now().date() - timedelta(days=random.randint(1, 30)),
                'invoice_line_ids': [(0, 0, {
                    'product_id': product.id,
                    'name': product.name,
                    'quantity': random.randint(1, 5),
                    'price_unit': product.list_price,
                    'tax_ids': [(6, 0, tax_ids)],
                })],
            }

            try:
                invoice = env['account.move'].create(invoice_vals)
                # Publicar la factura
                invoice.action_post()
                sale_invoices.append(invoice)
                print(f"   + Factura Venta: {invoice.name} - {partner.name} - ${invoice.amount_total:,.0f}")
            except Exception as e:
                print(f"   ! Error creando factura para {partner.name}: {str(e)}")

        # 8. Crear facturas de compra
        print("\n7. Creando facturas de COMPRA...")
        purchase_invoices = []

        for i, partner in enumerate(partners):
            product = products[(i + 2) % len(products)]

            # Preparar impuestos de compra
            tax_ids = []
            if iva_compra:
                tax_ids.append(iva_compra.id)
            if retefuente and partner.is_company:
                tax_ids.append(retefuente.id)
            if reteiva and partner.is_company:
                tax_ids.append(reteiva.id)

            invoice_vals = {
                'move_type': 'in_invoice',
                'partner_id': partner.id,
                'journal_id': journal_purchase.id,
                'invoice_date': datetime.now().date() - timedelta(days=random.randint(1, 30)),
                'ref': f'FAC-PROV-{random.randint(1000, 9999)}',
                'invoice_line_ids': [(0, 0, {
                    'product_id': product.id,
                    'name': product.name,
                    'quantity': random.randint(1, 3),
                    'price_unit': product.list_price * 0.8,  # Precio de compra
                    'tax_ids': [(6, 0, tax_ids)],
                })],
            }

            try:
                invoice = env['account.move'].create(invoice_vals)
                # Publicar la factura
                invoice.action_post()
                purchase_invoices.append(invoice)
                tipo_persona = "PJ" if partner.is_company else "PN"
                print(f"   + Factura Compra: {invoice.name} - {partner.name} ({tipo_persona}) - ${invoice.amount_total:,.0f}")
            except Exception as e:
                print(f"   ! Error creando factura para {partner.name}: {str(e)}")

        # 9. Resumen
        print("\n" + "=" * 60)
        print("RESUMEN DE CREACIÓN")
        print("=" * 60)
        print(f"   Terceros creados/actualizados: {len(partners)}")
        print(f"      - Personas Jurídicas (PJ): {sum(1 for p in partners if p.is_company)}")
        print(f"      - Personas Naturales (PN): {sum(1 for p in partners if not p.is_company)}")
        print(f"   Productos: {len(products)}")
        print(f"   Facturas de Venta: {len(sale_invoices)}")
        print(f"   Facturas de Compra: {len(purchase_invoices)}")

        # Commit cambios
        cr.commit()
        print("\n✓ Cambios guardados exitosamente")
        print("\nAhora puede acceder a los reportes de impuestos desde:")
        print("   Contabilidad > Reportes > Impuestos Colombia")


if __name__ == '__main__':
    main()
