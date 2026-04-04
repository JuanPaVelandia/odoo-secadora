from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestMaintenanceCost(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))

        # Plan y cuenta analítica de Mantenimiento
        cls.maint_account = cls.env.ref(
            'maintenance_purchase_link.analytic_account_mantenimiento'
        )

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

    def test_many2many_fields_exist(self):
        """Verifica que los campos Many2many se crean correctamente."""
        self.assertIn(
            'maintenance_equipment_ids',
            self.env['account.move.line']._fields,
        )
        self.assertIn(
            'maintenance_request_ids',
            self.env['account.move.line']._fields,
        )
        self.assertIn(
            'maintenance_invoice_line_ids',
            self.env['maintenance.equipment']._fields,
        )
        self.assertIn(
            'invoice_line_ids',
            self.env['maintenance.request']._fields,
        )

    def test_assign_equipment_to_line(self):
        """Verifica asignación de equipo a línea con analítica correcta."""
        self.invoice_line.write({
            'maintenance_equipment_ids': [(4, self.equipment.id)],
        })
        self.assertIn(self.equipment, self.invoice_line.maintenance_equipment_ids)
        # Verificar inverse
        self.assertIn(self.invoice_line, self.equipment.maintenance_invoice_line_ids)

    def test_assign_request_to_line(self):
        """Verifica asignación de OT a línea con analítica correcta."""
        self.invoice_line.write({
            'maintenance_request_ids': [(4, self.request.id)],
        })
        self.assertIn(self.request, self.invoice_line.maintenance_request_ids)
        self.assertIn(self.invoice_line, self.request.invoice_line_ids)

    def test_cost_total_computed(self):
        """Verifica que el costo total se calcula correctamente."""
        self.invoice_line.write({
            'maintenance_equipment_ids': [(4, self.equipment.id)],
            'maintenance_request_ids': [(4, self.request.id)],
        })
        self.equipment.invalidate_recordset()
        self.request.invalidate_recordset()
        self.assertAlmostEqual(
            self.equipment.maintenance_cost_total,
            500000.0,
            places=2,
        )
        self.assertAlmostEqual(
            self.request.total_cost,
            500000.0,
            places=2,
        )

    def test_constraint_no_analytic(self):
        """Verifica que no se puede asignar equipo sin analítica de mantenimiento."""
        with self.assertRaises(ValidationError):
            self.line_no_maint.write({
                'maintenance_equipment_ids': [(4, self.equipment.id)],
            })

    def test_constraint_no_analytic_request(self):
        """Verifica que no se puede asignar OT sin analítica de mantenimiento."""
        with self.assertRaises(ValidationError):
            self.line_no_maint.write({
                'maintenance_request_ids': [(4, self.request.id)],
            })

    def test_multiple_equipments_per_line(self):
        """Una línea puede tener múltiples equipos."""
        equipment2 = self.env['maintenance.equipment'].create({
            'name': 'Ventilador Secado #2',
            'category_id': self.category.id,
        })
        self.invoice_line.write({
            'maintenance_equipment_ids': [(6, 0, [self.equipment.id, equipment2.id])],
        })
        self.assertEqual(len(self.invoice_line.maintenance_equipment_ids), 2)

    def test_equipment_invoice_count(self):
        """Verifica contador de líneas de factura en equipo."""
        self.invoice_line.write({
            'maintenance_equipment_ids': [(4, self.equipment.id)],
        })
        self.equipment.invalidate_recordset()
        self.assertEqual(self.equipment.maintenance_invoice_count, 1)
