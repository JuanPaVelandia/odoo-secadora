# -*- coding: utf-8 -*-
from odoo import api, fields, models, _, Command
from odoo.addons.l10n_co_exogenous_information_reporting.models.l10n_co_exogenous_format_field_account import NATURE_ACCOUNT_SELECTION

class L10ncoExogenousFormatSettingLine(models.Model):
    _name = "l10n_co.exogenous_format_setting_line"
    _description = "Modelo para la configuración de los conceptos y categorías para las líneas de reporte exógeno"

    concept_id = fields.Many2one('l10n_co.exogenous_concept', string='Concepto', check_company=True)
    format_field_id = fields.Many2one('l10n_co.exogenous_format_field', string='Columna reporte', check_company=True)
    format_setting_id = fields.Many2one('l10n_co.exogenous_format_setting', string='Configuración de formato', check_company=True)
    apply_concepts = fields.Boolean(string='Aplicar conceptos', related='format_setting_id.apply_concepts', readonly=True)

    account_ids = fields.Many2many(
        comodel_name='account.account',
        relation='l10n_co_exogenous_setting_line_account_rel',
        column1='setting_line_id',
        column2='account_id',
        string='Cuentas')
    account_pattern = fields.Char(
        string='Patrón cuentas',
        help="Patrones separados por coma. Ej: 5105%, 5110%")
    account_count = fields.Integer(
        string='No. Cuentas',
        compute='_compute_account_count')
    nature_account = fields.Selection(
        selection=NATURE_ACCOUNT_SELECTION,
        string='Naturaleza',
        default='db_cr')

    # --- Campos de condición por línea (F2) ---
    move_type_filter = fields.Selection([
        ('all', 'Todos'),
        ('entry', 'Asiento contable'),
        ('out_invoice', 'Factura de venta'),
        ('out_refund', 'Nota crédito venta'),
        ('in_invoice', 'Factura de compra'),
        ('in_refund', 'Nota crédito compra'),
    ], string='Tipo movimiento', default='all',
        help='Filtra líneas por tipo de movimiento contable')
    exclude_reconciled = fields.Boolean(
        string='Excluir conciliadas', default=False,
        help='Excluye líneas que ya tienen conciliación completa (full_reconcile_id)')
    only_with_tax = fields.Boolean(
        string='Solo con impuesto', default=False,
        help='Solo incluye líneas que tengan impuestos asociados (tax_ids o tax_line_id)')
    custom_line_domain = fields.Char(
        string='Dominio línea',
        help=(
            'Dominio adicional en formato Odoo para filtrar las líneas de movimiento de esta columna. '
            'Se evalúa sobre account.move.line y se combina (AND) con los demás filtros de la columna. '
            'Ejemplo: [("account_id.code", "=like", "13%"), ("debit", ">", 0)]'
        ))

    journal_ids = fields.Many2many(
        comodel_name='account.journal',
        relation='l10n_co_exogenous_setting_line_journal_rel',
        column1='setting_line_id', column2='journal_id',
        string='Solo diarios',
        help='Si se especifican, solo considera líneas en estos diarios. '
             'Útil para reportes de saldos de cuentas de ahorro/corriente: 1 línea por diario bancario.')
    group_by_journal = fields.Boolean(
        string='Agrupar por diario',
        default=False,
        help='Genera una fila por (partner, diario) en lugar de solo por partner. '
             'Útil para reportar saldos por cuenta de ahorro/corriente individuales.')

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
        self.ensure_one()
        if not self.account_pattern:
            return self.env['account.account']

        patterns = [p.strip() for p in self.account_pattern.split(',') if p.strip()]
        if not patterns:
            return self.env['account.account']

        company = self.format_setting_id.company_id or self.env.company
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
