# -*- coding: utf-8 -*-
"""
Tests para cálculo de auxilio de transporte.
Cubre: tope salarial 2 SMMLV, proporcionalidad por días, modalidades.
"""
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from odoo.tests.common import TransactionCase, tagged


# Valores legales 2025
SMMLV_2025 = 1_423_500.0
AUX_TRANSPORTE_2025 = 200_000.0  # decreto vigente 2025
TOPE_AUX = SMMLV_2025 * 2  # 2.847.000 — por encima no paga auxilio


def _make_annual_params(smmlv=SMMLV_2025, aux=AUX_TRANSPORTE_2025):
    return SimpleNamespace(
        smmlv_monthly=smmlv,
        transportation_assistance_monthly=aux,
        top_max_transportation_assistance=smmlv * 2,
    )


def _make_contract(wage, modality_aux='basico', not_pay_auxtransportation=False):
    return SimpleNamespace(
        wage=wage,
        modality_aux=modality_aux,
        not_pay_auxtransportation=not_pay_auxtransportation,
        not_validate_top_auxtransportation=False,
    )


@tagged('standard', 'auxilio_transporte', 'post_install', '-at_install')
class TestAuxilioTransporte(TransactionCase):

    def setUp(self):
        super().setUp()
        self.rule = self.env['hr.salary.rule.aux'].browse([])

    def _calc(self, contract, annual_parameters, dias_pagados=30, dias_periodo=30):
        return self.rule._calcular_auxilio_provision(
            annual_parameters, contract, dias_pagados, dias_periodo=dias_periodo
        )

    def test_salario_bajo_tope_paga_auxilio_completo(self):
        contract = _make_contract(SMMLV_2025)
        params = _make_annual_params()
        r = self._calc(contract, params, 30)
        self.assertEqual(r['modality_aux'], 'basico')
        self.assertAlmostEqual(r['auxilio'], AUX_TRANSPORTE_2025, delta=1.0)

    def test_salario_igual_tope_no_paga_auxilio(self):
        contract = _make_contract(TOPE_AUX)
        params = _make_annual_params()
        r = self._calc(contract, params, 30)
        self.assertEqual(r['auxilio'], 0)

    def test_salario_sobre_tope_no_paga_auxilio(self):
        contract = _make_contract(TOPE_AUX + 1)
        params = _make_annual_params()
        r = self._calc(contract, params, 30)
        self.assertEqual(r['auxilio'], 0)

    def test_modalidad_no_no_paga(self):
        contract = _make_contract(SMMLV_2025, modality_aux='no')
        params = _make_annual_params()
        r = self._calc(contract, params, 30)
        self.assertEqual(r['auxilio'], 0)
        self.assertEqual(r['modality_aux'], 'no')

    def test_proporcional_quincena(self):
        contract = _make_contract(SMMLV_2025)
        params = _make_annual_params()
        r = self._calc(contract, params, dias_pagados=15, dias_periodo=30)
        esperado = AUX_TRANSPORTE_2025 / 30 * 15
        self.assertAlmostEqual(r['auxilio'], esperado, delta=1.0)

    def test_proporcional_un_dia(self):
        contract = _make_contract(SMMLV_2025)
        params = _make_annual_params()
        r = self._calc(contract, params, dias_pagados=1, dias_periodo=30)
        esperado = AUX_TRANSPORTE_2025 / 30
        self.assertAlmostEqual(r['auxilio'], esperado, delta=1.0)

    def test_sin_parametros_anuales_retorna_cero(self):
        contract = _make_contract(SMMLV_2025)
        r = self._calc(contract, None, 30)
        self.assertEqual(r['auxilio'], 0)

    def test_dos_smmlv_menos_un_peso_paga_auxilio(self):
        contract = _make_contract(TOPE_AUX - 1)
        params = _make_annual_params()
        r = self._calc(contract, params, 30)
        self.assertGreater(r['auxilio'], 0)

    def test_salario_integral_no_paga_auxilio(self):
        # Salario integral ≥ 13 SMMLV → nunca paga auxilio
        contract = _make_contract(SMMLV_2025 * 13, modality_aux='basico')
        params = _make_annual_params()
        r = self._calc(contract, params, 30)
        self.assertEqual(r['auxilio'], 0)
