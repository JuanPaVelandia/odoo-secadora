from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class MaintenanceEquipmentCostLine(models.Model):
    """Un costo de mantenimiento imputado a un equipo.

    La fuente habitual es una línea de factura de compra (`move_line_id`), pero
    NO es obligatoria: el histórico importado de sistemas externos no tiene
    respaldo contable y vive en este mismo modelo, para tener una sola lista,
    un solo total y un solo reporte de costos por equipo. El campo `origin`
    distingue de dónde viene cada línea.

    Los datos descriptivos (fecha, proveedor, cantidad, importe) se copian de
    la factura al crear y quedan almacenados, en vez de ser `related`: así una
    línea sin factura puede tenerlos igual.
    """

    _name = 'maintenance.equipment.cost.line'
    _description = 'Costo de mantenimiento por equipo'
    _order = 'date desc, id desc'

    # --- Origen del costo ---
    origin = fields.Selection(
        selection=[
            ('invoice', 'Factura'),
            ('historic', 'Histórico importado'),
            ('manual', 'Registro manual'),
        ],
        string='Origen',
        default='manual',
        required=True,
        index=True,
        help='De dónde proviene el costo. "Factura" lo mantiene sincronizado '
             'con el documento contable; los demás se editan a mano.',
    )
    move_line_id = fields.Many2one(
        'account.move.line',
        string='Línea de factura',
        ondelete='cascade',
        index=True,
        help='Vacío en los costos sin respaldo contable (histórico o manual).',
    )
    equipment_id = fields.Many2one(
        'maintenance.equipment',
        string='Equipo',
        index=True,
        ondelete='set null',
    )
    request_id = fields.Many2one(
        'maintenance.request',
        string='Orden de trabajo',
        index=True,
    )
    percentage = fields.Float(
        string='Porcentaje (%)',
        default=100.0,
        help='Parte de la línea de factura imputada a este equipo.',
    )
    amount = fields.Monetary(
        string='Monto',
        compute='_compute_amount',
        store=True,
        readonly=False,
        currency_field='currency_id',
        help='Se calcula desde la factura cuando la hay; en los costos sin '
             'factura se captura directamente.',
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        default=lambda self: self.env.company.currency_id,
        required=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        default=lambda self: self.env.company,
        index=True,
    )

    # --- Datos descriptivos ---
    # Se guardan (no son `related`) para que un costo sin factura los tenga.
    date = fields.Date(
        string='Fecha',
        required=True,
        index=True,
        default=fields.Date.context_today,
    )
    name = fields.Char(
        string='Descripción',
        required=True,
        default='Costo de mantenimiento',
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Proveedor',
        index=True,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Recurso',
    )
    quantity = fields.Float(string='Cantidad', default=1.0)
    uom_name = fields.Char(string='Unidad')
    unit_cost = fields.Monetary(
        string='Costo unitario',
        currency_field='currency_id',
    )

    # --- Trazabilidad del histórico importado ---
    source_name = fields.Char(
        string='Fuente',
        help='Taller o almacén de donde salió el recurso, tal como venía en '
             'el sistema de origen.',
    )
    code = fields.Char(string='Código del recurso')
    resource_type = fields.Selection([
        ('inventory', 'Inventario'),
        ('service', 'Servicios'),
        ('human', 'Recursos Humanos'),
        ('other', 'Otro'),
    ], string='Tipo de recurso')
    external_ref = fields.Char(
        string='Referencia externa',
        index=True,
        help='Identificador en el sistema de origen (ej. OT-999).',
    )
    notes = fields.Text(string='Notas')

    # --- Datos de la factura (solo cuando la hay) ---
    move_id = fields.Many2one(
        related='move_line_id.move_id',
        store=True,
        string='Factura',
    )
    x_webviewlink = fields.Char(
        related='move_id.x_webviewlink',
        string='Enlace documento Drive',
        readonly=True,
    )
    x_whatsapp_comprobante_link = fields.Char(
        related='move_id.x_whatsapp_comprobante_link',
        string='Enlace comprobante Whatsapp',
        readonly=True,
    )
    x_whatsapp_mensaje = fields.Char(
        related='move_id.x_whatsapp_mensaje',
        string='Mensaje de Whatsapp',
        readonly=True,
    )
    attachment_ids = fields.Many2many(
        'ir.attachment',
        compute='_compute_attachment_ids',
        string='Adjuntos',
    )
    attachment_count = fields.Integer(
        compute='_compute_attachment_ids',
        string='Nro. adjuntos',
    )

    def _compute_attachment_ids(self):
        Attachment = self.env['ir.attachment']
        for rec in self:
            if not rec.move_id:
                rec.attachment_ids = False
                rec.attachment_count = 0
                continue
            attachments = Attachment.search([
                ('res_model', '=', 'account.move'),
                ('res_id', '=', rec.move_id.id),
            ])
            rec.attachment_ids = attachments
            rec.attachment_count = len(attachments)

    _unique_line_equipment = models.Constraint(
        'UNIQUE(move_line_id, equipment_id)',
        'Un equipo solo puede asignarse una vez por línea de factura.',
    )

    @api.constrains('percentage')
    def _check_percentage_range(self):
        for rec in self:
            if rec.percentage < 0 or rec.percentage > 100:
                raise ValidationError(_(
                    'El porcentaje debe estar entre 0 y 100.'
                ))

    @api.constrains('percentage', 'move_line_id')
    def _check_total_percentage(self):
        for rec in self:
            if not rec.move_line_id:
                continue
            # sudo: los costos de una misma línea pueden quedar en compañías
            # distintas; sin él la suma ignoraba las que el usuario no tiene
            # activas y el reparto podía pasar del 100% sin avisar.
            total = sum(
                self.sudo().search([
                    ('move_line_id', '=', rec.move_line_id.id),
                ]).mapped('percentage')
            )
            if total > 100.0:
                raise ValidationError(_(
                    'La suma de porcentajes para la línea "%(line)s" '
                    'excede el 100%% (actual: %(total).1f%%).',
                    line=rec.move_line_id.name or rec.move_line_id.move_name,
                    total=total,
                ))

    def action_view_attachments(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Adjuntos de factura',
            'res_model': 'ir.attachment',
            'view_mode': 'list,form',
            'domain': [
                ('res_model', '=', 'account.move'),
                ('res_id', '=', self.move_id.id),
            ],
        }

    @api.depends('move_line_id.price_total', 'percentage')
    def _compute_amount(self):
        """El importe sigue a la factura; sin factura se respeta lo capturado."""
        for rec in self:
            if rec.move_line_id:
                rec.amount = rec.move_line_id.price_total * rec.percentage / 100.0
            else:
                rec.amount = rec.amount or 0.0

    @api.onchange('amount')
    def _onchange_amount_ajusta_porcentaje(self):
        """Repartir por monto: al escribir el importe se recalcula el %.

        El reparto entre equipos se guarda como porcentaje, pero en la práctica
        la factura se divide por montos ("a este equipo le tocan $300.000").
        Escribir el monto y que el sistema saque el porcentaje evita esa regla
        de tres a mano, que es de donde salían los repartos descuadrados.
        """
        for rec in self.filtered('move_line_id'):
            total = rec.move_line_id.price_total
            if total:
                rec.percentage = min(100.0, max(0.0, rec.amount * 100.0 / total))

    @api.onchange('move_line_id')
    def _onchange_move_line_id(self):
        """Al enlazar una factura, traer sus datos descriptivos."""
        for rec in self.filtered('move_line_id'):
            rec._copiar_datos_de_factura()

    def _copiar_datos_de_factura(self):
        """Copia a los campos propios los datos de la línea de factura."""
        for rec in self.filtered('move_line_id'):
            ml = rec.move_line_id
            rec.origin = 'invoice'
            rec.date = ml.date
            rec.name = ml.name or ml.product_id.display_name or _('Costo de mantenimiento')
            rec.partner_id = ml.partner_id
            rec.product_id = ml.product_id
            rec.quantity = ml.quantity
            rec.uom_name = ml.product_uom_id.name if ml.product_uom_id else False
            rec.currency_id = ml.currency_id or rec.company_id.currency_id
            rec.unit_cost = ml.price_unit
            if ml.move_id.company_id:
                rec.company_id = ml.move_id.company_id

    @api.model_create_multi
    def create(self, vals_list):
        # Las líneas creadas desde una factura heredan sus datos, para no
        # obligar a cada llamador a repetirlos.
        for vals in vals_list:
            if not vals.get('move_line_id'):
                continue
            ml = self.env['account.move.line'].sudo().browse(vals['move_line_id'])
            # La compañía y la moneda SIEMPRE mandan desde la factura, no desde
            # la compañía activa de quien guarda: con `setdefault` el default
            # del campo (env.company) ya venía puesto y el costo se registraba
            # en la compañía equivocada.
            if ml.move_id.company_id:
                vals['company_id'] = ml.move_id.company_id.id
            if ml.currency_id:
                vals['currency_id'] = ml.currency_id.id
            if not vals.get('date'):
                vals.setdefault('origin', 'invoice')
                vals.setdefault('date', ml.date)
                vals.setdefault(
                    'name',
                    ml.name or ml.product_id.display_name
                    or _('Costo de mantenimiento'))
                vals.setdefault('partner_id', ml.partner_id.id)
                vals.setdefault('product_id', ml.product_id.id)
                vals.setdefault('quantity', ml.quantity)
                vals.setdefault('unit_cost', ml.price_unit)
                if ml.product_uom_id:
                    vals.setdefault('uom_name', ml.product_uom_id.name)
        lineas = super().create(vals_list)
        lineas._propagar_equipo_a_la_ot()
        return lineas

    def write(self, vals):
        res = super().write(vals)
        if vals.get('equipment_id') or vals.get('request_id'):
            self._propagar_equipo_a_la_ot()
        return res

    def _propagar_equipo_a_la_ot(self):
        """Darle a la orden de trabajo el equipo del costo, si no tiene.

        Una OT creada desde el flujo de costos nace sin equipo: se elige el
        equipo en el costo, no en la orden. Sin esto la OT queda huérfana —
        no aparece en el historial del equipo y hereda la compañía activa de
        quien la crea en vez de la del equipo.

        Solo rellena las vacías: si la OT ya tiene equipo, manda ese.
        """
        for rec in self:
            ot = rec.request_id.sudo()
            if not (ot and rec.equipment_id and not ot.equipment_id):
                continue
            # Equipo y compañía se escriben JUNTOS, en un solo write. Por
            # separado, Odoo valida el cruce de compañías al poner el equipo
            # —cuando la OT todavía tiene la anterior— y rechaza la operación
            # con "inconsistencias en la empresa", aunque la línea siguiente
            # fuera a corregirla. El coordinador imputa facturas de varias
            # empresas seguidas, así que este caso es el normal, no el raro.
            valores = {'equipment_id': rec.equipment_id.id}
            # La compañía sigue al equipo: la OT es trabajo sobre ese activo,
            # no de quien la registró.
            if rec.equipment_id.company_id:
                valores['company_id'] = rec.equipment_id.company_id.id
            ot.write(valores)
