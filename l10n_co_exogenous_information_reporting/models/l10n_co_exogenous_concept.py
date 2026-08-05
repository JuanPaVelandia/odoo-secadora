# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class L10ncoExogenousConcept(models.Model):
    _name = "l10n_co.exogenous_concept"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Plantilla para la creación de conceptos de información exógena"
    _check_company_auto = True
    _rec_name = 'display_name'
    _order = 'format_id, code'

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for rec in self:
            concept_name = rec.name or ''
            if len(concept_name) > 100:
                concept_name = concept_name[:100] + '...'
            rec.display_name = f'[{rec.code}] {concept_name}'

    name = fields.Text(string='Nombre', tracking=True)
    code = fields.Char(string='Código', tracking=True, size=4)
    format_id = fields.Many2one('l10n_co.exogenous_format',
        string='Formato',
        tracking=True,
        ondelete='cascade',
        check_company=True)
    active = fields.Boolean(string='Activo', default=True, tracking=True)
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        default=lambda self: self.env.company.id
    )
    report_with_informan_nit = fields.Boolean(
        string="¿Reportar con NIT del informante?",
        default=False
    )

    field_account_ids = fields.One2many(
        comodel_name='l10n_co.exogenous_format_field_account',
        inverse_name='concept_id',
        string='Configuración por campo',
        help="Configure las cuentas y fórmula DIAN para cada columna del reporte"
    )
    field_account_count = fields.Integer(
        string='Campos configurados',
        compute='_compute_field_account_count',
        store=True
    )
    account_count = fields.Integer(
        string='No. Cuentas',
        compute='_compute_account_count',
        store=True
    )

    @api.depends('field_account_ids', 'field_account_ids.account_ids')
    def _compute_account_count(self):
        for rec in self:
            rec.account_count = sum(len(fa.account_ids) for fa in rec.field_account_ids)

    @api.depends('field_account_ids')
    def _compute_field_account_count(self):
        for rec in self:
            rec.field_account_count = len(rec.field_account_ids)

    def action_view_all_accounts(self):
        """Abre vista con todas las cuentas de todos los campos configurados"""
        self.ensure_one()
        all_account_ids = self.field_account_ids.mapped('account_ids').ids
        return {
            'type': 'ir.actions.act_window',
            'name': _('Cuentas - %s') % self.code,
            'res_model': 'account.account',
            'view_mode': 'list,form',
            'domain': [('id', 'in', all_account_ids)],
            'context': {'create': False},
        }

    def get_accounts_for_report(self, format_field_id=None):
        """Obtiene cuentas para el reporte desde field_account_ids"""
        self.ensure_one()
        if format_field_id and self.field_account_ids:
            field_account = self.field_account_ids.filtered(
                lambda fa: fa.format_field_id.id == format_field_id
            )
            if field_account:
                return field_account[0].account_ids or self.env['account.account']
        return self.env['account.account']

    def get_nature_for_report(self, format_field_id=None):
        """Obtiene la formula de acumulacion para el reporte

        Busca en field_account_ids la configuracion especifica para el campo.
        Si no encuentra, retorna 'db_cr' como formula por defecto.

        Args:
            format_field_id: ID del campo de formato
        """
        self.ensure_one()
        if format_field_id and self.field_account_ids:
            field_account = self.field_account_ids.filtered(
                lambda fa: fa.format_field_id.id == format_field_id
            )
            if field_account:
                return field_account[0].nature_account or 'db_cr'
        return 'db_cr'

    def get_field_account_config(self, format_field_id):
        """Obtiene la configuración completa para un campo de formato"""
        self.ensure_one()
        if self.field_account_ids:
            return self.field_account_ids.filtered(
                lambda fa: fa.format_field_id.id == format_field_id
            )[:1]
        return self.env['l10n_co.exogenous_format_field_account']