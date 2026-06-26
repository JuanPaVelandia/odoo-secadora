# -*- coding: utf-8 -*-
"""
Indicadores Financieros Colombia - Odoo 18
==========================================
Modelo abstracto con metodos para calcular indicadores financieros
usando el patron nativo de Odoo 18 account_reports.

Uso:
    class MiHandler(models.AbstractModel):
        _inherit = ['account.report.custom.handler', 'financial.indicators.mixin']

        def mi_metodo(self, data):
            ratio = self.calculate_liquidity_ratio(
                current_assets=data['current_assets'],
                current_liabilities=data['current_liabilities']
            )
"""

from odoo import models, api, _
import logging

_logger = logging.getLogger(__name__)


class FinancialIndicatorsMixin(models.AbstractModel):
    """
    Mixin con calculos de indicadores financieros para reportes.

    Incluye:
    - Ratios de liquidez
    - Ratios de endeudamiento
    - Ratios de rentabilidad
    - Ratios de actividad
    - Margenes y EBITDA
    - Analisis horizontal/vertical
    """
    _name = 'financial.indicators.mixin'
    _description = 'Mixin de Indicadores Financieros'

    # =====================================================
    # RATIOS DE LIQUIDEZ
    # =====================================================

    def calculate_liquidity_ratio(self, current_assets, current_liabilities):
        """
        Ratio de Liquidez Corriente = Activo Corriente / Pasivo Corriente

        Interpretacion:
        - > 2.0: Excelente liquidez
        - 1.5 - 2.0: Buena liquidez
        - 1.0 - 1.5: Liquidez ajustada
        - < 1.0: Problemas de liquidez
        """
        if current_liabilities and current_liabilities != 0:
            return current_assets / current_liabilities
        return False

    def calculate_working_capital(self, current_assets, current_liabilities):
        """Capital de Trabajo = Activo Corriente - Pasivo Corriente"""
        return current_assets - current_liabilities

    def calculate_acid_test_ratio(self, current_assets, inventory, current_liabilities):
        """
        Prueba Acida = (Activo Corriente - Inventario) / Pasivo Corriente

        Mas exigente que ratio corriente, excluye inventarios.
        """
        if current_liabilities and current_liabilities != 0:
            return (current_assets - inventory) / current_liabilities
        return False

    def calculate_cash_ratio(self, cash, current_liabilities):
        """
        Ratio de Caja = Efectivo / Pasivo Corriente

        El ratio mas exigente, solo considera efectivo.
        """
        if current_liabilities and current_liabilities != 0:
            return cash / current_liabilities
        return False

    # =====================================================
    # RATIOS DE ENDEUDAMIENTO
    # =====================================================

    def calculate_debt_ratio(self, total_liabilities, total_assets):
        """
        Ratio de Endeudamiento = Pasivo Total / Activo Total

        Interpretacion:
        - < 0.4: Bajo endeudamiento
        - 0.4 - 0.6: Endeudamiento moderado
        - > 0.6: Alto endeudamiento
        """
        if total_assets and total_assets != 0:
            return total_liabilities / total_assets
        return False

    def calculate_equity_ratio(self, total_equity, total_assets):
        """Ratio de Patrimonio = Patrimonio / Activo Total"""
        if total_assets and total_assets != 0:
            return total_equity / total_assets
        return False

    def calculate_debt_to_equity(self, total_liabilities, total_equity):
        """
        Ratio Deuda/Patrimonio = Pasivo Total / Patrimonio

        Mide apalancamiento financiero.
        """
        if total_equity and total_equity != 0:
            return total_liabilities / total_equity
        return False

    def calculate_financial_leverage(self, total_assets, total_equity):
        """Apalancamiento Financiero = Activo Total / Patrimonio"""
        if total_equity and total_equity != 0:
            return total_assets / total_equity
        return False

    def calculate_interest_coverage(self, ebit, interest_expense):
        """
        Cobertura de Intereses = EBIT / Gastos de Intereses

        Interpretacion:
        - > 3: Buena capacidad de pago
        - 1.5 - 3: Capacidad moderada
        - < 1.5: Riesgo de impago
        """
        if interest_expense and interest_expense != 0:
            return ebit / interest_expense
        return False

    # =====================================================
    # RATIOS DE RENTABILIDAD
    # =====================================================

    def calculate_roa(self, net_income, total_assets):
        """
        ROA (Return on Assets) = Utilidad Neta / Activo Total

        Mide eficiencia en uso de activos.
        """
        if total_assets and total_assets != 0:
            return (net_income / total_assets) * 100
        return False

    def calculate_roe(self, net_income, total_equity):
        """
        ROE (Return on Equity) = Utilidad Neta / Patrimonio

        Mide rentabilidad para accionistas.
        """
        if total_equity and total_equity != 0:
            return (net_income / total_equity) * 100
        return False

    def calculate_roic(self, nopat, invested_capital):
        """
        ROIC (Return on Invested Capital) = NOPAT / Capital Invertido

        Mide eficiencia del capital total.
        """
        if invested_capital and invested_capital != 0:
            return (nopat / invested_capital) * 100
        return False

    # =====================================================
    # MARGENES
    # =====================================================

    def calculate_gross_margin(self, sales, cost_of_sales):
        """Margen Bruto = (Ventas - Costo de Ventas) / Ventas * 100"""
        if sales and sales != 0:
            return ((sales - cost_of_sales) / sales) * 100
        return False

    def calculate_gross_profit(self, sales, cost_of_sales):
        """Utilidad Bruta = Ventas - Costo de Ventas"""
        return sales - cost_of_sales

    def calculate_operating_margin(self, operating_income, sales):
        """Margen Operacional = Utilidad Operacional / Ventas * 100"""
        if sales and sales != 0:
            return (operating_income / sales) * 100
        return False

    def calculate_net_margin(self, net_income, sales):
        """Margen Neto = Utilidad Neta / Ventas * 100"""
        if sales and sales != 0:
            return (net_income / sales) * 100
        return False

    def calculate_ebitda_margin(self, ebitda, sales):
        """Margen EBITDA = EBITDA / Ventas * 100"""
        if sales and sales != 0:
            return (ebitda / sales) * 100
        return False

    # =====================================================
    # EBITDA Y EBIT
    # =====================================================

    def calculate_ebitda(self, net_income, interest, taxes, depreciation, amortization):
        """
        EBITDA = Utilidad Neta + Intereses + Impuestos + Depreciacion + Amortizacion

        Mide capacidad operativa de generar efectivo.
        """
        return net_income + interest + taxes + depreciation + amortization

    def calculate_ebit(self, net_income, interest, taxes):
        """EBIT = Utilidad Neta + Intereses + Impuestos"""
        return net_income + interest + taxes

    def calculate_nopat(self, ebit, tax_rate):
        """NOPAT = EBIT * (1 - Tasa Impuestos)"""
        return ebit * (1 - tax_rate)

    # =====================================================
    # RATIOS DE ACTIVIDAD
    # =====================================================

    def calculate_asset_turnover(self, sales, total_assets):
        """Rotacion de Activos = Ventas / Activo Total"""
        if total_assets and total_assets != 0:
            return sales / total_assets
        return False

    def calculate_inventory_turnover(self, cost_of_sales, average_inventory):
        """Rotacion de Inventarios = Costo de Ventas / Inventario Promedio"""
        if average_inventory and average_inventory != 0:
            return cost_of_sales / average_inventory
        return False

    def calculate_days_inventory(self, inventory_turnover):
        """Dias de Inventario = 365 / Rotacion de Inventarios"""
        if inventory_turnover and inventory_turnover != 0:
            return 365 / inventory_turnover
        return False

    def calculate_receivables_turnover(self, sales, average_receivables):
        """Rotacion de Cartera = Ventas / CxC Promedio"""
        if average_receivables and average_receivables != 0:
            return sales / average_receivables
        return False

    def calculate_days_sales_outstanding(self, receivables_turnover):
        """DSO (Dias de Cobro) = 365 / Rotacion de Cartera"""
        if receivables_turnover and receivables_turnover != 0:
            return 365 / receivables_turnover
        return False

    def calculate_payables_turnover(self, purchases, average_payables):
        """Rotacion de Proveedores = Compras / CxP Promedio"""
        if average_payables and average_payables != 0:
            return purchases / average_payables
        return False

    def calculate_days_payable(self, payables_turnover):
        """Dias de Pago = 365 / Rotacion de Proveedores"""
        if payables_turnover and payables_turnover != 0:
            return 365 / payables_turnover
        return False

    def calculate_cash_conversion_cycle(self, days_inventory, days_receivables, days_payables):
        """
        Ciclo de Conversion de Efectivo = DIO + DSO - DPO

        Dias que toma convertir inversiones en efectivo.
        """
        return days_inventory + days_receivables - days_payables

    # =====================================================
    # ANALISIS DE CARTERA
    # =====================================================

    def calculate_aging_buckets(self, invoice_date, reference_date, aging_periods):
        """
        Calcula en que bucket de aging cae una factura.

        :param invoice_date: Fecha de la factura
        :param reference_date: Fecha de referencia
        :param aging_periods: Lista de periodos [{'name': '0-30', 'from': 0, 'to': 30}, ...]
        :return: str nombre del bucket o None
        """
        from datetime import datetime

        if isinstance(invoice_date, str):
            invoice_date = datetime.strptime(invoice_date, '%Y-%m-%d').date()
        if isinstance(reference_date, str):
            reference_date = datetime.strptime(reference_date, '%Y-%m-%d').date()

        days_overdue = (reference_date - invoice_date).days

        for period in aging_periods:
            if period['from'] <= days_overdue <= period['to']:
                return period['name']

        return aging_periods[-1]['name'] if aging_periods else None

    def calculate_collection_effectiveness(self, collected, total_due):
        """Efectividad de Cobranza = (Monto Cobrado / Total por Cobrar) * 100"""
        if total_due and total_due != 0:
            return (collected / total_due) * 100
        return False

    # =====================================================
    # ANALISIS HORIZONTAL Y VERTICAL
    # =====================================================

    def calculate_horizontal_analysis(self, current_value, previous_value):
        """
        Analisis Horizontal = ((Valor Actual - Valor Anterior) / Valor Anterior) * 100

        :return: Dict con {'change': float, 'percentage': float}
        """
        change = current_value - previous_value

        if previous_value and previous_value != 0:
            percentage = (change / previous_value) * 100
        else:
            percentage = False

        return {
            'change': change,
            'percentage': percentage
        }

    def calculate_vertical_analysis(self, item_value, base_value):
        """
        Analisis Vertical = (Valor del Item / Valor Base) * 100

        Ejemplo: Cada cuenta como % de Total Activos
        """
        if base_value and base_value != 0:
            return (item_value / base_value) * 100
        return False

    # =====================================================
    # UTILIDADES DE FORMATEO
    # =====================================================

    def format_ratio(self, ratio_value, decimals=2):
        """Formatea un ratio para visualizacion."""
        if ratio_value is False or ratio_value is None:
            return False
        return round(ratio_value, decimals)

    def format_percentage(self, percentage_value, decimals=2):
        """Formatea un porcentaje para visualizacion."""
        if percentage_value is False or percentage_value is None:
            return False
        return f"{round(percentage_value, decimals)}%"

    def format_currency(self, value, decimals=2):
        """Formatea un valor monetario."""
        if value is False or value is None:
            return False
        return self.env.company.currency_id.format(round(value, decimals))

    # =====================================================
    # INDICADORES CONSOLIDADOS
    # =====================================================

    def calculate_all_ratios(self, balance_data, income_data):
        """
        Calcula todos los ratios a partir de datos de balance y P&L.

        :param balance_data: Dict con datos del balance
        :param income_data: Dict con datos del P&L
        :return: Dict con todos los ratios calculados
        """
        ratios = {}

        # Extraer datos del balance
        current_assets = balance_data.get('current_assets', 0)
        current_liabilities = balance_data.get('current_liabilities', 0)
        total_assets = balance_data.get('total_assets', 0)
        total_liabilities = balance_data.get('total_liabilities', 0)
        total_equity = balance_data.get('total_equity', 0)
        inventory = balance_data.get('inventory', 0)
        cash = balance_data.get('cash', 0)

        # Extraer datos del P&L
        sales = income_data.get('sales', 0)
        cost_of_sales = income_data.get('cost_of_sales', 0)
        operating_income = income_data.get('operating_income', 0)
        net_income = income_data.get('net_income', 0)
        interest_expense = income_data.get('interest_expense', 0)
        taxes = income_data.get('taxes', 0)
        depreciation = income_data.get('depreciation', 0)

        # Ratios de liquidez
        ratios['liquidity'] = {
            'current_ratio': self.calculate_liquidity_ratio(current_assets, current_liabilities),
            'acid_test': self.calculate_acid_test_ratio(current_assets, inventory, current_liabilities),
            'cash_ratio': self.calculate_cash_ratio(cash, current_liabilities),
            'working_capital': self.calculate_working_capital(current_assets, current_liabilities),
        }

        # Ratios de endeudamiento
        ratios['leverage'] = {
            'debt_ratio': self.calculate_debt_ratio(total_liabilities, total_assets),
            'equity_ratio': self.calculate_equity_ratio(total_equity, total_assets),
            'debt_to_equity': self.calculate_debt_to_equity(total_liabilities, total_equity),
            'financial_leverage': self.calculate_financial_leverage(total_assets, total_equity),
        }

        # Ratios de rentabilidad
        ratios['profitability'] = {
            'roa': self.calculate_roa(net_income, total_assets),
            'roe': self.calculate_roe(net_income, total_equity),
            'gross_margin': self.calculate_gross_margin(sales, cost_of_sales),
            'operating_margin': self.calculate_operating_margin(operating_income, sales),
            'net_margin': self.calculate_net_margin(net_income, sales),
        }

        # EBITDA
        ebit = self.calculate_ebit(net_income, interest_expense, taxes)
        ebitda = self.calculate_ebitda(net_income, interest_expense, taxes, depreciation, 0)
        ratios['ebitda'] = {
            'ebit': ebit,
            'ebitda': ebitda,
            'ebitda_margin': self.calculate_ebitda_margin(ebitda, sales),
        }

        # Ratios de actividad
        ratios['activity'] = {
            'asset_turnover': self.calculate_asset_turnover(sales, total_assets),
        }

        return ratios
