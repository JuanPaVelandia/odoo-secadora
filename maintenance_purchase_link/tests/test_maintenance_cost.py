from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestMaintenanceCost(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))

        # Plan y cuenta analítica "Unidad de negocio" / "Maquinaria"
        plan = cls.env['account.analytic.plan'].search([
            ('name', '=', 'Unidad de negocio'),
        ], limit=1)
        if not plan:
            plan = cls.env['account.analytic.plan'].create({
                'name': 'Unidad de negocio',
            })
        cls.maint_account = cls.env['account.analytic.account'].search([
            ('name', '=', 'Maquinaria'),
            ('plan_id', '=', plan.id),
        ], limit=1)
        if not cls.maint_account:
            cls.maint_account = cls.env['account.analytic.account'].create({
                'name': 'Maquinaria',
                'plan_id': plan.id,
            })

        # Partner proveedor
        cls.partner = cls.env['res.partner'].create({
            'name': 'Proveedor Test Mantenimiento',
            'supplier_rank': 1,
        })

        # Equipo de mantenimiento
        cls.category = cls.env.ref(
            'maintenance_purchase_link.equipment_category_secado'
        )
        cls.equipment = cls.env['maintenance.equipment'].create({
            'name': 'Horno de Secado #1',
            'category_id': cls.category.id,
        })

        # Solicitud de mantenimiento
        cls.request = cls.env['maintenance.request'].create({
            'name': 'OT-001 Reparación Horno',
            'equipment_id': cls.equipment.id,
        })

        # Factura de proveedor con línea analítica de Mantenimiento
        cls.invoice = cls.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': cls.partner.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Repuesto horno secado',
                'quantity': 1,
                'price_unit': 500000.0,
                'analytic_distribution': {str(cls.maint_account.id): 100},
            })],
        })
        cls.invoice_line = cls.invoice.invoice_line_ids[0]

        # Factura sin analítica de mantenimiento
        cls.invoice_no_maint = cls.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': cls.partner.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Servicio administrativo',
                'quantity': 1,
                'price_unit': 200000.0,
            })],
        })
        cls.line_no_maint = cls.invoice_no_maint.invoice_line_ids[0]

    def test_fields_exist(self):
        """Verifica que los campos se crean correctamente."""
        aml_fields = self.env['account.move.line']._fields
        self.assertIn('maintenance_equipment_ids', aml_fields)
        self.assertIn('maintenance_request_ids', aml_fields)
        self.assertIn('equipment_cost_line_ids', aml_fields)

        eq_fields = self.env['maintenance.equipment']._fields
        self.assertIn('equipment_cost_line_ids', eq_fields)
        self.assertIn('lugar_id', eq_fields)
        self.assertIn('horometro_interval', eq_fields)

    def test_assign_equipment_via_cost_line(self):
        """Asignar equipo a línea mediante modelo intermedio."""
        self.env['maintenance.equipment.cost.line'].create({
            'move_line_id': self.invoice_line.id,
            'equipment_id': self.equipment.id,
            'percentage': 60.0,
        })
        self.invoice_line.invalidate_recordset()
        self.assertIn(self.equipment, self.invoice_line.maintenance_equipment_ids)
        self.assertEqual(len(self.invoice_line.equipment_cost_line_ids), 1)

    def test_assign_equipment_via_m2m_inverse(self):
        """Asignar equipo via M2M computed (compatibilidad hacia atrás)."""
        self.invoice_line.write({
            'maintenance_equipment_ids': [(4, self.equipment.id)],
        })
        self.assertIn(self.equipment, self.invoice_line.maintenance_equipment_ids)
        # Debe haber creado un cost line con 100%
        cost_line = self.invoice_line.equipment_cost_line_ids
        self.assertEqual(len(cost_line), 1)
        self.assertAlmostEqual(cost_line.percentage, 100.0)

    def test_assign_request_to_line(self):
        """Verifica asignación de OT a línea con analítica correcta."""
        self.invoice_line.write({
            'maintenance_request_ids': [(4, self.request.id)],
        })
        self.assertIn(self.request, self.invoice_line.maintenance_request_ids)
        self.assertIn(self.invoice_line, self.request.invoice_line_ids)

    def test_cost_total_with_percentage(self):
        """Costo total del equipo respeta porcentaje."""
        self.env['maintenance.equipment.cost.line'].create({
            'move_line_id': self.invoice_line.id,
            'equipment_id': self.equipment.id,
            'percentage': 60.0,
        })
        self.equipment.invalidate_recordset()
        self.assertAlmostEqual(
            self.equipment.maintenance_cost_total,
            300000.0,  # 500000 * 60%
            places=2,
        )

    def test_percentage_sum_constraint(self):
        """La suma de porcentajes no puede exceder 100%."""
        equipment2 = self.env['maintenance.equipment'].create({
            'name': 'Ventilador Secado #2',
            'category_id': self.category.id,
        })
        self.env['maintenance.equipment.cost.line'].create({
            'move_line_id': self.invoice_line.id,
            'equipment_id': self.equipment.id,
            'percentage': 70.0,
        })
        with self.assertRaises(ValidationError):
            self.env['maintenance.equipment.cost.line'].create({
                'move_line_id': self.invoice_line.id,
                'equipment_id': equipment2.id,
                'percentage': 40.0,  # 70 + 40 = 110 > 100
            })

    def test_percentage_range_constraint(self):
        """Porcentaje debe estar entre 0 y 100."""
        with self.assertRaises(ValidationError):
            self.env['maintenance.equipment.cost.line'].create({
                'move_line_id': self.invoice_line.id,
                'equipment_id': self.equipment.id,
                'percentage': 150.0,
            })

    def test_constraint_no_analytic(self):
        """No se puede asignar equipo sin analítica de mantenimiento."""
        with self.assertRaises(ValidationError):
            self.env['maintenance.equipment.cost.line'].create({
                'move_line_id': self.line_no_maint.id,
                'equipment_id': self.equipment.id,
                'percentage': 100.0,
            })

    def test_constraint_no_analytic_request(self):
        """No se puede asignar OT sin analítica de mantenimiento."""
        with self.assertRaises(ValidationError):
            self.line_no_maint.write({
                'maintenance_request_ids': [(4, self.request.id)],
            })

    def test_invoice_level_propagation(self):
        """Equipos a nivel de factura se propagan a todas las líneas."""
        # Crear factura con 2 líneas
        invoice2 = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner.id,
            'invoice_line_ids': [
                (0, 0, {
                    'name': 'Repuesto A',
                    'quantity': 1,
                    'price_unit': 100000.0,
                    'analytic_distribution': {str(self.maint_account.id): 100},
                }),
                (0, 0, {
                    'name': 'Repuesto B',
                    'quantity': 1,
                    'price_unit': 200000.0,
                    'analytic_distribution': {str(self.maint_account.id): 100},
                }),
            ],
        })
        # Asignar equipo a nivel de factura
        invoice2.write({
            'maintenance_equipment_line_ids': [(0, 0, {
                'equipment_id': self.equipment.id,
                'percentage': 50.0,
            })],
        })
        # Verificar que ambas líneas tienen el equipo
        for line in invoice2.invoice_line_ids:
            cost_lines = line.equipment_cost_line_ids
            self.assertEqual(len(cost_lines), 1)
            self.assertEqual(cost_lines.equipment_id, self.equipment)
            self.assertAlmostEqual(cost_lines.percentage, 50.0)

    def test_multiple_equipments_per_line(self):
        """Una línea puede tener múltiples equipos con porcentajes."""
        equipment2 = self.env['maintenance.equipment'].create({
            'name': 'Ventilador Secado #2',
            'category_id': self.category.id,
        })
        self.env['maintenance.equipment.cost.line'].create({
            'move_line_id': self.invoice_line.id,
            'equipment_id': self.equipment.id,
            'percentage': 60.0,
        })
        self.env['maintenance.equipment.cost.line'].create({
            'move_line_id': self.invoice_line.id,
            'equipment_id': equipment2.id,
            'percentage': 40.0,
        })
        self.invoice_line.invalidate_recordset()
        self.assertEqual(len(self.invoice_line.maintenance_equipment_ids), 2)
        self.assertEqual(len(self.invoice_line.equipment_cost_line_ids), 2)

    def test_equipment_invoice_count(self):
        """Verifica contador de líneas de costo en equipo."""
        self.env['maintenance.equipment.cost.line'].create({
            'move_line_id': self.invoice_line.id,
            'equipment_id': self.equipment.id,
            'percentage': 100.0,
        })
        self.equipment.invalidate_recordset()
        self.assertEqual(self.equipment.maintenance_invoice_count, 1)

    # ------------------------------------------------------------------
    # Costos sin factura (histórico importado / registro manual)
    # ------------------------------------------------------------------
    def test_cost_line_without_invoice(self):
        """Un costo sin factura conserva el importe que se le captura."""
        cost = self.env['maintenance.equipment.cost.line'].create({
            'equipment_id': self.equipment.id,
            'origin': 'historic',
            'date': '2025-06-15',
            'name': 'Filtro de aceite (histórico Fracttal)',
            'quantity': 2.0,
            'unit_cost': 50000.0,
            'amount': 100000.0,
            'source_name': 'TALLER LORENZO',
            'external_ref': 'OT-123',
        })
        self.assertFalse(cost.move_line_id)
        self.assertFalse(cost.move_id)
        self.assertAlmostEqual(cost.amount, 100000.0)

    def test_equipment_total_mixes_origins(self):
        """El total del equipo suma facturado e histórico en un solo campo."""
        CostLine = self.env['maintenance.equipment.cost.line']
        CostLine.create({
            'move_line_id': self.invoice_line.id,
            'equipment_id': self.equipment.id,
            'percentage': 100.0,
        })
        facturado = self.equipment.maintenance_cost_total
        self.assertGreater(facturado, 0.0)

        CostLine.create({
            'equipment_id': self.equipment.id,
            'origin': 'historic',
            'date': '2025-06-15',
            'name': 'Repuesto histórico',
            'amount': 250000.0,
        })
        self.equipment.invalidate_recordset()
        self.assertAlmostEqual(
            self.equipment.maintenance_cost_total, facturado + 250000.0)
        self.assertEqual(self.equipment.maintenance_invoice_count, 2)

    def test_invoice_cost_line_copies_invoice_data(self):
        """Al crear desde una factura se copian sus datos descriptivos."""
        cost = self.env['maintenance.equipment.cost.line'].create({
            'move_line_id': self.invoice_line.id,
            'equipment_id': self.equipment.id,
            'percentage': 100.0,
        })
        self.assertEqual(cost.origin, 'invoice')
        self.assertEqual(cost.date, self.invoice_line.date)
        self.assertEqual(cost.partner_id, self.invoice_line.partner_id)
        self.assertAlmostEqual(
            cost.amount, self.invoice_line.price_total)

    def test_percentage_check_ignores_lines_without_invoice(self):
        """La validación de 100% aplica a facturas, no a costos sueltos."""
        CostLine = self.env['maintenance.equipment.cost.line']
        for _ in range(3):
            CostLine.create({
                'equipment_id': self.equipment.id,
                'origin': 'historic',
                'date': '2025-06-15',
                'name': 'Costo suelto',
                'percentage': 100.0,
                'amount': 1000.0,
            })
        self.assertEqual(self.equipment.maintenance_invoice_count, 3)

    # ------------------------------------------------------------------
    # Numeración de órdenes de trabajo (OT-<n>)
    # ------------------------------------------------------------------
    def test_ot_number_se_asigna_al_crear(self):
        """Toda OT nueva recibe un número de la secuencia."""
        req = self.env['maintenance.request'].create({
            'name': 'Revisión general',
            'equipment_id': self.equipment.id,
        })
        self.assertTrue(req.ot_number)
        self.assertRegex(req.ot_number, r'^OT-\d+$')
        self.assertEqual(req.display_name, f'[{req.ot_number}] Revisión general')

    def test_ot_number_importado_se_respeta(self):
        """Una OT que trae su número de origen lo conserva."""
        req = self.env['maintenance.request'].create({
            'name': 'Histórica',
            'equipment_id': self.equipment.id,
            'ot_number': 'OT-777',
            'external_ref': 'OT-777',
        })
        self.assertEqual(req.ot_number, 'OT-777')

    def test_display_name_sin_nombre_no_dice_false(self):
        """Sin nombre, el display_name no debe mostrar el literal "False"."""
        req = self.env['maintenance.request'].create({
            'equipment_id': self.equipment.id,
        })
        self.assertNotIn('False', req.display_name)
        self.assertIn(req.ot_number, req.display_name)

    def test_secuencia_no_se_consume_de_mas(self):
        """Crear N órdenes consume N números, no más."""
        Request = self.env['maintenance.request']
        numeros = []
        for i in range(3):
            req = Request.create({
                'name': f'OT de prueba {i}',
                'equipment_id': self.equipment.id,
            })
            numeros.append(int(req.ot_number.removeprefix('OT-')))
        self.assertEqual(numeros, sorted(numeros))
        self.assertEqual(numeros[-1] - numeros[0], 2,
                         'La secuencia saltó números: se consumió de más.')
