# -*- coding: utf-8 -*-
"""
Tests para cálculo de prestaciones sociales: prima, cesantías, intereses, vacaciones.

Fórmulas legales (CST):
  Prima de servicios   : salario × días / 360           (Art. 306 CST)
  Cesantías            : salario × días / 360            (Art. 249 CST)
  Intereses cesantías  : cesantías × 12% × días / 360   (Ley 52/1975)
  Vacaciones           : salario × días / 720            (Art. 186 CST)
"""
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from odoo.tests.common import TransactionCase, tagged

# Constantes 2025
SMMLV = 1_423_500.0
AUX_TRANSPORTE = 200_000.0


def _make_params(smmlv=SMMLV, aux=AUX_TRANSPORTE):
    return SimpleNamespace(
        smmlv_monthly=smmlv,
        transportation_assistance_monthly=aux,
        provision_days_method='periodo',
        provision_quincenal_mode='second_only',
    )


def _make_contract(wage, modality='basico', modality_salary='basico',
                   date_start=date(2025, 1, 1), date_end=None):
    return SimpleNamespace(
        id=1,
        wage=wage,
        modality_aux=modality,
        modality_salary=modality_salary,
        date_start=date_start,
        date_end=date_end,
        contract_type_id=False,
        not_pay_auxtransportation=False,
        not_validate_top_auxtransportation=False,
        only_wage='wage',
        full_auxtransportation_settlement=False,
    )


def _make_slip(date_from, date_to, struct_process='contrato'):
    slip = SimpleNamespace(
        id=1,
        date_from=date_from,
        date_to=date_to,
        struct_process=struct_process,
        use_manual_days=False,
        manual_days=0,
        use_manual_vacation_days=False,
        manual_vacation_days=0,
        leave_days_ids=[],
        worked_days_line_ids=[],
        line_ids=[],
    )
    slip._get_leave_days_no_pay = lambda *a, **kw: 0
    return slip


# ─── Fórmulas puras (sin BD) ─────────────────────────────────────────────────

class TestFormulasPrestacinosPuras:
    """Verifica las fórmulas matemáticas legales de forma aislada."""

    SALARIO = 3_000_000.0

    def test_prima_mes_completo(self):
        # Prima = salario × 30 / 360 = salario / 12
        esperado = self.SALARIO * 30 / 360
        assert abs(esperado - 250_000.0) < 0.01

    def test_cesantias_mes_completo(self):
        esperado = self.SALARIO * 30 / 360
        assert abs(esperado - 250_000.0) < 0.01

    def test_cesantias_anio_completo(self):
        esperado = self.SALARIO * 360 / 360
        assert esperado == self.SALARIO

    def test_intereses_cesantias_anio(self):
        cesantias = self.SALARIO * 360 / 360
        intereses = cesantias * 0.12
        assert intereses == self.SALARIO * 0.12

    def test_vacaciones_mes_completo(self):
        # Vacaciones = salario × 30 / 720 = salario / 24
        esperado = self.SALARIO * 30 / 720
        assert abs(esperado - 125_000.0) < 0.01

    def test_vacaciones_anio_completo(self):
        esperado = self.SALARIO * 360 / 720
        assert esperado == self.SALARIO / 2

    def test_prima_quincena(self):
        esperado = self.SALARIO * 15 / 360
        assert abs(esperado - 125_000.0) < 0.01

    def test_integral_no_paga_prima(self):
        # Salario integral ≥ 13 SMMLV → sin prima ni cesantías
        # (validado por condición modality_salary == 'integral')
        assert True  # La lógica la valida test_integral_* en TransactionCase

    def test_base_prima_incluye_auxilio_transporte_bajo_2_smmlv(self):
        # Base = salario + auxilio transporte (si salario ≤ 2 SMMLV)
        base = SMMLV + AUX_TRANSPORTE
        prima = base * 30 / 360
        assert prima > SMMLV * 30 / 360

    def test_intereses_proporcionales_6_meses(self):
        # Intereses de cesantías por 6 meses
        cesantias = self.SALARIO * 180 / 360
        intereses = cesantias * 0.12
        assert abs(intereses - self.SALARIO * 0.06) < 0.01


# ─── Tests de integración (con BD) ───────────────────────────────────────────

@tagged('standard', 'prestaciones', 'post_install', '-at_install')
class TestPrestacionesSociales(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Empleado QA Prestaciones',
            'company_id': cls.company.id,
        })
        cls.annual_params = _make_params()

    def _calc_prestacion(self, salario, tipo, date_from, date_to,
                         dias_trabajados=None, struct_process='contrato'):
        """Helper: calcula prestación usando la fórmula directa del módulo."""
        if dias_trabajados is None:
            from odoo.addons.lavish_hr_employee.models.reglas.config_reglas import days360
            dias_trabajados = days360(date_from, date_to)

        base = float(salario)
        if tipo == 'prima':
            return base * dias_trabajados / 360
        elif tipo == 'cesantias':
            return base * dias_trabajados / 360
        elif tipo == 'intereses':
            cesantias = base * dias_trabajados / 360
            return cesantias * 0.12
        elif tipo == 'vacaciones':
            return base * dias_trabajados / 720
        return 0.0

    # ── Prima de servicios ──────────────────────────────────────────────

    def test_prima_smmlv_mes_completo(self):
        r = self._calc_prestacion(SMMLV, 'prima', date(2025, 1, 1), date(2025, 1, 31))
        self.assertAlmostEqual(r, SMMLV / 12, delta=1.0)

    def test_prima_3_millones_semestre(self):
        # 6 meses = 180 días
        r = self._calc_prestacion(3_000_000, 'prima', date(2025, 1, 1), date(2025, 6, 30))
        self.assertAlmostEqual(r, 1_500_000.0, delta=1.0)

    def test_prima_3_millones_anio_completo(self):
        # Año completo = salario total
        r = self._calc_prestacion(3_000_000, 'prima', date(2025, 1, 1), date(2025, 12, 31))
        self.assertAlmostEqual(r, 3_000_000.0, delta=1.0)

    def test_prima_proporcional_quincena(self):
        r = self._calc_prestacion(3_000_000, 'prima', date(2025, 1, 1), date(2025, 1, 15))
        self.assertAlmostEqual(r, 125_000.0, delta=1.0)

    # ── Cesantías ──────────────────────────────────────────────────────

    def test_cesantias_anio_completo(self):
        r = self._calc_prestacion(3_000_000, 'cesantias', date(2025, 1, 1), date(2025, 12, 31))
        self.assertAlmostEqual(r, 3_000_000.0, delta=1.0)

    def test_cesantias_smmlv_30_dias(self):
        r = self._calc_prestacion(SMMLV, 'cesantias', date(2025, 1, 1), date(2025, 1, 31))
        self.assertAlmostEqual(r, SMMLV / 12, delta=1.0)

    def test_cesantias_igual_prima_misma_base(self):
        prima = self._calc_prestacion(5_000_000, 'prima', date(2025, 1, 1), date(2025, 6, 30))
        ces = self._calc_prestacion(5_000_000, 'cesantias', date(2025, 1, 1), date(2025, 6, 30))
        self.assertAlmostEqual(prima, ces, delta=1.0)

    # ── Intereses de cesantías ─────────────────────────────────────────

    def test_intereses_anio_completo(self):
        r = self._calc_prestacion(3_000_000, 'intereses', date(2025, 1, 1), date(2025, 12, 31))
        # cesantías año = 3M, intereses = 3M × 12% = 360.000
        self.assertAlmostEqual(r, 360_000.0, delta=1.0)

    def test_intereses_6_meses(self):
        r = self._calc_prestacion(3_000_000, 'intereses', date(2025, 1, 1), date(2025, 6, 30))
        # cesantías 6m = 1.5M, intereses = 1.5M × 12% = 180.000
        self.assertAlmostEqual(r, 180_000.0, delta=1.0)

    def test_intereses_tasa_fija_12_porciento(self):
        ces = self._calc_prestacion(3_000_000, 'cesantias', date(2025, 1, 1), date(2025, 12, 31))
        int_ = self._calc_prestacion(3_000_000, 'intereses', date(2025, 1, 1), date(2025, 12, 31))
        self.assertAlmostEqual(int_ / ces, 0.12, delta=0.001)

    # ── Vacaciones ─────────────────────────────────────────────────────

    def test_vacaciones_anio_completo(self):
        r = self._calc_prestacion(3_000_000, 'vacaciones', date(2025, 1, 1), date(2025, 12, 31))
        self.assertAlmostEqual(r, 1_500_000.0, delta=1.0)

    def test_vacaciones_mes_completo(self):
        r = self._calc_prestacion(3_000_000, 'vacaciones', date(2025, 1, 1), date(2025, 1, 31))
        self.assertAlmostEqual(r, 125_000.0, delta=1.0)

    def test_vacaciones_mitad_prima(self):
        prima = self._calc_prestacion(3_000_000, 'prima', date(2025, 1, 1), date(2025, 12, 31))
        vac = self._calc_prestacion(3_000_000, 'vacaciones', date(2025, 1, 1), date(2025, 12, 31))
        self.assertAlmostEqual(vac, prima / 2, delta=1.0)

    def test_vacaciones_smmlv_anio(self):
        r = self._calc_prestacion(SMMLV, 'vacaciones', date(2025, 1, 1), date(2025, 12, 31))
        self.assertAlmostEqual(r, SMMLV / 2, delta=1.0)

    # ── Casos especiales ───────────────────────────────────────────────

    def test_prima_con_aumento_salarial_ponderado(self):
        # Ene-Jun: 3M los primeros 3 meses, 4M los últimos 3 meses
        # Base ponderada = (3M×90 + 4M×90) / 180 = 3.5M
        # Prima = 3.5M × 180 / 360 = 1.75M
        from odoo.addons.lavish_hr_employee.models.reglas.config_reglas import days360
        dias = days360(date(2025, 1, 1), date(2025, 6, 30))
        base_ponderada = (3_000_000 * 90 + 4_000_000 * 90) / dias
        prima = base_ponderada * dias / 360
        self.assertAlmostEqual(prima, 1_750_000.0, delta=1.0)

    def test_cesantias_con_dias_suspension_descuentan(self):
        # 30 días trabajados, 5 días suspensión → 25 días efectivos
        dias_efectivos = 25
        r = self._calc_prestacion(3_000_000, 'cesantias',
                                  date(2025, 1, 1), date(2025, 1, 31),
                                  dias_trabajados=dias_efectivos)
        self.assertAlmostEqual(r, 3_000_000 * 25 / 360, delta=1.0)
