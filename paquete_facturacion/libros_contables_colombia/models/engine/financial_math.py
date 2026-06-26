# -*- coding: utf-8 -*-
"""
Motor de Matematicas Financieras - Odoo 18
==========================================
Clases y funciones matematicas avanzadas para calculo de indicadores
financieros, predicciones y analisis estadistico.

Uso:
    from odoo.addons.libros_contables_colombia.models.engine.financial_math import FinancialMath

    math = FinancialMath()
    npv = math.npv(rate=0.1, cashflows=[-1000, 200, 300, 400, 500])
"""

import logging
from typing import List, Dict, Any, Optional, Tuple, Union
from collections import defaultdict

_logger = logging.getLogger(__name__)

# Verificar disponibilidad de numpy
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    _logger.info("numpy no disponible, usando implementacion manual")


class FinancialMath:
    """
    Clase con calculos matematicos financieros avanzados.

    Incluye:
    - Valor Presente Neto (NPV)
    - Tasa Interna de Retorno (TIR/IRR)
    - WACC (Costo Promedio Ponderado de Capital)
    - Analisis DuPont
    - Z-Score de Altman
    - Ratios financieros avanzados
    """

    # =====================================================
    # VALOR DEL DINERO EN EL TIEMPO
    # =====================================================

    @staticmethod
    def npv(rate: float, cashflows: List[float]) -> float:
        """
        Calcula el Valor Presente Neto (NPV).

        NPV = Sum(CFt / (1 + r)^t) para t = 0 hasta n

        :param rate: Tasa de descuento (ej: 0.10 para 10%)
        :param cashflows: Lista de flujos de caja [CF0, CF1, CF2, ...]
        :return: Valor Presente Neto
        """
        if not cashflows:
            return 0.0

        if HAS_NUMPY:
            periods = np.arange(len(cashflows))
            discount_factors = (1 + rate) ** periods
            return np.sum(np.array(cashflows) / discount_factors)
        else:
            return sum(cf / ((1 + rate) ** t) for t, cf in enumerate(cashflows))

    @staticmethod
    def irr(cashflows: List[float], guess: float = 0.1, max_iter: int = 100,
            tolerance: float = 1e-7) -> Optional[float]:
        """
        Calcula la Tasa Interna de Retorno (IRR/TIR).

        La TIR es la tasa que hace NPV = 0.
        Usa metodo de Newton-Raphson para aproximacion.

        :param cashflows: Flujos de caja
        :param guess: Estimacion inicial
        :param max_iter: Iteraciones maximas
        :param tolerance: Tolerancia para convergencia
        :return: TIR o None si no converge
        """
        if not cashflows or len(cashflows) < 2:
            return None

        rate = guess

        for _ in range(max_iter):
            # NPV
            npv = sum(cf / ((1 + rate) ** t) for t, cf in enumerate(cashflows))

            # Derivada del NPV
            npv_derivative = sum(
                -t * cf / ((1 + rate) ** (t + 1))
                for t, cf in enumerate(cashflows)
            )

            if abs(npv_derivative) < 1e-10:
                break

            # Newton-Raphson
            new_rate = rate - npv / npv_derivative

            if abs(new_rate - rate) < tolerance:
                return new_rate

            rate = new_rate

        return None  # No convergio

    @staticmethod
    def pv(rate: float, nper: int, pmt: float, fv: float = 0) -> float:
        """
        Calcula el Valor Presente de una anualidad.

        :param rate: Tasa de interes por periodo
        :param nper: Numero de periodos
        :param pmt: Pago por periodo
        :param fv: Valor futuro (default 0)
        :return: Valor Presente
        """
        if rate == 0:
            return -pmt * nper - fv

        pv_annuity = pmt * (1 - (1 + rate) ** -nper) / rate
        pv_fv = fv / ((1 + rate) ** nper)

        return -(pv_annuity + pv_fv)

    @staticmethod
    def fv(rate: float, nper: int, pmt: float, pv: float = 0) -> float:
        """
        Calcula el Valor Futuro de una anualidad.

        :param rate: Tasa de interes por periodo
        :param nper: Numero de periodos
        :param pmt: Pago por periodo
        :param pv: Valor presente (default 0)
        :return: Valor Futuro
        """
        if rate == 0:
            return -pv - pmt * nper

        fv_pv = pv * ((1 + rate) ** nper)
        fv_annuity = pmt * (((1 + rate) ** nper - 1) / rate)

        return -(fv_pv + fv_annuity)

    # =====================================================
    # COSTO DE CAPITAL
    # =====================================================

    @staticmethod
    def wacc(equity: float, debt: float, cost_equity: float,
             cost_debt: float, tax_rate: float) -> float:
        """
        Calcula el Costo Promedio Ponderado de Capital (WACC).

        WACC = (E/V) * Re + (D/V) * Rd * (1 - Tc)

        :param equity: Valor del patrimonio
        :param debt: Valor de la deuda
        :param cost_equity: Costo del patrimonio (Re)
        :param cost_debt: Costo de la deuda (Rd)
        :param tax_rate: Tasa de impuestos (Tc)
        :return: WACC
        """
        total_value = equity + debt

        if total_value == 0:
            return 0

        weight_equity = equity / total_value
        weight_debt = debt / total_value

        return (weight_equity * cost_equity +
                weight_debt * cost_debt * (1 - tax_rate))

    @staticmethod
    def capm(risk_free_rate: float, beta: float, market_return: float) -> float:
        """
        Calcula el retorno esperado usando CAPM.

        E(Ri) = Rf + Beta * (Rm - Rf)

        :param risk_free_rate: Tasa libre de riesgo
        :param beta: Beta del activo
        :param market_return: Retorno del mercado
        :return: Retorno esperado
        """
        return risk_free_rate + beta * (market_return - risk_free_rate)

    # =====================================================
    # ANALISIS DUPONT
    # =====================================================

    @staticmethod
    def dupont_3_factor(net_income: float, sales: float,
                        total_assets: float, equity: float) -> Dict[str, float]:
        """
        Analisis DuPont de 3 factores.

        ROE = Margen Neto * Rotacion Activos * Apalancamiento
        ROE = (NI/Sales) * (Sales/Assets) * (Assets/Equity)

        :return: Dict con los 3 factores y ROE
        """
        # Proteger division por cero
        net_margin = (net_income / sales) if sales else 0
        asset_turnover = (sales / total_assets) if total_assets else 0
        leverage = (total_assets / equity) if equity else 0

        roe = net_margin * asset_turnover * leverage

        return {
            'net_margin': net_margin,
            'asset_turnover': asset_turnover,
            'financial_leverage': leverage,
            'roe': roe,
            'components': {
                'profitability': net_margin,
                'efficiency': asset_turnover,
                'leverage': leverage
            }
        }

    @staticmethod
    def dupont_5_factor(ebit: float, interest: float, ebt: float,
                        net_income: float, sales: float,
                        total_assets: float, equity: float) -> Dict[str, float]:
        """
        Analisis DuPont de 5 factores.

        ROE = Tax Burden * Interest Burden * EBIT Margin * Asset Turnover * Leverage

        :return: Dict con los 5 factores y ROE
        """
        # Tax Burden = NI / EBT
        tax_burden = (net_income / ebt) if ebt else 0

        # Interest Burden = EBT / EBIT
        interest_burden = (ebt / ebit) if ebit else 0

        # EBIT Margin = EBIT / Sales
        ebit_margin = (ebit / sales) if sales else 0

        # Asset Turnover = Sales / Assets
        asset_turnover = (sales / total_assets) if total_assets else 0

        # Leverage = Assets / Equity
        leverage = (total_assets / equity) if equity else 0

        roe = tax_burden * interest_burden * ebit_margin * asset_turnover * leverage

        return {
            'tax_burden': tax_burden,
            'interest_burden': interest_burden,
            'ebit_margin': ebit_margin,
            'asset_turnover': asset_turnover,
            'financial_leverage': leverage,
            'roe': roe
        }

    # =====================================================
    # Z-SCORE DE ALTMAN
    # =====================================================

    @staticmethod
    def altman_z_score(working_capital: float, total_assets: float,
                       retained_earnings: float, ebit: float,
                       market_value_equity: float, total_liabilities: float,
                       sales: float, company_type: str = 'public') -> Dict[str, Any]:
        """
        Calcula el Z-Score de Altman para prediccion de quiebra.

        Para empresas publicas:
        Z = 1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 1.0*X5

        Para empresas privadas:
        Z' = 0.717*X1 + 0.847*X2 + 3.107*X3 + 0.420*X4 + 0.998*X5

        :param working_capital: Capital de trabajo
        :param total_assets: Total activos
        :param retained_earnings: Utilidades retenidas
        :param ebit: EBIT
        :param market_value_equity: Valor de mercado del patrimonio
        :param total_liabilities: Total pasivos
        :param sales: Ventas
        :param company_type: 'public', 'private', 'emerging'
        :return: Z-Score y clasificacion
        """
        if total_assets == 0:
            return {'error': 'Total assets cannot be zero'}

        # Calcular ratios
        x1 = working_capital / total_assets
        x2 = retained_earnings / total_assets
        x3 = ebit / total_assets
        x4 = market_value_equity / total_liabilities if total_liabilities else 0
        x5 = sales / total_assets

        # Calcular Z-Score segun tipo de empresa
        if company_type == 'public':
            z = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5
            zones = {'safe': 2.99, 'grey_upper': 2.99, 'grey_lower': 1.81}
        elif company_type == 'private':
            z = 0.717 * x1 + 0.847 * x2 + 3.107 * x3 + 0.420 * x4 + 0.998 * x5
            zones = {'safe': 2.9, 'grey_upper': 2.9, 'grey_lower': 1.23}
        else:  # emerging
            z = 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4
            zones = {'safe': 2.6, 'grey_upper': 2.6, 'grey_lower': 1.1}

        # Clasificar
        if z > zones['safe']:
            classification = 'safe'
            risk_level = 'low'
            description = 'Zona segura - Bajo riesgo de quiebra'
        elif z >= zones['grey_lower']:
            classification = 'grey'
            risk_level = 'medium'
            description = 'Zona gris - Riesgo moderado'
        else:
            classification = 'distress'
            risk_level = 'high'
            description = 'Zona de peligro - Alto riesgo de quiebra'

        return {
            'z_score': z,
            'classification': classification,
            'risk_level': risk_level,
            'description': description,
            'ratios': {
                'x1_working_capital': x1,
                'x2_retained_earnings': x2,
                'x3_ebit': x3,
                'x4_market_equity': x4,
                'x5_sales': x5
            },
            'zones': zones
        }

    # =====================================================
    # RATIOS FINANCIEROS AVANZADOS
    # =====================================================

    @staticmethod
    def eva(nopat: float, invested_capital: float, wacc: float) -> float:
        """
        Calcula el Valor Economico Agregado (EVA).

        EVA = NOPAT - (Capital Invertido * WACC)

        :param nopat: Utilidad operativa despues de impuestos
        :param invested_capital: Capital invertido
        :param wacc: Costo promedio ponderado de capital
        :return: EVA
        """
        return nopat - (invested_capital * wacc)

    @staticmethod
    def roic(nopat: float, invested_capital: float) -> float:
        """
        Calcula el Retorno sobre Capital Invertido (ROIC).

        ROIC = NOPAT / Capital Invertido

        :param nopat: Utilidad operativa despues de impuestos
        :param invested_capital: Capital invertido
        :return: ROIC
        """
        if invested_capital == 0:
            return 0
        return nopat / invested_capital

    @staticmethod
    def free_cash_flow(ebit: float, tax_rate: float, depreciation: float,
                       capex: float, change_working_capital: float) -> float:
        """
        Calcula el Flujo de Caja Libre (FCF).

        FCF = EBIT(1-t) + D&A - CapEx - Delta WC

        :param ebit: EBIT
        :param tax_rate: Tasa de impuestos
        :param depreciation: Depreciacion y amortizacion
        :param capex: Gastos de capital
        :param change_working_capital: Cambio en capital de trabajo
        :return: FCF
        """
        nopat = ebit * (1 - tax_rate)
        return nopat + depreciation - capex - change_working_capital


class StatisticalAnalysis:
    """
    Clase para analisis estadistico de datos financieros.
    """

    @staticmethod
    def calculate_basic_stats(values: List[float]) -> Dict[str, float]:
        """
        Calcula estadisticas basicas.

        :param values: Lista de valores
        :return: Dict con estadisticas
        """
        if not values:
            return {}

        if HAS_NUMPY:
            arr = np.array(values)
            return {
                'mean': float(np.mean(arr)),
                'median': float(np.median(arr)),
                'std': float(np.std(arr)),
                'min': float(np.min(arr)),
                'max': float(np.max(arr)),
                'range': float(np.max(arr) - np.min(arr)),
                'q1': float(np.percentile(arr, 25)),
                'q3': float(np.percentile(arr, 75)),
                'iqr': float(np.percentile(arr, 75) - np.percentile(arr, 25)),
                'count': len(values)
            }
        else:
            sorted_vals = sorted(values)
            n = len(sorted_vals)
            mean = sum(sorted_vals) / n
            variance = sum((x - mean) ** 2 for x in sorted_vals) / n
            std = variance ** 0.5

            return {
                'mean': mean,
                'median': sorted_vals[n // 2],
                'std': std,
                'min': min(sorted_vals),
                'max': max(sorted_vals),
                'range': max(sorted_vals) - min(sorted_vals),
                'count': n
            }

    @staticmethod
    def calculate_trend(values: List[float]) -> Dict[str, Any]:
        """
        Calcula tendencia lineal.

        :param values: Lista de valores
        :return: Dict con slope, intercept, r_squared
        """
        if len(values) < 2:
            return {}

        if HAS_NUMPY:
            x = np.arange(len(values))
            y = np.array(values)

            coefficients = np.polyfit(x, y, 1)
            slope = coefficients[0]
            intercept = coefficients[1]

            y_pred = np.polyval(coefficients, x)
            ss_res = np.sum((y - y_pred) ** 2)
            ss_tot = np.sum((y - np.mean(y)) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
        else:
            n = len(values)
            x = list(range(n))

            mean_x = sum(x) / n
            mean_y = sum(values) / n

            numerator = sum((x[i] - mean_x) * (values[i] - mean_y) for i in range(n))
            denominator = sum((x[i] - mean_x) ** 2 for i in range(n))

            slope = numerator / denominator if denominator else 0
            intercept = mean_y - slope * mean_x

            y_pred = [slope * xi + intercept for xi in x]
            ss_res = sum((values[i] - y_pred[i]) ** 2 for i in range(n))
            ss_tot = sum((values[i] - mean_y) ** 2 for i in range(n))
            r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

        return {
            'slope': float(slope),
            'intercept': float(intercept),
            'r_squared': float(r_squared),
            'direction': 'increasing' if slope > 0 else 'decreasing',
            'strength': 'strong' if abs(r_squared) > 0.7 else 'moderate' if abs(r_squared) > 0.4 else 'weak'
        }

    @staticmethod
    def detect_anomalies(values: List[float], threshold: float = 2.5) -> List[Dict]:
        """
        Detecta anomalias usando Z-score.

        :param values: Lista de valores
        :param threshold: Umbral de Z-score
        :return: Lista de anomalias
        """
        if len(values) < 3:
            return []

        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        std = variance ** 0.5

        if std == 0:
            return []

        anomalies = []
        for i, value in enumerate(values):
            z_score = abs((value - mean) / std)

            if z_score > threshold:
                anomalies.append({
                    'index': i,
                    'value': value,
                    'z_score': z_score,
                    'expected_range': (mean - threshold * std, mean + threshold * std),
                    'severity': 'high' if z_score > 3 else 'medium'
                })

        return anomalies
