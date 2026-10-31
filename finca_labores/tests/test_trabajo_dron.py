# -*- coding: utf-8 -*-

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestTrabajoDron(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.campana = cls.env['finca.campana'].create({
            'name': 'Campaña de prueba',
            'fecha_inicio': '2000-01-01',
            'fecha_fin': '2000-12-31',
        })
        cls.dueno = cls.company.partner_id
        cls.piloto = cls.env['res.partner'].create({'name': 'Piloto de prueba'})
        cls.equipo = cls.env['maintenance.equipment'].create({
            'name': 'DRON DE PRUEBA', 'company_id': cls.company.id,
        })
        cls.rociado = cls.env.ref('finca_labores.labor_rociado_dron')

    def _trabajo(self, **vals):
        return self.env['finca.maquinaria.trabajo'].create({
            'campana_id': self.campana.id,
            'equipment_id': self.equipo.id,
            'operador_id': self.piloto.id,
            'labor_id': self.rociado.id,
            'cantidad': 199.92,
            'tarifa': 5000,
            **vals,
        })

    def test_valor_es_cantidad_por_tarifa(self):
        trabajo = self._trabajo()
        self.assertAlmostEqual(trabajo.valor, 999600)
        self.assertEqual(trabajo.dueno_id, self.dueno)
        self.assertIn('Rociado dron', trabajo.descripcion)

    def test_valor_fijo_sigue_funcionando(self):
        trabajo = self.env['finca.maquinaria.trabajo'].create({
            'campana_id': self.campana.id,
            'equipment_id': self.equipo.id,
            'operador_id': self.piloto.id,
            'valor': 250000,
        })
        self.assertAlmostEqual(trabajo.valor, 250000)
        self.assertTrue(trabajo.descripcion.startswith('MTTO'))

    def test_dueno_en_labores_manda(self):
        sociedad = self.env['res.partner'].create({'name': 'Sociedad de prueba'})
        self.equipo.finca_dueno_id = sociedad
        self.assertEqual(self._trabajo().dueno_id, sociedad)

    def test_confirmar_crea_costo_con_cantidad(self):
        trabajo = self._trabajo()
        trabajo.action_confirmar()
        costo = trabajo.cost_line_id
        self.assertAlmostEqual(costo.quantity, 199.92)
        self.assertAlmostEqual(costo.unit_cost, 5000)
        self.assertAlmostEqual(costo.amount, 999600)
        self.assertEqual(costo.uom_name, 'ha')

    def test_tarifa_propone_la_ultima_del_operador(self):
        self._trabajo(tarifa=4500).action_confirmar()
        nuevo = self.env['finca.maquinaria.trabajo'].new({
            'labor_id': self.rociado.id, 'operador_id': self.piloto.id,
        })
        nuevo._onchange_proponer_tarifa()
        self.assertEqual(nuevo.tarifa, 4500)

    def test_tope_no_aplica_a_trabajos_por_cantidad(self):
        self.equipo.category_id = self.env['maintenance.equipment.category'].create({
            'name': 'Categoría de prueba', 'finca_valor_max_contrato': 1000,
        })
        self.assertFalse(self._trabajo().excede_tope)

    def _analitica(self):
        plan = self.env['account.analytic.plan'].create({'name': 'Unidad de Negocio'})
        return self.env['account.analytic.account'].create({
            'name': 'Maquinaria', 'plan_id': plan.id, 'company_id': self.company.id,
        })

    def _liquidacion(self):
        return self.env['finca.liquidacion'].new({
            'campana_id': self.campana.id,
            'dueno_id': self.dueno.id,
            'company_id': self.company.id,
        })

    def test_giro_de_drones_va_todo_a_maquinaria(self):
        cuenta = self.env['account.analytic.account'].search([
            ('name', '=ilike', 'maquinaria'),
            ('plan_id.name', '=ilike', 'unidad de negocio'),
            ('company_id', '=', self.company.id),
        ], limit=1) or self._analitica()
        self._trabajo().action_confirmar()
        self.assertEqual(
            self._liquidacion()._distribucion_maquinaria(self.piloto),
            {str(cuenta.id): 100.0})

    def test_giro_sin_trabajos_de_maquinaria_no_lleva_analitica(self):
        self.assertFalse(self._liquidacion()._distribucion_maquinaria(self.piloto))
