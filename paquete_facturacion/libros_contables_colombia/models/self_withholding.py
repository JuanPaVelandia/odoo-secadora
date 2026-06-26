# -*- coding: utf-8 -*-
"""
Modelo de Autoretención para Colombia.

Gestiona autoretenciones de:
- ICA (Impuesto de Industria y Comercio)
- Renta (Impuesto sobre la Renta)

Permite configurar las tasas por municipio/actividad y generar
asientos de autoretención de forma global.
"""
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import date
from collections import defaultdict
import logging

_logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURACIÓN DE AUTORETENCIÓN
# ============================================================================

class SelfWithholdingConfig(models.Model):
    """
    Configuración de autoretención por empresa/municipio.

    Define qué autoretenciones aplican y sus tasas.
    """
    _name = 'self.withholding.config'
    _description = 'Self-Withholding Configuration'
    _order = 'company_id, municipality_id, withholding_type'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    active = fields.Boolean(default=True)

    # Tipo de autoretención
    withholding_type = fields.Selection([
        ('ica', 'ICA - Industria y Comercio'),
        ('renta', 'Renta - Impuesto sobre la Renta'),
    ], string='Withholding Type', required=True)

    # Para ICA: municipio específico
    municipality_id = fields.Many2one(
        'res.city',
        string='Municipality',
        help='Municipality for ICA self-withholding. Leave empty for general config.',
    )

    # Tasa de autoretención
    rate = fields.Float(
        string='Rate (%)',
        digits=(10, 4),
        required=True,
        help='Self-withholding rate as percentage (e.g., 1.5 for 1.5%)',
    )
    rate_per_mil = fields.Float(
        string='Rate (‰)',
        compute='_compute_rate_per_mil',
        inverse='_inverse_rate_per_mil',
        digits=(10, 4),
        help='Rate in per thousand',
    )

    # Cuentas contables
    income_account_prefix = fields.Char(
        string='Income Account Prefix',
        default='41',
        help='Prefix for income accounts to apply self-withholding (e.g., 41 for all operational income)',
    )
    expense_account_id = fields.Many2one(
        'account.account',
        string='Self-Withholding Expense Account',
        help='Account to debit the self-withholding (e.g., 236805 for ICA, 236515 for Renta)',
    )
    liability_account_id = fields.Many2one(
        'account.account',
        string='Self-Withholding Liability Account',
        help='Account to credit the self-withholding payable',
    )

    # Umbral mínimo
    min_base_uvt = fields.Float(
        string='Minimum Base (UVT)',
        default=0,
        help='Minimum base in UVT to apply self-withholding. 0 = no minimum.',
    )
    min_base_amount = fields.Float(
        string='Minimum Base Amount',
        compute='_compute_min_base_amount',
        digits='Product Price',
    )

    # Vigencia
    date_from = fields.Date(
        string='Valid From',
        required=True,
        default=fields.Date.context_today,
    )
    date_to = fields.Date(string='Valid To')

    # Referencia legal
    legal_reference = fields.Char(
        string='Legal Reference',
        help='Resolution, decree or agreement reference',
    )
    notes = fields.Text(string='Notes')

    _sql_constraints = [
        ('unique_config',
         'unique(company_id, withholding_type, municipality_id, date_from)',
         'A configuration for this type/municipality/date already exists!'),
    ]

    @api.depends('rate')
    def _compute_rate_per_mil(self):
        for record in self:
            record.rate_per_mil = record.rate * 10  # % to ‰

    def _inverse_rate_per_mil(self):
        for record in self:
            record.rate = record.rate_per_mil / 10  # ‰ to %

    @api.depends('min_base_uvt')
    def _compute_min_base_amount(self):
        """Compute minimum base in currency"""
        TaxParam = self.env.get('tax.general.parameter')
        today = fields.Date.context_today(self)

        for record in self:
            if record.min_base_uvt and TaxParam:
                try:
                    uvt_value = TaxParam.get_uvt_value(today, record.company_id.id)
                    record.min_base_amount = record.min_base_uvt * uvt_value
                except Exception:
                    record.min_base_amount = record.min_base_uvt * 49799  # UVT 2025
            else:
                record.min_base_amount = 0.0

    @api.constrains('rate')
    def _check_rate(self):
        for record in self:
            if record.rate < 0:
                raise ValidationError(_('Rate cannot be negative.'))
            if record.rate > 20:
                raise ValidationError(_('Rate seems too high (max 20%). Please verify.'))

    def _compute_display_name(self):
        for record in self:
            name_parts = [
                dict(self._fields['withholding_type'].selection).get(record.withholding_type, ''),
            ]
            if record.municipality_id:
                name_parts.append(record.municipality_id.name)
            name_parts.append(f"{record.rate}%")
            record.display_name = ' - '.join(name_parts)

    @api.model
    def get_applicable_config(self, withholding_type, municipality_id=None, date_eval=None, company_id=None):
        """
        Get the applicable self-withholding configuration.

        Args:
            withholding_type: 'ica' or 'renta'
            municipality_id: Municipality ID for ICA
            date_eval: Date for evaluation
            company_id: Company ID

        Returns:
            self.withholding.config record or False
        """
        if not date_eval:
            date_eval = fields.Date.context_today(self)
        if not company_id:
            company_id = self.env.company.id

        domain = [
            ('withholding_type', '=', withholding_type),
            ('company_id', '=', company_id),
            ('date_from', '<=', date_eval),
            ('active', '=', True),
            '|',
            ('date_to', '>=', date_eval),
            ('date_to', '=', False),
        ]

        # For ICA, try specific municipality first
        if withholding_type == 'ica' and municipality_id:
            domain_specific = domain + [('municipality_id', '=', municipality_id)]
            config = self.search(domain_specific, limit=1, order='date_from desc')
            if config:
                return config

        # Fall back to general config (no municipality)
        domain_general = domain + [('municipality_id', '=', False)]
        return self.search(domain_general, limit=1, order='date_from desc')


# ============================================================================
# LÍNEAS DE AUTORETENCIÓN CALCULADAS
# ============================================================================

class SelfWithholdingLine(models.TransientModel):
    """
    Líneas de autoretención calculadas pero no aplicadas.

    Permite revisar antes de generar el asiento.
    Es TransientModel porque está ligada al wizard temporal.
    """
    _name = 'self.withholding.line'
    _description = 'Self-Withholding Calculated Line'
    _order = 'date desc, move_id'

    wizard_id = fields.Many2one(
        'self.withholding.wizard',
        string='Wizard',
        ondelete='cascade',
    )

    # Documento origen
    move_id = fields.Many2one(
        'account.move',
        string='Invoice/Entry',
        required=True,
    )
    date = fields.Date(related='move_id.date', store=True)
    move_name = fields.Char(related='move_id.name', store=True)
    partner_id = fields.Many2one(related='move_id.partner_id', store=True)

    # Configuración usada
    config_id = fields.Many2one(
        'self.withholding.config',
        string='Configuration',
    )
    withholding_type = fields.Selection(related='config_id.withholding_type', store=True)
    municipality_id = fields.Many2one(related='config_id.municipality_id', store=True)

    # Cálculo
    base_amount = fields.Float(
        string='Base Amount',
        digits='Product Price',
    )
    rate = fields.Float(
        string='Rate (%)',
        digits=(10, 4),
    )
    withholding_amount = fields.Float(
        string='Withholding Amount',
        digits='Product Price',
    )

    # Estado
    state = fields.Selection([
        ('draft', 'Draft'),
        ('applied', 'Applied'),
        ('cancelled', 'Cancelled'),
    ], string='State', default='draft')

    # Asiento generado
    generated_move_id = fields.Many2one(
        'account.move',
        string='Generated Entry',
    )

    account_code = fields.Char(
        string='Income Account',
        help='Income account code that generated this withholding',
    )


# ============================================================================
# WIZARD PARA CALCULAR Y APLICAR AUTORETENCIONES
# ============================================================================

class SelfWithholdingWizard(models.TransientModel):
    """
    Wizard para calcular y aplicar autoretenciones de forma masiva.

    Proceso:
    1. Seleccionar período y tipo de autoretención
    2. Calcular base gravable desde cuentas de ingresos
    3. Revisar líneas calculadas
    4. Generar asiento de autoretención
    """
    _name = 'self.withholding.wizard'
    _description = 'Self-Withholding Calculation Wizard'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )

    # Período
    date_from = fields.Date(
        string='From Date',
        required=True,
        default=lambda self: date.today().replace(day=1),
    )
    date_to = fields.Date(
        string='To Date',
        required=True,
        default=fields.Date.context_today,
    )

    # Tipo de autoretención
    withholding_type = fields.Selection([
        ('ica', 'ICA - Industria y Comercio'),
        ('renta', 'Renta - Impuesto sobre la Renta'),
        ('both', 'Ambos (ICA y Renta)'),
    ], string='Withholding Type', required=True, default='both')

    # Para ICA específico
    municipality_id = fields.Many2one(
        'res.city',
        string='Municipality (ICA)',
        help='Specific municipality for ICA. Leave empty to use company default.',
    )

    # Opciones
    include_posted_only = fields.Boolean(
        string='Posted Entries Only',
        default=True,
    )
    exclude_already_applied = fields.Boolean(
        string='Exclude Already Applied',
        default=True,
        help='Exclude invoices that already have self-withholding entries',
    )

    # Diario para el asiento
    journal_id = fields.Many2one(
        'account.journal',
        string='Journal',
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
        help='Journal for the self-withholding entry',
    )

    # Resultados
    state = fields.Selection([
        ('draft', 'Configuration'),
        ('calculated', 'Calculated'),
        ('applied', 'Applied'),
    ], string='State', default='draft')

    line_ids = fields.One2many(
        'self.withholding.line',
        'wizard_id',
        string='Calculated Lines',
    )

    # Totales
    total_base_ica = fields.Float(
        string='Total Base ICA',
        compute='_compute_totals',
        digits='Product Price',
    )
    total_withholding_ica = fields.Float(
        string='Total ICA Withholding',
        compute='_compute_totals',
        digits='Product Price',
    )
    total_base_renta = fields.Float(
        string='Total Base Renta',
        compute='_compute_totals',
        digits='Product Price',
    )
    total_withholding_renta = fields.Float(
        string='Total Renta Withholding',
        compute='_compute_totals',
        digits='Product Price',
    )

    # Asiento generado
    generated_move_id = fields.Many2one(
        'account.move',
        string='Generated Entry',
        readonly=True,
    )

    @api.depends('line_ids.withholding_type', 'line_ids.base_amount', 'line_ids.withholding_amount')
    def _compute_totals(self):
        for wizard in self:
            ica_lines = wizard.line_ids.filtered(lambda l: l.withholding_type == 'ica')
            renta_lines = wizard.line_ids.filtered(lambda l: l.withholding_type == 'renta')

            wizard.total_base_ica = sum(ica_lines.mapped('base_amount'))
            wizard.total_withholding_ica = sum(ica_lines.mapped('withholding_amount'))
            wizard.total_base_renta = sum(renta_lines.mapped('base_amount'))
            wizard.total_withholding_renta = sum(renta_lines.mapped('withholding_amount'))

    def action_calculate(self):
        """Calculate self-withholding from income accounts"""
        self.ensure_one()

        # Clear previous lines
        self.line_ids.unlink()

        lines_to_create = []

        # Get configurations
        configs = []
        if self.withholding_type in ('ica', 'both'):
            ica_config = self.env['self.withholding.config'].get_applicable_config(
                'ica',
                municipality_id=self.municipality_id.id if self.municipality_id else None,
                date_eval=self.date_to,
                company_id=self.company_id.id,
            )
            if ica_config:
                configs.append(ica_config)

        if self.withholding_type in ('renta', 'both'):
            renta_config = self.env['self.withholding.config'].get_applicable_config(
                'renta',
                date_eval=self.date_to,
                company_id=self.company_id.id,
            )
            if renta_config:
                configs.append(renta_config)

        if not configs:
            raise UserError(_(
                'No self-withholding configuration found for the selected type and period. '
                'Please configure self-withholding rates first.'
            ))

        # Query income by invoice
        for config in configs:
            income_prefix = config.income_account_prefix or '41'
            min_base = config.min_base_amount or 0

            # Get income amounts grouped by invoice
            query = """
                SELECT
                    am.id as move_id,
                    aa.code_store->>'1' as account_code,
                    SUM(CASE
                        WHEN aml.balance < 0 THEN ABS(aml.balance)
                        ELSE 0
                    END) as income_amount
                FROM account_move_line aml
                JOIN account_move am ON am.id = aml.move_id
                JOIN account_account aa ON aa.id = aml.account_id
                WHERE am.date >= %s
                    AND am.date <= %s
                    AND am.company_id = %s
                    AND am.state = 'posted'
                    AND am.move_type IN ('out_invoice', 'out_refund')
                    AND (aa.code_store->>'1') LIKE %s
                GROUP BY am.id, aa.code_store->>'1'
                HAVING SUM(CASE WHEN aml.balance < 0 THEN ABS(aml.balance) ELSE 0 END) > %s
                ORDER BY am.id
            """

            self.env.cr.execute(query, (
                self.date_from,
                self.date_to,
                self.company_id.id,
                f"{income_prefix}%",
                min_base,
            ))

            results = self.env.cr.dictfetchall()

            # Group by move
            move_totals = defaultdict(lambda: {'base': 0, 'accounts': []})
            for row in results:
                move_id = row['move_id']
                move_totals[move_id]['base'] += row['income_amount']
                move_totals[move_id]['accounts'].append(row['account_code'])

            # Create lines
            for move_id, data in move_totals.items():
                base = data['base']
                withholding = base * (config.rate / 100)

                lines_to_create.append({
                    'wizard_id': self.id,
                    'move_id': move_id,
                    'config_id': config.id,
                    'base_amount': base,
                    'rate': config.rate,
                    'withholding_amount': withholding,
                    'account_code': ', '.join(sorted(set(data['accounts']))),
                })

        # Create all lines
        self.env['self.withholding.line'].create(lines_to_create)

        self.state = 'calculated'

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_apply(self):
        """Generate accounting entry for self-withholdings"""
        self.ensure_one()

        if not self.line_ids:
            raise UserError(_('No lines to apply. Please calculate first.'))

        if not self.journal_id:
            raise UserError(_('Please select a journal for the entry.'))

        # Group lines by config
        lines_by_config = defaultdict(list)
        for line in self.line_ids.filtered(lambda l: l.state == 'draft'):
            lines_by_config[line.config_id].append(line)

        if not lines_by_config:
            raise UserError(_('No pending lines to apply.'))

        # Create one entry with all withholdings
        move_lines = []
        total_amount = 0

        for config, lines in lines_by_config.items():
            if not config.expense_account_id or not config.liability_account_id:
                raise UserError(_(
                    'Please configure expense and liability accounts for %s configuration.'
                ) % config.display_name)

            amount = sum(l.withholding_amount for l in lines)
            total_amount += amount

            # Debit: Expense (gasto autoretención)
            move_lines.append((0, 0, {
                'name': f"Autoretención {config.get_withholding_type_display()} - {self.date_from.strftime('%m/%Y')}",
                'account_id': config.expense_account_id.id,
                'debit': amount,
                'credit': 0,
            }))

            # Credit: Liability (autoretención por pagar)
            move_lines.append((0, 0, {
                'name': f"Autoretención {config.get_withholding_type_display()} por pagar",
                'account_id': config.liability_account_id.id,
                'debit': 0,
                'credit': amount,
            }))

        # Create move
        move_vals = {
            'move_type': 'entry',
            'date': self.date_to,
            'journal_id': self.journal_id.id,
            'company_id': self.company_id.id,
            'ref': f"Autoretención {self.date_from.strftime('%m/%Y')}",
            'line_ids': move_lines,
        }

        move = self.env['account.move'].create(move_vals)

        # Update lines
        self.line_ids.write({
            'state': 'applied',
            'generated_move_id': move.id,
        })

        self.generated_move_id = move
        self.state = 'applied'

        return {
            'type': 'ir.actions.act_window',
            'name': _('Self-Withholding Entry'),
            'res_model': 'account.move',
            'res_id': move.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_entry(self):
        """View the generated entry"""
        self.ensure_one()
        if not self.generated_move_id:
            raise UserError(_('No entry has been generated yet.'))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Self-Withholding Entry'),
            'res_model': 'account.move',
            'res_id': self.generated_move_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_reset(self):
        """Reset to draft state"""
        self.ensure_one()
        self.line_ids.unlink()
        self.state = 'draft'
        self.generated_move_id = False
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }


# ============================================================================
# EXTENSIÓN DE RES.COMPANY PARA AUTORETENCIONES
# ============================================================================

class ResCompanySelfWithholding(models.Model):
    """Extension to company for self-withholding settings"""
    _inherit = 'res.company'

    # Autoretención ICA
    self_withholding_ica = fields.Boolean(
        string='Self-Withholding ICA',
        help='Company performs self-withholding of ICA',
    )
    self_withholding_ica_rate = fields.Float(
        string='ICA Self-Withholding Rate (%)',
        digits=(10, 4),
        help='Default ICA self-withholding rate',
    )
    self_withholding_ica_account_id = fields.Many2one(
        'account.account',
        string='ICA Self-Withholding Account',
        help='Account for ICA self-withholding liability (e.g., 236805)',
    )

    # Autoretención Renta
    self_withholding_renta = fields.Boolean(
        string='Self-Withholding Renta',
        help='Company performs self-withholding of income tax',
    )
    self_withholding_renta_rate = fields.Float(
        string='Renta Self-Withholding Rate (%)',
        digits=(10, 4),
        help='Default income tax self-withholding rate',
    )
    self_withholding_renta_account_id = fields.Many2one(
        'account.account',
        string='Renta Self-Withholding Account',
        help='Account for income tax self-withholding liability (e.g., 236515)',
    )
