from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    maintenance_equipment_line_ids = fields.One2many(
        'maintenance.invoice.equipment',
        'move_id',
        string='Equipos de mantenimiento',
    )

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
            if not eq_rows:
                continue

            existing = CostLine.search([
                ('move_line_id', 'in', product_lines.ids),
            ])
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

            vals_list = []
            for eq_id, percentage, request_id in eq_rows:
                for ml in product_lines:
                    if (ml.id, eq_id) in existing_keys:
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
        if 'maintenance_equipment_line_ids' in vals or 'invoice_line_ids' in vals:
            self._propagate_equipment_to_lines()
        return res
