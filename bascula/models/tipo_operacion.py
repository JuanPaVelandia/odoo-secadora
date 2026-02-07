# -*- coding: utf-8 -*-

from odoo import models, fields, api


class TipoOperacion(models.Model):
    _name = 'secadora.tipo.operacion'
    _description = 'Tipo de Operación de Báscula'
    _order = 'sequence, name'

    name = fields.Char(
        string='Nombre',
        required=True,
        help='Nombre del tipo de operación (ej: Compra de Arroz, Servicio de Secamiento)'
    )
    codigo = fields.Char(
        string='Código',
        required=True,
        help='Código único para identificar el tipo (ej: COMP, SEC, PRELIM)'
    )
    direccion = fields.Selection([
        ('entrada', 'Entrada'),
        ('salida', 'Salida'),
    ], string='Dirección', required=True,
       help='Define si esta operación es una entrada o salida de peso')

    # Configuración de integración
    afecta_inventario = fields.Boolean(
        string='Afecta Inventario',
        default=False,
        help='Si está marcado, esta operación creará movimientos de inventario'
    )
    tipo_inventario = fields.Selection([
        ('entrada', 'Entrada a Inventario'),
        ('salida', 'Salida de Inventario'),
    ], string='Tipo Movimiento Inventario',
       help='Tipo de movimiento que se creará en inventario')

    genera_factura = fields.Boolean(
        string='Genera Factura',
        default=False,
        help='Si está marcado, se podrá generar factura desde este pesaje'
    )
    tipo_factura = fields.Selection([
        ('cliente', 'Factura a Cliente'),
        ('proveedor', 'Factura de Proveedor'),
    ], string='Tipo de Factura',
       help='Tipo de factura que se generará')

    es_servicio = fields.Boolean(
        string='Es Servicio (Maquila)',
        default=False,
        help='Marca si es un servicio de maquila donde el producto no es propio'
    )

    requiere_precio = fields.Boolean(
        string='Requiere Precio',
        default=False,
        help='Si está marcado, el precio será obligatorio en el pesaje'
    )

    # Campos de configuración
    active = fields.Boolean(string='Activo', default=True)
    sequence = fields.Integer(string='Secuencia', default=10)
    color = fields.Integer(string='Color')

    descripcion = fields.Text(string='Descripción')

    _sql_constraints = [
        ('codigo_unique', 'unique(codigo)', 'El código del tipo de operación debe ser único!')
    ]

    @api.onchange('afecta_inventario')
    def _onchange_afecta_inventario(self):
        """Si no afecta inventario, limpiar tipo_inventario"""
        if not self.afecta_inventario:
            self.tipo_inventario = False

    @api.onchange('genera_factura')
    def _onchange_genera_factura(self):
        """Si no genera factura, limpiar tipo_factura"""
        if not self.genera_factura:
            self.tipo_factura = False
