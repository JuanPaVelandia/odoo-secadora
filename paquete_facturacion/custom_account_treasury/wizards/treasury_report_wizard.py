# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime, timedelta


class TreasuryPaymentBookWizard(models.TransientModel):
    """Wizard para generar el Libro de Pagos"""
    _name = 'treasury.payment.book.wizard'
    _description = 'Wizard Libro de Pagos'

    date_from = fields.Date(
        string='Fecha Desde',
        required=True,
        default=lambda self: fields.Date.today().replace(day=1)
    )
    date_to = fields.Date(
        string='Fecha Hasta',
        required=True,
        default=fields.Date.today
    )
    journal_ids = fields.Many2many(
        'account.journal',
        string='Diarios',
        domain="[('type', 'in', ['bank', 'cash'])]",
        help="Dejar vacío para incluir todos los diarios de banco y caja"
    )
    payment_type = fields.Selection([
        ('all', 'Todos'),
        ('inbound', 'Cobros (Ingresos)'),
        ('outbound', 'Pagos (Egresos)'),
    ], string='Tipo de Movimiento', default='all', required=True)
    partner_id = fields.Many2one(
        'res.partner',
        string='Tercero',
        help="Filtrar por tercero específico"
    )
    state_filter = fields.Selection([
        ('all', 'Todos'),
        ('posted', 'Publicados'),
        ('draft', 'Borrador'),
    ], string='Estado', default='posted', required=True)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from > wizard.date_to:
                raise UserError(_('La fecha desde no puede ser mayor que la fecha hasta.'))

    def _get_payments_domain(self):
        """Construye el dominio para buscar pagos"""
        domain = [
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('company_id', '=', self.env.company.id),
        ]

        if self.journal_ids:
            domain.append(('journal_id', 'in', self.journal_ids.ids))
        else:
            # Solo diarios de banco y caja
            journals = self.env['account.journal'].search([
                ('type', 'in', ['bank', 'cash']),
                ('company_id', '=', self.env.company.id)
            ])
            domain.append(('journal_id', 'in', journals.ids))

        if self.payment_type != 'all':
            domain.append(('payment_type', '=', self.payment_type))

        if self.partner_id:
            domain.append(('partner_id', '=', self.partner_id.id))

        if self.state_filter != 'all':
            domain.append(('state', '=', self.state_filter))
        else:
            domain.append(('state', 'in', ['draft', 'posted']))

        return domain

    def _get_report_data(self):
        """Obtiene los datos para el reporte"""
        domain = self._get_payments_domain()
        payments = self.env['account.payment'].search(domain, order='date, id')

        # Agrupar por diario
        journals_data = {}
        for payment in payments:
            journal_id = payment.journal_id.id
            if journal_id not in journals_data:
                journals_data[journal_id] = {
                    'journal': payment.journal_id,
                    'payments': [],
                    'total_inbound': 0,
                    'total_outbound': 0,
                }
            journals_data[journal_id]['payments'].append(payment)
            if payment.payment_type == 'inbound':
                journals_data[journal_id]['total_inbound'] += payment.amount
            else:
                journals_data[journal_id]['total_outbound'] += payment.amount

        return {
            'wizard': self,
            'journals_data': journals_data,
            'payments': payments,
            'total_inbound': sum(p.amount for p in payments if p.payment_type == 'inbound'),
            'total_outbound': sum(p.amount for p in payments if p.payment_type == 'outbound'),
            'company': self.env.company,
            'print_date': fields.Datetime.now(),
        }

    def action_print_report(self):
        """Genera el reporte PDF"""
        self.ensure_one()
        data = self._get_report_data()
        return self.env.ref('custom_account_treasury.action_report_payment_book').report_action(self, data=data)

    def action_view_payments(self):
        """Abre la vista de pagos filtrada"""
        self.ensure_one()
        domain = self._get_payments_domain()
        return {
            'name': _('Libro de Pagos'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'view_mode': 'list,form',
            'domain': domain,
            'context': {'search_default_group_by_journal': 1},
        }


class TreasuryCashBoxWizard(models.TransientModel):
    """Wizard para generar el Arqueo de Caja"""
    _name = 'treasury.cash.box.wizard'
    _description = 'Wizard Arqueo de Caja'

    date_from = fields.Date(
        string='Fecha Desde',
        required=True,
        default=lambda self: fields.Date.today().replace(day=1)
    )
    date_to = fields.Date(
        string='Fecha Hasta',
        required=True,
        default=fields.Date.today
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Caja',
        domain="[('type', '=', 'cash')]",
        required=True,
        help="Seleccione la caja para el arqueo"
    )
    include_details = fields.Boolean(
        string='Incluir Detalle de Movimientos',
        default=True,
        help="Mostrar cada movimiento individual"
    )

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from > wizard.date_to:
                raise UserError(_('La fecha desde no puede ser mayor que la fecha hasta.'))

    def _get_opening_balance(self):
        """Calcula el saldo de apertura (antes de date_from)"""
        query = """
            SELECT COALESCE(SUM(aml.balance), 0) as balance
            FROM account_move_line aml
            JOIN account_move am ON aml.move_id = am.id
            WHERE aml.account_id = %s
                AND aml.date < %s
                AND am.state = 'posted'
                AND aml.company_id = %s
        """
        self.env.cr.execute(query, (
            self.journal_id.default_account_id.id,
            self.date_from,
            self.env.company.id
        ))
        result = self.env.cr.fetchone()
        return result[0] if result else 0

    def _get_movements(self):
        """Obtiene los movimientos del período"""
        query = """
            SELECT
                aml.date,
                am.name as move_name,
                aml.name as description,
                rp.name as partner_name,
                CASE WHEN aml.debit > 0 THEN aml.debit ELSE 0 END as inbound,
                CASE WHEN aml.credit > 0 THEN aml.credit ELSE 0 END as outbound,
                aml.balance
            FROM account_move_line aml
            JOIN account_move am ON aml.move_id = am.id
            LEFT JOIN res_partner rp ON aml.partner_id = rp.id
            WHERE aml.account_id = %s
                AND aml.date >= %s
                AND aml.date <= %s
                AND am.state = 'posted'
                AND aml.company_id = %s
            ORDER BY aml.date, am.name
        """
        self.env.cr.execute(query, (
            self.journal_id.default_account_id.id,
            self.date_from,
            self.date_to,
            self.env.company.id
        ))
        return self.env.cr.dictfetchall()

    def _get_summary(self):
        """Resumen de ingresos y egresos del período"""
        query = """
            SELECT
                COALESCE(SUM(aml.debit), 0) as total_inbound,
                COALESCE(SUM(aml.credit), 0) as total_outbound,
                COALESCE(SUM(aml.balance), 0) as net_movement
            FROM account_move_line aml
            JOIN account_move am ON aml.move_id = am.id
            WHERE aml.account_id = %s
                AND aml.date >= %s
                AND aml.date <= %s
                AND am.state = 'posted'
                AND aml.company_id = %s
        """
        self.env.cr.execute(query, (
            self.journal_id.default_account_id.id,
            self.date_from,
            self.date_to,
            self.env.company.id
        ))
        return self.env.cr.dictfetchone()

    def _get_report_data(self):
        """Obtiene los datos para el reporte de arqueo"""
        opening_balance = self._get_opening_balance()
        movements = self._get_movements() if self.include_details else []
        summary = self._get_summary()

        closing_balance = opening_balance + (summary['net_movement'] if summary else 0)

        return {
            'wizard': self,
            'journal': self.journal_id,
            'opening_balance': opening_balance,
            'movements': movements,
            'total_inbound': summary['total_inbound'] if summary else 0,
            'total_outbound': summary['total_outbound'] if summary else 0,
            'net_movement': summary['net_movement'] if summary else 0,
            'closing_balance': closing_balance,
            'company': self.env.company,
            'print_date': fields.Datetime.now(),
        }

    def action_print_report(self):
        """Genera el reporte PDF de arqueo de caja"""
        self.ensure_one()
        data = self._get_report_data()
        return self.env.ref('custom_account_treasury.action_report_cash_box').report_action(self, data=data)

    def action_view_movements(self):
        """Abre la vista de movimientos contables filtrada"""
        self.ensure_one()
        return {
            'name': _('Movimientos de Caja'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move.line',
            'view_mode': 'list,form',
            'domain': [
                ('account_id', '=', self.journal_id.default_account_id.id),
                ('date', '>=', self.date_from),
                ('date', '<=', self.date_to),
                ('parent_state', '=', 'posted'),
            ],
            'context': {'search_default_group_by_date': 1},
        }
