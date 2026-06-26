# -*- coding: utf-8 -*-
"""
Tests para cálculo de salario básico proporcional y promedio ponderado.
Cubre: calculate_proportional_salary, calculate_weighted_average_wage.
"""
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.lavish_hr_employee.models.reglas.basic import (
    calculate_proportional_salary,
    calculate_weighted_average_wage,
    get_wage_changes_in_period,
)


# ─── Tests de funciones puras (sin BD) ───────────────────────────────────────

class TestCalculateProportionalSalary:
    """calculate_proportional_salary: salario/30 × días."""

    def test_mes_completo(self):
        r = calculate_proportional_salary(3_000_000, 30)
        assert r['total'] == 3_000_000.0
        assert r['rate'] == 100_000.0
        assert r['quantity'] == 30

    def test_quincena(self):
        r = calculate_proportional_salary(3_000_000, 15)
        assert r['total'] == 1_500_000.0
        assert r['rate'] == 100_000.0

    def test_un_dia(self):
        r = calculate_proportional_salary(3_000_000, 1)
        assert abs(r['total'] - 100_000.0) < 0.01

    def test_salario_minimo_2025(self):
        # SMMLV 2025 = 1.423.500
        r = calculate_proportional_salary(1_423_500, 30)
        assert r['total'] == 1_423_500.0

    def test_por_horas(self):
        r = calculate_proportional_salary(3_000_000, 0, is_hourly=True,
                                          hours_monthly=240, hours_worked=120)
        assert abs(r['total'] - 1_500_000.0) < 0.01
        assert r['quantity'] == 120

    def test_zero_dias(self):
        r = calculate_proportional_salary(3_000_000, 0)
        assert r['total'] == 0.0

    def test_salario_integral(self):
        # 13 SMMLV = 18.505.500 (2025)
        r = calculate_proportional_salary(18_505_500, 30)
        assert r['total'] == 18_505_500.0

    def test_dias_mayor_30(self):
        # No debe bloquearse con 31 días (podría ocurrir en algunos períodos)
        r = calculate_proportional_salary(3_000_000, 31)
        assert abs(r['total'] - 3_100_000.0) < 0.01


# ─── Tests de calculate_weighted_average_wage (requiere mock de contract) ───

@tagged('standard', 'salario_basico', 'post_install', '-at_install')
class TestWeightedAverageWage(TransactionCase):

    def _make_contract(self, wage, changes=None):
        """Crea un SimpleNamespace que simula hr.contract con historial de cambios."""
        contract = SimpleNamespace(wage=wage)
        mock_changes = changes or []
        return contract, mock_changes

    def test_sin_cambios_salario_uniforme(self):
        contract = SimpleNamespace(wage=3_000_000)
        with patch('odoo.addons.lavish_hr_employee.models.reglas.basic.get_wage_changes_in_period',
                   return_value=[]):
            r = calculate_weighted_average_wage(
                contract, date(2025, 1, 1), date(2025, 1, 31)
            )
        self.assertEqual(r['salario_promedio'], 3_000_000)
        self.assertFalse(r['tiene_cambios'])
        self.assertEqual(r['dias_totales'], 30)

    def test_con_aumento_a_mitad_del_mes(self):
        # Ene 1-15: 2.000.000 / Ene 16-31: 3.000.000 → promedio ponderado
        contract = SimpleNamespace(wage=3_000_000)
        cambio = SimpleNamespace(date_start=date(2025, 1, 16), wage=3_000_000)
        with patch('odoo.addons.lavish_hr_employee.models.reglas.basic.get_wage_changes_in_period',
                   return_value=[cambio]):
            # El contrato empieza con 2.000.000
            contract.wage = 2_000_000
            # Después del cambio pasa a 3.000.000
            r = calculate_weighted_average_wage(
                contract, date(2025, 1, 1), date(2025, 1, 31)
            )
        self.assertTrue(r['tiene_cambios'])
        # 15 días × 2M + 15 días × 3M / 30 = 2.500.000
        self.assertAlmostEqual(r['salario_promedio'], 2_500_000.0, delta=1.0)

    def test_periodo_vacio(self):
        contract = SimpleNamespace(wage=3_000_000)
        with patch('odoo.addons.lavish_hr_employee.models.reglas.basic.get_wage_changes_in_period',
                   return_value=[]):
            r = calculate_weighted_average_wage(
                contract, date(2025, 1, 15), date(2025, 1, 14)  # fecha_fin < fecha_inicio
            )
        self.assertEqual(r['dias_totales'], 0)

    def test_factor_tiempo_parcial(self):
        contract = SimpleNamespace(wage=3_000_000)
        with patch('odoo.addons.lavish_hr_employee.models.reglas.basic.get_wage_changes_in_period',
                   return_value=[]):
            r = calculate_weighted_average_wage(
                contract, date(2025, 1, 1), date(2025, 1, 31), parcial_factor=0.5
            )
        self.assertAlmostEqual(r['salario_promedio'], 1_500_000.0, delta=1.0)

    def test_segmentos_contados_correctamente(self):
        contract = SimpleNamespace(wage=3_000_000)
        cambio1 = SimpleNamespace(date_start=date(2025, 1, 11), wage=3_500_000)
        cambio2 = SimpleNamespace(date_start=date(2025, 1, 21), wage=4_000_000)
        with patch('odoo.addons.lavish_hr_employee.models.reglas.basic.get_wage_changes_in_period',
                   return_value=[cambio1, cambio2]):
            contract.wage = 3_000_000
            r = calculate_weighted_average_wage(
                contract, date(2025, 1, 1), date(2025, 1, 31)
            )
        self.assertTrue(r['tiene_cambios'])
        self.assertEqual(len(r['segmentos']), 3)
        self.assertEqual(r['dias_totales'], 30)
