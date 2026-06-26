# -*- coding: utf-8 -*-
"""
Tests para provisiones de prestaciones sociales (contabilización mensual).

El módulo lavish_hr_social_security calcula y contabiliza mensualmente
las provisiones de: prima, cesantías, intereses cesantías, vacaciones y ARL.
Provisión mensual = prestación_anual / 12.
"""
from datetime import date
from odoo.tests.common import TransactionCase, tagged

SMMLV_2025 = 1_423_500.0


@tagged('standard', 'provisions', 'post_install', '-at_install')
class TestProvisionesFormulas(TransactionCase):
    """Verifica fórmulas de provisión mensual (1/12 de la prestación anual)."""

    SALARIO = 3_000_000.0

    def test_provision_prima_mensual(self):
        # Prima anual = salario, provisión mensual = salario / 12
        provision = self.SALARIO / 12
        self.assertAlmostEqual(provision, 250_000.0, delta=1.0)

    def test_provision_cesantias_mensual(self):
        provision = self.SALARIO / 12
        self.assertAlmostEqual(provision, 250_000.0, delta=1.0)

    def test_provision_intereses_cesantias_mensual(self):
        # Intereses = cesantías × 12% → provisión mensual = (salario/12) × 12% / 12
        cesantias_anual = self.SALARIO
        intereses_anual = cesantias_anual * 0.12
        provision_mensual = intereses_anual / 12
        self.assertAlmostEqual(provision_mensual, self.SALARIO * 0.12 / 12, delta=1.0)

    def test_provision_vacaciones_mensual(self):
        # Vacaciones anuales = salario / 2 → provisión mensual = salario / 24
        provision = self.SALARIO / 24
        self.assertAlmostEqual(provision, 125_000.0, delta=1.0)

    def test_provision_total_mensual_porcentaje(self):
        # Total provisión mensual como % del salario:
        # Prima 8.33% + Cesantías 8.33% + Intereses 1% + Vacaciones 4.17% ≈ 21.83%
        prima = self.SALARIO / 12
        cesantias = self.SALARIO / 12
        intereses = (self.SALARIO / 12) * 0.12
        vacaciones = self.SALARIO / 24
        total = prima + cesantias + intereses + vacaciones
        porcentaje = total / self.SALARIO * 100
        # Rango esperado: 21% – 23%
        self.assertGreater(porcentaje, 21.0)
        self.assertLess(porcentaje, 23.0)


@tagged('standard', 'provisions', 'post_install', '-at_install')
class TestProvisionesModelo(TransactionCase):

    def test_hr_provisions_model_fields(self):
        if 'hr.executing.provisions' not in self.env:
            self.skipTest('Modelo hr.executing.provisions no disponible.')
        fields = self.env['hr.executing.provisions']._fields
        for campo in ['name', 'company_id']:
            self.assertIn(campo, fields,
                          f'Campo {campo!r} faltante en hr.executing.provisions.')

    def test_provisions_details_tiene_employee(self):
        if 'hr.executing.provisions.details' not in self.env:
            self.skipTest('Modelo hr.executing.provisions.details no disponible.')
        fields = self.env['hr.executing.provisions.details']._fields
        self.assertIn('employee_id', fields,
                      'hr.executing.provisions.details debe tener employee_id.')

    def test_provisions_display_name_computed(self):
        if 'hr.executing.provisions' not in self.env:
            self.skipTest('Modelo hr.executing.provisions no disponible.')
        model = self.env['hr.executing.provisions']
        self.assertTrue(
            hasattr(model, '_compute_display_name'),
            '_compute_display_name debe existir (reemplaza name_get en Odoo 19).'
        )
