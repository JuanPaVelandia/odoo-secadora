# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class SecadoraPrecioCompra(models.Model):
    _name = 'secadora.precio.compra'
    _description = 'Precio de Compra de Arroz'
    _order = 'fecha_desde desc, variedad_id'

    _sql_constraints = [
        ('precio_positivo', 'CHECK(precio > 0)',
         'El precio debe ser mayor a cero.'),
    ]

    variedad_id = fields.Many2one(
        'secadora.variedad.arroz',
        string='Variedad',
        required=True,
        index=True,
    )
    precio = fields.Float(
        string='Precio ($/kg)',
        required=True,
        digits=(12, 2),
    )
    fecha_desde = fields.Date(
        string='Fecha Desde',
        required=True,
        index=True,
    )
    fecha_hasta = fields.Date(
        string='Fecha Hasta',
        help='Vacío = vigente indefinidamente',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        help='Vacío = aplica a todas las empresas',
    )
    active = fields.Boolean(
        string='Activo',
        default=True,
    )

    @api.constrains('fecha_desde', 'fecha_hasta')
    def _check_fechas(self):
        for rec in self:
            if rec.fecha_hasta and rec.fecha_hasta < rec.fecha_desde:
                raise ValidationError('La fecha hasta debe ser mayor o igual a la fecha desde.')

    @api.constrains('variedad_id', 'company_id', 'fecha_desde', 'fecha_hasta', 'active')
    def _check_solapamiento(self):
        for rec in self:
            if not rec.active:
                continue
            domain = [
                ('id', '!=', rec.id),
                ('variedad_id', '=', rec.variedad_id.id),
                ('company_id', '=', rec.company_id.id),
                ('active', '=', True),
            ]
            # Buscar registros que se solapen en fechas
            if rec.fecha_hasta:
                domain.append(('fecha_desde', '<=', rec.fecha_hasta))
            # El otro registro debe empezar antes de que termine este
            # y terminar después de que empiece este
            overlapping = self.search(domain)
            for other in overlapping:
                if other.fecha_hasta and other.fecha_hasta < rec.fecha_desde:
                    continue
                raise ValidationError(
                    'Ya existe un precio vigente para %s en el rango de fechas indicado.'
                    % rec.variedad_id.name
                )

    @api.model
    def _obtener_precio(self, variedad_id, fecha, company_id=False):
        """Busca el precio vigente para una variedad en una fecha.

        Prioridad: empresa específica > global (company_id=False).
        Retorna 0.0 si no hay precio configurado.
        """
        domain = [
            ('variedad_id', '=', variedad_id),
            ('fecha_desde', '<=', fecha),
            '|',
            ('fecha_hasta', '=', False),
            ('fecha_hasta', '>=', fecha),
        ]
        # Primero buscar con empresa específica
        if company_id:
            precio = self.search(
                domain + [('company_id', '=', company_id)],
                limit=1,
                order='fecha_desde desc',
            )
            if precio:
                return precio.precio
        # Fallback: buscar precio global
        precio = self.search(
            domain + [('company_id', '=', False)],
            limit=1,
            order='fecha_desde desc',
        )
        return precio.precio if precio else 0.0
