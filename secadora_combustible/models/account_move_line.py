# -*- coding: utf-8 -*-
"""Compras de ACPM a partir de las líneas de factura de proveedor.

Es control operativo, no contabilidad: la línea de la factura se marca como
ACPM y se le ponen galones, finca y campaña. No se toca ni la cuenta ni el
producto de la línea (cambiarlos en una factura publicada movería cuentas e
impuestos). Lo único contable que se corrige es la distribución analítica del
plan Punto operativo, para que el costo del cultivo por finca quede bien.
"""

import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Palabras con las que suele venir el combustible en las facturas.
ACPM_PALABRAS = ('acpm', 'diesel', 'diésel', 'combustible', 'gasolina')


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    acpm_es = fields.Boolean(
        string='ACPM',
        copy=False,
        index=True,
        help='Esta línea es una compra de combustible. Se lleva en el '
             'resumen de ACPM por finca y campaña.',
    )
    acpm_galones = fields.Float(
        string='Galones',
        digits=(12, 2),
        copy=False,
        help='Galones comprados. Se propone la cantidad de la línea; cámbiela '
             'si la factura viene en otra unidad. En notas crédito va en negativo.',
    )
    acpm_lugar_id = fields.Many2one(
        'secadora.lugar',
        string='Finca',
        copy=False,
        index='btree_not_null',
        ondelete='restrict',
        domain=[('tipo', 'in', ('finca', 'planta'))],
        help='Finca (o planta) donde se consumió el combustible. Al asignarla '
             'se corrige la analítica de Punto operativo de la línea.',
    )
    acpm_campana_id = fields.Many2one(
        'finca.campana',
        string='Campaña',
        compute='_compute_acpm_campana_id',
        store=True,
        readonly=False,
        copy=False,
        index='btree_not_null',
        ondelete='restrict',
        help='Se propone la campaña de Labores de Finca que contiene la fecha '
             'de la factura. Se puede cambiar.',
    )
    acpm_valor = fields.Monetary(
        string='Valor ACPM',
        compute='_compute_acpm_valor',
        store=True,
        currency_field='currency_id',
        help='Subtotal de la línea sin impuestos; negativo en notas crédito.',
    )
    acpm_analitica_ok = fields.Boolean(
        string='Analítica',
        compute='_compute_acpm_analitica_ok',
        help='La distribución analítica de la línea ya tiene la finca en el '
             'plan Punto operativo.',
    )

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------

    @api.depends('acpm_es', 'move_id.invoice_date', 'date')
    def _compute_acpm_campana_id(self):
        Campana = self.env['finca.campana'].sudo()
        for line in self:
            if not line.acpm_es:
                line.acpm_campana_id = False
                continue
            # Si ya tiene campaña (puesta a mano o antes) se respeta.
            line.acpm_campana_id = line.acpm_campana_id
            if line.acpm_campana_id:
                continue
            fecha = line.move_id.invoice_date or line.date
            if fecha:
                line.acpm_campana_id = Campana.search([
                    ('fecha_inicio', '<=', fecha),
                    ('fecha_fin', '>=', fecha),
                ], limit=1)

    @api.depends('acpm_es', 'price_subtotal', 'move_id.move_type')
    def _compute_acpm_valor(self):
        for line in self:
            if not line.acpm_es:
                line.acpm_valor = 0.0
            else:
                signo = -1 if line.move_id.move_type == 'in_refund' else 1
                line.acpm_valor = signo * line.price_subtotal

    @api.depends('acpm_es', 'acpm_lugar_id', 'analytic_distribution', 'company_id')
    def _compute_acpm_analitica_ok(self):
        planes = self._acpm_planes_punto_operativo()
        for line in self:
            cuenta = line._acpm_cuenta_analitica(planes) if line.acpm_es and line.acpm_lugar_id else None
            line.acpm_analitica_ok = bool(cuenta) and cuenta.id in line._acpm_ids_en_distribucion()

    # ------------------------------------------------------------------
    # Galones propuestos
    # ------------------------------------------------------------------

    def _acpm_galones_propuestos(self):
        self.ensure_one()
        signo = -1 if self.move_id.move_type == 'in_refund' else 1
        return signo * abs(self.quantity or 0.0)

    @api.onchange('acpm_es')
    def _onchange_acpm_es(self):
        if not self.acpm_es:
            self.acpm_galones = 0.0
            self.acpm_lugar_id = False
        elif not self.acpm_galones:
            self.acpm_galones = self._acpm_galones_propuestos()

    # ------------------------------------------------------------------
    # Escritura
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('acpm_es') is False:
                vals.update(acpm_galones=0.0, acpm_lugar_id=False)
        lines = super().create(vals_list)
        lines._acpm_completar_galones()
        lines._acpm_sincronizar_analitica()
        return lines

    def write(self, vals):
        if vals.get('acpm_es') is False:
            vals = dict(vals, acpm_galones=0.0, acpm_lugar_id=False)
        res = super().write(vals)
        if vals.get('acpm_es') and 'acpm_galones' not in vals:
            self._acpm_completar_galones()
        if vals.get('acpm_es') or 'acpm_lugar_id' in vals:
            self._acpm_sincronizar_analitica()
        return res

    def _acpm_completar_galones(self):
        for line in self.filtered(lambda l: l.acpm_es and not l.acpm_galones):
            super(AccountMoveLine, line).write({'acpm_galones': line._acpm_galones_propuestos()})

    # ------------------------------------------------------------------
    # Analítica (plan Punto operativo)
    # ------------------------------------------------------------------

    @api.model
    def _acpm_planes_punto_operativo(self):
        """Planes analíticos que representan la finca. Hay dos en la base:
        el de Báscula (al que apuntan los lugares) y el de Páramo."""
        planes = self.env['account.analytic.plan'].sudo()
        for xmlid in ('bascula.analytic_plan_punto_operativo',
                      'paramo_agro_costing.plan_punto_operativo'):
            plan = self.env.ref(xmlid, raise_if_not_found=False)
            if plan:
                planes |= plan.sudo()
        return planes

    def _acpm_cuenta_analitica(self, planes):
        """Cuenta analítica de la finca en el plan Punto operativo, usable en
        la compañía de la línea (las cuentas están duplicadas por compañía).
        None si no hay ninguna que sirva."""
        self.ensure_one()
        lugar = self.acpm_lugar_id.sudo()
        if not lugar or not planes:
            return None
        compania = self.company_id
        cuenta = lugar.analytic_account_id
        if cuenta and cuenta.plan_id in planes and (not cuenta.company_id or cuenta.company_id == compania):
            return cuenta
        # Las cuentas están duplicadas por compañía (y a veces dentro de la
        # misma): se busca por nombre, primero en la compañía de la línea, y
        # se toma la más antigua para que la elección sea estable.
        Analitica = self.env['account.analytic.account'].sudo()
        nombre = (lugar.name or '').strip()
        for dominio_cia in ([('company_id', '=', compania.id)], [('company_id', '=', False)]):
            cuenta = Analitica.search(
                [('plan_id', 'in', planes.ids), ('name', '=ilike', nombre)] + dominio_cia,
                order='id', limit=1)
            if cuenta:
                return cuenta
        return None

    def _acpm_ids_en_distribucion(self):
        """Ids de cuentas analíticas presentes en la distribución de la línea
        (las claves pueden ser "22" o "39,52")."""
        self.ensure_one()
        ids = set()
        for clave in (self.analytic_distribution or {}):
            ids.update(int(i) for i in str(clave).split(',') if i.strip().isdigit())
        return ids

    def _acpm_sincronizar_analitica(self):
        """Pone la finca en la analítica de la línea y conserva lo demás
        (Cultivo de arroz, cosecha, etc.). Reemplaza cualquier otra cuenta del
        plan Punto operativo que tuviera."""
        planes = self._acpm_planes_punto_operativo()
        if not planes:
            return
        ids_po = set(self.env['account.analytic.account'].sudo().with_context(active_test=False)
                     .search([('plan_id', 'in', planes.ids)]).ids)
        for line in self:
            if not line.acpm_es or not line.acpm_lugar_id:
                continue
            cuenta = line._acpm_cuenta_analitica(planes)
            if not cuenta:
                _logger.info('ACPM: la finca %s no tiene cuenta analítica de Punto operativo '
                             'en %s; la analítica de %s no se toca.',
                             line.acpm_lugar_id.name, line.company_id.name, line.move_id.name)
                continue
            actual = line.analytic_distribution or {}
            nueva = {}
            for clave, pct in actual.items():
                ids = [int(i) for i in str(clave).split(',') if i.strip().isdigit()]
                resto = [i for i in ids if i not in ids_po]
                if resto:
                    k = ','.join(map(str, resto))
                    nueva[k] = nueva.get(k, 0.0) + pct
            nueva[str(cuenta.id)] = 100.0
            if nueva == actual:
                continue
            try:
                with self.env.cr.savepoint():
                    line.write({'analytic_distribution': nueva})
            except UserError as e:
                # Típicamente fecha de bloqueo: la línea queda con la
                # analítica vieja y "Analítica" en falso para revisarla.
                _logger.warning('ACPM: no se pudo corregir la analítica de %s: %s',
                                line.move_id.name, e)

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------

    def action_acpm_marcar(self):
        """Marca como ACPM las líneas seleccionadas (botón de la lista)."""
        lineas = self.filtered(lambda l: not l.acpm_es
                               and l.display_type == 'product'
                               and l.move_id.move_type in ('in_invoice', 'in_refund'))
        lineas.write({'acpm_es': True})
        return True

    def action_acpm_desmarcar(self):
        self.filtered('acpm_es').write({'acpm_es': False})
        return True

    def action_acpm_abrir_factura(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'views': [(False, 'form')],
            'target': 'current',
        }
