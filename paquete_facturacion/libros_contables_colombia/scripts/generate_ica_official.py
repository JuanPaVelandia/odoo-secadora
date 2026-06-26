#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para generar formularios ICA con formato oficial municipal.

Genera formularios estilo oficial con:
- Estructura de renglones numerados (estilo DIAN/Municipal)
- Casillas de validación
- Sección de autoretenciones
- Separación PJ/PN en retenciones
- Auxiliar con datos usados

Basado en formatos municipales de:
- Bogotá (SHD)
- Barranquilla (DSH)
- Medellín (SHM)
"""
import sys
import os
import subprocess
from datetime import datetime, date
from collections import defaultdict

# Agregar path de Odoo
sys.path.insert(0, '/var/odoo/bohio/src')
os.chdir('/var/odoo/bohio')

import odoo
from odoo import api, SUPERUSER_ID

# Configuración
DB_NAME = 'bohio'
CONFIG_FILE = '/var/odoo/bohio/odoo.conf'
OUTPUT_DIR = '/tmp/tax_reports'

# Valor UVT 2025
UVT_2025 = 49799

# Configuración por ciudad
CITY_CONFIG = {
    'BOG': {
        'nombre': 'BOGOTÁ D.C.',
        'logo': 'escudo_bogota.png',
        'entidad': 'SECRETARÍA DISTRITAL DE HACIENDA',
        'formulario': 'FORMULARIO IBI - INDUSTRIA, COMERCIO, AVISOS Y TABLEROS',
        'codigo_form': 'SDH-ICA-2025',
        'normativa': 'Acuerdo 780/2020, Resolución SDH-000265',
        'tarifas': {
            'industrial': {'min': 4.14, 'max': 11.04, 'comun': 6.90},
            'comercial': {'min': 4.14, 'max': 11.04, 'comun': 6.90},
            'servicios': {'min': 4.14, 'max': 13.80, 'comun': 9.66},
            'financiero': {'min': 11.04, 'max': 14.00, 'comun': 11.04},
        },
        'avisos_tableros': 15.0,  # % sobre ICA
        'autorret_ica': 11.04,  # Por mil
        'autorret_renta': 0.4,  # %
        'base_min_uvt': {'servicios': 4, 'compras': 27},
    },
    'BAQ': {
        'nombre': 'BARRANQUILLA',
        'logo': 'escudo_barranquilla.png',
        'entidad': 'DISTRITO ESPECIAL - SECRETARÍA DE HACIENDA',
        'formulario': 'DECLARACIÓN IMPUESTO DE INDUSTRIA Y COMERCIO',
        'codigo_form': 'DSH-ICA-2025',
        'normativa': 'Decreto 0119/2019, Resolución DSH 001/2024',
        'tarifas': {
            'industrial': {'min': 7.40, 'max': 11.00, 'comun': 8.00},
            'comercial': {'min': 5.40, 'max': 12.50, 'comun': 10.00},
            'servicios': {'min': 4.50, 'max': 20.00, 'comun': 11.60},
            'financiero': {'min': 12.50, 'max': 30.00, 'comun': 30.00},
        },
        'avisos_tableros': 15.0,
        'autorret_ica': 10.0,
        'autorret_renta': 0.4,
        'base_min_uvt': {'servicios': 4, 'compras': 27},
    },
    'MDE': {
        'nombre': 'MEDELLÍN',
        'logo': 'escudo_medellin.png',
        'entidad': 'ALCALDÍA DE MEDELLÍN - SECRETARÍA DE HACIENDA',
        'formulario': 'DECLARACIÓN DE INDUSTRIA Y COMERCIO',
        'codigo_form': 'SHM-ICA-2025',
        'normativa': 'Acuerdo 066/2017, Acuerdo 040/2021',
        'tarifas': {
            'industrial': {'min': 2.00, 'max': 7.00, 'comun': 4.00},
            'comercial': {'min': 2.00, 'max': 10.00, 'comun': 5.00},
            'servicios': {'min': 2.00, 'max': 10.00, 'comun': 5.00},
            'financiero': {'min': 3.00, 'max': 5.00, 'comun': 5.00},
        },
        'avisos_tableros': 15.0,
        'autorret_ica': 5.0,  # Medellín tiene tarifa única
        'autorret_renta': 0.4,
        'base_min_uvt': {'servicios': 15, 'compras': 15},
    },
    'CTG': {
        'nombre': 'CARTAGENA DE INDIAS',
        'logo': 'escudo_cartagena.png',
        'entidad': 'DISTRITO TURÍSTICO - SECRETARÍA DE HACIENDA',
        'formulario': 'DECLARACIÓN DE INDUSTRIA Y COMERCIO',
        'codigo_form': 'SHC-ICA-2025',
        'normativa': 'Decreto 0810/2023',
        'tarifas': {
            'industrial': {'min': 4.00, 'max': 10.00, 'comun': 7.00},
            'comercial': {'min': 4.00, 'max': 10.00, 'comun': 7.00},
            'servicios': {'min': 7.00, 'max': 10.00, 'comun': 8.00},
            'financiero': {'min': 15.00, 'max': 15.00, 'comun': 15.00},
        },
        'avisos_tableros': 15.0,
        'autorret_ica': 8.0,
        'autorret_renta': 0.4,
        'base_min_uvt': {'servicios': 4, 'compras': 27},
    },
    'CLO': {
        'nombre': 'SANTIAGO DE CALI',
        'logo': 'escudo_cali.png',
        'entidad': 'ALCALDÍA DE CALI - DEPARTAMENTO DE HACIENDA',
        'formulario': 'DECLARACIÓN DE INDUSTRIA Y COMERCIO Y AVISOS',
        'codigo_form': 'DHC-ICA-2025',
        'normativa': 'Acuerdo 0439/2017',
        'tarifas': {
            'industrial': {'min': 2.00, 'max': 7.00, 'comun': 5.00},
            'comercial': {'min': 3.00, 'max': 10.00, 'comun': 6.00},
            'servicios': {'min': 3.00, 'max': 10.00, 'comun': 7.00},
            'financiero': {'min': 11.00, 'max': 11.00, 'comun': 11.00},
        },
        'avisos_tableros': 15.0,
        'autorret_ica': 7.0,
        'autorret_renta': 0.4,
        'base_min_uvt': {'servicios': 3, 'compras': 15},
    },
    'GEN': {
        'nombre': 'GENÉRICO COLOMBIA',
        'logo': 'escudo_colombia.png',
        'entidad': 'SECRETARÍA DE HACIENDA MUNICIPAL',
        'formulario': 'DECLARACIÓN DE INDUSTRIA Y COMERCIO',
        'codigo_form': 'ICA-GEN-2025',
        'normativa': 'Ley 14/1983, Ley 1819/2016',
        'tarifas': {
            'industrial': {'min': 2.00, 'max': 7.00, 'comun': 5.00},
            'comercial': {'min': 2.00, 'max': 10.00, 'comun': 6.00},
            'servicios': {'min': 2.00, 'max': 10.00, 'comun': 7.00},
            'financiero': {'min': 3.00, 'max': 15.00, 'comun': 10.00},
        },
        'avisos_tableros': 15.0,
        'autorret_ica': 7.0,
        'autorret_renta': 0.4,
        'base_min_uvt': {'servicios': 4, 'compras': 27},
    },
}


def format_money(value):
    """Formatear valor monetario colombiano"""
    if value is None:
        return "0"
    try:
        return f"{value:,.0f}".replace(",", ".")
    except:
        return str(value)


def get_ica_data(env, date_from, date_to, company_id):
    """Obtener datos de ICA del período"""
    query = """
        SELECT
            aml.id,
            aml.move_id,
            aml.partner_id,
            aml.balance,
            aml.tax_base_amount,
            am.name as move_name,
            am.date,
            am.move_type,
            at.name::text as tax_name,
            at.amount as tax_rate,
            COALESCE(rp.name, '') as partner_name,
            COALESCE(rp.vat, '') as partner_vat,
            COALESCE(rp.is_company, false) as is_company
        FROM account_move_line aml
        JOIN account_move am ON am.id = aml.move_id
        LEFT JOIN account_tax at ON at.id = aml.tax_line_id
        LEFT JOIN res_partner rp ON rp.id = aml.partner_id
        WHERE aml.tax_line_id IS NOT NULL
            AND am.date >= %s
            AND am.date <= %s
            AND am.company_id = %s
            AND am.state = 'posted'
            AND (
                UPPER(at.name::text) LIKE '%%ICA%%'
                OR UPPER(at.name::text) LIKE '%%INDUSTRIA%%'
            )
        ORDER BY am.date
    """
    env.cr.execute(query, (date_from, date_to, company_id))
    return env.cr.dictfetchall()


def get_income_data(env, date_from, date_to, company_id):
    """Obtener ingresos operacionales"""
    query = """
        SELECT
            aa.code_store->>'1' as account_code,
            COALESCE(aa.name->>'es_CO', aa.name->>'en_US', '') as account_name,
            SUM(CASE WHEN aml.balance < 0 THEN ABS(aml.balance) ELSE 0 END) as creditos
        FROM account_move_line aml
        JOIN account_move am ON am.id = aml.move_id
        JOIN account_account aa ON aa.id = aml.account_id
        WHERE am.date >= %s
            AND am.date <= %s
            AND am.company_id = %s
            AND am.state = 'posted'
            AND (aa.code_store->>'1') LIKE '41%%'
        GROUP BY aa.code_store->>'1', aa.name
        HAVING SUM(CASE WHEN aml.balance < 0 THEN ABS(aml.balance) ELSE 0 END) > 0
        ORDER BY aa.code_store->>'1'
    """
    env.cr.execute(query, (date_from, date_to, company_id))
    return env.cr.dictfetchall()


def process_ica_data(ica_data, city_code):
    """Procesar datos de ICA separando PJ y PN"""
    result = {
        'ica_causado': 0,
        'reteica_pj': 0,  # Retención a Personas Jurídicas
        'reteica_pn': 0,  # Retención a Personas Naturales
        'reteica_que_practican': 0,
        'base_gravable': 0,
        'terceros_pj': [],
        'terceros_pn': [],
    }

    terceros_pj = defaultdict(lambda: {'base': 0, 'retencion': 0, 'nombre': ''})
    terceros_pn = defaultdict(lambda: {'base': 0, 'retencion': 0, 'nombre': ''})

    for row in ica_data:
        tax_name = str(row.get('tax_name') or '').upper()
        balance = float(row.get('balance') or 0)
        base = abs(float(row.get('tax_base_amount') or 0))
        move_type = str(row.get('move_type') or '')
        is_company = row.get('is_company', False)
        nit = row.get('partner_vat') or 'SIN NIT'
        nombre = row.get('partner_name') or 'Desconocido'

        # Verificar si es de la ciudad
        if city_code != 'GEN' and city_code not in tax_name:
            continue

        if move_type in ('out_invoice', 'out_refund'):
            # Ventas
            if balance < 0:
                result['reteica_que_practican'] += abs(balance)
            else:
                result['ica_causado'] += balance
        else:
            # Compras - ReteICA practicado
            if balance < 0 or 'R.ICA' in tax_name or 'RETE' in tax_name:
                retencion = abs(balance)
                if is_company:
                    result['reteica_pj'] += retencion
                    terceros_pj[nit]['base'] += base
                    terceros_pj[nit]['retencion'] += retencion
                    terceros_pj[nit]['nombre'] = nombre
                else:
                    result['reteica_pn'] += retencion
                    terceros_pn[nit]['base'] += base
                    terceros_pn[nit]['retencion'] += retencion
                    terceros_pn[nit]['nombre'] = nombre

        result['base_gravable'] += base

    # Convertir a listas ordenadas
    result['terceros_pj'] = sorted(
        [{'nit': k, **v} for k, v in terceros_pj.items()],
        key=lambda x: -x['base']
    )[:10]
    result['terceros_pn'] = sorted(
        [{'nit': k, **v} for k, v in terceros_pn.items()],
        key=lambda x: -x['base']
    )[:10]

    return result


def generate_official_form_html(company, date_from, date_to, ica_result, income_data, city_code='GEN'):
    """Generar formulario HTML con formato oficial municipal"""

    config = CITY_CONFIG.get(city_code, CITY_CONFIG['GEN'])

    # Totales de ingresos
    total_ingresos = sum(acc.get('creditos', 0) for acc in income_data)

    # Calcular autoretenciones
    autorret_ica = total_ingresos * (config['autorret_ica'] / 1000)
    autorret_renta = total_ingresos * (config['autorret_renta'] / 100)

    # Calcular liquidación
    ica_causado = ica_result.get('ica_causado', 0)
    avisos_tableros = ica_causado * (config['avisos_tableros'] / 100)
    total_ica = ica_causado + avisos_tableros
    reteica_practicado = ica_result.get('reteica_pj', 0) + ica_result.get('reteica_pn', 0)
    reteica_que_practican = ica_result.get('reteica_que_practican', 0)
    saldo_a_pagar = max(total_ica - reteica_que_practican - autorret_ica, 0)
    saldo_a_favor = max(reteica_que_practican + autorret_ica - total_ica, 0)

    # Generar HTML de ingresos
    ingresos_html = ""
    for idx, acc in enumerate(income_data[:8], start=1):
        ingresos_html += f"""
        <tr>
            <td class="renglon">{30 + idx}</td>
            <td>{acc['account_code']} - {acc['account_name'][:35]}</td>
            <td class="valor">{format_money(acc['creditos'])}</td>
        </tr>
        """

    # Generar HTML de terceros PJ
    terceros_pj_html = ""
    for t in ica_result.get('terceros_pj', [])[:5]:
        terceros_pj_html += f"""
        <tr>
            <td>{t['nit']}</td>
            <td>{t['nombre'][:30]}</td>
            <td class="valor">{format_money(t['base'])}</td>
            <td class="valor">{format_money(t['retencion'])}</td>
        </tr>
        """

    # Generar HTML de terceros PN
    terceros_pn_html = ""
    for t in ica_result.get('terceros_pn', [])[:5]:
        terceros_pn_html += f"""
        <tr>
            <td>{t['nit']}</td>
            <td>{t['nombre'][:30]}</td>
            <td class="valor">{format_money(t['base'])}</td>
            <td class="valor">{format_money(t['retencion'])}</td>
        </tr>
        """

    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{config['formulario']}</title>
    <style>
        @page {{
            size: A4;
            margin: 5mm;
        }}
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: Arial, Helvetica, sans-serif;
            font-size: 8px;
            background: white;
            color: #1a1a1a;
        }}

        /* ENCABEZADO OFICIAL */
        .header-oficial {{
            border: 2px solid #333;
            margin-bottom: 3px;
        }}
        .header-top {{
            display: flex;
            background: #f0f0f0;
            border-bottom: 1px solid #333;
        }}
        .header-logo {{
            width: 80px;
            padding: 5px;
            border-right: 1px solid #333;
            text-align: center;
        }}
        .header-logo .escudo {{
            font-size: 24px;
            line-height: 1;
        }}
        .header-title {{
            flex: 1;
            padding: 5px 10px;
            text-align: center;
        }}
        .header-title h1 {{
            font-size: 11px;
            margin-bottom: 2px;
            letter-spacing: 1px;
        }}
        .header-title h2 {{
            font-size: 9px;
            font-weight: normal;
            color: #444;
        }}
        .header-code {{
            width: 100px;
            padding: 5px;
            border-left: 1px solid #333;
            text-align: center;
            font-size: 7px;
        }}
        .header-code .codigo {{
            font-size: 10px;
            font-weight: bold;
            color: #333;
        }}

        /* INFO CONTRIBUYENTE */
        .contribuyente {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            border: 1px solid #333;
            margin-bottom: 3px;
            font-size: 7px;
        }}
        .contribuyente .campo {{
            padding: 3px 5px;
            border-right: 1px solid #ccc;
            border-bottom: 1px solid #ccc;
        }}
        .contribuyente .campo:nth-child(4n) {{
            border-right: none;
        }}
        .contribuyente .label {{
            font-weight: bold;
            color: #555;
            display: block;
            font-size: 6px;
        }}
        .contribuyente .value {{
            font-weight: bold;
            color: #1a1a1a;
        }}

        /* SECCIONES */
        .seccion {{
            border: 1px solid #333;
            margin-bottom: 3px;
        }}
        .seccion-title {{
            background: #444;
            color: white;
            padding: 3px 8px;
            font-weight: bold;
            font-size: 8px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .seccion-content {{
            padding: 0;
        }}

        /* TABLA DE RENGLONES */
        table.renglones {{
            width: 100%;
            border-collapse: collapse;
        }}
        table.renglones th {{
            background: #e0e0e0;
            padding: 2px 4px;
            text-align: left;
            font-size: 7px;
            border-bottom: 1px solid #999;
        }}
        table.renglones td {{
            padding: 2px 4px;
            border-bottom: 1px solid #ddd;
            font-size: 7px;
        }}
        table.renglones .renglon {{
            width: 30px;
            text-align: center;
            background: #444;
            color: white;
            font-weight: bold;
        }}
        table.renglones .valor {{
            text-align: right;
            font-family: 'Courier New', monospace;
            font-weight: bold;
            width: 90px;
        }}
        table.renglones .total {{
            background: #f0f0f0;
            font-weight: bold;
        }}
        table.renglones .pagar {{
            background: #d0d0d0;
            font-weight: bold;
            font-size: 8px;
        }}
        table.renglones .favor {{
            background: #e8e8e8;
            font-weight: bold;
            font-size: 8px;
        }}

        /* COLUMNAS */
        .dos-columnas {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 3px;
        }}

        /* TERCEROS */
        table.terceros {{
            width: 100%;
            border-collapse: collapse;
            font-size: 7px;
        }}
        table.terceros th {{
            background: #555;
            color: white;
            padding: 2px 4px;
            text-align: left;
        }}
        table.terceros td {{
            padding: 2px 4px;
            border-bottom: 1px solid #eee;
        }}
        table.terceros .valor {{
            text-align: right;
            font-family: monospace;
        }}

        /* AUTORETENCIONES */
        .autorret {{
            background: #f5f5f5;
        }}
        .autorret .seccion-title {{
            background: #333;
        }}

        /* PIE */
        .footer {{
            margin-top: 5px;
            padding-top: 5px;
            border-top: 1px solid #ccc;
            font-size: 6px;
            color: #888;
            text-align: center;
        }}

        /* FIRMAS */
        .firmas {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 20px;
            margin-top: 10px;
            padding: 10px;
        }}
        .firma {{
            border-top: 1px solid #333;
            padding-top: 3px;
            text-align: center;
            font-size: 7px;
        }}
    </style>
</head>
<body>
    <!-- ENCABEZADO OFICIAL -->
    <div class="header-oficial">
        <div class="header-top">
            <div class="header-logo">
                <div class="escudo">🏛️</div>
                <div style="font-size:6px;margin-top:2px;">COLOMBIA</div>
            </div>
            <div class="header-title">
                <h1>{config['entidad']}</h1>
                <h2>{config['formulario']}</h2>
                <div style="font-size:7px;color:#666;">Año gravable 2025 - {config['normativa']}</div>
            </div>
            <div class="header-code">
                <div class="codigo">{config['codigo_form']}</div>
                <div style="margin-top:3px;">Página 1 de 1</div>
            </div>
        </div>
    </div>

    <!-- DATOS DEL CONTRIBUYENTE -->
    <div class="contribuyente">
        <div class="campo">
            <span class="label">1. NIT</span>
            <span class="value">{company.vat or 'N/A'}</span>
        </div>
        <div class="campo" style="grid-column: span 2;">
            <span class="label">2. RAZÓN SOCIAL</span>
            <span class="value">{company.name}</span>
        </div>
        <div class="campo">
            <span class="label">3. DV</span>
            <span class="value">{(company.vat or '')[-1] if company.vat else ''}</span>
        </div>
        <div class="campo">
            <span class="label">4. PERÍODO</span>
            <span class="value">{date_from.strftime('%m/%Y')}</span>
        </div>
        <div class="campo">
            <span class="label">5. DESDE</span>
            <span class="value">{date_from.strftime('%d/%m/%Y')}</span>
        </div>
        <div class="campo">
            <span class="label">6. HASTA</span>
            <span class="value">{date_to.strftime('%d/%m/%Y')}</span>
        </div>
        <div class="campo">
            <span class="label">7. MUNICIPIO</span>
            <span class="value">{config['nombre']}</span>
        </div>
    </div>

    <div class="dos-columnas">
        <!-- INGRESOS OPERACIONALES -->
        <div class="seccion">
            <div class="seccion-title">SECCIÓN A - INGRESOS GRAVABLES</div>
            <div class="seccion-content">
                <table class="renglones">
                    <tr>
                        <th style="width:30px;">Reng.</th>
                        <th>Cuenta / Concepto</th>
                        <th class="valor">Valor ($)</th>
                    </tr>
                    {ingresos_html}
                    <tr class="total">
                        <td class="renglon">39</td>
                        <td><strong>TOTAL INGRESOS OPERACIONALES</strong></td>
                        <td class="valor">{format_money(total_ingresos)}</td>
                    </tr>
                </table>
            </div>
        </div>

        <!-- LIQUIDACIÓN PRIVADA -->
        <div class="seccion">
            <div class="seccion-title">SECCIÓN B - LIQUIDACIÓN PRIVADA</div>
            <div class="seccion-content">
                <table class="renglones">
                    <tr>
                        <th style="width:30px;">Reng.</th>
                        <th>Concepto</th>
                        <th class="valor">Valor ($)</th>
                    </tr>
                    <tr>
                        <td class="renglon">40</td>
                        <td>Total ingresos gravables (del renglón 39)</td>
                        <td class="valor">{format_money(total_ingresos)}</td>
                    </tr>
                    <tr>
                        <td class="renglon">41</td>
                        <td>(-) Ingresos no gravados</td>
                        <td class="valor">0</td>
                    </tr>
                    <tr>
                        <td class="renglon">42</td>
                        <td>(=) Base gravable</td>
                        <td class="valor">{format_money(total_ingresos)}</td>
                    </tr>
                    <tr>
                        <td class="renglon">43</td>
                        <td>Impuesto ICA (tarifa {config['tarifas']['servicios']['comun']}‰)</td>
                        <td class="valor">{format_money(ica_causado)}</td>
                    </tr>
                    <tr>
                        <td class="renglon">44</td>
                        <td>(+) Avisos y tableros ({config['avisos_tableros']:.0f}%)</td>
                        <td class="valor">{format_money(avisos_tableros)}</td>
                    </tr>
                    <tr class="total">
                        <td class="renglon">45</td>
                        <td><strong>Total ICA + Avisos</strong></td>
                        <td class="valor">{format_money(total_ica)}</td>
                    </tr>
                    <tr>
                        <td class="renglon">46</td>
                        <td>(-) Retenciones que nos practican</td>
                        <td class="valor">{format_money(reteica_que_practican)}</td>
                    </tr>
                    <tr>
                        <td class="renglon">47</td>
                        <td>(-) Autoretención ICA aplicada</td>
                        <td class="valor">{format_money(autorret_ica)}</td>
                    </tr>
                    <tr class="pagar">
                        <td class="renglon">48</td>
                        <td><strong>SALDO A PAGAR</strong></td>
                        <td class="valor">{format_money(saldo_a_pagar)}</td>
                    </tr>
                    <tr class="favor">
                        <td class="renglon">49</td>
                        <td><strong>SALDO A FAVOR</strong></td>
                        <td class="valor">{format_money(saldo_a_favor)}</td>
                    </tr>
                </table>
            </div>
        </div>
    </div>

    <!-- AUTORETENCIONES -->
    <div class="seccion autorret">
        <div class="seccion-title">SECCIÓN C - AUTORETENCIONES (Art. 365 E.T. y Acuerdos Municipales)</div>
        <div class="seccion-content">
            <table class="renglones">
                <tr>
                    <th style="width:30px;">Reng.</th>
                    <th>Tipo de Autoretención</th>
                    <th style="width:60px;">Base Legal</th>
                    <th style="width:50px;text-align:center;">Tasa</th>
                    <th class="valor">Base ($)</th>
                    <th class="valor">Valor ($)</th>
                </tr>
                <tr>
                    <td class="renglon">50</td>
                    <td>Autoretención ICA - {config['nombre']}</td>
                    <td>{config['normativa'][:25]}...</td>
                    <td style="text-align:center;">{config['autorret_ica']}‰</td>
                    <td class="valor">{format_money(total_ingresos)}</td>
                    <td class="valor">{format_money(autorret_ica)}</td>
                </tr>
                <tr>
                    <td class="renglon">51</td>
                    <td>Autoretención Renta (Gran Contribuyente)</td>
                    <td>Art. 365 E.T.</td>
                    <td style="text-align:center;">{config['autorret_renta']}%</td>
                    <td class="valor">{format_money(total_ingresos)}</td>
                    <td class="valor">{format_money(autorret_renta)}</td>
                </tr>
                <tr class="total">
                    <td class="renglon">52</td>
                    <td colspan="4"><strong>TOTAL AUTORETENCIONES A DECLARAR Y PAGAR</strong></td>
                    <td class="valor"><strong>{format_money(autorret_ica + autorret_renta)}</strong></td>
                </tr>
            </table>
        </div>
    </div>

    <!-- RETENCIONES PRACTICADAS POR TIPO DE PERSONA -->
    <div class="dos-columnas">
        <div class="seccion">
            <div class="seccion-title">SECCIÓN D1 - RETEICA PRACTICADO A PERSONAS JURÍDICAS (PJ)</div>
            <div class="seccion-content">
                <table class="terceros">
                    <tr>
                        <th style="width:80px;">NIT</th>
                        <th>Razón Social</th>
                        <th class="valor" style="width:80px;">Base</th>
                        <th class="valor" style="width:60px;">Retención</th>
                    </tr>
                    {terceros_pj_html if terceros_pj_html else '<tr><td colspan="4" style="text-align:center;color:#888;">Sin retenciones a PJ</td></tr>'}
                    <tr style="background:#f0f0f0;font-weight:bold;">
                        <td colspan="2">Total PJ</td>
                        <td class="valor">{format_money(sum(t['base'] for t in ica_result.get('terceros_pj', [])))}</td>
                        <td class="valor">{format_money(ica_result.get('reteica_pj', 0))}</td>
                    </tr>
                </table>
            </div>
        </div>

        <div class="seccion">
            <div class="seccion-title">SECCIÓN D2 - RETEICA PRACTICADO A PERSONAS NATURALES (PN)</div>
            <div class="seccion-content">
                <table class="terceros">
                    <tr>
                        <th style="width:80px;">CC/NIT</th>
                        <th>Nombre</th>
                        <th class="valor" style="width:80px;">Base</th>
                        <th class="valor" style="width:60px;">Retención</th>
                    </tr>
                    {terceros_pn_html if terceros_pn_html else '<tr><td colspan="4" style="text-align:center;color:#888;">Sin retenciones a PN</td></tr>'}
                    <tr style="background:#f0f0f0;font-weight:bold;">
                        <td colspan="2">Total PN</td>
                        <td class="valor">{format_money(sum(t['base'] for t in ica_result.get('terceros_pn', [])))}</td>
                        <td class="valor">{format_money(ica_result.get('reteica_pn', 0))}</td>
                    </tr>
                </table>
            </div>
        </div>
    </div>

    <!-- RESUMEN TARIFAS -->
    <div class="seccion" style="background:#f8f8f8;">
        <div class="seccion-title" style="background:#666;">TARIFAS ICA VIGENTES - {config['nombre']} (por mil)</div>
        <div class="seccion-content" style="padding:5px;">
            <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:5px;text-align:center;font-size:7px;">
                <div style="background:#e0e0e0;padding:3px;border-radius:3px;">
                    <strong>INDUSTRIAL</strong><br>
                    {config['tarifas']['industrial']['min']}‰ - {config['tarifas']['industrial']['max']}‰<br>
                    <span style="color:#333;">Común: {config['tarifas']['industrial']['comun']}‰</span>
                </div>
                <div style="background:#e0e0e0;padding:3px;border-radius:3px;">
                    <strong>COMERCIAL</strong><br>
                    {config['tarifas']['comercial']['min']}‰ - {config['tarifas']['comercial']['max']}‰<br>
                    <span style="color:#333;">Común: {config['tarifas']['comercial']['comun']}‰</span>
                </div>
                <div style="background:#e0e0e0;padding:3px;border-radius:3px;">
                    <strong>SERVICIOS</strong><br>
                    {config['tarifas']['servicios']['min']}‰ - {config['tarifas']['servicios']['max']}‰<br>
                    <span style="color:#333;">Común: {config['tarifas']['servicios']['comun']}‰</span>
                </div>
                <div style="background:#e0e0e0;padding:3px;border-radius:3px;">
                    <strong>FINANCIERO</strong><br>
                    {config['tarifas']['financiero']['min']}‰ - {config['tarifas']['financiero']['max']}‰<br>
                    <span style="color:#333;">Común: {config['tarifas']['financiero']['comun']}‰</span>
                </div>
            </div>
            <div style="font-size:6px;color:#666;margin-top:3px;text-align:center;">
                Base mínima retención: Servicios {config['base_min_uvt']['servicios']} UVT (${format_money(config['base_min_uvt']['servicios'] * UVT_2025)}) |
                Compras {config['base_min_uvt']['compras']} UVT (${format_money(config['base_min_uvt']['compras'] * UVT_2025)}) |
                UVT 2025: ${format_money(UVT_2025)}
            </div>
        </div>
    </div>

    <!-- FIRMAS -->
    <div class="firmas">
        <div class="firma">
            <strong>CONTRIBUYENTE O REP. LEGAL</strong><br>
            C.C./NIT: ________________
        </div>
        <div class="firma">
            <strong>CONTADOR PÚBLICO</strong><br>
            T.P.: ________________
        </div>
        <div class="firma">
            <strong>REVISOR FISCAL</strong><br>
            T.P.: ________________
        </div>
    </div>

    <!-- PIE -->
    <div class="footer">
        Documento generado el {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} | {company.name} | Sistema de Reportes Fiscales Colombia<br>
        Este documento es un borrador para revisión interna. La declaración oficial debe presentarse en la plataforma de la secretaría de hacienda respectiva.
    </div>
</body>
</html>'''

    return html


def html_to_pdf(html_content, output_path):
    """Convertir HTML a PDF"""
    html_path = output_path.replace('.pdf', '.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    cmd = [
        '/usr/local/bin/wkhtmltopdf',
        '--orientation', 'Portrait',
        '--page-size', 'A4',
        '--margin-top', '3mm',
        '--margin-bottom', '3mm',
        '--margin-left', '3mm',
        '--margin-right', '3mm',
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
        print("GENERACIÓN DE FORMULARIOS ICA - FORMATO OFICIAL")
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
        ica_data = get_ica_data(env, date_from, date_to, company.id)
        print(f"   Registros encontrados: {len(ica_data)}")

        print("\n2. Obteniendo ingresos operacionales...")
        income_data = get_income_data(env, date_from, date_to, company.id)
        total_ingresos = sum(acc.get('creditos', 0) for acc in income_data)
        print(f"   Cuentas de ingresos: {len(income_data)}")
        print(f"   Total ingresos: ${format_money(total_ingresos)}")

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        print("\n3. Generando formularios por ciudad...")
        for city_code in CITY_CONFIG.keys():
            config = CITY_CONFIG[city_code]
            print(f"\n   → {config['nombre']}...")

            # Procesar datos ICA
            ica_result = process_ica_data(ica_data, city_code)

            # Generar HTML
            html = generate_official_form_html(
                company, date_from, date_to,
                ica_result, income_data, city_code
            )

            # Convertir a PDF
            pdf_path = os.path.join(OUTPUT_DIR, f"ica_oficial_{city_code.lower()}_{timestamp}.pdf")
            success, result = html_to_pdf(html, pdf_path)

            if success:
                autorret_ica = total_ingresos * (config['autorret_ica'] / 1000)
                autorret_renta = total_ingresos * (config['autorret_renta'] / 100)
                print(f"      ✓ PDF: {pdf_path}")
                print(f"        Autorret. ICA ({config['autorret_ica']}‰): ${format_money(autorret_ica)}")
                print(f"        Autorret. Renta ({config['autorret_renta']}%): ${format_money(autorret_renta)}")
                print(f"        ReteICA PJ: ${format_money(ica_result.get('reteica_pj', 0))}")
                print(f"        ReteICA PN: ${format_money(ica_result.get('reteica_pn', 0))}")
            else:
                print(f"      ✗ Error: {result}")

        print("\n" + "=" * 70)
        print("FORMULARIOS ICA OFICIALES GENERADOS")
        print("=" * 70)
        print(f"\nArchivos en: {OUTPUT_DIR}")

        for f in sorted(os.listdir(OUTPUT_DIR)):
            if 'ica_oficial' in f.lower() and f.endswith('.pdf'):
                size = os.path.getsize(os.path.join(OUTPUT_DIR, f))
                print(f"  - {f} ({size:,} bytes)")


if __name__ == '__main__':
    main()
