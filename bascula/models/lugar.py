# -*- coding: utf-8 -*-

from odoo import api, models, fields


class SecadoraLugar(models.Model):
    _name = 'secadora.lugar'
    _description = 'Lugares (Fincas, Bodegas, etc.)'
    _order = 'name'

    name = fields.Char(
        string='Nombre',
        required=True,
        index=True,
        help='Nombre del lugar (Ej: Finca La Esperanza, Bodega Central)'
    )
    tipo = fields.Selection([
        ('finca', 'Finca'),
        ('bodega', 'Bodega'),
        ('planta', 'Planta'),
        ('otro', 'Otro'),
    ], string='Tipo de Lugar', default='finca')
    codigo = fields.Char(string='Código')
    direccion = fields.Text(string='Dirección')
    municipio = fields.Char(string='Municipio')
    departamento = fields.Char(string='Departamento')
    contacto = fields.Char(string='Contacto')
    telefono = fields.Char(string='Teléfono')
    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        help='Empresa propietaria del lugar (informativo, dejar vacío si es compartido)',
    )
    active = fields.Boolean(
        string='Activo',
        default=True
    )
    notes = fields.Text(string='Notas')
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Cuenta analítica',
        readonly=True,
        ondelete='set null',
        copy=False,
    )

    def _get_analytic_plan_punto_operativo(self):
        return self.env.ref('bascula.analytic_plan_punto_operativo', raise_if_not_found=False)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        plan = self._get_analytic_plan_punto_operativo()
        if plan:
            for rec in records:
                if not rec.analytic_account_id:
                    account = self.env['account.analytic.account'].create({
                        'name': rec.name,
                        'plan_id': plan.id,
                    })
                    rec.analytic_account_id = account
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'name' in vals:
            for rec in self:
                if rec.analytic_account_id:
                    rec.analytic_account_id.name = rec.name
        return res

    def _assign_analytic_accounts(self):
        """Asigna cuentas analíticas a puntos operativos existentes que no tengan."""
        plan = self._get_analytic_plan_punto_operativo()
        if not plan:
            return
        lugares_sin_cuenta = self.search([('analytic_account_id', '=', False)])
        for lugar in lugares_sin_cuenta:
            account = self.env['account.analytic.account'].create({
                'name': lugar.name,
                'plan_id': plan.id,
            })
            lugar.analytic_account_id = account
