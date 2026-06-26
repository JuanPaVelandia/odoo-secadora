# -*- coding: utf-8 -*-
"""
Pruebas unitarias para hr.payslip.edi.line y hr.payslip.edi.worked_days.

Cubre:
- _compute_total (quantity × amount × rate / 100)
- _compute_dev_or_ded
- _compute_dian_code
- create() con líneas informativas vs normales
- _onchange_info_type: auto-completar nombre/código
- HrPayslipEdiWorkedDays: _compute_is_paid, _compute_amount
"""
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestHrPayslipEdiLine(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Empleado Líneas Test',
            'company_id': cls.company.id,
        })
        cls.edi = cls.env['hr.payslip.edi'].create({
            'name': 'EDI Líneas Test',
            'employee_id': cls.employee.id,
            'company_id': cls.company.id,
            'date_from': '2025-01-01',
            'date_to': '2025-01-31',
        })

    def _make_line(self, **kwargs):
        vals = {
            'slip_id': self.edi.id,
            'name': 'Línea Test',
            'code': 'TEST',
            'quantity': 1.0,
            'rate': 100.0,
            'amount': 1_000_000.0,
            'line_type': 'informativo',
        }
        vals.update(kwargs)
        return self.env['hr.payslip.edi.line'].create(vals)

    # ------------------------------------------------------------------
    # _compute_total
    # ------------------------------------------------------------------

    def test_total_simple(self):
        """total = quantity × amount × rate / 100."""
        line = self._make_line(quantity=1.0, amount=1_000_000.0, rate=100.0)
        self.assertAlmostEqual(line.total, 1_000_000.0)

    def test_total_with_rate(self):
        """Con rate=4, total = cantidad × monto × 0.04."""
        line = self._make_line(quantity=1.0, amount=1_000_000.0, rate=4.0)
        self.assertAlmostEqual(line.total, 40_000.0)

    def test_total_with_quantity(self):
        line = self._make_line(quantity=2.0, amount=500_000.0, rate=100.0)
        self.assertAlmostEqual(line.total, 1_000_000.0)

    def test_total_zero_amount(self):
        line = self._make_line(quantity=1.0, amount=0.0, rate=100.0)
        self.assertAlmostEqual(line.total, 0.0)

    def test_total_negative_amount(self):
        line = self._make_line(quantity=1.0, amount=-200_000.0, rate=100.0)
        self.assertAlmostEqual(line.total, -200_000.0)

    # ------------------------------------------------------------------
    # _compute_dev_or_ded
    # ------------------------------------------------------------------

    def test_dev_or_ded_none_without_rule(self):
        line = self._make_line()
        self.assertFalse(line.dev_or_ded)

    def test_dev_or_ded_devengo_with_devengado_rule(self):
        accrued = self.env['hr.accrued.rule'].search([], limit=1)
        if not accrued:
            self.skipTest('No hay hr.accrued.rule disponible')

        rule = self.env['hr.salary.rule'].search(
            [('devengado_rule_id', '!=', False)], limit=1
        )
        if not rule:
            self.skipTest('No hay regla salarial con devengado_rule_id')

        line = self._make_line(salary_rule_id=rule.id)
        self.assertEqual(line.dev_or_ded, 'devengo')

    def test_dev_or_ded_deduccion_with_deduccion_rule(self):
        rule = self.env['hr.salary.rule'].search(
            [('deduccion_rule_id', '!=', False)], limit=1
        )
        if not rule:
            self.skipTest('No hay regla salarial con deduccion_rule_id')

        line = self._make_line(salary_rule_id=rule.id)
        self.assertEqual(line.dev_or_ded, 'deduccion')

    # ------------------------------------------------------------------
    # _compute_dian_code
    # ------------------------------------------------------------------

    def test_dian_code_empty_without_rule(self):
        line = self._make_line()
        self.assertEqual(line.dian_code, '')

    # ------------------------------------------------------------------
    # create() - validaciones
    # ------------------------------------------------------------------

    def test_create_informativa_without_version_ok(self):
        """Líneas informativas no requieren versión de contrato."""
        line = self._make_line(line_type='informativo', info_type='banco')
        self.assertEqual(line.line_type, 'informativo')

    def test_create_normal_without_version_raises(self):
        """Líneas normales sin versión de contrato deben fallar."""
        with self.assertRaises(UserError):
            self.env['hr.payslip.edi.line'].create({
                'slip_id': self.edi.id,
                'name': 'Sueldo',
                'code': 'BASIC',
                'line_type': 'normal',
                'amount': 2_000_000.0,
                'version_id': False,
            })

    def test_create_informativa_auto_code(self):
        """Auto-genera código INFO_* si no se provee."""
        line = self.env['hr.payslip.edi.line'].create({
            'slip_id': self.edi.id,
            'name': 'EPS Test',
            'line_type': 'informativo',
            'info_type': 'eps',
        })
        self.assertEqual(line.code, 'INFO_EPS')

    def test_create_informativa_custom_code_kept(self):
        """Si se provee código propio, se conserva."""
        line = self.env['hr.payslip.edi.line'].create({
            'slip_id': self.edi.id,
            'name': 'ARL Custom',
            'code': 'MY_ARL',
            'line_type': 'informativo',
            'info_type': 'arl',
        })
        self.assertEqual(line.code, 'MY_ARL')

    def test_create_inherits_employee_from_slip(self):
        """Si no se da employee_id, se hereda del edi."""
        line = self._make_line()
        self.assertEqual(line.employee_id.id, self.edi.employee_id.id)

    # ------------------------------------------------------------------
    # _onchange_info_type
    # ------------------------------------------------------------------

    def test_onchange_info_type_sets_name(self):
        # El onchange solo sobreescribe el nombre si está vacío o es el label
        # del tipo anterior. Creamos la línea con nombre = label del tipo 'eps'
        # para que el onchange lo reemplace al cambiar a 'sindicato'.
        line = self._make_line(line_type='informativo', name='EPS')
        line.line_type = 'informativo'
        line.info_type = 'sindicato'
        line._onchange_info_type()
        self.assertEqual(line.name, 'Sindicato')

    def test_onchange_info_type_sets_code(self):
        # Creamos con code vacío para que el onchange lo genere
        line = self.env['hr.payslip.edi.line'].create({
            'slip_id': self.edi.id,
            'name': 'EPS',
            'code': 'INFO_EPS',
            'line_type': 'informativo',
            'info_type': 'eps',
        })
        # Simulamos cambio de tipo: vaciamos code para que _onchange lo rellene
        line.code = ''
        line.info_type = 'sindicato'
        line._onchange_info_type()
        self.assertEqual(line.code, 'INFO_SINDICATO')

    def test_onchange_info_type_does_not_override_custom_name(self):
        """Si el nombre es personalizado, no se sobreescribe."""
        line = self._make_line(line_type='informativo', name='Mi EPS Especial')
        line.info_type = 'eps'
        line._onchange_info_type()
        # El nombre no está en la lista de valores de selección → se mantiene
        self.assertEqual(line.name, 'Mi EPS Especial')

    def test_onchange_info_type_no_op_if_normal(self):
        """No hace nada si line_type != informativo."""
        line = self._make_line(line_type='informativo', name='Normal Line')
        line.line_type = 'normal'
        line.info_type = 'banco'
        # No debe lanzar excepción
        line._onchange_info_type()

    # ------------------------------------------------------------------
    # Campos relacionados
    # ------------------------------------------------------------------

    def test_date_from_related_to_slip(self):
        line = self._make_line()
        self.assertEqual(line.date_from, self.edi.date_from)

    def test_date_to_related_to_slip(self):
        line = self._make_line()
        self.assertEqual(line.date_to, self.edi.date_to)

    def test_company_id_related_to_slip(self):
        line = self._make_line()
        self.assertEqual(line.company_id.id, self.edi.company_id.id)


@tagged('post_install', '-at_install')
class TestHrPayslipEdiWorkedDays(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Empleado WD Test',
            'company_id': cls.company.id,
        })
        cls.edi = cls.env['hr.payslip.edi'].create({
            'name': 'EDI Worked Days Test',
            'employee_id': cls.employee.id,
            'company_id': cls.company.id,
            'date_from': '2025-01-01',
            'date_to': '2025-01-31',
        })
        cls.work_entry_type = cls.env['hr.work.entry.type'].search([], limit=1)

    def test_create_worked_days_line(self):
        if not self.work_entry_type:
            self.skipTest('No hay hr.work.entry.type disponible')
        wd = self.env['hr.payslip.edi.worked_days'].create({
            'payslip_id': self.edi.id,
            'work_entry_type_id': self.work_entry_type.id,
            'number_of_days': 30.0,
            'number_of_hours': 240.0,
        })
        self.assertEqual(wd.number_of_days, 30.0)
        self.assertEqual(wd.number_of_hours, 240.0)

    def test_worked_days_is_paid_default_true(self):
        if not self.work_entry_type:
            self.skipTest('No hay hr.work.entry.type disponible')
        wd = self.env['hr.payslip.edi.worked_days'].create({
            'payslip_id': self.edi.id,
            'work_entry_type_id': self.work_entry_type.id,
            'number_of_days': 15.0,
            'number_of_hours': 120.0,
        })
        # Sin estructura definida, es_paid = True por defecto
        self.assertTrue(wd.is_paid)

    def test_worked_days_amount_zero_if_not_paid(self):
        """Si is_paid es False, amount debe ser 0."""
        if not self.work_entry_type:
            self.skipTest('No hay hr.work.entry.type disponible')
        wd = self.env['hr.payslip.edi.worked_days'].create({
            'payslip_id': self.edi.id,
            'work_entry_type_id': self.work_entry_type.id,
            'number_of_days': 5.0,
            'number_of_hours': 40.0,
        })
        # Forzar is_paid=False para verificar que amount = 0
        # is_paid es computed/stored, lo manipulamos via write directo
        wd.write({'is_paid': False})
        wd._compute_amount()
        self.assertAlmostEqual(wd.amount, 0.0)

    def test_worked_days_amount_zero_without_version(self):
        """Sin versión de contrato, amount = 0."""
        if not self.work_entry_type:
            self.skipTest('No hay hr.work.entry.type disponible')
        wd = self.env['hr.payslip.edi.worked_days'].create({
            'payslip_id': self.edi.id,
            'work_entry_type_id': self.work_entry_type.id,
            'number_of_days': 30.0,
            'number_of_hours': 240.0,
        })
        # Sin version_id en el edi, amount debe ser 0
        self.assertAlmostEqual(wd.amount, 0.0)
