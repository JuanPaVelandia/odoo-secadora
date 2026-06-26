#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para generar formularios DIAN con formato oficial exacto:
- Formulario 300 (IVA Bimestral)
- Formulario 350 (Retención en la Fuente)

Replica el formato visual exacto de los formularios oficiales DIAN.
Basado en imágenes de referencia: l10n_co_tax_reports/Captura*.png
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


def format_money(value):
    """Formatear valor monetario colombiano"""
    if value is None or value == 0:
        return ""
    try:
        return f"{value:,.0f}".replace(",", ".")
    except:
        return str(value)


def get_tax_data(env, date_from, date_to, company_id):
    """Obtener datos de impuestos para el período"""
    query = """
        SELECT
            aml.id,
            aml.move_id,
            aml.account_id,
            aml.partner_id,
            aml.balance,
            aml.tax_base_amount,
            aml.tax_line_id,
            am.name as move_name,
            am.date,
            am.move_type,
            at.id as tax_id,
            at.name::text as tax_name,
            at.amount as tax_rate,
            at.amount_type,
            atg.name as tax_group_name,
            COALESCE(rp.name, '') as partner_name,
            COALESCE(rp.vat, '') as partner_vat,
            COALESCE(rp.is_company, false) as is_company
        FROM account_move_line aml
        JOIN account_move am ON am.id = aml.move_id
        LEFT JOIN account_tax at ON at.id = aml.tax_line_id
        LEFT JOIN account_tax_group atg ON atg.id = at.tax_group_id
        LEFT JOIN res_partner rp ON rp.id = aml.partner_id
        WHERE aml.tax_line_id IS NOT NULL
            AND am.date >= %s
            AND am.date <= %s
            AND am.company_id = %s
            AND am.state = 'posted'
        ORDER BY atg.name, at.name, am.date
    """
    env.cr.execute(query, (date_from, date_to, company_id))
    return env.cr.dictfetchall()


def generate_form_300_data(tax_data):
    """Calcular datos para Formulario 300 (IVA)"""
    form_data = {str(k): 0 for k in range(27, 101)}

    for row in tax_data:
        tax_name_raw = row.get('tax_name') or ''
        tax_name = str(tax_name_raw).upper() if tax_name_raw else ''
        tax_rate = abs(float(row.get('tax_rate') or 0))
        balance = abs(float(row.get('balance') or 0))
        base = abs(float(row.get('tax_base_amount') or 0))
        move_type = str(row.get('move_type') or '')

        # IVA 19%
        if tax_rate == 19 or '19' in tax_name:
            if move_type in ('out_invoice', 'out_refund'):
                form_data['29'] += base  # Tarifa general
                form_data['63'] += balance  # IVA generado 19%
            else:
                form_data['51'] += base  # Compras nacionales 19%
                form_data['72'] += balance  # IVA descontable 19%
        # IVA 5%
        elif tax_rate == 5 or '5%' in tax_name:
            if move_type in ('out_invoice', 'out_refund'):
                form_data['27'] += base
                form_data['62'] += balance
            else:
                form_data['50'] += base
                form_data['71'] += balance

    # Calcular totales
    form_data['41'] = sum(form_data.get(str(k), 0) for k in range(27, 41))  # Total ingresos brutos
    form_data['43'] = form_data['41'] - form_data['42']  # Total ingresos netos
    form_data['55'] = sum(form_data.get(str(k), 0) for k in range(44, 55))  # Total compras brutas
    form_data['57'] = form_data['55'] - form_data['56']  # Total compras netas
    form_data['67'] = sum(form_data.get(str(k), 0) for k in range(62, 67))  # Total IVA generado
    form_data['77'] = sum(form_data.get(str(k), 0) for k in range(68, 77))  # Total impuesto pagado
    form_data['81'] = sum(form_data.get(str(k), 0) for k in range(68, 81))  # Total IVA descontable
    form_data['82'] = max(form_data['67'] - form_data['81'], 0)  # Saldo a pagar
    form_data['83'] = max(form_data['81'] - form_data['67'], 0)  # Saldo a favor
    form_data['86'] = max(form_data['82'] - form_data['84'] - form_data['85'], 0)  # Saldo a pagar por impuesto
    form_data['88'] = form_data['86'] + form_data['87']  # Total a pagar
    form_data['89'] = max(form_data['83'] + form_data['84'] + form_data['85'] - form_data['87'], 0)  # Total saldo a favor

    return form_data


def generate_form_350_data(tax_data):
    """Calcular datos para Formulario 350 (Retención en la Fuente) - Formato oficial"""
    # Estructura según imagen oficial del formulario 350
    form_data = {str(k): 0 for k in range(27, 141)}

    for row in tax_data:
        tax_name_raw = row.get('tax_name') or ''
        tax_name = str(tax_name_raw).upper() if tax_name_raw else ''
        balance = abs(float(row.get('balance') or 0))
        base = abs(float(row.get('tax_base_amount') or 0))
        is_company = bool(row.get('is_company', False))

        if 'RETE' not in tax_name and 'RTE' not in tax_name:
            continue

        # Persona Jurídica (casillas 29-41 bases, 42-54 retenciones)
        # Persona Natural (casillas 77-92 bases, 93-108 retenciones)
        if 'IVA' in tax_name:
            # Retenciones IVA (casillas 131-134)
            form_data['131'] += base
            form_data['134'] += balance
        elif 'HONOR' in tax_name:
            if is_company:
                form_data['29'] += base
                form_data['42'] += balance
            else:
                form_data['79'] += base
                form_data['95'] += balance
        elif 'COMIS' in tax_name:
            if is_company:
                form_data['30'] += base
                form_data['43'] += balance
            else:
                form_data['80'] += base
                form_data['96'] += balance
        elif 'SERVIC' in tax_name:
            if is_company:
                form_data['31'] += base
                form_data['44'] += balance
            else:
                form_data['81'] += base
                form_data['97'] += balance
        elif 'FINANC' in tax_name or 'INTERES' in tax_name:
            if is_company:
                form_data['32'] += base
                form_data['45'] += balance
            else:
                form_data['82'] += base
                form_data['98'] += balance
        elif 'ARREND' in tax_name:
            if is_company:
                form_data['33'] += base
                form_data['46'] += balance
            else:
                form_data['83'] += base
                form_data['99'] += balance
        elif 'REGAL' in tax_name:
            if is_company:
                form_data['34'] += base
                form_data['47'] += balance
            else:
                form_data['84'] += base
                form_data['100'] += balance
        elif 'DIVID' in tax_name:
            if is_company:
                form_data['35'] += base
                form_data['48'] += balance
            else:
                form_data['85'] += base
                form_data['101'] += balance
        elif 'COMPR' in tax_name:
            if is_company:
                form_data['36'] += base
                form_data['49'] += balance
            else:
                form_data['86'] += base
                form_data['102'] += balance
        elif 'TARJETA' in tax_name or 'DÉBITO' in tax_name or 'CRÉDITO' in tax_name:
            if is_company:
                form_data['37'] += base
                form_data['50'] += balance
            else:
                form_data['87'] += base
                form_data['103'] += balance
        elif 'CONSTRUC' in tax_name:
            if is_company:
                form_data['38'] += base
                form_data['51'] += balance
            else:
                form_data['88'] += base
                form_data['104'] += balance
        elif 'LOTER' in tax_name or 'RIFA' in tax_name or 'APUESTA' in tax_name:
            if is_company:
                form_data['39'] += base
                form_data['52'] += balance
            else:
                form_data['90'] += base
                form_data['106'] += balance
        elif 'HIDROCARB' in tax_name or 'MINER' in tax_name:
            if is_company:
                form_data['40'] += base
                form_data['53'] += balance
            else:
                form_data['91'] += base
                form_data['107'] += balance
        else:
            # Otros pagos sujetos a retención
            if is_company:
                form_data['41'] += base
                form_data['54'] += balance
            else:
                form_data['92'] += base
                form_data['108'] += balance

    # Autorretenciones (casillas 60-76 base, 68-76 retencion según imagen)
    # Se deja para implementación futura con cuentas específicas

    # Totales
    form_data['129'] = 0  # Menos retenciones en exceso
    form_data['130'] = sum(form_data.get(str(k), 0) for k in range(42, 55))  # Total retenciones PJ
    form_data['130'] += sum(form_data.get(str(k), 0) for k in range(95, 109))  # + Total retenciones PN
    form_data['130'] += sum(form_data.get(str(k), 0) for k in range(68, 77))  # + Autorretenciones
    form_data['130'] -= form_data['129']  # - Retenciones en exceso

    # Retenciones IVA
    form_data['134'] = form_data.get('134', 0)  # Total ReteIVA

    # Retenciones timbre
    form_data['135'] = 0

    # Total retenciones
    form_data['136'] = form_data['130'] + form_data['134'] + form_data['135']

    # Sanciones
    form_data['137'] = 0

    # Total retenciones más sanciones
    form_data['138'] = form_data['136'] + form_data['137']

    return form_data


# ============================================================================
# CSS ESTILO DIAN OFICIAL - BASADO EN IMÁGENES DEL FORMULARIO
# ============================================================================
DIAN_CSS_300 = '''
@page {
    size: letter;
    margin: 5mm;
}
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}
body {
    font-family: Arial, Helvetica, sans-serif;
    font-size: 6.5px;
    background: white;
    color: #000;
    line-height: 1.15;
}

/* ENCABEZADO DIAN - FIJO */
.header-table {
    width: 100%;
    border-collapse: collapse;
    border: 1px solid #000;
    margin-bottom: 1px;
    table-layout: fixed;
}
.header-table td {
    border: 1px solid #000;
    vertical-align: middle;
}
.logo-cell {
    width: 55px;
    min-width: 55px;
    max-width: 55px;
    text-align: center;
    padding: 2px;
}
.dian-logo {
    font-family: 'Arial Black', Arial, sans-serif;
    font-size: 16px;
    font-weight: bold;
    letter-spacing: 2px;
    white-space: nowrap;
}
.title-cell {
    text-align: center;
    padding: 3px;
}
.title-main {
    font-size: 9px;
    font-weight: bold;
    white-space: nowrap;
}
.title-sub {
    font-size: 5px;
    color: #666;
}
.form-num-cell {
    width: 50px;
    min-width: 50px;
    max-width: 50px;
    text-align: center;
    background: #4a86c7;
    color: white;
}
.form-number {
    font-size: 24px;
    font-weight: bold;
}
.form-type {
    font-size: 5px;
}

/* FILA DE PERÍODO */
.period-row {
    display: table;
    width: 100%;
    border: 1px solid #000;
    border-top: none;
    margin-bottom: 1px;
}
.period-cell {
    display: table-cell;
    border-right: 1px solid #000;
    padding: 1px 3px;
    vertical-align: top;
}
.period-cell:last-child { border-right: none; }
.cas-inline {
    display: inline-block;
    background: #404040;
    color: white;
    font-size: 5.5px;
    font-weight: bold;
    padding: 0 3px;
    min-width: 12px;
    text-align: center;
    margin-right: 2px;
}
.field-label {
    font-size: 5px;
    color: #666;
}
.field-value {
    font-weight: bold;
    font-size: 7px;
}

/* DATOS DECLARANTE */
.declarant-section {
    border: 1px solid #000;
    margin-bottom: 1px;
}
.declarant-row {
    display: flex;
    border-bottom: 1px solid #ccc;
}
.declarant-row:last-child { border-bottom: none; }
.declarant-cell {
    padding: 1px 3px;
    border-right: 1px solid #ccc;
    min-height: 12px;
}
.declarant-cell:last-child { border-right: none; }
.declarant-cell.w-nit { width: 90px; }
.declarant-cell.w-dv { width: 25px; }
.declarant-cell.w-name { width: 55px; }
.declarant-cell.w-razon { flex: 1; }
.declarant-cell.w-cod { width: 45px; }
.declarant-cell.w-period { width: 50px; }

/* SECCIONES CON TÍTULO LATERAL */
.section-container {
    display: table;
    width: 100%;
    border: 1px solid #000;
    margin-bottom: 1px;
}
.section-label {
    display: table-cell;
    width: 12px;
    background: #f0f0f0;
    border-right: 1px solid #000;
    vertical-align: middle;
    text-align: center;
}
.section-label span {
    writing-mode: vertical-rl;
    transform: rotate(180deg);
    font-size: 5.5px;
    font-weight: bold;
    padding: 2px;
}
.section-content {
    display: table-cell;
    vertical-align: top;
}

/* TABLAS DE DATOS */
table.form-table {
    width: 100%;
    border-collapse: collapse;
}
table.form-table td {
    border: 1px solid #999;
    padding: 0.5px 2px;
    font-size: 6px;
    height: 10px;
    vertical-align: middle;
}
table.form-table .cas {
    width: 14px;
    background: #404040;
    color: white;
    text-align: center;
    font-weight: bold;
    font-size: 5.5px;
}
table.form-table .concepto {
    text-align: left;
    padding-left: 3px;
}
table.form-table .valor {
    width: 65px;
    text-align: right;
    padding-right: 3px;
    font-family: 'Courier New', monospace;
    background: #fafafa;
}
table.form-table tr.subtotal td {
    background: #e8e8e8;
    font-weight: bold;
}
table.form-table tr.total td {
    background: #d0d0d0;
    font-weight: bold;
}
table.form-table tr.total .cas {
    background: #202020;
}
table.form-table tr.pagar td {
    background: #c8c8c8;
    font-weight: bold;
}
table.form-table tr.favor td {
    background: #e0e0e0;
}

/* DOS COLUMNAS */
.two-cols {
    display: flex;
    gap: 0;
}
.two-cols .col {
    flex: 1;
}
.two-cols .col:first-child {
    border-right: 1px solid #000;
}

/* FIRMAS */
.signatures {
    border: 1px solid #000;
    padding: 3px;
    margin-top: 1px;
}
.sig-row {
    display: flex;
    gap: 15px;
}
.sig-box {
    flex: 1;
    text-align: center;
}
.sig-line {
    border-top: 1px solid #000;
    margin-top: 15px;
    padding-top: 2px;
    font-size: 5.5px;
    font-weight: bold;
}
.sig-label {
    font-size: 5px;
    color: #666;
}

/* PIE */
.footer {
    font-size: 4.5px;
    color: #888;
    text-align: center;
    margin-top: 2px;
    padding-top: 2px;
    border-top: 1px solid #ddd;
}
'''


DIAN_CSS_350 = '''
@page {
    size: letter;
    margin: 5mm;
}
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}
body {
    font-family: Arial, Helvetica, sans-serif;
    font-size: 6px;
    background: white;
    color: #000;
    line-height: 1.1;
}

/* ENCABEZADO DIAN - FIJO */
.header-table {
    width: 100%;
    border-collapse: collapse;
    border: 1px solid #000;
    margin-bottom: 1px;
    table-layout: fixed;
}
.header-table td {
    border: 1px solid #000;
    vertical-align: middle;
}
.logo-cell {
    width: 55px;
    min-width: 55px;
    max-width: 55px;
    text-align: center;
    padding: 2px;
}
.dian-logo {
    font-family: 'Arial Black', Arial, sans-serif;
    font-size: 16px;
    font-weight: bold;
    letter-spacing: 2px;
    white-space: nowrap;
}
.title-cell {
    text-align: center;
    padding: 3px;
}
.title-main {
    font-size: 9px;
    font-weight: bold;
    white-space: nowrap;
}
.form-num-cell {
    width: 50px;
    min-width: 50px;
    max-width: 50px;
    text-align: center;
    background: #4a86c7;
    color: white;
}
.form-number {
    font-size: 24px;
    font-weight: bold;
}

/* PERÍODO */
.period-row {
    display: table;
    width: 100%;
    border: 1px solid #000;
    border-top: none;
    margin-bottom: 1px;
}
.period-cell {
    display: table-cell;
    border-right: 1px solid #000;
    padding: 1px 2px;
}
.period-cell:last-child { border-right: none; }
.cas-inline {
    display: inline-block;
    background: #404040;
    color: white;
    font-size: 5px;
    font-weight: bold;
    padding: 0 2px;
    min-width: 10px;
    text-align: center;
}

/* DATOS DECLARANTE */
.declarant-box {
    border: 1px solid #000;
    margin-bottom: 1px;
}
.declarant-title {
    background: #e8e8e8;
    padding: 1px 3px;
    font-weight: bold;
    font-size: 5.5px;
    border-bottom: 1px solid #000;
}
.declarant-row {
    display: flex;
    border-bottom: 1px solid #ccc;
}
.declarant-row:last-child { border-bottom: none; }
.declarant-cell {
    padding: 1px 2px;
    border-right: 1px solid #ccc;
    font-size: 5.5px;
}
.declarant-cell:last-child { border-right: none; }
.declarant-cell .val { font-weight: bold; font-size: 6px; }

/* TABLA PRINCIPAL 350 - 4 COLUMNAS */
table.ret-table {
    width: 100%;
    border-collapse: collapse;
    border: 1px solid #000;
    margin-bottom: 1px;
}
table.ret-table th {
    background: #e8e8e8;
    border: 1px solid #000;
    padding: 1px 2px;
    font-size: 5px;
    font-weight: bold;
    text-align: center;
}
table.ret-table td {
    border: 1px solid #999;
    padding: 0.5px 2px;
    font-size: 5.5px;
    height: 9px;
}
table.ret-table .cas {
    width: 12px;
    background: #404040;
    color: white;
    text-align: center;
    font-weight: bold;
    font-size: 5px;
}
table.ret-table .concepto {
    text-align: left;
    padding-left: 2px;
    width: 140px;
}
table.ret-table .base {
    width: 55px;
    text-align: right;
    padding-right: 2px;
    font-family: 'Courier New', monospace;
    background: #fafafa;
}
table.ret-table .ret {
    width: 50px;
    text-align: right;
    padding-right: 2px;
    font-family: 'Courier New', monospace;
    background: #f5f5f5;
}

/* SECCIÓN CON TÍTULO LATERAL */
.section-wrap {
    display: table;
    width: 100%;
    border: 1px solid #000;
    margin-bottom: 1px;
}
.section-side {
    display: table-cell;
    width: 10px;
    background: #f0f0f0;
    border-right: 1px solid #000;
    vertical-align: middle;
}
.section-side span {
    writing-mode: vertical-rl;
    transform: rotate(180deg);
    font-size: 5px;
    font-weight: bold;
}
.section-main {
    display: table-cell;
}

/* TOTALES */
table.ret-table tr.subtotal td {
    background: #e0e0e0;
    font-weight: bold;
}
table.ret-table tr.total td {
    background: #d0d0d0;
    font-weight: bold;
}
table.ret-table tr.total .cas {
    background: #202020;
}

/* FIRMAS */
.signatures {
    border: 1px solid #000;
    padding: 2px;
    margin-top: 1px;
    font-size: 5px;
}
.sig-row {
    display: flex;
    gap: 10px;
    margin-top: 3px;
}
.sig-box {
    flex: 1;
    text-align: center;
}
.sig-line {
    border-top: 1px solid #000;
    margin-top: 12px;
    padding-top: 1px;
    font-weight: bold;
}

/* FOOTER */
.footer {
    font-size: 4.5px;
    color: #888;
    text-align: center;
    margin-top: 2px;
}
'''


def generate_form_300_html(company, date_from, date_to, form_data):
    """Generar HTML del Formulario 300 - IVA - Formato DIAN Oficial"""

    month = date_from.month
    bimestre = (month - 1) // 2 + 1

    nit_full = company.vat or ''
    if '-' in nit_full:
        nit, dv = nit_full.rsplit('-', 1)
    else:
        nit, dv = nit_full, ''

    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Formulario 300 - IVA</title>
    <style>{DIAN_CSS_300}</style>
</head>
<body>
    <!-- ENCABEZADO -->
    <table class="header-table">
        <tr>
            <td class="logo-cell">
                <div class="dian-logo">DIAN</div>
            </td>
            <td class="title-cell">
                <div class="title-main">Declaración del Impuesto sobre las Ventas - IVA</div>
                <div class="title-sub">Lea cuidadosamente las instrucciones</div>
            </td>
            <td class="form-num-cell">
                <div class="form-number">300</div>
                <div class="form-type">Privada</div>
            </td>
        </tr>
    </table>

    <!-- PERÍODO -->
    <div class="period-row">
        <div class="period-cell" style="width:60px;">
            <span class="cas-inline">1</span> <span class="field-label">Año</span><br>
            <span class="field-value">{date_from.year}</span>
        </div>
        <div class="period-cell" style="width:60px;">
            <span class="cas-inline">3</span> <span class="field-label">Período</span><br>
            <span class="field-value">{bimestre:02d}</span>
        </div>
        <div class="period-cell">
            <span class="cas-inline">4</span> <span class="field-label">Número de formulario</span>
        </div>
        <div class="period-cell" style="width:80px;">
            <span class="field-label">Si es una corrección indique:</span><br>
            <span class="cas-inline">25</span> Cód. <span class="cas-inline">26</span> No. Form anterior
        </div>
    </div>

    <!-- DATOS DEL DECLARANTE -->
    <div class="declarant-section">
        <div style="background:#e8e8e8;padding:1px 3px;font-weight:bold;font-size:5.5px;border-bottom:1px solid #000;">
            Datos del declarante
        </div>
        <div class="declarant-row">
            <div class="declarant-cell w-nit">
                <span class="cas-inline">5</span> <span class="field-label">Número de Identificación Tributaria (NIT)</span><br>
                <span class="field-value">{nit}</span>
            </div>
            <div class="declarant-cell w-dv">
                <span class="cas-inline">6</span> <span class="field-label">DV.</span><br>
                <span class="field-value">{dv}</span>
            </div>
            <div class="declarant-cell w-name">
                <span class="cas-inline">7</span> <span class="field-label">Primer apellido</span>
            </div>
            <div class="declarant-cell w-name">
                <span class="cas-inline">8</span> <span class="field-label">Segundo apellido</span>
            </div>
            <div class="declarant-cell w-name">
                <span class="cas-inline">9</span> <span class="field-label">Primer nombre</span>
            </div>
            <div class="declarant-cell w-name">
                <span class="cas-inline">10</span> <span class="field-label">Otros nombres</span>
            </div>
        </div>
        <div class="declarant-row">
            <div class="declarant-cell w-razon">
                <span class="cas-inline">11</span> <span class="field-label">Razón social</span><br>
                <span class="field-value">{company.name}</span>
            </div>
            <div class="declarant-cell w-cod">
                <span class="cas-inline">12</span> <span class="field-label">Cód. Dir. Seccional</span>
            </div>
        </div>
        <div class="declarant-row">
            <div class="declarant-cell" style="flex:1;">
                <span class="cas-inline">24</span> <span class="field-label">Periodicidad de la declaración, marque "X"</span>
                <span style="margin-left:10px;">Bimestral ☑</span>
                <span style="margin-left:10px;">Cuatrimestral ☐</span>
                <span style="margin-left:10px;">Anual ☐</span>
            </div>
        </div>
    </div>

    <!-- CONTENIDO PRINCIPAL EN DOS COLUMNAS -->
    <div class="two-cols">
        <!-- COLUMNA IZQUIERDA: INGRESOS + COMPRAS -->
        <div class="col">
            <!-- INGRESOS -->
            <div class="section-container">
                <div class="section-label"><span>Ingresos</span></div>
                <div class="section-content">
                    <table class="form-table">
                        <tr><td class="cas">27</td><td class="concepto">Por operaciones gravadas al 5%</td><td class="valor">{format_money(form_data.get('27', 0))}</td></tr>
                        <tr><td class="cas">28</td><td class="concepto">Por operaciones gravadas a la tarifa general</td><td class="valor">{format_money(form_data.get('28', 0))}</td></tr>
                        <tr><td class="cas">29</td><td class="concepto">A.I.U. por operaciones gravadas (base gravable especial)</td><td class="valor">{format_money(form_data.get('29', 0))}</td></tr>
                        <tr><td class="cas">30</td><td class="concepto">Por exportación de bienes</td><td class="valor">{format_money(form_data.get('30', 0))}</td></tr>
                        <tr><td class="cas">31</td><td class="concepto">Por exportación de servicios</td><td class="valor">{format_money(form_data.get('31', 0))}</td></tr>
                        <tr><td class="cas">32</td><td class="concepto">Por ventas a sociedades de comercialización internacional</td><td class="valor">{format_money(form_data.get('32', 0))}</td></tr>
                        <tr><td class="cas">33</td><td class="concepto">Por ventas a Zonas Francas</td><td class="valor">{format_money(form_data.get('33', 0))}</td></tr>
                        <tr><td class="cas">34</td><td class="concepto">Por juegos de suerte y azar</td><td class="valor">{format_money(form_data.get('34', 0))}</td></tr>
                        <tr><td class="cas">35</td><td class="concepto">Por operaciones exentas</td><td class="valor">{format_money(form_data.get('35', 0))}</td></tr>
                        <tr><td class="cas">36</td><td class="concepto">Por venta de cerveza de producción nacional o importada</td><td class="valor">{format_money(form_data.get('36', 0))}</td></tr>
                        <tr><td class="cas">37</td><td class="concepto">Por venta de gaseosas y similares</td><td class="valor">{format_money(form_data.get('37', 0))}</td></tr>
                        <tr><td class="cas">38</td><td class="concepto">Por venta de licores, aperitivos, vinos y similares</td><td class="valor">{format_money(form_data.get('38', 0))}</td></tr>
                        <tr><td class="cas">39</td><td class="concepto">Por operaciones excluidas</td><td class="valor">{format_money(form_data.get('39', 0))}</td></tr>
                        <tr><td class="cas">40</td><td class="concepto">Por operaciones no gravadas</td><td class="valor">{format_money(form_data.get('40', 0))}</td></tr>
                        <tr class="subtotal"><td class="cas">41</td><td class="concepto">Total ingresos brutos (Sume 27 a 40)</td><td class="valor">{format_money(form_data.get('41', 0))}</td></tr>
                        <tr><td class="cas">42</td><td class="concepto">Devoluciones en ventas anuladas, rescindidas o resueltas</td><td class="valor">{format_money(form_data.get('42', 0))}</td></tr>
                        <tr class="total"><td class="cas">43</td><td class="concepto">Total ingresos netos recibidos durante el período (41 - 42)</td><td class="valor">{format_money(form_data.get('43', 0))}</td></tr>
                    </table>
                </div>
            </div>

            <!-- COMPRAS - IMPORTACIONES -->
            <div class="section-container">
                <div class="section-label"><span>Compras</span></div>
                <div class="section-content">
                    <table class="form-table">
                        <tr style="background:#f0f0f0;"><td colspan="3" style="font-weight:bold;padding-left:20px;">Importaciones</td></tr>
                        <tr><td class="cas">44</td><td class="concepto">De bienes gravados a la tarifa del 5%</td><td class="valor">{format_money(form_data.get('44', 0))}</td></tr>
                        <tr><td class="cas">45</td><td class="concepto">De bienes gravados a la tarifa general</td><td class="valor">{format_money(form_data.get('45', 0))}</td></tr>
                        <tr><td class="cas">46</td><td class="concepto">De bienes y servicios gravados provenientes de zonas francas</td><td class="valor">{format_money(form_data.get('46', 0))}</td></tr>
                        <tr><td class="cas">47</td><td class="concepto">De bienes no gravados</td><td class="valor">{format_money(form_data.get('47', 0))}</td></tr>
                        <tr><td class="cas">48</td><td class="concepto">De bienes excluidos, exentos y no gravados provenientes de zonas francas</td><td class="valor">{format_money(form_data.get('48', 0))}</td></tr>
                        <tr><td class="cas">49</td><td class="concepto">De servicios</td><td class="valor">{format_money(form_data.get('49', 0))}</td></tr>
                        <tr style="background:#f0f0f0;"><td colspan="3" style="font-weight:bold;padding-left:20px;">Nacionales</td></tr>
                        <tr><td class="cas">50</td><td class="concepto">De bienes gravados a la tarifa del 5%</td><td class="valor">{format_money(form_data.get('50', 0))}</td></tr>
                        <tr><td class="cas">51</td><td class="concepto">De bienes gravados a la tarifa general</td><td class="valor">{format_money(form_data.get('51', 0))}</td></tr>
                        <tr><td class="cas">52</td><td class="concepto">De servicios gravados a la tarifa del 5%</td><td class="valor">{format_money(form_data.get('52', 0))}</td></tr>
                        <tr><td class="cas">53</td><td class="concepto">De servicios gravados a la tarifa general</td><td class="valor">{format_money(form_data.get('53', 0))}</td></tr>
                        <tr><td class="cas">54</td><td class="concepto">De bienes y servicios excluidos, exentos y no gravados</td><td class="valor">{format_money(form_data.get('54', 0))}</td></tr>
                        <tr class="subtotal"><td class="cas">55</td><td class="concepto">Total compras e importaciones brutas (Sume 44 a 54)</td><td class="valor">{format_money(form_data.get('55', 0))}</td></tr>
                        <tr><td class="cas">56</td><td class="concepto">Devoluciones en compras anuladas, rescindidas o resueltas en este periodo</td><td class="valor">{format_money(form_data.get('56', 0))}</td></tr>
                        <tr class="total"><td class="cas">57</td><td class="concepto">Total compras netas realizadas durante el período (55 - 56)</td><td class="valor">{format_money(form_data.get('57', 0))}</td></tr>
                    </table>
                </div>
            </div>

            <!-- LIQUIDACIÓN PRIVADA - IVA GENERADO -->
            <div class="section-container">
                <div class="section-label"><span>Liquidación privada</span></div>
                <div class="section-content">
                    <table class="form-table">
                        <tr><td class="cas">58</td><td class="concepto">A la tarifa del 5%</td><td class="valor">{format_money(form_data.get('58', 0))}</td></tr>
                        <tr><td class="cas">59</td><td class="concepto">A la tarifa general</td><td class="valor">{format_money(form_data.get('59', 0))}</td></tr>
                        <tr><td class="cas">60</td><td class="concepto">Sobre A.I.U. en operaciones gravadas (base gravable especial)</td><td class="valor">{format_money(form_data.get('60', 0))}</td></tr>
                        <tr><td class="cas">61</td><td class="concepto">En juegos de suerte y azar</td><td class="valor">{format_money(form_data.get('61', 0))}</td></tr>
                    </table>
                </div>
            </div>
        </div>

        <!-- COLUMNA DERECHA: IVA GENERADO + DESCONTABLE + SALDOS -->
        <div class="col">
            <!-- IMPUESTO GENERADO (Continuación) -->
            <div class="section-container">
                <div class="section-label"><span>Impuesto generado</span></div>
                <div class="section-content">
                    <table class="form-table">
                        <tr><td class="cas">62</td><td class="concepto">En venta cerveza de producción nacional o importada</td><td class="valor">{format_money(form_data.get('62', 0))}</td></tr>
                        <tr><td class="cas">63</td><td class="concepto">En venta de gaseosas y similares</td><td class="valor">{format_money(form_data.get('63', 0))}</td></tr>
                        <tr><td class="cas">64</td><td class="concepto">En venta de licores, aperitivos, vinos y similares 5%</td><td class="valor">{format_money(form_data.get('64', 0))}</td></tr>
                        <tr><td class="cas">65</td><td class="concepto">En retiro de inventario para activos fijos, consumo, muestras gratis o donaciones</td><td class="valor">{format_money(form_data.get('65', 0))}</td></tr>
                        <tr><td class="cas">66</td><td class="concepto">IVA recuperado en devoluciones en compras anuladas, rescindidas o resueltas</td><td class="valor">{format_money(form_data.get('66', 0))}</td></tr>
                        <tr class="subtotal"><td class="cas">67</td><td class="concepto">Total Impuesto generado por operaciones gravadas (Sume 58 a 66)</td><td class="valor">{format_money(form_data.get('67', 0))}</td></tr>
                    </table>
                </div>
            </div>

            <!-- IMPUESTO DESCONTABLE -->
            <div class="section-container">
                <div class="section-label"><span>Impuesto descontable</span></div>
                <div class="section-content">
                    <table class="form-table">
                        <tr><td class="cas">68</td><td class="concepto">Por importaciones gravadas a la tarifa del 5%</td><td class="valor">{format_money(form_data.get('68', 0))}</td></tr>
                        <tr><td class="cas">69</td><td class="concepto">Por importaciones gravadas a la tarifa general</td><td class="valor">{format_money(form_data.get('69', 0))}</td></tr>
                        <tr><td class="cas">70</td><td class="concepto">De bienes y servicios gravados provenientes de zonas francas</td><td class="valor">{format_money(form_data.get('70', 0))}</td></tr>
                        <tr><td class="cas">71</td><td class="concepto">Por compras de bienes gravados a la tarifa del 5%</td><td class="valor">{format_money(form_data.get('71', 0))}</td></tr>
                        <tr><td class="cas">72</td><td class="concepto">Por compras de bienes gravados a la tarifa general</td><td class="valor">{format_money(form_data.get('72', 0))}</td></tr>
                        <tr><td class="cas">73</td><td class="concepto">Por licores, aperitivos, vinos y similares</td><td class="valor">{format_money(form_data.get('73', 0))}</td></tr>
                        <tr><td class="cas">74</td><td class="concepto">Por servicios gravados a la tarifa del 5%</td><td class="valor">{format_money(form_data.get('74', 0))}</td></tr>
                        <tr><td class="cas">75</td><td class="concepto">Por servicios gravados a la tarifa general</td><td class="valor">{format_money(form_data.get('75', 0))}</td></tr>
                        <tr><td class="cas">76</td><td class="concepto">Descuento IVA exploración hidrocarburos Art. 485-2 E.T.</td><td class="valor">{format_money(form_data.get('76', 0))}</td></tr>
                        <tr class="subtotal"><td class="cas">77</td><td class="concepto">Total impuesto pagado o facturado (Sume 68 a 76)</td><td class="valor">{format_money(form_data.get('77', 0))}</td></tr>
                        <tr><td class="cas">78</td><td class="concepto">IVA retenido por servicios prestados en Colombia por no domiciliados o no residentes</td><td class="valor">{format_money(form_data.get('78', 0))}</td></tr>
                        <tr><td class="cas">79</td><td class="concepto">IVA resultante por devoluciones en ventas anuladas, rescindidas o resueltas</td><td class="valor">{format_money(form_data.get('79', 0))}</td></tr>
                        <tr><td class="cas">80</td><td class="concepto">Ajuste impuestos descontables (pérdidas, hurto o castigo de inventarios)</td><td class="valor">{format_money(form_data.get('80', 0))}</td></tr>
                        <tr class="total"><td class="cas">81</td><td class="concepto">Total impuestos descontables (Sume 77 a 79 y reste 80)</td><td class="valor">{format_money(form_data.get('81', 0))}</td></tr>
                    </table>
                </div>
            </div>

            <!-- SALDOS -->
            <div class="section-container">
                <div class="section-label"><span>Saldo</span></div>
                <div class="section-content">
                    <table class="form-table">
                        <tr class="pagar"><td class="cas">82</td><td class="concepto">Saldo a pagar por el período fiscal (67 - 81, si el resultado es menor a cero escriba 0)</td><td class="valor">{format_money(form_data.get('82', 0))}</td></tr>
                        <tr class="favor"><td class="cas">83</td><td class="concepto">Saldo a favor del período fiscal (81 - 67, si el resultado es menor a cero escriba 0)</td><td class="valor">{format_money(form_data.get('83', 0))}</td></tr>
                        <tr><td class="cas">84</td><td class="concepto">Saldo a favor del período fiscal anterior</td><td class="valor">{format_money(form_data.get('84', 0))}</td></tr>
                        <tr><td class="cas">85</td><td class="concepto">Retenciones por IVA que le practicaron</td><td class="valor">{format_money(form_data.get('85', 0))}</td></tr>
                        <tr class="subtotal"><td class="cas">86</td><td class="concepto">Saldo a pagar por impuesto (82 - 84 - 85 si el resultado es menor a cero escriba 0)</td><td class="valor">{format_money(form_data.get('86', 0))}</td></tr>
                        <tr><td class="cas">87</td><td class="concepto">Sanciones</td><td class="valor">{format_money(form_data.get('87', 0))}</td></tr>
                        <tr class="total"><td class="cas">88</td><td class="concepto">Total saldo a pagar (82 - 84 - 85 + 87, si el resultado es menor a cero escriba 0)</td><td class="valor">{format_money(form_data.get('88', 0))}</td></tr>
                        <tr class="favor"><td class="cas">89</td><td class="concepto">Total saldo a favor (83 + 84 + 85 - 87 si el resultado es menor a cero escriba 0)</td><td class="valor">{format_money(form_data.get('89', 0))}</td></tr>
                    </table>
                </div>
            </div>

            <!-- CONTROL DE SALDOS -->
            <div class="section-container">
                <div class="section-label"><span>Control saldos</span></div>
                <div class="section-content">
                    <table class="form-table">
                        <tr><td class="cas">90</td><td class="concepto">Saldo a favor susceptible de devolución y/o compensación por el presente período</td><td class="valor">{format_money(form_data.get('90', 0))}</td></tr>
                        <tr><td class="cas">91</td><td class="concepto">Saldo a favor susceptible de ser devuelto y/o compensado a imputar en el período siguiente</td><td class="valor">{format_money(form_data.get('91', 0))}</td></tr>
                        <tr><td class="cas">92</td><td class="concepto">Saldo a favor sin derecho a devolución y/o compensación susceptible de ser imputado en el siguiente período</td><td class="valor">{format_money(form_data.get('92', 0))}</td></tr>
                        <tr class="subtotal"><td class="cas">93</td><td class="concepto">Total saldo a favor a imputar al período siguiente (Casilla 89 - 90)</td><td class="valor">{format_money(form_data.get('93', 0))}</td></tr>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <!-- ANTICIPOS IVA RÉGIMEN SIMPLE -->
    <table class="form-table" style="margin-top:1px;">
        <tr style="background:#e8e8e8;">
            <td colspan="4" style="font-weight:bold;font-size:5.5px;">Anticipos IVA Régimen Simple</td>
            <td class="cas">100</td>
            <td class="valor" style="width:60px;">Total anticipos IVA Régimen Simple</td>
            <td class="valor">{format_money(form_data.get('100', 0))}</td>
        </tr>
    </table>

    <!-- FIRMAS -->
    <div class="signatures">
        <div style="display:flex;gap:5px;font-size:5px;">
            <span class="cas-inline">101</span> No. Identificación signatario
            <span style="flex:1;border-bottom:1px dotted #999;"></span>
            <span class="cas-inline">102</span> DV
        </div>
        <div class="sig-row">
            <div class="sig-box">
                <div class="sig-line">Firma del declarante o de quien lo representa</div>
                <div class="sig-label"><span class="cas-inline">981</span> Cód. Representación</div>
            </div>
            <div class="sig-box">
                <div class="sig-line">Firma Contador o Revisor Fiscal</div>
                <div class="sig-label"><span class="cas-inline">994</span> Con salvedades</div>
            </div>
        </div>
        <div style="display:flex;gap:5px;font-size:5px;margin-top:3px;">
            <span class="cas-inline">982</span> Código Contador o Revisor Fiscal
            <span style="flex:1;"></span>
            <span class="cas-inline">983</span> No. Tarjeta profesional
        </div>
        <div style="display:flex;gap:10px;margin-top:5px;">
            <div style="flex:1;">
                <span class="cas-inline">997</span> Espacio exclusivo para el sello de la entidad recaudadora
            </div>
            <div style="border:1px solid #000;padding:2px 10px;">
                <span class="cas-inline">980</span> <strong>Pago total $</strong>
            </div>
        </div>
        <div style="text-align:right;font-size:4.5px;margin-top:2px;">
            996. Espacio para el número interno de la DIAN / Adhesivo
        </div>
    </div>

    <div class="footer">
        Documento borrador generado el {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} | {company.name}<br>
        La declaración oficial debe presentarse en www.dian.gov.co
    </div>
</body>
</html>'''

    return html


def generate_form_350_html(company, date_from, date_to, form_data):
    """Generar HTML del Formulario 350 - Retención en la Fuente - Formato DIAN Oficial Exacto"""

    nit_full = company.vat or ''
    if '-' in nit_full:
        nit, dv = nit_full.rsplit('-', 1)
    else:
        nit, dv = nit_full, ''

    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Formulario 350 - Retención en la Fuente</title>
    <style>{DIAN_CSS_350}</style>
</head>
<body>
    <!-- ENCABEZADO -->
    <table class="header-table">
        <tr>
            <td class="logo-cell">
                <div class="dian-logo">DIAN</div>
            </td>
            <td class="title-cell">
                <div class="title-main">Declaración retenciones en la fuente</div>
            </td>
            <td class="form-num-cell">
                <div class="form-number">350</div>
            </td>
        </tr>
    </table>

    <!-- PERÍODO -->
    <div class="period-row">
        <div class="period-cell" style="width:50px;">
            <span class="cas-inline">1</span> Año<br>
            <strong>{date_from.year}</strong>
        </div>
        <div class="period-cell" style="width:50px;">
            <span class="cas-inline">3</span> Período<br>
            <strong>{date_from.month:02d}</strong>
        </div>
        <div class="period-cell">
            <span class="cas-inline">4</span> Número de formulario
        </div>
    </div>

    <!-- DATOS DEL DECLARANTE -->
    <div class="declarant-box">
        <div class="declarant-title">Datos del declarante</div>
        <div class="declarant-row">
            <div class="declarant-cell" style="width:100px;">
                <span class="cas-inline">5</span> Número de Identificación Tributaria (NIT)<br>
                <span class="val">{nit}</span>
            </div>
            <div class="declarant-cell" style="width:25px;">
                <span class="cas-inline">6</span> DV<br>
                <span class="val">{dv}</span>
            </div>
            <div class="declarant-cell" style="width:50px;">
                <span class="cas-inline">7</span> Primer apellido
            </div>
            <div class="declarant-cell" style="width:50px;">
                <span class="cas-inline">8</span> Segundo apellido
            </div>
            <div class="declarant-cell" style="width:50px;">
                <span class="cas-inline">9</span> Primer nombre
            </div>
            <div class="declarant-cell" style="flex:1;">
                <span class="cas-inline">10</span> Otros nombres
            </div>
        </div>
        <div class="declarant-row">
            <div class="declarant-cell" style="flex:1;">
                <span class="cas-inline">11</span> Razón social<br>
                <span class="val">{company.name}</span>
            </div>
            <div class="declarant-cell" style="width:50px;">
                <span class="cas-inline">12</span> Cód. Dir. Seccional
            </div>
        </div>
    </div>

    <!-- CASILLAS DE CORRECCIÓN -->
    <div style="border:1px solid #000;padding:2px;margin-bottom:1px;font-size:5px;">
        Si es una corrección indique: <span class="cas-inline">25</span> Cód. &nbsp;&nbsp; <span class="cas-inline">26</span> No. Formulario anterior
        &nbsp;&nbsp;&nbsp;
        <span class="cas-inline">27</span> Autorretenedores PJ exonerados de aportes (Art. 114-1 E.T.) Actividad económica principal
        &nbsp;&nbsp;&nbsp;
        <span class="cas-inline">28</span> Tarifa
    </div>

    <!-- TABLA PRINCIPAL DE RETENCIONES -->
    <table class="ret-table">
        <!-- ENCABEZADO -->
        <tr>
            <th colspan="4" style="text-align:center;">A personas jurídicas</th>
            <th colspan="4" style="text-align:center;">A personas naturales</th>
        </tr>
        <tr>
            <th colspan="2">Concepto</th>
            <th>Base sujeta a retención para pagos o abonos en cuenta</th>
            <th>Retenciones a título de renta</th>
            <th colspan="2"></th>
            <th>Base sujeta a retención para pagos o abonos en cuenta</th>
            <th>Retenciones a título de renta</th>
        </tr>
        <!-- RENTAS DE TRABAJO Y PENSIONES (Solo PN) -->
        <tr>
            <td class="cas"></td>
            <td class="concepto">Rentas de trabajo</td>
            <td class="base"></td>
            <td class="ret"></td>
            <td class="cas">77</td>
            <td class="concepto">Rentas de trabajo</td>
            <td class="base">{format_money(form_data.get('77', 0))}</td>
            <td class="ret cas">93</td>
            <td class="ret">{format_money(form_data.get('93', 0))}</td>
        </tr>
        <tr>
            <td class="cas"></td>
            <td class="concepto">Rentas de pensiones</td>
            <td class="base"></td>
            <td class="ret"></td>
            <td class="cas">78</td>
            <td class="concepto">Rentas de pensiones</td>
            <td class="base">{format_money(form_data.get('78', 0))}</td>
            <td class="ret cas">94</td>
            <td class="ret">{format_money(form_data.get('94', 0))}</td>
        </tr>
        <!-- HONORARIOS -->
        <tr>
            <td class="cas">29</td>
            <td class="concepto">Honorarios</td>
            <td class="base">{format_money(form_data.get('29', 0))}</td>
            <td class="ret cas">42</td>
            <td class="ret">{format_money(form_data.get('42', 0))}</td>
            <td class="cas">79</td>
            <td class="concepto">Honorarios</td>
            <td class="base">{format_money(form_data.get('79', 0))}</td>
            <td class="ret cas">95</td>
            <td class="ret">{format_money(form_data.get('95', 0))}</td>
        </tr>
        <!-- COMISIONES -->
        <tr>
            <td class="cas">30</td>
            <td class="concepto">Comisiones</td>
            <td class="base">{format_money(form_data.get('30', 0))}</td>
            <td class="ret cas">43</td>
            <td class="ret">{format_money(form_data.get('43', 0))}</td>
            <td class="cas">80</td>
            <td class="concepto">Comisiones</td>
            <td class="base">{format_money(form_data.get('80', 0))}</td>
            <td class="ret cas">96</td>
            <td class="ret">{format_money(form_data.get('96', 0))}</td>
        </tr>
        <!-- SERVICIOS -->
        <tr>
            <td class="cas">31</td>
            <td class="concepto">Servicios</td>
            <td class="base">{format_money(form_data.get('31', 0))}</td>
            <td class="ret cas">44</td>
            <td class="ret">{format_money(form_data.get('44', 0))}</td>
            <td class="cas">81</td>
            <td class="concepto">Servicios</td>
            <td class="base">{format_money(form_data.get('81', 0))}</td>
            <td class="ret cas">97</td>
            <td class="ret">{format_money(form_data.get('97', 0))}</td>
        </tr>
        <!-- RENDIMIENTOS FINANCIEROS -->
        <tr>
            <td class="cas">32</td>
            <td class="concepto">Rendimientos financieros e intereses</td>
            <td class="base">{format_money(form_data.get('32', 0))}</td>
            <td class="ret cas">45</td>
            <td class="ret">{format_money(form_data.get('45', 0))}</td>
            <td class="cas">82</td>
            <td class="concepto">Rendimientos financieros e intereses</td>
            <td class="base">{format_money(form_data.get('82', 0))}</td>
            <td class="ret cas">98</td>
            <td class="ret">{format_money(form_data.get('98', 0))}</td>
        </tr>
        <!-- ARRENDAMIENTOS -->
        <tr>
            <td class="cas">33</td>
            <td class="concepto">Arrendamientos (Muebles e inmuebles)</td>
            <td class="base">{format_money(form_data.get('33', 0))}</td>
            <td class="ret cas">46</td>
            <td class="ret">{format_money(form_data.get('46', 0))}</td>
            <td class="cas">83</td>
            <td class="concepto">Arrendamientos (Muebles e inmuebles)</td>
            <td class="base">{format_money(form_data.get('83', 0))}</td>
            <td class="ret cas">99</td>
            <td class="ret">{format_money(form_data.get('99', 0))}</td>
        </tr>
        <!-- REGALÍAS -->
        <tr>
            <td class="cas">34</td>
            <td class="concepto">Regalías y explotación de la propiedad intelectual</td>
            <td class="base">{format_money(form_data.get('34', 0))}</td>
            <td class="ret cas">47</td>
            <td class="ret">{format_money(form_data.get('47', 0))}</td>
            <td class="cas">84</td>
            <td class="concepto">Regalías y explotación de la propiedad intelectual</td>
            <td class="base">{format_money(form_data.get('84', 0))}</td>
            <td class="ret cas">100</td>
            <td class="ret">{format_money(form_data.get('100', 0))}</td>
        </tr>
        <!-- DIVIDENDOS -->
        <tr>
            <td class="cas">35</td>
            <td class="concepto">Dividendos y participaciones</td>
            <td class="base">{format_money(form_data.get('35', 0))}</td>
            <td class="ret cas">48</td>
            <td class="ret">{format_money(form_data.get('48', 0))}</td>
            <td class="cas">85</td>
            <td class="concepto">Dividendos y participaciones</td>
            <td class="base">{format_money(form_data.get('85', 0))}</td>
            <td class="ret cas">101</td>
            <td class="ret">{format_money(form_data.get('101', 0))}</td>
        </tr>
        <!-- COMPRAS -->
        <tr>
            <td class="cas">36</td>
            <td class="concepto">Compras</td>
            <td class="base">{format_money(form_data.get('36', 0))}</td>
            <td class="ret cas">49</td>
            <td class="ret">{format_money(form_data.get('49', 0))}</td>
            <td class="cas">86</td>
            <td class="concepto">Compras</td>
            <td class="base">{format_money(form_data.get('86', 0))}</td>
            <td class="ret cas">102</td>
            <td class="ret">{format_money(form_data.get('102', 0))}</td>
        </tr>
        <!-- TARJETAS -->
        <tr>
            <td class="cas">37</td>
            <td class="concepto">Transacciones con tarjetas débito y crédito</td>
            <td class="base">{format_money(form_data.get('37', 0))}</td>
            <td class="ret cas">50</td>
            <td class="ret">{format_money(form_data.get('50', 0))}</td>
            <td class="cas">87</td>
            <td class="concepto">Transacciones con tarjetas débito y crédito</td>
            <td class="base">{format_money(form_data.get('87', 0))}</td>
            <td class="ret cas">103</td>
            <td class="ret">{format_money(form_data.get('103', 0))}</td>
        </tr>
        <!-- CONSTRUCCIÓN -->
        <tr>
            <td class="cas">38</td>
            <td class="concepto">Contratos de construcción</td>
            <td class="base">{format_money(form_data.get('38', 0))}</td>
            <td class="ret cas">51</td>
            <td class="ret">{format_money(form_data.get('51', 0))}</td>
            <td class="cas">88</td>
            <td class="concepto">Contratos de construcción</td>
            <td class="base">{format_money(form_data.get('88', 0))}</td>
            <td class="ret cas">104</td>
            <td class="ret">{format_money(form_data.get('104', 0))}</td>
        </tr>
        <!-- ENAJENACIÓN ACTIVOS -->
        <tr>
            <td class="cas"></td>
            <td class="concepto">Enajenación de activos fijos de per. naturales ante notarios y autoridades de tránsito</td>
            <td class="base"></td>
            <td class="ret"></td>
            <td class="cas">89</td>
            <td class="concepto">Enajenación activos fijos</td>
            <td class="base">{format_money(form_data.get('89', 0))}</td>
            <td class="ret cas">105</td>
            <td class="ret">{format_money(form_data.get('105', 0))}</td>
        </tr>
        <!-- LOTERÍAS -->
        <tr>
            <td class="cas">39</td>
            <td class="concepto">Loterías, rifas, apuestas y similares</td>
            <td class="base">{format_money(form_data.get('39', 0))}</td>
            <td class="ret cas">52</td>
            <td class="ret">{format_money(form_data.get('52', 0))}</td>
            <td class="cas">90</td>
            <td class="concepto">Loterías, rifas, apuestas y similares</td>
            <td class="base">{format_money(form_data.get('90', 0))}</td>
            <td class="ret cas">106</td>
            <td class="ret">{format_money(form_data.get('106', 0))}</td>
        </tr>
        <!-- HIDROCARBUROS -->
        <tr>
            <td class="cas">40</td>
            <td class="concepto">Hidrocarburos, carbón y demás productos mineros</td>
            <td class="base">{format_money(form_data.get('40', 0))}</td>
            <td class="ret cas">53</td>
            <td class="ret">{format_money(form_data.get('53', 0))}</td>
            <td class="cas">91</td>
            <td class="concepto">Hidrocarburos, carbón y demás productos mineros</td>
            <td class="base">{format_money(form_data.get('91', 0))}</td>
            <td class="ret cas">107</td>
            <td class="ret">{format_money(form_data.get('107', 0))}</td>
        </tr>
        <!-- OTROS -->
        <tr>
            <td class="cas">41</td>
            <td class="concepto">Otros pagos sujetos a retención</td>
            <td class="base">{format_money(form_data.get('41', 0))}</td>
            <td class="ret cas">54</td>
            <td class="ret">{format_money(form_data.get('54', 0))}</td>
            <td class="cas">92</td>
            <td class="concepto">Otros pagos sujetos a retención</td>
            <td class="base">{format_money(form_data.get('92', 0))}</td>
            <td class="ret cas">108</td>
            <td class="ret">{format_money(form_data.get('108', 0))}</td>
        </tr>
    </table>

    <!-- PAGOS AL EXTERIOR -->
    <div class="section-wrap">
        <div class="section-side"><span>Pagos al exterior</span></div>
        <div class="section-main">
            <table class="ret-table">
                <tr>
                    <td class="cas">55</td>
                    <td class="concepto">Pagos o abonos en cuenta al exterior a países sin convenio</td>
                    <td class="base">{format_money(form_data.get('55', 0))}</td>
                    <td class="ret cas">57</td>
                    <td class="ret">{format_money(form_data.get('57', 0))}</td>
                    <td class="cas">109</td>
                    <td class="concepto">Pagos al exterior PN sin convenio</td>
                    <td class="base">{format_money(form_data.get('109', 0))}</td>
                    <td class="ret cas">111</td>
                    <td class="ret">{format_money(form_data.get('111', 0))}</td>
                </tr>
                <tr>
                    <td class="cas">56</td>
                    <td class="concepto">Pagos o abonos en cuenta al exterior a países con convenio vigente</td>
                    <td class="base">{format_money(form_data.get('56', 0))}</td>
                    <td class="ret cas">58</td>
                    <td class="ret">{format_money(form_data.get('58', 0))}</td>
                    <td class="cas">110</td>
                    <td class="concepto">Pagos al exterior PN con convenio</td>
                    <td class="base">{format_money(form_data.get('110', 0))}</td>
                    <td class="ret cas">112</td>
                    <td class="ret">{format_money(form_data.get('112', 0))}</td>
                </tr>
            </table>
        </div>
    </div>

    <!-- AUTORRETENCIONES -->
    <div class="section-wrap">
        <div class="section-side"><span>Autorretenciones</span></div>
        <div class="section-main">
            <table class="ret-table">
                <tr>
                    <td class="cas">59</td>
                    <td class="concepto">Contribuyentes exonerados de aportes (art. 114-1 E.T.)</td>
                    <td class="base">{format_money(form_data.get('59', 0))}</td>
                    <td class="ret cas">68</td>
                    <td class="ret">{format_money(form_data.get('68', 0))}</td>
                    <td colspan="4"></td>
                </tr>
                <tr>
                    <td class="cas">60</td>
                    <td class="concepto">Ventas</td>
                    <td class="base">{format_money(form_data.get('60', 0))}</td>
                    <td class="ret cas">69</td>
                    <td class="ret">{format_money(form_data.get('69', 0))}</td>
                    <td class="cas">113</td>
                    <td class="concepto">Ventas PN</td>
                    <td class="base">{format_money(form_data.get('113', 0))}</td>
                    <td class="ret cas">121</td>
                    <td class="ret">{format_money(form_data.get('121', 0))}</td>
                </tr>
                <tr>
                    <td class="cas">61</td>
                    <td class="concepto">Honorarios</td>
                    <td class="base">{format_money(form_data.get('61', 0))}</td>
                    <td class="ret cas">70</td>
                    <td class="ret">{format_money(form_data.get('70', 0))}</td>
                    <td class="cas">114</td>
                    <td class="concepto">Honorarios PN</td>
                    <td class="base">{format_money(form_data.get('114', 0))}</td>
                    <td class="ret cas">122</td>
                    <td class="ret">{format_money(form_data.get('122', 0))}</td>
                </tr>
                <tr>
                    <td class="cas">62</td>
                    <td class="concepto">Comisiones</td>
                    <td class="base">{format_money(form_data.get('62', 0))}</td>
                    <td class="ret cas">71</td>
                    <td class="ret">{format_money(form_data.get('71', 0))}</td>
                    <td class="cas">115</td>
                    <td class="concepto">Comisiones PN</td>
                    <td class="base">{format_money(form_data.get('115', 0))}</td>
                    <td class="ret cas">123</td>
                    <td class="ret">{format_money(form_data.get('123', 0))}</td>
                </tr>
                <tr>
                    <td class="cas">63</td>
                    <td class="concepto">Servicios</td>
                    <td class="base">{format_money(form_data.get('63', 0))}</td>
                    <td class="ret cas">72</td>
                    <td class="ret">{format_money(form_data.get('72', 0))}</td>
                    <td class="cas">116</td>
                    <td class="concepto">Servicios PN</td>
                    <td class="base">{format_money(form_data.get('116', 0))}</td>
                    <td class="ret cas">124</td>
                    <td class="ret">{format_money(form_data.get('124', 0))}</td>
                </tr>
                <tr>
                    <td class="cas">64</td>
                    <td class="concepto">Rendimientos financieros</td>
                    <td class="base">{format_money(form_data.get('64', 0))}</td>
                    <td class="ret cas">73</td>
                    <td class="ret">{format_money(form_data.get('73', 0))}</td>
                    <td class="cas">117</td>
                    <td class="concepto">Rendimientos financieros PN</td>
                    <td class="base">{format_money(form_data.get('117', 0))}</td>
                    <td class="ret cas">125</td>
                    <td class="ret">{format_money(form_data.get('125', 0))}</td>
                </tr>
                <tr>
                    <td class="cas">65</td>
                    <td class="concepto">Pagos men. provisionales de car vol (Hidrocarburos y demás prod mineros)</td>
                    <td class="base">{format_money(form_data.get('65', 0))}</td>
                    <td class="ret cas">74</td>
                    <td class="ret">{format_money(form_data.get('74', 0))}</td>
                    <td class="cas">118</td>
                    <td class="concepto">Hidrocarburos PN</td>
                    <td class="base">{format_money(form_data.get('118', 0))}</td>
                    <td class="ret cas">126</td>
                    <td class="ret">{format_money(form_data.get('126', 0))}</td>
                </tr>
                <tr>
                    <td class="cas">66</td>
                    <td class="concepto">Exportación de hidrocarburos, carbón y demás productos mineros</td>
                    <td class="base">{format_money(form_data.get('66', 0))}</td>
                    <td class="ret cas">75</td>
                    <td class="ret">{format_money(form_data.get('75', 0))}</td>
                    <td class="cas">119</td>
                    <td class="concepto">Exportación hidrocarburos PN</td>
                    <td class="base">{format_money(form_data.get('119', 0))}</td>
                    <td class="ret cas">127</td>
                    <td class="ret">{format_money(form_data.get('127', 0))}</td>
                </tr>
                <tr>
                    <td class="cas">67</td>
                    <td class="concepto">Otros conceptos</td>
                    <td class="base">{format_money(form_data.get('67', 0))}</td>
                    <td class="ret cas">76</td>
                    <td class="ret">{format_money(form_data.get('76', 0))}</td>
                    <td class="cas">120</td>
                    <td class="concepto">Otros conceptos PN</td>
                    <td class="base">{format_money(form_data.get('120', 0))}</td>
                    <td class="ret cas">128</td>
                    <td class="ret">{format_money(form_data.get('128', 0))}</td>
                </tr>
            </table>
        </div>
    </div>

    <!-- TOTALES Y LIQUIDACIÓN -->
    <table class="ret-table">
        <tr>
            <td class="concepto" colspan="6">Menos retenciones practicadas en exceso o indebidas o por operaciones anuladas, rescindidas o resueltas</td>
            <td class="ret cas">129</td>
            <td class="ret">{format_money(form_data.get('129', 0))}</td>
        </tr>
        <tr class="subtotal">
            <td class="concepto" colspan="6"><strong>Total retenciones renta y complementario</strong></td>
            <td class="ret cas">130</td>
            <td class="ret">{format_money(form_data.get('130', 0))}</td>
        </tr>
    </table>

    <!-- RETENCIONES IVA -->
    <div class="section-wrap">
        <div class="section-side"><span>A título de IVA</span></div>
        <div class="section-main">
            <table class="ret-table">
                <tr style="background:#f0f0f0;">
                    <td colspan="8" style="font-weight:bold;">Retenciones practicadas por otros impuestos</td>
                </tr>
                <tr>
                    <td class="concepto" colspan="5">A responsables del impuesto sobre las ventas</td>
                    <td class="ret cas">131</td>
                    <td class="ret">{format_money(form_data.get('131', 0))}</td>
                </tr>
                <tr>
                    <td class="concepto" colspan="5">Practicadas por servicios a no residentes o no domiciliados</td>
                    <td class="ret cas">132</td>
                    <td class="ret">{format_money(form_data.get('132', 0))}</td>
                </tr>
                <tr>
                    <td class="concepto" colspan="5">Menos retenciones practicadas en exceso o indebidas o por operaciones anuladas, rescindidas o resueltas</td>
                    <td class="ret cas">133</td>
                    <td class="ret">{format_money(form_data.get('133', 0))}</td>
                </tr>
                <tr class="subtotal">
                    <td class="concepto" colspan="5"><strong>Total retenciones IVA</strong></td>
                    <td class="ret cas">134</td>
                    <td class="ret">{format_money(form_data.get('134', 0))}</td>
                </tr>
            </table>
        </div>
    </div>

    <!-- TOTALES FINALES -->
    <div class="section-wrap">
        <div class="section-side"><span>Total</span></div>
        <div class="section-main">
            <table class="ret-table">
                <tr>
                    <td class="concepto" colspan="5">Retenciones impuesto timbre nacional</td>
                    <td class="ret cas">135</td>
                    <td class="ret">{format_money(form_data.get('135', 0))}</td>
                </tr>
                <tr class="subtotal">
                    <td class="concepto" colspan="5"><strong>Total retenciones</strong></td>
                    <td class="ret cas">136</td>
                    <td class="ret">{format_money(form_data.get('136', 0))}</td>
                </tr>
                <tr>
                    <td class="concepto" colspan="5">Sanciones</td>
                    <td class="ret cas">137</td>
                    <td class="ret">{format_money(form_data.get('137', 0))}</td>
                </tr>
                <tr class="total">
                    <td class="concepto" colspan="5"><strong>Total retenciones más sanciones</strong></td>
                    <td class="ret cas">138</td>
                    <td class="ret">{format_money(form_data.get('138', 0))}</td>
                </tr>
            </table>
        </div>
    </div>

    <!-- FIRMAS -->
    <div class="signatures">
        <div style="display:flex;gap:5px;">
            <span class="cas-inline">139</span> No. Identificación signatario
            <span style="flex:1;border-bottom:1px dotted #999;"></span>
            <span class="cas-inline">140</span> DV
        </div>
        <div class="sig-row">
            <div class="sig-box">
                <div class="sig-line">Firma del declarante o de quien lo representa</div>
                <div class="sig-label"><span class="cas-inline">981</span> Cód. Representación</div>
            </div>
            <div class="sig-box">
                <div class="sig-line">Firma Contador</div>
                <div class="sig-label"><span class="cas-inline">994</span> Con salvedades</div>
            </div>
            <div class="sig-box">
                <div class="sig-line">Revisor Fiscal</div>
            </div>
        </div>
        <div style="display:flex;gap:5px;margin-top:3px;">
            <span class="cas-inline">982</span> Código Contador o Revisor Fiscal
            <span class="cas-inline">983</span> No. Tarjeta profesional
        </div>
        <div style="display:flex;gap:10px;margin-top:5px;">
            <div>
                <span class="cas-inline">997</span> Espacio exclusivo para el sello de la entidad recaudadora<br>
                <span style="font-size:4px;">(Fecha efectiva de la transacción)</span>
            </div>
            <div style="border:1px solid #000;padding:2px 8px;">
                <span class="cas-inline">980</span> <strong>Pago total $</strong>
            </div>
        </div>
        <div style="text-align:right;font-size:4px;margin-top:2px;">
            996. Espacio para el número interno de la DIAN / Adhesivo
        </div>
    </div>

    <div class="footer">
        Documento borrador generado el {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} | {company.name}<br>
        La declaración oficial debe presentarse en www.dian.gov.co
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
        '--page-size', 'Letter',
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
        # Keep HTML for debugging
        # os.remove(html_path)
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
        print("GENERACIÓN DE FORMULARIOS DIAN - FORMATO OFICIAL EXACTO")
        print("=" * 70)

        today = date.today()
        date_from = today.replace(day=1)
        date_to = today

        company = env.company

        print(f"\nEmpresa: {company.name}")
        print(f"NIT: {company.vat}")
        print(f"Período: {date_from.strftime('%d/%m/%Y')} - {date_to.strftime('%d/%m/%Y')}")

        print("\n1. Obteniendo datos de impuestos...")
        tax_data = get_tax_data(env, date_from, date_to, company.id)
        print(f"   Registros encontrados: {len(tax_data)}")

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Formulario 300 - IVA
        print("\n2. Generando Formulario 300 (IVA)...")
        form_300_data = generate_form_300_data(tax_data)
        html_300 = generate_form_300_html(company, date_from, date_to, form_300_data)
        pdf_300_path = os.path.join(OUTPUT_DIR, f"dian_300_iva_{timestamp}.pdf")

        success, result = html_to_pdf(html_300, pdf_300_path)
        if success:
            print(f"   ✓ PDF: {pdf_300_path}")
            print(f"     IVA Generado (67): ${format_money(form_300_data.get('67', 0))}")
            print(f"     IVA Descontable (81): ${format_money(form_300_data.get('81', 0))}")
            print(f"     Saldo a Pagar (88): ${format_money(form_300_data.get('88', 0))}")
        else:
            print(f"   ✗ Error: {result}")

        # Formulario 350 - ReteFuente
        print("\n3. Generando Formulario 350 (Retención en la Fuente)...")
        form_350_data = generate_form_350_data(tax_data)
        html_350 = generate_form_350_html(company, date_from, date_to, form_350_data)
        pdf_350_path = os.path.join(OUTPUT_DIR, f"dian_350_retefuente_{timestamp}.pdf")

        success, result = html_to_pdf(html_350, pdf_350_path)
        if success:
            print(f"   ✓ PDF: {pdf_350_path}")
            print(f"     Total Retenciones Renta (130): ${format_money(form_350_data.get('130', 0))}")
            print(f"     Total Retenciones IVA (134): ${format_money(form_350_data.get('134', 0))}")
            print(f"     TOTAL A PAGAR (138): ${format_money(form_350_data.get('138', 0))}")
        else:
            print(f"   ✗ Error: {result}")

        print("\n" + "=" * 70)
        print("FORMULARIOS DIAN GENERADOS - FORMATO OFICIAL")
        print("=" * 70)
        print(f"\nArchivos en: {OUTPUT_DIR}")

        for f in sorted(os.listdir(OUTPUT_DIR)):
            if 'dian_3' in f and (f.endswith('.pdf') or f.endswith('.html')):
                size = os.path.getsize(os.path.join(OUTPUT_DIR, f))
                print(f"  - {f} ({size:,} bytes)")


if __name__ == '__main__':
    main()
