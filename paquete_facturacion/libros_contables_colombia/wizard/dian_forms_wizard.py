# -*- coding: utf-8 -*-
"""
Wizard para generar Formularios DIAN Colombia:
- Formulario 300 (IVA Bimestral)
- Formulario 350 (Retención en la Fuente Mensual)
"""
import base64
import subprocess
import os
from datetime import datetime, date
from tempfile import NamedTemporaryFile

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class DianFormsWizard(models.TransientModel):
    _name = 'dian.forms.wizard'
    _description = 'Generador de Formularios DIAN'

    # === Campos de configuración ===
    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        required=True,
        default=lambda self: self.env.company,
    )
    form_type = fields.Selection([
        ('300', 'Formulario 300 - IVA'),
        ('350', 'Formulario 350 - Retención en la Fuente'),
        ('ica', 'Formulario ICA - Industria y Comercio'),
        ('all', 'Todos los Formularios'),
    ], string='Tipo de Formulario', required=True, default='all')

    # === Período ===
    date_from = fields.Date(
        string='Fecha Desde',
        required=True,
        default=lambda self: date.today().replace(day=1),
    )
    date_to = fields.Date(
        string='Fecha Hasta',
        required=True,
        default=lambda self: date.today(),
    )

    # === Estado del wizard ===
    state = fields.Selection([
        ('draft', 'Configuración'),
        ('preview', 'Vista Previa'),
        ('done', 'Generado'),
    ], string='Estado', default='draft')

    # === Datos calculados Form 300 ===
    f300_total_ingresos = fields.Monetary(string='Total Ingresos (41)', currency_field='currency_id', readonly=True)
    f300_total_compras = fields.Monetary(string='Total Compras (55)', currency_field='currency_id', readonly=True)
    f300_iva_generado = fields.Monetary(string='IVA Generado (67)', currency_field='currency_id', readonly=True)
    f300_iva_descontable = fields.Monetary(string='IVA Descontable (81)', currency_field='currency_id', readonly=True)
    f300_saldo_pagar = fields.Monetary(string='Saldo a Pagar (88)', currency_field='currency_id', readonly=True)
    f300_saldo_favor = fields.Monetary(string='Saldo a Favor (89)', currency_field='currency_id', readonly=True)

    # === Datos calculados Form 350 ===
    f350_ret_pj = fields.Monetary(string='Retenciones PJ', currency_field='currency_id', readonly=True)
    f350_ret_pn = fields.Monetary(string='Retenciones PN', currency_field='currency_id', readonly=True)
    f350_ret_iva = fields.Monetary(string='Retenciones IVA (134)', currency_field='currency_id', readonly=True)
    f350_total = fields.Monetary(string='Total a Pagar (138)', currency_field='currency_id', readonly=True)

    # === Datos calculados Form ICA ===
    ica_municipio_id = fields.Many2one(
        'res.city',
        string='Municipio',
        domain="[('country_id.code', '=', 'CO')]",
    )
    ica_ingresos_brutos = fields.Monetary(string='Ingresos Brutos', currency_field='currency_id', readonly=True)
    ica_deducciones = fields.Monetary(string='Deducciones', currency_field='currency_id', readonly=True)
    ica_base_gravable = fields.Monetary(string='Base Gravable', currency_field='currency_id', readonly=True)
    ica_tarifa = fields.Float(string='Tarifa (x mil)', digits=(16, 2), default=11.04)
    ica_impuesto = fields.Monetary(string='Impuesto ICA', currency_field='currency_id', readonly=True)
    ica_reteica = fields.Monetary(string='ReteICA a Favor', currency_field='currency_id', readonly=True)
    ica_total = fields.Monetary(string='Total a Pagar', currency_field='currency_id', readonly=True)

    # === Archivos generados ===
    pdf_300 = fields.Binary(string='PDF Formulario 300', readonly=True)
    pdf_300_name = fields.Char(string='Nombre PDF 300', readonly=True)
    pdf_350 = fields.Binary(string='PDF Formulario 350', readonly=True)
    pdf_350_name = fields.Char(string='Nombre PDF 350', readonly=True)
    pdf_ica = fields.Binary(string='PDF Formulario ICA', readonly=True)
    pdf_ica_name = fields.Char(string='Nombre PDF ICA', readonly=True)

    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        related='company_id.currency_id',
        readonly=True,
    )

    # === Métodos de obtención de datos ===
    def _get_tax_data(self):
        """Obtener datos de impuestos del período"""
        query = """
            SELECT
                aml.id,
                aml.balance,
                aml.tax_base_amount,
                am.move_type,
                at.name::text as tax_name,
                at.amount as tax_rate,
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
        """
        self.env.cr.execute(query, (self.date_from, self.date_to, self.company_id.id))
        return self.env.cr.dictfetchall()

    def _calculate_form_300(self, tax_data):
        """Calcular datos del Formulario 300 (IVA)"""
        data = {str(k): 0 for k in range(27, 101)}

        for row in tax_data:
            tax_name = (row.get('tax_name') or '').upper()
            tax_rate = abs(float(row.get('tax_rate') or 0))
            balance = abs(float(row.get('balance') or 0))
            base = abs(float(row.get('tax_base_amount') or 0))
            move_type = row.get('move_type') or ''

            # IVA 19%
            if tax_rate == 19 or '19' in tax_name:
                if move_type in ('out_invoice', 'out_refund'):
                    data['29'] += base
                    data['63'] += balance
                else:
                    data['51'] += base
                    data['72'] += balance
            # IVA 5%
            elif tax_rate == 5 or '5%' in tax_name:
                if move_type in ('out_invoice', 'out_refund'):
                    data['27'] += base
                    data['62'] += balance
                else:
                    data['50'] += base
                    data['71'] += balance

        # Totales
        data['41'] = sum(data.get(str(k), 0) for k in range(27, 41))
        data['55'] = sum(data.get(str(k), 0) for k in range(44, 55))
        data['67'] = sum(data.get(str(k), 0) for k in range(62, 67))
        data['81'] = sum(data.get(str(k), 0) for k in range(68, 81))
        data['82'] = max(data['67'] - data['81'], 0)
        data['83'] = max(data['81'] - data['67'], 0)
        data['88'] = data['82']
        data['89'] = data['83']

        return data

    def _calculate_form_350(self, tax_data):
        """Calcular datos del Formulario 350 (Retención)"""
        data = {str(k): 0 for k in range(27, 141)}

        for row in tax_data:
            tax_name = (row.get('tax_name') or '').upper()
            balance = abs(float(row.get('balance') or 0))
            base = abs(float(row.get('tax_base_amount') or 0))
            is_company = row.get('is_company', False)

            if 'RETE' not in tax_name and 'RTE' not in tax_name:
                continue

            if 'IVA' in tax_name:
                data['131'] += base
                data['134'] += balance
            elif 'HONOR' in tax_name:
                if is_company:
                    data['29'] += base
                    data['42'] += balance
                else:
                    data['79'] += base
                    data['95'] += balance
            elif 'SERVIC' in tax_name:
                if is_company:
                    data['31'] += base
                    data['44'] += balance
                else:
                    data['81'] += base
                    data['97'] += balance
            elif 'COMPR' in tax_name:
                if is_company:
                    data['36'] += base
                    data['49'] += balance
                else:
                    data['86'] += base
                    data['102'] += balance
            else:
                if is_company:
                    data['41'] += base
                    data['54'] += balance
                else:
                    data['92'] += base
                    data['108'] += balance

        # Totales
        data['130'] = sum(data.get(str(k), 0) for k in range(42, 55))
        data['130'] += sum(data.get(str(k), 0) for k in range(95, 109))
        data['136'] = data['130'] + data['134']
        data['138'] = data['136']

        return data

    def _get_ica_data(self):
        """Obtener datos de ICA del período"""
        # Obtener ingresos brutos (cuentas 41xx) - Odoo 18 usa code_store JSONB
        query_ingresos = """
            SELECT COALESCE(SUM(ABS(aml.balance)), 0) as total
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            JOIN account_account aa ON aa.id = aml.account_id
            WHERE (aa.code_store::text LIKE '%%"41%%' OR aa.code_store::text LIKE '%%41%%')
                AND am.date >= %s
                AND am.date <= %s
                AND am.company_id = %s
                AND am.state = 'posted'
        """
        self.env.cr.execute(query_ingresos, (self.date_from, self.date_to, self.company_id.id))
        ingresos = self.env.cr.fetchone()[0] or 0

        # Obtener ReteICA practicado (a favor)
        query_reteica = """
            SELECT COALESCE(SUM(ABS(aml.balance)), 0) as total
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            LEFT JOIN account_tax at ON at.id = aml.tax_line_id
            WHERE (at.name::text ILIKE '%%reteica%%' OR at.name::text ILIKE '%%rete%%ica%%')
                AND am.date >= %s
                AND am.date <= %s
                AND am.company_id = %s
                AND am.state = 'posted'
        """
        self.env.cr.execute(query_reteica, (self.date_from, self.date_to, self.company_id.id))
        reteica = self.env.cr.fetchone()[0] or 0

        return {
            'ingresos_brutos': ingresos,
            'deducciones': 0,  # Por ahora sin deducciones
            'reteica': reteica,
        }

    def _calculate_form_ica(self, ica_data):
        """Calcular datos del Formulario ICA"""
        ingresos = ica_data.get('ingresos_brutos', 0)
        deducciones = ica_data.get('deducciones', 0)
        base = ingresos - deducciones
        tarifa = self.ica_tarifa or 11.04  # Tarifa por mil
        impuesto = base * tarifa / 1000
        reteica = ica_data.get('reteica', 0)
        total = max(impuesto - reteica, 0)

        return {
            'ingresos_brutos': ingresos,
            'deducciones': deducciones,
            'base_gravable': base,
            'tarifa': tarifa,
            'impuesto': impuesto,
            'reteica': reteica,
            'total': total,
        }

    # === Acciones ===
    def action_calculate(self):
        """Calcular datos y mostrar vista previa"""
        self.ensure_one()

        tax_data = self._get_tax_data()

        # Calcular Form 300
        f300 = self._calculate_form_300(tax_data)
        self.f300_total_ingresos = f300.get('41', 0)
        self.f300_total_compras = f300.get('55', 0)
        self.f300_iva_generado = f300.get('67', 0)
        self.f300_iva_descontable = f300.get('81', 0)
        self.f300_saldo_pagar = f300.get('88', 0)
        self.f300_saldo_favor = f300.get('89', 0)

        # Calcular Form 350
        f350 = self._calculate_form_350(tax_data)
        self.f350_ret_pj = sum(f350.get(str(k), 0) for k in range(42, 55))
        self.f350_ret_pn = sum(f350.get(str(k), 0) for k in range(95, 109))
        self.f350_ret_iva = f350.get('134', 0)
        self.f350_total = f350.get('138', 0)

        # Calcular Form ICA
        ica_data = self._get_ica_data()
        ica = self._calculate_form_ica(ica_data)
        self.ica_ingresos_brutos = ica.get('ingresos_brutos', 0)
        self.ica_deducciones = ica.get('deducciones', 0)
        self.ica_base_gravable = ica.get('base_gravable', 0)
        self.ica_impuesto = ica.get('impuesto', 0)
        self.ica_reteica = ica.get('reteica', 0)
        self.ica_total = ica.get('total', 0)

        self.state = 'preview'

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_generate_pdf(self):
        """Generar PDFs de los formularios"""
        self.ensure_one()

        tax_data = self._get_tax_data()
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        if self.form_type in ('300', 'all'):
            f300_data = self._calculate_form_300(tax_data)
            html_300 = self._generate_form_300_html(f300_data)
            pdf_content = self._html_to_pdf(html_300)
            if pdf_content:
                self.pdf_300 = base64.b64encode(pdf_content)
                self.pdf_300_name = f'DIAN_300_IVA_{timestamp}.pdf'

        if self.form_type in ('350', 'all'):
            f350_data = self._calculate_form_350(tax_data)
            html_350 = self._generate_form_350_html(f350_data)
            pdf_content = self._html_to_pdf(html_350)
            if pdf_content:
                self.pdf_350 = base64.b64encode(pdf_content)
                self.pdf_350_name = f'DIAN_350_ReteFuente_{timestamp}.pdf'

        if self.form_type in ('ica', 'all'):
            ica_data = self._get_ica_data()
            ica_calc = self._calculate_form_ica(ica_data)
            html_ica = self._generate_form_ica_html(ica_calc)
            pdf_content = self._html_to_pdf(html_ica)
            if pdf_content:
                self.pdf_ica = base64.b64encode(pdf_content)
                municipio = self.ica_municipio_id.name if self.ica_municipio_id else 'Municipal'
                self.pdf_ica_name = f'ICA_{municipio}_{timestamp}.pdf'

        self.state = 'done'

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_reset(self):
        """Volver al estado inicial"""
        self.state = 'draft'
        self.pdf_300 = False
        self.pdf_350 = False
        self.pdf_ica = False
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _html_to_pdf(self, html_content):
        """Convertir HTML a PDF"""
        try:
            with NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as html_file:
                html_file.write(html_content)
                html_path = html_file.name

            pdf_path = html_path.replace('.html', '.pdf')

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
                pdf_path,
            ]

            subprocess.run(cmd, capture_output=True, timeout=60)

            with open(pdf_path, 'rb') as pdf_file:
                pdf_content = pdf_file.read()

            os.unlink(html_path)
            os.unlink(pdf_path)

            return pdf_content
        except Exception as e:
            raise UserError(_('Error generando PDF: %s') % str(e))

    def _format_money(self, value):
        """Formatear valor monetario"""
        if not value:
            return ""
        return f"{value:,.0f}".replace(",", ".")

    def _generate_form_300_html(self, data):
        """Generar HTML del Formulario 300"""
        company = self.company_id
        nit_full = company.vat or ''
        nit, dv = (nit_full.rsplit('-', 1) + [''])[:2] if '-' in nit_full else (nit_full, '')
        bimestre = (self.date_from.month - 1) // 2 + 1

        css = self._get_dian_css()

        return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Formulario 300 - IVA</title>
    <style>{css}</style>
</head>
<body>
    <table class="header-table">
        <tr>
            <td class="logo-cell"><div class="dian-logo">DIAN</div></td>
            <td class="title-cell">
                <div class="title-main">Declaracion del Impuesto sobre las Ventas - IVA</div>
                <div class="title-sub">Lea cuidadosamente las instrucciones</div>
            </td>
            <td class="form-num-cell"><div class="form-number">300</div><div class="form-type">Privada</div></td>
        </tr>
    </table>

    <div class="period-row">
        <div class="period-cell" style="width:60px;"><span class="cas-inline">1</span> Ano<br><strong>{self.date_from.year}</strong></div>
        <div class="period-cell" style="width:60px;"><span class="cas-inline">3</span> Periodo<br><strong>{bimestre:02d}</strong></div>
        <div class="period-cell"><span class="cas-inline">4</span> Numero de formulario</div>
    </div>

    <div class="declarant-section">
        <div style="background:#e8e8e8;padding:2px 5px;font-weight:bold;font-size:6px;border-bottom:1px solid #000;">Datos del declarante</div>
        <div class="declarant-row">
            <div class="declarant-cell" style="width:100px;"><span class="cas-inline">5</span> NIT<br><strong>{nit}</strong></div>
            <div class="declarant-cell" style="width:30px;"><span class="cas-inline">6</span> DV<br><strong>{dv}</strong></div>
            <div class="declarant-cell" style="flex:1;"><span class="cas-inline">11</span> Razon social<br><strong>{company.name}</strong></div>
        </div>
    </div>

    <div class="section-container">
        <div class="section-label"><span>Resumen</span></div>
        <div class="section-content">
            <table class="form-table">
                <tr><td class="cas">41</td><td class="concepto">Total ingresos brutos</td><td class="valor">{self._format_money(data.get('41', 0))}</td></tr>
                <tr><td class="cas">55</td><td class="concepto">Total compras e importaciones brutas</td><td class="valor">{self._format_money(data.get('55', 0))}</td></tr>
                <tr class="subtotal"><td class="cas">67</td><td class="concepto">Total IVA generado</td><td class="valor">{self._format_money(data.get('67', 0))}</td></tr>
                <tr class="subtotal"><td class="cas">81</td><td class="concepto">Total IVA descontable</td><td class="valor">{self._format_money(data.get('81', 0))}</td></tr>
                <tr class="pagar"><td class="cas">88</td><td class="concepto">Total saldo a pagar</td><td class="valor">{self._format_money(data.get('88', 0))}</td></tr>
                <tr class="favor"><td class="cas">89</td><td class="concepto">Total saldo a favor</td><td class="valor">{self._format_money(data.get('89', 0))}</td></tr>
            </table>
        </div>
    </div>

    <div class="footer">
        Documento generado el {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} | {company.name}<br>
        La declaracion oficial debe presentarse en www.dian.gov.co
    </div>
</body>
</html>'''

    def _generate_form_350_html(self, data):
        """Generar HTML del Formulario 350"""
        company = self.company_id
        nit_full = company.vat or ''
        nit, dv = (nit_full.rsplit('-', 1) + [''])[:2] if '-' in nit_full else (nit_full, '')

        css = self._get_dian_css()

        return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Formulario 350 - Retencion en la Fuente</title>
    <style>{css}</style>
</head>
<body>
    <table class="header-table">
        <tr>
            <td class="logo-cell"><div class="dian-logo">DIAN</div></td>
            <td class="title-cell"><div class="title-main">Declaracion Mensual de Retenciones en la Fuente</div></td>
            <td class="form-num-cell"><div class="form-number">350</div><div class="form-type">Privada</div></td>
        </tr>
    </table>

    <div class="period-row">
        <div class="period-cell" style="width:60px;"><span class="cas-inline">1</span> Ano<br><strong>{self.date_from.year}</strong></div>
        <div class="period-cell" style="width:60px;"><span class="cas-inline">3</span> Periodo<br><strong>{self.date_from.month:02d}</strong></div>
        <div class="period-cell"><span class="cas-inline">4</span> Numero de formulario</div>
    </div>

    <div class="declarant-section">
        <div style="background:#e8e8e8;padding:2px 5px;font-weight:bold;font-size:6px;border-bottom:1px solid #000;">Datos del declarante</div>
        <div class="declarant-row">
            <div class="declarant-cell" style="width:100px;"><span class="cas-inline">5</span> NIT<br><strong>{nit}</strong></div>
            <div class="declarant-cell" style="width:30px;"><span class="cas-inline">6</span> DV<br><strong>{dv}</strong></div>
            <div class="declarant-cell" style="flex:1;"><span class="cas-inline">11</span> Razon social<br><strong>{company.name}</strong></div>
        </div>
    </div>

    <div class="section-container">
        <div class="section-label"><span>Resumen</span></div>
        <div class="section-content">
            <table class="form-table">
                <tr class="subtotal"><td class="cas">130</td><td class="concepto">Total retenciones renta y complementario</td><td class="valor">{self._format_money(data.get('130', 0))}</td></tr>
                <tr class="subtotal"><td class="cas">134</td><td class="concepto">Total retenciones IVA</td><td class="valor">{self._format_money(data.get('134', 0))}</td></tr>
                <tr class="subtotal"><td class="cas">136</td><td class="concepto">Total retenciones</td><td class="valor">{self._format_money(data.get('136', 0))}</td></tr>
                <tr class="pagar"><td class="cas">138</td><td class="concepto">Total retenciones mas sanciones</td><td class="valor">{self._format_money(data.get('138', 0))}</td></tr>
            </table>
        </div>
    </div>

    <div class="footer">
        Documento generado el {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} | {company.name}<br>
        La declaracion oficial debe presentarse en www.dian.gov.co
    </div>
</body>
</html>'''

    def _generate_form_ica_html(self, data):
        """Generar HTML del Formulario ICA"""
        company = self.company_id
        nit_full = company.vat or ''
        nit, dv = (nit_full.rsplit('-', 1) + [''])[:2] if '-' in nit_full else (nit_full, '')
        municipio = self.ica_municipio_id.name if self.ica_municipio_id else 'Municipio'
        tarifa = data.get('tarifa', 11.04)

        css = self._get_dian_css()

        return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Formulario ICA - {municipio}</title>
    <style>{css}</style>
</head>
<body>
    <table class="header-table">
        <tr>
            <td class="logo-cell"><div class="dian-logo" style="font-size:14px;">ICA</div></td>
            <td class="title-cell">
                <div class="title-main">Declaracion del Impuesto de Industria y Comercio</div>
                <div class="title-sub">{municipio}</div>
            </td>
            <td class="form-num-cell" style="background:#2e7d32;"><div class="form-number" style="font-size:18px;">ICA</div><div class="form-type">Municipal</div></td>
        </tr>
    </table>

    <div class="period-row">
        <div class="period-cell" style="width:60px;">Ano<br><strong>{self.date_from.year}</strong></div>
        <div class="period-cell" style="width:60px;">Periodo<br><strong>{self.date_from.month:02d}</strong></div>
        <div class="period-cell">Municipio<br><strong>{municipio}</strong></div>
    </div>

    <div class="declarant-section">
        <div style="background:#e8e8e8;padding:2px 5px;font-weight:bold;font-size:6px;border-bottom:1px solid #000;">Datos del declarante</div>
        <div class="declarant-row">
            <div class="declarant-cell" style="width:100px;">NIT<br><strong>{nit}</strong></div>
            <div class="declarant-cell" style="width:30px;">DV<br><strong>{dv}</strong></div>
            <div class="declarant-cell" style="flex:1;">Razon social<br><strong>{company.name}</strong></div>
        </div>
    </div>

    <div class="section-container">
        <div class="section-label"><span>Liquidacion</span></div>
        <div class="section-content">
            <table class="form-table">
                <tr><td class="cas">1</td><td class="concepto">Ingresos brutos del periodo</td><td class="valor">{self._format_money(data.get('ingresos_brutos', 0))}</td></tr>
                <tr><td class="cas">2</td><td class="concepto">(-) Deducciones</td><td class="valor">{self._format_money(data.get('deducciones', 0))}</td></tr>
                <tr class="subtotal"><td class="cas">3</td><td class="concepto">Base gravable</td><td class="valor">{self._format_money(data.get('base_gravable', 0))}</td></tr>
                <tr><td class="cas">4</td><td class="concepto">Tarifa (x mil)</td><td class="valor">{tarifa:.2f}</td></tr>
                <tr class="subtotal"><td class="cas">5</td><td class="concepto">Impuesto de ICA</td><td class="valor">{self._format_money(data.get('impuesto', 0))}</td></tr>
                <tr><td class="cas">6</td><td class="concepto">(-) ReteICA a favor</td><td class="valor">{self._format_money(data.get('reteica', 0))}</td></tr>
                <tr class="pagar"><td class="cas">7</td><td class="concepto">Total a pagar</td><td class="valor">{self._format_money(data.get('total', 0))}</td></tr>
            </table>
        </div>
    </div>

    <div class="footer">
        Documento generado el {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} | {company.name}<br>
        La declaracion oficial debe presentarse en la secretaria de hacienda de {municipio}
    </div>
</body>
</html>'''

    def _get_dian_css(self):
        """CSS para formularios DIAN"""
        return '''
@page { size: letter; margin: 5mm; }
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: Arial, sans-serif; font-size: 7px; background: white; color: #000; line-height: 1.2; }
.header-table { width: 100%; border-collapse: collapse; border: 1px solid #000; margin-bottom: 2px; table-layout: fixed; }
.header-table td { border: 1px solid #000; vertical-align: middle; }
.logo-cell { width: 55px; min-width: 55px; max-width: 55px; text-align: center; padding: 3px; }
.dian-logo { font-family: 'Arial Black', Arial, sans-serif; font-size: 18px; font-weight: bold; letter-spacing: 2px; }
.title-cell { text-align: center; padding: 5px; }
.title-main { font-size: 10px; font-weight: bold; white-space: nowrap; }
.title-sub { font-size: 6px; color: #666; }
.form-num-cell { width: 50px; min-width: 50px; max-width: 50px; text-align: center; background: #4a86c7; color: white; }
.form-number { font-size: 26px; font-weight: bold; }
.form-type { font-size: 6px; }
.period-row { display: table; width: 100%; border: 1px solid #000; border-top: none; margin-bottom: 2px; }
.period-cell { display: table-cell; border-right: 1px solid #000; padding: 2px 4px; vertical-align: top; }
.period-cell:last-child { border-right: none; }
.cas-inline { display: inline-block; background: #404040; color: white; font-size: 6px; font-weight: bold; padding: 1px 4px; min-width: 14px; text-align: center; margin-right: 3px; }
.declarant-section { border: 1px solid #000; margin-bottom: 2px; }
.declarant-row { display: flex; border-bottom: 1px solid #ccc; }
.declarant-row:last-child { border-bottom: none; }
.declarant-cell { padding: 2px 4px; border-right: 1px solid #ccc; min-height: 16px; font-size: 6px; }
.declarant-cell:last-child { border-right: none; }
.section-container { display: table; width: 100%; border: 1px solid #000; margin-bottom: 2px; }
.section-label { display: table-cell; width: 14px; background: #f0f0f0; border-right: 1px solid #000; vertical-align: middle; text-align: center; }
.section-label span { writing-mode: vertical-rl; transform: rotate(180deg); font-size: 6px; font-weight: bold; padding: 3px; }
.section-content { display: table-cell; vertical-align: top; }
table.form-table { width: 100%; border-collapse: collapse; }
table.form-table td { border: 1px solid #999; padding: 2px 4px; font-size: 7px; height: 14px; vertical-align: middle; }
table.form-table .cas { width: 18px; background: #404040; color: white; text-align: center; font-weight: bold; font-size: 6px; }
table.form-table .concepto { text-align: left; padding-left: 5px; }
table.form-table .valor { width: 80px; text-align: right; padding-right: 5px; font-family: 'Courier New', monospace; background: #fafafa; }
table.form-table tr.subtotal td { background: #e8e8e8; font-weight: bold; }
table.form-table tr.pagar td { background: #c8c8c8; font-weight: bold; }
table.form-table tr.pagar .cas { background: #000; }
table.form-table tr.favor td { background: #e0e0e0; }
.footer { font-size: 5px; color: #888; text-align: center; margin-top: 5px; padding-top: 3px; border-top: 1px solid #ddd; }
'''
