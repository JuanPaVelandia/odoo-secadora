from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.misc import formatLang
class HrLoanCategory(models.Model):
    _name = 'hr.loan.category'
    _description = 'Loan Category'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True)
    description = fields.Text()
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    salary_rule_id = fields.Many2one('hr.salary.rule', required=True)
    journal_id = fields.Many2one(
        'account.journal',
        string='Diario de Cruce',
        help='Diario contable por defecto para registrar operaciones de préstamos de esta categoría',
        domain="[('type', 'in', ['bank', 'cash'])]"
    )

    _code_uniq = models.Constraint('unique(code,company_id)', 'Category code must be unique per company!')


class HrLoan(models.Model):
    _name = 'hr.loan'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Employee Loan Management"
    _order = "name desc"

    name = fields.Char(
        string="Número",
        default="/",
        readonly=True,
        copy=False
    )
    date = fields.Date(
        string="Fecha",
        default=fields.Date.today,
        required=True,
        tracking=True
    )
    date_account = fields.Date(
        string="Fecha Contable",
        default=fields.Date.today,
        tracking=True
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string="Empleado",
        required=True,
        tracking=True
    )
    department_id = fields.Many2one(
        'hr.department',
        string="Departamento",
        related="employee_id.department_id",
        store=True
    )
    contract_id = fields.Many2one(
        'hr.contract',
        string="Contrato",
        required=True,
        domain="[('employee_id','=',employee_id),('state','in',['open','finished'])]",
        tracking=True
    )
    installment_ids = fields.One2many(
        'hr.loan.installment',
        'loan_id',
        string='Cuotas del Préstamo'
    )
    company_id = fields.Many2one(
        related='contract_id.company_id',
        string="Compañía"
    )
    currency_id = fields.Many2one(
        'res.currency',
        string="Moneda",
        default=lambda self: self.env.company.currency_id
    )
    category_id = fields.Many2one(
        'hr.loan.category',
        string="Categoría",
        required=True
    )
    
    loan_type = fields.Selection([
        ('advance', 'Anticipo'),
        ('loan', 'Préstamo'),
        ('advance_prima', 'Anticipo de Prima'),
        ('advance_cesantias', 'Anticipo de Cesantías')
    ], string="Tipo de Préstamo", required=True, default='loan')

    # Campos para descuento en estructuras específicas
    deduct_in_structure = fields.Boolean(
        string="Descontar en Estructura Específica",
        help="Si está marcado, se descontará automáticamente en la estructura de prima/cesantías/liquidación"
    )
    structure_type = fields.Selection([
        ('prima', 'Prima de Servicios'),
        ('cesantias', 'Cesantías'),
        ('liquidacion', 'Liquidación de Contrato')
    ], string="Tipo de Estructura",
       help="Estructura donde se descontará automáticamente")
    
    calculation_type = fields.Selection([
        ('period', 'Número de Períodos'),
        ('custom', 'Cuotas Personalizadas')
    ], string="Tipo de Cálculo", required=True, default='period')
    
    num_periods = fields.Integer(
        string="Número de Períodos",
        default=1
    )
    num_custom_installments = fields.Integer(
        string="Número de Cuotas Personalizadas"
    )
    
    payment_start_date = fields.Date(
        string="Fecha Primera Cuota",
        required=True
    )
    payment_end_date = fields.Date(
        string="Fecha Última Cuota",
        readonly=True
    )
    
    apply_on = fields.Selection([
        ('15', 'Primera Quincena'),
        ('30', 'Segunda Quincena'),
        ('both', 'Ambas')
    ], string="Aplicar en", required=True, default='15')
    
    original_amount = fields.Monetary(
        string="Monto Original",
        required=True
    )
    loan_amount = fields.Monetary(
        string="Monto del Préstamo",
        required=True
    )
    total_amount = fields.Monetary(
        string="Monto Total",
        compute='_compute_amounts',
        store=True
    )
    total_paid = fields.Monetary(
        string="Total Pagado",
        compute='_compute_amounts',
        store=True
    )
    remaining_amount = fields.Monetary(
        string="Monto Restante",
        compute='_compute_amounts',
        store=True
    )
    pending_amount = fields.Monetary(
        string="Monto Pendiente",
        compute='_compute_pending',
        store=True
    )
    pending_installments = fields.Integer(
        string="Cuotas Pendientes",
        compute='_compute_pending',
        store=True
    )
    
    description = fields.Text(string="Descripción")
    entity_id = fields.Many2one(
        'res.partner',
        string="Entidad Financiera"
    )
    deduct_on_settlement = fields.Boolean(
        string="Deducir Saldo en Finiquito",
        help="Si está marcado, el saldo restante será deducido del finiquito"
    )

    # Campos de intereses
    apply_interest = fields.Boolean(
        string="Aplicar Intereses",
        help="Si está marcado, se calcularán intereses sobre el préstamo"
    )
    interest_rate = fields.Float(
        string="Tasa de Interés (%)",
        help="Tasa de interés mensual aplicada al saldo pendiente"
    )
    interest_type = fields.Selection([
        ('simple', 'Interés Simple'),
        ('compound', 'Interés Compuesto')
    ], string="Tipo de Interés", default='simple')

    total_interest = fields.Monetary(
        string="Total Intereses",
        compute='_compute_interest_amounts',
        store=True
    )
    interest_generated = fields.Monetary(
        string="Intereses Generados",
        compute='_compute_interest_amounts',
        store=True
    )
    interest_charged = fields.Monetary(
        string="Intereses Cobrados",
        compute='_compute_interest_amounts',
        store=True
    )
    pending_interest = fields.Monetary(
        string="Intereses Pendientes",
        compute='_compute_interest_amounts',
        store=True
    )

    interest_rule_id = fields.Many2one(
        'hr.salary.rule',
        string="Regla de Intereses",
        help="Regla salarial utilizada para cobrar los intereses en nómina"
    )

    # Cuota manual de abono
    manual_payment_ids = fields.One2many(
        'hr.loan.manual.payment',
        'loan_id',
        string="Abonos Manuales"
    )
    total_manual_payments = fields.Monetary(
        string="Total Abonos Manuales",
        compute='_compute_manual_payments',
        store=True
    )
    
    journal_id = fields.Many2one(
        'account.journal',
        string="Diario Contable",
        domain=[('type', 'in', ['bank', 'cash'])]
    )
    move_id = fields.Many2one(
        'account.move',
        string="Asiento Contable",
        readonly=True,
        copy=False
    )
    payment_id = fields.Many2one(
        'account.payment',
        string="Pago",
        readonly=True,
        copy=False
    )
    refund_move_id = fields.Many2one(
        'account.move',
        string='Asiento de Reembolso',
        readonly=True
    )
    refund_payment_id = fields.Many2one(
        'account.payment',
        string='Pago de Reembolso',
        readonly=True
    )
    
    move_count = fields.Integer(
        string="Número de Asientos",
        compute='_compute_move_count'
    )
    
    payment_state = fields.Selection([
        ('not_paid', 'No Pagado'),
        ('in_payment', 'En Proceso de Pago'),
        ('paid', 'Pagado')
    ], string="Estado de Pago", default='not_paid', tracking=True)
    
    active = fields.Boolean(default=True)
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('waiting_approval', 'Esperando Aprobación'),
        ('approved', 'Aprobado'),
        ('paid', 'Pagado'),
        ('refused', 'Rechazado'),
        ('cancelled', 'Cancelado'),
    ], string="Estado", default='draft', tracking=True)
    # Relación inversa con solicitud de préstamo
    loan_request_id = fields.Many2one(
        'hr.loan.request',
        string='Solicitud de Préstamo',
        readonly=True,
        tracking=True,
        help='Solicitud de préstamo del portal que originó este préstamo'
    )

    def action_view_loan_request(self):
        """Ver solicitud de préstamo relacionada"""
        self.ensure_one()

        if not self.loan_request_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': _('No hay una solicitud de préstamo asociada'),
                    'type': 'warning',
                    'sticky': False,
                }
            }

        return {
            'type': 'ir.actions.act_window',
            'name': _('Solicitud de Préstamo'),
            'res_model': 'hr.loan.request',
            'res_id': self.loan_request_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.depends('installment_ids.amount', 'installment_ids.paid', 'loan_amount')
    def _compute_amounts(self):
        for loan in self:
            paid_installments = loan.installment_ids.filtered('paid')
            loan.total_amount = loan.loan_amount
            loan.total_paid = sum(paid_installments.mapped('amount'))
            loan.remaining_amount = loan.loan_amount - loan.total_paid

    @api.depends('installment_ids.paid', 'installment_ids.amount')
    def _compute_pending(self):
        for loan in self:
            pending = loan.installment_ids.filtered(lambda x: not x.paid)
            loan.pending_amount = sum(pending.mapped('amount'))
            loan.pending_installments = len(pending)

    @api.depends('installment_ids.interest_amount', 'installment_ids.paid')
    def _compute_interest_amounts(self):
        """Calcula montos de intereses"""
        for loan in self:
            if not loan.apply_interest:
                loan.total_interest = 0
                loan.interest_generated = 0
                loan.interest_charged = 0
                loan.pending_interest = 0
                continue

            # Total de intereses generados
            loan.interest_generated = sum(loan.installment_ids.mapped('interest_amount'))

            # Intereses cobrados (de cuotas pagadas)
            paid_installments = loan.installment_ids.filtered('paid')
            loan.interest_charged = sum(paid_installments.mapped('interest_amount'))

            # Intereses pendientes
            loan.pending_interest = loan.interest_generated - loan.interest_charged
            loan.total_interest = loan.interest_generated

    @api.depends('manual_payment_ids.amount', 'manual_payment_ids.state')
    def _compute_manual_payments(self):
        """Calcula total de abonos manuales"""
        for loan in self:
            confirmed_payments = loan.manual_payment_ids.filtered(lambda x: x.state == 'done')
            loan.total_manual_payments = sum(confirmed_payments.mapped('amount'))

    def _compute_move_count(self):
        for loan in self:
            loan.move_count = len(loan.mapped('installment_ids.move_id')) + \
                bool(loan.move_id) + bool(loan.refund_move_id)
                
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                loan_type = vals.get('loan_type', 'loan')
                sequence_code = 'payroll.advance.number' if loan_type == 'advance' else 'hr.loans.seq'
                vals['name'] = self.env['ir.sequence'].next_by_code(sequence_code)
        return super().create(vals_list)
    
    @api.constrains('loan_amount', 'original_amount', 'num_periods')
    def _check_amounts(self):
        for loan in self:
            if loan.loan_amount <= 0:
                raise ValidationError(_("Loan amounts must be positive"))
            
    def _get_credit_account(self):
        """
        Obtiene la cuenta de crédito basada en el departamento del empleado.
        Si no se encuentra una regla específica, muestra una advertencia.
        
        Returns:
            account.account: Cuenta contable de crédito
            False: Si no se encuentra una cuenta válida
        """
        self.ensure_one()
        
        # Buscar regla contable específica para el departamento
        rule = self.category_id.salary_rule_id.salary_rule_accounting.filtered(
            lambda r: r.department.id == self.department_id.id
        )
        
        # Si no hay regla específica para el departamento, buscar regla general
        if not rule:
            rule = self.category_id.salary_rule_id.salary_rule_accounting.filtered(
                lambda r: not r.department
            )
        
        if rule:
            return rule[0].credit_account
        else:
            # Mostrar advertencia al usuario
            warning_msg = _(
                'No se encontró una regla contable para el departamento %(dept)s en la categoría %(cat)s. '
                'Por favor, configure las reglas contables.'
            ) % {
                'dept': self.department_id.name or _('Sin Departamento'),
                'cat': self.category_id.name
            }
            
            # Lanzar advertencia al usuario
            raise UserError(warning_msg)
            
        return False
    def _prepare_move_vals(self):
        debit_account = self._get_credit_account()
        credit_account = self.employee_id.work_contact_id.property_account_payable_id
        
        if not all([debit_account, credit_account]):
            raise UserError(_("Please configure accounts properly"))

        return {
            'journal_id': self.journal_id.id,
            'date': self.date,
            'ref': f'{self.name}/INICIAL',
            'line_ids': [
                (0, 0, {
                    'name': 'Reconocimiento incial del préstamo (CAUSA PRESTAMO) ',
                    'partner_id': self.employee_id.work_contact_id.id,
                    'account_id': debit_account.id,
                    'debit': self.loan_amount,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': 'Reconocimiento incial del préstamo (CREDITO)',
                    'partner_id': self.employee_id.work_contact_id.id,
                    'account_id': credit_account.id,
                    'debit': 0.0,
                    'credit': self.loan_amount,
                })
            ]
        }

    def _prepare_refund_move_vals(self):
        debit_account = self.employee_id.work_contact_id.property_account_receivable_id
        credit_account = self._get_credit_account()

        return {
            'journal_id': self.journal_id.id,
            'date': fields.Date.context_today(self),
            'ref': f'{self.name}/REFUND',
            'line_ids': [
                (0, 0, {
                    'name': 'Rechazo de Préstamo (DEBITO)',
                    'partner_id': self.employee_id.work_contact_id.id,
                    'account_id': debit_account.id,
                    'debit': self.remaining_amount,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': 'Rechazo de Préstamo (CREDITO)',
                    'partner_id': self.employee_id.work_contact_id.id,
                    'account_id': credit_account.id,
                    'debit': 0.0,
                    'credit': self.remaining_amount,
                })
            ]
        }

    def _calculate_installment_interest(self, installment_amount, pending_balance):
        """
        Calcula el interés para una cuota específica
        Args:
            installment_amount: Monto de capital de la cuota
            pending_balance: Saldo pendiente antes de esta cuota
        Returns:
            Monto de interés para esta cuota
        """
        self.ensure_one()
        if not self.apply_interest or not self.interest_rate:
            return 0.0

        # Interés = Saldo * Tasa / 100
        if self.interest_type == 'simple':
            # Interés simple sobre el saldo pendiente
            interest = (pending_balance * self.interest_rate) / 100
        else:  # compound
            # Para interés compuesto, se calcula sobre el saldo más intereses acumulados
            interest = ((pending_balance + self.total_interest) * self.interest_rate) / 100

        return round(interest, 2)

    def action_generate_installments(self):
        self.ensure_one()
        # Eliminar cuotas no pagadas existentes
        self.installment_ids.filtered(lambda x: not x.paid).unlink()
        
        amount = self.remaining_amount
        installment_vals = []
        sequence = len(self.installment_ids) + 1
        
        # Caso especial para anticipos
        if self.loan_type == 'advance':
            start_date = fields.Date.from_string(self.payment_start_date)
            # Si la fecha es después del 15, la cuota será el último día del mes actual
            if start_date.day > 15:
                month_end = 28 if start_date.month == 2 else 30
                installment_vals.append({
                    'loan_id': self.id,
                    'date': start_date.replace(day=month_end),
                    'amount': amount,
                    'sequence': sequence
                })
            else:
                installment_vals.append({
                    'loan_id': self.id,
                    'date': start_date.replace(day=15),
                    'amount': amount,
                    'sequence': sequence
                })
            self.payment_start_date = installment_vals[0]['date']
            self.payment_end_date = installment_vals[0]['date']
            
        else:  # loan_type == 'loan'
            start_date = fields.Date.from_string(self.payment_start_date)
            
            if self.calculation_type == 'period':
                num_months = self.num_periods
                installments_per_month = 2 if self.apply_on == 'both' else 1
                total_installments = num_months * installments_per_month
                installment_amount = amount / total_installments
                
                # Manejo especial para la primera cuota si está después del 15
                first_month_installments = 0
                if start_date.day > 15:
                    month_end = 28 if start_date.month == 2 else 30
                    installment_vals.append({
                        'loan_id': self.id,
                        'date': start_date.replace(day=month_end),
                        'amount': installment_amount,
                        'sequence': sequence
                    })
                    sequence += 1
                    first_month_installments = 1
                    start_date += relativedelta(months=1)
                
                remaining_installments = total_installments - first_month_installments
                
                for i in range(remaining_installments):
                    if self.apply_on == 'both':
                        # Primera quincena
                        installment_vals.append({
                            'loan_id': self.id,
                            'date': start_date.replace(day=15),
                            'amount': installment_amount,
                            'sequence': sequence
                        })
                        sequence += 1
                        
                        # Segunda quincena
                        month_end = 28 if start_date.month == 2 else 30
                        installment_vals.append({
                            'loan_id': self.id,
                            'date': start_date.replace(day=month_end),
                            'amount': installment_amount,
                            'sequence': sequence
                        })
                        sequence += 1
                        start_date += relativedelta(months=1)
                        
                    elif self.apply_on == '15':
                        installment_vals.append({
                            'loan_id': self.id,
                            'date': start_date.replace(day=15),
                            'amount': installment_amount,
                            'sequence': sequence
                        })
                        sequence += 1
                        start_date += relativedelta(months=1)
                        
                    else:  # self.apply_on == '30'
                        day = 28 if start_date.month == 2 else 30
                        installment_vals.append({
                            'loan_id': self.id,
                            'date': start_date.replace(day=day),
                            'amount': installment_amount,
                            'sequence': sequence
                        })
                        sequence += 1
                        start_date += relativedelta(months=1)
                        
            else:  # calculation_type == 'custom'
                total_installments = self.num_custom_installments
                installment_amount = amount / total_installments
                installments_created = 0
                current_date = start_date
                
                # Manejo especial para la primera cuota si está después del 15
                if current_date.day > 15:
                    month_end = 28 if current_date.month == 2 else 30
                    installment_vals.append({
                        'loan_id': self.id,
                        'date': current_date.replace(day=month_end),
                        'amount': installment_amount,
                        'sequence': sequence
                    })
                    sequence += 1
                    installments_created += 1
                    current_date += relativedelta(months=1)
                
                while installments_created < total_installments:
                    if self.apply_on == 'both':
                        if installments_created < total_installments:
                            installment_vals.append({
                                'loan_id': self.id,
                                'date': current_date.replace(day=15),
                                'amount': installment_amount,
                                'sequence': sequence
                            })
                            sequence += 1
                            installments_created += 1
                        
                        if installments_created < total_installments:
                            month_end = 28 if current_date.month == 2 else 30
                            installment_vals.append({
                                'loan_id': self.id,
                                'date': current_date.replace(day=month_end),
                                'amount': installment_amount,
                                'sequence': sequence
                            })
                            sequence += 1
                            installments_created += 1
                            
                    else:
                        day = 15 if self.apply_on == '15' else (28 if current_date.month == 2 else 30)
                        installment_vals.append({
                            'loan_id': self.id,
                            'date': current_date.replace(day=day),
                            'amount': installment_amount,
                            'sequence': sequence
                        })
                        sequence += 1
                        installments_created += 1
                        
                    current_date += relativedelta(months=1)
        
        # Calcular intereses para cada cuota si aplica
        if self.apply_interest and installment_vals:
            pending_balance = self.remaining_amount
            for inst_val in installment_vals:
                interest = self._calculate_installment_interest(inst_val['amount'], pending_balance)
                inst_val['interest_amount'] = interest
                pending_balance -= inst_val['amount']

        # Crear todas las cuotas en un solo create
        if installment_vals:
            self.env['hr.loan.installment'].create(installment_vals)
            self.payment_end_date = installment_vals[-1]['date']

    def action_submit(self):
        """Enviar a aprobación con validaciones estrictas"""
        # Validar que montos NO estén vacíos al confirmar
        if not self.loan_amount or self.loan_amount <= 0:
            raise UserError(_("El monto del préstamo debe ser mayor a cero antes de enviar a aprobación"))

        if not self.original_amount or self.original_amount <= 0:
            raise UserError(_("El monto original debe ser mayor a cero antes de enviar a aprobación"))

        self.write({'state': 'waiting_approval'})

    def action_approve(self):
        """Aprobar préstamo - monto puede quedar en cero"""
        # Validaciones mínimas - el monto puede estar en cero
        if not self.installment_ids:
            raise UserError(_("Por favor genere las cuotas primero"))

        if not self.employee_id:
            raise UserError(_("Debe seleccionar un empleado"))

        if not self.contract_id:
            raise UserError(_("Debe seleccionar un contrato"))

        move_vals = self._prepare_move_vals()
        move = self.env['account.move'].create(move_vals)
        move.action_post()

        self.write({
            'move_id': move.id,
            'state': 'approved'
        })

    def action_refuse(self):
        if self.move_id:
            refund_move = self.move_id._reverse_moves()
            self.write({
                'refund_move_id': refund_move.id,
            })
        self.write({'state': 'refused'})

    def action_cancel(self):
        if self.installment_ids.filtered('paid'):
            raise UserError(_("Cannot cancel a loan with paid installments"))
        self.write({'state': 'cancelled'})

    def action_register_payment(self):
        return {
            'name': _('Register Payment'),
            'type': 'ir.actions.act_window',
            'res_model': 'wizard.loan.payment.register',
            'view_mode': 'form',
            'context': {'active_id': self.id},
            'target': 'new'
        }

    def action_refund(self):
        self.ensure_one()
        if not self.move_id:
            raise UserError(_("No accounting entry to refund"))
            
        refund_move = self.move_id._reverse_moves()
        self.write({
            'refund_move_id': refund_move.id,
            'state': 'cancelled'
        })
        return refund_move

    def action_modify_amount(self):
        return {
            'name': _('Modify Loan Amount'),
            'type': 'ir.actions.act_window',
            'res_model': 'wizard.loan.modify.amount',
            'view_mode': 'form',
            'target': 'new',
            'context': {'active_id': self.id}
        }

    def action_view_moves(self):
        self.ensure_one()
        moves = self.mapped('installment_ids.move_id') + \
            self.move_id + self.refund_move_id
        action = self.env['ir.actions.actions']._for_xml_id('account.action_move_line_form')
        if len(moves) > 1:
            action['domain'] = [('id', 'in', moves.ids)]
        elif moves:
            action['views'] = [(self.env.ref('account.view_move_form').id, 'form')]
            action['res_id'] = moves.id
        return action

    def action_view_interest_summary(self):
        """Ver resumen de intereses del préstamo"""
        self.ensure_one()
        return {
            'name': _('Resumen de Intereses'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.loan.installment',
            'view_mode': 'list,form',
            'domain': [('loan_id', '=', self.id), ('interest_amount', '>', 0)],
            'context': {
                'default_loan_id': self.id,
                'search_default_group_by_status': 1,
            }
        }

class HrLoanInstallment(models.Model):
    _name = 'hr.loan.installment'
    _description = 'Loan Installment'
    _order = 'date, id'

    loan_id = fields.Many2one('hr.loan', required=True, ondelete='cascade')
    currency_id = fields.Many2one(related='loan_id.currency_id')
    employee_id = fields.Many2one(related='loan_id.employee_id')
    company_id = fields.Many2one(related='loan_id.company_id')

    sequence = fields.Integer()
    date = fields.Date(required=True)
    amount = fields.Monetary(required=True, string="Monto Capital")

    # Campos de intereses
    interest_amount = fields.Monetary(
        string="Monto Intereses",
        help="Intereses calculados para esta cuota"
    )
    total_amount = fields.Monetary(
        string="Total Cuota (Capital + Intereses)",
        compute='_compute_total_amount',
        store=True
    )
    interest_charged = fields.Boolean(
        string="Intereses Cobrados",
        help="Indica si los intereses de esta cuota ya fueron cobrados"
    )
    interest_payslip_id = fields.Many2one(
        'hr.payslip',
        string="Nómina de Intereses",
        help="Nómina donde se cobraron los intereses"
    )

    paid = fields.Boolean(string="Pagado", compute='_compute_paid', store=True)
    skip = fields.Boolean("Cuota Saltada")
    skip_reason = fields.Text("Razón de Salto")

    payslip_id = fields.Many2one('hr.payslip', "Paid in Payslip")
    move_id = fields.Many2one('account.move', "Accounting Entry")
    refund_move_id = fields.Many2one('account.move', 'Refund Entry')

    # Campo para el estado de pago
    payment_state = fields.Selection([
        ('pending', 'Pendiente'),
        ('paid_payslip', 'Pagado por Nómina'),
        ('paid_accounting', 'Pagado por Contabilidad'),
        ('skipped', 'Omitido'),
        ('refunded', 'Reembolsado')
    ], string='Estado de Pago', compute='_compute_payment_state', store=True)

    display_name = fields.Char(
        string='Nombre',
        compute='_compute_display_name',
        store=True
    )

    @api.depends('amount', 'interest_amount')
    def _compute_total_amount(self):
        """Calcula el total de la cuota (capital + intereses)"""
        for installment in self:
            installment.total_amount = installment.amount + installment.interest_amount

    @api.depends('payment_state')
    def _compute_paid(self):
        """Computa si la cuota está pagada basado en su estado de pago"""
        for installment in self:
            installment.paid = installment.payment_state in ['paid_payslip', 'paid_accounting']

    @api.depends('skip', 'payslip_id', 'move_id', 'refund_move_id')
    def _compute_payment_state(self):
        for installment in self:
            if installment.skip:
                installment.payment_state = 'skipped'
            elif installment.refund_move_id:
                installment.payment_state = 'refunded'
            elif installment.payslip_id.state in ['done', 'paid']:
                installment.payment_state = 'paid_payslip'
            elif installment.move_id:
                installment.payment_state = 'paid_accounting'
            else:
                installment.payment_state = 'pending'

    @api.depends('sequence', 'loan_id.installment_ids', 'amount', 'payment_state')
    def _compute_display_name(self):
        for installment in self:
            total_installments = len(installment.loan_id.installment_ids)
            
            formatted_amount = formatLang(
                self.env,
                installment.amount,
                currency_obj=installment.currency_id
            )
            
            status_map = {
                'pending': 'Pendiente',
                'paid_payslip': 'Pagado por Nómina',
                'paid_accounting': 'Pagado por Contabilidad',
                'skipped': 'Omitido',
                'refunded': 'Reembolsado'
            }
            status = status_map.get(installment.payment_state, 'Pendiente')
            
            installment.display_name = f"Cuota {installment.sequence}/{total_installments} - {formatted_amount} ({status})"

    def _prepare_move_vals(self):
        self.ensure_one()
        debit_account = self.loan_id.journal_id.default_account_id
        credit_account = self.loan_id.category_id.salary_rule_id.account_credit

        return {
            'journal_id': self.loan_id.journal_id.id,
            'date': self.date,
            'partner_id': self.employee_id.work_contact_id.id,
            'ref': f'{self.loan_id.name}/INST/{self.sequence}',
            'line_ids': [
                (0, 0, {'name': f'Loan Installment {self.sequence}',
                    'partner_id': self.employee_id.work_contact_id.id,
                    'account_id': debit_account.id,
                    'debit': self.amount,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': f'Loan Installment {self.sequence}',
                    'partner_id': self.employee_id.work_contact_id.id,
                    'account_id': credit_account.id,
                    'debit': 0.0,
                    'credit': self.amount,
                })
            ]
        }

    def create_accounting_entry(self):
        self.ensure_one()
        if self.move_id:
            raise UserError(_("Accounting entry already exists"))

        move_vals = self._prepare_move_vals()
        move = self.env['account.move'].create(move_vals)
        move.action_post()
        
        self.write({
            'move_id': move.id,
            'paid': True
        })

    def action_refund_installment(self):
        self.ensure_one()
        if not self.move_id:
            raise UserError(_("No accounting entry to refund"))
            
        refund_move = self.move_id._reverse_moves()
        self.write({
            'refund_move_id': refund_move.id,
            'paid': False
        })
        
        # Recalculate loan status
        self.loan_id._compute_amounts()
        if self.loan_id.state == 'paid':
            self.loan_id.write({'state': 'approved'})

    def action_skip_installment(self):
        return {
            'name': _('Skip Installment'),
            'type': 'ir.actions.act_window',
            'res_model': 'wizard.loan.skip.installment',
            'view_mode': 'form',
            'context': {'active_id': self.id},
            'target': 'new'
        }

# models/hr_payslip.py
class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    loan_installment_ids = fields.One2many('hr.loan.installment', 'payslip_id', string='Prestamos')
    process_loans = fields.Boolean(string='Procesar Préstamos', default=True)
    double_installment = fields.Boolean(string='Procesar Doble Cuota', help='Permite procesar dos cuotas en este período')
    process_settlement_loans = fields.Boolean(
        string='Descontar Préstamos en Liquidación',
        help='Permite descontar los saldos de préstamos marcados para liquidación'
    )

    def _get_loan_lines(self, date_from, date_to, employee_id):
        """Obtiene las cuotas de préstamo para el período"""
        self.ensure_one()
        domain = [
            ('employee_id', '=', employee_id),
            ('loan_id.state', '=', 'approved'),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('paid', '=', False),
            ('skip', '=', False)
        ]

        # Si está marcado para procesar doble cuota, ampliar el dominio
        if self.double_installment:
            next_installment_domain = [
                ('employee_id', '=', employee_id),
                ('loan_id.state', '=', 'approved'),
                ('date', '>', date_to),
                ('paid', '=', False),
                ('skip', '=', False)
            ]
            current_installments = self.env['hr.loan.installment'].search(domain, order='date')
            if current_installments:
                next_installments = self.env['hr.loan.installment'].search(
                    next_installment_domain,
                    order='date',
                    limit=len(current_installments)
                )
                return current_installments + next_installments

        return self.env['hr.loan.installment'].search(domain)

    def _get_settlement_loans(self, employee_id):
        """Obtiene los préstamos para liquidación"""
        domain = [
            ('employee_id', '=', employee_id),
            ('state', '=', 'approved'),
            ('deduct_on_settlement', '=', True)
        ]
        loans = self.env['hr.loan'].search(domain)
        result = self.env['hr.loan.installment']

        for loan in loans:
            pending_installments = loan.installment_ids.filtered(
                lambda x: not x.paid and not x.skip
            )
            if pending_installments:
                result |= pending_installments

        return result

    def _get_advance_loans_for_structure(self, employee_id, structure_type):
        """
        Obtiene anticipos que deben descontarse en estructuras específicas
        Args:
            employee_id: ID del empleado
            structure_type: Tipo de estructura ('prima', 'cesantias', 'liquidacion')
        Returns:
            Cuotas pendientes de préstamos que deben descontarse en esta estructura
        """
        domain = [
            ('employee_id', '=', employee_id),
            ('loan_id.state', '=', 'approved'),
            ('loan_id.deduct_in_structure', '=', True),
            ('loan_id.structure_type', '=', structure_type),
            ('paid', '=', False),
            ('skip', '=', False)
        ]
        return self.env['hr.loan.installment'].search(domain)

    def _get_loan_interest_lines(self, date_from, date_to, employee_id):
        """
        Obtiene cuotas con intereses pendientes de cobro para el período
        Args:
            date_from: Fecha inicial del período
            date_to: Fecha final del período
            employee_id: ID del empleado
        Returns:
            Cuotas con intereses pendientes
        """
        domain = [
            ('employee_id', '=', employee_id),
            ('loan_id.state', '=', 'approved'),
            ('loan_id.apply_interest', '=', True),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('interest_charged', '=', False),
            ('skip', '=', False),
            ('interest_amount', '>', 0)
        ]
        return self.env['hr.loan.installment'].search(domain)

    def _mark_interest_as_charged(self, installments):
        """
        Marca los intereses de las cuotas como cobrados
        Args:
            installments: Cuotas cuyos intereses fueron cobrados
        """
        for installment in installments:
            installment.write({
                'interest_charged': True,
                'interest_payslip_id': self.id
            })

    def _process_loan_lines(self):
        """Procesa las cuotas de préstamo según el tipo de nómina"""
        self.ensure_one()

        self.loan_installment_ids = False

        if not self.process_loans:
            return

        loan_lines = self.env['hr.loan.installment']

        # Caso 1: Liquidación de contrato
        if self.struct_id.process == 'contrato' and self.process_settlement_loans:
            loan_lines = self._get_settlement_loans(self.employee_id.id)
            # Incluir también anticipos marcados para liquidación
            structure_loans = self._get_advance_loans_for_structure(self.employee_id.id, 'liquidacion')
            loan_lines |= structure_loans

        # Caso 2: Prima de servicios
        elif self.struct_id.process == 'prima':
            # Obtener SOLO anticipos de prima (prestamos marcados para descontar en prima)
            # NO incluir prestamos regulares - la Prima no debe descontar cuotas normales
            advance_loans = self._get_advance_loans_for_structure(self.employee_id.id, 'prima')
            loan_lines = advance_loans

        # Caso 3: Cesantias
        elif self.struct_id.process == 'cesantias':
            # Obtener SOLO anticipos de cesantias (prestamos marcados para descontar en cesantias)
            # NO incluir prestamos regulares - las Cesantias no deben descontar cuotas normales
            advance_loans = self._get_advance_loans_for_structure(self.employee_id.id, 'cesantias')
            loan_lines = advance_loans

        # Caso 4: Nómina regular
        else:
            loan_lines = self._get_loan_lines(self.date_from, self.date_to, self.employee_id.id)

        if loan_lines:
            self.loan_installment_ids = [(6, 0, loan_lines.ids)]

    def get_loan_interests(self):
        """
        Obtiene el total de intereses a cobrar en esta nómina
        Utilizado por la regla salarial de intereses
        Returns:
            Diccionario con información de intereses:
            - total: Total de intereses a cobrar
            - count: Número de cuotas con intereses
            - details: Lista de detalles por préstamo
        """
        self.ensure_one()

        interest_installments = self._get_loan_interest_lines(
            self.date_from,
            self.date_to,
            self.employee_id.id
        )

        if not interest_installments:
            return {'total': 0.0, 'count': 0, 'details': []}

        total_interest = sum(interest_installments.mapped('interest_amount'))

        # Agrupar por préstamo para el detalle
        details = []
        loans = interest_installments.mapped('loan_id')
        for loan in loans:
            loan_installments = interest_installments.filtered(lambda x: x.loan_id == loan)
            loan_interest = sum(loan_installments.mapped('interest_amount'))
            details.append({
                'loan_name': loan.name,
                'loan_id': loan.id,
                'interest': loan_interest,
                'count': len(loan_installments)
            })

        # Marcar intereses como cobrados
        self._mark_interest_as_charged(interest_installments)

        return {
            'total': total_interest,
            'count': len(interest_installments),
            'details': details
        }


# wizards/wizard_loan_payment_register.py
class WizardLoanPaymentRegister(models.TransientModel):
    _name = 'wizard.loan.payment.register'
    _description = 'Register Loan Payment'
    
    loan_id = fields.Many2one('hr.loan', required=True)
    amount = fields.Monetary(required=True)
    currency_id = fields.Many2one(related='loan_id.currency_id')
    payment_date = fields.Date(required=True, default=fields.Date.context_today)
    journal_id = fields.Many2one('account.journal', required=True,
        domain=[('type', 'in', ['bank', 'cash'])])
    payment_method_id = fields.Many2one('account.payment.method',
        domain=[('payment_type', '=', 'outbound')])
    communication = fields.Char('Memo')
    
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'active_id' in self.env.context:
            loan = self.env['hr.loan'].browse(self.env.context['active_id'])
            res.update({
                'loan_id': loan.id,
                'amount': loan.loan_amount,
                'communication': loan.name
            })
        return res
    
    def action_register_payment(self):
        self.ensure_one()
        
        # Create the payment
        payment = self.env['account.payment'].create({
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': self.loan_id.employee_id.work_contact_id.id,
            'amount': self.amount,
            'currency_id': self.currency_id.id,
            'journal_id': self.journal_id.id,
            'date': self.payment_date,
            'memo': self.communication or self.loan_id.name,
        })
        
        # Post the payment
        payment.action_post()
        
        # Find the payable move line from the loan's journal entry
        loan_move = self.loan_id.move_id
        if loan_move:
            payable_line = loan_move.line_ids.filtered(
                lambda l: l.account_id.account_type == 'liability_payable' and not l.reconciled
            )
            
            # Find the receivable/payable line from the payment
            payment_line = payment.move_id.line_ids.filtered(
                lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable')
            )
            
            # Reconcile the lines if both exist
            if payable_line and payment_line:
                (payable_line + payment_line).reconcile()
        
        # Update loan status
        self.loan_id.write({
            'payment_id': payment.id,
            'payment_state': 'paid',
        })
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'res_id': payment.id,
            'view_mode': 'form',
            'context': {'create': False}
        }
# wizards/wizard_loan_reconcile.py  
class WizardLoanReconcile(models.TransientModel):
    _name = 'wizard.loan.reconcile'
    _description = 'Reconcile Loan'

    loan_id = fields.Many2one('hr.loan', required=True)
    move_line_ids = fields.Many2many('account.move.line', 
        domain="[('partner_id','=',partner_id),('reconciled','=',False)]")
    partner_id = fields.Many2one('res.partner', related='loan_id.employee_id.work_contact_id')
    amount = fields.Monetary(related='loan_id.remaining_amount')
    currency_id = fields.Many2one(related='loan_id.currency_id')

    def action_reconcile(self):
        self.ensure_one()
        if not self.move_line_ids:
            raise UserError(_("Please select move lines to reconcile"))
            
        # Create writeoff if needed
        if sum(self.move_line_ids.mapped('balance')) != 0:
            writeoff_account = self.loan_id.journal_id.default_account_id
            if not writeoff_account:
                raise UserError(_("Please configure default account on journal"))

            writeoff_move = self.env['account.move'].create({
                'journal_id': self.loan_id.journal_id.id,
                'date': fields.Date.context_today(self),
                'ref': f'{self.loan_id.name}/WRITEOFF',
                'line_ids': [
                    (0, 0, {
                        'name': 'Writeoff',
                        'partner_id': self.partner_id.id,
                        'account_id': writeoff_account.id,
                        'debit': -sum(self.move_line_ids.mapped('balance')),  
                        'credit': 0.0 if sum(self.move_line_ids.mapped('balance')) < 0 else sum(self.move_line_ids.mapped('balance')),
                    }),
                ]
            })
            writeoff_move.action_post()
            self.move_line_ids |= writeoff_move.line_ids

        # Reconcile lines
        self.move_line_ids.reconcile()

        # Update loan status if fully reconciled
        if all(self.loan_id.move_id.line_ids.mapped('reconciled')):
            self.loan_id.write({'state': 'paid'})

# wizards/wizard_loan_modify_amount.py
class WizardLoanModifyAmount(models.TransientModel):
    _name = 'wizard.loan.modify.amount'
    _description = 'Modify Loan Amount'

    loan_id = fields.Many2one('hr.loan', required=True)
    current_amount = fields.Monetary(related='loan_id.loan_amount', readonly=True)
    new_amount = fields.Monetary(required=True)
    reason = fields.Text(required=True)
    currency_id = fields.Many2one(related='loan_id.currency_id')
    adjustment_date = fields.Date(required=True, default=fields.Date.context_today)

    @api.constrains('new_amount')
    def _check_amount(self):
        for wizard in self:
            if wizard.new_amount >= wizard.current_amount:
                raise ValidationError(_("New amount must be less than current amount"))
            if wizard.new_amount <= wizard.loan_id.total_paid:
                raise ValidationError(_("New amount cannot be less than already paid amount"))

    def action_modify(self):
        self.ensure_one()
        loan = self.loan_id
        
        adjustment_amount = self.current_amount - self.new_amount
        move_vals = {
            'journal_id': loan.journal_id.id,
            'date': self.adjustment_date,
            'ref': f'{loan.name}/ADJUSTMENT',
            'line_ids': [
                (0, 0, {
                    'name': 'Loan Amount Adjustment',
                    'partner_id': loan.employee_id.work_contact_id.id,
                    'account_id': loan.category_id.salary_rule_id.account_credit.id,
                    'debit': adjustment_amount,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': 'Loan Amount Adjustment',
                    'partner_id': loan.employee_id.work_contact_id.id,
                    'account_id': loan.category_id.salary_rule_id.account_debit.id,
                    'debit': 0.0,
                    'credit': adjustment_amount,
                })
            ]
        }
        
        adjustment_move = self.env['account.move'].create(move_vals)
        adjustment_move.action_post()

        loan.write({
            'loan_amount': self.new_amount,
            'description': f"{loan.description or ''}\n\nAmount adjusted on {self.adjustment_date}: {self.reason}"
        })
        
        unpaid_installments = loan.installment_ids.filtered(lambda x: not x.paid)
        if unpaid_installments:
            remaining = loan.remaining_amount
            amount_per_installment = remaining / len(unpaid_installments)
            unpaid_installments.write({'amount': amount_per_installment})

        return {'type': 'ir.actions.act_window_close'}

# wizards/wizard_loan_skip_installment.py
class WizardLoanSkipInstallment(models.TransientModel):
    _name = 'wizard.loan.skip.installment'
    _description = 'Skip Loan Installment'

    installment_id = fields.Many2one('hr.loan.installment', required=True)
    reason = fields.Text(required=True)
    skip_type = fields.Selection([
        ('double_next', 'Cobrar Doble en Siguiente Período'),
        ('move_end', 'Mover al Final del Préstamo')
    ], string='Tipo de Salto', required=True, default='double_next')
    
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'active_id' in self.env.context:
            loan = self.env['hr.loan.installment'].browse(self.env.context['active_id'])
            res.update({
                'installment_id': loan.id,
            })
        return res
    @api.onchange('skip_type')
    def _onchange_skip_type(self):
        """Muestra información sobre el impacto de la selección"""
        if self.skip_type == 'double_next':
            next_installment = self.env['hr.loan.installment'].search([
                ('loan_id', '=', self.installment_id.loan_id.id),
                ('sequence', '>', self.installment_id.sequence),
                ('skip', '=', False)
            ], order='sequence', limit=1)
            
            if next_installment:
                return {
                    'warning': {
                        'title': _('Información'),
                        'message': _(
                            'La cuota del %(date)s será de %(amount)s'
                        ) % {
                            'date': next_installment.date,
                            'amount': self.installment_id.currency_id.symbol + ' ' + 
                                    str(self.installment_id.amount + next_installment.amount)
                        }
                    }
                }

    def action_confirm(self):
        self.ensure_one()
        loan = self.installment_id.loan_id
        current_installment = self.installment_id

        if self.skip_type == 'double_next':
            # Encontrar la siguiente cuota
            next_installment = self.env['hr.loan.installment'].search([
                ('loan_id', '=', loan.id),
                ('sequence', '>', current_installment.sequence),
                ('skip', '=', False)
            ], order='sequence', limit=1)

            if not next_installment:
                raise UserError(_('No hay cuotas siguientes disponibles para combinar.'))

            # Actualizar el monto de la siguiente cuota
            next_installment.write({
                'amount': next_installment.amount + current_installment.amount,
            })

            # Marcar la cuota actual como saltada
            current_installment.write({
                'skip': True,
                'skip_reason': self.reason
            })

        else:  # move_end
            # Encontrar la última cuota
            last_installment = self.env['hr.loan.installment'].search([
                ('loan_id', '=', loan.id),
                ('skip', '=', False)
            ], order='sequence desc', limit=1)

            if not last_installment:
                raise UserError(_('No se encontró la última cuota.'))

            # Crear nueva cuota al final
            new_sequence = last_installment.sequence + 1
            new_date = last_installment.date + relativedelta(months=1)

            self.env['hr.loan.installment'].create({
                'loan_id': loan.id,
                'sequence': new_sequence,
                'date': new_date,
                'amount': current_installment.amount,
                'currency_id': current_installment.currency_id.id,
            })

            # Marcar la cuota actual como saltada
            current_installment.write({
                'skip': True,
                'skip_reason': self.reason
            })

        return {'type': 'ir.actions.act_window_close'}

class HrContractConcepts(models.Model):
    _inherit = 'hr.contract.concepts'

    loan_id = fields.Many2one('hr.loan', 'Prestamo', readonly=True)
    # Campo movido desde lavish_hr_employee para evitar dependencia circular
    line_ids = fields.One2many('hr.payslip.line', 'concept_id', string='Lineas de Nomina',
        help='Lineas de nomina donde se ha aplicado este concepto')

    # Campos computados basados en line_ids
    lines_count = fields.Integer('Cantidad Aplicaciones', compute='_compute_lines_stats', store=True)
    lines_total = fields.Float('Total Aplicado', compute='_compute_lines_stats', store=True, digits=(18, 2))
    last_application_date = fields.Date('Ultima Aplicacion', compute='_compute_lines_stats', store=True)
    first_application_date = fields.Date('Primera Aplicacion', compute='_compute_lines_stats', store=True)

    @api.depends('line_ids', 'line_ids.total', 'line_ids.slip_id.state', 'line_ids.slip_id.date_to')
    def _compute_lines_stats(self):
        """Calcula estadisticas de las lineas de nomina."""
        for record in self:
            lines = record._get_payslip_lines()
            done_lines = lines.filtered(lambda l: l.slip_id.state in ['done', 'paid'])

            record.lines_count = len(done_lines)
            record.lines_total = sum(done_lines.mapped('total'))

            if done_lines:
                dates = done_lines.mapped('slip_id.date_to')
                record.last_application_date = max(dates) if dates else False
                record.first_application_date = min(dates) if dates else False
            else:
                record.last_application_date = False
                record.first_application_date = False

    def _get_payslip_lines(self):
        """Override para usar el campo line_ids en lugar de buscar."""
        return self.line_ids

    def _get_done_payslip_lines(self):
        """Obtiene solo las lineas de nominas confirmadas o pagadas."""
        return self._get_payslip_lines().filtered(
            lambda l: l.slip_id.state in ['done', 'paid']
        )

    def _get_pending_payslip_lines(self):
        """Obtiene lineas de nominas en borrador o verificadas."""
        return self._get_payslip_lines().filtered(
            lambda l: l.slip_id.state in ['draft', 'verify']
        )

    def _get_lines_by_period(self, date_from, date_to):
        """Obtiene lineas de nomina en un periodo especifico."""
        return self._get_payslip_lines().filtered(
            lambda l: l.date_from >= date_from and l.date_from <= date_to
        )

    # ══════════════════════════════════════════════════════════════════════════
    # OVERRIDE DE DEPENDENCIAS DINAMICAS
    # Agregan line_ids a las dependencias de los campos computados
    # ══════════════════════════════════════════════════════════════════════════

    def _get_accumulated_depends(self):
        """Agrega line_ids a las dependencias."""
        return ('line_ids', 'line_ids.total')

    def _get_balance_depends(self):
        """Agrega line_ids a las dependencias base."""
        base = super()._get_balance_depends()
        return base + ('line_ids', 'line_ids.total')

    def _get_remaining_depends(self):
        """Agrega line_ids a las dependencias base."""
        base = super()._get_remaining_depends()
        return base + ('line_ids', 'line_ids.slip_id.state')

    def _get_next_payment_depends(self):
        """Agrega line_ids a las dependencias base."""
        base = super()._get_next_payment_depends()
        return base + ('line_ids', 'line_ids.slip_id.state')

    def change_state_cancel(self):
        super(HrContractConcepts, self).change_state_cancel()
        if self.loan_id:
            obj_loan = self.env['hr.loan'].search([('id', '=', self.loan_id.id)])
            obj_loan.write({'state': 'cancel'})

    _change_contract_uniq = models.Constraint('unique(input_id, contract_id, loan_id)', 'Ya existe esta regla para este contrato, por favor verficar.')


class HrLoanManualPayment(models.Model):
    """Modelo para registrar abonos manuales a préstamos"""
    _name = 'hr.loan.manual.payment'
    _description = 'Abono Manual de Préstamo'
    _order = 'date desc, id desc'

    loan_id = fields.Many2one('hr.loan', string='Préstamo', required=True, ondelete='cascade')
    employee_id = fields.Many2one(related='loan_id.employee_id', string='Empleado', store=True)
    currency_id = fields.Many2one(related='loan_id.currency_id')
    company_id = fields.Many2one(related='loan_id.company_id')

    name = fields.Char(string='Referencia', required=True)
    date = fields.Date(string='Fecha', required=True, default=fields.Date.context_today)
    amount = fields.Monetary(string='Monto', required=True)
    description = fields.Text(string='Descripción')

    state = fields.Selection([
        ('draft', 'Borrador'),
        ('done', 'Aplicado'),
        ('cancelled', 'Cancelado')
    ], string='Estado', default='draft')

    # Campos contables
    move_id = fields.Many2one('account.move', string='Asiento Contable', readonly=True)
    journal_id = fields.Many2one('account.journal', string='Diario', domain=[('type', 'in', ['bank', 'cash'])])

    # Tipo de abono
    payment_type = fields.Selection([
        ('reduce_balance', 'Reducir Saldo (No descuenta en nómina)'),
        ('advance_payment', 'Pago Anticipado de Cuotas')
    ], string='Tipo de Abono', required=True, default='reduce_balance')

    @api.constrains('amount')
    def _check_amount(self):
        for payment in self:
            if payment.amount <= 0:
                raise ValidationError(_("El monto debe ser mayor a cero"))
            if payment.amount > payment.loan_id.remaining_amount:
                raise ValidationError(_("El monto no puede ser mayor al saldo restante del préstamo"))

    def action_apply(self):
        """Aplica el abono manual"""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_("Solo se pueden aplicar abonos en estado Borrador"))

        # Si es un pago anticipado, marcar cuotas como pagadas
        if self.payment_type == 'advance_payment':
            self._apply_to_installments()

        # Crear asiento contable si hay diario configurado
        if self.journal_id:
            self._create_accounting_entry()

        self.write({'state': 'done'})
        self.loan_id._compute_amounts()

        return True

    def _apply_to_installments(self):
        """Aplica el abono a las cuotas pendientes"""
        remaining = self.amount
        pending_installments = self.loan_id.installment_ids.filtered(
            lambda x: not x.paid and not x.skip
        ).sorted('sequence')

        for installment in pending_installments:
            if remaining <= 0:
                break

            if remaining >= installment.amount:
                # Marcar la cuota como pagada
                installment.write({
                    'paid': True,
                    'payment_state': 'paid_accounting'
                })
                remaining -= installment.amount
            else:
                # Reducir el monto de la cuota
                installment.write({
                    'amount': installment.amount - remaining
                })
                remaining = 0

    def _create_accounting_entry(self):
        """Crea el asiento contable del abono"""
        self.ensure_one()

        debit_account = self.journal_id.default_account_id
        credit_account = self.loan_id._get_credit_account()

        if not all([debit_account, credit_account]):
            raise UserError(_("Configure las cuentas contables correctamente"))

        move_vals = {
            'journal_id': self.journal_id.id,
            'date': self.date,
            'ref': f'{self.loan_id.name}/ABONO/{self.name}',
            'line_ids': [
                (0, 0, {
                    'name': f'Abono Manual - {self.name}',
                    'partner_id': self.employee_id.work_contact_id.id,
                    'account_id': debit_account.id,
                    'debit': self.amount,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': f'Abono Manual - {self.name}',
                    'partner_id': self.employee_id.work_contact_id.id,
                    'account_id': credit_account.id,
                    'debit': 0.0,
                    'credit': self.amount,
                })
            ]
        }

        move = self.env['account.move'].create(move_vals)
        move.action_post()
        self.move_id = move.id

    def action_cancel(self):
        """Cancela el abono manual"""
        self.ensure_one()
        if self.state == 'cancelled':
            raise UserError(_("El abono ya está cancelado"))

        # Revertir asiento contable si existe
        if self.move_id:
            refund_move = self.move_id._reverse_moves()
            refund_move.action_post()

        self.write({'state': 'cancelled'})
        self.loan_id._compute_amounts()

        return True

    def unlink(self):
        if any(payment.state == 'done' for payment in self):
            raise UserError(_("No puede eliminar abonos aplicados. Use 'Cancelar' en su lugar."))
        return super().unlink()
