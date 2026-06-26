
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)


class AccountJournal(models.Model):
    """Extensión de diarios para gestión de tesorería"""
    _inherit = 'account.journal'
    

    
    is_treasury_journal = fields.Boolean(
        string='Diario de Tesorería',
        default=False,
        help='Marca este diario para operaciones de tesorería y anticipos'
    )
    
    allow_advances = fields.Boolean(
        string='Permitir Anticipos',
        default=True,
        help='Permite registrar anticipos en este diario'
    )
    
    # Tipos de anticipo permitidos
    advance_type_ids = fields.Many2many(
        'advance.type',
        'journal_advance_type_rel',
        'journal_id',
        'type_id',
        string='Tipos de Anticipo',
        help='Tipos de anticipo permitidos en este diario'
    )
    
    default_advance_type_id = fields.Many2one(
        'advance.type',
        string='Tipo de Anticipo por Defecto',
        help='Tipo de anticipo predeterminado para pagos en este diario'
    )
    

    # Saldos de anticipos
    total_advance_balance = fields.Monetary(
        string='Saldo de Anticipos',
        currency_field='currency_id',
        compute='_compute_treasury_metrics'
    )
    
    customer_advance_balance = fields.Monetary(
        string='Anticipos de Clientes',
        currency_field='currency_id',
        compute='_compute_treasury_metrics'
    )
    
    supplier_advance_balance = fields.Monetary(
        string='Anticipos a Proveedores',
        currency_field='currency_id',
        compute='_compute_treasury_metrics'
    )
    
    employee_advance_balance = fields.Monetary(
        string='Anticipos a Empleados',
        currency_field='currency_id',
        compute='_compute_treasury_metrics'
    )
    
    # Conteos
    pending_advance_count = fields.Integer(
        string='Anticipos Pendientes',
        compute='_compute_treasury_metrics'
    )

    unreconciled_advance_count = fields.Integer(
        string='Anticipos sin Conciliar',
        compute='_compute_treasury_metrics',
        help='Número de anticipos sin conciliar'
    )

    pending_payment_count = fields.Integer(
        string='Pagos por Validar',
        compute='_compute_treasury_metrics'
    )

    pending_payment_amount = fields.Monetary(
        string='Monto por Validar',
        currency_field='currency_id',
        compute='_compute_treasury_metrics',
        help='Monto total de pagos pendientes de validación'
    )
    
    # Saldos bancarios
    bank_balance = fields.Monetary(
        string='Saldo Bancario',
        currency_field='currency_id',
        compute='_compute_bank_balance'
    )
    
    available_balance = fields.Monetary(
        string='Saldo Disponible',
        currency_field='currency_id',
        compute='_compute_bank_balance',
        help='Saldo bancario menos anticipos pendientes'
    )
    
    projected_balance = fields.Monetary(
        string='Saldo Proyectado',
        currency_field='currency_id',
        compute='_compute_projected_balance',
        help='Saldo proyectado considerando pagos pendientes'
    )
    

    
    use_treasury_numbering = fields.Boolean(
        string='Usar Numeración de Tesorería',
        default=False,
        help='Usa secuencias especiales de tesorería para pagos'
    )
    
    treasury_sequence_id = fields.Many2one(
        'ir.sequence',
        string='Secuencia de Tesorería',
        help='Secuencia para numeración de tesorería'
    )
    
    # Secuencias por tipo de operación
    customer_payment_sequence_id = fields.Many2one(
        'ir.sequence',
        string='Secuencia Cobros',
        help='Secuencia para cobros de clientes'
    )
    
    supplier_payment_sequence_id = fields.Many2one(
        'ir.sequence',
        string='Secuencia Pagos',
        help='Secuencia para pagos a proveedores'
    )
    

    
    def _compute_treasury_metrics(self):
        """Calcula métricas de tesorería para el dashboard usando SQL para mejor performance"""
        for journal in self:
            if journal.type != 'bank':
                journal.total_advance_balance = 0
                journal.customer_advance_balance = 0
                journal.supplier_advance_balance = 0
                journal.employee_advance_balance = 0
                journal.pending_advance_count = 0
                journal.pending_payment_count = 0
                journal.pending_payment_amount = 0
                journal.unreconciled_advance_count = 0
                continue

            # Usar consulta SQL para anticipos sin conciliar (mejor performance)
            self.env.cr.execute("""
                SELECT
                    payment_type,
                    partner_type,
                    COUNT(*) as count,
                    COALESCE(SUM(amount), 0) as total_amount
                FROM account_payment
                WHERE journal_id = %s
                    AND advance = true
                    AND state = 'posted'
                    AND is_reconciled = false
                GROUP BY payment_type, partner_type
            """, (journal.id,))

            advances_data = self.env.cr.dictfetchall()

            customer_balance = 0
            supplier_balance = 0
            employee_balance = 0
            total_count = 0

            for data in advances_data:
                total_count += data['count']
                if data['payment_type'] == 'inbound':
                    customer_balance += data['total_amount']
                elif data['payment_type'] == 'outbound':
                    if data['partner_type'] == 'supplier':
                        supplier_balance += data['total_amount']
                    elif data['partner_type'] == 'employee':
                        employee_balance += data['total_amount']

            journal.customer_advance_balance = customer_balance
            journal.supplier_advance_balance = supplier_balance
            journal.employee_advance_balance = employee_balance
            journal.total_advance_balance = customer_balance - supplier_balance - employee_balance
            journal.pending_advance_count = total_count

            # Conteo de anticipos sin conciliar para kanban
            journal.unreconciled_advance_count = total_count

            # Pagos pendientes de validación
            self.env.cr.execute("""
                SELECT
                    COUNT(*) as count,
                    COALESCE(SUM(amount), 0) as total_amount
                FROM account_payment
                WHERE journal_id = %s AND state = 'draft'
            """, (journal.id,))

            pending_data = self.env.cr.dictfetchone()
            journal.pending_payment_count = pending_data['count'] or 0
            journal.pending_payment_amount = pending_data['total_amount'] or 0
    
    def _compute_bank_balance(self):
        """Calcula saldo bancario actual"""
        for journal in self:
            if journal.type != 'bank' or not journal.default_account_id:
                journal.bank_balance = 0
                journal.available_balance = 0
                continue
            
            domain = [
                ('account_id', '=', journal.default_account_id.id),
                ('parent_state', '=', 'posted')
            ]
            
            move_lines = self.env['account.move.line'].search(domain)
            journal.bank_balance = sum(move_lines.mapped('balance'))
            
            journal.available_balance = journal.bank_balance - abs(journal.total_advance_balance)
    
    def _compute_projected_balance(self):
        """Calcula saldo proyectado"""
        for journal in self:
            if journal.type != 'bank':
                journal.projected_balance = 0
                continue
            
            projected = journal.bank_balance
            
            pending_inbound = self.env['account.payment'].search([
                ('journal_id', '=', journal.id),
                ('payment_type', '=', 'inbound'),
                ('state', '=', 'draft')
            ])
            projected += sum(pending_inbound.mapped('amount'))
            
            pending_outbound = self.env['account.payment'].search([
                ('journal_id', '=', journal.id),
                ('payment_type', '=', 'outbound'),
                ('state', '=', 'draft')
            ])
            projected -= sum(pending_outbound.mapped('amount'))
            
            journal.projected_balance = projected
    

    
    def action_view_treasury_dashboard(self):
        """Abre el dashboard de tesorería"""
        self.ensure_one()
        
        return {
            'name': _('Dashboard de Tesorería - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'account.journal',
            'view_mode': 'kanban',
            'view_id': self.env.ref('custom_account_treasury.view_journal_treasury_dashboard').id,
            'domain': [('id', '=', self.id)],
            'context': {
                'search_default_treasury': True,
                'default_type': 'bank'
            }
        }
    
    def action_view_advances(self):
        """Ver anticipos del diario"""
        self.ensure_one()

        return {
            'name': _('Anticipos - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'view_mode': 'list,form',
            'domain': [
                ('journal_id', '=', self.id),
                ('advance', '=', True),
                ('is_reconciled', '=', False)
            ],
            'context': {
                'default_journal_id': self.id,
                'search_default_group_by_payment_type': 1
            }
        }

    def action_view_unreconciled_advances(self):
        """Ver anticipos sin conciliar del diario"""
        self.ensure_one()

        return {
            'name': _('Anticipos sin Conciliar - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'view_mode': 'list,kanban,form',
            'domain': [
                ('journal_id', '=', self.id),
                ('advance', '=', True),
                ('state', '=', 'posted'),
                ('is_reconciled', '=', False)
            ],
            'context': {
                'default_journal_id': self.id,
                'search_default_group_by_partner_type': 1,
                'group_by': ['partner_type', 'payment_type']
            }
        }
    
    def action_view_pending_payments(self):
        """Ver pagos pendientes de validación"""
        self.ensure_one()
        
        return {
            'name': _('Pagos Pendientes - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'view_mode': 'list,form',
            'domain': [
                ('journal_id', '=', self.id),
                ('state', '=', 'draft')
            ],
            'context': {
                'default_journal_id': self.id
            }
        }
    
    def get_advance_type_for_payment(self, payment_type='inbound', partner=None):
        """
        Obtiene el tipo de anticipo apropiado para un pago
        
        :param payment_type: 'inbound' o 'outbound'
        :param partner: res.partner (opcional)
        :return: advance.type record
        """
        self.ensure_one()
        
        if self.default_advance_type_id:
            return self.default_advance_type_id
        
        if len(self.advance_type_ids) == 1:
            return self.advance_type_ids[0]
        
        if self.advance_type_ids and partner:
            if partner.customer_rank > partner.supplier_rank:
                customer_types = self.advance_type_ids.filtered(
                    lambda t: t.advance_type == 'customer'
                )
                if customer_types:
                    return customer_types[0]
            elif partner.supplier_rank > 0:
                supplier_types = self.advance_type_ids.filtered(
                    lambda t: t.advance_type == 'supplier'
                )
                if supplier_types:
                    return supplier_types[0]
        
        return self.env['advance.type'].get_advance_type_for_partner(
            partner or self.env['res.partner'],
            payment_type
        )
    
    def get_next_treasury_number(self, payment_type='inbound', partner_type='customer'):
        """
        Genera el siguiente número de tesorería
        
        :param payment_type: 'inbound' o 'outbound'
        :param partner_type: 'customer', 'supplier', 'employee'
        :return: String con el número
        """
        self.ensure_one()
        
        if not self.use_treasury_numbering:
            return False
        
        if self.treasury_sequence_id:
            sequence = self.treasury_sequence_id
        elif payment_type == 'inbound' and self.customer_payment_sequence_id:
            sequence = self.customer_payment_sequence_id
        elif payment_type == 'outbound' and self.supplier_payment_sequence_id:
            sequence = self.supplier_payment_sequence_id
        else:
            sequence = self._create_treasury_sequence(payment_type, partner_type)
        
        return sequence.next_by_id()
    
    def _create_treasury_sequence(self, payment_type, partner_type):
        """
        Crea una secuencia de tesorería
        
        :param payment_type: 'inbound' o 'outbound'
        :param partner_type: 'customer', 'supplier', 'employee'
        :return: ir.sequence record
        """
        prefix_map = {
            ('inbound', 'customer'): 'COB/',
            ('outbound', 'supplier'): 'PAG/',
            ('outbound', 'employee'): 'ANT-EMP/',
            ('inbound', 'supplier'): 'DEV-PROV/',
            ('outbound', 'customer'): 'DEV-CLI/',
        }
        
        prefix = prefix_map.get((payment_type, partner_type), 'TES/')
        
        sequence = self.env['ir.sequence'].create({
            'name': f'Tesorería {self.name} - {payment_type}',
            'code': f'treasury.{self.id}.{payment_type}',
            'prefix': prefix + '%(year)s/',
            'padding': 6,
            'company_id': self.company_id.id
        })
        
        # Asignar según tipo
        if payment_type == 'inbound':
            self.customer_payment_sequence_id = sequence
        else:
            self.supplier_payment_sequence_id = sequence
        
        return sequence

    def open_action_with_context(self):
        """Override para incluir información de anticipos en dashboard"""
        action = super().open_action_with_context() if hasattr(super(), 'open_action_with_context') else {}

        # Agregar información adicional al contexto
        if self.type == 'bank':
            if 'context' not in action:
                action['context'] = {}

            action['context'].update({
                'bank_balance': self.bank_balance,
                'total_advance_balance': self.total_advance_balance,
                'pending_payment_count': self.pending_payment_count,
                'pending_payment_amount': self.pending_payment_amount,
                'customer_advance_balance': self.customer_advance_balance,
                'supplier_advance_balance': self.supplier_advance_balance,
                'projected_balance': self.projected_balance
            })

        return action
