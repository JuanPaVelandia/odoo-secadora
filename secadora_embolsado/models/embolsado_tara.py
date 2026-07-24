# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


class EmbolsadoTara(models.Model):
    _name = 'secadora.embolsado.tara'
    _description = 'Tara de Pareja Tractor+Tolvo'
    _inherit = ['mail.thread']
    _order = 'fecha desc, id desc'
    _peso_tara_positivo = models.Constraint(
        'CHECK(peso_tara_kg > 0)',
        'El peso de la tara debe ser mayor a cero.',
    )

    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    tractor_id = fields.Many2one(
        'secadora.vehiculo',
        string='Tractor',
        required=True,
        index=True,
        tracking=True,
    )
    tolvo_id = fields.Many2one(
        'secadora.vehiculo',
        string='Tolvo',
        required=True,
        index=True,
        tracking=True,
    )
    peso_tara_kg = fields.Float(
        string='Peso Vacío (Kg)',
        digits=(12, 2),
        required=True,
        tracking=True,
        help='Peso de la pareja tractor+tolvo vacía, pesada en la báscula.',
    )
    fecha = fields.Datetime(
        string='Fecha de Tara',
        default=fields.Datetime.now,
        required=True,
        index=True,
    )
    usuario_id = fields.Many2one(
        'res.users',
        string='Usuario',
        default=lambda self: self.env.uid,
        required=True,
    )
    # Campo ancla del widget de peso en vivo (el valor real capturado va en peso_tara_kg)
    peso_vivo = fields.Float(string='Peso en Vivo')
    capturada_de_bascula = fields.Boolean(
        string='Capturada de Báscula',
        readonly=True,
        help='Marca si el peso se tomó de la lectura en vivo de la báscula.',
    )
    esta_vencida = fields.Boolean(
        string='Tara Vencida',
        compute='_compute_esta_vencida',
        help='La tara supera los días de vigencia configurados '
             '(parámetro secadora_embolsado.tara_max_dias).',
    )
    notas = fields.Text(string='Notas')
    active = fields.Boolean(string='Activo', default=True)

    @api.constrains('tractor_id', 'tolvo_id')
    def _check_tractor_distinto_tolvo(self):
        for rec in self:
            if rec.tractor_id == rec.tolvo_id:
                raise ValidationError('El tractor y el tolvo deben ser vehículos distintos.')

    @api.depends('tractor_id', 'tolvo_id', 'peso_tara_kg', 'fecha')
    def _compute_display_name(self):
        for rec in self:
            fecha_local = fields.Datetime.context_timestamp(rec, rec.fecha) if rec.fecha else False
            rec.display_name = '%s + %s — %.2f kg (%s)' % (
                rec.tractor_id.placa or '?',
                rec.tolvo_id.placa or '?',
                rec.peso_tara_kg,
                fecha_local.strftime('%d/%m/%Y') if fecha_local else 'sin fecha',
            )

    def _compute_esta_vencida(self):
        max_dias = int(self.env['ir.config_parameter'].sudo().get_param(
            'secadora_embolsado.tara_max_dias', '7'))
        ahora = fields.Datetime.now()
        for rec in self:
            rec.esta_vencida = bool(
                rec.fecha and (ahora - rec.fecha).days >= max_dias
            )

    @api.model
    def _tara_vigente(self, tractor_id, tolvo_id):
        """Tara más reciente registrada para la pareja tractor+tolvo."""
        if not tractor_id or not tolvo_id:
            return self.browse()
        return self.search([
            ('tractor_id', '=', tractor_id),
            ('tolvo_id', '=', tolvo_id),
            ('company_id', 'in', [self.env.company.id, False]),
        ], order='fecha desc, id desc', limit=1)

    def action_capturar_peso_bascula(self):
        """Tomar el peso vacío de la lectura en vivo de la báscula."""
        self.ensure_one()
        peso = self.env['secadora.pesaje']._peso_bascula_reciente()
        if peso <= 0:
            raise UserError(
                'No hay peso reciente de la báscula (últimos 15 segundos). '
                'Verifica que la báscula esté conectada y enviando datos.'
            )
        self.write({
            'peso_tara_kg': peso,
            'fecha': fields.Datetime.now(),
            'capturada_de_bascula': True,
        })
        return True
