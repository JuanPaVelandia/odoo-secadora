# -*- coding: utf-8 -*-
"""
Formulas de Reportes Colombia - Odoo 18
=======================================
Modelo abstracto con formulas y calculos especificos para reportes
contables colombianos, adaptado al patron nativo de Odoo 18.

Este modulo contiene las formulas de calculo que usan los handlers
de reportes financieros para Colombia.
"""

from odoo import models, api, _
from odoo.tools import SQL, Query
import logging

_logger = logging.getLogger(__name__)


class ReportFormulasMixin(models.AbstractModel):
    """
    Mixin con formulas de calculo para reportes contables Colombia.

    Incluye:
    - Formulas para Balance General
    - Formulas para Estado de Resultados
    - Formulas para Flujo de Efectivo
    - Formulas para Estado de Cambios en Patrimonio
    """
    _name = 'report.formulas.mixin'
    _description = 'Mixin de Formulas para Reportes Colombia'

    # =====================================================
    # FORMULAS BALANCE GENERAL
    # =====================================================

    def compute_balance_section(self, account_codes, report_data):
        """
        Calcula el total de una seccion del balance.

        :param account_codes: Lista de prefijos de codigo de cuenta
        :param report_data: Datos del reporte con balances
        :return: Total de la seccion
        """
        total = 0.0
        for row in report_data:
            code = row.get('account_code', '')
            for prefix in account_codes:
                if code.startswith(prefix):
                    total += row.get('balance', 0)
                    break
        return total

    def compute_total_assets(self, report_data):
        """
        Calcula Total Activos.
        En PUC Colombia: cuentas que empiezan con 1
        """
        return self.compute_balance_section(['1'], report_data)

    def compute_current_assets(self, report_data):
        """
        Calcula Activo Corriente.
        En PUC Colombia: 11 (Efectivo), 12 (Inversiones CP), 13 (Deudores), 14 (Inventarios)
        """
        return self.compute_balance_section(['11', '12', '13', '14'], report_data)

    def compute_non_current_assets(self, report_data):
        """
        Calcula Activo No Corriente.
        En PUC Colombia: 15 (Propiedades), 16 (Intangibles), 17 (Diferidos), etc.
        """
        return self.compute_balance_section(['15', '16', '17', '18', '19'], report_data)

    def compute_total_liabilities(self, report_data):
        """
        Calcula Total Pasivos.
        En PUC Colombia: cuentas que empiezan con 2
        """
        return abs(self.compute_balance_section(['2'], report_data))

    def compute_current_liabilities(self, report_data):
        """
        Calcula Pasivo Corriente.
        En PUC Colombia: 21 (Obligaciones financieras CP), 22 (Proveedores), 23 (Cuentas por pagar), 24 (Impuestos)
        """
        return abs(self.compute_balance_section(['21', '22', '23', '24'], report_data))

    def compute_non_current_liabilities(self, report_data):
        """
        Calcula Pasivo No Corriente.
        En PUC Colombia: 25 (Obligaciones laborales LP), 26 (Pasivos estimados), 27 (Diferidos), etc.
        """
        return abs(self.compute_balance_section(['25', '26', '27', '28', '29'], report_data))

    def compute_total_equity(self, report_data):
        """
        Calcula Total Patrimonio.
        En PUC Colombia: cuentas que empiezan con 3
        """
        return abs(self.compute_balance_section(['3'], report_data))

    # =====================================================
    # FORMULAS ESTADO DE RESULTADOS
    # =====================================================

    def compute_income_section(self, account_codes, report_data):
        """
        Calcula el total de una seccion del P&L.
        Los ingresos tienen saldo credito (negativo en balance),
        los gastos tienen saldo debito (positivo).
        """
        total = 0.0
        for row in report_data:
            code = row.get('account_code', '')
            for prefix in account_codes:
                if code.startswith(prefix):
                    total += row.get('balance', 0)
                    break
        return total

    def compute_revenue(self, report_data):
        """
        Calcula Ingresos Operacionales.
        En PUC Colombia: 41 (Ingresos operacionales)
        """
        return abs(self.compute_income_section(['41'], report_data))

    def compute_other_income(self, report_data):
        """
        Calcula Otros Ingresos.
        En PUC Colombia: 42 (No operacionales)
        """
        return abs(self.compute_income_section(['42'], report_data))

    def compute_cost_of_sales(self, report_data):
        """
        Calcula Costo de Ventas.
        En PUC Colombia: 6 (Costos de ventas)
        """
        return self.compute_income_section(['6'], report_data)

    def compute_operating_expenses(self, report_data):
        """
        Calcula Gastos Operacionales.
        En PUC Colombia: 51 (Administracion), 52 (Ventas)
        """
        return self.compute_income_section(['51', '52'], report_data)

    def compute_financial_expenses(self, report_data):
        """
        Calcula Gastos Financieros.
        En PUC Colombia: 5305 (Gastos financieros)
        """
        return self.compute_income_section(['5305'], report_data)

    def compute_tax_expense(self, report_data):
        """
        Calcula Gasto por Impuestos.
        En PUC Colombia: 54 (Impuesto de renta)
        """
        return self.compute_income_section(['54'], report_data)

    def compute_gross_profit(self, report_data):
        """Utilidad Bruta = Ingresos - Costo de Ventas"""
        revenue = self.compute_revenue(report_data)
        cost = self.compute_cost_of_sales(report_data)
        return revenue - cost

    def compute_operating_income(self, report_data):
        """Utilidad Operacional = Utilidad Bruta - Gastos Operacionales"""
        gross = self.compute_gross_profit(report_data)
        expenses = self.compute_operating_expenses(report_data)
        return gross - expenses

    def compute_net_income(self, report_data):
        """
        Utilidad Neta = Ingresos - Costos - Gastos - Impuestos

        Formula completa del P&L Colombia.
        """
        revenue = self.compute_revenue(report_data)
        other_income = self.compute_other_income(report_data)
        cost = self.compute_cost_of_sales(report_data)
        op_expenses = self.compute_operating_expenses(report_data)
        fin_expenses = self.compute_financial_expenses(report_data)
        taxes = self.compute_tax_expense(report_data)

        return revenue + other_income - cost - op_expenses - fin_expenses - taxes

    # =====================================================
    # FORMULAS FLUJO DE EFECTIVO
    # =====================================================

    def compute_cash_from_operations(self, net_income, depreciation, delta_receivables,
                                      delta_inventory, delta_payables, other_adjustments=0):
        """
        Flujo de Efectivo de Operaciones (Metodo Indirecto).

        CFO = Utilidad Neta + Depreciacion
              - Aumento CxC + Disminucion CxC
              - Aumento Inventario + Disminucion Inventario
              + Aumento CxP - Disminucion CxP
              + Otros ajustes
        """
        return (net_income + depreciation
                - delta_receivables
                - delta_inventory
                + delta_payables
                + other_adjustments)

    def compute_cash_from_investing(self, capex, asset_sales, investment_purchases,
                                     investment_sales, other=0):
        """
        Flujo de Efectivo de Inversion.

        CFI = - Compras de activos fijos + Ventas de activos
              - Compras de inversiones + Ventas de inversiones
              + Otros
        """
        return -capex + asset_sales - investment_purchases + investment_sales + other

    def compute_cash_from_financing(self, new_debt, debt_repayment, equity_issuance,
                                     dividends, other=0):
        """
        Flujo de Efectivo de Financiamiento.

        CFF = + Nueva deuda - Pago de deuda
              + Emision de acciones - Recompra
              - Dividendos pagados
              + Otros
        """
        return new_debt - debt_repayment + equity_issuance - dividends + other

    def compute_net_cash_change(self, cfo, cfi, cff):
        """Cambio Neto en Efectivo = CFO + CFI + CFF"""
        return cfo + cfi + cff

    # =====================================================
    # FORMULAS CAMBIOS EN PATRIMONIO
    # =====================================================

    def compute_equity_change(self, beginning_equity, net_income, dividends,
                              other_comprehensive_income, capital_transactions):
        """
        Cambio en Patrimonio.

        Patrimonio Final = Patrimonio Inicial
                          + Utilidad Neta
                          - Dividendos
                          + OCI (Otro Resultado Integral)
                          + Transacciones de Capital
        """
        return (beginning_equity + net_income - dividends +
                other_comprehensive_income + capital_transactions)

    def compute_retained_earnings(self, beginning_retained, net_income, dividends):
        """
        Utilidades Retenidas.

        UR Final = UR Inicial + Utilidad Neta - Dividendos
        """
        return beginning_retained + net_income - dividends

    # =====================================================
    # FORMULAS AUXILIARES
    # =====================================================

    def compute_percentage_of_total(self, value, total):
        """Calcula porcentaje de un valor respecto al total."""
        if total and total != 0:
            return (value / total) * 100
        return 0

    def compute_variation(self, current, previous):
        """Calcula variacion absoluta y porcentual."""
        absolute = current - previous
        if previous and previous != 0:
            percentage = (absolute / previous) * 100
        else:
            percentage = 0 if current == 0 else 100

        return {
            'absolute': absolute,
            'percentage': percentage
        }

    def apply_sign_convention(self, value, account_type):
        """
        Aplica convencion de signos segun tipo de cuenta.

        En contabilidad colombiana:
        - Activos: saldo debito (positivo)
        - Pasivos: saldo credito (mostrar como positivo)
        - Patrimonio: saldo credito (mostrar como positivo)
        - Ingresos: saldo credito (mostrar como positivo)
        - Gastos: saldo debito (positivo)
        """
        credit_types = ['liability', 'equity', 'income', 'liability_payable',
                        'liability_non_current', 'equity_unaffected']

        if account_type in credit_types:
            return -value if value < 0 else value
        return value

    # =====================================================
    # VALIDACIONES
    # =====================================================

    def validate_balance_equation(self, assets, liabilities, equity):
        """
        Valida ecuacion contable: Activos = Pasivos + Patrimonio

        :return: Dict con resultado de validacion
        """
        difference = assets - (liabilities + equity)
        is_balanced = abs(difference) < 0.01  # Tolerancia de 1 centavo

        return {
            'is_balanced': is_balanced,
            'difference': difference,
            'assets': assets,
            'liabilities': liabilities,
            'equity': equity,
            'equation': f"{assets:,.2f} = {liabilities:,.2f} + {equity:,.2f}"
        }

    def validate_income_statement(self, revenue, cost, expenses, net_income):
        """
        Valida que el Estado de Resultados cuadre.

        :return: Dict con resultado de validacion
        """
        calculated_net = revenue - cost - expenses
        difference = net_income - calculated_net
        is_valid = abs(difference) < 0.01

        return {
            'is_valid': is_valid,
            'difference': difference,
            'calculated': calculated_net,
            'reported': net_income
        }

    def validate_cash_flow(self, beginning_cash, ending_cash, net_change):
        """
        Valida que el Flujo de Efectivo cuadre.

        Efectivo Final = Efectivo Inicial + Cambio Neto
        """
        expected_ending = beginning_cash + net_change
        difference = ending_cash - expected_ending
        is_valid = abs(difference) < 0.01

        return {
            'is_valid': is_valid,
            'difference': difference,
            'expected': expected_ending,
            'reported': ending_cash
        }
