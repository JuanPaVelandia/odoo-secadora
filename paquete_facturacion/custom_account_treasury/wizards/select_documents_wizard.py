from odoo import fields, models, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class SelectDocumentsWizard(models.TransientModel):
    _name = 'select.documents.wizard'
    _description = 'Wizard para selección de documentos a pagar/cobrar'

    payment_id = fields.Many2one('account.payment', string='Pago', required=True)
    payment_type = fields.Selection(related='payment_id.payment_type')
    partner_type = fields.Selection(related='payment_id.partner_type')
    currency_id = fields.Many2one(related='payment_id.currency_id')
    company_id = fields.Many2one(related='payment_id.company_id')

    # Filtros
    filter_partner_ids = fields.Many2many(
        'res.partner',
        'wizard_filter_partner_rel',
        string='Filtrar por Terceros',
        help='Seleccione uno o más terceros para filtrar. Deje vacío para ver todos.'
    )
    filter_account_ids = fields.Many2many(
        'account.account',
        'wizard_filter_account_rel',
        string='Filtrar por Cuentas',
        help='Seleccione cuentas específicas'
    )
    filter_date_from = fields.Date(string='Desde')
    filter_date_to = fields.Date(string='Hasta')
    filter_amount_min = fields.Float(string='Monto Mínimo')
    filter_amount_max = fields.Float(string='Monto Máximo')

    # Filtro de vencimiento
    filter_due_status = fields.Selection([
        ('all', 'Todos'),
        ('overdue', 'Vencidos'),
        ('due_soon', 'Por Vencer (7 días)'),
        ('not_due', 'No Vencidos'),
    ], string='Estado de Vencimiento', default='all')

    # Tipo de documento a buscar
    document_type = fields.Selection([
        ('receivable', 'Por Cobrar'),
        ('payable', 'Por Pagar'),
        ('advance', 'Anticipos'),
        ('all', 'Todos'),
    ], string='Tipo de Documento', default='all')

    # Líneas de documentos disponibles
    line_ids = fields.One2many(
        'select.documents.wizard.line',
        'wizard_id',
        string='Documentos Disponibles'
    )

    # Totales
    total_selected = fields.Monetary(
        string='Total Seleccionado',
        compute='_compute_totals',
        currency_field='currency_id'
    )
    total_documents = fields.Integer(
        string='Documentos Seleccionados',
        compute='_compute_totals'
    )

    @api.depends('line_ids.selected', 'line_ids.amount_to_pay')
    def _compute_totals(self):
        for wizard in self:
            selected_lines = wizard.line_ids.filtered('selected')
            wizard.total_selected = sum(selected_lines.mapped('amount_to_pay'))
            wizard.total_documents = len(selected_lines)

    @api.onchange('filter_partner_ids', 'filter_account_ids', 'filter_date_from',
                  'filter_date_to', 'filter_amount_min', 'filter_amount_max', 'document_type',
                  'filter_due_status')
    def _onchange_filters(self):
        """Recargar documentos cuando cambian los filtros"""
        self._load_documents()

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        payment_id = self.env.context.get('active_id')
        if payment_id:
            payment = self.env['account.payment'].browse(payment_id)
            res['payment_id'] = payment_id
            # Establecer tipo de documento según el tipo de pago
            if payment.partner_type == 'customer':
                res['document_type'] = 'receivable'
            elif payment.partner_type == 'supplier':
                res['document_type'] = 'payable'
            else:
                res['document_type'] = 'all'
        return res

    def _load_documents(self):
        """Carga los documentos disponibles según los filtros"""
        self.ensure_one()

        # Limpiar líneas existentes
        self.line_ids = [(5, 0, 0)]

        if not self.payment_id:
            return

        # Construir dominio base
        domain = [
            ('reconciled', '=', False),
            ('amount_residual', '!=', 0),
            ('company_id', '=', self.company_id.id),
            ('parent_state', '=', 'posted'),
        ]

        # Filtrar por tipo de documento
        if self.document_type == 'receivable':
            domain.append(('account_id.account_type', '=', 'asset_receivable'))
        elif self.document_type == 'payable':
            domain.append(('account_id.account_type', '=', 'liability_payable'))
        elif self.document_type == 'advance':
            # Anticipos: buscar en cuentas de anticipo (sin company_id en Odoo 18)
            advance_accounts = self.env['account.account'].search([
                ('code', 'like', '1305%')
            ])
            if advance_accounts:
                domain.append(('account_id', 'in', advance_accounts.ids))

        # Filtrar por terceros
        if self.filter_partner_ids:
            domain.append(('partner_id', 'in', self.filter_partner_ids.ids))

        # Filtrar por cuentas
        if self.filter_account_ids:
            domain.append(('account_id', 'in', self.filter_account_ids.ids))

        # Filtrar por fechas
        if self.filter_date_from:
            domain.append(('date', '>=', self.filter_date_from))
        if self.filter_date_to:
            domain.append(('date', '<=', self.filter_date_to))

        # Filtrar por estado de vencimiento
        today = fields.Date.context_today(self)
        if self.filter_due_status == 'overdue':
            # Vencidos: fecha de vencimiento < hoy
            domain.append(('date_maturity', '<', today))
        elif self.filter_due_status == 'due_soon':
            # Por vencer en 7 días
            from datetime import timedelta
            next_week = today + timedelta(days=7)
            domain.extend([
                ('date_maturity', '>=', today),
                ('date_maturity', '<=', next_week)
            ])
        elif self.filter_due_status == 'not_due':
            # No vencidos
            domain.append(('date_maturity', '>=', today))

        # Buscar líneas de movimiento
        move_lines = self.env['account.move.line'].search(domain, limit=200, order='partner_id, account_id, date')

        # Filtrar por monto si está definido
        if self.filter_amount_min or self.filter_amount_max:
            filtered_lines = move_lines.filtered(lambda l:
                (not self.filter_amount_min or abs(l.amount_residual) >= self.filter_amount_min) and
                (not self.filter_amount_max or abs(l.amount_residual) <= self.filter_amount_max)
            )
            move_lines = filtered_lines

        # Excluir líneas ya agregadas al pago
        existing_move_lines = self.payment_id.payment_line_ids.mapped('move_line_id')
        move_lines = move_lines - existing_move_lines

        # Crear líneas del wizard
        line_vals = []
        for ml in move_lines:
            line_vals.append((0, 0, {
                'wizard_id': self.id,
                'move_line_id': ml.id,
                'partner_id': ml.partner_id.id,
                'account_id': ml.account_id.id,
                'move_id': ml.move_id.id,
                'date': ml.date,
                'date_maturity': ml.date_maturity,
                'name': ml.name or ml.move_id.name,
                'amount_residual': ml.amount_residual,
                'amount_to_pay': abs(ml.amount_residual),
                'currency_id': ml.currency_id.id or ml.company_currency_id.id,
                'selected': False,
            }))

        self.line_ids = line_vals

    def action_load_documents(self):
        """Botón para recargar documentos"""
        self._load_documents()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_select_all(self):
        """Seleccionar todos los documentos visibles"""
        self.line_ids.write({'selected': True})
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_deselect_all(self):
        """Deseleccionar todos los documentos"""
        self.line_ids.write({'selected': False})
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_select_by_partner(self):
        """Seleccionar todos los documentos de los terceros filtrados"""
        if self.filter_partner_ids:
            self.line_ids.filtered(
                lambda l: l.partner_id in self.filter_partner_ids
            ).write({'selected': True})
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_confirm(self):
        """Agregar los documentos seleccionados al pago"""
        self.ensure_one()

        selected_lines = self.line_ids.filtered('selected')
        if not selected_lines:
            raise UserError(_('Debe seleccionar al menos un documento.'))

        # Obtener las move_lines seleccionadas
        move_lines = selected_lines.mapped('move_line_id')

        # Llamar al método del pago para agregar las líneas
        self.payment_id._change_and_add_payment_detail(move_lines)

        return {'type': 'ir.actions.act_window_close'}


class SelectDocumentsWizardLine(models.TransientModel):
    _name = 'select.documents.wizard.line'
    _description = 'Línea del wizard de selección de documentos'
    _order = 'partner_id, account_id, date'

    wizard_id = fields.Many2one('select.documents.wizard', string='Wizard', ondelete='cascade')
    selected = fields.Boolean(string='Sel.', default=False)
    move_line_id = fields.Many2one('account.move.line', string='Línea Contable')
    move_id = fields.Many2one('account.move', string='Documento')
    partner_id = fields.Many2one('res.partner', string='Tercero')
    account_id = fields.Many2one('account.account', string='Cuenta')
    date = fields.Date(string='Fecha')
    date_maturity = fields.Date(string='Vencimiento')
    name = fields.Char(string='Referencia')
    amount_residual = fields.Monetary(string='Saldo', currency_field='currency_id')
    amount_to_pay = fields.Monetary(string='A Pagar', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='Moneda')

    def action_toggle_select(self):
        """Toggle selección"""
        for line in self:
            line.selected = not line.selected
