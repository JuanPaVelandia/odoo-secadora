# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _, Command
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

CERTIFICATE_TYPES = [
    ('ica', 'Retención de ICA'),
    ('iva', 'Retención de IVA'),
    ('timbre', 'Retención de Timbre'),
    ('fuente', 'Retención en la Fuente'),
]


class L10nCoExogenousCertificateConfig(models.Model):
    _name = 'l10n_co.exogenous_certificate_config'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Configuración de certificados de retención'
    _check_company_auto = True
    _rec_name = 'display_name'

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        default=lambda self: self.env.company,
        required=True,
        tracking=True)

    certificate_type = fields.Selection(
        selection=CERTIFICATE_TYPES,
        string='Tipo de certificado',
        required=True,
        tracking=True)

    line_ids = fields.One2many(
        comodel_name='l10n_co.exogenous_certificate_config_line',
        inverse_name='config_id',
        string='Cuentas contables')

    # Solo para IVA: cuentas de compras y de IVA descontable
    purchase_account_ids = fields.Many2many(
        comodel_name='account.account',
        relation='l10n_co_cert_config_purchase_account_rel',
        string='Cuentas contables de compras',
        help='Cuentas de gastos, costos y compras que se mostrarán como valor facturado. '
             'Aplica únicamente para retención de IVA')

    iva_deductible_account_ids = fields.Many2many(
        comodel_name='account.account',
        relation='l10n_co_cert_config_iva_deductible_rel',
        string='Cuentas contables de IVA descontable',
        help='Cuentas donde se registra IVA descontable. '
             'Aplica únicamente para retención de IVA')

    report_title = fields.Char(
        string='Título del certificado',
        help='Nombre personalizado que aparecerá en el encabezado del certificado PDF. '
             'Si se deja vacío se usará el nombre por defecto según el tipo')

    report_style = fields.Selection([
        ('classic', 'Clásico'),
        ('modern', 'Moderno'),
    ], string='Estilo del certificado',
        default='classic',
        help='Clásico: formato tradicional con tabla de conceptos. '
             'Moderno: formato con secciones numeradas y colores')

    report_template = fields.Html(
        string='Plantilla personalizada',
        help='Plantilla HTML personalizada para el cuerpo del certificado. '
             'Si se deja vacío se usa la plantilla estándar')

    signer_name = fields.Char(
        string='Nombre del firmante',
        help='Nombre que aparecerá en la sección de firma del certificado')

    signer_position = fields.Char(
        string='Cargo del firmante',
        help='Cargo que aparecerá bajo la firma')

    signer_signature = fields.Binary(
        string='Imagen de firma',
        help='Imagen de la firma digitalizada para incluir en el certificado')

    article = fields.Char(
        string='Artículo legal',
        default='ART. 10 DECRETO 836/91',
        help='Referencia al artículo legal que ampara el certificado')

    consecutive_sequence_id = fields.Many2one(
        comodel_name='ir.sequence',
        string='Secuencia de consecutivo',
        help='Secuencia para generar consecutivos automáticos en los certificados')

    active = fields.Boolean(default=True)

    display_name = fields.Char(
        compute='_compute_display_name', store=True)

    _unique_type_company = models.Constraint(
        'UNIQUE(certificate_type, company_id)',
        'Solo puede existir una configuración por tipo de certificado y compañía')

    @api.depends('certificate_type', 'company_id')
    def _compute_display_name(self):
        type_labels = dict(CERTIFICATE_TYPES)
        for rec in self:
            type_name = type_labels.get(rec.certificate_type, '')
            company_name = rec.company_id.name or ''
            rec.display_name = f"{type_name} - {company_name}"

    @api.constrains('purchase_account_ids', 'iva_deductible_account_ids', 'certificate_type')
    def _check_iva_accounts(self):
        for rec in self:
            if rec.certificate_type != 'iva':
                if rec.purchase_account_ids or rec.iva_deductible_account_ids:
                    raise ValidationError(
                        _('Las cuentas de compras e IVA descontable solo aplican para retención de IVA'))

    def action_open_mass_send_wizard(self):
        """Abre el wizard de envío masivo de certificados"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Envío masivo de certificados'),
            'res_model': 'l10n_co.exogenous_certificate_send_wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_config_id': self.id,
                'default_certificate_type': self.certificate_type,
                'dialog_size': 'extra-large',
            },
        }


class L10nCoExogenousCertificateConfigLine(models.Model):
    _name = 'l10n_co.exogenous_certificate_config_line'
    _description = 'Línea de configuración de certificado - cuenta contable'
    _order = 'id'

    config_id = fields.Many2one('l10n_co.exogenous_certificate_config',
        string='Configuración',
        required=True,
        ondelete='cascade',
        check_company=True)

    account_ids = fields.Many2many(
        comodel_name='account.account',
        relation='l10n_co_cert_config_line_account_rel',
        column1='config_line_id',
        column2='account_id',
        string='Cuentas contables')

    concept_name = fields.Char(
        string='Nombre concepto',
        help='Nombre personalizado que aparecerá en el certificado. '
             'Si se deja vacío se usa el nombre de la cuenta contable. '
             'Útil para agrupar varias cuentas bajo un solo concepto')

    account_pattern = fields.Char(
        string='Patrón cuentas',
        help='Patrones separados por coma. Ej: 2368%, 236801')

    account_count = fields.Integer(
        string='No. Cuentas',
        compute='_compute_account_count')

    city_id = fields.Many2one(
        comodel_name='res.city',
        string='Ciudad',
        help='Ciudad asociada a esta cuenta. Aplica únicamente para retención de ICA')

    certificate_type = fields.Selection(
        related='config_id.certificate_type',
        store=True,
        readonly=True)

    nature_account = fields.Selection([
        ('debit', 'Débito'),
        ('credit', 'Crédito'),
        ('db_cr', 'Débito - Crédito'),
        ('cr_db', 'Crédito - Débito'),
        ('base_calc_db', 'Base (Débito)'),
        ('base_calc_cr', 'Base (Crédito)'),
        ('base_calc_db_cr', 'Base (Débito - Crédito)'),
        ('base_calc_cr_db', 'Base (Crédito - Débito)'),
        ('tax_base_amount', 'Base imponible'),
    ], string='Naturaleza', default='cr_db',
        help='Fórmula de cálculo para el valor de retención')

    @api.depends('account_ids')
    def _compute_account_count(self):
        for rec in self:
            rec.account_count = len(rec.account_ids)

    @api.onchange('account_pattern')
    def _onchange_account_pattern(self):
        if self.account_pattern:
            accounts = self._get_accounts_from_pattern()
            if accounts:
                self.account_ids = [Command.set(accounts.ids)]

    def _get_accounts_from_pattern(self):
        """Resuelve patrón de cuentas a cuentas reales (misma lógica que format_setting_line)"""
        self.ensure_one()
        if not self.account_pattern:
            return self.env['account.account']

        patterns = [p.strip() for p in self.account_pattern.split(',') if p.strip()]
        if not patterns:
            return self.env['account.account']

        company = self.config_id.company_id or self.env.company
        Account = self.env['account.account']
        domain = [*Account._check_company_domain(company)]
        pattern_domain = []

        for pattern in patterns:
            if '%' in pattern:
                pattern_domain.append(('code', '=like', pattern))
            else:
                pattern_domain.append(('code', '=', pattern))

        if len(pattern_domain) == 1:
            domain.append(pattern_domain[0])
        elif len(pattern_domain) > 1:
            or_domain = ['|'] * (len(pattern_domain) - 1)
            domain = domain + or_domain + pattern_domain

        return Account.search(domain, order='code')

    def get_resolved_accounts(self):
        """Obtiene las cuentas resueltas: account_ids > patrón"""
        self.ensure_one()
        if self.account_ids:
            return self.account_ids
        if self.account_pattern:
            return self._get_accounts_from_pattern()
        return self.env['account.account']
