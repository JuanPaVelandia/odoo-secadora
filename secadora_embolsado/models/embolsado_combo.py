# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class EmbolsadoCombo(models.Model):
    _name = 'secadora.embolsado.combo'
    _description = 'Combo Tractor+Tolvo'
    _order = 'name, id'

    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    name = fields.Char(
        string='Nombre',
        help='Nombre corto del combo (ej: "Combo 1"). Si se deja vacío se '
             'muestran los nombres de los equipos.',
    )
    tractor_equipo_id = fields.Many2one(
        'maintenance.equipment',
        string='Tractor (Equipo)',
        required=True,
        ondelete='restrict',
        index=True,
    )
    tolvo_equipo_id = fields.Many2one(
        'maintenance.equipment',
        string='Tolvo (Equipo)',
        required=True,
        ondelete='restrict',
        index=True,
    )
    tara_ids = fields.One2many(
        'secadora.embolsado.tara',
        'combo_id',
        string='Historial de Taras',
    )
    tara_vigente_kg = fields.Float(
        string='Tara Vigente (Kg)',
        digits=(12, 2),
        compute='_compute_tara_vigente',
    )
    tara_vigente_fecha = fields.Datetime(
        string='Fecha Tara Vigente',
        compute='_compute_tara_vigente',
    )
    notas = fields.Text(string='Notas')
    active = fields.Boolean(string='Activo', default=True)

    @api.constrains('tractor_equipo_id', 'tolvo_equipo_id')
    def _check_equipos_distintos(self):
        for rec in self:
            if rec.tractor_equipo_id == rec.tolvo_equipo_id:
                raise ValidationError('El tractor y el tolvo deben ser equipos distintos.')

    @api.depends('name', 'tractor_equipo_id', 'tolvo_equipo_id')
    def _compute_display_name(self):
        for rec in self:
            equipos = '%s + %s' % (
                rec.tractor_equipo_id.name or '?',
                rec.tolvo_equipo_id.name or '?',
            )
            rec.display_name = '%s (%s)' % (rec.name, equipos) if rec.name else equipos

    def _compute_tara_vigente(self):
        Tara = self.env['secadora.embolsado.tara']
        for rec in self:
            tara = Tara._tara_vigente(rec.id)
            rec.tara_vigente_kg = tara.peso_tara_kg if tara else 0.0
            rec.tara_vigente_fecha = tara.fecha if tara else False

    def action_registrar_tara(self):
        self.ensure_one()
        return {
            'name': 'Registrar Tara',
            'type': 'ir.actions.act_window',
            'res_model': 'secadora.embolsado.tara',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {'default_combo_id': self.id},
        }
