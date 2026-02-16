# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval


class DescuentoCalidad(models.Model):
    _name = 'secadora.descuento.calidad'
    _description = 'Regla de Descuento por Calidad'
    _order = 'sequence, id'

    name = fields.Char(string='Nombre', required=True)
    sequence = fields.Integer(string='Secuencia', default=10)
    active = fields.Boolean(string='Activo', default=True)

    tipo_operacion_id = fields.Many2one(
        'secadora.tipo.operacion',
        string='Tipo de Operación',
        required=True,
        ondelete='cascade',
    )

    producto_id = fields.Many2one(
        'product.product',
        string='Producto',
        ondelete='set null',
        help='Dejar vacío para aplicar a todos los productos',
    )

    parametro = fields.Selection([
        ('humedad', 'Humedad (%)'),
        ('impurezas', 'Impurezas (%)'),
        ('grano_partido', 'Grano Partido (%)'),
        ('grano_partido_verde', 'Grano Partido Verde (%)'),
        ('grano_rojo', 'Grano Rojo (%)'),
        ('infestacion', 'Infestación'),
        ('cascarilla_pct', 'Cascarilla (%)'),
        ('harina_pct', 'Harina (%)'),
        ('grano_yesado_pct', 'Grano Yesado (%)'),
        ('grano_ambarino_pct', 'Grano Ambarino (%)'),
        ('grano_con_dano_pct', 'Grano con Daño (%)'),
    ], string='Parámetro a Evaluar', required=True)

    umbral = fields.Float(
        string='Umbral Máximo Permitido',
        digits=(5, 2),
        required=True,
        help='Valor máximo permitido antes de aplicar descuento',
    )

    modo_descuento = fields.Selection([
        ('doble_descuento', 'Doble Descuento (factor)'),
        ('porcentaje_por_punto', 'Porcentaje por Punto de Exceso'),
        ('factor_por_punto', 'Factor por Punto de Exceso'),
        ('formula_personalizada', 'Fórmula Personalizada'),
    ], string='Modo de Descuento', required=True, default='doble_descuento')

    factor = fields.Float(
        string='Factor',
        digits=(8, 4),
        required=True,
        default=1.0,
        help='Factor multiplicador del descuento',
    )

    formula = fields.Text(
        string='Fórmula',
        help='Variables disponibles: peso, valor, umbral, exceso, factor. '
             'Debe retornar un dict: {\"tipo\": \"factor\"|\"kg\", \"valor\": float}',
    )

    _sql_constraints = [
        ('unique_tipo_producto_parametro',
         'UNIQUE(tipo_operacion_id, producto_id, parametro)',
         'Ya existe una regla para esta combinación de tipo de operación, producto y parámetro.'),
    ]

    @api.constrains('formula', 'modo_descuento')
    def _check_formula(self):
        for record in self:
            if record.modo_descuento == 'formula_personalizada':
                if not record.formula:
                    raise ValidationError(
                        _('Debe ingresar una fórmula cuando el modo es "Fórmula Personalizada".')
                    )
                # Validar sintaxis con valores de prueba
                try:
                    test_ctx = {
                        'peso': 1000.0,
                        'valor': 15.0,
                        'umbral': 13.0,
                        'exceso': 2.0,
                        'factor': 1.0,
                    }
                    result = safe_eval(record.formula, test_ctx, nocopy=True)
                    if not isinstance(result, dict) or 'tipo' not in result or 'valor' not in result:
                        raise ValidationError(
                            _('La fórmula debe retornar un dict con claves "tipo" y "valor". '
                              'Ejemplo: {"tipo": "factor", "valor": 0.96}')
                        )
                    if result['tipo'] not in ('factor', 'kg'):
                        raise ValidationError(
                            _('El "tipo" retornado debe ser "factor" o "kg".')
                        )
                except ValidationError:
                    raise
                except Exception as e:
                    raise ValidationError(
                        _('Error de sintaxis en la fórmula: %s') % str(e)
                    )

    def calcular_descuento(self, analisis):
        """Calcular el descuento para un análisis dado.

        Args:
            analisis: record de secadora.analisis.lab

        Returns:
            dict: {'tipo': 'factor'|'kg', 'valor': float, 'detalle': str}
        """
        self.ensure_one()
        valor = getattr(analisis, self.parametro, 0.0) or 0.0
        peso_neto = analisis.pesaje_id.peso_neto if analisis.pesaje_id else 0.0
        parametro_label = dict(self._fields['parametro'].selection).get(self.parametro, self.parametro)

        if valor <= self.umbral:
            return {'tipo': 'factor', 'valor': 1.0, 'detalle': ''}

        exceso = valor - self.umbral

        if self.modo_descuento == 'doble_descuento':
            # Factor = (100 - valor_real) / (100 - umbral), capped a 1.0
            denominador = 100.0 - self.umbral
            if denominador <= 0:
                return {'tipo': 'factor', 'valor': 1.0, 'detalle': ''}
            factor_calc = (100.0 - valor) / denominador
            factor_calc = min(factor_calc, 1.0)
            detalle = (
                f"{parametro_label}: (100 - {valor:.2f}) / (100 - {self.umbral:.2f}) "
                f"= {factor_calc:.6f}"
            )
            return {'tipo': 'factor', 'valor': factor_calc, 'detalle': detalle}

        elif self.modo_descuento == 'porcentaje_por_punto':
            # kg = peso × (exceso/100) × factor
            kg = peso_neto * (exceso / 100.0) * self.factor
            detalle = (
                f"{parametro_label}: {peso_neto:.2f} × ({exceso:.2f}/100) × {self.factor:.4f} "
                f"= {kg:.2f} kg"
            )
            return {'tipo': 'kg', 'valor': kg, 'detalle': detalle}

        elif self.modo_descuento == 'factor_por_punto':
            # kg = exceso × factor
            kg = exceso * self.factor
            detalle = (
                f"{parametro_label}: {exceso:.2f} × {self.factor:.4f} = {kg:.2f} kg"
            )
            return {'tipo': 'kg', 'valor': kg, 'detalle': detalle}

        elif self.modo_descuento == 'formula_personalizada':
            ctx = {
                'peso': peso_neto,
                'valor': valor,
                'umbral': self.umbral,
                'exceso': exceso,
                'factor': self.factor,
            }
            result = safe_eval(self.formula, ctx, nocopy=True)
            detalle = f"{parametro_label} (fórmula): {result['tipo']}={result['valor']:.4f}"
            return {
                'tipo': result['tipo'],
                'valor': result['valor'],
                'detalle': detalle,
            }

        return {'tipo': 'factor', 'valor': 1.0, 'detalle': ''}
