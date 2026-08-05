from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestMaintenanceCost(TransactionCase):

    # Columnas de res_partner que alguna localización dejó NOT NULL sin default,
    # con el valor a usar. La localización colombiana pone el régimen fiscal;
    # '48' = No responsable de IVA.
    COLUMNAS_OBLIGATORIAS_PARTNER = {
        'l10n_co_edi_fiscal_regimen': '48',
    }

    @classmethod
    def _crear_partner_de_prueba(cls, vals):
        """Crear el proveedor sorteando las columnas NOT NULL de localizaciones.

        No basta con mirar `_fields`: una localización desinstalada puede dejar
        la columna NOT NULL en Postgres aunque el ORM ya no conozca el campo,
        y entonces el INSERT sale sin ella y el test ni siquiera arranca. Se
        consulta la tabla real y lo que el ORM no sepa escribir se rellena por
        SQL después de crear.
        """
        partner_model = cls.env['res.partner']
        cls.env.cr.execute("""
            SELECT column_name
              FROM information_schema.columns
             WHERE table_name = 'res_partner'
               AND is_nullable = 'NO'
               AND column_default IS NULL
        """)
        no_nulas = {fila[0] for fila in cls.env.cr.fetchall()}

        pendientes_sql = {}
        for columna, valor in cls.COLUMNAS_OBLIGATORIAS_PARTNER.items():
            if columna not in no_nulas:
                continue
            if columna in partner_model._fields:
                vals[columna] = valor
            else:
                # El ORM no conoce el campo: hay que ponerlo a mano.
                pendientes_sql[columna] = valor

        if not pendientes_sql:
            return partner_model.create(vals)

        # Sin el campo en el ORM, `create` genera un INSERT que viola el NOT
        # NULL. Se pone un valor por defecto en la columna solo durante la
        # transacción del test, que se revierte al terminar.
        for columna, valor in pendientes_sql.items():
            cls.env.cr.execute(
                'ALTER TABLE res_partner ALTER COLUMN "%s" SET DEFAULT %%s'
                % columna, (valor,))
        partner = partner_model.create(vals)
        for columna in pendientes_sql:
            cls.env.cr.execute(
                'ALTER TABLE res_partner ALTER COLUMN "%s" DROP DEFAULT' % columna)
        return partner

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
        partner_vals = {
            'name': 'Proveedor Test Mantenimiento',
            'supplier_rank': 1,
        }
        cls.partner = cls._crear_partner_de_prueba(partner_vals)

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

    # --- Equipo asignado después de publicar ---

    def _factura_maquinaria(self, fecha, precio=300000.0):
        """Factura de compra publicable, con la línea marcada como Maquinaria."""
        return self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner.id,
            'invoice_date': fecha,
            'invoice_line_ids': [(0, 0, {
                'name': 'Repuesto',
                'quantity': 1,
                'price_unit': precio,
                'analytic_distribution': {str(self.maint_account.id): 100},
            })],
        })

    def test_equipo_asignado_despues_de_publicar_no_duplica(self):
        """Publicar y luego asignar el equipo rellena el costo, no crea otro."""
        factura = self._factura_maquinaria('2026-08-01')
        factura.action_post()

        linea = factura.invoice_line_ids
        costos = linea.equipment_cost_line_ids
        self.assertEqual(len(costos), 1, 'Al publicar debe nacer un costo.')
        self.assertFalse(costos.equipment_id, 'Nace sin equipo, por diseño.')

        factura.write({
            'maintenance_equipment_line_ids': [(0, 0, {
                'equipment_id': self.equipment.id,
                'percentage': 100.0,
            })],
        })

        linea.invalidate_recordset()
        costos = linea.equipment_cost_line_ids
        self.assertEqual(len(costos), 1,
                         'El costo huérfano debía rellenarse, no duplicarse.')
        self.assertEqual(costos.equipment_id, self.equipment)

    def test_equipo_asignado_en_borrador_baja_al_publicar(self):
        """Equipos puestos en borrador deben bajar a los costos al publicar."""
        factura = self._factura_maquinaria('2026-08-02')
        factura.write({
            'maintenance_equipment_line_ids': [(0, 0, {
                'equipment_id': self.equipment.id,
                'percentage': 100.0,
            })],
        })
        factura.action_post()

        linea = factura.invoice_line_ids
        linea.invalidate_recordset()
        costos = linea.equipment_cost_line_ids
        self.assertEqual(len(costos), 1)
        self.assertEqual(costos.equipment_id, self.equipment,
                         'El equipo asignado en borrador se perdió al publicar.')

    # --- Compañía y fecha pivote ---

    def _otra_compania(self):
        """Una compañía distinta de la activa.

        Se prefiere una que ya exista (la secadora tiene varias) antes que
        crearla: `res.company.create` crea por dentro su propio partner, y con
        la localización colombiana ese partner exige campos que aquí no se
        pueden pasar.
        """
        otra = self.env['res.company'].search(
            [('id', '!=', self.env.company.id)], limit=1)
        return otra or self.env['res.company'].create(
            {'name': 'Otra Compañía Test'})

    def test_costo_toma_la_compania_de_la_factura(self):
        """La compañía sale de la factura, no de la compañía activa."""
        otra = self._otra_compania()
        factura = self._factura_maquinaria('2026-08-03')
        factura.company_id = otra

        costo = self.env['maintenance.equipment.cost.line'].create({
            'move_line_id': factura.invoice_line_ids[0].id,
            'equipment_id': self.equipment.id,
        })
        self.assertEqual(costo.company_id, otra,
                         'El costo quedó en la compañía equivocada.')

    def test_factura_anterior_al_pivote_no_crea_costos(self):
        """Antes del corte manda el histórico importado: no duplicar."""
        factura = self._factura_maquinaria('2026-01-15')
        factura.action_post()
        self.assertFalse(
            factura.invoice_line_ids.equipment_cost_line_ids,
            'Una factura anterior al pivote no debe generar costos.')

    def test_factura_posterior_al_pivote_si_crea_costos(self):
        """Desde el corte en adelante el costo sí sale de la factura."""
        factura = self._factura_maquinaria('2026-07-21')
        factura.action_post()
        self.assertTrue(
            factura.invoice_line_ids.equipment_cost_line_ids,
            'Una factura posterior al pivote debe generar su costo.')

    def test_pivote_usa_la_fecha_contable_si_no_hay_fecha_de_factura(self):
        """Sin invoice_date manda la fecha del asiento, no se cuela la factura."""
        factura = self._factura_maquinaria(False)
        factura.date = '2026-01-15'
        factura.action_post()
        self.assertFalse(
            factura.invoice_line_ids.equipment_cost_line_ids,
            'Sin fecha de factura se coló una anterior al pivote.')

    # --- La OT asignada a mano no se debe perder ---

    def test_propagar_equipo_no_borra_la_ot_puesta_a_mano(self):
        """La factura no trae OT; la que se puso en el costo debe sobrevivir."""
        factura = self._factura_maquinaria('2026-08-04')
        factura.action_post()

        costo = factura.invoice_line_ids.equipment_cost_line_ids
        costo.request_id = self.request

        # Asignar el equipo desde la factura (sin OT en esa pestaña).
        factura.write({
            'maintenance_equipment_line_ids': [(0, 0, {
                'equipment_id': self.equipment.id,
                'percentage': 100.0,
            })],
        })

        costo.invalidate_recordset()
        self.assertEqual(costo.equipment_id, self.equipment)
        self.assertEqual(costo.request_id, self.request,
                         'La orden de trabajo asignada a mano se borró.')

    # --- Reparto por montos ---

    def test_escribir_el_monto_recalcula_el_porcentaje(self):
        """Repartir en pesos: el % sale del monto, no al revés."""
        factura = self._factura_maquinaria('2026-08-05', precio=500000.0)
        factura.action_post()

        costo = factura.invoice_line_ids.equipment_cost_line_ids
        total = costo.move_line_id.price_total

        costo.equipment_id = self.equipment
        costo.amount = total * 0.30
        costo._onchange_amount_ajusta_porcentaje()

        self.assertAlmostEqual(
            costo.percentage, 30.0, places=2,
            msg='El monto escrito no se tradujo al porcentaje correcto.')

    # --- Total del equipo con varias compañías ---

    def test_total_del_equipo_suma_todas_las_companias(self):
        """El total no debe depender de las compañías activas del usuario."""
        otra = self._otra_compania()
        CostLine = self.env['maintenance.equipment.cost.line']
        total_previo = self.equipment.maintenance_cost_total

        CostLine.create({
            'equipment_id': self.equipment.id,
            'name': 'Costo compañía propia',
            'date': '2026-08-06',
            'amount': 100000.0,
            'company_id': self.env.company.id,
        })
        CostLine.create({
            'equipment_id': self.equipment.id,
            'name': 'Costo de la otra compañía',
            'date': '2026-08-06',
            'amount': 250000.0,
            'company_id': otra.id,
        })

        self.equipment.invalidate_recordset()
        self.assertEqual(
            self.equipment.maintenance_cost_total - total_previo, 350000.0,
            'El total ignoró los costos de otra compañía del grupo.')

    # --- Asignación a nivel de factura (vista "Facturas por asignar") ---

    def _factura_maquinaria_multilinea(self, fecha, lineas=3, precio=100000.0):
        """Factura publicable con varias líneas marcadas como Maquinaria."""
        return self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner.id,
            'invoice_date': fecha,
            'invoice_line_ids': [
                (0, 0, {
                    'name': f'Repuesto {n + 1}',
                    'quantity': 1,
                    'price_unit': precio,
                    'analytic_distribution': {str(self.maint_account.id): 100},
                })
                for n in range(lineas)
            ],
        })

    def test_asignar_equipo_en_la_factura_llega_a_todas_las_lineas(self):
        """Un solo equipo escrito en la factura basta para todas sus líneas."""
        factura = self._factura_maquinaria_multilinea('2026-08-07')
        factura.action_post()
        self.assertEqual(factura.maintenance_pending_count, 3,
                         'Deben quedar 3 costos sin equipo tras publicar.')

        factura.maintenance_equipment_id = self.equipment

        costos = factura.invoice_line_ids.equipment_cost_line_ids
        self.assertEqual(len(costos), 3,
                         'Debe haber un costo por línea, sin duplicados.')
        self.assertEqual(costos.equipment_id, self.equipment)
        factura.invalidate_recordset()
        self.assertEqual(factura.maintenance_pending_count, 0,
                         'Ya no debería quedar nada pendiente.')

    def test_asignar_ot_despues_del_equipo_baja_a_los_costos(self):
        """La OT puesta después del equipo debe llegar a los costos existentes."""
        factura = self._factura_maquinaria_multilinea('2026-08-08', lineas=2)
        factura.action_post()
        factura.maintenance_equipment_id = self.equipment

        factura.maintenance_request_id = self.request

        costos = factura.invoice_line_ids.equipment_cost_line_ids
        self.assertEqual(len(costos), 2, 'La OT no debía crear costos nuevos.')
        self.assertEqual(costos.request_id, self.request,
                         'La orden de trabajo no bajó a los costos ya creados.')

    def test_asignar_ot_antes_del_equipo_baja_a_los_costos(self):
        """La OT sola (aún sin equipo) también debe llegar a los costos."""
        factura = self._factura_maquinaria_multilinea('2026-08-09', lineas=2)
        factura.action_post()

        factura.maintenance_request_id = self.request

        costos = factura.invoice_line_ids.equipment_cost_line_ids
        self.assertEqual(len(costos), 2)
        self.assertEqual(costos.request_id, self.request,
                         'La OT sin equipo no bajó a los costos.')

    def test_ot_primero_y_equipo_despues(self):
        """Indicar la OT antes que el equipo no debe bloquear la asignación."""
        factura = self._factura_maquinaria_multilinea('2026-08-14', lineas=2)
        factura.action_post()

        factura.maintenance_request_id = self.request
        factura.maintenance_equipment_id = self.equipment

        costos = factura.invoice_line_ids.equipment_cost_line_ids
        self.assertEqual(len(costos), 2,
                         'Debe quedar un costo por línea, sin duplicados.')
        self.assertEqual(costos.equipment_id, self.equipment)
        self.assertEqual(costos.request_id, self.request)
        self.assertEqual(sum(costos.mapped('percentage')), 200.0,
                         'Cada línea se imputa al 100% a su único equipo.')

    def test_la_ot_puesta_a_mano_sobrevive_a_la_asignacion_por_factura(self):
        """Asignar el equipo desde la factura no pisa una OT puesta a mano."""
        factura = self._factura_maquinaria_multilinea('2026-08-10', lineas=1)
        factura.action_post()
        costo = factura.invoice_line_ids.equipment_cost_line_ids
        otra_ot = self.env['maintenance.request'].create({
            'name': 'OT puesta a mano',
            'equipment_id': self.equipment.id,
        })
        costo.request_id = otra_ot

        factura.maintenance_equipment_id = self.equipment

        costo.invalidate_recordset()
        self.assertEqual(costo.request_id, otra_ot,
                         'Se perdió la OT asignada a mano en el costo.')

    def test_el_equipo_de_la_factura_queda_vacio_si_hay_reparto(self):
        """Con reparto entre equipos no hay un único equipo que mostrar."""
        equipo2 = self.env['maintenance.equipment'].create({
            'name': 'Horno de Secado #2',
            'category_id': self.category.id,
        })
        factura = self._factura_maquinaria_multilinea('2026-08-11', lineas=1)
        factura.action_post()
        factura.write({
            'maintenance_equipment_line_ids': [
                (0, 0, {'equipment_id': self.equipment.id, 'percentage': 60.0}),
                (0, 0, {'equipment_id': equipo2.id, 'percentage': 40.0}),
            ],
        })

        factura.invalidate_recordset()
        self.assertFalse(
            factura.maintenance_equipment_id,
            'Con dos equipos no debe mostrarse uno solo como si fuera todo.')
        costos = factura.invoice_line_ids.equipment_cost_line_ids
        self.assertEqual(len(costos), 2, 'El reparto debe dejar dos costos.')
        self.assertEqual(sum(costos.mapped('percentage')), 100.0)

    def test_la_ot_no_rompe_el_reparto_entre_equipos(self):
        """Escribir la OT sobre un reparto lo conserva."""
        equipo2 = self.env['maintenance.equipment'].create({
            'name': 'Horno de Secado #3',
            'category_id': self.category.id,
        })
        factura = self._factura_maquinaria_multilinea('2026-08-12', lineas=1)
        factura.action_post()
        factura.write({
            'maintenance_equipment_line_ids': [
                (0, 0, {'equipment_id': self.equipment.id, 'percentage': 60.0}),
                (0, 0, {'equipment_id': equipo2.id, 'percentage': 40.0}),
            ],
        })

        factura.maintenance_request_id = self.request

        costos = factura.invoice_line_ids.equipment_cost_line_ids
        self.assertEqual(len(costos), 2, 'La OT no debía alterar el reparto.')
        self.assertEqual(sorted(costos.mapped('percentage')), [40.0, 60.0])
        self.assertEqual(costos.request_id, self.request)

    def test_buscar_facturas_pendientes(self):
        """El filtro 'Pendientes por asignar' debe encontrar la factura."""
        factura = self._factura_maquinaria_multilinea('2026-08-13', lineas=2)
        factura.action_post()

        pendientes = self.env['account.move'].search([
            ('maintenance_pending_count', '>', 0),
        ])
        self.assertIn(factura, pendientes,
                      'La factura sin asignar no salió en el filtro.')

        factura.maintenance_equipment_id = self.equipment

        pendientes = self.env['account.move'].search([
            ('maintenance_pending_count', '>', 0),
        ])
        self.assertNotIn(factura, pendientes,
                         'La factura ya asignada sigue apareciendo pendiente.')
        asignadas = self.env['account.move'].search([
            ('maintenance_pending_count', '=', 0),
        ])
        self.assertIn(factura, asignadas,
                      'La factura asignada no salió en "Ya asignadas".')
