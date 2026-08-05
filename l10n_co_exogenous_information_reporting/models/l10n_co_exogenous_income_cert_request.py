# -*- coding: utf-8 -*-
import base64
import html
import re
from datetime import date, datetime

from odoo import models, fields, api, tools, _, Command
from odoo.exceptions import ValidationError, UserError


class HrIncomeCertificateRequest(models.Model):
    """Solicitud de Certificado de Ingresos y Retenciones.

    Permite al empleado o al área de RRHH solicitar la generación
    del certificado en PDF o Excel, y enviarlo por correo electrónico.
    """
    _name = 'l10n_co.exogenous_income_cert_request'
    _description = 'Solicitud de Certificado de Ingresos y Retenciones'
    _check_company_auto = True
    _order = 'request_date desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Número de Solicitud',
        required=True,
        copy=False,
        readonly=True,
        default='Nuevo',
        tracking=True
    )

    employee_id = fields.Many2one(
        'hr.employee',
        string='Empleado',
        required=True,
        tracking=True
    )

    header_id = fields.Many2one('l10n_co.exogenous_income_cert_config',
        string='Configuración del Certificado',
        required=True,
        tracking=True,
        check_company=True)

    year = fields.Integer(
        string='Año Fiscal',
        required=True,
        tracking=True
    )

    date_from = fields.Date(
        string='Fecha Desde',
        required=True,
        tracking=True
    )

    date_to = fields.Date(
        string='Fecha Hasta',
        required=True,
        tracking=True
    )

    request_date = fields.Datetime(
        string='Fecha de Solicitud',
        default=fields.Datetime.now,
        required=True,
        readonly=True,
        tracking=True
    )

    generation_date = fields.Datetime(
        string='Fecha de Generación',
        readonly=True,
        tracking=True
    )

    notes = fields.Text(
        string='Observaciones'
    )

    state = fields.Selection([
        ('draft', 'Borrador'),
        ('requested', 'Solicitado'),
        ('done', 'Generado'),
        ('cancelled', 'Cancelado')
    ], string='Estado', default='draft', required=True, tracking=True)

    company_id = fields.Many2one('res.company',
        string='Compañía',
        related='employee_id.company_id',
        store=True,
        readonly=True,
        default=lambda self: self.env.company)

    # Formato de salida
    output_format = fields.Selection([
        ('pdf', 'PDF'),
        ('excel', 'Excel'),
    ], string='Formato de Salida', default='pdf')

    # Archivos generados
    pdf_file = fields.Binary(
        string='Certificado PDF',
        readonly=True,
        attachment=True
    )
    pdf_filename = fields.Char(
        string='Nombre PDF',
        readonly=True
    )
    excel_file = fields.Binary(
        string='Certificado Excel',
        readonly=True,
        attachment=True
    )
    excel_filename = fields.Char(
        string='Nombre Excel',
        readonly=True
    )

    # Envío por correo
    send_by_email = fields.Boolean(
        string='Enviar por Correo',
        default=False,
        help='Envía el certificado al correo del empleado al generarlo'
    )
    email_sent = fields.Boolean(
        string='Correo Enviado',
        readonly=True,
        tracking=True
    )
    email_sent_date = fields.Datetime(
        string='Fecha de Envío',
        readonly=True
    )

    @api.onchange('header_id')
    def _onchange_header_id(self):
        """Actualiza año y fechas según la configuración seleccionada"""
        if self.header_id:
            self.year = self.header_id.year
            self.date_from = fields.Date.from_string(f'{self.header_id.year}-01-01')
            self.date_to = fields.Date.from_string(f'{self.header_id.year}-12-31')

    @api.model_create_multi
    def create(self, vals_list):
        """Override para asignar secuencia"""
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'l10n_co.exogenous_income_cert_request'
                ) or 'Nuevo'

        return super().create(vals_list)

    def action_request(self):
        """Marcar como solicitado"""
        self.ensure_one()
        self.state = 'requested'

    def action_generate(self):
        """Genera el certificado según el formato seleccionado"""
        self.ensure_one()

        if self.state == 'done':
            raise ValidationError(_('El certificado ya ha sido generado'))

        employee = self.employee_id
        header = self.header_id

        # Calcular valores del certificado
        values, lines_results = self._compute_certificate_values(employee, header)

        write_vals = {
            'generation_date': fields.Datetime.now(),
            'state': 'done',
        }

        if self.output_format == 'pdf':
            pdf_bytes = self._generate_pdf(employee, header, values, lines_results)
            filename = f'Certificado_Ingresos_{employee.name}_{self.year}.pdf'
            write_vals.update({
                'pdf_file': base64.b64encode(pdf_bytes),
                'pdf_filename': filename,
            })
        else:
            excel_bytes = self._generate_excel(employee, header, values, lines_results)
            filename = f'Certificado_Ingresos_{employee.name}_{self.year}.xlsx'
            write_vals.update({
                'excel_file': base64.b64encode(excel_bytes),
                'excel_filename': filename,
            })

        self.write(write_vals)

        self.message_post(
            body=_('Certificado de ingresos generado exitosamente para el período %s - %s') % (
                self.date_from, self.date_to
            )
        )

        if self.send_by_email:
            self.action_send_email()

        return True

    def _compute_certificate_values(self, employee, header):
        """Calcula los valores del certificado para un empleado.

        Returns:
            tuple: (values_dict, lines_results_dict)
        """
        values = {}
        lines_results = {}

        sorted_lines = header.line_ids.sorted(key=lambda l: l.sequence)

        for line in sorted_lines:
            key = f'val{line.sequence}'

            if line.calculation in ('sum_rule', 'sum_accounting', 'sum_rule_accounting',
                                    'average_rule', 'sum_sequence'):
                value = line.compute_line_value(
                    employee, self.date_from, self.date_to, lines_results
                )
                lines_results[line.sequence] = value
                values[key] = f"${value:,.2f}" if value else '$0.00'

            elif line.calculation == 'info' and line.information_fields_id:
                values[key] = self._get_info_value(
                    employee, line
                )

            elif line.calculation == 'date_issue':
                values[key] = (
                    header.issue_date.strftime('%d/%m/%Y')
                    if header.issue_date else ''
                )

            elif line.calculation == 'start_date_year':
                values[key] = self.date_from.strftime('%d/%m/%Y')

            elif line.calculation == 'end_date_year':
                values[key] = self.date_to.strftime('%d/%m/%Y')

            elif line.calculation.startswith('dependents_'):
                dep_values = self._get_dependent_values(employee)
                dep_map = {
                    'dependents_type_vat': 'type_vat',
                    'dependents_vat': 'vat',
                    'dependents_name': 'name',
                    'dependents_type': 'type',
                }
                dep_key = dep_map.get(line.calculation, '')
                values[key] = dep_values.get(dep_key, '')

            else:
                values[key] = ''

        # Datos fijos del retenedor (compañía)
        company = header.company_id
        partner = company.partner_id
        values.setdefault('val4', header.form_number or '')
        values.setdefault('val6', partner.vat_vd or '')
        values.setdefault('val7', partner.x_first_lastname or '')
        values.setdefault('val8', partner.x_second_lastname or '')
        values.setdefault('val9', partner.x_first_name or '')
        values.setdefault('val10', partner.x_second_name or '')
        values.setdefault('val11', company.name or '')
        values.setdefault('val12', company.street or '')
        values.setdefault('val13', company.state_id.code if company.state_id else '')
        values.setdefault('val14', company.city or '')
        values.setdefault('val33', company.city or '')
        values.setdefault('val34', company.state_id.code if company.state_id else '')
        values.setdefault('val35', company.city or '')

        for i in range(1, 7):
            values.setdefault(f'val71_{i}', '')
            values.setdefault(f'val72_{i}', '')
        values.setdefault('val73', '$0.00')

        values.update({
            'year': self.year,
            'uvt_4500': f"${header.patrimony_cop:,.2f}",
            'uvt_1400': f"${header.income_cop:,.2f}",
        })

        return values, lines_results

    def _get_info_value(self, employee, line):
        """Obtiene valor de campo de información sin usar getattr"""
        if not line.information_fields_id:
            return ''

        if line.type_partner == 'employee':
            if line.information_fields_id.model_id.model == 'hr.employee':
                source = employee
            elif line.information_fields_id.model_id.model == 'res.partner':
                # En Odoo 19 no existe address_home_id: usar partner_encab_id
                # (lavish_hr_employee) o work_contact_id (core hr).
                source = employee.partner_encab_id or employee.work_contact_id
            else:
                return ''
        elif line.type_partner == 'company':
            if line.information_fields_id.model_id.model == 'res.partner':
                source = employee.company_id.partner_id
            else:
                return ''
        else:
            return ''

        value = source[line.information_fields_id.name]

        if line.related_field_id and value:
            value = value[line.related_field_id.name]

        if isinstance(value, (int, float)):
            return f"${value:,.2f}"
        elif isinstance(value, (date, datetime)):
            return value.strftime('%d/%m/%Y')
        else:
            return str(value) if value else ''

    DOCUMENT_TYPE_MAP = {
        '11': 'RC', '12': 'TI', '13': 'CC', '21': 'TE', '22': 'CE',
        '31': 'NIT', '41': 'PA', '42': 'DE', '43': 'SI', '44': 'DIE',
        'PE': 'PEP', 'PT': 'PPT',
    }

    DEPENDENT_TYPE_MAP = {
        'hijo(a)': 'Hijo(a)', 'padre': 'Padre', 'madre': 'Madre',
        'cónyuge': 'Cónyuge', 'hermano(a)': 'Hermano(a)', 'otro': 'Otro',
    }

    def _get_dependent_values(self, employee):
        """Obtiene datos del dependiente económico marcado para reporte fiscal"""
        dependent = employee.dependents_information.filtered(
            lambda d: d.report_income_and_withholdings
        )
        if not dependent:
            return {}

        dep = dependent[0]
        return {
            'type_vat': self.DOCUMENT_TYPE_MAP.get(dep.document_type, dep.document_type or ''),
            'vat': dep.vat or '',
            'name': dep.name or '',
            'type': self.DEPENDENT_TYPE_MAP.get(dep.dependents_type, dep.dependents_type or ''),
        }

    @api.model
    @tools.ormcache()
    def _get_dian_logo_data_uri(self):
        """Devuelve el logo DIAN como data URI para embeber en wkhtmltopdf.

        El subprocess wkhtmltopdf no comparte sesión Odoo y los src relativos
        a /module/static no resuelven en el HTML inline; embebemos en base64.
        Cacheado vía ormcache para no leer el archivo en cada generación.
        """
        try:
            import os
            module_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            logo_path = os.path.join(module_path, 'static', 'img', 'dian_logo.png')
            with open(logo_path, 'rb') as f:
                return 'data:image/png;base64,' + base64.b64encode(f.read()).decode('ascii')
        except Exception:
            return ''

    def _generate_pdf(self, employee, header, values, lines_results):
        """Genera PDF del certificado renderizando el template HTML via wkhtmltopdf"""
        html_content = header.report_template or ''
        # Inyectar logo DIAN como data URI antes de los placeholders {valX}
        values = dict(values)
        values.setdefault('logo_dian', self._get_dian_logo_data_uri())
        for key, value in values.items():
            placeholder = '{' + key + '}'
            html_content = html_content.replace(placeholder, str(value) if key == 'logo_dian' else html.escape(str(value)))
        html_content = re.sub(r'\{[a-z0-9_]+\}', '', html_content)

        full_html = self._get_certificate_html_wrapper(html_content)

        try:
            # Vincular self al ir.actions.report propio para que el
            # paperformat (Letter compacto) sea respetado por wkhtmltopdf.
            IrReport = self.env.ref(
                'l10n_co_exogenous_information_reporting.'
                'action_report_income_certificate_individual')
            # _run_wkhtmltopdf escribe los bodies en archivos temporales abiertos
            # con modo 'wb', por lo que el HTML debe ir en bytes (no str).
            # Márgenes mínimos para que el certificado quepa en 1 hoja carta.
            pdf_content = IrReport._run_wkhtmltopdf(
                [full_html.encode('utf-8')],
                landscape=False,
                specific_paperformat_args={
                    'data-report-margin-top': 5,
                    'data-report-margin-bottom': 5,
                    'data-report-header-spacing': 0,
                }
            )
            return pdf_content
        except Exception:
            return self._generate_pdf_fallback(employee, header, lines_results)

    def _get_certificate_html_wrapper(self, body_html):
        """Envuelve el contenido HTML del certificado con estilos CSS completos.

        Optimizado para que el certificado (Form 220 DIAN) quepa en UNA hoja
        carta. Márgenes pequeños, padding=0 en body y page-break-inside:avoid
        en tablas para evitar cortes.
        """
        return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/>
<style>
    @page {{ size: legal; margin: 5mm 5mm 5mm 5mm; }}
    html, body {{ margin: 0; padding: 0; }}
    body {{
        font-family: Arial, sans-serif; font-size: 8px;
        -webkit-print-color-adjust: exact;
    }}
    .container-fluid {{ width: 100%; max-width: 100%; }}
    table {{ page-break-inside: avoid; }}
    .table {{ width: 100%; border-collapse: collapse; margin-bottom: 0; }}
    .table td, .table th {{ border: 1px solid #555; padding: 1px 3px; font-size: 7.5px; line-height: 1.1; }}
    .table-bordered {{ border: 1px solid #555; }}
    .table-sm td, .table-sm th {{ padding: 1px 2px; }}
    .table-striped tbody tr:nth-of-type(odd) {{ background-color: #f5f5f5; }}
    .text-center {{ text-align: center; }}
    .text-end {{ text-align: right; }}
    .fw-bold, strong {{ font-weight: bold; }}
    .fw-normal {{ font-weight: normal; }}
    .bg-light {{ background-color: #eee; }}
    .table-secondary {{ background-color: #d6d6d6; }}
    .table-primary {{ background-color: #cfe2ff; }}
    .table-info {{ background-color: #cff4fc; }}
    .table-warning {{ background-color: #fff3cd; }}
    .align-middle {{ vertical-align: middle; }}
    .small {{ font-size: 6.5px; }}
    .mt-2 {{ margin-top: 4px; }}
    .mb-0 {{ margin-bottom: 0; }}
    .p-0 {{ padding: 0; }}
    h5 {{ font-size: 11px; margin: 3px 0; }}
    /* Fuerza que toda la plantilla DIAN del usuario respete el ancho útil */
    div[style*="max-width"] {{ max-width: 100% !important; }}
</style>
</head><body>{body_html}</body></html>"""

    def _generate_pdf_fallback(self, employee, header, lines_results):
        """Fallback PDF en HTML mínimo cuando _run_wkhtmltopdf falla.

        Adaptación a Odoo 14: el módulo `lavish_tool_report` (PdfReportBuilder)
        y el modelo `pdf.report.service` no están disponibles en este sistema,
        así que armamos un HTML simple y lo pasamos al wkhtmltopdf nativo. Si
        ESO también falla, raise UserError con mensaje claro al usuario.
        """
        from .l10n_co_exogenous_income_cert_config import RENGLON_NAMES
        company = header.company_id

        numeric_lines = header.line_ids.filtered(
            lambda l: l.calculation in (
                'sum_rule', 'sum_accounting', 'sum_rule_accounting',
                'average_rule', 'sum_sequence'
            )
        ).sorted(key=lambda l: l.sequence)

        rows_html = []
        for line in numeric_lines:
            label = html.escape(RENGLON_NAMES.get(line.sequence, f'Campo {line.sequence}'))
            value = lines_results.get(line.sequence, 0.0)
            rows_html.append(
                f'<tr><td>{label}</td>'
                f'<td style="text-align:center;">{line.sequence}</td>'
                f'<td style="text-align:right;">${value:,.2f}</td></tr>'
            )

        body = f"""
        <h2 style="text-align:center;">Certificado de Ingresos y Retenciones - {self.year}</h2>
        <p><strong>Empresa:</strong> {html.escape(company.name or '')}
           &nbsp;&nbsp; <strong>NIT:</strong> {html.escape(company.partner_id.vat or '')}</p>
        <p><strong>Empleado:</strong> {html.escape(employee.name or '')}
           &nbsp;&nbsp; <strong>Período:</strong>
           {self.date_from.strftime('%d/%m/%Y')} - {self.date_to.strftime('%d/%m/%Y')}</p>
        <table class="table table-bordered" style="width:100%;border-collapse:collapse;margin-top:10px;">
          <thead style="background:#eee;">
            <tr><th>Concepto</th><th>Renglón</th><th style="text-align:right;">Valor</th></tr>
          </thead>
          <tbody>{''.join(rows_html)}</tbody>
        </table>
        <p style="margin-top:30px;font-size:10px;color:#555;">
          Generado el {fields.Datetime.now().strftime('%Y-%m-%d %H:%M')} por {html.escape(self.env.user.name or '')}.
        </p>
        """
        full_html = self._get_certificate_html_wrapper(body)
        try:
            return self.env['ir.actions.report']._run_wkhtmltopdf(
                [full_html.encode('utf-8')], landscape=False)
        except Exception as e:
            raise UserError(_(
                'No se pudo generar el PDF del certificado. '
                'Verifique que wkhtmltopdf esté instalado correctamente. '
                'Detalle: %s'
            ) % str(e))

    def _generate_excel(self, employee, header, values, lines_results):
        """Genera Excel del certificado con layout DIAN usando xlsxwriter"""
        import io
        import xlsxwriter
        from .l10n_co_exogenous_income_cert_config import RENGLON_NAMES

        output = io.BytesIO()
        wb = xlsxwriter.Workbook(output, {'in_memory': True})
        ws = wb.add_worksheet('Certificado')

        # Formatos
        title_fmt = wb.add_format({
            'bold': True, 'font_size': 12, 'align': 'center',
            'valign': 'vcenter', 'text_wrap': True, 'border': 1,
        })
        section_fmt = wb.add_format({
            'bold': True, 'font_size': 9, 'align': 'center',
            'bg_color': '#D6D6D6', 'border': 1,
        })
        label_fmt = wb.add_format({
            'font_size': 8, 'align': 'left', 'border': 1,
            'text_wrap': True, 'valign': 'vcenter',
        })
        label_bold_fmt = wb.add_format({
            'bold': True, 'font_size': 8, 'align': 'left', 'border': 1,
            'text_wrap': True, 'valign': 'vcenter',
        })
        value_fmt = wb.add_format({
            'font_size': 8, 'align': 'right', 'border': 1,
            'num_format': '$#,##0',
        })
        total_label_fmt = wb.add_format({
            'bold': True, 'font_size': 8, 'align': 'left',
            'bg_color': '#CFE2FF', 'border': 1,
        })
        total_value_fmt = wb.add_format({
            'bold': True, 'font_size': 8, 'align': 'right',
            'bg_color': '#CFE2FF', 'border': 1, 'num_format': '$#,##0',
        })
        reten_label_fmt = wb.add_format({
            'bold': True, 'font_size': 8, 'align': 'left',
            'bg_color': '#CFF4FC', 'border': 1,
        })
        reten_value_fmt = wb.add_format({
            'bold': True, 'font_size': 8, 'align': 'right',
            'bg_color': '#CFF4FC', 'border': 1, 'num_format': '$#,##0',
        })
        info_fmt = wb.add_format({
            'font_size': 8, 'align': 'left', 'border': 1,
        })
        num_fmt = wb.add_format({
            'font_size': 8, 'align': 'center', 'border': 1,
        })

        ws.set_column('A:A', 8)
        ws.set_column('B:B', 45)
        ws.set_column('C:C', 18)
        ws.set_column('D:D', 8)
        ws.set_column('E:E', 18)

        row = 0

        # Titulo
        ws.merge_range(row, 0, row + 1, 4,
            f'Certificado de Ingresos y Retenciones por Rentas de Trabajo y Pensiones\n'
            f'Año Gravable {self.year}', title_fmt)
        row += 3

        # Datos del Retenedor
        ws.merge_range(row, 0, row, 4, 'DATOS DEL RETENEDOR', section_fmt)
        row += 1
        retenedor_data = [
            ('5', 'NIT', values.get('val5', '')),
            ('6', 'D.V.', values.get('val6', '')),
            ('11', 'Razón Social', values.get('val11', '')),
            ('12', 'Dirección', values.get('val12', '')),
            ('13', 'Cód. Departamento', values.get('val13', '')),
            ('14', 'Cód. Ciudad/Municipio', values.get('val14', '')),
        ]
        for seq, concept, val in retenedor_data:
            ws.write(row, 0, seq, num_fmt)
            ws.write(row, 1, concept, label_fmt)
            ws.merge_range(row, 2, row, 4, str(val), info_fmt)
            row += 1

        # Datos del Empleado
        row += 1
        ws.merge_range(row, 0, row, 4, 'DATOS DEL EMPLEADO', section_fmt)
        row += 1
        empleado_data = [
            ('24', 'Tipo Documento', values.get('val24', '')),
            ('25', 'Identificación', values.get('val25', '')),
            ('26', 'Primer Apellido', values.get('val26', '')),
            ('27', 'Segundo Apellido', values.get('val27', '')),
            ('28', 'Primer Nombre', values.get('val28', '')),
            ('29', 'Otros Nombres', values.get('val29', '')),
        ]
        for seq, concept, val in empleado_data:
            ws.write(row, 0, seq, num_fmt)
            ws.write(row, 1, concept, label_fmt)
            ws.merge_range(row, 2, row, 4, str(val), info_fmt)
            row += 1

        # Periodo
        row += 1
        ws.write(row, 0, '', num_fmt)
        ws.write(row, 1, f'Período: DE {values.get("val30", "")} A {values.get("val31", "")}', label_bold_fmt)
        ws.merge_range(row, 2, row, 4, f'Expedición: {values.get("val32", "")}', info_fmt)
        row += 2

        # Concepto de los Ingresos
        ws.merge_range(row, 0, row, 4, 'CONCEPTO DE LOS INGRESOS', section_fmt)
        row += 1
        ws.write(row, 0, 'Reng.', label_bold_fmt)
        ws.write(row, 1, 'Concepto', label_bold_fmt)
        ws.merge_range(row, 2, row, 4, 'Valor', label_bold_fmt)
        row += 1
        for seq in range(36, 49):
            val = lines_results.get(seq, 0.0)
            ws.write(row, 0, str(seq), num_fmt)
            ws.write(row, 1, RENGLON_NAMES.get(seq, f'Campo {seq}'), label_fmt)
            ws.merge_range(row, 2, row, 4, val, value_fmt)
            row += 1
        # Total 49
        ws.write(row, 0, '49', num_fmt)
        ws.write(row, 1, RENGLON_NAMES.get(49, 'Total ingresos brutos'), total_label_fmt)
        ws.merge_range(row, 2, row, 4, lines_results.get(49, 0.0), total_value_fmt)
        row += 2

        # Concepto de los Aportes
        ws.merge_range(row, 0, row, 4, 'CONCEPTO DE LOS APORTES', section_fmt)
        row += 1
        for seq in range(50, 55):
            val = lines_results.get(seq, 0.0)
            ws.write(row, 0, str(seq), num_fmt)
            ws.write(row, 1, RENGLON_NAMES.get(seq, f'Campo {seq}'), label_fmt)
            ws.merge_range(row, 2, row, 4, val, value_fmt)
            row += 1
        # Retencion 55
        ws.write(row, 0, '55', num_fmt)
        ws.write(row, 1, RENGLON_NAMES.get(55, 'Retención en la fuente'), reten_label_fmt)
        ws.merge_range(row, 2, row, 4, lines_results.get(55, 0.0), reten_value_fmt)
        row += 2

        # Datos a cargo del trabajador
        ws.merge_range(row, 0, row, 4, 'DATOS A CARGO DEL TRABAJADOR O PENSIONADO', section_fmt)
        row += 1
        ws.write(row, 0, 'Reng.', label_bold_fmt)
        ws.write(row, 1, 'Concepto', label_bold_fmt)
        ws.write(row, 2, 'Valor Recibido', label_bold_fmt)
        ws.write(row, 3, 'Reng.', label_bold_fmt)
        ws.write(row, 4, 'Valor Retenido', label_bold_fmt)
        row += 1
        pairs = [(56, 63), (57, 64), (58, 65), (59, 66), (60, 67), (61, 68)]
        for seq_r, seq_ret in pairs:
            ws.write(row, 0, str(seq_r), num_fmt)
            ws.write(row, 1, RENGLON_NAMES.get(seq_r, f'Campo {seq_r}'), label_fmt)
            ws.write(row, 2, lines_results.get(seq_r, 0.0), value_fmt)
            ws.write(row, 3, str(seq_ret), num_fmt)
            ws.write(row, 4, lines_results.get(seq_ret, 0.0), value_fmt)
            row += 1
        # Totales 62, 69
        ws.write(row, 0, '62', num_fmt)
        ws.write(row, 1, 'Totales', total_label_fmt)
        ws.write(row, 2, lines_results.get(62, 0.0), total_value_fmt)
        ws.write(row, 3, '69', num_fmt)
        ws.write(row, 4, lines_results.get(69, 0.0), total_value_fmt)
        row += 1
        # Total retenciones 70
        ws.write(row, 0, '70', num_fmt)
        ws.merge_range(row, 1, row, 2, RENGLON_NAMES.get(70, 'Total retenciones'), total_label_fmt)
        ws.merge_range(row, 3, row, 4, lines_results.get(70, 0.0), total_value_fmt)
        row += 2

        # Patrimonio
        ws.merge_range(row, 0, row, 4, 'PATRIMONIO', section_fmt)
        row += 1
        for i in range(1, 7):
            ws.write(row, 0, str(i), num_fmt)
            ws.write(row, 1, values.get(f'val71_{i}', ''), label_fmt)
            ws.merge_range(row, 2, row, 4, values.get(f'val72_{i}', ''), info_fmt)
            row += 1
        ws.write(row, 0, '73', num_fmt)
        ws.write(row, 1, RENGLON_NAMES.get(73, 'Deudas vigentes'), reten_label_fmt)
        ws.merge_range(row, 2, row, 4, lines_results.get(73, 0.0), reten_value_fmt)
        row += 2

        # Dependientes
        ws.merge_range(row, 0, row, 4, 'DEPENDIENTE ECONÓMICO', section_fmt)
        row += 1
        dep_data = [
            ('74', 'Tipo documento', values.get('val74', '')),
            ('75', 'No. Documento', values.get('val75', '')),
            ('76', 'Apellidos y Nombres', values.get('val76', '')),
            ('77', 'Parentesco', values.get('val77', '')),
        ]
        for seq, concept, val in dep_data:
            ws.write(row, 0, seq, num_fmt)
            ws.write(row, 1, concept, label_fmt)
            ws.merge_range(row, 2, row, 4, str(val), info_fmt)
            row += 1

        # Certificación UVT
        row += 1
        uvt_text = (
            f'Certifico que durante el año gravable {self.year}:\n'
            f'1. Mi patrimonio bruto no excedió de 4.500 UVT ({values.get("uvt_4500", "")})\n'
            f'2. Mis ingresos brutos fueron inferiores a 1.400 UVT ({values.get("uvt_1400", "")})\n'
            f'3. No fui responsable del impuesto sobre las ventas\n'
            f'4. Mis consumos mediante tarjeta de crédito no excedieron 1.400 UVT ({values.get("uvt_1400", "")})\n'
            f'5. Total de compras y consumos no superaron 1.400 UVT ({values.get("uvt_1400", "")})\n'
            f'6. Consignaciones bancarias no excedieron 1.400 UVT ({values.get("uvt_1400", "")})'
        )
        text_fmt = wb.add_format({
            'font_size': 7, 'text_wrap': True, 'border': 1, 'valign': 'top',
        })
        ws.merge_range(row, 0, row + 5, 4, uvt_text, text_fmt)

        wb.close()
        output.seek(0)
        return output.read()

    def action_send_email(self):
        """Envía el certificado por correo al empleado"""
        self.ensure_one()

        if self.state != 'done':
            raise ValidationError(_('Debe generar el certificado antes de enviarlo'))

        template = self.env.ref(
            'lavish_hr_employee.email_template_certificate_income',
            raise_if_not_found=False
        )

        if not template:
            raise ValidationError(_(
                'No se encontró la plantilla de correo para certificado de ingresos. '
                'Verifique que el módulo esté correctamente instalado.'
            ))

        # Adjuntar el archivo generado
        attachment_vals = {}
        if self.pdf_file and self.pdf_filename:
            attachment_vals = {
                'name': self.pdf_filename,
                'datas': self.pdf_file,
                'res_model': self._name,
                'res_id': self.id,
                'type': 'binary',
            }
        elif self.excel_file and self.excel_filename:
            attachment_vals = {
                'name': self.excel_filename,
                'datas': self.excel_file,
                'res_model': self._name,
                'res_id': self.id,
                'type': 'binary',
            }

        if attachment_vals:
            attachment = self.env['ir.attachment'].create(attachment_vals)
            template.attachment_ids = [(6, 0, [attachment.id])]

        template.send_mail(self.id, force_send=True)

        # Limpiar adjuntos del template
        if attachment_vals:
            template.attachment_ids = [Command.clear()]

        self.write({
            'email_sent': True,
            'email_sent_date': fields.Datetime.now(),
        })

        self.message_post(
            body=_('Certificado enviado por correo a %s') % (
                self.employee_id.work_email or self.employee_id.private_email or 'sin correo'
            )
        )

        return True

    def action_generate_and_send(self):
        """Genera el certificado y lo envía por correo en un solo paso"""
        self.ensure_one()
        self.send_by_email = True
        return self.action_generate()

    def action_cancel(self):
        """Cancelar la solicitud"""
        self.ensure_one()
        self.state = 'cancelled'

    def action_draft(self):
        """Volver a borrador"""
        self.ensure_one()
        self.write({
            'state': 'draft',
            'pdf_file': False,
            'pdf_filename': False,
            'excel_file': False,
            'excel_filename': False,
            'email_sent': False,
            'email_sent_date': False,
            'generation_date': False,
        })

    # =========================================================================
    # PREVIEW Y QWEB REPORT
    # =========================================================================

    preview_html = fields.Html(
        string='Vista Previa del Certificado',
        compute='_compute_preview_html',
        sanitize=False
    )

    @api.depends('employee_id', 'header_id', 'date_from', 'date_to', 'year')
    def _compute_preview_html(self):
        """Genera HTML de vista previa del certificado"""
        for record in self:
            if not record.employee_id or not record.header_id:
                record.preview_html = '<div class="text-muted text-center p-4">Seleccione un empleado y configuración para ver la vista previa</div>'
                continue

            try:
                cert_data = record.get_certificate_data()
                record.preview_html = record._render_preview_html(cert_data)
            except Exception as e:
                record.preview_html = f'<div class="alert alert-warning">Error generando vista previa: {str(e)}</div>'

    def get_certificate_data(self):
        """Obtiene todos los datos del certificado para QWeb y preview.

        Returns:
            dict: Diccionario con todos los valores del certificado
        """
        self.ensure_one()

        if not self.employee_id or not self.header_id:
            return {}

        employee = self.employee_id
        header = self.header_id

        # Obtener valores calculados
        values, lines_results = self._compute_certificate_values(employee, header)

        # Agregar líneas estructuradas para el template QWeb
        from .l10n_co_exogenous_income_cert_config import RENGLON_NAMES

        # Líneas de ingresos (36-49)
        income_lines = []
        for seq in range(36, 49):
            income_lines.append({
                'concept': RENGLON_NAMES.get(seq, f'Campo {seq}'),
                'renglon': str(seq),
                'value': self._format_currency(lines_results.get(seq, 0)),
                'is_total': False,
            })
        # Total de ingresos (49)
        income_lines.append({
            'concept': RENGLON_NAMES.get(49, 'Total ingresos brutos'),
            'renglon': '49',
            'value': self._format_currency(lines_results.get(49, 0)),
            'is_total': True,
        })

        # Líneas de aportes (50-55)
        contribution_lines = []
        for seq in range(50, 55):
            contribution_lines.append({
                'concept': RENGLON_NAMES.get(seq, f'Campo {seq}'),
                'renglon': str(seq),
                'value': self._format_currency(lines_results.get(seq, 0)),
                'is_retention': False,
            })
        # Retención (55)
        contribution_lines.append({
            'concept': RENGLON_NAMES.get(55, 'Retención en la fuente'),
            'renglon': '55',
            'value': self._format_currency(lines_results.get(55, 0)),
            'is_retention': True,
        })

        # Líneas a cargo del trabajador (56-70)
        worker_lines = []
        pairs = [(56, 63), (57, 64), (58, 65), (59, 66), (60, 67), (61, 68)]
        for seq_r, seq_ret in pairs:
            worker_lines.append({
                'concept': RENGLON_NAMES.get(seq_r, f'Campo {seq_r}'),
                'renglon_received': str(seq_r),
                'value_received': self._format_currency(lines_results.get(seq_r, 0)),
                'renglon_retained': str(seq_ret),
                'value_retained': self._format_currency(lines_results.get(seq_ret, 0)),
                'is_total': False,
                'is_grand_total': False,
            })
        # Totales (62, 69)
        worker_lines.append({
            'concept': 'Totales',
            'renglon_received': '62',
            'value_received': self._format_currency(lines_results.get(62, 0)),
            'renglon_retained': '69',
            'value_retained': self._format_currency(lines_results.get(69, 0)),
            'is_total': True,
            'is_grand_total': False,
        })
        # Total retenciones (70)
        worker_lines.append({
            'concept': f'Total retenciones año gravable {self.year} (Sume 55 + 69)',
            'renglon_retained': '70',
            'value_retained': self._format_currency(lines_results.get(70, 0)),
            'is_total': False,
            'is_grand_total': True,
        })

        # Combinar todo
        result = dict(values)
        result.update({
            'income_lines': income_lines,
            'contribution_lines': contribution_lines,
            'worker_lines': worker_lines,
        })

        return result

    def _format_currency(self, value):
        """Formatea un valor como moneda colombiana"""
        if not value:
            return '$0'
        return f"${value:,.0f}".replace(',', '.')

    def _render_preview_html(self, cert_data):
        """Renderiza el HTML de vista previa del certificado"""
        year = self.year
        employee = self.employee_id
        company = self.company_id
        header = self.header_id

        # Generar HTML compacto para preview
        html = f'''
        <div style="font-family: Arial, sans-serif; font-size: 11px; max-width: 100%; margin: 0 auto; border: 1px solid #ccc; padding: 15px; background: #fff;">
            <!-- Encabezado -->
            <table style="width: 100%; border-collapse: collapse; border: 2px solid #003366; margin-bottom: 10px;">
                <tr>
                    <td style="width: 12%; padding: 8px; border: 1px solid #003366; text-align: center;">
                        <div style="font-size: 18px; font-weight: bold; color: #003366;">220</div>
                        <div style="font-size: 8px; color: #666;">Formato DIAN</div>
                    </td>
                    <td style="width: 76%; padding: 8px; text-align: center; border: 1px solid #003366;">
                        <div style="font-size: 14px; font-weight: bold; color: #003366;">
                            Certificado de Ingresos y Retenciones<br/>
                            Año Gravable {year}
                        </div>
                    </td>
                    <td style="width: 12%; padding: 8px; border: 1px solid #003366; font-size: 9px;">
                        <strong>4. No. Form</strong><br/>
                        {header.form_number or '-'}
                    </td>
                </tr>
            </table>

            <!-- Datos del Retenedor -->
            <table style="width: 100%; border-collapse: collapse; border: 1px solid #003366; margin-bottom: 5px;">
                <tr style="background: #003366; color: white;">
                    <td colspan="4" style="padding: 4px 8px; font-weight: bold; font-size: 10px;">DATOS DEL RETENEDOR</td>
                </tr>
                <tr>
                    <td style="padding: 4px; border: 1px solid #99b3cc; background: #e8f0fe; font-size: 9px; width: 15%;"><strong>5. NIT</strong></td>
                    <td style="padding: 4px; border: 1px solid #99b3cc; width: 35%;">{cert_data.get('val5', '-')}</td>
                    <td style="padding: 4px; border: 1px solid #99b3cc; background: #e8f0fe; font-size: 9px; width: 15%;"><strong>11. Razón Social</strong></td>
                    <td style="padding: 4px; border: 1px solid #99b3cc; width: 35%;">{cert_data.get('val11', '-')}</td>
                </tr>
            </table>

            <!-- Datos del Empleado -->
            <table style="width: 100%; border-collapse: collapse; border: 1px solid #003366; margin-bottom: 5px;">
                <tr style="background: #003366; color: white;">
                    <td colspan="4" style="padding: 4px 8px; font-weight: bold; font-size: 10px;">DATOS DEL TRABAJADOR</td>
                </tr>
                <tr>
                    <td style="padding: 4px; border: 1px solid #99b3cc; background: #e8f0fe; font-size: 9px; width: 15%;"><strong>25. Identificación</strong></td>
                    <td style="padding: 4px; border: 1px solid #99b3cc; width: 35%;">{cert_data.get('val25', '-')}</td>
                    <td style="padding: 4px; border: 1px solid #99b3cc; background: #e8f0fe; font-size: 9px; width: 15%;"><strong>Nombre</strong></td>
                    <td style="padding: 4px; border: 1px solid #99b3cc; width: 35%;">{employee.name}</td>
                </tr>
                <tr>
                    <td style="padding: 4px; border: 1px solid #99b3cc; background: #e8f0fe; font-size: 9px;"><strong>Período</strong></td>
                    <td colspan="3" style="padding: 4px; border: 1px solid #99b3cc;">
                        {cert_data.get('val30', '-')} a {cert_data.get('val31', '-')}
                    </td>
                </tr>
            </table>

            <!-- Ingresos -->
            <table style="width: 100%; border-collapse: collapse; border: 1px solid #003366; margin-bottom: 5px; font-size: 10px;">
                <tr style="background: #003366; color: white;">
                    <td colspan="3" style="padding: 4px 8px; font-weight: bold;">CONCEPTO DE LOS INGRESOS</td>
                </tr>
                <tr style="background: #336699; color: white; font-size: 9px;">
                    <td style="padding: 3px 6px; border: 1px solid #003366; width: 70%;">Concepto</td>
                    <td style="padding: 3px 6px; border: 1px solid #003366; width: 8%; text-align: center;">Reng.</td>
                    <td style="padding: 3px 6px; border: 1px solid #003366; width: 22%; text-align: right;">Valor</td>
                </tr>
        '''

        # Agregar líneas de ingresos
        for i, line in enumerate(cert_data.get('income_lines', [])):
            bg = '#fafcff' if i % 2 else '#fff'
            if line.get('is_total'):
                bg = '#ccdbe8'
            html += f'''
                <tr>
                    <td style="padding: 3px 6px; border: 1px solid #99b3cc; background: {bg};">{line.get('concept', '')}</td>
                    <td style="padding: 3px 6px; border: 1px solid #99b3cc; text-align: center; background: #f0f4f8; color: #003366; font-weight: bold;">{line.get('renglon', '')}</td>
                    <td style="padding: 3px 6px; border: 1px solid #99b3cc; text-align: right; background: {bg};">{line.get('value', '$0')}</td>
                </tr>
            '''

        html += '''
            </table>

            <!-- Aportes -->
            <table style="width: 100%; border-collapse: collapse; border: 1px solid #003366; margin-bottom: 5px; font-size: 10px;">
                <tr style="background: #003366; color: white;">
                    <td colspan="3" style="padding: 4px 8px; font-weight: bold;">CONCEPTO DE LOS APORTES</td>
                </tr>
        '''

        for line in cert_data.get('contribution_lines', []):
            bg = '#d4e6f1' if line.get('is_retention') else '#fff'
            html += f'''
                <tr>
                    <td style="padding: 3px 6px; border: 1px solid #99b3cc; background: {bg}; width: 70%;">{line.get('concept', '')}</td>
                    <td style="padding: 3px 6px; border: 1px solid #99b3cc; text-align: center; background: #f0f4f8; color: #003366; font-weight: bold; width: 8%;">{line.get('renglon', '')}</td>
                    <td style="padding: 3px 6px; border: 1px solid #99b3cc; text-align: right; background: {bg}; width: 22%;">{line.get('value', '$0')}</td>
                </tr>
            '''

        html += f'''
            </table>

            <!-- UVT Info -->
            <div style="background: #f8f9fa; border: 1px solid #dee2e6; padding: 10px; margin-top: 10px; font-size: 10px;">
                <strong style="color: #003366;">Valores UVT para {year}:</strong><br/>
                • 4.500 UVT (Patrimonio): {cert_data.get('uvt_4500', '-')}<br/>
                • 1.400 UVT (Ingresos): {cert_data.get('uvt_1400', '-')}
            </div>
        </div>
        '''

        return html

    def action_generate_qweb_pdf(self):
        """Genera el certificado usando el template QWeb"""
        self.ensure_one()

        return self.env.ref(
            'l10n_co_exogenous_information_reporting.'
            'action_report_income_certificate_individual'
        ).report_action(self)
