# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class FincaCampana(models.Model):
    """Periodo interno de las cuentas con los operadores (saldos por año).

    No se muestra: se asigna solo por la fecha. La campaña que la gente
    escoge es la Cosecha (cuenta analítica del plan "Cosecha": 2026 secano,
    2026 riego, 2027 secano...), la misma de las facturas.
    """
    _name = 'finca.campana'
    _description = 'Campaña Agrícola'
    _order = 'fecha_inicio desc'

    _name_unique = models.Constraint(
        'UNIQUE(name)',
        'Ya existe una campaña con ese nombre.',
    )

    name = fields.Char(
        string='Campaña',
        required=True,
        help='Ej: 2026-2027',
    )
    fecha_inicio = fields.Date(string='Inicio', required=True)
    fecha_fin = fields.Date(string='Fin', required=True)
    state = fields.Selection([
        ('abierta', 'Abierta'),
        ('cerrada', 'Cerrada'),
    ], string='Estado', default='abierta', required=True)
    # Las campañas son comunes a todas las compañías: los pagos pueden
    # registrarse en la compañía de cada dueño y deben caer en la misma campaña.
    active = fields.Boolean(default=True)
    notes = fields.Text(string='Notas')

    @api.constrains('fecha_inicio', 'fecha_fin')
    def _check_fechas(self):
        for rec in self:
            if rec.fecha_fin < rec.fecha_inicio:
                raise ValidationError('La fecha de fin debe ser posterior a la de inicio.')
            solapada = self.search([
                ('id', '!=', rec.id),
                ('fecha_inicio', '<=', rec.fecha_fin),
                ('fecha_fin', '>=', rec.fecha_inicio),
            ], limit=1)
            if solapada:
                raise ValidationError(
                    'Las fechas se cruzan con la campaña %s. Los pagos se asignan '
                    'a la campaña por su fecha, así que no pueden solaparse.' % solapada.name)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._asignar_pagos()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'fecha_inicio' in vals or 'fecha_fin' in vals:
            self._asignar_pagos()
        return res

    def _asignar_pagos(self):
        """Pagos a operadores ya registrados en las fechas de la campaña que
        todavía no tienen campaña (ej. anticipos hechos antes de crearla)."""
        for rec in self:
            pagos = self.env['account.payment'].sudo().search([
                ('partner_id.es_operador_finca', '=', True),
                ('finca_campana_id', '=', False),
                ('date', '>=', rec.fecha_inicio),
                ('date', '<=', rec.fecha_fin),
            ])
            pagos._compute_finca_labores()

    @api.model
    def _get_campana(self, fecha=None):
        """Campaña abierta que contiene la fecha; si ninguna la contiene,
        la campaña abierta más reciente."""
        fecha = fecha or fields.Date.context_today(self)
        domain = [('state', '=', 'abierta')]
        return (
            self.search(domain + [('fecha_inicio', '<=', fecha), ('fecha_fin', '>=', fecha)], limit=1)
            or self.search(domain, limit=1)
        )

    # --- Cosecha (plan analítico) ------------------------------------------

    @api.model
    def _plan_cosecha(self):
        plan = self.env.ref('paramo_agro_costing.plan_cosecha', raise_if_not_found=False)
        if not plan:
            plan = self.env['account.analytic.plan'].sudo().search(
                [('name', '=ilike', 'cosecha')], limit=1)
        return plan

    @api.model
    def _dominio_cosecha(self):
        plan = self._plan_cosecha()
        return [('plan_id', '=', plan.id)] if plan else [('id', '=', 0)]

    @api.model
    def _cosecha_sugerida(self, model, domain):
        """Cosecha del último registro de `model` que cumple `domain` y la
        tiene (p. ej. el último jornal de la misma finca)."""
        if not domain:
            return self.env['account.analytic.account']
        anterior = self.env[model].search(
            domain + [('cosecha_id', '!=', False)], order='id desc', limit=1)
        return anterior.cosecha_id

    def action_cerrar(self):
        self.write({'state': 'cerrada'})

    def action_reabrir(self):
        self.write({'state': 'abierta'})
