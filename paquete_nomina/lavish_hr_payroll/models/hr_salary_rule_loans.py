# -*- coding: utf-8 -*-
"""
MÓDULO: Extensión de Reglas Salariales para Préstamos
DESCRIPCIÓN: Contiene la lógica de cálculo de descuentos de préstamos en nómina
BASADO EN: hr_loans.py métodos _get_loan_lines() y get_loan_interests()

Este archivo extiende hr.salary.rule para agregar métodos específicos
de cálculo de préstamos que pueden ser llamados desde reglas salariales
con amount_select='concept'

AUTOR: Sistema GROUPCDM-1
FECHA: 2025
"""

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging
from odoo.addons.lavish_hr_payroll.models.services.prestamos import PrestamoService

_logger = logging.getLogger(__name__)


class HrSalaryRuleLoan(models.Model):
    """
    Extensión de reglas salariales con métodos para cálculo de préstamos
    """
    _inherit = 'hr.salary.rule'

    # ============================================================================
    # MÉTODOS PARA DESCUENTO DE PRÉSTAMOS (CAPITAL)
    # ============================================================================

    def _loan_discount(self, localdict):
        """
        Calcula el descuento de préstamos (capital) para la nómina actual

        BASADO EN: hr_loans.py método _get_loan_lines() líneas 889-919

        USO:
            En regla salarial:
            - amount_select = 'concept'
            - Código de regla debe coincidir con este método (sin guión bajo inicial)

        Retorna:
            tuple: (amount, quantity, rate, name, log, metadata)
            - amount: Total a descontar de préstamos
            - quantity: Número de cuotas
            - rate: 100 (siempre 100%)
            - name: Descripción del descuento
            - log: Log de ejecución
            - metadata: Información adicional (dict)

        Args:
            localdict (dict): Diccionario con contexto de nómina:
                - payslip: Objeto hr.payslip
                - employee: Objeto hr.employee
                - contract: Objeto hr.contract
                - inputs: Entradas manuales
                - worked_days: Días trabajados
                - rules: Reglas calculadas
                - categories: Categorías calculadas

        Ejemplo de uso en XML (data):
            <record id="hr_salary_rule_loan_discount" model="hr.salary.rule">
                <field name="code">LOAN_DISCOUNT</field>
                <field name="name">Descuento de Préstamos</field>
                <field name="category_id" ref="hr_payroll.DED"/>
                <field name="amount_select">concept</field>
                <field name="sequence">200</field>
            </record>
        """
        payslip = localdict.get('payslip')

        if not payslip:
            error_msg = "No se encontró objeto 'payslip' en localdict"
            _logger.error(f"[LOAN_DISCOUNT] {error_msg}")
            return (0.0, 0.0, 100.0, self.name, error_msg, {})

        try:
            service = PrestamoService(self.env, payslip, localdict.get('_batch_context'))

            # Obtener cuotas de préstamo para esta nómina
            loan_installments = service.get_cuotas_pendientes()

            if not loan_installments:
                log_msg = "No hay cuotas de préstamos pendientes para esta nómina"
                _logger.info(f"[LOAN_DISCOUNT] Nómina {payslip.number}: {log_msg}")
                return (0.0, 0.0, 100.0, self.name, log_msg, {})

            resumen = service.get_installments_summary(loan_installments)
            total_amount = resumen.get('total', 0.0)
            num_installments = resumen.get('count', 0)
            loans_detail = resumen.get('details', [])

            metadata = {
                'total_loans': len(loans_detail),
                'total_installments': num_installments,
                'details': loans_detail,
                'type': 'capital',  # Para distinguir de intereses
            }

            # Construir descripción detallada
            name_parts = [self.name]
            for detail in loans_detail:
                name_parts.append(
                    f"{detail['loan_name']}: {detail['count']} cuota(s) - "
                    f"${detail['amount']:,.2f}"
                )

            detailed_name = "\n".join(name_parts)

            log_msg = (
                f"Descuento de {num_installments} cuota(s) de "
                f"{len(loans_detail)} préstamo(s): ${total_amount:,.2f}"
            )
            _logger.info(f"[LOAN_DISCOUNT] Nómina {payslip.number}: {log_msg}")

            # Marcar cuotas como procesadas en nómina
            # NOTA: No marcar como 'paid' aquí, se hace al confirmar la nómina
            for installment in loan_installments:
                if not installment.payslip_id:
                    installment.write({'payslip_id': payslip.id})

            return (
                total_amount,      # amount: Total a descontar
                num_installments,  # quantity: Número de cuotas
                100.0,            # rate: Siempre 100%
                detailed_name,    # name: Descripción detallada
                log_msg,          # log: Mensaje de log
                metadata          # metadata: Información adicional
            )

        except Exception as e:
            error_msg = f"Error calculando descuento de préstamos: {str(e)}"
            _logger.error(f"[LOAN_DISCOUNT] {error_msg}", exc_info=True)
            raise UserError(_(error_msg))

    # ============================================================================
    # MÉTODOS PARA DESCUENTO DE INTERESES
    # ============================================================================

    def _loan_interest(self, localdict):
        """
        Calcula el descuento de intereses de préstamos para la nómina actual

        BASADO EN: hr_loans.py método get_loan_interests() líneas 1036-1079

        Retorna:
            tuple: (amount, quantity, rate, name, log, metadata)
            - amount: Total de intereses a descontar
            - quantity: Número de cuotas con intereses
            - rate: 100 (siempre 100%)
            - name: Descripción del descuento
            - log: Log de ejecución
            - metadata: Información adicional (dict)

        Ejemplo de uso en XML (data):
            <record id="hr_salary_rule_loan_interest" model="hr.salary.rule">
                <field name="code">LOAN_INTEREST</field>
                <field name="name">Intereses de Préstamos</field>
                <field name="category_id" ref="hr_payroll.DED"/>
                <field name="amount_select">concept</field>
                <field name="sequence">201</field>
            </record>
        """
        payslip = localdict.get('payslip')

        if not payslip:
            error_msg = "No se encontró objeto 'payslip' en localdict"
            _logger.error(f"[LOAN_INTEREST] {error_msg}")
            return (0.0, 0.0, 100.0, self.name, error_msg, {})

        try:
            # Obtener resultado del método de nómina
            service = PrestamoService(self.env, payslip, localdict.get('_batch_context'))
            interest_data = service.get_total_intereses(mark_charged=True)

            if not interest_data or interest_data['total'] == 0:
                log_msg = "No hay intereses de préstamos para esta nómina"
                _logger.info(f"[LOAN_INTEREST] Nómina {payslip.number}: {log_msg}")
                return (0.0, 0.0, 100.0, self.name, log_msg, {})

            total_interest = interest_data['total']
            num_installments = interest_data['count']
            details = interest_data['details']

            # Construir metadata
            metadata = {
                'total_loans': len(details),
                'total_installments': num_installments,
                'details': details,
                'type': 'interest',  # Para distinguir de capital
            }

            # Construir descripción detallada
            name_parts = [self.name]
            for detail in details:
                name_parts.append(
                    f"{detail['loan_name']}: {detail['count']} cuota(s) - "
                    f"${detail['interest']:,.2f}"
                )

            detailed_name = "\n".join(name_parts)

            log_msg = (
                f"Intereses de {num_installments} cuota(s) de "
                f"{len(details)} préstamo(s): ${total_interest:,.2f}"
            )
            _logger.info(f"[LOAN_INTEREST] Nómina {payslip.number}: {log_msg}")

            return (
                -total_interest,   # amount: Total de intereses (negativo para deducción)
                num_installments,  # quantity: Número de cuotas
                100.0,            # rate: Siempre 100%
                detailed_name,    # name: Descripción detallada
                log_msg,          # log: Mensaje de log
                metadata          # metadata: Información adicional
            )

        except Exception as e:
            error_msg = f"Error calculando intereses de préstamos: {str(e)}"
            _logger.error(f"[LOAN_INTEREST] {error_msg}", exc_info=True)
            raise UserError(_(error_msg))

    # ============================================================================
    # MÉTODOS AUXILIARES PARA USO EN CÓDIGO PYTHON DE REGLAS
    # ============================================================================

    @api.model
    def get_loan_discount_for_payslip(self, payslip):
        """
        Método auxiliar para obtener descuento de préstamos desde código Python

        Uso en regla con amount_select='code':
            payslip_obj = payslip  # Objeto payslip del localdict
            rule_obj = self.env['hr.salary.rule']
            result = rule_obj.get_loan_discount_for_payslip(payslip_obj)
            result = result  # Total a descontar
            result_qty = 1.0

        Args:
            payslip: Objeto hr.payslip

        Returns:
            float: Total a descontar de préstamos
        """
        loan_installments = payslip.loan_installment_ids.filtered(
            lambda x: not x.paid and not x.skip
        )
        return sum(loan_installments.mapped('amount'))

    @api.model
    def get_loan_interest_for_payslip(self, payslip):
        """
        Método auxiliar para obtener intereses desde código Python

        Args:
            payslip: Objeto hr.payslip

        Returns:
            float: Total de intereses a descontar
        """
        interest_data = payslip.get_loan_interests()
        return interest_data.get('total', 0.0)

    @api.model
    def get_loan_details_for_payslip(self, payslip):
        """
        Obtiene detalles completos de préstamos para la nómina

        Args:
            payslip: Objeto hr.payslip

        Returns:
            dict: {
                'capital': float,
                'interest': float,
                'total': float,
                'num_installments': int,
                'num_loans': int,
                'details': list[dict]
            }
        """
        loan_installments = payslip.loan_installment_ids.filtered(
            lambda x: not x.paid and not x.skip
        )

        capital = sum(loan_installments.mapped('amount'))
        interest_data = payslip.get_loan_interests()
        interest = interest_data.get('total', 0.0)

        loans_detail = []
        for loan in loan_installments.mapped('loan_id'):
            loan_inst = loan_installments.filtered(lambda x: x.loan_id == loan)
            loan_capital = sum(loan_inst.mapped('amount'))
            loan_interest = sum(loan_inst.mapped('interest_amount'))

            loans_detail.append({
                'loan_id': loan.id,
                'loan_name': loan.name,
                'loan_category': loan.category_id.name,
                'installments': len(loan_inst),
                'capital': loan_capital,
                'interest': loan_interest,
                'total': loan_capital + loan_interest
            })

        return {
            'capital': capital,
            'interest': interest,
            'total': capital + interest,
            'num_installments': len(loan_installments),
            'num_loans': len(loan_installments.mapped('loan_id')),
            'details': loans_detail
        }


# ============================================================================
# EXTENSIÓN DE HR.PAYSLIP CON HELPERS ADICIONALES
# ============================================================================

class HrPayslipLoanExtension(models.Model):
    """
    Extensión adicional de hr.payslip para helpers de préstamos
    """
    _inherit = 'hr.payslip'

    def get_total_loans(self):
        """
        Helper simple para obtener total de préstamos (capital + intereses)

        Uso en regla Python:
            result = payslip.get_total_loans()
        """
        self.ensure_one()
        capital = sum(self.loan_installment_ids.filtered(
            lambda x: not x.paid and not x.skip
        ).mapped('amount'))

        interest_data = self.get_loan_interests()
        interest = interest_data.get('total', 0.0)

        return capital + interest

    def get_loan_by_category(self, category_code):
        """
        Obtiene total de préstamos de una categoría específica

        Args:
            category_code (str): Código de categoría de préstamo

        Returns:
            float: Total de préstamos de la categoría

        Uso en regla Python:
            result = payslip.get_loan_by_category('LIBRANZA')
        """
        self.ensure_one()

        loan_installments = self.loan_installment_ids.filtered(
            lambda x: not x.paid and
                     not x.skip and
                     x.loan_id.category_id.code == category_code
        )

        return sum(loan_installments.mapped('amount'))

    def has_settlement_loans(self):
        """
        Verifica si hay préstamos marcados para liquidación

        Returns:
            bool: True si hay préstamos para liquidación

        Uso en regla Python:
            if payslip.has_settlement_loans():
                # Lógica específica
        """
        self.ensure_one()

        settlement_loans = self.loan_installment_ids.filtered(
            lambda x: x.loan_id.deduct_on_settlement and
                     not x.paid and
                     not x.skip
        )

        return len(settlement_loans) > 0

    def get_structure_specific_loans(self, structure_type):
        """
        Obtiene préstamos específicos para un tipo de estructura

        Args:
            structure_type (str): 'prima', 'cesantias', 'liquidacion'

        Returns:
            float: Total de préstamos para esa estructura

        Uso en regla Python:
            # En nómina de prima
            result = payslip.get_structure_specific_loans('prima')
        """
        self.ensure_one()

        structure_loans = self.loan_installment_ids.filtered(
            lambda x: x.loan_id.deduct_in_structure and
                     x.loan_id.structure_type == structure_type and
                     not x.paid and
                     not x.skip
        )

        return sum(structure_loans.mapped('amount'))
