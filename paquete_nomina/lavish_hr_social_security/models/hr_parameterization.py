from odoo import models, fields, api

#Tipos de Ausencia
class ResCompany(models.Model):
    _inherit = 'res.company'

    exonerated_law_1607 = fields.Boolean('Exonerado Ley 1607')
    entity_arp_id = fields.Many2one('hr.employee.entities',string='Entidad ARP')
    type_contributor = fields.Selection([('01', 'Empleador'),
                                            ('02', 'Independiente'),
                                            ('03', 'Entidades o universidades públicas con régimen especial en Salud'),
                                            ('04', 'Agremiación o Asociación'),
                                            ('05', 'Cooperativa o Precooperativa de trabajo asociado'),
                                            ('06', 'Misión Diplomática'),
                                            ('07', 'Organización administradora de programa de hogares de bienestar'),
                                            ('08', 'Pagador de aportes de los concejales, municipales o distritales'),
                                            ('09', 'Pagador de aportes contrato sindical'),
                                            ('10', 'Pagador programa de reincorporación'),
                                            ('11', 'Pagador aportes parafiscales del Magisterio'),
                                            ], string='Tipo de aportante')

    # Configuración de cálculo de IBC (Ley 1393)
    include_absences_1393 = fields.Boolean(
        string='Incluir Ausencias en Ley 1393',
        default=False,
        help='Si está activo, las ausencias (vacaciones, incapacidades) participan en el cálculo del límite 40% de Ley 1393. '
             'Si está desactivado (recomendado), las ausencias se suman directamente al IBC sin participar en el límite 40%.'
    )

    # Configuración de provisiones
    simple_provisions = fields.Boolean(
        string='Provisiones Simplificadas',
        default=False,
        help='Si está activo, usa el método simple para calcular provisiones (independiente del IBC). '
             'Si está desactivado, usa el método completo considerando el IBC calculado.'
    )
