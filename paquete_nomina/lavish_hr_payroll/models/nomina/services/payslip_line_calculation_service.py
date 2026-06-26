# -*- coding: utf-8 -*-
"""
Servicio de Cálculo de Líneas de Nómina
=======================================

Gestiona la creación y cálculo de líneas de nómina (hr.payslip.line).
Incluye:
- Líneas de préstamos
- Líneas de conceptos de contrato
- Líneas de novedades
- Líneas de ausencias
- Procesamiento de reglas salariales
"""

import json

from odoo.exceptions import UserError
from odoo import _

from odoo.addons.lavish_hr_employee.models.payroll.hr_payslip_constants import json_serial
from odoo.addons.lavish_hr_employee.models.payroll.hr_slip_data_structures import (
    CategoryCollection,
    CategoryData,
    RulesCollection,
    RuleData
)

class PayslipLineCalculationService:
    """
    Servicio para calcular y crear líneas de nómina.
    Extrae la lógica de creación de líneas de hr.payslip.
    """

    def __init__(self, payslip):
        """
        Args:
            payslip: hr.payslip record
        """
        self.payslip = payslip
        self.env = payslip.env
        self.employee_id = payslip.employee_id.id
        self.contract_id = payslip.contract_id.id
        self.struct_process = payslip.struct_id.process if payslip.struct_id else 'nomina'

    # =========================================================================
    # LÍNEAS DE PRÉSTAMOS
    # =========================================================================

    def create_loan_line(self, localdict, installment, result):
        """
        Crea una línea para una cuota de préstamo.

        Args:
            localdict: Diccionario local de contexto
            installment: hr.loan.installment record
            result: Diccionario de resultados

        Returns:
            tuple: (localdict, result) actualizados
        """
        line_code = f'LOAN-{installment.loan_id.id}-{installment.sequence}'

        loan = installment.loan_id
        amount = -abs(installment.amount)

        description = f"Cuota {installment.sequence}/{len(loan.installment_ids)} -[{loan.category_id.code}] {loan.category_id.name}"
        if len(localdict['slip'].loan_installment_ids) > 1:
            description += f" ({installment.date})"

        rule = loan.category_id.salary_rule_id
        if not rule:
            return localdict, result

        localdict[line_code] = amount

        localdict = self.sum_salary_rule_category(
            localdict,
            rule.category_id,
            amount,
            rule_code=rule.code
        )
        localdict = self.sum_salary_rule(localdict, rule, amount)

        computation_data = {
            'tipo': 'prestamo',
            'prestamo': {
                'id': loan.id,
                'nombre': loan.name,
                'categoria': loan.category_id.name if loan.category_id else '',
                'categoria_code': loan.category_id.code if loan.category_id else '',
                'monto_original': loan.amount or 0,
                'saldo': loan.balance_amount or 0,
                'entidad': loan.entity_id.name if loan.entity_id else '',
            },
            'cuota': {
                'numero': installment.sequence,
                'total_cuotas': len(loan.installment_ids),
                'monto': abs(installment.amount),
                'fecha': str(installment.date) if installment.date else '',
            },
            'formula': f"Cuota {installment.sequence} de {len(loan.installment_ids)}",
            'steps': [
                {'label': 'Monto Original Préstamo', 'value': loan.amount or 0, 'format': 'currency'},
                {'label': 'Cuota Actual', 'value': abs(installment.amount), 'format': 'currency'},
                {'label': 'Saldo Pendiente', 'value': loan.balance_amount or 0, 'format': 'currency'},
                {'label': 'Descuento en Nómina', 'value': round(amount), 'format': 'currency', 'highlight': True},
            ]
        }

        result[line_code] = {
            'sequence': rule.sequence,
            'code': rule.code,
            'name': description,
            'salary_rule_id': rule.id,
            'contract_id': localdict['contract'].id,
            'employee_id': localdict['employee'].id,
            'entity_id': loan.entity_id.id,
            'loan_id': loan.id,
            'amount': amount,
            'quantity': 1.00,
            'rate': 100,
            'total': round(amount),
            'slip_id': self.payslip.id,
            'is_previous_period': False,
            'computation': json.dumps(computation_data, default=json_serial),
        }

        return localdict, result

    # =========================================================================
    # LÍNEAS DE CONCEPTOS DE CONTRATO
    # =========================================================================

    def create_concept_line(self, localdict, concept, amount, data, description, result):
        """
        Crea una línea de concepto de contrato.

        Args:
            localdict: Diccionario local de contexto
            concept: hr.contract.concepts record
            amount: Monto calculado
            data: Datos adicionales del cálculo
            description: Descripción de la línea
            result: Diccionario de resultados

        Returns:
            tuple: (localdict, result) actualizados
        """
        line_code = concept.input_id.code + '-PCD' + str(concept.id)

        previous_amount = localdict.get(concept.input_id.code, 0.0)

        localdict[line_code] = amount

        localdict = self.sum_salary_rule_category(
            localdict,
            concept.input_id.category_id,
            amount - previous_amount,
            rule_code=concept.input_id.code
        )
        localdict = self.sum_salary_rule(localdict, concept.input_id, amount, 1.0, 100.0)

        es_deduccion = concept.input_id.category_id.code in ['DED', 'DEDUCCION', 'DEDUCCIONES'] if concept.input_id.category_id else False

        computation_data = {
            'tipo': 'concepto_contrato',
            'concepto': {
                'id': concept.id,
                'descripcion': description or '',
                'regla': concept.input_id.name if concept.input_id else '',
                'regla_code': concept.input_id.code if concept.input_id else '',
                'categoria': concept.input_id.category_id.name if concept.input_id and concept.input_id.category_id else '',
                'entidad': concept.partner_id.name if concept.partner_id else '',
                'prestamo_id': concept.loan_id.id if concept.loan_id else None,
            },
            'formula': f"Monto = ${amount:,.0f}" if amount else 'Monto = $0',
            'explanation': 'Deducción de Contrato' if es_deduccion else 'Devengo de Contrato',
            'steps': [
                {'label': 'Monto Concepto', 'value': amount, 'format': 'currency'},
                {'label': 'Cantidad', 'value': 1.0, 'format': 'number'},
                {'label': 'Porcentaje', 'value': 100, 'format': 'percent'},
                {'label': 'Total', 'value': round(amount), 'format': 'currency', 'highlight': True},
            ],
            'indicators': [
                {'label': 'Tipo', 'value': 'Deducción' if es_deduccion else 'Devengo', 'color': 'danger' if es_deduccion else 'success'},
                {'label': 'Origen', 'value': 'Contrato', 'color': 'primary'},
            ]
        }

        result[line_code] = {
            'sequence': concept.input_id.sequence,
            'code': concept.input_id.code,
            'name': description,
            'salary_rule_id': concept.input_id.id,
            'contract_id': localdict['contract'].id,
            'employee_id': localdict['employee'].id,
            'entity_id': concept.partner_id.id,
            'loan_id': concept.loan_id.id,
            'concept_id': concept.id,
            'amount': amount,
            'quantity': 1.00,
            'rate': 100,
            'log_compute': data.get('detail_html', ''),
            'total': round(amount),
            'slip_id': self.payslip.id,
            'computation': json.dumps(computation_data, default=json_serial),
        }

        return localdict, result

    # =========================================================================
    # LÍNEAS DE NOVEDADES
    # =========================================================================

    def create_novelty_line(self, localdict, concepts, result):
        """
        Crea una línea de novedad.

        Args:
            localdict: Diccionario local de contexto
            concepts: hr.novelties.different.concepts record
            result: Diccionario de resultados

        Returns:
            tuple: (localdict, result) actualizados
        """
        previous_amount = localdict.get(concepts.salary_rule_id.code, 0.0)
        tot_rule = self.payslip._get_payslip_line_total(concepts.amount, 1, 100, concepts.salary_rule_id)

        localdict[concepts.salary_rule_id.code + '-PCD'] = tot_rule

        localdict = self.sum_salary_rule_category(
            localdict,
            concepts.salary_rule_id.category_id,
            tot_rule - previous_amount,
            rule_code=concepts.salary_rule_id.code
        )
        localdict = self.sum_salary_rule(localdict, concepts.salary_rule_id, tot_rule, 1.0, 100.0)

        es_deduccion = concepts.salary_rule_id.category_id.code in ['DED', 'DEDUCCION', 'DEDUCCIONES'] if concepts.salary_rule_id.category_id else False

        computation_data = {
            'tipo': 'novedad',
            'novedad': {
                'id': concepts.id,
                'descripcion': concepts.description or concepts.name or '',
                'fecha': str(concepts.date) if concepts.date else '',
                'estado': concepts.state or '',
                'regla': concepts.salary_rule_id.name if concepts.salary_rule_id else '',
                'regla_code': concepts.salary_rule_id.code if concepts.salary_rule_id else '',
                'categoria': concepts.salary_rule_id.category_id.name if concepts.salary_rule_id and concepts.salary_rule_id.category_id else '',
                'entidad': concepts.partner_id.name if concepts.partner_id else '',
            },
            'formula': f"Monto = ${concepts.amount:,.0f}" if concepts.amount else 'Monto = $0',
            'explanation': 'Deducción' if es_deduccion else 'Devengo',
            'steps': [
                {'label': 'Monto Novedad', 'value': concepts.amount, 'format': 'currency'},
                {'label': 'Cantidad', 'value': 1.0, 'format': 'number'},
                {'label': 'Porcentaje', 'value': 100, 'format': 'percent'},
                {'label': 'Total', 'value': tot_rule, 'format': 'currency', 'highlight': True},
            ],
            'indicators': [
                {'label': 'Tipo', 'value': 'Deducción' if es_deduccion else 'Devengo', 'color': 'danger' if es_deduccion else 'success'},
            ]
        }

        result_item = concepts.salary_rule_id.code + '-PCD' + str(concepts.id)
        result[result_item] = {
            'sequence': concepts.salary_rule_id.sequence,
            'code': concepts.salary_rule_id.code,
            'name': concepts.description or concepts.salary_rule_id.name,
            'salary_rule_id': concepts.salary_rule_id.id,
            'contract_id': localdict['contract'].id,
            'employee_id': localdict['employee'].id,
            'entity_id': concepts.partner_id.id if concepts.partner_id else False,
            'amount': tot_rule,
            'quantity': 1.0,
            'rate': 100,
            'total': tot_rule,
            'slip_id': self.payslip.id,
            'computation': json.dumps(computation_data, default=json_serial),
        }

        return localdict, result

    # =========================================================================
    # GESTIÓN DE LOCALDICT
    # =========================================================================

    def sum_salary_rule_category(self, localdict, category, amount, rule_code=None, line_id=None):
        """
        Suma recursivamente el monto en la categoría y sus padres.
        Usa estructura NATIVA Odoo 18 con tracking de líneas y reglas.

        Args:
            localdict: Diccionario local de contexto
            category: Objeto hr.salary.rule.category
            amount: Monto a sumar
            rule_code: Código de la regla que contribuye (opcional)
            line_id: ID de la línea de nómina (opcional)

        Returns:
            dict: localdict actualizado
        """
        if category.parent_id:
            localdict = self.sum_salary_rule_category(localdict, category.parent_id, amount, rule_code, line_id)

        categories = localdict['categories']
        cat_data = categories.get(category.code)

        if not cat_data:
            cat_data = CategoryData(code=category.code)
            categories.add_category(cat_data)

        cat_data.add_value(amount=amount, rule_code=rule_code)

        if rule_code and rule_code not in cat_data.rule_codes:
            cat_data.rule_codes.append(rule_code)

        if line_id and line_id not in cat_data.line_ids:
            cat_data.line_ids.append(line_id)

        return localdict

    def sum_salary_rule(self, localdict, rule, amount, quantity=1.0, rate=100.0,
                        has_leave=False, leave_id=0, leave_novelty='', leave_liquidacion_value=''):
        """
        Actualiza la suma de reglas usando RulesCollection (Odoo 18).
        Usa RuleData objects que son tipo-seguros y se acumulan automáticamente.

        Args:
            localdict: Diccionario local de contexto
            rule: hr.salary.rule record
            amount: Monto a sumar
            quantity: Cantidad
            rate: Tasa/porcentaje
            has_leave: Si tiene ausencia asociada
            leave_id: ID de ausencia
            leave_novelty: Tipo de novedad de ausencia
            leave_liquidacion_value: Valor de liquidación de ausencia

        Returns:
            dict: localdict actualizado
        """
        rules = localdict['rules']
        existing_rule = rules.get(rule.code)

        if existing_rule:
            leave_id = leave_id or existing_rule.leave_id
            leave_novelty = leave_novelty or existing_rule.leave_novelty
            leave_liquidacion_value = leave_liquidacion_value or existing_rule.leave_liquidacion_value

        rule_data = RuleData(
            code=rule.code,
            total=amount,
            amount=amount,
            quantity=quantity,
            rate=rate,
            category_id=rule.category_id.id if rule.category_id else 0,
            category_code=rule.category_id.code if rule.category_id else '',
            rule_id=rule.id,
            rule=rule,
            has_leave=has_leave or (existing_rule.has_leave if existing_rule else False),
            leave_id=leave_id,
            leave_novelty=leave_novelty,
            leave_liquidacion_value=leave_liquidacion_value,
            payslip_id=self.payslip.id,
        )

        rules.add_rule(rule_data)

        return localdict

    def convert_localdict_to_collections(self, localdict):
        """
        Convierte localdict['categories'] y localdict['rules'] a objetos tipo-seguros.
        Método de migración desde estructuras legacy (diccionarios) a Collections.

        Args:
            localdict: Diccionario local de contexto

        Returns:
            None (modifica localdict in-place)
        """
        categories_dict = localdict.get('categories', {})

        if not isinstance(categories_dict, CategoryCollection):
            categories_collection = CategoryCollection()
            for code, data in categories_dict.items():
                if isinstance(data, dict):
                    cat_data = CategoryData(
                        code=code,
                        total=data.get('total', 0.0),
                        quantity=data.get('quantity', 0.0),
                        rule_codes=data.get('rule_codes', data.get('source_rules', [])),
                        line_ids=data.get('line_ids', [])
                    )
                    categories_collection.add_category(cat_data)
            localdict['categories'] = categories_collection

        rules_dict = localdict.get('rules', {})
        if not isinstance(rules_dict, RulesCollection):
            rules_collection = RulesCollection()
            for code, data in rules_dict.items():
                if isinstance(data, dict):
                    rule_data = RuleData(
                        code=code,
                        amount=data.get('amount', 0.0),
                        total=data.get('total', 0.0),
                        quantity=data.get('quantity', 1.0),
                        rate=data.get('rate', 100.0),
                        rule_id=data.get('id', data.get('rule_id', 0)),
                        has_leave=data.get('has_leave', False),
                        leave_id=data.get('leave_id', 0),
                        leave_novelty=data.get('leave_novelty', ''),
                        leave_liquidacion_value=data.get('leave_liquidacion_value', ''),
                        extra_data=data.get('extra_data', {})
                    )
                    rules_collection.add_rule(rule_data)
            localdict['rules'] = rules_collection

    # =========================================================================
    # VALIDACIONES
    # =========================================================================

    def should_process_novelty(self, novelty, payslip):
        """
        Determina si una novedad debe ser procesada según estructuras y condiciones.

        Args:
            novelty: hr.novelties.different.concepts record
            payslip: hr.payslip record

        Returns:
            bool: True si debe procesarse
        """
        if not novelty.salary_structure_ids:
            return payslip.struct_process in ['nomina', 'contrato']
        return payslip.struct_id.id in novelty.salary_structure_ids.ids

    def concept_already_computed(self, payslip, concept, rule):
        """
        Verifica si un concepto ya fue liquidado en otra nómina del mismo período.

        ANTI-DUPLICACION: Evita doble cómputo cuando:
        - Se liquidan vacaciones y luego nómina quincenal
        - Se liquida nómina quincenal y luego liquidación de contrato
        - Cualquier combinación de nóminas en el mismo mes

        Args:
            payslip: hr.payslip record
            concept: hr.contract.concepts record
            rule: hr.salary.rule record

        Returns:
            bool: True si ya fue computado (saltar), False si debe procesarse
        """
        from calendar import monthrange

        year = payslip.date_from.year
        month = payslip.date_from.month

        first_day = payslip.date_from.replace(day=1)
        last_day_num = monthrange(year, month)[1]
        last_day = payslip.date_from.replace(day=last_day_num)

        other_payslips = self.env['hr.payslip'].search([
            ('employee_id', '=', payslip.employee_id.id),
            ('id', '!=', payslip.id),
            ('date_from', '>=', first_day),
            ('date_to', '<=', last_day),
            ('state', 'not in', ['draft', 'cancel']),
        ])

        if not other_payslips:
            return False

        for other_slip in other_payslips:
            existing_line = self.env['hr.payslip.line'].search([
                ('slip_id', '=', other_slip.id),
                ('salary_rule_id', '=', rule.id),
                ('concept_id', '=', concept.id),
            ], limit=1)

            if existing_line:
                return True

        return False

    # =========================================================================
    # LÍNEAS DE AUSENCIAS
    # =========================================================================

    def create_leave_line(self, localdict, concept, tot_rule, result):
        """
        Crea una línea de ausencia (licencia, vacación, incapacidad).

        Args:
            localdict: Diccionario local de contexto
            concept: Diccionario con datos de la ausencia
            tot_rule: Total calculado de la regla
            result: Diccionario de resultados

        Returns:
            tuple: (localdict, result) actualizados
        """
        from datetime import timedelta
        from decimal import Decimal, ROUND_HALF_UP

        input_code = concept['input_id'].code
        previous_amount = localdict.get(input_code, 0.0)
        tot_rule = tot_rule * (1 if concept['input_id'].dev_or_ded == 'devengo' else -1)
        leave = concept['leave_id']
        leave_key = f"{input_code}-PCD{leave.id}"
        localdict[leave_key] = tot_rule

        rule = concept['input_id']
        days = concept['days']
        contract = localdict['contract']
        employee = localdict['employee']
        amount_per_day = tot_rule / days if days else 0

        # Fechas REALES de la ausencia (del leave, no del período)
        leave_date_from = leave.date_from.date()
        leave_date_to = leave.date_to.date()
        # Fecha de regreso = día siguiente al fin de la ausencia
        leave_return_date = leave_date_to + timedelta(days=1) if leave_date_to else None

        # Determinar tipo de vacación
        is_money_vacation = input_code == 'VACATIONS_MONEY' or (
            leave.holiday_status_id.is_vacation_money if leave.holiday_status_id else False
        )
        vacation_type = 'money' if is_money_vacation else 'enjoy'
        localdict[f"vacation_type-PCD{leave.id}"] = vacation_type

        # Actualizar categorías y reglas
        localdict = self.sum_salary_rule_category(
            localdict,
            rule.category_id,
            tot_rule - previous_amount,
            rule_code=rule.code
        )

        leave_type = leave.holiday_status_id
        localdict = self.sum_salary_rule(
            localdict,
            rule,
            tot_rule,
            days,
            100,
            has_leave=True,
            leave_id=leave.id,
            leave_novelty=leave_type.novelty if leave_type else '',
            leave_liquidacion_value=leave_type.liquidacion_value if leave_type else ''
        )

        # Construir computation_data
        is_paid = not leave_type.unpaid_absences if leave_type else True
        novelty_type = leave_type.novelty if leave_type else ''
        additional_novelties = concept.get('additional_novelties', [])
        is_incapacity_with_variation = novelty_type in ['ige', 'irl'] and len(additional_novelties) > 0

        if is_incapacity_with_variation:
            steps = self._build_incapacity_steps(additional_novelties, days, tot_rule)
            formula = "IBC/30 × Días × %Reconocimiento"
            explanation = f"Incapacidad {novelty_type.upper()} con variación de porcentaje por días"
        else:
            steps = [
                {'label': 'Valor Diario', 'value': amount_per_day, 'format': 'currency'},
                {'label': 'Días de Trabajo', 'value': concept['days_work'], 'format': 'number'},
                {'label': 'Días Festivos', 'value': concept['days_holiday'], 'format': 'number'},
                {'label': 'Total Días', 'value': days, 'format': 'number'},
                {'label': 'Total', 'value': round(tot_rule), 'format': 'currency', 'highlight': True},
            ]
            formula = "Valor Diario × Días = Total"
            explanation = f"{'Licencia Remunerada' if is_paid else 'Ausencia No Pagada'} - {leave_type.name if leave_type else ''}"

        computation_data = {
            'tipo': 'ausencia',
            'ausencia': {
                'id': leave.id,
                'nombre': leave.name,
                'tipo_ausencia': leave_type.name if leave_type else '',
                'tipo_code': leave_type.code if leave_type else '',
                'novelty': novelty_type,
                # Fechas REALES de la ausencia completa
                'fecha_inicio_ausencia': str(leave_date_from) if leave_date_from else '',
                'fecha_fin_ausencia': str(leave_date_to) if leave_date_to else '',
                'fecha_regreso': str(leave_return_date) if leave_return_date else '',
                # Fechas del PERÍODO liquidado en esta nómina
                'fecha_inicio_periodo': str(concept['date_from']) if concept['date_from'] else '',
                'fecha_fin_periodo': str(concept['date_to']) if concept['date_to'] else '',
                'es_pagada': is_paid,
                'es_vacacion': leave_type.is_vacation if leave_type else False,
                'entidad': leave.entity.name if leave.entity else '',
            },
            'dias': {
                'total': days,
                'trabajo': concept['days_work'],
                'festivos': concept['days_holiday'],
                'dia_31': concept['days_31'],
                'festivo_31': concept['days_holiday_31'],
            },
            'formula': formula,
            'explanation': explanation,
            'steps': steps,
            'indicators': [
                {'label': 'Estado', 'value': 'Pagada' if is_paid else 'No Pagada', 'color': 'success' if is_paid else 'warning'},
                {'label': 'Tipo', 'value': novelty_type.upper() if novelty_type else 'LICENCIA', 'color': 'primary'},
            ]
        }

        if is_incapacity_with_variation:
            computation_data['lineas_detalle'] = [
                {
                    'fecha': str(nov.get('date', '')),
                    'secuencia': nov.get('sequence', 0),
                    'rate': nov.get('rate_applied', 100),
                    'monto': nov.get('amount', 0),
                    'ibc_day': nov.get('ibc_day', 0),
                }
                for nov in additional_novelties
            ]

        result[leave_key] = {
            'sequence': rule.sequence,
            'code': rule.code,
            'name': rule.name,
            'salary_rule_id': rule.id,
            'contract_id': contract.id,
            'employee_id': employee.id,
            'entity_id': concept['partner_id'],
            'loan_id': concept['loan_id'],
            'amount': amount_per_day,
            'quantity': days,
            'rate': 100,
            'total': round(tot_rule),
            'slip_id': self.payslip.id,
            'leave_id': leave.id,
            # Fechas REALES de la ausencia completa (no del período)
            'initial_accrual_date': leave_date_from,
            'final_accrual_date': leave_date_to,
            # Fecha salida y regreso
            'date_out': leave_date_from,
            'date_in': leave_return_date,
            # Días por tipo
            'business_units': concept['days_work'],
            'holiday_units': concept['days_holiday'],
            'business_31_units': concept['days_31'],
            'holiday_31_units': concept['days_holiday_31'],
            # Período liquidado en esta nómina (para referencia)
            'period_start': concept['date_from'],
            'period_end': concept['date_to'],
            'computation': json.dumps(computation_data, default=json_serial),
        }

        # Procesar vacaciones si aplica
        if leave_type and (leave_type.is_vacation or leave_type.is_vacation_money):
            self._process_vacation_accrual(
                localdict, result, leave_key, concept, leave, employee, contract,
                days, amount_per_day, is_money_vacation
            )

        return localdict, result

    def _build_incapacity_steps(self, additional_novelties, days, tot_rule):
        """Construye pasos detallados para incapacidades con variación de porcentaje."""
        rates_summary = {}
        for nov in additional_novelties:
            rate = nov.get('rate_applied', 100)
            rate_key = str(rate)
            if rate_key not in rates_summary:
                rates_summary[rate_key] = {'dias': 0, 'monto': 0, 'rate': rate}
            rates_summary[rate_key]['dias'] += nov.get('days', 0) or nov.get('days_work', 0) or 1
            rates_summary[rate_key]['monto'] += nov.get('amount', 0)

        steps = []
        ibc_base = additional_novelties[0].get('ibc_base', 0) if additional_novelties else 0
        ibc_day = additional_novelties[0].get('ibc_day', 0) if additional_novelties else 0

        if ibc_base:
            steps.append({'label': 'Base Mensual (IBC)', 'value': ibc_base, 'format': 'currency'})
        if ibc_day:
            steps.append({'label': 'Valor Diario (IBC/30)', 'value': ibc_day, 'format': 'currency'})

        for rate_key, rate_data in sorted(rates_summary.items(), key=lambda x: float(x[0]), reverse=True):
            rate_label = f"Días al {rate_data['rate']:.0f}%"
            steps.append({
                'label': rate_label,
                'value': f"{rate_data['dias']} días = ${rate_data['monto']:,.0f}",
                'format': 'text'
            })

        steps.append({'label': 'Total Días', 'value': days, 'format': 'number'})
        steps.append({'label': 'Total', 'value': round(tot_rule), 'format': 'currency', 'highlight': True})

        return steps

    def _process_vacation_accrual(self, localdict, result, leave_key, concept, leave, employee, contract, days, amount_per_day, is_money_vacation):
        """Procesa y calcula datos de causación de vacaciones."""
        from datetime import timedelta
        from decimal import Decimal, ROUND_HALF_UP

        Vac = self.env['hr.vacation']

        if '_vacation_accrual_dates' not in localdict:
            localdict['_vacation_accrual_dates'] = {}

        employee_id = employee.id

        if employee_id in localdict['_vacation_accrual_dates']:
            start = localdict['_vacation_accrual_dates'][employee_id] + timedelta(days=1)
        else:
            last = Vac.search(
                [('employee_id', '=', employee.id)],
                order='final_accrual_date desc', limit=1
            )
            if last and last.final_accrual_date:
                start = last.final_accrual_date
                if start < contract.date_start:
                    start = contract.date_start
            else:
                start = contract.date_start

        # Calcular ausencias no pagadas
        domain = [
            ('state', '=', 'validate'),
            ('employee_id', '=', employee.id),
            ('unpaid_absences', '=', True),
            ('date_from', '>=', start),
            ('date_to', '<=', self.payslip.date_to),
        ]
        dias_aus = sum(l.number_of_days_in_payslip for l in self.env['hr.leave'].search(domain))
        dias_aus += sum(h.days for h in self.env['hr.absence.history'].search([
            ('employee_id', '=', employee.id),
            ('leave_type_id.unpaid_absences', '=', True),
            ('star_date', '>=', start),
            ('end_date', '<=', self.payslip.date_to),
        ]))

        dias_hab = concept['days_work']
        dias_fest = concept['days_holiday']
        dias_31_hab = concept['days_31']
        dias_31_fest = concept['days_holiday_31']

        dias_equiv = ((Decimal(dias_hab) + Decimal(dias_31_hab)) * Decimal(365)) / Decimal(15)
        dias_equiv = int(dias_equiv.quantize(0, rounding=ROUND_HALF_UP))

        if not start:
            start = contract.date_start

        end = start + timedelta(days=(dias_equiv + dias_aus) + 1)
        localdict['_vacation_accrual_dates'][employee_id] = end

        disp = self.payslip.get_holiday_book(contract, start)['days_left']
        dias_rest = max(disp - dias_hab, 0)

        vacation_log_data = {
            'tipo_vacaciones': 'En Dinero' if is_money_vacation else 'Disfrute',
            'inicio_causacion': start.strftime("%d/%m/%Y"),
            'fin_causacion': end.strftime("%d/%m/%Y"),
            'dias_habiles': dias_hab,
            'dias_festivos': dias_fest,
            'dias_31_habiles': dias_31_hab,
            'dias_31_festivos': dias_31_fest,
            'equivalente_calendario': dias_equiv + dias_aus,
            'ausencias_no_pagadas': dias_aus,
            'disponibles_antes': disp,
            'restantes': dias_rest,
        }

        vacation_info = {
            'start_date': start,
            'end_date': end,
            'business_days': dias_hab,
            'holiday_days': dias_fest,
            'equivalent_days': dias_equiv,
            'unpaid_absences': dias_aus,
            'available_days': disp,
            'remaining_days': dias_rest,
            'base_value': amount_per_day * 30
        }
        localdict[f"vacation_info-PCD{leave.id}"] = vacation_info

        vacation_values = {
            'amount_base': amount_per_day * 30,
            'object_type': 'vacation',
            'vacation_leave_id': leave.id,
            'vacation_departure_date': concept['date_from'],
            'vacation_return_date': concept['date_to'],
            'initial_accrual_date': start,
            'final_accrual_date': end,
            'business_units': dias_hab,
            'holiday_units': dias_fest,
            'business_31_units': dias_31_hab,
            'holiday_31_units': dias_31_fest,
            'days_count': days,
            'log_compute': json.dumps(vacation_log_data, default=json_serial),
        }

        result[leave_key].update(vacation_values)

    # =========================================================================
    # PREPARACIÓN DE RESULTADOS DE REGLAS
    # =========================================================================

    def prepare_rule_result(self, rule, localdict, amount, qty, rate, name, log, data, override_total=None):
        """
        Prepara el diccionario de resultado para una línea de nómina.

        Args:
            rule: hr.salary.rule record
            localdict: Diccionario local de contexto
            amount: Monto calculado
            qty: Cantidad
            rate: Tasa/porcentaje
            name: Nombre de la línea
            log: Log de cálculo
            data: Datos adicionales del cálculo
            override_total: Total con override aplicado (opcional, de _process_rules)

        Returns:
            dict: Diccionario con datos de la línea
        """
        # Usar override_total si se proporciona (ya tiene el override aplicado desde _process_rules)
        if override_total is not None:
            tot_rule = override_total
        else:
            tot_rule = self.payslip._get_payslip_line_total(amount, qty, rate, rule)

        result = {
            'sequence': rule.sequence,
            'code': rule.code,
            'name': name or rule.name,
            'salary_rule_id': rule.id,
            'contract_id': localdict['contract'].id,
            'employee_id': localdict['employee'].id,
            'entity_id': False,
            'amount': amount,
            'quantity': qty,
            'rate': rate,
            'total': tot_rule,
            'slip_id': self.payslip.id,
            'run_id': self.payslip.payslip_run_id.id if self.payslip.payslip_run_id else False,
        }

        # Asignar entidad según categoría
        if rule.category_id.code == 'SSOCIAL':
            result['entity_id'] = self._get_social_security_entity(localdict['employee'], rule.code)

        # Procesar según tipo de regla
        category_code = rule.category_id.code if rule.category_id else ''
        # Determinar si hay un override activo (si se pasó override_total)
        has_override = override_total is not None

        if category_code == 'PROV':
            self._process_provision_result(result, amount, qty, rate, data)
        elif rule.code in ('CESANTIAS', 'PRIMA', 'INTCESANTIAS', 'INTCES_YEAR', 'CES_YEAR', 'VACCONTRATO'):
            self._process_prestacion_result(result, data, has_override=has_override)
        elif rule.code in ('BASIC', 'BASIC002', 'BASIC003', 'BASIC004', 'BASIC005'):
            self._process_basic_result(result, data)
        elif rule.code == 'AUX000':
            self._process_aux_result(result, data)
        elif rule.code == 'IBD':
            self._process_ibd_result(result, data)
        elif rule.code in ('SSOCIAL001', 'SSOCIAL002', 'SSOCIAL003', 'SSOCIAL004'):
            self._process_ssocial_result(result, data)
        elif rule.code == 'RT_MET_01':
            self._process_retencion_result(result, data, log)
        elif data and isinstance(data, dict) and 'computation' not in result:
            result['computation'] = json.dumps(data, default=json_serial)

        if log:
            result['log_compute'] = log

        return result

    def _get_social_security_entity(self, employee, rule_code):
        """Obtiene la entidad de seguridad social según la regla."""
        entity_mapping = {
            'SSOCIAL001': 'eps',
            'SSOCIAL002': 'pension',
            'SSOCIAL003': 'subsistencia',
            'SSOCIAL004': 'solidaridad',
        }
        target_type = entity_mapping.get(rule_code)

        for entity in employee.social_security_entities:
            if entity.contrib_id.type_entities == target_type:
                return entity.partner_id.id
            # Casos especiales de pensión
            if rule_code in ('SSOCIAL003', 'SSOCIAL004') and entity.contrib_id.type_entities == 'pension':
                return entity.partner_id.id

        return False

    def _process_provision_result(self, result, amount, qty, rate, data):
        """Procesa resultado para provisiones."""

        if data and isinstance(data, dict):
            if 'prov_line_ids' in data:
                result['accounting_line_ids'] = [(6, 0, data['prov_line_ids'])]
            if 'acum_line_ids' in data:
                result['accumulated_line_ids'] = [(6, 0, data['acum_line_ids'])]
            if 'source_rule_ids' in data and data['source_rule_ids']:
                result['source_rule_ids'] = [(6, 0, data['source_rule_ids'])]

            data_kpi = data.get('data_kpi', {})
            if data_kpi:
                result['calculation_method'] = 'consolidado' if data_kpi.get('compute_average') else 'simple'
                result['discount_suspensions'] = data_kpi.get('descontar_suspensiones', False)

            if 'fecha_inicio' in data:
                result['period_start'] = data['fecha_inicio']
            if 'fecha_fin' in data:
                result['period_end'] = data['fecha_fin']

            # Base y dias liquidados (compartido con prestaciones)
            base_mensual = data.get('base_mensual', 0)
            if not base_mensual and data_kpi:
                base_mensual = data_kpi.get('base_mensual', 0)
            if base_mensual:
                result['amount_base'] = round(base_mensual, 2)

            dias_liq = data.get('dias_liquidados', 0)
            if dias_liq:
                result['dias_liquidados'] = round(float(dias_liq), 4)

            # Serializar data dict completo al campo computation para el widget JS
            result['computation'] = json.dumps(data, default=json_serial)

    def _process_prestacion_result(self, result, data, has_override=False):
        """
        Procesa resultado para prestaciones sociales.

        Popula campos de la linea: amount_base, dias_liquidados,
        days_unpaid_absences, fechas de causacion, computation.

        Args:
            result: dict - resultado de la línea
            data: dict - datos de la prestación
            has_override: bool - si hay un override activo, NO sobrescribir el total
        """
        if not data or not isinstance(data, dict):
            return

        # Base mensual: directo de data (nuevo _build_calculo) o legacy data_kpi
        base_mensual = data.get('base_mensual', 0)
        if not base_mensual:
            data_kpi = data.get('data_kpi', {})
            base_mensual = data_kpi.get('base_mensual', 0)

        # Dias liquidados: dias trabajados en el periodo (de data extras)
        dias_liquidados = data.get('dias_liquidados', 0) or data.get('dias_a_pagar', 0)

        # Dias ausencias no pagadas: de sueldo_info o legacy data_kpi
        days_no_pay = 0
        sueldo_info = data.get('sueldo_info')
        if isinstance(sueldo_info, dict):
            days_no_pay = sueldo_info.get('days_no_pay', 0) or 0
        if not days_no_pay:
            data_kpi = data.get('data_kpi', {})
            days_no_pay = data_kpi.get('days_no_pay', 0) or 0

        update_dict = {
            'amount_base': round(base_mensual, 2),
            'dias_liquidados': round(float(dias_liquidados), 4),
            'days_unpaid_absences': round(days_no_pay),
            'initial_accrual_date': data.get('fecha_inicio'),
            'final_accrual_date': data.get('fecha_fin'),
            'computation': json.dumps(data, default=json_serial),
        }
        result.update(update_dict)

    def _process_basic_result(self, result, data):
        """Procesa resultado para salario básico."""
        if data and isinstance(data, dict):
            result['computation'] = json.dumps(data, default=json_serial)

    def _process_aux_result(self, result, data):
        """Procesa resultado para auxilio de transporte."""
        if data and isinstance(data, dict):
            result['computation'] = json.dumps(data, default=json_serial)

    def _process_ibd_result(self, result, data):
        """Procesa resultado para IBD."""
        if data and isinstance(data, dict):
            result['computation'] = json.dumps(data, default=json_serial)
            if 'acum_line_ids' in data:
                result['accumulated_line_ids'] = [(6, 0, data['acum_line_ids'])]

    def _process_ssocial_result(self, result, data):
        """Procesa resultado para seguridad social."""
        if data and isinstance(data, dict):
            result['computation'] = json.dumps(data, default=json_serial)

    def _process_retencion_result(self, result, data, log):
        """Procesa resultado para retención en la fuente."""
        if not data:
            return

        first_item = data[0] if isinstance(data, list) and len(data) > 0 else (data if isinstance(data, dict) else {})
        amount_base = 0

        if first_item:
            if not first_item.get('es_proyectado', False):
                amount_base = first_item.get('subtotal_ibr3', 0)
            else:
                otro_valor = first_item.get('otro_valor', 0) or 0
                amount_base = otro_valor / 2

        result.update({
            'amount_base': amount_base,
            'computation': json.dumps(data, default=json_serial),
        })

        self.payslip.resulados_rt = log
