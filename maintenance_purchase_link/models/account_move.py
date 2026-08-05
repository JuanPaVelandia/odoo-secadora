import operator

from odoo import api, fields, models

# Operadores admitidos al buscar por número de costos pendientes.
OPERADORES = {
    '=': operator.eq,
    '!=': operator.ne,
    '<': operator.lt,
    '<=': operator.le,
    '>': operator.gt,
    '>=': operator.ge,
}


class AccountMove(models.Model):
    _inherit = 'account.move'

    maintenance_equipment_line_ids = fields.One2many(
        'maintenance.invoice.equipment',
        'move_id',
        string='Equipos de mantenimiento',
    )
    maintenance_pending_count = fields.Integer(
        string='Costos sin equipo',
        compute='_compute_maintenance_pending_count',
        search='_search_maintenance_pending_count',
        help='Cuántos costos de mantenimiento de esta factura siguen sin '
             'equipo asignado.',
    )
    # El reparto real vive en `maintenance_equipment_line_ids`, que admite
    # varios equipos con su porcentaje. Estos dos campos son la vista
    # "un equipo y una OT para toda la factura", que es el caso corriente:
    # permiten asignar desde una lista (incluso en varias facturas a la vez)
    # sin abrir cada factura ni cada línea de costo.
    maintenance_equipment_id = fields.Many2one(
        'maintenance.equipment',
        string='Equipo',
        compute='_compute_maintenance_assignment',
        inverse='_inverse_maintenance_equipment_id',
        help='Equipo al que se imputa toda la factura. Si el costo está '
             'repartido entre varios equipos se muestra vacío; en ese caso '
             'el reparto se edita en la pestaña Mantenimiento de la factura.',
    )
    maintenance_request_id = fields.Many2one(
        'maintenance.request',
        string='Orden de trabajo',
        compute='_compute_maintenance_assignment',
        inverse='_inverse_maintenance_request_id',
        help='Orden de trabajo a la que se imputa toda la factura.',
    )

    @api.depends('maintenance_equipment_line_ids.equipment_id',
                 'maintenance_equipment_line_ids.request_id')
    def _compute_maintenance_assignment(self):
        """Equipo y OT de la factura, solo cuando son uno solo.

        Con reparto entre varios equipos no hay un único valor que mostrar:
        se deja vacío antes que enseñar uno de los dos y hacer creer que ese
        es todo el costo.
        """
        for move in self:
            lineas = move.maintenance_equipment_line_ids
            equipos = lineas.equipment_id
            ots = lineas.request_id
            move.maintenance_equipment_id = equipos if len(equipos) == 1 else False
            move.maintenance_request_id = ots if len(ots) == 1 else False

    def _inverse_maintenance_equipment_id(self):
        """Asignar un equipo único a la factura completa."""
        for move in self:
            lineas = move.maintenance_equipment_line_ids
            if not move.maintenance_equipment_id:
                # Vaciar el campo no puede borrar un reparto entre varios
                # equipos: ese vacío es el que el compute muestra por no
                # haber un valor único, no una orden de desasignar.
                if len(lineas) == 1:
                    if lineas.request_id:
                        # Quitar el equipo pero conservar la OT indicada.
                        lineas.equipment_id = False
                    else:
                        lineas.unlink()
                continue
            if len(lineas) == 1:
                lineas.equipment_id = move.maintenance_equipment_id
                continue
            # Reemplazar un reparto por un solo equipo: se conserva la OT si
            # todas las filas coincidían en ella.
            ot = lineas.request_id if len(lineas.request_id) == 1 else False
            lineas.unlink()
            self.env['maintenance.invoice.equipment'].create({
                'move_id': move.id,
                'equipment_id': move.maintenance_equipment_id.id,
                'percentage': 100.0,
                'request_id': ot.id if ot else False,
            })

    def _inverse_maintenance_request_id(self):
        """Asignar la OT a la factura completa, respetando el reparto."""
        for move in self:
            lineas = move.maintenance_equipment_line_ids
            if lineas:
                # La OT aplica a todo el reparto: es la misma intervención,
                # aunque el costo se divida entre varios equipos.
                lineas.request_id = move.maintenance_request_id
                continue
            if not move.maintenance_request_id:
                continue
            # Poner OT sin equipo todavía: se guarda la intención para que
            # baje a los costos en cuanto se elija el equipo.
            self.env['maintenance.invoice.equipment'].create({
                'move_id': move.id,
                'request_id': move.maintenance_request_id.id,
                'percentage': 100.0,
            })

    def _compute_maintenance_pending_count(self):
        """Costos de la factura que aún no tienen equipo.

        sudo: los costos pueden vivir en otra compañía que el usuario no
        tiene activa; sin él la factura parecería ya asignada.
        """
        agrupado = {}
        if self.ids:
            agrupado = {
                move.id: contador
                for move, contador in self.env['maintenance.equipment.cost.line'].sudo()._read_group(
                    [('move_id', 'in', self.ids), ('equipment_id', '=', False)],
                    groupby=['move_id'],
                    aggregates=['__count'],
                )
            }
        for move in self:
            move.maintenance_pending_count = agrupado.get(move.id, 0)

    def _search_maintenance_pending_count(self, operador, valor):
        """Buscar facturas por costos sin equipo (para el filtro 'Pendientes').

        El agrupado solo trae facturas que tienen algún costo pendiente. Las
        demás cuentan cero, y hay que incluirlas cuando la condición se cumple
        con cero (p. ej. "= 0", el filtro "Ya asignadas").
        """
        if operador not in OPERADORES:
            raise NotImplementedError(
                'Operador no soportado en maintenance_pending_count: %s' % operador)
        comparar = OPERADORES[operador]
        pendientes = self.env['maintenance.equipment.cost.line'].sudo()._read_group(
            [('equipment_id', '=', False), ('move_id', '!=', False)],
            groupby=['move_id'],
            aggregates=['__count'],
        )
        con_pendientes = [
            move.id for move, contador in pendientes if comparar(contador, valor)
        ]
        if comparar(0, valor):
            # Cumplen las que no aparecen en el agrupado más las del agrupado
            # que también satisfacen la condición.
            return ['|',
                    ('id', 'not in', [move.id for move, _c in pendientes]),
                    ('id', 'in', con_pendientes)]
        return [('id', 'in', con_pendientes)]

    def _post(self, soft=True):
        """Al publicar factura, crear cost lines para líneas con Unidad de negocio = Maquinaria."""
        posted = super()._post(soft=soft)
        posted._auto_create_maintenance_cost_lines()
        # Si los equipos ya se habían asignado con la factura en borrador,
        # bajarlos ahora: las líneas de costo acaban de nacer y estarían vacías.
        posted._propagate_equipment_to_lines()
        return posted

    def _fecha_pivote_costos(self):
        """Fecha desde la cual los costos de mantenimiento salen de facturas.

        Antes de esta fecha el costo del equipo ya viene del histórico importado
        del sistema anterior (Fracttal), que se trajo desde el principio. Como en
        contabilidad las facturas se migran desde enero, sin este corte el mismo
        gasto quedaría contado dos veces: una por el histórico y otra por la
        factura. Ajustable en Ajustes > Técnico > Parámetros del sistema.
        """
        valor = self.env['ir.config_parameter'].sudo().get_param(
            'maintenance_purchase_link.fecha_pivote_costos', '2026-07-20')
        return fields.Date.to_date(valor) if valor else None

    def _auto_create_maintenance_cost_lines(self):
        """Crear cost lines automáticamente para líneas con Unidad de negocio = Maquinaria."""
        CostLine = self.env['maintenance.equipment.cost.line']
        fecha_pivote = self._fecha_pivote_costos()
        # Hay una cuenta "Maquinaria" POR COMPAÑÍA: aceptar cualquiera de
        # ellas (con sudo: el usuario que publica puede no ver las de otras
        # compañías por las reglas multi-compañía).
        maquinaria_keys = {
            str(a.id) for a in self.env['account.analytic.account'].sudo().search([
                ('name', '=ilike', 'maquinaria'),
                ('plan_id.name', '=ilike', 'unidad de negocio'),
            ])
        }
        if not maquinaria_keys:
            return

        for move in self.filtered(lambda m: m.move_type == 'in_invoice'):
            # Las facturas anteriores al corte ya están representadas en el
            # histórico importado; crearles costos los duplicaría.
            # Al publicar siempre hay fecha: si `invoice_date` viniera vacía se
            # usa la del asiento, para que ninguna factura se cuele por no
            # tenerla.
            fecha_factura = move.invoice_date or move.date
            if fecha_pivote and fecha_factura and fecha_factura < fecha_pivote:
                continue
            for ml in move.invoice_line_ids.filtered(lambda l: l.display_type == 'product'):
                distribution = ml.analytic_distribution or {}
                # Las claves de la distribución pueden ser compuestas
                # ("16,45") cuando la línea combina varios planes analíticos.
                if not any(maquinaria_keys & set(k.split(',')) for k in distribution):
                    continue

                # Solo crear si no existe ya una cost line para esta línea
                existing = CostLine.search([
                    ('move_line_id', '=', ml.id),
                ], limit=1)
                if existing:
                    continue

                CostLine.create({
                    'move_line_id': ml.id,
                    # Sin equipo ni OT — se asignan después desde mantenimiento
                })

    def _propagate_equipment_to_lines(self):
        """Propagar equipos a cost lines. Solo agrega nuevos, nunca borra ni sobreescribe.

        Se usa sudo porque el equipo asignado puede pertenecer a otra compañía
        que el usuario no tiene activa; sin él la propagación lo omitía en
        silencio y el costo quedaba sin equipo.
        """
        CostLine = self.env['maintenance.equipment.cost.line'].sudo()
        for move in self:
            product_lines = move.invoice_line_ids.filtered(
                lambda l: l.display_type == 'product'
            )
            if not product_lines:
                continue

            # Leer por ORM (no SQL crudo): los equipos recién agregados en el
            # mismo guardado todavía viven en la caché y el SELECT no los veía,
            # así que el equipo nunca bajaba a las líneas de costo.
            eq_rows = [
                (line.equipment_id.id, line.percentage, line.request_id.id)
                for line in move.sudo().maintenance_equipment_line_ids
                if line.equipment_id
            ]

            existing = CostLine.search([
                ('move_line_id', 'in', product_lines.ids),
            ])

            if not eq_rows:
                # Puede haberse indicado la OT antes que el equipo. Esa orden
                # sí baja a los costos: identifica la intervención aunque
                # todavía no se sepa a qué equipo imputarla.
                ot_sola = move.sudo().maintenance_equipment_line_ids.filtered(
                    lambda l: not l.equipment_id and l.request_id
                ).request_id[:1]
                if ot_sola:
                    existing.filtered(lambda cl: not cl.request_id).request_id = ot_sola
                continue

            existing_keys = {
                (cl.move_line_id.id, cl.equipment_id.id)
                for cl in existing
            }

            # Al publicar se crean líneas de costo sin equipo. Si el equipo se
            # asigna después, hay que rellenar esas líneas en vez de crear otras
            # nuevas: si no, el mismo costo quedaba dos veces (una huérfana sin
            # equipo y otra con él) y el total del equipo salía inflado.
            huerfanas = {
                cl.move_line_id.id: cl
                for cl in existing
                if not cl.equipment_id
            }

            # Índice de los costos ya asignados, para poder completarlos: si
            # la OT se agrega después del equipo (el caso corriente al asignar
            # desde la lista de facturas), el par línea+equipo ya existe y sin
            # esto la orden nunca bajaba al costo.
            por_linea_y_equipo = {
                (cl.move_line_id.id, cl.equipment_id.id): cl
                for cl in existing
                if cl.equipment_id
            }

            vals_list = []
            for eq_id, percentage, request_id in eq_rows:
                for ml in product_lines:
                    if (ml.id, eq_id) in existing_keys:
                        # Solo se rellena la OT vacía: una puesta a mano en el
                        # detalle de costos manda sobre la de la factura.
                        ya_existente = por_linea_y_equipo.get((ml.id, eq_id))
                        if request_id and ya_existente and not ya_existente.request_id:
                            ya_existente.request_id = request_id
                        continue
                    # Marcar de una vez: si el mismo equipo vuelve a aparecer
                    # en esta pasada no debe generar una segunda línea.
                    existing_keys.add((ml.id, eq_id))
                    valores = {'equipment_id': eq_id, 'percentage': percentage}
                    # La OT solo se propaga si la factura la trae. Un `False`
                    # aquí borraría la orden que el usuario haya puesto a mano
                    # en el detalle de costos, que es donde se asigna.
                    if request_id:
                        valores['request_id'] = request_id
                    huerfana = huerfanas.pop(ml.id, None)
                    if huerfana:
                        huerfana.write(valores)
                        continue
                    vals_list.append(dict(valores, move_line_id=ml.id))
            if vals_list:
                CostLine.create(vals_list)

    def action_view_cost_lines(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Costos asignados',
            'res_model': 'maintenance.equipment.cost.line',
            'view_mode': 'list,form',
            'domain': [('move_id', '=', self.id)],
        }

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        moves.filtered('maintenance_equipment_line_ids')._propagate_equipment_to_lines()
        return moves

    def write(self, vals):
        res = super().write(vals)
        # También cuando cambian las líneas de la factura: una línea nueva en
        # una factura que ya tenía equipos asignados debe recibirlos igual.
        # Los campos de asignación rápida escriben a través de su `inverse`,
        # que el super ya ejecutó: aquí solo hay que bajar el resultado a los
        # costos.
        disparadores = {
            'maintenance_equipment_line_ids',
            'invoice_line_ids',
            'maintenance_equipment_id',
            'maintenance_request_id',
        }
        if disparadores & vals.keys():
            self._propagate_equipment_to_lines()
        return res
