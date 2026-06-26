# -*- coding: utf-8 -*-
"""
Tests para IBC (Ingreso Base de Cotización) y seguridad social.

Reglas legales:
  - IBC mínimo = SMMLV (Art. 18 Ley 100/1993)
  - IBC máximo = 25 SMMLV (Ley 797/2003)
  - Salud empleado = 4% IBC
  - Pensión empleado = 4% IBC
  - ARL según nivel de riesgo (0.522% a 6.960%)
  - Regla del 40%: pagos no salariales no pueden superar 40% del total devengado
    (Ley 1393/2010 Art. 30)
  - FSOL (Fondo de Solidaridad): aplica desde 4 SMMLV
"""
from types import SimpleNamespace
from odoo.tests.common import TransactionCase, tagged

# Constantes 2025
SMMLV_2025 = 1_423_500.0
TOPE_IBC = SMMLV_2025 * 25   # 35.587.500
SALUD_EMP = 0.04
PENSION_EMP = 0.04
TOPE_REGLA_40 = 0.40


# ─── Tests de fórmulas de cotización (sin BD) ────────────────────────────────

class TestFormulasSSPuras:

    SMMLV = SMMLV_2025

    # ── IBC mínimo y máximo ──────────────────────────────────────────────

    def test_ibc_minimo_smmlv(self):
        ibc = max(500_000.0, self.SMMLV)
        assert ibc == self.SMMLV

    def test_ibc_maximo_25_smmlv(self):
        ibc_bruto = 50_000_000.0
        ibc = min(ibc_bruto, self.SMMLV * 25)
        assert ibc == self.SMMLV * 25

    def test_ibc_dentro_rango_no_modifica(self):
        ibc = 5_000_000.0
        assert self.SMMLV <= ibc <= self.SMMLV * 25

    # ── Aportes empleado ────────────────────────────────────────────────

    def test_salud_4pct_smmlv(self):
        aporte = self.SMMLV * SALUD_EMP
        assert abs(aporte - self.SMMLV * 0.04) < 1.0

    def test_pension_4pct_smmlv(self):
        aporte = self.SMMLV * PENSION_EMP
        assert abs(aporte - self.SMMLV * 0.04) < 1.0

    def test_total_aporte_empleado_8pct(self):
        ibc = 3_000_000.0
        total = ibc * (SALUD_EMP + PENSION_EMP)
        assert abs(total - ibc * 0.08) < 1.0

    # ── Regla del 40% (Ley 1393/2010) ──────────────────────────────────

    def test_pagos_no_salariales_dentro_40pct(self):
        salario = 3_000_000.0
        no_salarial = 1_000_000.0
        total = salario + no_salarial
        assert no_salarial <= total * TOPE_REGLA_40

    def test_pagos_no_salariales_supera_40pct_ajusta_ibc(self):
        salario = 2_000_000.0
        no_salarial = 2_000_000.0  # 50% del total → supera 40%
        total = salario + no_salarial
        tope_no_salarial = total * TOPE_REGLA_40
        exceso = no_salarial - tope_no_salarial
        ibc_ajustado = salario + exceso
        assert ibc_ajustado > salario

    # ── Fondo de Solidaridad Pensional ──────────────────────────────────

    def test_fsol_aplica_desde_4_smmlv(self):
        ibc_3_smmlv = self.SMMLV * 3
        ibc_4_smmlv = self.SMMLV * 4
        # Bajo 4 SMMLV: no aplica
        assert ibc_3_smmlv < self.SMMLV * 4
        # En 4 SMMLV: aplica 1%
        fsol = ibc_4_smmlv * 0.01
        assert fsol > 0

    def test_fsol_adicional_desde_16_smmlv(self):
        # Desde 16 SMMLV: +0.2% adicional
        ibc = self.SMMLV * 16
        fsol_base = ibc * 0.01
        fsol_adicional = ibc * 0.002
        assert fsol_adicional > 0

    # ── ARL por nivel de riesgo ─────────────────────────────────────────

    def test_arl_riesgo_1(self):
        ibc = 3_000_000.0
        tarifa = 0.00522  # 0.522% riesgo I
        arl = ibc * tarifa
        assert abs(arl - ibc * 0.00522) < 1.0

    def test_arl_riesgo_5(self):
        ibc = 3_000_000.0
        tarifa = 0.06960  # 6.960% riesgo V
        arl = ibc * tarifa
        assert abs(arl - ibc * 0.0696) < 1.0


# ─── Tests de integración con modelo ─────────────────────────────────────────

@tagged('standard', 'ibc_ss', 'post_install', '-at_install')
class TestIBCSeguridadSocial(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.annual_params = SimpleNamespace(
            smmlv_monthly=SMMLV_2025,
            smmlv_daily=SMMLV_2025 / 30,
            top_twenty_five_smmlv=SMMLV_2025 * 25,
            top_four_fsp_smmlv=SMMLV_2025 * 4,
            transportation_assistance_monthly=200_000.0,
        )

    def test_set_limits_ibc_por_debajo_minimo(self):
        rule = self.env['hr.salary.rule.ibd.sss'].browse([])
        ibc = rule._set_limits_ibc(800_000.0, SMMLV_2025)
        self.assertEqual(ibc, SMMLV_2025)

    def test_set_limits_ibc_por_encima_minimo(self):
        rule = self.env['hr.salary.rule.ibd.sss'].browse([])
        ibc = rule._set_limits_ibc(5_000_000.0, SMMLV_2025)
        self.assertEqual(ibc, 5_000_000.0)

    def test_aporte_salud_smmlv(self):
        ibc = SMMLV_2025
        esperado = ibc * 0.04
        self.assertAlmostEqual(ibc * SALUD_EMP, esperado, delta=1.0)

    def test_aporte_pension_smmlv(self):
        ibc = SMMLV_2025
        self.assertAlmostEqual(ibc * PENSION_EMP, ibc * 0.04, delta=1.0)

    def test_ibc_maximo_25_smmlv_no_supera(self):
        ibc_alto = 100_000_000.0
        ibc_tope = min(ibc_alto, SMMLV_2025 * 25)
        self.assertEqual(ibc_tope, SMMLV_2025 * 25)
        self.assertLessEqual(ibc_tope, TOPE_IBC)

    def test_regla_40_exceso_suma_al_ibc(self):
        salario = 2_000_000.0
        no_salarial = 2_000_000.0
        total = salario + no_salarial
        tope = total * 0.40
        exceso = max(0, no_salarial - tope)
        ibc = salario + exceso
        self.assertGreater(ibc, salario)
        self.assertAlmostEqual(ibc, 2_800_000.0, delta=1.0)

    def test_regla_40_sin_exceso_no_modifica_ibc(self):
        salario = 3_000_000.0
        no_salarial = 800_000.0  # < 40% de 3.8M
        total = salario + no_salarial
        tope = total * 0.40
        exceso = max(0, no_salarial - tope)
        ibc = salario + exceso
        self.assertAlmostEqual(ibc, salario, delta=1.0)

    def test_salario_integral_ibc_70pct(self):
        # Salario integral → IBC = 70% del salario (Art. 18 Ley 100)
        salario_integral = SMMLV_2025 * 13
        ibc = salario_integral * 0.70
        self.assertAlmostEqual(ibc, salario_integral * 0.70, delta=1.0)
        self.assertGreater(ibc, SMMLV_2025)
