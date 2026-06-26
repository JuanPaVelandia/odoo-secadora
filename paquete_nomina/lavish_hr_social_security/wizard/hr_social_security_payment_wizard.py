# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class HrSocialSecurityPaymentWizard(models.TransientModel):
    """Wizard para registrar pagos de seguridad social"""
    _name = 'hr.social.security.payment.wizard'
    _description = 'Wizard de Pago de Seguridad Social'

    social_security_id = fields.Many2one(
        'hr.payroll.social.security',
        string='Seguridad Social',
        required=True,
        readonly=True
    )
    payment_date = fields.Date(
        string='Fecha de Pago',
        required=True,
        default=fields.Date.today
    )
    amount = fields.Float(
        string='Monto a Pagar',
        required=True
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Diario de Pago',
        required=True,
        domain=[('type', 'in', ['bank', 'cash'])]
    )
    reference = fields.Char(
        string='Referencia',
        help='Número de transacción, cheque, etc.'
    )
    notes = fields.Text(string='Notas')

    # Campos informativos
    amount_to_pay = fields.Float(
        string='Monto Total a Pagar',
        related='social_security_id.amount_to_pay',
        readonly=True
    )
    amount_already_paid = fields.Float(
        string='Ya Pagado',
        related='social_security_id.amount_paid',
        readonly=True
    )
    current_balance = fields.Float(
        string='Saldo Actual',
        related='social_security_id.balance',
        readonly=True
    )

    create_accounting_entry = fields.Boolean(
        string='Crear Asiento Contable',
        default=True,
        help='Si está marcado, se creará un asiento contable para este pago'
    )

    is_vacation_liquidation = fields.Boolean(
        string='Es Liquidación de Vacaciones',
        related='social_security_id.is_vacation_liquidation',
        readonly=True
    )

    @api.onchange('social_security_id')
    def _onchange_social_security_id(self):
        """Establece el monto por defecto al saldo pendiente"""
        if self.social_security_id:
            self.amount = self.social_security_id.balance
            self.journal_id = self.social_security_id.payment_journal_id

    @api.constrains('amount')
    def _check_amount(self):
        for record in self:
            if record.amount <= 0:
                raise ValidationError(_('El monto debe ser mayor a cero.'))

    def action_register_payment(self):
        """Registra el pago de seguridad social"""
        self.ensure_one()

        if self.amount <= 0:
            raise UserError(_('El monto debe ser mayor a cero.'))

        ss = self.social_security_id

        # Crear línea de pago
        payment_line = self.env['hr.social.security.payment.line'].create({
            'social_security_id': ss.id,
            'payment_date': self.payment_date,
            'amount': self.amount,
            'payment_type': 'payment',
            'journal_id': self.journal_id.id,
            'reference': self.reference,
            'notes': self.notes,
        })

        # Actualizar monto pagado en seguridad social
        new_amount_paid = ss.amount_paid + self.amount
        ss.write({
            'amount_paid': new_amount_paid,
            'payment_date': self.payment_date,
            'payment_journal_id': self.journal_id.id,
        })

        # Crear asiento contable si está habilitado
        if self.create_accounting_entry and not ss.skip_accounting_entry:
            move = self._create_payment_accounting_entry(payment_line)
            if move:
                payment_line.write({'move_id': move.id})

        # Calcular si hay sobrepago
        total_credited = new_amount_paid + ss.applied_overpayment
        if total_credited > ss.amount_to_pay:
            overpayment = total_credited - ss.amount_to_pay
            message = _(
                'Pago registrado exitosamente.\n'
                'Monto pagado: ${:,.2f}\n'
                'Sobrepago generado: ${:,.2f}\n'
                'Este sobrepago puede aplicarse a futuros periodos.'
            ).format(self.amount, overpayment)
        elif total_credited == ss.amount_to_pay:
            message = _(
                'Pago registrado exitosamente.\n'
                'Monto pagado: ${:,.2f}\n'
                'El periodo está completamente pagado.'
            ).format(self.amount)
        else:
            balance = ss.amount_to_pay - total_credited
            message = _(
                'Pago registrado exitosamente.\n'
                'Monto pagado: ${:,.2f}\n'
                'Saldo pendiente: ${:,.2f}'
            ).format(self.amount, balance)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Pago Registrado'),
                'message': message,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }

    def _create_payment_accounting_entry(self, payment_line):
        """Crea el asiento contable para el pago"""
        ss = self.social_security_id

        # Buscar configuración de cierre para obtener cuentas
        closing_config = self.env['hr.closing.configuration.header'].search([
            ('process', 'in', ['ss_empresa_salud', 'ss_empresa_pension'])
        ], limit=1)

        if not closing_config:
            # Si no hay configuración, no crear asiento
            return False

        # Obtener cuenta de banco/caja del diario
        if self.journal_id.type == 'bank':
            credit_account = self.journal_id.default_account_id
        else:
            credit_account = self.journal_id.default_account_id

        if not credit_account:
            raise UserError(_('El diario seleccionado no tiene cuenta predeterminada configurada.'))

        # Crear asiento de pago
        move_vals = {
            'journal_id': self.journal_id.id,
            'date': self.payment_date,
            'ref': f'Pago SS {ss.name} - {self.reference or ""}',
            'social_security_payment_id': ss.id,
            'line_ids': [],
        }

        # El pago reduce el pasivo (débito a la cuenta de pasivo SS)
        # y reduce la cuenta de banco/caja (crédito)

        # Buscar la cuenta de pasivo de SS desde la configuración
        # Por simplicidad, usamos una distribución proporcional entre los conceptos

        total = ss.amount_to_pay
        if total <= 0:
            return False

        # Proporciones de cada concepto
        proportions = {
            'health': ss.total_health / total if total else 0,
            'pension': ss.total_pension / total if total else 0,
            'solidarity': ss.total_solidarity / total if total else 0,
            'arl': ss.total_arl / total if total else 0,
            'parafiscal': ss.total_parafiscal / total if total else 0,
        }

        line_ids = []

        # Línea de crédito (banco/caja)
        line_ids.append((0, 0, {
            'name': f'Pago Seguridad Social {ss.name}',
            'account_id': credit_account.id,
            'debit': 0.0,
            'credit': self.amount,
            'partner_id': ss.company_id.partner_id.id,
        }))

        # Línea de débito (reducción de pasivo)
        # Buscamos la cuenta de pasivo de SS
        debit_account = False
        for closing in self.env['hr.closing.configuration.header'].search([
            ('process', 'in', ['ss_empresa_salud', 'ss_empresa_pension', 'ss_empresa_arp', 'ss_empresa_caja'])
        ]):
            for detail in closing.detail_ids:
                if detail.credit_account:
                    debit_account = detail.credit_account
                    break
            if debit_account:
                break

        if debit_account:
            line_ids.append((0, 0, {
                'name': f'Pago Seguridad Social {ss.name}',
                'account_id': debit_account.id,
                'debit': self.amount,
                'credit': 0.0,
                'partner_id': ss.company_id.partner_id.id,
            }))

            move_vals['line_ids'] = line_ids

            move = self.env['account.move'].create(move_vals)
            return move

        return False

    def action_register_and_mark_vacation(self):
        """Registra el pago y marca como liquidación de vacaciones"""
        self.ensure_one()

        # Marcar como liquidación de vacaciones (omitir asiento)
        self.social_security_id.mark_as_vacation_liquidation()
        self.create_accounting_entry = False

        return self.action_register_payment()
