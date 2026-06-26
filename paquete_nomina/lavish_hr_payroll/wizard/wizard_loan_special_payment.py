# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class WizardLoanSpecialPayment(models.TransientModel):
    _name = 'wizard.loan.special.payment'
    _description = 'Wizard for Special Loan Payments'

    loan_id = fields.Many2one('hr.loan', string='Préstamo', required=True)
    amount = fields.Monetary(string='Monto del Pago', required=True, currency_field='currency_id')
    currency_id = fields.Many2one(related='loan_id.currency_id')
    date = fields.Date(string='Fecha del Pago', required=True, default=fields.Date.context_today)
    
    policy = fields.Selection([
        ('replace_next', 'Reemplazar Siguiente Cuota'),
        ('reduce_installments', 'Reducir Cuotas Restantes'),
        ('extra_payment', 'Pago Adicional (No Afecta Cuotas)'),
        ('group_next', 'Agrupar Cuotas'),
        ('pay_all', 'Pagar Todo el Saldo'),
    ], string='Política de Aplicación', required=True, default='replace_next')
    
    settlement = fields.Boolean(
        string='Finiquito/Liquidación',
        help='Marcar si este pago es parte de una liquidación de contrato'
    )
    
    group_count = fields.Integer(
        string='Número de Cuotas a Agrupar',
        default=2,
        help='Solo aplica si la política es "Agrupar Cuotas"'
    )
    
    apply_interest = fields.Boolean(
        string='Aplicar Intereses',
        default=True,
        help='Si debe aplicar intereses devengados antes del pago'
    )
    
    note = fields.Text(string='Observaciones')
    
    # Campos informativos
    current_balance = fields.Monetary(
        string='Saldo Actual',
        related='loan_id.remaining_amount',
        readonly=True
    )
    
    pending_installments_count = fields.Integer(
        string='Cuotas Pendientes',
        related='loan_id.pending_installments',
        readonly=True
    )
    
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self.env.context.get('active_id'):
            loan = self.env['hr.loan'].browse(self.env.context['active_id'])
            res.update({
                'loan_id': loan.id,
                'amount': loan.remaining_amount,
            })
        return res
        
    @api.constrains('amount')
    def _check_amount(self):
        for wizard in self:
            if wizard.amount <= 0:
                raise ValidationError(_("El monto debe ser mayor a cero"))
                
    @api.constrains('group_count', 'policy')
    def _check_group_count(self):
        for wizard in self:
            if wizard.policy == 'group_next' and wizard.group_count < 2:
                raise ValidationError(_("Para agrupar cuotas debe especificar al menos 2 cuotas"))
                
    @api.onchange('policy')
    def _onchange_policy(self):
        if self.policy == 'pay_all' or self.settlement:
            self.amount = self.loan_id.remaining_amount
        elif self.policy == 'replace_next':
            # Sugerir el monto de la siguiente cuota
            next_installment = self.loan_id.installment_ids.filtered(
                lambda x: not x.paid and not x.skip
            ).sorted('date')[:1]
            if next_installment:
                self.amount = next_installment.amount + (next_installment.total_interest or 0.0)
                
    @api.onchange('settlement')
    def _onchange_settlement(self):
        if self.settlement:
            self.policy = 'pay_all'
            self.amount = self.loan_id.remaining_amount
            
    def action_apply_payment(self):
        """Aplica el pago especial usando el sistema unificado"""
        self.ensure_one()
        
        if not self.loan_id:
            raise UserError(_("Debe seleccionar un préstamo"))
            
        if self.amount <= 0:
            raise UserError(_("El monto debe ser mayor a cero"))
            
        # Validar que el préstamo tenga el método register_special_payment
        if not hasattr(self.loan_id, 'register_special_payment'):
            raise UserError(_("El préstamo no soporta pagos especiales mejorados"))
            
        try:
            # Llamar al hook unificado de pagos especiales
            result = self.loan_id.register_special_payment(
                amount=self.amount,
                date=self.date,
                policy=self.policy,
                settlement=self.settlement,
                group_count=self.group_count if self.policy == 'group_next' else 0,
                note=self.note or '',
                apply_interest=self.apply_interest
            )
            
            if not result.get('success', False):
                raise UserError(_("Error al aplicar el pago especial: %s") % 
                               result.get('error', 'Error desconocido'))
                
            # Crear registro de pago especial para auditoría
            special_payment = self.env['hr.loan.special.payment'].create({
                'loan_id': self.loan_id.id,
                'name': f"Pago especial - {self.policy}",
                'date': self.date,
                'amount': self.amount,
                'payment_type': self.policy,
                'apply_interest': self.apply_interest,
                'state': 'applied',
            })
            
            # Mostrar notificación de éxito
            message = self._format_success_message(result)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Pago Especial Aplicado'),
                    'message': message,
                    'type': 'success',
                    'sticky': False,
                },
            }
            
        except Exception as e:
            raise UserError(_("Error al procesar el pago especial: %s") % str(e))
            
    def _format_success_message(self, result):
        """Formatea el mensaje de éxito según el tipo de política"""
        policy_names = {
            'replace_next': 'Reemplazo de cuota siguiente',
            'reduce_installments': 'Reducción de cuotas restantes', 
            'extra_payment': 'Pago adicional',
            'group_next': 'Agrupación de cuotas',
            'pay_all': 'Liquidación completa',
        }
        
        policy_name = policy_names.get(self.policy, self.policy)
        message = f"✅ {policy_name} por ${self.amount:,.2f} aplicado exitosamente."
        
        if self.policy == 'group_next' and result.get('grouped_installment_id'):
            message += f" Se creó una nueva cuota agrupada."
            
        if result.get('fully_paid'):
            message += " 🎉 ¡Préstamo completamente pagado!"
            
        return message
        
    def action_preview(self):
        """Muestra una vista previa del impacto del pago especial"""
        self.ensure_one()
        
        # Aquí podrías implementar lógica para mostrar una vista previa
        # del impacto del pago sin aplicarlo realmente
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Vista Previa del Pago Especial'),
            'res_model': 'wizard.loan.special.payment.preview',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_loan_id': self.loan_id.id,
                'default_amount': self.amount,
                'default_policy': self.policy,
                'default_settlement': self.settlement,
                'default_group_count': self.group_count,
                'default_apply_interest': self.apply_interest,
            }
        }