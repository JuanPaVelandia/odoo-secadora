#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para generar liquidaciones de ICA con formato oficial.

Incluye:
- Cuentas de ingresos afectadas por actividad
- Tarifas por actividad económica
- Saldos a favor y a pagar
- Posición fiscal del tercero
- Categoría de producto/servicio
- AUTORETENCIÓN ICA
- AUTORETENCIÓN RENTA

Ciudades soportadas:
- Bogotá (Resolución SDH-000265)
- Barranquilla (Resolución DSH 001/2024)
- Medellín (Acuerdo 066/2017)
- Cartagena (Decreto 0810/2023)
- Cali (Acuerdo 0439/2017)
"""
import sys
import os
import subprocess
from datetime import datetime, date
from collections import defaultdict
from decimal import Decimal

# Agregar path de Odoo
sys.path.insert(0, '/var/odoo/bohio/src')
os.chdir('/var/odoo/bohio')

import odoo
from odoo import api, SUPERUSER_ID

# Configuración
DB_NAME = 'bohio'
CONFIG_FILE = '/var/odoo/bohio/odoo.conf'
OUTPUT_DIR = '/tmp/tax_reports'

# ============================================================================
# CUENTAS PUC COLOMBIA - Ingresos y Gastos relacionados con ICA
# ============================================================================
CUENTAS_ICA = {
    # Ingresos operacionales afectos a ICA
    'ingresos': {
        '4135': 'Comercio al por mayor y por menor',
        '4140': 'Hoteles, restaurantes, bares',
        '4145': 'Transporte, almacenamiento, comunicaciones',
        '4155': 'Actividades inmobiliarias, empresariales y de alquiler',
        '4160': 'Construcción',
        '4165': 'Financieros',
        '4170': 'Servicios',
        '4175': 'Devoluciones, rebajas y descuentos en ventas',
    },
    # Cuentas de impuestos
    'impuestos': {
        '2368': 'Impuesto de industria y comercio retenido',
        '236805': 'Industria y comercio retenido',
        '2412': 'ICA por pagar',
        '241205': 'Impuesto industria y comercio',
        '1355': 'Anticipo de impuestos - ReteICA',
        '135530': 'Retención industria y comercio',
    },
    # Saldos a favor
    'saldo_favor': {
        '135595': 'Otros anticipos impuestos',
        '135599': 'Ajustes por inflación',
    }
}

# Posiciones fiscales por tipo de régimen
POSICION_FISCAL = {
    'responsable_iva': {
        'nombre': 'Responsable de IVA',
        'aplica_reteica': True,
        'codigo': '01',
    },
    'no_responsable_iva': {
        'nombre': 'No Responsable de IVA',
        'aplica_reteica': True,
        'codigo': '02',
    },
    'regimen_simple': {
        'nombre': 'Régimen Simple de Tributación',
        'aplica_reteica': False,  # SIMPLE no le aplican retenciones
        'codigo': '03',
    },
    'gran_contribuyente': {
        'nombre': 'Gran Contribuyente',
        'aplica_reteica': True,
        'codigo': '04',
    },
    'autorretenedor': {
        'nombre': 'Autorretenedor de ICA',
        'aplica_reteica': False,  # Se autoretiene
        'codigo': '05',
    },
}

# Categorías de productos/servicios para ICA
CATEGORIAS_ICA = {
    'industrial': {
        'nombre': 'Actividades Industriales',
        'descripcion': 'Producción, fabricación, transformación de bienes',
        'cuentas': ['4130', '4131', '4132', '4133', '4134'],
    },
    'comercial': {
        'nombre': 'Actividades Comerciales',
        'descripcion': 'Compra y venta de bienes',
        'cuentas': ['4135', '4136', '4137', '4138', '4139'],
    },
    'servicios': {
        'nombre': 'Actividades de Servicios',
        'descripcion': 'Prestación de servicios',
        'cuentas': ['4140', '4145', '4155', '4160', '4165', '4170'],
    },
    'financiero': {
        'nombre': 'Sector Financiero',
        'descripcion': 'Servicios bancarios y financieros',
        'cuentas': ['4165'],
    },
}

# Tarifas por ciudad (por mil)
TARIFAS_CIUDAD = {
    'BOG': {
        'nombre': 'Bogotá D.C.',
        'normativa': 'Resolución SDH-000265, Acuerdo 780/2020',
        'industrial': {'min': 4.14, 'max': 11.04, 'comun': 6.90},
        'comercial': {'min': 4.14, 'max': 11.04, 'comun': 6.90},
        'servicios': {'min': 4.14, 'max': 11.04, 'comun': 9.66},
        'financiero': {'min': 11.04, 'max': 14.00, 'comun': 11.04},
        'base_min_uvt': {'servicios': 4, 'compras': 27},
    },
    'BAQ': {
        'nombre': 'Barranquilla',
        'normativa': 'Decreto 0119/2019, Resolución DSH 001/2024',
        'industrial': {'min': 7.40, 'max': 11.00, 'comun': 8.00},
        'comercial': {'min': 5.40, 'max': 12.50, 'comun': 10.00},
        'servicios': {'min': 4.50, 'max': 20.00, 'comun': 11.60},
        'financiero': {'min': 12.50, 'max': 30.00, 'comun': 30.00},
        'base_min_uvt': {'servicios': 4, 'compras': 27},
    },
    'MDE': {
        'nombre': 'Medellín',
        'normativa': 'Acuerdo 066/2017, Acuerdo 040/2021',
        'industrial': {'min': 2.00, 'max': 7.00, 'comun': 4.00},
        'comercial': {'min': 2.00, 'max': 10.00, 'comun': 5.00},
        'servicios': {'min': 2.00, 'max': 10.00, 'comun': 5.00},
        'financiero': {'min': 3.00, 'max': 5.00, 'comun': 5.00},
        'base_min_uvt': {'servicios': 15, 'compras': 15},
        'reteica_unica': 2.0,  # Tarifa única de retención
    },
    'CTG': {
        'nombre': 'Cartagena',
        'normativa': 'Decreto 0810/2023',
        'industrial': {'min': 4.00, 'max': 10.00, 'comun': 7.00},
        'comercial': {'min': 4.00, 'max': 10.00, 'comun': 7.00},
        'servicios': {'min': 7.00, 'max': 10.00, 'comun': 8.00},
        'financiero': {'min': 15.00, 'max': 15.00, 'comun': 15.00},
        'base_min_uvt': {'servicios': 4, 'compras': 27},
    },
    'CLO': {
        'nombre': 'Cali',
        'normativa': 'Acuerdo 0439/2017',
        'industrial': {'min': 2.00, 'max': 7.00, 'comun': 5.00},
        'comercial': {'min': 3.00, 'max': 10.00, 'comun': 6.00},
        'servicios': {'min': 3.00, 'max': 10.00, 'comun': 7.00},
        'financiero': {'min': 11.00, 'max': 11.00, 'comun': 11.00},
        'base_min_uvt': {'servicios': 3, 'compras': 15},
    },
}

# Valor UVT 2025
UVT_2025 = 49799

# ============================================================================
# TARIFAS DE AUTORETENCIÓN
# ============================================================================
AUTORRET_ICA = {
    'BOG': {
        'tasa': 11.04,  # Por mil - tarifa máxima
        'normativa': 'Acuerdo 780/2020, Art. 2',
        'base_min_uvt': 4,
    },
    'BAQ': {
        'tasa': 10.0,  # Por mil
        'normativa': 'Decreto 0119/2019',
        'base_min_uvt': 0,
    },
    'MDE': {
        'tasa': 5.0,  # Por mil
        'normativa': 'Acuerdo 040/2021',
        'base_min_uvt': 0,
    },
    'CTG': {
        'tasa': 8.0,  # Por mil
        'normativa': 'Decreto 0810/2023',
        'base_min_uvt': 4,
    },
    'CLO': {
        'tasa': 7.0,  # Por mil
        'normativa': 'Acuerdo 0439/2017',
        'base_min_uvt': 3,
    },
}

AUTORRET_RENTA = {
    'gran_contribuyente': {
        'tasa': 0.4,  # Porcentaje
        'normativa': 'Art. 365 E.T., Decreto 2201/2016',
    },
    'autorretenedor': {
        'tasa': 1.6,  # Porcentaje
        'normativa': 'Art. 365 E.T.',
    },
    'servicios': {
        'tasa': 0.8,  # Porcentaje para servicios profesionales
        'normativa': 'Art. 392 E.T.',
    },
}


def format_money(value, show_decimals=True):
    """Formatear valor monetario colombiano"""
    if value is None or value == 0:
        return "0"
    try:
        if show_decimals:
            return f"{value:,.0f}".replace(",", ".")
        else:
            return f"{int(value):,}".replace(",", ".")
    except:
        return str(value)


def get_ica_tax_data(env, date_from, date_to, company_id):
    """Obtener datos de impuestos ICA para el período"""
    query = """
        SELECT
            aml.id,
            aml.move_id,
            aml.account_id,
            aml.partner_id,
            aml.balance,
            aml.tax_base_amount,
            aml.tax_line_id,
            aml.product_id,
            am.name as move_name,
            am.date,
            am.move_type,
            at.id as tax_id,
            at.name::text as tax_name,
            at.amount as tax_rate,
            atg.name as tax_group_name,
            aa.code_store->>'1' as account_code,
            COALESCE(aa.name->>'es_CO', aa.name->>'en_US', '') as account_name,
            COALESCE(rp.name, '') as partner_name,
            COALESCE(rp.vat, '') as partner_vat,
            COALESCE(rp.is_company, false) as is_company,
            COALESCE(pt.name::text, '') as product_name,
            COALESCE(pc.name::text, '') as category_name
        FROM account_move_line aml
        JOIN account_move am ON am.id = aml.move_id
        LEFT JOIN account_tax at ON at.id = aml.tax_line_id
        LEFT JOIN account_tax_group atg ON atg.id = at.tax_group_id
        LEFT JOIN account_account aa ON aa.id = aml.account_id
        LEFT JOIN res_partner rp ON rp.id = aml.partner_id
        LEFT JOIN product_product pp ON pp.id = aml.product_id
        LEFT JOIN product_template pt ON pt.id = pp.product_tmpl_id
        LEFT JOIN product_category pc ON pc.id = pt.categ_id
        WHERE aml.tax_line_id IS NOT NULL
            AND am.date >= %s
            AND am.date <= %s
            AND am.company_id = %s
            AND am.state = 'posted'
            AND (
                UPPER(at.name::text) LIKE '%%ICA%%'
                OR UPPER(at.name::text) LIKE '%%INDUSTRIA%%'
                OR UPPER(atg.name::text) LIKE '%%ICA%%'
            )
        ORDER BY am.date, at.name::text
    """
    env.cr.execute(query, (date_from, date_to, company_id))
    return env.cr.dictfetchall()


def get_income_accounts(env, date_from, date_to, company_id):
    """Obtener cuentas de ingresos afectas a ICA"""
    query = """
        SELECT
            aa.code_store->>'1' as account_code,
            COALESCE(aa.name->>'es_CO', aa.name->>'en_US', '') as account_name,
            SUM(CASE WHEN aml.balance > 0 THEN aml.balance ELSE 0 END) as debitos,
            SUM(CASE WHEN aml.balance < 0 THEN ABS(aml.balance) ELSE 0 END) as creditos,
            SUM(aml.balance) as saldo
        FROM account_move_line aml
        JOIN account_move am ON am.id = aml.move_id
        JOIN account_account aa ON aa.id = aml.account_id
        WHERE am.date >= %s
            AND am.date <= %s
            AND am.company_id = %s
            AND am.state = 'posted'
            AND (aa.code_store->>'1') LIKE '41%%'
        GROUP BY aa.code_store->>'1', aa.name
        HAVING SUM(aml.balance) != 0
        ORDER BY aa.code_store->>'1'
    """
    env.cr.execute(query, (date_from, date_to, company_id))
    return env.cr.dictfetchall()


def calculate_self_withholding(income_data, city_code):
    """
    Calcular autoretenciones de ICA y Renta basado en ingresos.

    Returns:
        dict con:
        - base_ica: Base gravable para ICA
        - autorret_ica: Monto de autoretención ICA
        - tasa_ica: Tasa aplicada ICA (por mil)
        - base_renta: Base gravable para Renta
        - autorret_renta: Monto de autoretención Renta
        - tasa_renta: Tasa aplicada Renta (%)
    """
    # Total de ingresos operacionales
    total_ingresos = sum(abs(acc.get('saldo', 0)) for acc in income_data)

    # Autoretención ICA
    ica_config = AUTORRET_ICA.get(city_code, AUTORRET_ICA.get('BOG', {}))
    tasa_ica = ica_config.get('tasa', 0)
    base_min_uvt = ica_config.get('base_min_uvt', 0)
    base_min_ica = base_min_uvt * UVT_2025

    if total_ingresos >= base_min_ica:
        autorret_ica = total_ingresos * (tasa_ica / 1000)
    else:
        autorret_ica = 0

    # Autoretención Renta (usamos tasa de Gran Contribuyente por defecto)
    renta_config = AUTORRET_RENTA.get('gran_contribuyente', {})
    tasa_renta = renta_config.get('tasa', 0.4)
    autorret_renta = total_ingresos * (tasa_renta / 100)

    return {
        'base_ica': total_ingresos,
        'autorret_ica': autorret_ica,
        'tasa_ica': tasa_ica,
        'normativa_ica': ica_config.get('normativa', ''),
        'base_min_ica': base_min_ica,
        'base_renta': total_ingresos,
        'autorret_renta': autorret_renta,
        'tasa_renta': tasa_renta,
        'normativa_renta': renta_config.get('normativa', ''),
    }


def calculate_ica_by_city(tax_data):
    """Calcular ICA agrupado por ciudad"""
    result = defaultdict(lambda: {
        'ica_causado': 0,
        'reteica_practicado': 0,
        'reteica_que_nos_practican': 0,
        'base_gravable': 0,
        'detalle': [],
    })

    for row in tax_data:
        tax_name = str(row.get('tax_name') or '').upper()
        balance = float(row.get('balance') or 0)
        base = abs(float(row.get('tax_base_amount') or 0))
        move_type = str(row.get('move_type') or '')

        # Determinar ciudad del impuesto
        city_code = 'GEN'  # General/Otros
        for code in TARIFAS_CIUDAD.keys():
            if code in tax_name:
                city_code = code
                break

        # Clasificar según tipo de movimiento y signo
        if move_type in ('out_invoice', 'out_refund'):
            # Ventas - ICA causado o ReteICA que nos practican
            if balance < 0:
                result[city_code]['reteica_que_nos_practican'] += abs(balance)
            else:
                result[city_code]['ica_causado'] += balance
        else:
            # Compras - ReteICA practicado
            if balance < 0 or 'R.ICA' in tax_name or 'RETE' in tax_name:
                result[city_code]['reteica_practicado'] += abs(balance)

        result[city_code]['base_gravable'] += base
        result[city_code]['detalle'].append({
            'fecha': row.get('date'),
            'documento': row.get('move_name'),
            'tercero': row.get('partner_name'),
            'nit': row.get('partner_vat'),
            'base': base,
            'impuesto': balance,
            'producto': row.get('product_name'),
            'categoria': row.get('category_name'),
        })

    return dict(result)


def generate_ica_form_html(company, date_from, date_to, ica_data, income_data, city_code='BOG', self_withholding=None):
    """Generar formulario HTML de liquidación de ICA con autoretenciones"""

    city_info = TARIFAS_CIUDAD.get(city_code, TARIFAS_CIUDAD['BOG'])
    city_data = ica_data.get(city_code, {})

    # Calcular autoretenciones si no se proporcionan
    if self_withholding is None:
        self_withholding = calculate_self_withholding(income_data, city_code)

    base_gravable = city_data.get('base_gravable', 0)
    ica_causado = city_data.get('ica_causado', 0)
    reteica_practicado = city_data.get('reteica_practicado', 0)
    reteica_que_practican = city_data.get('reteica_que_nos_practican', 0)

    # Calcular saldo
    saldo_a_pagar = max(ica_causado - reteica_que_practican, 0)
    saldo_a_favor = max(reteica_que_practican - ica_causado, 0)

    # Calcular bases mínimas en pesos
    base_min_servicios = city_info['base_min_uvt']['servicios'] * UVT_2025
    base_min_compras = city_info['base_min_uvt']['compras'] * UVT_2025

    # Generar tabla de detalle por tercero
    detalle_html = ""
    terceros = defaultdict(lambda: {'base': 0, 'impuesto': 0, 'docs': []})

    for det in city_data.get('detalle', []):
        nit = det.get('nit') or 'SIN NIT'
        terceros[nit]['nombre'] = det.get('tercero', 'Desconocido')
        terceros[nit]['base'] += det.get('base', 0)
        terceros[nit]['impuesto'] += abs(det.get('impuesto', 0))
        terceros[nit]['docs'].append(det.get('documento', ''))

    for nit, info in sorted(terceros.items(), key=lambda x: -x[1]['base'])[:15]:
        tipo_persona = 'PJ' if len(nit) > 10 else 'PN'
        detalle_html += f"""
            <tr>
                <td>{nit}</td>
                <td>{info['nombre'][:40]}</td>
                <td style="text-align:center;">{tipo_persona}</td>
                <td class="valor">{format_money(info['base'])}</td>
                <td class="valor">{format_money(info['impuesto'])}</td>
            </tr>
        """

    # Generar tabla de cuentas de ingresos
    ingresos_html = ""
    total_ingresos = 0
    for acc in income_data[:10]:
        ingresos_html += f"""
            <tr>
                <td>{acc['account_code']}</td>
                <td>{acc['account_name']}</td>
                <td class="valor">{format_money(abs(acc['saldo']))}</td>
            </tr>
        """
        total_ingresos += abs(acc.get('saldo', 0))

    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Liquidación ICA - {city_info['nombre']}</title>
    <style>
        @page {{
            size: A4;
            margin: 0.5cm;
        }}
        body {{
            font-family: Arial, sans-serif;
            font-size: 9px;
            margin: 0;
            padding: 10px;
            background: #fff;
        }}
        .header {{
            background: linear-gradient(135deg, #2c2c2c, #4a4a4a);
            color: white;
            padding: 15px;
            text-align: center;
            margin-bottom: 10px;
        }}
        .header h1 {{
            margin: 0;
            font-size: 16px;
        }}
        .header h2 {{
            margin: 5px 0 0 0;
            font-size: 12px;
            font-weight: normal;
        }}
        .header .city {{
            font-size: 14px;
            font-weight: bold;
            margin-top: 5px;
        }}
        .company-info {{
            background: #f5f5f5;
            padding: 10px;
            margin-bottom: 10px;
            border: 1px solid #ccc;
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 5px;
        }}
        .company-info .item {{
            display: flex;
        }}
        .company-info .label {{
            font-weight: bold;
            width: 120px;
            font-size: 9px;
            color: #333;
        }}
        .company-info .value {{
            font-size: 9px;
            color: #555;
        }}
        .section {{
            margin-bottom: 10px;
        }}
        .section-title {{
            background: #4a4a4a;
            color: white;
            padding: 5px 10px;
            font-weight: bold;
            font-size: 10px;
            margin-bottom: 0;
        }}
        .section-title.ingresos {{ background: #555; }}
        .section-title.tarifas {{ background: #666; }}
        .section-title.liquidacion {{ background: #444; }}
        .section-title.terceros {{ background: #5a5a5a; }}
        table.form {{
            width: 100%;
            border-collapse: collapse;
        }}
        table.form th, table.form td {{
            border: 1px solid #ccc;
            padding: 4px 6px;
            font-size: 8px;
        }}
        table.form th {{
            background: #e8e8e8;
            font-weight: bold;
            text-align: left;
            color: #333;
        }}
        table.form .casilla {{
            width: 40px;
            text-align: center;
            background: #4a4a4a;
            color: white;
            font-weight: bold;
        }}
        table.form .valor {{
            text-align: right;
            font-family: 'Courier New', monospace;
            font-weight: bold;
        }}
        table.form .total-row {{
            background: #e0e0e0;
            font-weight: bold;
        }}
        table.form .pagar {{
            background: #d0d0d0;
            font-weight: bold;
            font-size: 10px;
        }}
        table.form .favor {{
            background: #e8e8e8;
            font-weight: bold;
            font-size: 10px;
        }}
        .tarifas-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 5px;
            padding: 10px;
            background: #f0f0f0;
            border: 1px solid #ccc;
        }}
        .tarifa-card {{
            background: white;
            padding: 8px;
            border-radius: 5px;
            text-align: center;
            border: 1px solid #ddd;
        }}
        .tarifa-card .tipo {{
            font-weight: bold;
            font-size: 9px;
            color: #333;
        }}
        .tarifa-card .rango {{
            font-size: 8px;
            color: #666;
        }}
        .tarifa-card .comun {{
            font-size: 12px;
            font-weight: bold;
            color: #333;
        }}
        .info-box {{
            background: #f5f5f5;
            border: 1px solid #ccc;
            padding: 8px;
            margin: 10px 0;
            font-size: 8px;
        }}
        .info-box .title {{
            font-weight: bold;
            color: #333;
        }}
        .footer {{
            margin-top: 15px;
            text-align: center;
            font-size: 8px;
            color: #888;
            border-top: 1px solid #ddd;
            padding-top: 10px;
        }}
        .two-columns {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>LIQUIDACIÓN IMPUESTO DE INDUSTRIA Y COMERCIO</h1>
        <h2>ICA - AVISOS Y TABLEROS</h2>
        <div class="city">{city_info['nombre'].upper()}</div>
    </div>

    <div class="company-info">
        <div class="item"><span class="label">Razón Social:</span><span class="value">{company.name}</span></div>
        <div class="item"><span class="label">NIT:</span><span class="value">{company.vat or 'N/A'}</span></div>
        <div class="item"><span class="label">Período:</span><span class="value">{date_from.strftime('%d/%m/%Y')} - {date_to.strftime('%d/%m/%Y')}</span></div>
        <div class="item"><span class="label">Normativa:</span><span class="value">{city_info['normativa']}</span></div>
    </div>

    <!-- TARIFAS VIGENTES -->
    <div class="section">
        <div class="section-title tarifas">TARIFAS VIGENTES POR ACTIVIDAD (por mil)</div>
        <div class="tarifas-grid">
            <div class="tarifa-card">
                <div class="tipo">INDUSTRIAL</div>
                <div class="rango">{city_info['industrial']['min']}‰ - {city_info['industrial']['max']}‰</div>
                <div class="comun">{city_info['industrial']['comun']}‰</div>
            </div>
            <div class="tarifa-card">
                <div class="tipo">COMERCIAL</div>
                <div class="rango">{city_info['comercial']['min']}‰ - {city_info['comercial']['max']}‰</div>
                <div class="comun">{city_info['comercial']['comun']}‰</div>
            </div>
            <div class="tarifa-card">
                <div class="tipo">SERVICIOS</div>
                <div class="rango">{city_info['servicios']['min']}‰ - {city_info['servicios']['max']}‰</div>
                <div class="comun">{city_info['servicios']['comun']}‰</div>
            </div>
            <div class="tarifa-card">
                <div class="tipo">FINANCIERO</div>
                <div class="rango">{city_info['financiero']['min']}‰ - {city_info['financiero']['max']}‰</div>
                <div class="comun">{city_info['financiero']['comun']}‰</div>
            </div>
        </div>
    </div>

    <div class="info-box">
        <span class="title">Bases mínimas de retención:</span>
        Servicios: {city_info['base_min_uvt']['servicios']} UVT (${format_money(base_min_servicios)}) |
        Compras: {city_info['base_min_uvt']['compras']} UVT (${format_money(base_min_compras)}) |
        UVT 2025: ${format_money(UVT_2025)}
    </div>

    <div class="two-columns">
        <!-- CUENTAS DE INGRESOS -->
        <div class="section">
            <div class="section-title ingresos">CUENTAS DE INGRESOS AFECTAS</div>
            <table class="form">
                <tr>
                    <th style="width:60px;">Cuenta</th>
                    <th>Nombre</th>
                    <th class="valor" style="width:100px;">Saldo</th>
                </tr>
                {ingresos_html}
                <tr class="total-row">
                    <td colspan="2"><strong>TOTAL INGRESOS OPERACIONALES</strong></td>
                    <td class="valor">{format_money(total_ingresos)}</td>
                </tr>
            </table>
        </div>

        <!-- LIQUIDACIÓN -->
        <div class="section">
            <div class="section-title liquidacion">LIQUIDACIÓN DEL IMPUESTO</div>
            <table class="form">
                <tr>
                    <th class="casilla">Cas.</th>
                    <th>Concepto</th>
                    <th class="valor" style="width:100px;">Valor ($)</th>
                </tr>
                <tr>
                    <td class="casilla">1</td>
                    <td>Base gravable del período</td>
                    <td class="valor">{format_money(base_gravable)}</td>
                </tr>
                <tr>
                    <td class="casilla">2</td>
                    <td>ICA causado</td>
                    <td class="valor">{format_money(ica_causado)}</td>
                </tr>
                <tr>
                    <td class="casilla">3</td>
                    <td>Avisos y tableros (15%)</td>
                    <td class="valor">{format_money(ica_causado * 0.15)}</td>
                </tr>
                <tr>
                    <td class="casilla">4</td>
                    <td>ReteICA practicado (a terceros)</td>
                    <td class="valor">{format_money(reteica_practicado)}</td>
                </tr>
                <tr>
                    <td class="casilla">5</td>
                    <td>ReteICA que nos practican</td>
                    <td class="valor">{format_money(reteica_que_practican)}</td>
                </tr>
                <tr class="pagar">
                    <td class="casilla">6</td>
                    <td><strong>SALDO A PAGAR</strong></td>
                    <td class="valor">{format_money(saldo_a_pagar)}</td>
                </tr>
                <tr class="favor">
                    <td class="casilla">7</td>
                    <td><strong>SALDO A FAVOR</strong></td>
                    <td class="valor">{format_money(saldo_a_favor)}</td>
                </tr>
            </table>
        </div>
    </div>

    <!-- AUTORETENCIONES -->
    <div class="section">
        <div class="section-title" style="background:#333;">AUTORETENCIONES (Calculadas sobre Ingresos)</div>
        <table class="form">
            <tr>
                <th class="casilla">Cas.</th>
                <th>Concepto</th>
                <th style="width:80px;text-align:center;">Tasa</th>
                <th class="valor" style="width:100px;">Base ($)</th>
                <th class="valor" style="width:100px;">Valor ($)</th>
            </tr>
            <tr>
                <td class="casilla">A1</td>
                <td>Autoretención ICA ({self_withholding['normativa_ica']})</td>
                <td style="text-align:center;">{self_withholding['tasa_ica']}‰</td>
                <td class="valor">{format_money(self_withholding['base_ica'])}</td>
                <td class="valor">{format_money(self_withholding['autorret_ica'])}</td>
            </tr>
            <tr>
                <td class="casilla">A2</td>
                <td>Autoretención Renta ({self_withholding['normativa_renta']})</td>
                <td style="text-align:center;">{self_withholding['tasa_renta']}%</td>
                <td class="valor">{format_money(self_withholding['base_renta'])}</td>
                <td class="valor">{format_money(self_withholding['autorret_renta'])}</td>
            </tr>
            <tr class="total-row">
                <td class="casilla">A3</td>
                <td colspan="3"><strong>TOTAL AUTORETENCIONES</strong></td>
                <td class="valor"><strong>{format_money(self_withholding['autorret_ica'] + self_withholding['autorret_renta'])}</strong></td>
            </tr>
        </table>
        <div style="font-size:7px;color:#666;margin-top:3px;">
            <strong>Nota:</strong> Las autoretenciones se calculan sobre el total de ingresos operacionales del período.
            ICA: Cuenta 236805/241205 | Renta: Cuenta 236515
        </div>
    </div>

    <!-- DETALLE POR TERCEROS -->
    <div class="section">
        <div class="section-title terceros">DETALLE POR TERCEROS - POSICIÓN FISCAL</div>
        <table class="form">
            <tr>
                <th style="width:80px;">NIT/CC</th>
                <th>Tercero</th>
                <th style="width:40px;text-align:center;">Tipo</th>
                <th class="valor" style="width:100px;">Base</th>
                <th class="valor" style="width:80px;">Retención</th>
            </tr>
            {detalle_html if detalle_html else '<tr><td colspan="5" style="text-align:center;">Sin movimientos de ICA en el período</td></tr>'}
        </table>
        <div style="font-size:7px;color:#7f8c8d;margin-top:3px;">
            PJ = Persona Jurídica | PN = Persona Natural | Se muestran los 15 principales por base gravable
        </div>
    </div>

    <!-- CUENTAS CONTABLES ICA -->
    <div class="info-box">
        <span class="title">Cuentas contables aplicables:</span><br>
        <strong>2368/236805:</strong> ICA retenido por pagar |
        <strong>2412/241205:</strong> ICA por pagar |
        <strong>1355/135530:</strong> ReteICA a favor (anticipo)
    </div>

    <div class="footer">
        Documento generado el {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} | {company.name} | Sistema de Reportes Fiscales Colombia
        <br>Este documento es un borrador para revisión interna. La declaración oficial debe presentarse en la plataforma de la secretaría de hacienda municipal.
    </div>
</body>
</html>'''

    return html


def html_to_pdf(html_content, output_path):
    """Convertir HTML a PDF usando wkhtmltopdf"""
    html_path = output_path.replace('.pdf', '.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    cmd = [
        '/usr/local/bin/wkhtmltopdf',
        '--orientation', 'Portrait',
        '--page-size', 'A4',
        '--margin-top', '5mm',
        '--margin-bottom', '5mm',
        '--margin-left', '5mm',
        '--margin-right', '5mm',
        '--encoding', 'UTF-8',
        '--enable-local-file-access',
        '--quiet',
        html_path,
        output_path
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        os.remove(html_path)
        if result.returncode == 0:
            return True, os.path.getsize(output_path)
        return False, result.stderr
    except Exception as e:
        return False, str(e)


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    odoo.tools.config.parse_config(['--config', CONFIG_FILE])

    with odoo.registry(DB_NAME).cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})

        print("=" * 70)
        print("GENERACIÓN DE LIQUIDACIONES ICA - CIUDADES PRINCIPALES")
        print("=" * 70)

        today = date.today()
        date_from = today.replace(day=1)
        date_to = today

        company = env.company

        print(f"\nEmpresa: {company.name}")
        print(f"NIT: {company.vat}")
        print(f"Período: {date_from.strftime('%d/%m/%Y')} - {date_to.strftime('%d/%m/%Y')}")

        # Obtener datos
        print("\n1. Obteniendo datos de ICA...")
        ica_data = get_ica_tax_data(env, date_from, date_to, company.id)
        print(f"   Registros ICA encontrados: {len(ica_data)}")

        print("\n2. Obteniendo cuentas de ingresos...")
        income_data = get_income_accounts(env, date_from, date_to, company.id)
        print(f"   Cuentas de ingresos: {len(income_data)}")

        # Calcular por ciudad
        ica_by_city = calculate_ica_by_city(ica_data)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        print("\n3. Generando formularios por ciudad...")
        for city_code, city_info in TARIFAS_CIUDAD.items():
            print(f"\n   → {city_info['nombre']}...")

            # Calcular autoretenciones
            self_withholding = calculate_self_withholding(income_data, city_code)

            html = generate_ica_form_html(
                company, date_from, date_to,
                ica_by_city, income_data, city_code,
                self_withholding=self_withholding
            )

            pdf_path = os.path.join(OUTPUT_DIR, f"liquidacion_ica_{city_code.lower()}_{timestamp}.pdf")
            success, result = html_to_pdf(html, pdf_path)

            if success:
                city_data = ica_by_city.get(city_code, {})
                print(f"      ✓ PDF: {pdf_path}")
                print(f"        Base gravable: ${format_money(city_data.get('base_gravable', 0))}")
                print(f"        ICA causado: ${format_money(city_data.get('ica_causado', 0))}")
                print(f"        Autorret. ICA: ${format_money(self_withholding['autorret_ica'])}")
                print(f"        Autorret. Renta: ${format_money(self_withholding['autorret_renta'])}")
            else:
                print(f"      ✗ Error: {result}")

        print("\n" + "=" * 70)
        print("LIQUIDACIONES ICA GENERADAS")
        print("=" * 70)
        print(f"\nArchivos en: {OUTPUT_DIR}")

        for f in sorted(os.listdir(OUTPUT_DIR)):
            if 'ica' in f.lower() and f.endswith('.pdf'):
                size = os.path.getsize(os.path.join(OUTPUT_DIR, f))
                print(f"  - {f} ({size:,} bytes)")


if __name__ == '__main__':
    main()
