from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class MaintenanceHistoricCost(models.Model):
    """Costo de mantenimiento sin factura asociada.

    El costo corriente vive en `maintenance.equipment.cost.line`, que exige una
    línea de factura real (`move_line_id`). El histórico importado de Fracttal
    no tiene respaldo contable, así que se guarda aquí: suma en los totales por
    equipo y por OT, pero no toca contabilidad.
    """

    _name = 'maintenance.historic.cost'
    _description = 'Costo histórico de mantenimiento (sin factura)'
    _order = 'date desc, id desc'

    equipment_id = fields.Many2one(
        'maintenance.equipment',
        string='Equipo',
        required=True,
        index=True,
        ondelete='cascade',
    )
    request_id = fields.Many2one(
        'maintenance.request',
        string='Orden de trabajo',
        index=True,
        ondelete='cascade',
    )
    date = fields.Date(
        string='Fecha',
        required=True,
        index=True,
    )
    name = fields.Char(
        string='Descripción',
        required=True,
    )
    code = fields.Char(
        string='Código del recurso',
        help='Código del repuesto/servicio en el sistema de origen.',
    )
    resource_type = fields.Selection([
        ('inventory', 'Inventario'),
        ('service', 'Servicios'),
        ('human', 'Recursos Humanos'),
        ('other', 'Otro'),
    ], string='Tipo de recurso', default='inventory')
    partner_id = fields.Many2one(
        'res.partner',
        string='Proveedor / Fuente',
        help='Taller o almacén de donde salió el recurso.',
    )
    source_name = fields.Char(
        string='Fuente (texto original)',
        help='Nombre de la fuente tal como venía en el sistema de origen.',
    )
    quantity = fields.Float(
        string='Cantidad',
        default=1.0,
    )
    uom_name = fields.Char(string='Unidad')
    unit_cost = fields.Monetary(
        string='Costo unitario',
        currency_field='currency_id',
    )
    amount = fields.Monetary(
        string='Costo total',
        currency_field='currency_id',
        required=True,
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
    origin = fields.Char(
        string='Origen',
        default='Fracttal',
        help='Sistema del que proviene el registro.',
    )
    external_ref = fields.Char(
        string='Referencia externa',
        index=True,
        help='Id de la OT en el sistema de origen (ej. OT-999).',
    )
    notes = fields.Text(string='Notas')

    @api.constrains('quantity')
    def _check_quantity(self):
        for rec in self:
            if rec.quantity < 0:
                raise ValidationError(_('La cantidad no puede ser negativa.'))
