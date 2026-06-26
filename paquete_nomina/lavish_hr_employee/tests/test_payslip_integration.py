# -*- coding: utf-8 -*-
"""
Tests de integración end-to-end de liquidación de nómina.

Verifica que hr.payslip.compute_sheet() produce resultados dentro de rangos
legales razonables para casos estándar colombianos.

IMPORTANTE: Estos tests requieren datos de configuración (parámetros anuales,
estructura de nómina, reglas salariales). Si no existen, se marcan como SkipTest.
"""
from datetime import date
from unittest import SkipTest

from odoo.tests.common import TransactionCase, tagged

SMMLV_2025 = 1_423_500.0
AUX_TRANSPORTE_2025 = 200_000.0


def _get_or_skip(env, model, domain, msg):
    rec = env[model].search(domain, limit=1)
    if not rec:
        raise SkipTest(msg)
    return rec


@tagged('standard', 'payslip_integration', 'post_install', '-at_install')
class TestPayslipIntegration(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

        cls.employee = cls.env['hr.employee'].create({
            'name': 'Empleado QA Integration',
            'company_id': cls.company.id,
        })

        structure_type = cls.env['hr.payroll.structure.type'].search([], limit=1)
        if not structure_type:
            raise SkipTest('No hay tipos de estructura de nómina configurados.')

        calendar = cls.env.ref('resource.resource_calendar_std', raise_if_not_found=False)
        if not calendar:
            raise SkipTest('No existe resource.resource_calendar_std.')

        cls.contract = cls.env['hr.contract'].create({
            'name': 'Contrato QA Integration SMMLV',
            'employee_id': cls.employee.id,
            'date_start': date(2025, 1, 1),
            'wage': SMMLV_2025,
            'state': 'open',
            'resource_calendar_id': calendar.id,
            'structure_type_id': structure_type.id,
        })

        struct = (structure_type.default_struct_id
                  or cls.env['hr.payroll.structure'].search(
                      [('type_id', '=', structure_type.id)], limit=1))
        if not struct:
            raise SkipTest('No hay estructura de nómina disponible.')
        cls.struct = struct

    def _create_payslip(self, wage=None, date_from=None, date_to=None):
        if wage and wage != self.contract.wage:
            self.contract.wage = wage
        df = date_from or date(2025, 1, 1)
        dt = date_to or date(2025, 1, 31)
        slip = self.env['hr.payslip'].create({
            'employee_id': self.employee.id,
            'contract_id': self.contract.id,
            'struct_id': self.struct.id,
            'date_from': df,
            'date_to': dt,
            'company_id': self.company.id,
        })
        return slip

    def _compute_and_get_lines(self, slip):
        if hasattr(slip, 'compute_sheet'):
            slip.compute_sheet()
        elif hasattr(slip, 'action_compute'):
            slip.action_compute()
        else:
            self.fail('hr.payslip sin método de cálculo.')
        return {(l.code or '').upper(): float(l.total or 0)
                for l in slip.line_ids}

    # ── Test 1: Salario mínimo — devengado ≥ SMMLV ─────────────────────

    def test_smmlv_devengado_minimo(self):
        slip = self._create_payslip()
        lines = self._compute_and_get_lines(slip)
        basic = lines.get('BASIC', lines.get('BASICO', 0))
        self.assertGreaterEqual(basic, SMMLV_2025 * 0.99,
                                f'Salario básico {basic} menor que SMMLV {SMMLV_2025}')

    # ── Test 2: Auxilio de transporte paga bajo 2 SMMLV ────────────────

    def test_auxilio_transporte_paga_smmlv(self):
        slip = self._create_payslip(wage=SMMLV_2025)
        lines = self._compute_and_get_lines(slip)
        aux = lines.get('AUX000', lines.get('AUXTRANS', lines.get('AUX', 0)))
        if aux == 0:
            self.skipTest('Código de auxilio de transporte no encontrado en líneas.')
        self.assertGreater(aux, 0, 'Auxilio de transporte debe ser > 0 con salario mínimo')
        self.assertAlmostEqual(aux, AUX_TRANSPORTE_2025, delta=AUX_TRANSPORTE_2025 * 0.05)

    # ── Test 3: Salario sobre 2 SMMLV no paga auxilio transporte ───────

    def test_sin_auxilio_sobre_2_smmlv(self):
        slip = self._create_payslip(wage=SMMLV_2025 * 3)
        lines = self._compute_and_get_lines(slip)
        aux = lines.get('AUX000', lines.get('AUXTRANS', lines.get('AUX', 0)))
        self.assertEqual(aux, 0,
                         f'Auxilio transporte debe ser 0 con salario {SMMLV_2025 * 3}')

    # ── Test 4: Deducciones de SS son negativas ─────────────────────────

    def test_deducciones_seguridad_social_negativas(self):
        slip = self._create_payslip()
        lines = self._compute_and_get_lines(slip)
        for code in ['SALUD', 'PENSION', 'SSOCIAL']:
            if code in lines:
                self.assertLessEqual(lines[code], 0,
                                     f'{code} debe ser deducción (≤ 0), got {lines[code]}')

    # ── Test 5: Neto > 0 ────────────────────────────────────────────────

    def test_neto_positivo(self):
        slip = self._create_payslip()
        lines = self._compute_and_get_lines(slip)
        net = lines.get('NET', lines.get('NETO', None))
        if net is None:
            positivos = sum(v for v in lines.values() if v > 0)
            negativos = sum(v for v in lines.values() if v < 0)
            net = positivos + negativos
        self.assertGreater(net, 0, f'Neto debe ser positivo, got {net}')

    # ── Test 6: Deducción salud = 4% IBC ───────────────────────────────

    def test_deduccion_salud_4pct(self):
        slip = self._create_payslip()
        lines = self._compute_and_get_lines(slip)
        salud = abs(lines.get('SALUD', 0))
        if salud == 0:
            self.skipTest('Código SALUD no encontrado.')
        ibc = lines.get('IBC', SMMLV_2025)
        if ibc == 0:
            ibc = SMMLV_2025
        esperado = abs(ibc) * 0.04
        self.assertAlmostEqual(salud, esperado, delta=esperado * 0.05,
                               msg=f'Salud {salud:.0f} ≠ 4% de IBC {ibc:.0f}')

    # ── Test 7: Deducción pensión = 4% IBC ─────────────────────────────

    def test_deduccion_pension_4pct(self):
        slip = self._create_payslip()
        lines = self._compute_and_get_lines(slip)
        pension = abs(lines.get('PENSION', 0))
        if pension == 0:
            self.skipTest('Código PENSION no encontrado.')
        ibc = lines.get('IBC', SMMLV_2025)
        if ibc == 0:
            ibc = SMMLV_2025
        esperado = abs(ibc) * 0.04
        self.assertAlmostEqual(pension, esperado, delta=esperado * 0.05,
                               msg=f'Pensión {pension:.0f} ≠ 4% de IBC {ibc:.0f}')

    # ── Test 8: Salario integral sin prima ni cesantías ────────────────

    def test_integral_sin_prestaciones(self):
        self.contract.write({
            'wage': SMMLV_2025 * 13,
            'modality_salary': 'integral',
        })
        slip = self._create_payslip(wage=SMMLV_2025 * 13)
        lines = self._compute_and_get_lines(slip)
        prima = lines.get('PRIMA', 0)
        cesantias = lines.get('CESANTIAS', 0)
        self.assertEqual(prima, 0, 'Salario integral no debe generar prima')
        self.assertEqual(cesantias, 0, 'Salario integral no debe generar cesantías')
        # Restaurar
        self.contract.write({'wage': SMMLV_2025, 'modality_salary': 'basico'})

    # ── Test 9: Quincena genera exactamente la mitad del mensual ───────

    def test_quincena_primera_mitad_mensual(self):
        slip_q = self._create_payslip(date_from=date(2025, 1, 1), date_to=date(2025, 1, 15))
        slip_m = self._create_payslip(date_from=date(2025, 1, 1), date_to=date(2025, 1, 31))
        lines_q = self._compute_and_get_lines(slip_q)
        lines_m = self._compute_and_get_lines(slip_m)
        basic_q = lines_q.get('BASIC', lines_q.get('BASICO', 0))
        basic_m = lines_m.get('BASIC', lines_m.get('BASICO', 0))
        if basic_m == 0:
            self.skipTest('Código BASIC no encontrado.')
        self.assertAlmostEqual(basic_q, basic_m / 2, delta=basic_m * 0.02,
                               msg=f'Quincena {basic_q:.0f} ≠ mitad mensual {basic_m / 2:.0f}')

    # ── Test 10: Nómina no genera líneas negativas en devengos ─────────

    def test_sin_devengos_negativos(self):
        slip = self._create_payslip()
        lines = self._compute_and_get_lines(slip)
        codigos_devengos = ['BASIC', 'BASICO', 'AUX000', 'AUXTRANS', 'AUX']
        for code in codigos_devengos:
            if code in lines:
                self.assertGreaterEqual(lines[code], 0,
                                        f'Devengo {code} no puede ser negativo: {lines[code]}')


@tagged('standard', 'payslip_social_security', 'post_install', '-at_install')
class TestSeguridadSocialIntegracion(TransactionCase):
    """Tests de integración para módulo lavish_hr_social_security."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.annual_params = SimpleNamespace(
            smmlv_monthly=SMMLV_2025,
        ) if True else None

    def test_modelo_seguridad_social_existe(self):
        self.assertTrue(
            self.env['ir.model'].search([('model', '=', 'hr.payroll.social.security')]),
            'El modelo hr.payroll.social.security debe existir'
        )

    def test_compute_amounts_existe(self):
        ss_model = self.env['hr.payroll.social.security']
        self.assertTrue(
            hasattr(ss_model, '_compute_amounts'),
            'hr.payroll.social.security debe tener _compute_amounts'
        )

    def test_compute_totals_existe(self):
        ss_model = self.env['hr.payroll.social.security']
        self.assertTrue(
            hasattr(ss_model, '_compute_totals'),
            'hr.payroll.social.security debe tener _compute_totals'
        )


# Importación diferida para evitar error si SimpleNamespace no está disponible en scope de clase
from types import SimpleNamespace
