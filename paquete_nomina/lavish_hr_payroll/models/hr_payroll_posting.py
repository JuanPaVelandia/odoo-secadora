# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError,UserError
from odoo.tools import float_compare
import logging
import base64
import datetime
#---------------------------Modelo para contabilizar el pago de nómina-------------------------------#

_logger = logging.getLogger(__name__)
class HrPayrollPostingAccountMove(models.Model):
    _name = 'hr.payroll.posting.account.move'
    _description = 'Pago contabilización de nomina - Movimientos Contables'

    payroll_posting = fields.Many2one('hr.payroll.posting',string='Contabilización', required=True)
    journal_id = fields.Many2one('account.journal', string='Diario', domain=[('is_payroll_spreader', '=', True)])
    move_id = fields.Many2one('account.move', string='Movimiento Contable', readonly=True)

class HrPayrollPostingDistribution(models.Model):
    _name = 'hr.payroll.posting.distribution'
    _description = 'Pago contabilización de nomina - distribución'

    payroll_posting = fields.Many2one('hr.payroll.posting',string='Contabilización', required=True)
    partner_id = fields.Many2one('res.company',string='Ubicación laboral', required=True)
    account_id = fields.Many2one('account.account',string='Cuenta', required=True)

class HrPayrollPosting(models.Model):
    _name = 'hr.payroll.posting'
    _description = 'Pago contabilización de nomina'
    _rec_name = 'description'

    payment_type = fields.Selection([('225', 'Pago de Nómina')], string='Tipo de pago', required=True, default='225', readonly=True)
    journal_id = fields.Many2one('account.journal', string='Diario', domain=[('is_payroll_spreader', '=', True)])
    company_id = fields.Many2one('res.company',string='Compañia', required=True, default=lambda self: self.env.company)
    vat_payer = fields.Char(string='NIT Pagador', readonly=True, related='company_id.partner_id.vat')
    payslip_id = fields.Many2one('hr.payslip.run',string='Lote de nómina')
    description = fields.Char(string='Descripción', required=True) 
    state = fields.Selection([('draft', 'Borrador'),('done', 'Hecho')], string='Estado', default='draft')
    source_information = fields.Selection([('lote', 'Por lote'),
                                          ('liquidacion', 'Por liquidaciones')],'Origen información', default='lote') 
    liquidations_ids= fields.Many2many('hr.payslip', string='Liquidaciones')
    payment_date = fields.Date(string='Fecha de pago', default=fields.Date.today())
    payslip_id_run_ids= fields.Many2many('hr.payslip.run', string='Lotes de Liquidaciones')
    payroll_posting_distribution_ids = fields.One2many('hr.payroll.posting.distribution', 'payroll_posting',string='Distribución')
    payroll_posting_account_move_ids = fields.One2many('hr.payroll.posting.account.move', 'payroll_posting',string='Movimientos Contables')
    disaggregate_counterparty = fields.Boolean(string='¿Desea desagregar la contrapartida?')
    #_sql_constraints = [('change_payslip_id_uniq', 'unique(payslip_id,liquidations_ids)', 'Ya existe un pago de contabilización para este lote/liquidación, por favor verificar')]
    #Realizar validacion
    type = fields.Selection([('CD', 'Cuenta de dispersion Por Contacto'),
                            ('Gl', 'Global'),],'Tipo de dispersion', default='Gl') 

    def payroll_posting(self):
        if self.payment_type != '225':
            raise ValidationError(_('El tipo de pago seleccionado no esta desarrollado.'))
            
        payslips = self.env['hr.payslip']
        if self.source_information == 'lote':
            batch_ids = [x for x in ([self.payslip_id.id] + self.payslip_id_run_ids.ids) if x]
            if not batch_ids:
                raise ValidationError(_('No se han seleccionado lotes de nómina válidos.'))
            payslips = self.env['hr.payslip'].search([
                ('payslip_run_id', 'in', batch_ids),
                ('employee_id.company_id', '=', self.company_id.id)
            ])
        elif self.source_information == 'liquidacion':
            if not self.liquidations_ids:
                raise ValidationError(_('No se han seleccionado liquidaciones.'))
            payslips = self.env['hr.payslip'].search([
                ('id', 'in', self.liquidations_ids.ids),
                ('employee_id.company_id', '=', self.company_id.id)
            ])
        else:
            raise ValidationError(_('No se ha configurado origen de información.'))

        if not payslips:
            raise ValidationError(_('No se encontraron nóminas válidas para procesar.'))

        journals = [self.journal_id]
        if self.type == 'CD':
            journals = self.env['account.journal'].search([
                ('plane_type', 'in', ['bancolombiasap', 'bancolombiapab', 'davivienda1', 
                                    'occired', 'avvillas1', 'bancobogota', 'popular', 'bbva'])
            ])

        for journal in journals:
            self.journal_id = journal
            if not self.journal_id:
                continue

            move_lines = []
            total_credit = 0.0

            for payslip in payslips:
                analytic_account_id = payslip.employee_id.analytic_account_id.id 
                net_line = payslip.move_id.line_ids.filtered(lambda l: l.hr_salary_rule_id.code == 'NET')
                
                if not net_line:
                    continue

                value = net_line.credit
                if value <= 0:
                    continue

                move_lines.append({
                    'name': f"{net_line.name} | {payslip.employee_id.name} | Nómina {payslip.name}",
                    'partner_id': payslip.employee_id.work_contact_id.id,
                    'account_id': net_line.account_id.id,
                    'journal_id': self.journal_id.id,
                    'date': self.payment_date,
                    'debit': value,
                    'credit': 0,
                    'analytic_distribution': (analytic_account_id and {analytic_account_id: 100})
                })
                total_credit += value

                if self.disaggregate_counterparty:
                    credit_account =  self.journal_id.default_account_id.id
                    move_lines.append({
                        'name': f"{self.description} | {payslip.employee_id.name} | Nómina {payslip.number}",
                        'partner_id': payslip.employee_id.work_contact_id.id,
                        'account_id': credit_account,
                        'journal_id': self.journal_id.id,
                        'date': self.payment_date,
                        'debit': 0,
                        'credit': value,
                        'analytic_distribution': (analytic_account_id and {analytic_account_id: 100})
                    })

            if not self.disaggregate_counterparty and total_credit > 0:
                credit_account = (self.journal_id.default_account_id.id)
                move_lines.append({
                    'name': f"{self.description} | Nómina {payslip.payslip_run_id.name or payslip.number}",
                    'partner_id': payslip.employee_id.work_contact_id.id,
                    'account_id': credit_account,
                    'journal_id': self.journal_id.id,
                    'date': self.payment_date,
                    'debit': 0,
                    'credit': total_credit,
                    'analytic_distribution': (analytic_account_id and {analytic_account_id: 100})
                })

            if move_lines:
                move = self.env['account.move'].create({
                    'company_id': self.company_id.id,
                    'ref': self.description,
                    'journal_id': self.journal_id.id,
                    'date': self.payment_date,
                    'line_ids': [(0, 0, line) for line in move_lines]
                })
                
                # Create move relation
                self.env['hr.payroll.posting.account.move'].create({
                    'payroll_posting': self.id,
                    'journal_id': self.journal_id.id,
                    'move_id': move.id
                })

        # Mark as done
        if self.source_information == 'lote':
            self.payslip_id.write({'definitive_plan': True})
        elif self.source_information == 'liquidacion':
            self.liquidations_ids.write({'definitive_plan': True})
        self.write({'state': 'done'})


    def payroll_rever_posting(self):
        for moves in self.payroll_posting_account_move_ids:
            self.env['account.move'].search([('id', '=', moves.move_id.id)]).unlink()
            moves.unlink()
        if self.source_information == 'lote':
            self.payslip_id.write({'definitive_plan':False})
        elif self.source_information == 'liquidacion':
            for liq in self.liquidations_ids:
                liq.write({'definitive_plan':False})
        self.write({'state': 'draft'})

    def action_post(self):
        for record in self:
            moves = record.payroll_posting_account_move_ids.move_id
            for move in moves:
                if move.state != 'posted':
                    move.action_post()

            payslips = record._get_source_payslips_for_reconcile()
            net_lines = record._get_net_lines_for_reconcile(payslips)
            payment_debit_lines = moves.line_ids.filtered(
                lambda l: l.move_id.state == 'posted'
                and not l.reconciled
                and l.account_id.reconcile
                and l.debit > 0
            )

            if not net_lines or not payment_debit_lines:
                continue

            rounding = record.company_id.currency_id.rounding
            unmatched_count = 0

            for payment_line in payment_debit_lines:
                amount_to_match = abs(payment_line.amount_residual or payment_line.balance)
                candidate_lines = net_lines.filtered(
                    lambda l: not l.reconciled
                    and l.account_id.id == payment_line.account_id.id
                    and l.partner_id.id == payment_line.partner_id.id
                )

                match_line = candidate_lines.filtered(
                    lambda l: float_compare(
                        abs(l.amount_residual or l.balance),
                        amount_to_match,
                        precision_rounding=rounding
                    ) == 0
                )[:1]

                if not match_line:
                    unmatched_count += 1
                    continue

                (payment_line + match_line).with_context(skip_account_move_synchronization=True).reconcile()

            if unmatched_count:
                _logger.warning(
                    "No fue posible conciliar %s líneas de pago en la contabilización %s.",
                    unmatched_count,
                    record.display_name,
                )

    def _get_source_payslips_for_reconcile(self):
        self.ensure_one()
        payslips = self.env['hr.payslip']

        if self.source_information == 'lote':
            batch_ids = [x for x in ([self.payslip_id.id] + self.payslip_id_run_ids.ids) if x]
            if not batch_ids:
                raise UserError(_('No se han seleccionado lotes para conciliar.'))
            payslips = self.env['hr.payslip'].search([
                ('payslip_run_id', 'in', batch_ids),
                ('employee_id.company_id', '=', self.company_id.id),
            ])
        elif self.source_information == 'liquidacion':
            if not self.liquidations_ids:
                raise UserError(_('No se han seleccionado liquidaciones para conciliar.'))
            payslips = self.liquidations_ids.filtered(lambda p: p.employee_id.company_id == self.company_id)

        if not payslips:
            raise UserError(_('No se encontraron nóminas origen para conciliar.'))
        return payslips

    def _get_net_lines_for_reconcile(self, payslips):
        self.ensure_one()
        missing_move = payslips.filtered(lambda p: not p.move_id)
        if missing_move:
            names = ', '.join(missing_move.mapped('display_name')[:5])
            raise UserError(_('Estas nóminas no están contabilizadas: %s') % names)

        not_posted = payslips.filtered(lambda p: p.move_id.state != 'posted')
        if not_posted:
            names = ', '.join(not_posted.mapped('display_name')[:5])
            raise UserError(_('Estas pólizas de nómina no están publicadas: %s') % names)

        net_lines = payslips.move_id.line_ids.filtered(
            lambda l: l.hr_salary_rule_id.code == 'NET'
            and not l.reconciled
            and l.account_id.reconcile
            and l.move_id.state == 'posted'
        )
        non_reconcilable = payslips.move_id.line_ids.filtered(
            lambda l: l.hr_salary_rule_id.code == 'NET' and not l.account_id.reconcile
        )
        if non_reconcilable:
            accounts = ', '.join(non_reconcilable.mapped('account_id.display_name')[:5])
            raise UserError(_('Las cuentas NET no permiten conciliación: %s') % accounts)

        return net_lines
    def open_reconcile_view(self):
        return self.payroll_posting_account_move_ids.move_id.line_ids.open_reconcile_view()

    @api.constrains('payslip_id','liquidations_ids')
    def _check_uniq_payslip_id(self):  
        for record in self:
            obj_lote = False
            obj_liq = False
            if record.source_information == 'lote':
                obj_lote = self.env['hr.payroll.posting'].search([('payslip_id','=',record.payslip_id.id),('id','!=',record.id)])
            if record.source_information == 'liquidacion':
                obj_liq = self.env['hr.payroll.posting'].search([('liquidations_ids','in',record.liquidations_ids.ids),('id','!=',record.id)])

            #if obj_lote or obj_liq:
            #    raise ValidationError(_('Ya existe un pago de contabilización para este lote/liquidación, por favor verificar'))  

    def unlink(self):
        if any(self.filtered(lambda posting: posting.state not in ('draft'))):
            raise ValidationError(_('No se puede eliminar una contabilización del pago en estado hecho!'))
        return super(HrPayrollPosting, self).unlink()
