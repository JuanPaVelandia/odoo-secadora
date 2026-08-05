# -*- coding: utf-8 -*-
from odoo import api, fields, models, _, Command

NATURE_ACCOUNT_SELECTION = [
    ('debit', 'DB - Solo debitos'),
    ('credit', 'CR - Solo creditos'),
    ('db_cr', 'DB-CR - Debito menos credito'),
    ('cr_db', 'CR-DB - Credito menos debito'),
    ('base_calc_db', 'Base calculada DB'),
    ('base_calc_cr', 'Base calculada CR'),
    ('base_calc_db_cr', 'Base calculada DB-CR'),
    ('base_calc_cr_db', 'Base calculada CR-DB'),
    ('tax_base_amount', 'Base almacenada'),
]

NATURE_ACCOUNT_HELP = (
    "Formula de acumulacion segun resolucion DIAN:\n"
    "- DB: Suma solo valores debito de las lineas\n"
    "- CR: Suma solo valores credito de las lineas\n"
    "- DB-CR: Diferencia debito menos credito (naturaleza debito)\n"
    "- CR-DB: Diferencia credito menos debito (naturaleza credito)\n"
    "- Base calculada DB: tax_base_amount solo cuando hay debito > 0\n"
    "- Base calculada CR: tax_base_amount solo cuando hay credito > 0\n"
    "- Base calculada DB-CR: tax_base_amount cuando (DB-CR) != 0\n"
    "- Base calculada CR-DB: tax_base_amount cuando (CR-DB) != 0\n"
    "- Base almacenada: campo tax_base_amount directo (base sobre la cual se practico retencion)\n\n"
    "Impacto en la consulta:\n"
    "- DB/CR/DB-CR/CR-DB: usa campos debit y credit de account.move.line\n"
    "- Base calculada: usa tax_base_amount condicionado a debito/credito\n"
    "- Base almacenada: usa tax_base_amount directamente"
)

NATURE_LABELS = {
    'debit': 'DB', 'credit': 'CR',
    'db_cr': 'DB-CR', 'cr_db': 'CR-DB',
    'base_calc_db': 'Base DB', 'base_calc_cr': 'Base CR',
    'base_calc_db_cr': 'Base DB-CR', 'base_calc_cr_db': 'Base CR-DB',
    'tax_base_amount': 'Base almacenada', 'balance': 'Saldo',
}


class L10ncoExogenousFormatFieldsAccount(models.Model):
    """Configuracion de cuentas y formula por campo de formato dentro de un concepto"""
    _name = "l10n_co.exogenous_format_field_account"
    _description = "Configuración de cuentas por campo de formato"
    _check_company_auto = True

    nature_account = fields.Selection(
        selection=NATURE_ACCOUNT_SELECTION,
        string='Formula',
        default='db_cr',
        help=NATURE_ACCOUNT_HELP
    )
    account_pattern = fields.Char(
        string='Patrón de cuentas',
        help="Patrones de cuenta separados por coma. Ej: 5105%, 5110%"
    )
    account_ids = fields.Many2many(
        comodel_name='account.account',
        relation='l10n_co_exogenous_field_account_account_rel',
        column1='field_account_id',
        column2='account_id',
        string='Cuentas',
        check_company=True
    )
    account_count = fields.Integer(
        string='No. Cuentas',
        compute='_compute_account_count'
    )
    format_field_id = fields.Many2one('l10n_co.exogenous_format_field',
        string='Campo de formato',
        check_company=True)
    concept_id = fields.Many2one('l10n_co.exogenous_concept',
        string='Concepto',
        check_company=True)
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        default=lambda self: self.env.company
    )

    @api.depends('account_ids')
    def _compute_account_count(self):
        for rec in self:
            rec.account_count = len(rec.account_ids)

    @api.onchange('account_pattern')
    def _onchange_account_pattern(self):
        """Carga cuentas automaticamente cuando cambia el patron"""
        if self.account_pattern:
            accounts = self._get_accounts_from_pattern()
            if accounts:
                self.account_ids = [Command.set(accounts.ids)]

    def _get_accounts_from_pattern(self):
        """Obtiene cuentas basadas en el patron definido (Odoo 14: company_id Many2one)"""
        self.ensure_one()
        if not self.account_pattern:
            return self.env['account.account']

        patterns = [p.strip() for p in self.account_pattern.split(',') if p.strip()]
        if not patterns:
            return self.env['account.account']

        company = self.company_id or self.env.company
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
