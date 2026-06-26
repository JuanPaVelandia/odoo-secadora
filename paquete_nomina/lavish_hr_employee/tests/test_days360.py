# -*- coding: utf-8 -*-
"""
Tests para la función days360 (método comercial colombiano).
Sin dependencia de BD — se ejecutan como unittest puro.
"""
from datetime import date
from unittest import TestCase

from odoo.addons.lavish_hr_employee.models.reglas.config_reglas import days360


class TestDays360(TestCase):
    """Método comercial 360: cada mes = 30 días, año = 360 días."""

    def test_mes_completo_enero(self):
        self.assertEqual(days360(date(2025, 1, 1), date(2025, 1, 31)), 30)

    def test_mes_completo_febrero_no_bisiesto(self):
        # Feb 28 se trata como día 30
        self.assertEqual(days360(date(2025, 2, 1), date(2025, 2, 28)), 30)

    def test_mes_completo_febrero_bisiesto(self):
        # Feb 29 también se trata como día 30
        self.assertEqual(days360(date(2024, 2, 1), date(2024, 2, 29)), 30)

    def test_mes_completo_marzo(self):
        self.assertEqual(days360(date(2025, 3, 1), date(2025, 3, 31)), 30)

    def test_quincena_primera(self):
        self.assertEqual(days360(date(2025, 1, 1), date(2025, 1, 15)), 15)

    def test_quincena_segunda(self):
        self.assertEqual(days360(date(2025, 1, 16), date(2025, 1, 31)), 15)

    def test_anio_completo(self):
        self.assertEqual(days360(date(2025, 1, 1), date(2025, 12, 31)), 360)

    def test_dia_31_inicio_equivale_30(self):
        # 31 de enero al 31 de enero = 1 día (mismo día)
        self.assertEqual(days360(date(2025, 1, 31), date(2025, 1, 31)), 1)

    def test_dia_31_inicio_al_siguiente_mes(self):
        # 31 ene → 28 feb = 30 días (31→30, 28→30: (30-1)*30 + (30-30) + 1 = 30)
        self.assertEqual(days360(date(2025, 1, 31), date(2025, 2, 28)), 30)

    def test_mismo_dia(self):
        self.assertEqual(days360(date(2025, 6, 15), date(2025, 6, 15)), 1)

    def test_fechas_none(self):
        self.assertEqual(days360(None, date(2025, 1, 31)), 0)
        self.assertEqual(days360(date(2025, 1, 1), None), 0)
        self.assertEqual(days360(None, None), 0)

    def test_tres_meses(self):
        self.assertEqual(days360(date(2025, 1, 1), date(2025, 3, 31)), 90)

    def test_semestre(self):
        self.assertEqual(days360(date(2025, 1, 1), date(2025, 6, 30)), 180)

    def test_periodo_enero_a_junio_con_dia_31(self):
        # 1 ene al 30 jun: 6 meses × 30 = 180
        self.assertEqual(days360(date(2025, 1, 1), date(2025, 6, 30)), 180)

    def test_cruce_anio(self):
        # 1 dic 2024 al 28 feb 2025 = 2 meses + 27 días → 87 días
        # (2025-2024)*360 + (2-12)*30 + (30-1) + 1 = 360 - 300 + 29 + 1 = 90
        self.assertEqual(days360(date(2024, 12, 1), date(2025, 2, 28)), 90)
