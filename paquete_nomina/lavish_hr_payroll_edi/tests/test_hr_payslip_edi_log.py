# -*- coding: utf-8 -*-
"""
Pruebas unitarias para hr.payslip.edi.log.

Cubre:
- DIAN_RESPONSE_CODES: mapeo correcto de códigos a state_dian
- log_validation()
- log_dian_response()
- log_send()
- log_warning()
- get_state_for_code()
- get_rejection_help(): búsqueda en glosario hardcoded
- log_dian_response_with_help()
"""
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.addons.lavish_hr_payroll_edi.models.hr_payslip_edi_log import (
    DIAN_RESPONSE_CODES,
    DIAN_REJECTION_GLOSSARY,
)


@tagged('post_install', '-at_install')
class TestDianResponseCodes(TransactionCase):
    """Verifica el diccionario DIAN_RESPONSE_CODES importado del modelo."""

    def test_exitoso_codes(self):
        for code in ('200', '299', '00'):
            with self.subTest(code=code):
                self.assertEqual(DIAN_RESPONSE_CODES[code]['state_dian'], 'exitoso')
                self.assertEqual(DIAN_RESPONSE_CODES[code]['level'], 'success')

    def test_por_validar_codes(self):
        for code in ('201', '202', '203', '204', '208', '90', '66'):
            with self.subTest(code=code):
                self.assertEqual(DIAN_RESPONSE_CODES[code]['state_dian'], 'por_validar')

    def test_error_codes(self):
        for code in ('101', '109', '110', '111'):
            with self.subTest(code=code):
                self.assertEqual(DIAN_RESPONSE_CODES[code]['state_dian'], 'error')
                self.assertEqual(DIAN_RESPONSE_CODES[code]['level'], 'error')

    def test_rechazado_codes(self):
        for code in ('99', '2', '63'):
            with self.subTest(code=code):
                self.assertEqual(DIAN_RESPONSE_CODES[code]['state_dian'], 'rechazado')

    def test_timeout_code(self):
        self.assertEqual(DIAN_RESPONSE_CODES['504']['state_dian'], 'error')

    def test_all_entries_have_required_keys(self):
        for code, info in DIAN_RESPONSE_CODES.items():
            with self.subTest(code=code):
                self.assertIn('state_dian', info, f"Código {code} sin state_dian")
                self.assertIn('level', info, f"Código {code} sin level")
                self.assertIn('description', info, f"Código {code} sin description")


@tagged('post_install', '-at_install')
class TestDianRejectionGlossary(TransactionCase):
    """Verifica el diccionario DIAN_REJECTION_GLOSSARY."""

    def test_key_92_exists(self):
        self.assertIn('92', DIAN_REJECTION_GLOSSARY)
        self.assertEqual(DIAN_REJECTION_GLOSSARY['92']['category'], 'habilitacion')

    def test_nie024_cune(self):
        info = DIAN_REJECTION_GLOSSARY['NIE024']
        self.assertIn('CUNE', info['message'])
        self.assertEqual(info['category'], 'cune')

    def test_niae191a_nota_ajuste(self):
        info = DIAN_REJECTION_GLOSSARY['NIAE191a']
        self.assertEqual(info['category'], 'nota_ajuste')

    def test_all_entries_have_required_keys(self):
        for code, info in DIAN_REJECTION_GLOSSARY.items():
            with self.subTest(code=code):
                self.assertIn('rule', info, f"Código {code} sin rule")
                self.assertIn('message', info, f"Código {code} sin message")
                self.assertIn('solution', info, f"Código {code} sin solution")
                self.assertIn('category', info, f"Código {code} sin category")


@tagged('post_install', '-at_install')
class TestHrPayslipEdiLog(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Empleado Log Test',
            'company_id': cls.company.id,
        })
        cls.edi = cls.env['hr.payslip.edi'].create({
            'name': 'EDI Log Test',
            'employee_id': cls.employee.id,
            'company_id': cls.company.id,
            'date_from': '2025-01-01',
            'date_to': '2025-01-31',
        })
        cls.Log = cls.env['hr.payslip.edi.log']

    # ------------------------------------------------------------------
    # log_validation
    # ------------------------------------------------------------------

    def test_log_validation_creates_records(self):
        errors = ['Error campo NIT', 'Error dirección empresa']
        logs = self.Log.log_validation(self.edi, errors)
        self.assertEqual(len(logs), 2)

    def test_log_validation_empty_list(self):
        logs = self.Log.log_validation(self.edi, [])
        self.assertEqual(len(logs), 0)

    def test_log_validation_level_is_error(self):
        self.Log.log_validation(self.edi, ['Algún error'])
        log = self.Log.search([
            ('payslip_edi_id', '=', self.edi.id),
            ('log_type', '=', 'validation'),
        ], limit=1, order='id desc')
        self.assertEqual(log.level, 'error')

    def test_log_validation_truncates_summary_to_200(self):
        long_error = 'A' * 300
        self.Log.log_validation(self.edi, [long_error])
        log = self.Log.search([
            ('payslip_edi_id', '=', self.edi.id),
            ('log_type', '=', 'validation'),
        ], limit=1, order='id desc')
        self.assertLessEqual(len(log.summary), 200)

    # ------------------------------------------------------------------
    # log_dian_response
    # ------------------------------------------------------------------

    def test_log_dian_response_code_200(self):
        log = self.Log.log_dian_response(self.edi, '200', 'Documento aceptado')
        self.assertEqual(log.level, 'success')
        self.assertEqual(log.state_dian_result, 'exitoso')
        self.assertEqual(log.dian_code, '200')

    def test_log_dian_response_code_99(self):
        log = self.Log.log_dian_response(self.edi, '99', 'Documento rechazado')
        self.assertEqual(log.state_dian_result, 'rechazado')
        self.assertEqual(log.level, 'error')

    def test_log_dian_response_code_201(self):
        log = self.Log.log_dian_response(self.edi, '201', 'Pendiente')
        self.assertEqual(log.state_dian_result, 'por_validar')

    def test_log_dian_response_unknown_code(self):
        log = self.Log.log_dian_response(self.edi, '9999', 'Código desconocido')
        self.assertEqual(log.level, 'warning')
        self.assertFalse(log.state_dian_result)

    def test_log_dian_response_with_raw_response(self):
        raw = '<Response><Status>OK</Status></Response>'
        log = self.Log.log_dian_response(self.edi, '200', 'OK', raw_response=raw)
        self.assertIn('RAW', log.detail)
        self.assertIn(raw[:50], log.detail)

    def test_log_dian_response_integer_code(self):
        """Acepta código numérico entero además de string."""
        log = self.Log.log_dian_response(self.edi, 200, 'OK entero')
        self.assertEqual(log.state_dian_result, 'exitoso')

    # ------------------------------------------------------------------
    # log_send
    # ------------------------------------------------------------------

    def test_log_send_success(self):
        log = self.Log.log_send(self.edi, True, 'Envío OK')
        self.assertEqual(log.level, 'success')
        self.assertEqual(log.log_type, 'send')

    def test_log_send_failure(self):
        log = self.Log.log_send(self.edi, False, 'Timeout')
        self.assertEqual(log.level, 'error')

    # ------------------------------------------------------------------
    # log_warning
    # ------------------------------------------------------------------

    def test_log_warning_creates_record(self):
        log = self.Log.log_warning(self.edi, 'Advertencia de prueba')
        self.assertEqual(log.log_type, 'warning')
        self.assertEqual(log.level, 'warning')

    def test_log_warning_truncates_summary(self):
        long_msg = 'W' * 300
        log = self.Log.log_warning(self.edi, long_msg)
        self.assertLessEqual(len(log.summary), 200)

    # ------------------------------------------------------------------
    # get_state_for_code
    # ------------------------------------------------------------------

    def test_get_state_for_code_200(self):
        state = self.Log.get_state_for_code('200')
        self.assertEqual(state, 'exitoso')

    def test_get_state_for_code_99(self):
        state = self.Log.get_state_for_code(99)
        self.assertEqual(state, 'rechazado')

    def test_get_state_for_code_unknown(self):
        state = self.Log.get_state_for_code('XYZUNKNOWN')
        self.assertIsNone(state)

    def test_get_state_for_code_201(self):
        state = self.Log.get_state_for_code('201')
        self.assertEqual(state, 'por_validar')

    def test_get_state_for_code_101(self):
        state = self.Log.get_state_for_code('101')
        self.assertEqual(state, 'error')

    # ------------------------------------------------------------------
    # get_rejection_help
    # ------------------------------------------------------------------

    def test_get_rejection_help_empty_message(self):
        results = self.Log.get_rejection_help('')
        self.assertEqual(results, [])

    def test_get_rejection_help_none_message(self):
        results = self.Log.get_rejection_help(None)
        self.assertEqual(results, [])

    def test_get_rejection_help_finds_nie024(self):
        results = self.Log.get_rejection_help('NIE024 error en CUNE')
        self.assertTrue(len(results) > 0)
        codes = [r.get('rule', '') for r in results]
        self.assertTrue(any('NIE024' in c for c in codes))

    def test_get_rejection_help_finds_92(self):
        results = self.Log.get_rejection_help('Regla 92 emisor no habilitado')
        self.assertTrue(len(results) > 0)

    def test_get_rejection_help_no_match(self):
        results = self.Log.get_rejection_help('XYZXYZ_CODIGO_INEXISTENTE_123456')
        self.assertEqual(results, [])

    def test_get_rejection_help_case_insensitive(self):
        results_upper = self.Log.get_rejection_help('nie024 cune error')
        results_lower = self.Log.get_rejection_help('NIE024 CUNE ERROR')
        # Ambos deben encontrar el mismo resultado
        self.assertEqual(len(results_upper), len(results_lower))

    def test_get_rejection_help_niae191a(self):
        results = self.Log.get_rejection_help('NIAE191a documento no encontrado')
        self.assertTrue(len(results) > 0)

    def test_get_rejection_help_timeout(self):
        results = self.Log.get_rejection_help('timeout conexion DIAN')
        self.assertTrue(len(results) > 0)

    # ------------------------------------------------------------------
    # log_dian_response_with_help
    # ------------------------------------------------------------------

    def test_log_dian_response_with_help_adds_help_on_rejection(self):
        """Con mensaje que contiene código de rechazo, el detalle incluye ayuda."""
        msg = 'Error NIE024: CUNE incorrecto'
        log = self.Log.log_dian_response_with_help(self.edi, '99', msg)
        self.assertIn('AYUDA', log.detail)

    def test_log_dian_response_with_help_no_help_for_success(self):
        """Mensaje de éxito sin código de rechazo: no agrega sección AYUDA."""
        msg = 'Documento procesado correctamente'
        log = self.Log.log_dian_response_with_help(self.edi, '200', msg)
        # No debería haber sección de ayuda ya que no hay código de rechazo
        self.assertNotIn('AYUDA', log.detail or '')

    def test_log_dian_response_with_help_returns_log_record(self):
        log = self.Log.log_dian_response_with_help(self.edi, '201', 'Pendiente DIAN')
        self.assertEqual(log._name, 'hr.payslip.edi.log')

    # ------------------------------------------------------------------
    # Relaciones
    # ------------------------------------------------------------------

    def test_log_payslip_run_related(self):
        """payslip_run_id es related desde el edi."""
        log = self.Log.log_send(self.edi, True, 'OK')
        # Sin run, debe ser vacío
        self.assertFalse(log.payslip_run_id)

    def test_log_employee_related(self):
        """employee_id es related desde el edi."""
        log = self.Log.log_send(self.edi, True, 'OK')
        self.assertEqual(log.employee_id.id, self.edi.employee_id.id)
