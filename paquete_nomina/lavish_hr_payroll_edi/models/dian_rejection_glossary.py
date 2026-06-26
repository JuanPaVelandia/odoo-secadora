# -*- coding: utf-8 -*-
from odoo import fields, models


class DianRejectionGlossary(models.Model):
    _name = 'dian.rejection.glossary'
    _description = 'Glosario Reglas de Rechazo DIAN'
    _order = 'code'

    code = fields.Char(string='Código', required=True, index=True)
    rule = fields.Char(string='Regla', required=True)
    message = fields.Text(string='Mensaje de Error')
    solution = fields.Text(string='Solución Sugerida')
    category = fields.Selection([
        ('datos_empresa', 'Datos Empresa'),
        ('datos_trabajador', 'Datos Trabajador'),
        ('datos_contrato', 'Datos Contrato'),
        ('cune', 'CUNE'),
        ('secuencial', 'Secuencial'),
        ('devengos', 'Devengos'),
        ('deducciones', 'Deducciones'),
        ('vacaciones', 'Vacaciones'),
        ('basico', 'Básico'),
        ('nota_ajuste', 'Nota de Ajuste'),
        ('habilitacion', 'Habilitación'),
        ('autenticacion', 'Autenticación'),
        ('conectividad', 'Conectividad'),
        ('totales', 'Totales'),
    ], string='Categoría')
    active = fields.Boolean(string='Activo', default=True)
