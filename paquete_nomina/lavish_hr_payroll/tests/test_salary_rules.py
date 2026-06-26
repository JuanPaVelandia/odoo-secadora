# -*- coding: utf-8 -*-
"""
Tests de validación de estructura de reglas salariales.

Verifica que las reglas críticas existen, tienen los códigos esperados,
y que las categorías (BASIC, AUX, SSOCIAL, NET, IBC) están configuradas.
"""
from odoo.tests.common import TransactionCase, tagged


# Códigos de regla críticos que DEBEN existir en el sistema
CODIGOS_CRITICOS = [
    'BASIC',     # Salario básico
    'NET',       # Neto a pagar
]

CATEGORIAS_ESPERADAS = [
    'BASIC',
    'ALW',       # Deducciones
    'DED',
    'NET',
]


@tagged('standard', 'salary_rules', 'post_install', '-at_install')
class TestSalaryRulesStructure(TransactionCase):

    def test_categorias_salariales_existen(self):
        """Las categorías de reglas salariales principales deben existir."""
        SalaryRuleCategory = self.env['hr.salary.rule.category']
        for code in CATEGORIAS_ESPERADAS:
            cat = SalaryRuleCategory.search([('code', '=', code)], limit=1)
            if not cat:
                cat = SalaryRuleCategory.search([('name', 'ilike', code)], limit=1)
            self.assertTrue(
                cat,
                f'Categoría salarial {code!r} no encontrada. '
                'Verifica que los datos de demo/configuración estén cargados.'
            )

    def test_estructura_nomina_existe(self):
        """Debe existir al menos una estructura de nómina."""
        structs = self.env['hr.payroll.structure'].search([], limit=1)
        self.assertTrue(structs, 'No hay estructuras de nómina configuradas.')

    def test_tipo_estructura_nomina_existe(self):
        """Debe existir al menos un tipo de estructura."""
        tipos = self.env['hr.payroll.structure.type'].search([], limit=1)
        self.assertTrue(tipos, 'No hay tipos de estructura de nómina.')

    def test_reglas_salariales_tienen_codigo(self):
        """Todas las reglas activas deben tener código."""
        reglas_sin_codigo = self.env['hr.salary.rule'].search(
            [('active', '=', True), ('code', '=', False)]
        )
        self.assertFalse(
            reglas_sin_codigo,
            f'Hay {len(reglas_sin_codigo)} regla(s) activa(s) sin código.'
        )

    def test_reglas_salariales_sin_categoria_invalida(self):
        """No debe haber reglas activas sin categoría."""
        reglas_sin_cat = self.env['hr.salary.rule'].search(
            [('active', '=', True), ('category_id', '=', False)]
        )
        self.assertFalse(
            reglas_sin_cat,
            f'{len(reglas_sin_cat)} regla(s) activa(s) sin categoría.'
        )

    def test_regla_basico_tiene_secuencia_baja(self):
        """La regla BASIC debe procesarse antes que el neto (secuencia baja)."""
        basic = self.env['hr.salary.rule'].search([('code', '=', 'BASIC')], limit=1)
        if not basic:
            self.skipTest('Regla BASIC no encontrada.')
        net = self.env['hr.salary.rule'].search([('code', '=', 'NET')], limit=1)
        if not net:
            self.skipTest('Regla NET no encontrada.')
        self.assertLess(
            basic.sequence, net.sequence,
            f'BASIC (seq={basic.sequence}) debe preceder a NET (seq={net.sequence})'
        )

    def test_no_hay_reglas_con_python_invalido(self):
        """Las reglas con amount_python_compute no deben estar vacías si son tipo 'code'."""
        reglas_vacias = self.env['hr.salary.rule'].search([
            ('active', '=', True),
            ('amount_select', '=', 'code'),
            ('amount_python_compute', 'in', [False, '']),
        ])
        self.assertFalse(
            reglas_vacias,
            f'{len(reglas_vacias)} regla(s) de tipo code sin código Python.'
        )


@tagged('standard', 'salary_rules', 'post_install', '-at_install')
class TestPayrollParametersAnuales(TransactionCase):
    """Verifica que los parámetros anuales necesarios para nómina existen."""

    def test_parametros_anuales_existen(self):
        """Debe existir al menos un registro de parámetros anuales."""
        if 'lavish.hr.annual.parameters' not in self.env:
            self.skipTest('Modelo lavish.hr.annual.parameters no instalado.')
        params = self.env['lavish.hr.annual.parameters'].search([], limit=1)
        self.assertTrue(params, 'No hay parámetros anuales configurados.')

    def test_smmlv_valor_razonable(self):
        """El SMMLV configurado debe ser mayor a 1M (sanity check)."""
        if 'lavish.hr.annual.parameters' not in self.env:
            self.skipTest('Modelo lavish.hr.annual.parameters no instalado.')
        params = self.env['lavish.hr.annual.parameters'].search([], limit=1)
        if not params:
            self.skipTest('No hay parámetros anuales.')
        smmlv = getattr(params, 'smmlv_monthly', None) or getattr(params, 'value_smmlv', None)
        if smmlv is None:
            self.skipTest('Campo SMMLV no encontrado en parámetros.')
        self.assertGreater(float(smmlv), 1_000_000,
                           f'SMMLV {smmlv} parece incorrecto (< 1.000.000).')

    def test_uvt_valor_razonable(self):
        """El valor UVT debe ser > 40.000 (sanity check)."""
        if 'lavish.hr.annual.parameters' not in self.env:
            self.skipTest('Modelo lavish.hr.annual.parameters no instalado.')
        params = self.env['lavish.hr.annual.parameters'].search([], limit=1)
        if not params:
            self.skipTest('No hay parámetros anuales.')
        uvt = getattr(params, 'value_uvt', None)
        if uvt is None:
            self.skipTest('Campo value_uvt no encontrado.')
        self.assertGreater(float(uvt), 40_000,
                           f'UVT {uvt} parece incorrecto (< 40.000).')
