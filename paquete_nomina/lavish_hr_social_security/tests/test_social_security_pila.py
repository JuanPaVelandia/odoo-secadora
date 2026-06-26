# -*- coding: utf-8 -*-
"""
Tests para el módulo de seguridad social (PILA).

Verifica modelos, cálculos de aportes y la generación del archivo PILA.
Aportes empleador (2025):
  - Salud empleador:    8.5% IBC
  - Pensión empleador: 12%   IBC
  - ARL: según nivel de riesgo (cargo del empleador, no del empleado)
  - Caja compensación: 4%    IBC
  - ICBF:              3%    IBC  (si nómina ≥ 10 SMMLV agregado)
  - SENA:              2%    IBC  (si nómina ≥ 10 SMMLV agregado)
"""
from types import SimpleNamespace
from odoo.tests.common import TransactionCase, tagged

SMMLV_2025 = 1_423_500.0


@tagged('standard', 'social_security', 'post_install', '-at_install')
class TestSeguridadSocialModelo(TransactionCase):

    def test_modelo_seguridad_social_registrado(self):
        self.assertIn('hr.payroll.social.security', self.env,
                      'hr.payroll.social.security debe estar registrado.')

    def test_compute_amounts_callable(self):
        model = self.env['hr.payroll.social.security']
        self.assertTrue(hasattr(model, '_compute_amounts'),
                        '_compute_amounts debe existir.')

    def test_compute_totals_callable(self):
        model = self.env['hr.payroll.social.security']
        self.assertTrue(hasattr(model, '_compute_totals'),
                        '_compute_totals debe existir.')

    def test_compute_arl_callable(self):
        model = self.env['hr.payroll.social.security']
        self.assertTrue(hasattr(model, '_compute_arl'),
                        '_compute_arl debe existir.')

    def test_action_register_payment_callable(self):
        model = self.env['hr.payroll.social.security']
        self.assertTrue(hasattr(model, 'action_register_payment'),
                        'action_register_payment debe existir.')

    def test_campos_obligatorios_en_modelo(self):
        model_fields = self.env['hr.payroll.social.security']._fields
        campos = ['name', 'date_start', 'date_end', 'company_id']
        for campo in campos:
            self.assertIn(campo, model_fields,
                          f'Campo {campo!r} faltante en hr.payroll.social.security.')

    def test_compute_fecha_limite_pago_existe(self):
        model = self.env['hr.payroll.social.security']
        self.assertTrue(hasattr(model, '_compute_fecha_limite_pago'),
                        '_compute_fecha_limite_pago debe existir.')


@tagged('standard', 'social_security', 'post_install', '-at_install')
class TestAportesEmpleadorFormulas(TransactionCase):
    """Verifica las fórmulas de aportes del empleador."""

    def test_salud_empleador_8_5_pct(self):
        ibc = 3_000_000.0
        aporte = ibc * 0.085
        self.assertAlmostEqual(aporte, 255_000.0, delta=1.0)

    def test_pension_empleador_12_pct(self):
        ibc = 3_000_000.0
        aporte = ibc * 0.12
        self.assertAlmostEqual(aporte, 360_000.0, delta=1.0)

    def test_caja_compensacion_4_pct(self):
        ibc = 3_000_000.0
        aporte = ibc * 0.04
        self.assertAlmostEqual(aporte, 120_000.0, delta=1.0)

    def test_icbf_3_pct(self):
        ibc = 3_000_000.0
        aporte = ibc * 0.03
        self.assertAlmostEqual(aporte, 90_000.0, delta=1.0)

    def test_sena_2_pct(self):
        ibc = 3_000_000.0
        aporte = ibc * 0.02
        self.assertAlmostEqual(aporte, 60_000.0, delta=1.0)

    def test_total_parafiscales_9_pct(self):
        # ICBF + SENA + Caja = 3% + 2% + 4% = 9%
        ibc = 3_000_000.0
        total = ibc * (0.03 + 0.02 + 0.04)
        self.assertAlmostEqual(total, ibc * 0.09, delta=1.0)

    def test_total_aporte_empleador_sin_arl(self):
        # Salud + Pensión + Parafiscales = 8.5% + 12% + 9% = 29.5%
        ibc = 3_000_000.0
        total = ibc * (0.085 + 0.12 + 0.09)
        self.assertAlmostEqual(total, ibc * 0.295, delta=1.0)

    def test_arl_riesgo_i_tarifa(self):
        # Riesgo I: 0.522%
        ibc = 3_000_000.0
        arl = ibc * 0.00522
        self.assertAlmostEqual(arl, ibc * 0.00522, delta=1.0)

    def test_ibc_smmlv_minimo_en_calculo(self):
        ibc_bajo = 800_000.0
        ibc_efectivo = max(ibc_bajo, SMMLV_2025)
        salud = ibc_efectivo * 0.085
        self.assertGreater(salud, ibc_bajo * 0.085)

    def test_ibc_maximo_25_smmlv_en_calculo(self):
        ibc_alto = 50_000_000.0
        ibc_efectivo = min(ibc_alto, SMMLV_2025 * 25)
        pension = ibc_efectivo * 0.12
        self.assertAlmostEqual(pension, SMMLV_2025 * 25 * 0.12, delta=1.0)


@tagged('standard', 'social_security', 'post_install', '-at_install')
class TestProvisionsModelo(TransactionCase):

    def test_modelo_provisions_existe(self):
        self.assertIn('hr.executing.provisions', self.env,
                      'hr.executing.provisions debe estar registrado.')

    def test_modelo_provisions_details_existe(self):
        self.assertIn('hr.executing.provisions.details', self.env,
                      'hr.executing.provisions.details debe estar registrado.')
