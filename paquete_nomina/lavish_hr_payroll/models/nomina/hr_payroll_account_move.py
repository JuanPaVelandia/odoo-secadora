# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero

from collections import defaultdict
from datetime import datetime, timedelta, date, time
import pytz

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    hr_salary_rule_id = fields.Many2one('hr.salary.rule', string='Regla salarial')
    hr_struct_id_id = fields.Many2one('hr.payroll.structure', string='Estructura salarial')
    run_id = fields.Many2one('hr.payslip.run', 'Lote de nomina')
    # Campos de trazabilidad para asociar líneas contables con líneas de nómina
    payslip_line_id = fields.Many2one('hr.payslip.line', string='Línea de Nómina', index=True)
    loan_id = fields.Many2one('hr.loan', string='Préstamo', index=True)
    loan_installment_id = fields.Many2one('hr.loan.installment', string='Cuota Préstamo')
    concept_id = fields.Many2one('hr.contract.concepts', string='Concepto', index=True)
    entity_id = fields.Many2one('hr.employee.entities', string='Entidad', index=True)

class AccountMove(models.Model):
    _inherit = 'account.move'



class Hr_payslip(models.Model):
    _inherit = 'hr.payslip'

    # ---------------------------------------CONTABILIZACIÓN DE LA NÓMINA---------------------------------------------#

    def _get_batch_account_setting(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            'lavish_hr_payroll.module_hr_payroll_batch_account'
        ) or False

    def _get_move_date(self, slip):
        if slip.struct_id.process in ['vacaciones', 'contrato']:
            return slip.date_from
        return slip.date_to

    def _get_move_ref(self, slip, date, by_employee):
        if by_employee:
            return slip.display_name or slip.number or date.strftime('%B %Y')
        return date.strftime('%B %Y')

    def _append_move_narration(self, move_dict, slip):
        parts = []
        if slip.number:
            parts.append(slip.number)
        if slip.employee_id and slip.employee_id.name:
            parts.append(slip.employee_id.name)
        if parts:
            move_dict['narration'] += " - ".join(parts) + "\n"

    def _get_partner_from_social_security(self, line, slip, entity_type):
        """Obtiene partner desde entidades de seguridad social del empleado"""
        if line.code not in ['SSOCIAL001', 'SSOCIAL002', 'SSOCIAL003', 'SSOCIAL004']:
            return False
        
        code_mapping = {
            'SSOCIAL001': 'eps',
            'SSOCIAL002': 'pension',
            'SSOCIAL003': ['subsistencia', 'pension'],
            'SSOCIAL004': ['solidaridad', 'pension'],
        }
        
        valid_types = code_mapping.get(line.code, [])
        if entity_type not in valid_types and line.code != 'SSOCIAL001':
            return False
        
        for entity in slip.employee_id.social_security_entities:
            if entity.contrib_id.type_entities == entity_type:
                if line.code == 'SSOCIAL001' and entity_type == 'eps':
                    return entity.partner_id.partner_id if entity.partner_id else False
                elif line.code in ['SSOCIAL002', 'SSOCIAL003', 'SSOCIAL004'] and entity_type == 'pension':
                    return entity.partner_id.partner_id if entity.partner_id else False
                elif line.code == 'SSOCIAL003' and entity_type == 'subsistencia':
                    return entity.partner_id.partner_id if entity.partner_id else False
                elif line.code == 'SSOCIAL004' and entity_type == 'solidaridad':
                    return entity.partner_id.partner_id if entity.partner_id else False
        return False

    def _get_partner_from_entity_line(self, line, slip):
        """Obtiene partner desde entity_id de la línea o concepto"""
        # Prioridad 1: entity_id de la línea de nómina
        if line.entity_id and line.entity_id.partner_id:
            return line.entity_id.partner_id
        # Prioridad 2: partner desde concepto
        if line.concept_id and line.concept_id.partner_id and line.concept_id.partner_id.partner_id:
            return line.concept_id.partner_id.partner_id
        return False

    def _get_partner_for_account_rule(self, line, slip, account_rule, partner_type='debit'):
        """Obtiene el partner según la configuración de la regla contable"""
        if partner_type == 'debit':
            third_config = account_rule.third_debit
        else:
            third_config = account_rule.third_credit
        
        if third_config == 'entidad':
            # Intentar desde entity_id o concepto
            partner = self._get_partner_from_entity_line(line, slip)
            if partner:
                return partner
            # Buscar en entidades de seguridad social
            if line.code == 'SSOCIAL001':
                return self._get_partner_from_social_security(line, slip, 'eps')
            elif line.code in ['SSOCIAL002', 'SSOCIAL003', 'SSOCIAL004']:
                partner = self._get_partner_from_social_security(line, slip, 'pension')
                if partner:
                    return partner
                if line.code == 'SSOCIAL003':
                    return self._get_partner_from_social_security(line, slip, 'subsistencia')
                elif line.code == 'SSOCIAL004':
                    return self._get_partner_from_social_security(line, slip, 'solidaridad')
        elif third_config == 'compañia':
            return slip.employee_id.company_id.partner_id
        elif third_config == 'empleado':
            return slip.employee_id.work_contact_id
        
        return slip.employee_id.work_contact_id

    def _get_default_partner(self, line, slip):
        """Obtiene el partner por defecto para una línea"""
        # Prioridad 1: entity_id de la línea
        if line.entity_id and line.entity_id.partner_id:
            return line.entity_id.partner_id
        # Prioridad 2: partner desde concepto
        if line.concept_id and line.concept_id.partner_id and line.concept_id.partner_id.partner_id:
            return line.concept_id.partner_id.partner_id
        # Prioridad 3: partner de la línea
        if line.partner_id:
            return line.partner_id
        # Fallback: partner del empleado
        return slip.employee_id.work_contact_id or slip.employee_id.address_home_id

    def _validate_department_match(self, account_rule, employee, max_levels=3):
        """Valida si el departamento del empleado coincide con la regla contable"""
        if not account_rule.department:
            return True
        dept = employee.department_id
        levels = 0
        while dept and levels < max_levels:
            if account_rule.department.id == dept.id:
                return True
            dept = dept.parent_id
            levels += 1
        return False

    def _get_account_rule_for_line(self, line, slip):
        """Busca la regla contable que aplica para una línea de nómina"""
        for account_rule in line.salary_rule_id.salary_rule_accounting:
            # Validar ubicación de trabajo
            if account_rule.work_location and account_rule.work_location.id != slip.employee_id.address_id.id:
                continue
            # Validar compañía
            if account_rule.company and account_rule.company.id != slip.employee_id.company_id.id:
                continue
            # Validar departamento (con jerarquía)
            if not self._validate_department_match(account_rule, slip.employee_id):
                continue
            # Verificar que tenga al menos una cuenta configurada
            if account_rule.debit_account or account_rule.credit_account:
                return account_rule
        return False

    def _get_account_from_loan(self, loan):
        """Obtiene la cuenta de crédito desde un préstamo"""
        if not loan:
            return False
        try:
            # El método _get_credit_account existe en hr.loan
            return loan._get_credit_account()
        except (AttributeError, Exception):
            return False

    def _get_account_from_concept(self, concept, salary_rule):
        """Obtiene las cuentas desde un concepto"""
        if not concept:
            return False, False
        if concept.payroll_account_id:
            if salary_rule.dev_or_ded == 'deduccion':
                return False, concept.payroll_account_id
            else:
                return concept.payroll_account_id, False
        return False, False

    def _get_account_from_entity(self, entity):
        """Obtiene las cuentas desde una entidad"""
        if not entity:
            return False, False
        try:
            debit = entity.debit_account if entity.debit_account else False
        except (AttributeError, KeyError):
            debit = False
        try:
            credit = entity.credit_account if entity.credit_account else False
        except (AttributeError, KeyError):
            credit = False
        return debit, credit

    def _get_account_ids_for_line(self, line, slip):
        """Obtiene las cuentas de débito y crédito para una línea con prioridades"""
        # Inicializar con cuentas por defecto de la regla
        debit_account_id = line.salary_rule_id.account_debit.id if line.salary_rule_id.account_debit else False
        credit_account_id = line.salary_rule_id.account_credit.id if line.salary_rule_id.account_credit else False
        account_rule = None

        # Prioridad 1: Cuentas desde entidad (más específico)
        if line.entity_id:
            entity_debit, entity_credit = self._get_account_from_entity(line.entity_id)
            if entity_debit:
                debit_account_id = entity_debit.id
            if entity_credit:
                credit_account_id = entity_credit.id

        # Prioridad 2: Cuentas desde concepto
        if line.concept_id:
            concept_debit, concept_credit = self._get_account_from_concept(line.concept_id, line.salary_rule_id)
            if concept_debit:
                debit_account_id = concept_debit.id
            if concept_credit:
                credit_account_id = concept_credit.id

        # Prioridad 3: Cuenta de crédito desde préstamo
        if line.loan_id:
            loan_credit = self._get_account_from_loan(line.loan_id)
            if loan_credit:
                credit_account_id = loan_credit.id

        # Prioridad 4: Cuentas desde regla contable (configuración por ubicación/departamento)
        account_rule = self._get_account_rule_for_line(line, slip)
        if account_rule:
            if account_rule.debit_account:
                debit_account_id = account_rule.debit_account.id
            if account_rule.credit_account:
                credit_account_id = account_rule.credit_account.id

        return debit_account_id, credit_account_id, account_rule

    def _get_retention_base_amount(self, line):
        base = line.amount_base or line.amount or line.total or 0.0
        return abs(base)

    def _get_retention_rule_codes(self):
        return {
            'RETFTE001',
            'RT_MET_01',
            'RET_PRIMA',
            'RTF_INDEM',
        }

    def _is_retention_rule(self, rule):
        if not rule or not rule.code:
            return False
        if rule.code in self._get_retention_rule_codes():
            return True
        return rule.code.startswith('RET') and bool(rule.account_tax_id)

    def _get_adjustment_entry_name(self, slip):
        addref_work_address_account_moves = self.env['ir.config_parameter'].sudo().get_param(
            'lavish_hr_payroll.addref_work_address_account_moves'
        ) or False
        if addref_work_address_account_moves and slip.employee_id.address_id:
            if slip.employee_id.address_id.parent_id:
                return f"{slip.employee_id.address_id.parent_id.vat} {slip.employee_id.address_id.display_name}|Ajuste al peso"
            return f"{slip.employee_id.address_id.vat} {slip.employee_id.address_id.display_name}|Ajuste al peso"
        return 'Ajuste al peso'

    def _prepare_move_dict(self, slip, journal_id, date, by_employee):
        move_dict = {
            'narration': '',
            'ref': self._get_move_ref(slip, date, by_employee),
            'journal_id': journal_id,
            'date': date,
        }
        if by_employee:
            move_dict['partner_id'] = slip.employee_id.address_id.id
        return move_dict

    def _calculate_line_amount(self, line, slip):
        """Calcula el monto de una línea de nómina considerando NET y not_computed_in_net"""
        amount = -line.total if slip.credit_note else line.total
        if line.code == 'NET':  # Check if the line is the 'Net Salary'.
            obj_rule_net = self.env['hr.salary.rule'].search([('code', '=', 'NET'), ('struct_id', '=', slip.struct_id.id)], limit=1)
            if len(obj_rule_net) > 0:
                line.write({'salary_rule_id': obj_rule_net.id})
            for tmp_line in slip.line_ids.filtered(lambda line: line.category_id and line.salary_rule_id.not_computed_in_net == False):
                if tmp_line.salary_rule_id.not_computed_in_net:  # Check if the rule must be computed in the 'Net Salary' or not.
                    if amount > 0:
                        amount -= abs(tmp_line.total)
                    elif amount < 0:
                        amount += abs(tmp_line.total)
        return amount

    def _prepare_traceability_fields(self, line):
        """Prepara los campos de trazabilidad para una línea contable"""
        return {
            'payslip_line_id': line.id,
            'loan_id': line.loan_id.id if line.loan_id else False,
            'loan_installment_id': line.loan_installment_id.id if line.loan_installment_id else False,
            'concept_id': line.concept_id.id if line.concept_id else False,
            'entity_id': line.entity_id.id if line.entity_id else False,
        }

    def _get_line_grouping_setting(self):
        """Obtiene la configuración de agrupación de líneas desde parámetros anuales"""
        try:
            params = self.env['hr.annual.parameters'].get_for_year(
                fields.Date.today().year,
                company_id=self.env.company.id,
                raise_if_not_found=False
            )
            if params:
                return params.accounting_line_grouping == 'group'
        except (AttributeError, KeyError, Exception):
            pass
        # Por defecto agrupar si no hay configuración
        return True

    def _find_existing_line(self, line, line_ids, partner_id, account_id, debit, credit):
        """Busca una línea existente que coincida con los criterios según configuración de agrupación"""
        # Si está configurado para mostrar detalle, no buscar líneas existentes
        if not self._get_line_grouping_setting():
            return False
        
        # Si está configurado para agrupar, buscar línea existente
        existing_line = (
            line_id for line_id in line_ids if
            line_id['partner_id'] == partner_id
            and line_id['account_id'] == account_id
            and line_id.get('hr_salary_rule_id') == line.salary_rule_id.id
            and ((line_id['debit'] > 0 and credit <= 0) or (line_id['credit'] > 0 and debit <= 0))
        )
        return next(existing_line, False)

    def _merge_line_values(self, existing_line, line_name, debit, credit):
        """Fusiona valores en una línea existente"""
        line_name_pieces = set(existing_line['name'].split(', '))
        line_name_pieces.add(line_name)
        existing_line['name'] = ', '.join(line_name_pieces)
        existing_line['debit'] += debit
        existing_line['credit'] += credit

    def _create_accounting_line(self, line, slip, date, account_id, partner_id, debit, credit, analytic_account_id):
        """Crea un diccionario con los datos de una línea contable"""
        traceability = self._prepare_traceability_fields(line)
        return {
            'name': line.name,
            'hr_salary_rule_id': line.salary_rule_id.id,
            'hr_struct_id_id': line.slip_id.struct_id.id,
            'partner_id': partner_id,
            'account_id': account_id,
            'journal_id': slip.struct_id.journal_id.id,
            'date': date,
            'debit': debit,
            'credit': credit,
            'analytic_distribution': (analytic_account_id and {analytic_account_id: 100}),
            **traceability
        }

    def _process_debit_line(self, line, slip, date, amount, debit_account_id, debit_third_id, analytic_account_id, line_ids):
        """Procesa y crea/actualiza la línea de débito"""
        if not debit_account_id:
            return
        
        debit = amount if amount > 0.0 else 0.0
        credit = -amount if amount < 0.0 else 0.0
        debit_partner_id = debit_third_id.id if debit_third_id else False
        
        existing_line = self._find_existing_line(line, line_ids, debit_partner_id, debit_account_id, debit, credit)
        
        if existing_line:
            self._merge_line_values(existing_line, line.name, debit, credit)
        else:
            debit_line = self._create_accounting_line(
                line, slip, date, debit_account_id, debit_partner_id, debit, credit, analytic_account_id
            )
            line_ids.append(debit_line)

    def _prepare_retention_tax_data(self, line, credit_account_id):
        """Prepara los datos de impuestos para una regla de retención"""
        if not self._is_retention_rule(line.salary_rule_id) or not line.salary_rule_id.account_tax_id:
            return {}
        
        tax_repartition_line_id = (
            self.env["account.tax.repartition.line"]
            .search([
                ("invoice_tax_id", "=", line.salary_rule_id.account_tax_id.id),
                ("account_id", "=", credit_account_id),
            ])
            .id
        )
        
        tax_tag_ids = (
            self.env["account.tax.repartition.line"]
            .search([
                ("invoice_tax_id", "=", line.salary_rule_id.account_tax_id.id),
                ("repartition_type", "=", "tax"),
                ("account_id", "=", credit_account_id),
            ])
            .tag_ids
        )
        
        return {
            'tax_line_id': line.salary_rule_id.account_tax_id.id,
            'tax_base_amount': self._get_retention_base_amount(line),
            'tax_ids': [line.salary_rule_id.account_tax_id.id],
            'tax_repartition_line_id': tax_repartition_line_id,
            'tax_tag_ids': tax_tag_ids,
        }

    def _process_credit_line(self, line, slip, date, amount, credit_account_id, credit_third_id, analytic_account_id, line_ids):
        """Procesa y crea/actualiza la línea de crédito"""
        if not credit_account_id:
            return
        
        # Ajustar monto si es deducción negativa
        adjusted_amount = amount
        if amount < 0.0 and line.salary_rule_id.dev_or_ded == 'deduccion':
            adjusted_amount = amount * -1
        
        debit = -adjusted_amount if adjusted_amount < 0.0 else 0.0
        credit = adjusted_amount if adjusted_amount > 0.0 else 0.0
        credit_partner_id = credit_third_id.id if credit_third_id else False
        
        existing_line = self._find_existing_line(line, line_ids, credit_partner_id, credit_account_id, debit, credit)
        
        if existing_line:
            self._merge_line_values(existing_line, line.name, debit, credit)
        else:
            credit_line = self._create_accounting_line(
                line, slip, date, credit_account_id, credit_partner_id, debit, credit, analytic_account_id
            )
            # Agregar datos de retención si aplica
            retention_data = self._prepare_retention_tax_data(line, credit_account_id)
            credit_line.update(retention_data)
            line_ids.append(credit_line)

    def _process_payslip_line(self, line, slip, date, precision, line_ids):
        """Procesa una línea de nómina y crea las líneas contables correspondientes"""
        amount = self._calculate_line_amount(line, slip)
        if float_is_zero(amount, precision_digits=precision):
            return
        
        # Obtener cuentas y terceros
        debit_third_id = self._get_default_partner(line, slip)
        credit_third_id = debit_third_id
        analytic_account_id = line.employee_id.analytic_account_id.id
        debit_account_id, credit_account_id, account_rule = self._get_account_ids_for_line(line, slip)

        # Ajustar terceros según regla contable
        if account_rule:
            debit_partner = self._get_partner_for_account_rule(line, slip, account_rule, 'debit')
            if debit_partner:
                debit_third_id = debit_partner
            
            credit_partner = self._get_partner_for_account_rule(line, slip, account_rule, 'credit')
            if credit_partner:
                credit_third_id = credit_partner
            
            # Ajustar cuenta analítica según código de cuenta
            if debit_account_id and account_rule.debit_account:
                account_code = account_rule.debit_account.code[0:1] if account_rule.debit_account.code else ''
                if account_code in ['4', '5', '6', '7']:
                    analytic_account_id = line.employee_id.analytic_account_id.id
            elif credit_account_id and account_rule.credit_account:
                account_code = account_rule.credit_account.code[0:1] if account_rule.credit_account.code else ''
                if account_code in ['4', '5', '6', '7']:
                    analytic_account_id = line.employee_id.analytic_account_id.id

        # Procesar líneas de débito y crédito
        self._process_debit_line(line, slip, date, amount, debit_account_id, debit_third_id, analytic_account_id, line_ids)
        self._process_credit_line(line, slip, date, amount, credit_account_id, credit_third_id, analytic_account_id, line_ids)

    def _calculate_totals(self, line_ids):
        """Calcula los totales de débito y crédito de las líneas contables"""
        debit_sum = 0.0
        credit_sum = 0.0
        for line_id in line_ids:
            debit_sum += line_id['debit']
            credit_sum += line_id['credit']
        return debit_sum, credit_sum

    def _collect_move_lines(self, slip, date, precision, line_ids):
        """Recopila todas las líneas contables de una nómina"""
        for line in slip.line_ids.filtered(lambda line: line.category_id and line.salary_rule_id.not_computed_in_net == False):
            self._process_payslip_line(line, slip, date, precision, line_ids)
        
        # Calcular totales
        debit_sum, credit_sum = self._calculate_totals(line_ids)
        # Retornar analytic_account_id del último procesado (para ajustes)
        analytic_account_id = False
        if slip.line_ids:
            analytic_account_id = slip.line_ids[0].employee_id.analytic_account_id.id
        
        return line_ids, debit_sum, credit_sum, analytic_account_id

    def _apply_adjustment_line(self, slip, line_ids, debit_sum, credit_sum, date, analytic_account_id, precision):
        adjustment_entry_name = self._get_adjustment_entry_name(slip)

        if float_compare(credit_sum, debit_sum, precision_digits=precision) == -1:
            acc_id = slip.journal_id.default_account_id.id
            if not acc_id:
                raise UserError(
                    _('The Expense Journal "%s" has not properly configured the Credit Account!') % (
                        slip.journal_id.name))
            existing_adjustment_line = (
                line_id for line_id in line_ids if line_id['name'] == adjustment_entry_name
            )
            adjust_credit = next(existing_adjustment_line, False)

            if not adjust_credit:
                adjust_credit = {
                    'name': adjustment_entry_name,
                    'partner_id': slip.employee_id.work_contact_id.id,
                    'account_id': acc_id,
                    'journal_id': slip.journal_id.id,
                    'date': date,
                    'debit': 0.0,
                    'credit': debit_sum - credit_sum,
                    'analytic_distribution': (analytic_account_id and {analytic_account_id: 100})
                }
                line_ids.append(adjust_credit)
            else:
                adjust_credit['credit'] = debit_sum - credit_sum

        elif float_compare(debit_sum, credit_sum, precision_digits=precision) == -1:
            acc_id = slip.journal_id.default_account_id.id
            if not acc_id:
                raise UserError(
                    _('The Expense Journal "%s" has not properly configured the Debit Account!') % (
                        slip.journal_id.name))
            existing_adjustment_line = (
                line_id for line_id in line_ids if line_id['name'] == adjustment_entry_name
            )
            adjust_debit = next(existing_adjustment_line, False)

            if not adjust_debit:
                adjust_debit = {
                    'name': adjustment_entry_name,
                    'partner_id': slip.employee_id.work_contact_id.id,
                    'account_id': acc_id,
                    'journal_id': slip.journal_id.id,
                    'date': date,
                    'debit': credit_sum - debit_sum,
                    'credit': 0.0,
                    'analytic_distribution': (analytic_account_id and {analytic_account_id: 100})
                }
                line_ids.append(adjust_debit)
            else:
                adjust_debit['debit'] = credit_sum - debit_sum

        return line_ids

    def _link_payslip_lines(self, move):
        for move_line in move.line_ids:
            if move_line.payslip_line_id:
                move_line.payslip_line_id.accounting_line_ids = [(4, move_line.id)]

    # # Contabilización de la liquidación de nómina - se sobreescribe el metodo original
  
    def _action_create_account_move(self):
        # lavish - Obtener modalidad de contabilización
        settings_batch_account = self._get_batch_account_setting()
        by_employee = settings_batch_account == '1'
        is_batch = settings_batch_account == '0'
        precision = self.env['decimal.precision'].precision_get('Payroll')
        # Add payslip without run
        payslips_to_post = self#.filtered(lambda slip: not slip.payslip_run_id)
        payslips_to_post = payslips_to_post.filtered(lambda slip: slip.state == 'done' and not slip.move_id)
        # Check that a journal exists on all the structures
        if any(not payslip.struct_id for payslip in payslips_to_post):
            raise ValidationError(_('One of the contract for these payslips has no structure type.'))
        if any(not structure.journal_id for structure in payslips_to_post.mapped('struct_id')):
            raise ValidationError(_('One of the payroll structures has no account journal defined on it.'))
        slip_mapped_data = {
            slip.struct_id.journal_id.id: {fields.Date().end_of(slip.date_to, 'month'): self.env['hr.payslip']} for slip
            in payslips_to_post}
        for slip in payslips_to_post:
            slip_mapped_data[slip.struct_id.journal_id.id][fields.Date().end_of(slip.date_to, 'month')] |= slip
        for journal_id in slip_mapped_data:  # For each journal_id.
            for slip_date in slip_mapped_data[journal_id]:  # For each month.
                slips = slip_mapped_data[journal_id][slip_date]
                if not slips:
                    continue
                if by_employee:
                    for slip in slips:
                        if len(slip.line_ids) <= 0:
                            continue
                        date = self._get_move_date(slip)
                        move_dict = self._prepare_move_dict(slip, journal_id, date, by_employee=True)
                        self._append_move_narration(move_dict, slip)
                        line_ids, debit_sum, credit_sum, analytic_account_id = self._collect_move_lines(
                            slip, date, precision, []
                        )
                        line_ids = self._apply_adjustment_line(
                            slip, line_ids, debit_sum, credit_sum, date, analytic_account_id, precision
                        )
                        if not line_ids:
                            continue
                        move_dict['line_ids'] = [(0, 0, line_vals) for line_vals in line_ids]
                        move = self.env['account.move'].create(move_dict)
                        slip.write({'move_id': move.id, 'date': date})
                        self._link_payslip_lines(move)
                elif is_batch:
                    date = self._get_move_date(slips[0])
                    move_dict = self._prepare_move_dict(slips[0], journal_id, date, by_employee=False)
                    line_ids = []
                    debit_sum = 0.0
                    credit_sum = 0.0
                    analytic_account_id = False
                    for slip in slips:
                        if len(slip.line_ids) <= 0:
                            continue
                        self._append_move_narration(move_dict, slip)
                        line_ids, debit_sum, credit_sum, analytic_account_id = self._collect_move_lines(
                            slip, date, precision, line_ids
                        )
                        line_ids = self._apply_adjustment_line(
                            slip, line_ids, debit_sum, credit_sum, date, analytic_account_id, precision
                        )
                    if line_ids:
                        move_dict['line_ids'] = [(0, 0, line_vals) for line_vals in line_ids]
                        move = self.env['account.move'].create(move_dict)
                        for slip in slips:
                            slip.write({'move_id': move.id, 'date': date})
                        self._link_payslip_lines(move)
        return True

