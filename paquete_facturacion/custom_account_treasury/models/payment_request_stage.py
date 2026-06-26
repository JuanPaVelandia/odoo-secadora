# -*- coding: utf-8 -*-
from odoo import models, fields

class PaymentRequestStage(models.Model):
    _name = 'payment.request.stage'
    _description = 'Etapas de Solicitud de Pago'
    _order = 'sequence, id'

    name = fields.Char(string='Nombre', required=True)
    sequence = fields.Integer(string='Secuencia', default=10)
    fold = fields.Boolean(string='Plegado en Kanban')

    # Estados específicos
    is_approved = fields.Boolean(string='Es Aprobado', help='Marcar si esta etapa significa aprobación')
    is_paid = fields.Boolean(string='Es Pagado', help='Marcar si esta etapa significa pago realizado')
    is_cancelled = fields.Boolean(string='Es Cancelado', help='Marcar si esta etapa significa cancelación')

    # Configuración de aprobación
    approval_amount = fields.Float(string='Monto Mínimo para Aprobación',
                                   help='Monto mínimo requerido para necesitar aprobación en esta etapa')
    approval_group_id = fields.Many2one('res.groups', string='Grupo de Aprobación',
                                        help='Grupo que puede aprobar en esta etapa')