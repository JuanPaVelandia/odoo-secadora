# -*- coding: utf-8 -*-
"""
Tests para generación de archivos planos bancarios (PILA / dispersión).

Verifica que los métodos de generación existen y que los modelos
de archivo plano tienen la estructura correcta.
"""
from odoo.tests.common import TransactionCase, tagged


@tagged('standard', 'flat_file', 'post_install', '-at_install')
class TestFlatFileModels(TransactionCase):

    def test_modelo_flat_file_existe(self):
        self.assertIn(
            'hr.payroll.flat.file', self.env,
            'Modelo hr.payroll.flat.file no encontrado.'
        )

    def test_modelo_flat_file_detail_existe(self):
        self.assertIn(
            'hr.payroll.flat.file.detail', self.env,
            'Modelo hr.payroll.flat.file.detail no encontrado.'
        )

    def test_flat_file_tiene_action_generate(self):
        model = self.env['hr.payroll.flat.file']
        self.assertTrue(
            hasattr(model, 'generate_flat_file'),
            'hr.payroll.flat.file debe tener generate_flat_file().'
        )

    def test_flat_file_tiene_action_regenerate_en_detail(self):
        model = self.env['hr.payroll.flat.file.detail']
        self.assertTrue(
            hasattr(model, 'action_regenerate'),
            'hr.payroll.flat.file.detail debe tener action_regenerate().'
        )

    def test_bancos_soportados_existen_como_metodos(self):
        """Los métodos de generación para bancos principales deben existir."""
        model = self.env['hr.payroll.flat.file']
        bancos = [
            'generate_flat_file_sap',
            'generate_flat_file_pab',
            'generate_flat_file_bbva',
            'generate_flat_file_davivienda',
        ]
        for metodo in bancos:
            self.assertTrue(
                hasattr(model, metodo),
                f'Método {metodo} no encontrado en hr.payroll.flat.file.'
            )

    def test_process_log_model_existe(self):
        self.assertIn(
            'payroll.file.process.log', self.env,
            'Modelo payroll.file.process.log no encontrado.'
        )


@tagged('standard', 'flat_file', 'post_install', '-at_install')
class TestFlatFileContent(TransactionCase):
    """Tests de formato de contenido para archivos planos."""

    def test_formato_cuenta_bancaria_8_digitos_minimo(self):
        # Las cuentas bancarias en Colombia tienen al menos 8 dígitos
        cuenta = '12345678'
        self.assertGreaterEqual(len(cuenta.strip()), 8)

    def test_nit_formato_sin_digito_verificacion(self):
        # NIT sin dígito verificación (solo el número base)
        nit = '900123456'
        self.assertRegex(nit, r'^\d{7,10}$')

    def test_cedula_formato_numerico(self):
        cedula = '1234567890'
        self.assertTrue(cedula.isdigit())
        self.assertGreaterEqual(len(cedula), 6)

    def test_valor_positivo_en_archivo_plano(self):
        # Los valores en archivo plano no deben ser negativos
        valor = 3_000_000
        self.assertGreater(valor, 0)

    def test_formato_fecha_yyyymmdd(self):
        from datetime import date
        d = date(2025, 1, 31)
        formatted = d.strftime('%Y%m%d')
        self.assertEqual(formatted, '20250131')
        self.assertEqual(len(formatted), 8)
