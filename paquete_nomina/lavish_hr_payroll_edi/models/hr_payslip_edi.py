# -*- coding: utf-8 -*-
"""
Modelo principal de Nómina Electrónica DIAN.
Documento electrónico que agrupa una o varias nóminas de un empleado.
"""
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.misc import format_date
from odoo.addons.lavish_hr_payroll.models.hr_slip_constante import CATEGORY_MAPPINGS

import logging
_logger = logging.getLogger(__name__)

try:
    import xmltodict
except ImportError:
    xmltodict = None


class HrPayslipEdi(models.Model):
    _name = 'hr.payslip.edi'
    _inherit = ['mail.thread.cc', 'mail.activity.mixin']
    _description = 'Nómina Electrónica DIAN'
    _order = 'date_to desc'

    # ================================================================
    # CAMPOS BÁSICOS
    # ================================================================

    name = fields.Char(string='Referencia', required=True)
    number = fields.Char(string='Número', default='/', copy=False)
    employee_id = fields.Many2one(
        'hr.employee', string='Empleado', required=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        tracking=True
    )
    version_id = fields.Many2one(
        'hr.version', string='Versión Contrato',
        domain="[('employee_id', '=', employee_id)]"
    )
    struct_id = fields.Many2one(
        'hr.payroll.structure', string='Estructura',
        help='Estructura salarial aplicada'
    )
    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True,
        default=lambda self: self.env.company
    )
    currency_id = fields.Many2one(related='version_id.currency_id')

    # ================================================================
    # PERIODO
    # ================================================================

    date_from = fields.Date(
        string='Desde', required=True,
        default=lambda self: fields.Date.to_string(date.today().replace(day=1))
    )
    date_to = fields.Date(
        string='Hasta', required=True,
        default=lambda self: fields.Date.to_string(
            (datetime.now() + relativedelta(months=+1, day=1, days=-1)).date()
        )
    )
    payment_date = fields.Date(
        string='Fecha de Pago',
        default=fields.Date.today
    )
    fecha_vencimiento = fields.Date(string='Fecha de Vencimiento')
    date_end_contract = fields.Date(
        string='Fecha Terminación Contrato',
        compute='_compute_date_end_contract',
        store=True,
        help='Fecha de terminación del contrato. Se muestra solo en liquidaciones.'
    )
    is_liquidacion = fields.Boolean(
        string='Es Liquidación',
        compute='_compute_date_end_contract',
        store=True,
    )

    @api.depends('version_id', 'version_id.contract_date_end', 'payslip_ids')
    def _compute_date_end_contract(self):
        for rec in self:
            version = rec.version_id
            rec.date_end_contract = version.contract_date_end if version else False
            # Es liquidación si el contrato tiene fecha fin dentro del periodo
            if version and version.contract_date_end:
                rec.is_liquidacion = (
                    rec.date_from and rec.date_to
                    and version.contract_date_end >= rec.date_from
                    and version.contract_date_end <= rec.date_to
                )
            else:
                rec.is_liquidacion = False

    # ================================================================
    # ESTADO DOCUMENTO
    # ================================================================

    state = fields.Selection([
        ('draft', 'Borrador'),
        ('verify', 'En Espera'),
        ('done', 'Hecho'),
        ('cancel', 'Cancelado'),
    ], string='Estado', default='draft', tracking=True, copy=False)

    # ================================================================
    # ESTADO DIAN
    # ================================================================

    state_dian = fields.Selection([
        ('por_notificar', 'Por Notificar'),
        ('error', 'Error'),
        ('por_validar', 'Por Validar'),
        ('exitoso', 'Exitoso'),
        ('rechazado', 'Rechazado'),
    ], string='Estado DIAN', default='por_notificar', tracking=True, copy=False)

    current_cune = fields.Char(string='CUNE', readonly=True, copy=False)
    cune_url = fields.Char(string='URL DIAN', compute='_compute_cune_url')
    QR_code = fields.Binary(string='Código QR', compute='_compute_qr_code', store=True)
    previous_cune = fields.Char(string='CUNE Anterior', copy=False)
    ZipKey = fields.Char(string='ZipKey DIAN', readonly=True, copy=False)
    name_xml = fields.Char(string='Nombre XML', copy=False)
    name_zip = fields.Char(string='Nombre ZIP', copy=False)
    resend = fields.Boolean(string='Autorizar Reenvío', default=False, copy=False)

    # Respuestas DIAN
    response_message_dian = fields.Text(string='Respuesta DIAN', readonly=True, copy=False)
    xml_response_dian = fields.Text(string='XML Respuesta', readonly=True, copy=False)
    xml_send_query_dian = fields.Text(string='XML Consulta', readonly=True, copy=False)
    xml_sended = fields.Text(string='XML Enviado', readonly=True, copy=False)

    # ================================================================
    # MODO PROVISIONES
    # ================================================================

    provision_mode = fields.Selection([
        ('include', 'Incluir Provisiones'),
        ('exclude', 'Excluir Provisiones'),
        ('only', 'Solo Provisiones'),
    ], string='Modo Provisiones', default='include',
        help='Controla cómo se manejan las provisiones de prestaciones '
             '(PRV_PRIM, PRV_CES, PRV_ICES, PRV_VAC) en la nómina electrónica.\n\n'
             '- Incluir: Agrega las provisiones junto con los demás devengados y deducciones.\n'
             '- Excluir: Omite las provisiones (reportar solo al momento del pago real).\n'
             '- Solo Provisiones: Genera documento solo con las provisiones.\n\n'
             'IMPORTANTE: Cuando hay provisión reportada previamente y se paga la '
             'prestación real, se resta el valor provisionado para enviar solo la '
             'diferencia. Si el resultado es negativo (valor 0 o menos), el documento '
             'no podrá corregirse ya que DIAN no acepta valores negativos, lo que '
             'probablemente tendrá afectación futura por imprecisión en los reportes.\n\n'
             'RECOMENDADO: Usar provisiones en liquidación de contrato para garantizar '
             'que los valores finales sean consistentes.'
    )
    use_external_accumulated = fields.Boolean(
        string='Incluir Acumulados Externos',
        default=False,
        help='Cuando está activo, la consolidación también busca en los '
             'Acumulados de Nómina registros de tipo "Carga Inicial" o '
             '"Ajuste Manual" para incluir provisiones y prestaciones '
             'reportadas en un sistema de nómina anterior.\n\n'
             'Útil cuando la empresa migró a Odoo a mitad de año y necesita '
             'que las prestaciones anuales (CES_YEAR, INTCES_YEAR, PRIMA) '
             'se ajusten restando lo ya reportado en el sistema anterior.\n\n'
             'Los acumulados se cargan desde: Nómina > Configuración > '
             'Acumulados de Nómina con tipo "Carga Inicial".'
    )
    provision_warning = fields.Text(
        string='Alerta Provisiones',
        compute='_compute_provision_warning'
    )

    @api.depends('line_ids', 'line_ids.total', 'provision_mode')
    def _compute_provision_warning(self):
        for rec in self:
            warnings = []
            if rec.provision_mode != 'exclude':
                for line in rec.line_ids:
                    if line.total < 0 and line.salary_rule_id and \
                       line.salary_rule_id.devengado_rule_id:
                        warnings.append(_(
                            '%s tiene valor negativo (%.2f). '
                            'DIAN no acepta valores negativos en devengados.'
                        ) % (line.name, line.total))
            # Advertencia si hay pagos anuales del año anterior
            annual_codes = {l.code for l in rec.line_ids} & rec.ANNUAL_PREV_YEAR_CODES
            if annual_codes and rec.date_from and rec.provision_mode == 'include':
                warnings.append(_(
                    'Documento contiene pagos anuales del año anterior (%s). '
                    'Las provisiones reportadas en %d fueron restadas automáticamente.'
                ) % (', '.join(annual_codes), rec.date_from.year - 1))
            # Advertencia si usa acumulados externos
            if rec.use_external_accumulated and rec.employee_id:
                ext_current = rec._get_external_reported_provisions()
                ext_prev = rec._get_external_reported_provisions(
                    year=rec.date_from.year - 1) if rec.date_from else {}
                total_ext = sum(ext_current.values()) + sum(ext_prev.values())
                if total_ext > 0:
                    warnings.append(_(
                        'Se incluyen $%s de acumulados externos (Carga Inicial) '
                        'en la resta de provisiones.'
                    ) % '{:,.0f}'.format(total_ext))
            rec.provision_warning = '\n'.join(warnings) if warnings else False

    # ================================================================
    # NOTA DE AJUSTE
    # ================================================================

    credit_note = fields.Boolean(
        string='Nota de Ajuste',
        help='Indica si es una nota de ajuste de nómina electrónica'
    )
    type_note = fields.Selection([
        ('1', 'Reemplazar'),
        ('2', 'Eliminar'),
    ], string='Tipo de Nota', copy=False)
    adjustment_note_description = fields.Text(
        string='Descripción del Ajuste',
        help='Razón de la nota de ajuste'
    )

    # Cadena de ajustes
    origin_edi_id = fields.Many2one(
        'hr.payslip.edi', string='Documento Original',
        index=True, copy=False, readonly=True, tracking=True,
        help='Documento original absoluto de la cadena de ajustes',
    )
    parent_edi_id = fields.Many2one(
        'hr.payslip.edi', string='Documento Ajustado',
        index=True, copy=False, readonly=True, tracking=True,
        help='Documento inmediatamente anterior que se ajusta',
    )
    child_edi_ids = fields.One2many(
        'hr.payslip.edi', 'parent_edi_id', string='Notas de Ajuste Hijas',
    )
    adjustment_count = fields.Integer(
        string='Num. Ajustes', compute='_compute_adjustment_count',
    )
    is_latest_in_chain = fields.Boolean(
        string='Vigente', compute='_compute_is_latest_in_chain',
    )

    # ================================================================
    # RELACIONES
    # ================================================================

    payslip_run_id = fields.Many2one(
        'hr.payslip.edi.run', string='Lote',
        ondelete='cascade',
        domain="[('company_id', '=', company_id)]"
    )
    payslip_ids = fields.Many2many(
        'hr.payslip',
        'hr_payslip_edi_rel',
        'edi_id',
        'payslip_id',
        string='Nóminas del Mes'
    )
    payslip_count = fields.Integer(
        string='Nóminas',
        compute='_compute_payslip_count'
    )
    line_ids = fields.One2many(
        'hr.payslip.edi.line', 'slip_id',
        string='Líneas de Nómina', store=True,
        domain=[('line_type', '=', 'normal')]
    )
    info_line_ids = fields.One2many(
        'hr.payslip.edi.line', 'slip_id',
        string='Líneas Informativas',
        domain=[('line_type', '=', 'informativo')]
    )
    worked_days_line_ids = fields.One2many(
        'hr.payslip.edi.worked_days', 'payslip_id',
        string='Días Trabajados', copy=True
    )

    # ================================================================
    # LÍNEAS POR CATEGORÍA
    # ================================================================

    earnings_ids = fields.One2many('hr.payslip.edi.line', compute='_compute_concepts_category', string='Devengos')
    deductions_ids = fields.One2many('hr.payslip.edi.line', compute='_compute_concepts_category', string='Deducciones')
    social_security_ids = fields.One2many('hr.payslip.edi.line', compute='_compute_concepts_category', string='Seguridad Social')
    provisions_ids = fields.One2many('hr.payslip.edi.line', compute='_compute_concepts_category', string='Provisiones')
    bases_ids = fields.One2many('hr.payslip.edi.line', compute='_compute_concepts_category', string='Bases')
    outcome_ids = fields.One2many('hr.payslip.edi.line', compute='_compute_concepts_category', string='Neto')

    # ================================================================
    # LOGS
    # ================================================================

    log_ids = fields.One2many(
        'hr.payslip.edi.log', 'payslip_edi_id', string='Logs',
    )
    log_count = fields.Integer(
        string='Num. Logs', compute='_compute_log_count',
    )
    log_error_count = fields.Integer(
        string='Errores', compute='_compute_log_count',
    )

    @api.depends('log_ids', 'log_ids.level')
    def _compute_log_count(self):
        for rec in self:
            rec.log_count = len(rec.log_ids)
            rec.log_error_count = len(rec.log_ids.filtered(
                lambda l: l.level == 'error'
            ))

    def action_view_logs(self):
        """Ver logs del documento."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Logs - %s') % self.number,
            'res_model': 'hr.payslip.edi.log',
            'view_mode': 'list,form',
            'domain': [('payslip_edi_id', '=', self.id)],
            'context': {'default_payslip_edi_id': self.id},
        }

    # ================================================================
    # TOTALES
    # ================================================================

    total_devengos = fields.Float(string='Total Devengados', default=0.0)
    total_deducciones = fields.Float(string='Total Deducciones', default=0.0)
    total_paid = fields.Float(string='Total Comprobante', default=0.0)
    basic_wage = fields.Monetary(compute='_compute_basic_net')
    net_wage = fields.Monetary(compute='_compute_basic_net')

    # Otros
    note = fields.Text(string='Notas Internas')
    paid = fields.Boolean(string='Pagado', readonly=True, copy=False)
    validar_cron = fields.Boolean(string='Validar por Cron')
    warning_message = fields.Char(readonly=True)
    certificate_expiry_warning = fields.Char(
        string='Alerta Certificado',
        compute='_compute_certificate_expiry_warning'
    )

    @api.depends('company_id')
    def _compute_certificate_expiry_warning(self):
        today = date.today()
        for rec in self:
            expiry = rec.company_id.certificate_expiry_payroll
            if expiry and expiry <= today + timedelta(days=30):
                days_left = (expiry - today).days
                if days_left <= 0:
                    rec.certificate_expiry_warning = _(
                        'CERTIFICADO VENCIDO desde %s. No podrá enviar documentos a DIAN.'
                    ) % expiry
                else:
                    rec.certificate_expiry_warning = _(
                        'El certificado digital vence en %d días (%s). Renuévelo pronto.'
                    ) % (days_left, expiry)
            else:
                rec.certificate_expiry_warning = False

    # ================================================================
    # COMPUTED FIELDS
    # ================================================================

    @api.depends('line_ids', 'line_ids.category_id')
    def _compute_concepts_category(self):
        """Categoriza las líneas de nómina electrónica igual que la nómina normal."""
        EdiLine = self.env['hr.payslip.edi.line']
        empty = EdiLine

        for rec in self:
            earnings = empty
            deductions = empty
            social_security = empty
            provisions = empty
            bases = empty
            outcome = empty

            for line in rec.line_ids.filtered(lambda l: l.total != 0):
                cat_code = line.category_id.code or ''
                parent_code = line.category_id.parent_id.code if line.category_id.parent_id else ''

                if cat_code in CATEGORY_MAPPINGS.get('EARNINGS', []) or parent_code in CATEGORY_MAPPINGS.get('EARNINGS', []):
                    earnings |= line
                elif cat_code in CATEGORY_MAPPINGS.get('SOCIAL_SECURITY', []) or parent_code in CATEGORY_MAPPINGS.get('SOCIAL_SECURITY', []):
                    social_security |= line
                elif cat_code in CATEGORY_MAPPINGS.get('DEDUCTIONS', []) or parent_code in CATEGORY_MAPPINGS.get('DEDUCTIONS', []):
                    deductions |= line
                elif cat_code in CATEGORY_MAPPINGS.get('PROVISIONS', []) or parent_code in CATEGORY_MAPPINGS.get('PROVISIONS', []):
                    provisions |= line
                elif cat_code in CATEGORY_MAPPINGS.get('OUTCOME', []) or parent_code in CATEGORY_MAPPINGS.get('OUTCOME', []):
                    outcome |= line
                else:
                    bases |= line

            rec.earnings_ids = earnings
            rec.deductions_ids = deductions
            rec.social_security_ids = social_security
            rec.provisions_ids = provisions
            rec.bases_ids = bases
            rec.outcome_ids = outcome

    @api.depends('payslip_ids')
    def _compute_payslip_count(self):
        for record in self:
            record.payslip_count = len(record.payslip_ids)

    @api.depends('child_edi_ids')
    def _compute_adjustment_count(self):
        for rec in self:
            rec.adjustment_count = len(rec.child_edi_ids)

    @api.depends('child_edi_ids', 'child_edi_ids.state_dian')
    def _compute_is_latest_in_chain(self):
        for rec in self:
            rec.is_latest_in_chain = not any(
                child.state_dian == 'exitoso' for child in rec.child_edi_ids
            )

    def action_view_adjustment_chain(self):
        """Smart button: muestra toda la cadena de ajustes."""
        self.ensure_one()
        origin = self.origin_edi_id or self
        domain = [
            '|',
            ('id', '=', origin.id),
            ('origin_edi_id', '=', origin.id),
        ]
        return {
            'type': 'ir.actions.act_window',
            'name': _('Cadena de Ajustes - %s') % origin.number,
            'res_model': 'hr.payslip.edi',
            'view_mode': 'list,form',
            'domain': domain,
            'context': {'search_default_group_employee': 0},
        }

    @api.depends('current_cune')
    def _compute_cune_url(self):
        """Genera la URL de consulta en el portal DIAN."""
        base_url = "https://catalogo-vpfe.dian.gov.co/Document/FindDocument?documentKey="
        for record in self:
            if record.current_cune:
                record.cune_url = base_url + record.current_cune
            else:
                record.cune_url = False

    @api.depends('current_cune', 'number', 'date_from', 'date_to',
                 'total_devengos', 'total_deducciones', 'total_paid')
    def _compute_qr_code(self):
        """Genera imagen QR con datos del documento como en facturación electrónica."""
        try:
            import pyqrcode
        except ImportError:
            for rec in self:
                rec.QR_code = False
            return

        for rec in self:
            if not rec.current_cune:
                rec.QR_code = False
                continue
            try:
                qr_data = (
                    'NumNIE: %s\n'
                    'FecNIE: %s\n'
                    'NitEmp: %s\n'
                    'DocEmp: %s\n'
                    'DevTotal: %s\n'
                    'DedTotal: %s\n'
                    'CompTotal: %s\n'
                    'CUNE: %s\n'
                    'QRUrl: %s'
                ) % (
                    rec.number or '',
                    rec.payment_date or '',
                    rec.company_id.partner_id.vat_co or rec.company_id.vat or '',
                    rec.employee_id.identification_id or '',
                    '{:.2f}'.format(rec.total_devengos),
                    '{:.2f}'.format(abs(rec.total_deducciones)),
                    '{:.2f}'.format(rec.total_paid),
                    rec.current_cune,
                    rec._get_url_qr() + rec.current_cune,
                )
                qr = pyqrcode.create(qr_data, error='L')
                rec.QR_code = qr.png_as_base64_str(scale=2)
            except Exception as e:
                _logger.warning('Error generando QR para %s: %s', rec.number, e)
                rec.QR_code = False

    @api.depends('payslip_ids', 'payslip_ids.line_ids')
    def _compute_basic_net(self):
        for rec in self:
            BASIC = NET = 0
            for payslip in rec.payslip_ids.filtered(
                lambda x: x.struct_process in ('nomina', 'contrato')
            ):
                for line in payslip.line_ids:
                    if line.category_id.code == 'BASIC':
                        BASIC += abs(line.total)
                    elif line.category_id.code == 'NET':
                        NET += abs(line.total)
            rec.basic_wage = BASIC
            rec.net_wage = NET

    # ================================================================
    # ONCHANGE
    # ================================================================

    @api.onchange('employee_id', 'struct_id', 'version_id', 'date_from', 'date_to')
    def _onchange_employee(self):
        if not self.employee_id or not self.date_from or not self.date_to:
            return

        employee = self.employee_id
        self.company_id = employee.company_id

        if not self.version_id or self.employee_id != self.version_id.employee_id:
            closed_payslips = self.env['hr.payslip'].search([
                ('employee_id', '=', employee.id),
                ('state', 'in', ['done', 'paid']),
                ('date_from', '<=', self.date_to),
                ('date_to', '>=', self.date_from)
            ], order='date_to desc', limit=1)
            if closed_payslips:
                self.version_id = closed_payslips.version_id
                self.struct_id = closed_payslips.struct_id
            else:
                self.version_id = False
                self.struct_id = False

        lang = employee.sudo().work_contact_id.lang or self.env.user.lang
        payslip_name = self.struct_id.payslip_name or _('Nómina Electrónica')
        self.name = '%s - %s - %s' % (
            payslip_name, self.employee_id.name or '',
            format_date(self.env, self.date_from, date_format="MMMM y", lang_code=lang)
        )

    # ================================================================
    # CRUD
    # ================================================================

    @api.model_create_multi
    def create(self, vals_list):
        new_list = []
        for vals in vals_list:
            if vals.get('number', '/') == '/':
                company = self.env['res.company'].browse(
                    vals.get('company_id', self.env.company.id)
                )
                if vals.get('credit_note'):
                    # Usar secuencia de notas de ajuste de la empresa, fallback a genérica
                    seq = company.sequence_payroll_note_id
                    if seq:
                        vals['number'] = seq.next_by_id()
                    else:
                        vals['number'] = self.env['ir.sequence'].next_by_code(
                            'hr.payslip.edi.note.sequence'
                        ) or '/'
                else:
                    # Usar secuencia de nómina de la empresa, fallback a genérica
                    seq = company.sequence_payroll_id
                    if seq:
                        vals['number'] = seq.next_by_id()
                    else:
                        vals['number'] = self.env['ir.sequence'].next_by_code(
                            'hr.payslip.edi.sequence'
                        ) or '/'
            new_list.append(vals)
        return super().create(new_list)

    # ================================================================
    # ACCIONES DE ESTADO
    # ================================================================

    def action_draft(self):
        for rec in self:
            rec.line_ids.unlink()
            rec.worked_days_line_ids.unlink()
        return self.write({
            'state': 'draft',
            'total_devengos': 0.0,
            'total_deducciones': 0.0,
            'total_paid': 0.0
        })

    def action_cancel(self):
        return self.write({'state': 'cancel'})

    def action_confirm(self):
        """Confirma el documento de nómina electrónica."""
        for rec in self:
            if not rec.payslip_ids:
                raise UserError(_('Debe agregar al menos una nómina relacionada.'))
            rec.get_payslip_period()
            rec.update_total()
        return self.write({'state': 'verify'})

    def action_done(self):
        """Marca como hecho el documento."""
        return self.write({'state': 'done'})

    # ================================================================
    # ACCIONES DIAN
    # ================================================================

    def action_send_dian(self):
        """Envía el documento a la DIAN."""
        for rec in self:
            if rec.state != 'done':
                raise UserError(_('El documento debe estar en estado "Hecho" para enviar a DIAN.'))
            if rec.state_dian == 'exitoso' and not rec.resend:
                raise UserError(_('Este documento ya fue validado por DIAN.'))

            generator = self.env['nomina.xml.generator']
            generator.send_to_dian(rec)

    def action_check_status_dian(self):
        """Consulta el estado del documento en la DIAN."""
        for rec in self:
            if rec.state_dian != 'por_validar':
                raise UserError(_('Solo puede consultar documentos en estado "Por Validar".'))

            generator = self.env['nomina.xml.generator']
            generator.check_status(rec)

    def action_recuperar_nomina(self):
        """Recupera una nómina rechazada o pendiente para corregir y reenviar."""
        for rec in self:
            if rec.state_dian not in ('rechazado', 'error', 'por_validar'):
                raise UserError(_('Solo puede recuperar documentos rechazados, con error o pendientes de validación.'))
            rec.write({
                'state_dian': 'por_notificar',
                'resend': True,
                'response_message_dian': False,
                'xml_response_dian': False,
            })
        return True

    def action_retry_send_dian(self):
        """Reintentar envío a DIAN mostrando valores de provisión."""
        self.ensure_one()
        if self.state_dian == 'exitoso':
            raise UserError(_('Este documento ya fue validado por DIAN. No requiere reenvío.'))

        # Mostrar comparación de valores antes de reintentar
        comparison = self._get_provision_comparison()

        # Verificar si ya fue enviado antes consultando DIAN
        if self.ZipKey:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Reintentar Envío DIAN'),
                'res_model': 'hr.payslip.edi.retry.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_payslip_edi_id': self.id,
                    'default_comparison_text': comparison,
                    'default_has_zipkey': True,
                    'default_zipkey': self.ZipKey,
                },
            }
        else:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Reintentar Envío DIAN'),
                'res_model': 'hr.payslip.edi.retry.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_payslip_edi_id': self.id,
                    'default_comparison_text': comparison,
                    'default_has_zipkey': False,
                },
            }

    def action_consult_dian_status(self):
        """Consulta estado en la DIAN sin validar estado actual."""
        self.ensure_one()
        if not self.ZipKey:
            raise UserError(_('No hay ZipKey para consultar. El documento no ha sido enviado a DIAN.'))

        generator = self.env['nomina.xml.generator']
        try:
            result = generator.check_existence(self)
            if result.get('result_verify_status'):
                self.write({
                    'state_dian': 'exitoso',
                    'state': 'done',
                    'resend': False,
                    'response_message_dian': (self.response_message_dian or '') +
                        '\n- Consulta directa: Documento encontrado y validado en DIAN\n',
                })
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Éxito'),
                        'message': _('Documento validado correctamente en DIAN.'),
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                self.response_message_dian = (self.response_message_dian or '') + \
                    '\n- Consulta directa: ' + result.get('response_message_dian', '') + '\n'
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Información'),
                        'message': result.get('response_message_dian', _('Documento no encontrado en DIAN.')),
                        'type': 'warning',
                        'sticky': False,
                    }
                }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def _get_provision_comparison(self):
        """Genera texto comparativo de provisiones enviadas vs. existentes."""
        lines = []
        lines.append(_('=== COMPARACIÓN DE VALORES ===\n'))

        # Valores actuales del documento
        lines.append(_('\n--- Valores Actuales (a enviar) ---'))
        lines.append(_('Total Devengados: ${:,.2f}').format(self.total_devengos))
        lines.append(_('Total Deducciones: ${:,.2f}').format(self.total_deducciones))
        lines.append(_('Total Comprobante: ${:,.2f}').format(self.total_paid))

        # Detalle de devengados
        lines.append(_('\n--- Detalle Devengados ---'))
        for line in self.nes_dev_line_ids:
            try:
                rule_code = line.salary_rule_id.devengado_rule_id.code if line.salary_rule_id.devengado_rule_id else line.code
            except Exception:
                rule_code = line.code
            lines.append('{}: ${:,.2f} (Código DIAN: {})'.format(
                line.name, abs(line.total or 0), rule_code
            ))

        # Detalle de deducciones
        lines.append(_('\n--- Detalle Deducciones ---'))
        for line in self.nes_ded_line_ids:
            try:
                rule_code = line.salary_rule_id.deduccion_rule_id.code if line.salary_rule_id.deduccion_rule_id else line.code
            except Exception:
                rule_code = line.code
            lines.append('{}: ${:,.2f} (Código DIAN: {})'.format(
                line.name, abs(line.total or 0), rule_code
            ))

        # Líneas informativas
        info_lines = self.line_ids.filtered(lambda l: l.line_type == 'informativo')
        if info_lines:
            lines.append(_('\n--- Información Adicional ---'))
            for line in info_lines:
                info_type_label = dict(line._fields['info_type'].selection or []).get(line.info_type, line.info_type or 'Otro')
                value_str = line.info_value or ''
                if line.amount:
                    value_str += ' (${:,.2f})'.format(abs(line.amount))
                if line.info_percentage:
                    value_str += ' [{}%]'.format(line.info_percentage)
                lines.append('{} - {}: {}'.format(info_type_label, line.name, value_str))

        # Si hay XML previo, mostrar valores enviados
        if self.xml_sended and xmltodict:
            lines.append(_('\n\n--- Valores Previamente Enviados ---'))
            try:
                xml_dict = xmltodict.parse(self.xml_sended)
                if 'NominaIndividual' in xml_dict:
                    nomina = xml_dict['NominaIndividual']
                    lines.append(_('Devengados: {}').format(
                        nomina.get('DevengadosTotal', 'N/A')
                    ))
                    lines.append(_('Deducciones: {}').format(
                        nomina.get('DeduccionesTotal', 'N/A')
                    ))
                    lines.append(_('Comprobante: {}').format(
                        nomina.get('ComprobanteTotal', 'N/A')
                    ))
            except Exception as e:
                lines.append(_('Error parseando XML anterior: {}').format(str(e)))

        # Estado DIAN
        lines.append(_('\n\n--- Estado DIAN ---'))
        lines.append(_('Estado: {}').format(dict(self._fields['state_dian'].selection).get(self.state_dian, self.state_dian)))
        lines.append(_('CUNE: {}').format(self.current_cune or 'No generado'))
        lines.append(_('ZipKey: {}').format(self.ZipKey or 'No generado'))

        if self.response_message_dian:
            lines.append(_('\n--- Último Mensaje DIAN ---'))
            lines.append(self.response_message_dian[:500])

        return '\n'.join(lines)

    # ================================================================
    # NOTIFICACIONES POR CORREO
    # ================================================================

    def send_email_notification(self, template_xmlid):
        """Envía notificación por correo usando el template especificado."""
        template = self.env.ref(template_xmlid, raise_if_not_found=False)
        if template:
            for rec in self:
                template.send_mail(rec.id, force_send=True)

    def _send_validated_notification(self):
        """Envía notificación cuando la nómina es validada por DIAN."""
        self.send_email_notification('lavish_hr_payroll_edi.email_template_payslip_edi_validated')

    def _send_rejected_notification(self):
        """Envía notificación cuando la nómina es rechazada por DIAN."""
        self.send_email_notification('lavish_hr_payroll_edi.email_template_payslip_edi_rejected')

    def write(self, vals):
        """Override write para notificar cambios de estado DIAN (sin envío automático de correo)."""
        res = super().write(vals)
        if 'state_dian' in vals:
            for rec in self:
                if vals['state_dian'] == 'exitoso':
                    # Notificar al padre si es nota de ajuste
                    if rec.credit_note and rec.parent_edi_id:
                        rec.parent_edi_id.message_post(
                            body=_(
                                'La nota de ajuste <b>%s</b> (%s) fue validada '
                                'exitosamente por DIAN.'
                            ) % (rec.number, dict(rec._fields['type_note'].selection).get(rec.type_note, '')),
                            message_type='comment',
                            subtype_xmlid='mail.mt_note',
                        )
        return res

    def action_send_email_nomina(self):
        """Enviar correo de nómina electrónica manualmente al empleado con PDF adjunto."""
        template = self.env.ref(
            'lavish_hr_payroll_edi.email_template_payslip_edi_validated',
            raise_if_not_found=False,
        )
        if not template:
            raise UserError(_('No se encontró la plantilla de correo.'))
        for rec in self:
            if rec.state_dian != 'exitoso':
                raise UserError(_(
                    'Solo se puede enviar correo para nóminas validadas por DIAN. '
                    'La nómina %s está en estado: %s'
                ) % (rec.number, rec.state_dian))
            template.send_mail(rec.id, force_send=True)
            rec.message_post(
                body=_('Correo de nómina electrónica enviado al empleado.'),
                message_type='comment',
                subtype_xmlid='mail.mt_note',
            )

    # ================================================================
    # SMART BUTTONS
    # ================================================================

    def action_view_payslips(self):
        """Ver nóminas relacionadas."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Nóminas'),
            'res_model': 'hr.payslip',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.payslip_ids.ids)],
            'context': {'default_employee_id': self.employee_id.id},
        }

    def action_view_xml(self):
        """Ver XML enviado."""
        self.ensure_one()
        if not self.xml_sended:
            raise UserError(_('No hay XML generado.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('XML Nómina Electrónica'),
            'res_model': 'hr.payslip.edi',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }

    # ================================================================
    # DESCARGA XML
    # ================================================================

    def _action_download_content(self, field_name, filename_prefix):
        """Genérico para descargar contenido XML como archivo."""
        self.ensure_one()
        content = getattr(self, field_name)
        if not content:
            raise UserError(_('No hay contenido disponible para descargar.'))
        return {
            'type': 'ir.actions.act_url',
            'url': '/payslip_edi/download_content/%d/%s' % (self.id, filename_prefix),
            'target': 'new',
        }

    def action_download_xml_enviado(self):
        """Descarga el XML enviado a DIAN."""
        return self._action_download_content('xml_sended', 'xml_enviado')

    def action_download_xml_respuesta(self):
        """Descarga el XML de respuesta DIAN."""
        return self._action_download_content('xml_response_dian', 'xml_respuesta')

    def action_download_xml_consulta(self):
        """Descarga el XML de consulta DIAN."""
        return self._action_download_content('xml_send_query_dian', 'xml_consulta')

    def action_download_xml_firmado(self):
        """Descarga el archivo XML firmado desde el repositorio."""
        self.ensure_one()
        if not self.name_xml:
            raise UserError(_('No hay archivo XML firmado disponible.'))
        return {
            'type': 'ir.actions.act_url',
            'url': '/payslip_edi/download/%d/xml' % self.id,
            'target': 'new',
        }

    def action_download_zip(self):
        """Descarga el archivo ZIP desde el repositorio."""
        self.ensure_one()
        if not self.name_zip:
            raise UserError(_('No hay archivo ZIP disponible.'))
        return {
            'type': 'ir.actions.act_url',
            'url': '/payslip_edi/download/%d/zip' % self.id,
            'target': 'new',
        }

    def action_update_employee_data(self):
        """Actualiza los datos del empleado antes del envío."""
        for rec in self:
            if rec.state_dian == 'exitoso':
                raise UserError(_('No puede modificar un documento ya validado por DIAN.'))
            rec.message_post(body=_('Datos del empleado actualizados.'))
        return True

    def action_create_adjustment(self):
        """Crea nota de ajuste tipo Reemplazar con todos los datos del original.

        Copia el documento completo (lineas, dias trabajados, payslips
        relacionados) y lo deja en draft para que el usuario edite los
        valores que necesite ajustar antes de enviarlo a DIAN. La nota
        queda marcada credit_note=True, type_note='1' (Reemplazar) y
        vinculada al original via previous_cune / parent_edi_id.
        """
        self.ensure_one()
        if self.state_dian != 'exitoso':
            raise UserError(_('Solo puede crear ajuste de documentos exitosos.'))
        if not self.current_cune:
            raise UserError(_('El documento original no tiene CUNE; no se puede crear nota de reemplazo.'))

        # Secuencia de notas (fallback a la de nomina)
        company = self.company_id
        sequence = company.sequence_payroll_note_id or company.sequence_payroll_id
        if not sequence:
            raise UserError(_('Configure la secuencia de notas de ajuste en la compania.'))
        number = sequence.next_by_id()

        adjustment = self.copy({
            'name': _('Ajuste - %s') % self.name,
            'number': number,
            'credit_note': True,
            'type_note': '1',  # Reemplazar
            'previous_cune': self.current_cune,
            'current_cune': False,
            'ZipKey': False,
            'state': 'draft',
            'state_dian': 'por_notificar',
            'response_message_dian': False,
            'xml_response_dian': False,
            'xml_send_query_dian': False,
            'xml_sended': False,
            'name_xml': False,
            'name_zip': False,
            'resend': False,
            'parent_edi_id': self.id,
            'origin_edi_id': (self.origin_edi_id or self).id,
        })

        # Copiar lineas (devengados/deducciones/informativos)
        for line in self.line_ids:
            line.copy({'slip_id': adjustment.id})

        # Copiar dias trabajados
        if hasattr(self, 'worked_days_line_ids') and self.worked_days_line_ids:
            for wd in self.worked_days_line_ids:
                wd.copy({'payslip_id': adjustment.id})

        # Reasociar nominas origen
        if self.payslip_ids:
            adjustment.payslip_ids = [(6, 0, self.payslip_ids.ids)]

        adjustment.update_total()

        self.message_post(
            body=_('Nota de reemplazo <b>%s</b> creada en borrador para ajustar este documento.') % adjustment.number,
            message_type='comment',
            subtype_xmlid='mail.mt_note',
        )

        return {
            'type': 'ir.actions.act_window',
            'name': _('Nota de Ajuste (Reemplazar)'),
            'res_model': 'hr.payslip.edi',
            'res_id': adjustment.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_create_data_adjustment(self):
        """Crea nota de ajuste solo para actualizar datos del empleado.

        Genera una nota tipo Reemplazar con los mismos valores financieros
        del documento original pero con los datos actualizados del empleado
        (nombre, documento, banco, etc).
        """
        self.ensure_one()
        if self.state_dian != 'exitoso':
            raise UserError(_('Solo puede crear ajuste de documentos exitosos.'))

        # Obtener secuencia
        company = self.company_id
        sequence = company.sequence_payroll_note_id or company.sequence_payroll_id
        if not sequence:
            raise UserError(_('Configure la secuencia de notas de ajuste en la compañía.'))
        number = sequence.next_by_id()

        # Crear la nota de ajuste con los mismos datos financieros
        adjustment = self.copy({
            'name': _('Ajuste Datos - %s') % self.name,
            'number': number,
            'credit_note': True,
            'type_note': '1',  # Reemplazar
            'previous_cune': self.current_cune,
            'current_cune': False,
            'ZipKey': False,
            'state': 'draft',
            'state_dian': 'por_notificar',
            'response_message_dian': False,
            'xml_response_dian': False,
            'xml_send_query_dian': False,
            'xml_sended': False,
            'name_xml': False,
            'name_zip': False,
            'resend': False,
            'parent_edi_id': self.id,
            'origin_edi_id': (self.origin_edi_id or self).id,
            'adjustment_note_description': _(
                'Ajuste por actualización de datos del empleado. '
                'Los valores financieros permanecen iguales.'
            ),
        })

        # Copiar las líneas del documento original
        for line in self.line_ids:
            line.copy({'slip_id': adjustment.id})

        # Copiar días trabajados si existen
        if hasattr(self, 'worked_days_line_ids') and self.worked_days_line_ids:
            for wd in self.worked_days_line_ids:
                wd.copy({'payslip_id': adjustment.id})

        # Copiar las nóminas relacionadas
        if self.payslip_ids:
            adjustment.payslip_ids = [(6, 0, self.payslip_ids.ids)]

        # Recalcular totales
        adjustment.update_total()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Nota de Ajuste - Datos Empleado'),
            'res_model': 'hr.payslip.edi',
            'res_id': adjustment.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ================================================================
    # LÓGICA DE CONSOLIDACIÓN
    # ================================================================

    def action_compute_sheet(self):
        """Computa líneas y totales de la nómina electrónica."""
        for slip in self:
            slip.get_payslip_period()
            slip.update_total()

    def get_payslip_period(self):
        """Obtiene las nóminas del periodo y las asocia."""
        self.payslip_ids = [(5, 0, 0)]
        # Si el lote EDI tiene lote origen (ej: consolidación), buscar solo en ese lote
        source_batch = self.payslip_run_id.payslip_run_source_id if self.payslip_run_id else False
        if source_batch:
            payslips = self.env['hr.payslip'].search([
                ('employee_id', '=', self.employee_id.id),
                ('payslip_run_id', '=', source_batch.id),
                ('state', 'in', ('verify', 'done', 'paid')),
            ])
        else:
            payslips = self.env['hr.payslip'].search([
                ('employee_id', '=', self.employee_id.id),
                ('state', 'in', ('done', 'paid')),
                ('date_to', '>=', self.date_from),
                ('date_to', '<=', self.date_to)
            ])
        if payslips:
            self.payslip_ids = [(6, 0, payslips.ids)]
        self._consolidate_lines()

    def update_total(self):
        """Actualiza los totales del documento."""
        devengados = sum(
            (line.total + (line.total_2 or 0)) for line in self.line_ids
            if line.salary_rule_id.devengado_rule_id
        )
        deducciones = sum(
            abs(line.total) for line in self.line_ids
            if line.salary_rule_id.deduccion_rule_id
        )
        self.total_devengos = round(devengados, 2)
        self.total_deducciones = round(deducciones, 2)
        self.total_paid = round(devengados - deducciones, 2)

    # Códigos de reglas salariales de provisiones
    PROVISION_CODES = {
        'PRV_PRIM', 'PRV_CES', 'PRV_ICES', 'PRV_VAC',
        'CONS_CES', 'CONS_INT', 'CONS_VAC',
    }

    # Mapeo: código provisión -> códigos de pago real del mismo concepto DIAN
    PROVISION_TO_ACTUAL = {
        'PRV_PRIM': {'PRIMA'},
        'PRV_CES': {'CESANTIAS', 'CES_YEAR', 'CONS_CES'},
        'PRV_ICES': {'INTCESANTIAS', 'INTCES_YEAR', 'CONS_INT'},
        'PRV_VAC': {'VACDISFRUTADAS', 'VACANOVE', 'VACATIONS_MONEY', 'VACCONTRATO', 'CONS_VAC'},
    }

    # Códigos de pagos anuales correspondientes al año ANTERIOR
    # CES_YEAR = Cesantías Año Anterior (consignación al fondo, antes de Feb 14)
    # INTCES_YEAR = Intereses Cesantías Año Anterior (pago directo al empleado)
    ANNUAL_PREV_YEAR_CODES = {'CES_YEAR', 'INTCES_YEAR'}

    # Códigos de cesantías e intereses para consolidación XML DIAN
    CESANTIAS_CODES = {'CESANTIAS', 'CES_YEAR', 'CONS_CES'}
    INTEREST_CODES = {'INTCESANTIAS', 'INTCES_YEAR', 'CONS_INT'}

    def _get_previously_reported_provisions(self, year=None):
        """Obtiene el total de provisiones ya reportadas en EDIs exitosos anteriores
        del mismo empleado.

        Args:
            year: Año específico donde buscar provisiones. Si es None, busca en
                  el año actual (date_from) en periodos anteriores al actual.
                  Útil para CES_YEAR/INTCES_YEAR que son pagos anuales del año
                  anterior y necesitan restar provisiones de ese año.

        Retorna dict: {código_dian: total_ya_reportado}
        Ej: {'Cesantias': 800000, 'IntCesantias': 96000, ...}
        """
        if not self.employee_id or not self.date_from:
            return {}

        if year:
            # Buscar en un año específico (todas las EDIs de ese año)
            from datetime import date as date_cls
            year_start = date_cls(year, 1, 1)
            year_end = date_cls(year, 12, 31)
            previous_edis = self.search([
                ('employee_id', '=', self.employee_id.id),
                ('date_from', '>=', year_start),
                ('date_to', '<=', year_end),
                ('state_dian', '=', 'exitoso'),
                ('credit_note', '=', False),
                ('id', '!=', self.id),
            ])
        else:
            # Buscar en el año actual, periodos anteriores
            year_start = self.date_from.replace(month=1, day=1)
            previous_edis = self.search([
                ('employee_id', '=', self.employee_id.id),
                ('date_from', '>=', year_start),
                ('date_to', '<', self.date_from),
                ('state_dian', '=', 'exitoso'),
                ('credit_note', '=', False),
                ('id', '!=', self.id),
            ])

        reported = {}
        for edi in previous_edis:
            for line in edi.line_ids:
                if line.code in self.PROVISION_CODES and line.salary_rule_id.devengado_rule_id:
                    dian_code = line.salary_rule_id.devengado_rule_id.code
                    reported.setdefault(dian_code, 0)
                    reported[dian_code] += abs(line.total)
        return reported

    def _get_external_reported_provisions(self, year=None):
        """Obtiene provisiones reportadas en un sistema externo vía acumulados
        de nómina con tipo 'Carga Inicial' o 'Ajuste Manual'.

        Busca en hr.accumulated.payroll registros del empleado para el año
        indicado, filtrando por reglas salariales de provisión (PRV_CES, etc.).

        Args:
            year: Año donde buscar. Si None, usa el año de date_from.

        Retorna dict: {código_dian: total_externo}
        """
        if not self.employee_id or not self.use_external_accumulated:
            return {}

        target_year = year or (self.date_from.year if self.date_from else False)
        if not target_year:
            return {}

        from datetime import date as date_cls
        year_start = date_cls(target_year, 1, 1)
        year_end = date_cls(target_year, 12, 31)

        AccPayroll = self.env['hr.accumulated.payroll']
        accumulated = AccPayroll.search([
            ('employee_id', '=', self.employee_id.id),
            ('date', '>=', year_start),
            ('date', '<=', year_end),
            ('accumulated_type', 'in', ('inception', 'adjustment')),
            ('salary_rule_id', '!=', False),
        ])

        reported = {}
        for acc in accumulated:
            rule = acc.salary_rule_id
            if rule.code in self.PROVISION_CODES and rule.devengado_rule_id:
                dian_code = rule.devengado_rule_id.code
                reported.setdefault(dian_code, 0)
                reported[dian_code] += abs(acc.amount)
        return reported

    def _consolidate_lines(self):
        """Consolida las líneas de las nóminas relacionadas.

        Lógica de provisiones:
        - 'include': Incluye provisiones. Si coexisten con pago real del mismo
          concepto DIAN, resta las provisiones ya reportadas en EDIs anteriores
          del año para enviar solo la diferencia.
        - 'exclude': Omite las provisiones completamente.
        - 'only': Solo incluye las provisiones.

        Lógica de pagos anuales (CES_YEAR, INTCES_YEAR):
        Estos son pagos correspondientes al año ANTERIOR (ej: cesantías 2025
        pagadas en enero 2026). Si provision_mode='include', se restan las
        provisiones reportadas durante el año anterior.

        Consolidación DIAN:
        El XML DIAN tiene un único nodo <Cesantias> con Pago (cesantías) y
        PagoIntereses (intereses). La consolidación fusiona las líneas de
        intereses (INTCESANTIAS, INTCES_YEAR) en total_2/rate_2 del nodo
        cesantías, y suma múltiples líneas de cesantías en una sola.
        """
        self.line_ids.unlink()
        self.worked_days_line_ids.unlink()

        if not self.payslip_ids:
            return

        provision_mode = self.provision_mode or 'include'

        # Recolectar todos los códigos presentes en las nóminas del periodo
        all_codes = set()
        for payslip in self.payslip_ids:
            for line in payslip.line_ids:
                if line.salary_rule_id.devengado_rule_id or line.salary_rule_id.deduccion_rule_id:
                    all_codes.add(line.code)

        # Determinar si hay pago real para cada concepto de provisión
        # Si PRIMA existe en el periodo, no incluir PRV_PRIM (evitar doble conteo)
        provision_has_actual = set()
        if provision_mode == 'include':
            for prv_code, actual_codes in self.PROVISION_TO_ACTUAL.items():
                if prv_code in all_codes and actual_codes & all_codes:
                    provision_has_actual.add(prv_code)

        # Consolidar líneas salariales
        lines_data = {}
        for payslip in self.payslip_ids:
            for line in payslip.line_ids:
                if not line.salary_rule_id.devengado_rule_id and \
                   not line.salary_rule_id.deduccion_rule_id:
                    continue

                # Filtrar según modo de provisiones
                is_provision = line.code in self.PROVISION_CODES
                if provision_mode == 'exclude' and is_provision:
                    continue
                if provision_mode == 'only' and not is_provision:
                    continue
                # Excluir provisión cuando coexiste con pago real en el mismo periodo
                if line.code in provision_has_actual:
                    continue
                # Usar leave_id en key para mantener ausencias individuales
                leave_id = getattr(line, 'leave_id', False) and line.leave_id.id or False
                key = (line.salary_rule_id.id, line.code, leave_id)
                if key not in lines_data:
                    lines_data[key] = {
                        'salary_rule_id': line.salary_rule_id.id,
                        'code': line.code,
                        'name': line.name,
                        'quantity': 0,
                        'rate': line.rate,
                        'amount': 0,
                        'total': 0,
                        'slip_id': self.id,
                        'employee_id': self.employee_id.id,
                        'version_id': self.version_id.id,
                    }
                    if leave_id:
                        lines_data[key]['leave_id'] = leave_id
                lines_data[key]['quantity'] += line.quantity
                lines_data[key]['total'] += line.total

        for data in lines_data.values():
            # Licencia No Remunerada: solo reporta días, sin valor monetario para DIAN
            rule = self.env['hr.salary.rule'].browse(data['salary_rule_id'])
            dev_code = rule.devengado_rule_id.code if rule.devengado_rule_id else ''
            is_nr = ('NO_REMUNERADA' in (rule.code or '').upper()
                     or dev_code == 'LicenciaNR')
            if is_nr:
                data['amount'] = 0
                data['rate'] = 0
            elif data['quantity'] != 0:
                if data['rate'] and data['rate'] != 0:
                    # amount = total / (quantity * rate / 100)
                    data['amount'] = data['total'] / (data['quantity'] * data['rate'] / 100)
                else:
                    data['amount'] = data['total'] / data['quantity']
            self.env['hr.payslip.edi.line'].create(data)

        # Garantizar conceptos obligatorios DIAN (Básico, Salud, Pensión)
        # Estos deben existir siempre en el XML aunque tengan valor 0
        existing_codes = {d['code'] for d in lines_data.values()}
        MANDATORY_DIAN_CODES = {
            'BASIC': {'name': 'Sueldo Básico', 'quantity': 30, 'rate': 100.0},
            'SSOCIAL001': {'name': 'Salud Empleado', 'quantity': -1, 'rate': 4.0},
            'SSOCIAL002': {'name': 'Pensión Empleado', 'quantity': -1, 'rate': 4.0},
        }
        SalaryRule = self.env['hr.salary.rule']
        for mcode, defaults in MANDATORY_DIAN_CODES.items():
            if mcode not in existing_codes:
                rule = SalaryRule.search([
                    ('code', '=', mcode),
                    '|', ('devengado_rule_id', '!=', False),
                         ('deduccion_rule_id', '!=', False),
                ], limit=1)
                if rule:
                    self.env['hr.payslip.edi.line'].create({
                        'salary_rule_id': rule.id,
                        'code': mcode,
                        'name': defaults['name'],
                        'quantity': defaults['quantity'],
                        'rate': defaults['rate'],
                        'amount': 0,
                        'total': 0,
                        'slip_id': self.id,
                        'employee_id': self.employee_id.id,
                        'version_id': self.version_id.id,
                    })

        # ── PASO 5: Restar provisiones del AÑO ACTUAL reportadas anteriormente ──
        # Solo aplica a pagos del periodo actual (CESANTIAS, INTCESANTIAS, PRIMA, etc.)
        # Los pagos anuales del año anterior (CES_YEAR, INTCES_YEAR) se manejan aparte
        if provision_has_actual and provision_mode == 'include':
            reported = self._get_previously_reported_provisions()
            # Incluir provisiones de sistema externo (acumulados carga inicial)
            ext_reported = self._get_external_reported_provisions()
            for k, v in ext_reported.items():
                reported.setdefault(k, 0)
                reported[k] += v
            if reported:
                # Mapeo inverso: código provisión -> código DIAN
                prv_to_dian = {}
                for prv_code in provision_has_actual:
                    rule = self.env['hr.salary.rule'].search(
                        [('code', '=', prv_code)], limit=1
                    )
                    if rule and rule.devengado_rule_id:
                        prv_to_dian[prv_code] = rule.devengado_rule_id.code

                for prv_code, dian_code in prv_to_dian.items():
                    if dian_code not in reported:
                        continue
                    amount_to_subtract = reported[dian_code]
                    # Buscar líneas del pago real (NO anuales del año anterior)
                    for line in self.line_ids:
                        if line.code in self.ANNUAL_PREV_YEAR_CODES:
                            continue  # CES_YEAR/INTCES_YEAR se manejan en paso 6
                        if not line.salary_rule_id.devengado_rule_id:
                            continue
                        if line.salary_rule_id.devengado_rule_id.code == dian_code \
                                and line.code not in self.PROVISION_CODES:
                            original = line.total
                            adjusted = original - amount_to_subtract
                            line.write({
                                'total': adjusted,
                                'amount': adjusted / line.quantity if line.quantity else adjusted,
                            })
                            amount_to_subtract = 0
                            break

        # ── PASO 6: Restar provisiones del AÑO ANTERIOR para pagos anuales ──
        # CES_YEAR = Cesantías Año Anterior, INTCES_YEAR = Intereses Año Anterior
        # Estos pagos corresponden a provisiones reportadas durante el año anterior
        annual_codes_present = self.ANNUAL_PREV_YEAR_CODES & all_codes
        if annual_codes_present and provision_mode == 'include':
            prev_year = self.date_from.year - 1
            prev_reported = self._get_previously_reported_provisions(year=prev_year)
            # Incluir provisiones de sistema externo del año anterior
            ext_prev_reported = self._get_external_reported_provisions(year=prev_year)
            for k, v in ext_prev_reported.items():
                prev_reported.setdefault(k, 0)
                prev_reported[k] += v
            if prev_reported:
                for annual_code in annual_codes_present:
                    rule = self.env['hr.salary.rule'].search(
                        [('code', '=', annual_code)], limit=1
                    )
                    if rule and rule.devengado_rule_id:
                        dian_code = rule.devengado_rule_id.code
                        if dian_code in prev_reported:
                            amount_to_subtract = prev_reported[dian_code]
                            for line in self.line_ids:
                                if line.code == annual_code:
                                    original = line.total
                                    adjusted = original - amount_to_subtract
                                    if adjusted < 0:
                                        adjusted = 0
                                    line.write({
                                        'total': adjusted,
                                        'amount': adjusted / line.quantity if line.quantity else adjusted,
                                    })
                                    break

        # ── PASO 7: Consolidar cesantías e intereses para XML DIAN ──
        # El XML DIAN tiene un solo nodo <Cesantias Pago="X" Porcentaje="Y"
        # PagoIntereses="Z"/>. Debemos:
        # a) Fusionar múltiples líneas de cesantías (CESANTIAS + CES_YEAR) en una
        # b) Mover intereses (INTCESANTIAS, INTCES_YEAR) a total_2/rate_2 de cesantías
        cesantias_lines = self.line_ids.filtered(
            lambda l: l.code in self.CESANTIAS_CODES
        )
        interest_lines = self.line_ids.filtered(
            lambda l: l.code in self.INTEREST_CODES
        )

        if cesantias_lines:
            primary_ces = cesantias_lines[0]
            # a) Si hay múltiples líneas de cesantías, sumar en la primera
            if len(cesantias_lines) > 1:
                total_ces = sum(l.total for l in cesantias_lines)
                total_qty = sum(l.quantity for l in cesantias_lines)
                primary_ces.write({
                    'total': total_ces,
                    'quantity': total_qty or 1,
                    'amount': total_ces / (total_qty or 1),
                })
                (cesantias_lines - primary_ces).unlink()

            # b) Fusionar intereses en cesantías como total_2/rate_2
            if interest_lines:
                total_interest = sum(abs(l.total) for l in interest_lines)
                # Obtener tasa de interés (normalmente 12% anual)
                interest_rate = 12.0
                for il in interest_lines:
                    if il.rate and il.rate > 0:
                        interest_rate = il.rate
                        break
                primary_ces.write({
                    'total_2': total_interest,
                    'rate_2': interest_rate,
                })
                interest_lines.unlink()
        elif interest_lines:
            # Hay intereses pero no cesantías (caso inusual)
            # Crear nodo cesantías con Pago=0 y los intereses como PagoIntereses
            primary_int = interest_lines[0]
            total_interest = sum(abs(l.total) for l in interest_lines)
            interest_rate = 12.0
            for il in interest_lines:
                if il.rate and il.rate > 0:
                    interest_rate = il.rate
                    break
            primary_int.write({
                'total_2': total_interest,
                'rate_2': interest_rate,
                'total': 0,
                'code': 'CESANTIAS',  # Código base cesantías para nodo DIAN
            })
            if len(interest_lines) > 1:
                (interest_lines - primary_int).unlink()

        # Consolidar días trabajados
        worked_days = {}
        for payslip in self.payslip_ids:
            for wd in payslip.worked_days_line_ids:
                key = (wd.work_entry_type_id.id, wd.code)
                if key not in worked_days:
                    worked_days[key] = {
                        'payslip_id': self.id,
                        'work_entry_type_id': wd.work_entry_type_id.id,
                        'number_of_days': 0,
                        'number_of_hours': 0,
                        'amount': 0,
                        'version_id': self.version_id.id,
                    }
                worked_days[key]['number_of_days'] += wd.number_of_days
                worked_days[key]['number_of_hours'] += wd.number_of_hours
                worked_days[key]['amount'] += wd.amount

        for data in worked_days.values():
            # Limitar WORK100 a 30 días
            if data.get('code') == 'WORK100':
                data['number_of_days'] = min(data['number_of_days'], 30)
            self.env['hr.payslip.edi.worked_days'].create(data)

        # ── PASO 9: Líneas informativas de ausencias y dotaciones ──
        self._create_info_lines_absences_dotations()

    def _create_info_lines_absences_dotations(self):
        """Crea líneas informativas para ausencias y dotaciones del periodo.

        Las líneas informativas no van al XML DIAN pero permiten reportes
        internos con cantidad, valor, fechas y tipo de ausencia/dotación.
        """
        EdiLine = self.env['hr.payslip.edi.line']

        # --- Ausencias: buscar hr.leave del empleado en el periodo ---
        if self.employee_id and self.date_from and self.date_to:
            leaves = self.env['hr.leave'].search([
                ('employee_id', '=', self.employee_id.id),
                ('state', '=', 'validate'),
                ('date_from', '<=', self.date_to),
                ('date_to', '>=', self.date_from),
            ])
            for leave in leaves:
                leave_type = leave.holiday_status_id
                EdiLine.create({
                    'slip_id': self.id,
                    'employee_id': self.employee_id.id,
                    'contract_id': self.contract_id.id if self.contract_id else False,
                    'line_type': 'informativo',
                    'info_type': 'ausencia',
                    'code': 'INFO_AUSENCIA',
                    'name': leave_type.name if leave_type else 'Ausencia',
                    'quantity': leave.number_of_days or 0,
                    'amount': 0,
                    'total': 0,
                    'rate': 0,
                    'leave_id': leave.id,
                    'departure_date': leave.date_from.date() if leave.date_from else False,
                    'return_date': leave.date_to.date() if leave.date_to else False,
                    'info_value': leave_type.name if leave_type else '',
                    'info_code': leave_type.code if leave_type and hasattr(leave_type, 'code') else '',
                    'info_notes': 'Días: %s | %s - %s' % (
                        leave.number_of_days or 0,
                        leave.date_from.strftime('%Y-%m-%d') if leave.date_from else '',
                        leave.date_to.strftime('%Y-%m-%d') if leave.date_to else '',
                    ),
                })

        # --- Dotaciones: buscar en líneas de nómina con código DOTACION ---
        for payslip in self.payslip_ids:
            for line in payslip.line_ids:
                if line.code == 'DOTACION' and line.total:
                    EdiLine.create({
                        'slip_id': self.id,
                        'employee_id': self.employee_id.id,
                        'version_id': self.version_id.id if self.version_id else False,
                        'line_type': 'informativo',
                        'info_type': 'dotacion',
                        'code': 'INFO_DOTACION',
                        'name': line.name or 'Dotación',
                        'quantity': line.quantity or 1,
                        'amount': abs(line.total),
                        'total': abs(line.total),
                        'rate': 100,
                        'info_value': '{:,.0f}'.format(abs(line.total)),
                        'info_notes': 'Dotación del periodo %s' % (
                            self.date_from.strftime('%B %Y') if self.date_from else ''),
                    })

    # ================================================================
    # MÉTODOS PARA XML GENERATOR
    # ================================================================

    def _get_number(self):
        # NO usar padding — la DIAN rechaza con ZE02
        prefix = self._get_sequence().prefix or ''
        consecutivo = self._get_consecutivo()
        return f"{prefix}{consecutivo}" if consecutivo else (self.number or '')

    def _get_total_devengados(self):
        return '{:.2f}'.format(abs(self.total_devengos))

    def _get_total_deducciones(self):
        return '{:.2f}'.format(abs(self.total_deducciones))

    def _get_total_pagado(self):
        return '{:.2f}'.format(abs(self.total_paid))

    def _get_emisor(self):
        return self.company_id.partner_id

    def _get_employee(self):
        return self.employee_id.work_contact_id or self.employee_id

    def _get_employee_object(self):
        return self.employee_id

    def _get_contract(self):
        return self.version_id

    def _get_company_id(self):
        return self.company_id

    def _get_tipo_xml(self):
        return '103' if self.credit_note else '102'

    def _get_tipo_ambiente(self):
        return '1' if self.company_id.production_payroll else '2'

    def _get_sequence(self):
        # En notas de ajuste usar la secuencia de notas (con su propio prefix);
        # asi _get_consecutivo() retira correctamente el prefix completo.
        if self.credit_note and self.company_id.sequence_payroll_note_id:
            return self.company_id.sequence_payroll_note_id
        return self.company_id.sequence_payroll_id

    def _get_consecutivo(self):
        # NO usar padding — la DIAN rechaza con ZE02 (ej: 00000062 → 62)
        number = self.number or ''
        prefix = self._get_sequence().prefix or ''
        raw = number.replace(prefix, '')
        return raw.lstrip('0') or '0'

    def _get_notes(self):
        return self.note or ''

    def _get_url_qr(self):
        return 'https://catalogo-vpfe.dian.gov.co/document/searchqr?documentkey='

    def get_subtipo_trabajador(self):
        """Obtiene el código del subtipo de trabajador."""
        try:
            employee = self.employee_id
            if employee.subtipo_coti_id:
                return employee.subtipo_coti_id.code or '00'
        except Exception:
            pass
        return '00'

    def return_number_document_type(self, code):
        """Convierte código de documento a código DIAN."""
        mapping = {
            'CC': '13',  # Cédula de ciudadanía
            'CE': '22',  # Cédula de extranjería
            'TI': '12',  # Tarjeta de identidad
            'PA': '41',  # Pasaporte
            'RC': '11',  # Registro civil
            'NIT': '31', # NIT
            'PE': '47',  # Permiso especial permanencia
        }
        return mapping.get(code, '13')

    def _integral(self, modality_salary):
        """Determina si el salario es integral."""
        if modality_salary == 'integral':
            return 'true'
        return 'false'

    def type_contract_e(self, contract_type):
        """Convierte tipo de contrato a código DIAN."""
        mapping = {
            'fijo': '1',
            'indefinido': '2',
            'obra_labor': '3',
            'aprendizaje': '4',
            'practicante': '5',
        }
        if isinstance(contract_type, str):
            return mapping.get(contract_type, '1')
        return '1'

    def get_bank_information(self, r_bank=0, r_type=0, r_account=0):
        """Obtiene información bancaria del empleado."""
        try:
            employee = self.employee_id
            if not employee.bank_account_id:
                return None

            bank_account = employee.bank_account_id
            if r_bank:
                if bank_account.bank_id:
                    return bank_account.bank_id.bic or bank_account.bank_id.name[:3]
                return None
            if r_type:
                try:
                    return 'CA' if bank_account.account_type == 'savings' else 'CC'
                except Exception:
                    return 'CC'
            if r_account:
                return bank_account.acc_number
        except Exception:
            pass
        return None

    @property
    def nes_dev_line_ids(self):
        """Líneas de devengados para XML DIAN (excluyendo informativas)."""
        return self.line_ids.filtered(
            lambda l: l.line_type != 'informativo' and l.salary_rule_id and l.salary_rule_id.devengado_rule_id
        )

    @property
    def nes_ded_line_ids(self):
        """Líneas de deducciones para XML DIAN (excluyendo informativas)."""
        return self.line_ids.filtered(
            lambda l: l.line_type != 'informativo' and l.salary_rule_id and l.salary_rule_id.deduccion_rule_id
        )

    # ================================================================
    # AJUSTES PARCIALES (FASE 2)
    # ================================================================

    def action_create_partial_adjustment_wizard(self):
        """Abre wizard para ajuste parcial de conceptos."""
        self.ensure_one()
        if self.state_dian != 'exitoso':
            raise UserError(_('Solo puede crear ajuste de documentos exitosos.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Ajuste Parcial - %s') % self.number,
            'res_model': 'hr.payslip.edi.partial.adjustment',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_source_edi_id': self.id,
            },
        }

    # ================================================================
    # DETECCIÓN AUTOMÁTICA DE AJUSTES (FASE 3)
    # ================================================================

    @api.model
    def detect_adjustment_candidates(self, domain=None):
        """Busca documentos exitosos que podrían necesitar ajuste.

        Retorna lista de dicts: [{'edi_id': id, 'reasons': [...]}]
        """
        base_domain = [
            ('state_dian', '=', 'exitoso'),
            ('credit_note', '=', False),
        ]
        if domain:
            base_domain += domain

        edis = self.search(base_domain)
        candidates = []

        for edi in edis:
            # Saltar si ya tiene un hijo exitoso (ya fue reemplazado)
            if any(c.state_dian == 'exitoso' for c in edi.child_edi_ids):
                continue

            reasons = []

            # 1. Datos del empleado cambiaron después del envío
            partner = edi.employee_id.work_contact_id
            if partner and partner.write_date and edi.write_date:
                if partner.write_date > edi.write_date:
                    reasons.append(_(
                        'Datos del empleado modificados después del envío (%s)'
                    ) % fields.Datetime.to_string(partner.write_date))

            # 2. Nómina base recalculada
            for payslip in edi.payslip_ids:
                if payslip.write_date and edi.write_date:
                    if payslip.write_date > edi.write_date:
                        reasons.append(_(
                            'Nómina %s recalculada después del envío'
                        ) % payslip.number)
                        break

            # 3. Advertencia de provisiones (valores negativos)
            if edi.provision_warning:
                reasons.append(_(
                    'Tiene alertas de provisiones con valores negativos'
                ))

            if reasons:
                candidates.append({
                    'edi_id': edi.id,
                    'reasons': reasons,
                })

        return candidates

    # ================================================================
    # TEST XML
    # ================================================================

    def action_test_xml(self):
        """Genera XML de prueba sin firma para previsualizar."""
        self.ensure_one()

        generator = self.env['nomina.xml.generator']
        errors = []
        xml_content = ''
        cune = ''

        try:
            # Validar datos básicos
            validation_errors = generator.validate_all(self, raise_error=False)
            if validation_errors:
                errors = validation_errors if isinstance(validation_errors, list) else [validation_errors]
        except Exception as e:
            errors.append(str(e))

        try:
            # Generar constantes DIAN
            dian_constants = generator.get_dian_constants(self)

            # Generar CUNE
            cune = generator.generate_cune(self, dian_constants)
            dian_constants['CUNE'] = cune

            # Generar XML sin firma
            if self.credit_note:
                previous_payslip = generator._find_previous_payslip(self)
                xml_content = generator.generate_nomina_ajuste(
                    self, dian_constants, previous_payslip
                )
            else:
                xml_content = generator.generate_nomina_individual(self, dian_constants)

            # Formatear XML para mejor lectura
            try:
                from lxml import etree
                parser = etree.XMLParser(remove_blank_text=True)
                root = etree.fromstring(xml_content.encode('utf-8'), parser=parser)
                xml_content = etree.tostring(
                    root, encoding='unicode', pretty_print=True
                )
            except Exception:
                pass  # Mantener XML sin formatear si falla

        except Exception as e:
            errors.append(f"Error generando XML: {str(e)}")

        # Crear wizard con resultado
        wizard = self.env['hr.payslip.edi.xml.preview'].create({
            'payslip_edi_id': self.id,
            'xml_content': xml_content,
            'validation_errors': '\n'.join(errors) if errors else False,
            'cune': cune,
        })

        return {
            'type': 'ir.actions.act_window',
            'name': _('Test XML - %s') % self.number,
            'res_model': 'hr.payslip.edi.xml.preview',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }
