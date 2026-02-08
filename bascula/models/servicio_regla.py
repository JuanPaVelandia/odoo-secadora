# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ServicioRegla(models.Model):
    _name = 'secadora.servicio.regla'
    _description = 'Reglas de Servicios Automáticos'
    _order = 'sequence, id'

    name = fields.Char(
        string='Nombre de Regla',
        required=True,
        help='Nombre descriptivo de esta regla'
    )

    sequence = fields.Integer(
        string='Secuencia',
        default=10,
        help='Orden de aplicación de las reglas'
    )

    active = fields.Boolean(
        string='Activo',
        default=True
    )

    # ==================== CONDICIONES ====================

    tipo_servicio = fields.Selection([
        ('secamiento', 'Secamiento'),
        ('prelimpieza', 'Prelimpieza'),
        ('combinado', 'Secamiento + Prelimpieza'),
        ('todos', 'Todos los servicios'),
    ], string='Aplica a Tipo de Servicio',
       default='todos',
       required=True,
       help='A qué tipo de servicio aplica esta regla')

    condicion = fields.Selection([
        ('siempre', 'Siempre'),
        ('peso_minimo', 'Si el peso supera un mínimo'),
        ('peso_maximo', 'Si el peso NO supera un máximo'),
    ], string='Condición',
       default='siempre',
       required=True,
       help='Cuándo se debe aplicar esta regla')

    peso_referencia = fields.Float(
        string='Peso de Referencia (Kg)',
        help='Peso para evaluar la condición (si aplica)'
    )

    # ==================== SERVICIO A AGREGAR ====================

    producto_id = fields.Many2one(
        'product.product',
        string='Servicio a Agregar',
        required=True,
        domain=[('type', '=', 'service')],
        help='Producto/servicio que se agregará automáticamente'
    )

    base_calculo = fields.Selection([
        ('peso_entrada', 'Peso de Entrada'),
        ('peso_salida', 'Peso de Salida'),
        ('bultos', 'Cantidad de Bultos'),
        ('fijo', 'Cantidad Fija'),
    ], string='Base de Cálculo',
       default='fijo',
       required=True,
       help='Cómo se calculará la cantidad del servicio')

    cantidad_fija = fields.Float(
        string='Cantidad Fija',
        default=1.0,
        help='Cantidad a agregar si la base de cálculo es "Fija"'
    )

    factor_multiplicador = fields.Float(
        string='Factor Multiplicador',
        default=1.0,
        help='Factor para multiplicar el peso (ej: si es por tonelada, usar 0.001)'
    )

    # ==================== FACTURACIÓN ====================

    incluir_en_factura = fields.Boolean(
        string='Incluir en Factura',
        default=True,
        help='Si está desmarcado, el servicio se registra pero NO se cobra (no aparece en factura)'
    )

    precio_unitario = fields.Float(
        string='Precio Unitario',
        digits='Product Price',
        help='Precio unitario que se usará al agregar el servicio (si está vacío, usa el precio del producto)'
    )

    descripcion = fields.Text(
        string='Descripción',
        help='Descripción de cuándo y cómo se aplica esta regla'
    )

    # ==================== MÉTODOS ====================

    @api.onchange('producto_id')
    def _onchange_producto_id(self):
        """Actualizar precio unitario cuando se selecciona un producto"""
        if self.producto_id:
            self.precio_unitario = self.producto_id.list_price

    def evaluar_condicion(self, orden):
        """
        Evalúa si esta regla aplica a la orden de servicio dada
        Retorna True si la regla debe aplicarse
        """
        self.ensure_one()

        # Verificar tipo de servicio
        if self.tipo_servicio != 'todos' and orden.tipo_servicio != self.tipo_servicio:
            return False

        # Evaluar condición
        if self.condicion == 'siempre':
            return True
        elif self.condicion == 'peso_minimo':
            return orden.peso_entrada >= self.peso_referencia
        elif self.condicion == 'peso_maximo':
            return orden.peso_entrada <= self.peso_referencia

        return False

    def calcular_cantidad(self, orden):
        """
        Calcula la cantidad del servicio según la base de cálculo
        """
        self.ensure_one()

        if self.base_calculo == 'fijo':
            return self.cantidad_fija
        elif self.base_calculo == 'peso_entrada':
            return orden.peso_entrada * self.factor_multiplicador
        elif self.base_calculo == 'peso_salida':
            return orden.peso_salida_real * self.factor_multiplicador
        elif self.base_calculo == 'bultos':
            return orden.total_bultos * self.factor_multiplicador

        return 0.0
