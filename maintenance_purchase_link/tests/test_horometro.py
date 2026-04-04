from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestHorometro(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))

        cls.category = cls.env.ref(
            'maintenance_purchase_link.equipment_category_secado'
        )
        cls.equipment = cls.env['maintenance.equipment'].create({
            'name': 'Horno de Secado Test',
            'category_id': cls.category.id,
            'horometro_interval': 500.0,
            'horometro_last_maintenance': 0.0,
        })

    def test_reading_creation(self):
        """Crear lectura de horómetro."""
        reading = self.env['maintenance.horometro.reading'].create({
            'equipment_id': self.equipment.id,
            'value': 100.0,
        })
        self.assertEqual(reading.value, 100.0)
        self.equipment.invalidate_recordset()
        self.assertAlmostEqual(self.equipment.horometro_current, 100.0)

    def test_no_trigger_below_threshold(self):
        """No se genera OT si no se alcanza el intervalo."""
        reading = self.env['maintenance.horometro.reading'].create({
            'equipment_id': self.equipment.id,
            'value': 400.0,  # < 500
        })
        self.assertFalse(reading.triggered_request_id)

    def test_trigger_at_threshold(self):
        """Se genera OT al alcanzar el intervalo."""
        reading = self.env['maintenance.horometro.reading'].create({
            'equipment_id': self.equipment.id,
            'value': 500.0,
        })
        self.assertTrue(reading.triggered_request_id)
        self.assertEqual(
            reading.triggered_request_id.equipment_id,
            self.equipment,
        )
        # Verificar que last_maintenance se actualizó
        self.assertAlmostEqual(
            self.equipment.horometro_last_maintenance, 500.0,
        )

    def test_trigger_above_threshold(self):
        """Se genera OT al superar el intervalo."""
        reading = self.env['maintenance.horometro.reading'].create({
            'equipment_id': self.equipment.id,
            'value': 600.0,
        })
        self.assertTrue(reading.triggered_request_id)

    def test_consecutive_triggers(self):
        """Se generan OTs consecutivas cada intervalo."""
        # Primera lectura: 500h → trigger
        r1 = self.env['maintenance.horometro.reading'].create({
            'equipment_id': self.equipment.id,
            'value': 500.0,
        })
        self.assertTrue(r1.triggered_request_id)

        # Segunda lectura: 800h → no trigger (500+500=1000, 800<1000)
        r2 = self.env['maintenance.horometro.reading'].create({
            'equipment_id': self.equipment.id,
            'value': 800.0,
        })
        self.assertFalse(r2.triggered_request_id)

        # Tercera lectura: 1000h → trigger
        r3 = self.env['maintenance.horometro.reading'].create({
            'equipment_id': self.equipment.id,
            'value': 1000.0,
        })
        self.assertTrue(r3.triggered_request_id)

    def test_no_trigger_without_interval(self):
        """No se genera OT si el equipo no tiene intervalo configurado."""
        equipment2 = self.env['maintenance.equipment'].create({
            'name': 'Equipo sin intervalo',
            'category_id': self.category.id,
            'horometro_interval': 0.0,
        })
        reading = self.env['maintenance.horometro.reading'].create({
            'equipment_id': equipment2.id,
            'value': 9999.0,
        })
        self.assertFalse(reading.triggered_request_id)

    def test_negative_value_constraint(self):
        """No se permite lectura negativa."""
        with self.assertRaises(ValidationError):
            self.env['maintenance.horometro.reading'].create({
                'equipment_id': self.equipment.id,
                'value': -10.0,
            })

    def test_reading_count(self):
        """Verifica el contador de lecturas."""
        self.env['maintenance.horometro.reading'].create({
            'equipment_id': self.equipment.id,
            'value': 100.0,
        })
        self.env['maintenance.horometro.reading'].create({
            'equipment_id': self.equipment.id,
            'value': 200.0,
        })
        self.equipment.invalidate_recordset()
        self.assertEqual(self.equipment.horometro_reading_count, 2)
