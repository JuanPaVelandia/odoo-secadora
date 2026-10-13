# -*- coding: utf-8 -*-
"""Compras de ACPM a partir de las líneas de factura de proveedor.

Es control operativo, no contabilidad: la línea de la factura se marca como
ACPM y se le ponen galones y destino. No se toca ni la cuenta ni el producto
de la línea (cambiarlos en una factura publicada movería cuentas e impuestos).

Hay dos tipos de ACPM:

- **Finca**: costo del cultivo. Lleva finca (punto operativo) y campaña. Al
  asignar la finca se corrige la distribución analítica del plan Punto
  operativo, conservando lo demás (Cultivo de arroz, cosecha...).
- **Logística**: va a un vehículo (camioneta). No lleva finca ni campaña y,
  si la línea traía una finca en la analítica, se le quita.
"""

import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

ACPM_TIPOS = [
    ('finca', 'Finca'),
    ('logistica', 'Logística'),
]


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    acpm_es = fields.Boolean(
        string='ACPM',
        copy=False,
        index=True,
        help='Esta línea es una compra de combustible. Se lleva en el '
             'resumen de ACPM.',
    )
    acpm_tipo = fields.Selection(
        ACPM_TIPOS,
        string='Tipo ACPM',
        copy=False,
        index=True,
        help='Finca: costo del cultivo, con finca y campaña. '
             'Logística: combustible de un vehículo.',
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
    acpm_equipment_id = fields.Many2one(
        'maintenance.equipment',
        string='Vehículo',
        copy=False,
        index='btree_not_null',
        ondelete='restrict',
        domain=[('es_vehiculo', '=', True)],
        help='Vehículo que recibió el combustible (ACPM de logística). Solo '
             'aparecen los equipos marcados como vehículo en Mantenimiento.',
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
        help='Finca: la analítica de la línea ya tiene la finca en el plan '
             'Punto operativo. Logística: la línea no tiene finca en la analítica.',
    )

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------

    @api.depends('acpm_es', 'acpm_tipo', 'move_id.invoice_date', 'date')
    def _compute_acpm_campana_id(self):
        Campana = self.env['finca.campana'].sudo()
        for line in self:
            if not line.acpm_es or line.acpm_tipo != 'finca':
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

    @api.depends('acpm_es', 'acpm_tipo', 'acpm_lugar_id', 'analytic_distribution', 'company_id')
    def _compute_acpm_analitica_ok(self):
        planes = self._acpm_planes_punto_operativo()
        ids_po = self._acpm_ids_punto_operativo(planes)
        for line in self:
            en_linea = line._acpm_ids_en_distribucion()
            if not line.acpm_es:
                line.acpm_analitica_ok = False
            elif line.acpm_tipo == 'logistica':
                line.acpm_analitica_ok = not (en_linea & ids_po)
            else:
                cuenta = line._acpm_cuenta_analitica(planes) if line.acpm_lugar_id else None
                line.acpm_analitica_ok = bool(cuenta) and cuenta.id in en_linea

    # ------------------------------------------------------------------
    # Valores propuestos
    # ------------------------------------------------------------------

    def _acpm_galones_propuestos(self):
        self.ensure_one()
        signo = -1 if self.move_id.move_type == 'in_refund' else 1
        return signo * abs(self.quantity or 0.0)

    @api.onchange('acpm_es')
    def _onchange_acpm_es(self):
        if not self.acpm_es:
            self.acpm_galones = 0.0
            self.acpm_tipo = False
            self.acpm_lugar_id = False
            self.acpm_equipment_id = False
        else:
            if not self.acpm_galones:
                self.acpm_galones = self._acpm_galones_propuestos()
            if not self.acpm_tipo:
                self.acpm_tipo = 'finca'

    @api.onchange('acpm_tipo')
    def _onchange_acpm_tipo(self):
        if self.acpm_tipo == 'finca':
            self.acpm_equipment_id = False
        elif self.acpm_tipo == 'logistica':
            self.acpm_lugar_id = False

    @api.onchange('acpm_equipment_id')
    def _onchange_acpm_equipment_id(self):
        if self.acpm_equipment_id:
            self.acpm_tipo = 'logistica'
            self.acpm_lugar_id = False

    @api.onchange('acpm_lugar_id')
    def _onchange_acpm_lugar_id(self):
        if self.acpm_lugar_id:
            self.acpm_tipo = 'finca'
            self.acpm_equipment_id = False

    # ------------------------------------------------------------------
    # Escritura
    # ------------------------------------------------------------------

    @api.model
    def _acpm_ajustar_vals(self, vals):
        """Mantiene coherentes los campos de ACPM en una escritura."""
        if vals.get('acpm_es') is False:
            vals = dict(vals, acpm_tipo=False, acpm_galones=0.0,
                        acpm_lugar_id=False, acpm_equipment_id=False)
            return vals
        # Escribir un vehículo o una finca define el tipo por sí solo.
        if not vals.get('acpm_tipo'):
            if vals.get('acpm_equipment_id'):
                vals = dict(vals, acpm_tipo='logistica')
            elif vals.get('acpm_lugar_id'):
                vals = dict(vals, acpm_tipo='finca')
        if vals.get('acpm_tipo') == 'finca':
            vals = dict(vals, acpm_equipment_id=False)
        elif vals.get('acpm_tipo') == 'logistica':
            vals = dict(vals, acpm_lugar_id=False)
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._acpm_ajustar_vals(v) for v in vals_list]
        lines = super().create(vals_list)
        lines._acpm_completar()
        lines._acpm_sincronizar_analitica()
        return lines

    def write(self, vals):
        vals = self._acpm_ajustar_vals(vals)
        # Borrar la finca a mano: se quita también de la analítica.
        quitar_finca = ('acpm_lugar_id' in vals and not vals['acpm_lugar_id']
                        and vals.get('acpm_es') is not False and not vals.get('acpm_tipo'))
        res = super().write(vals)
        if vals.get('acpm_es'):
            self._acpm_completar()
        if vals.get('acpm_es') or 'acpm_tipo' in vals or 'acpm_lugar_id' in vals:
            self._acpm_sincronizar_analitica(quitar_finca=quitar_finca)
        return res

    def _acpm_completar(self):
        """Galones, tipo y finca por defecto en las líneas recién marcadas. La
        finca se propone de la analítica si contabilidad ya la había puesto."""
        planes = self._acpm_planes_punto_operativo()
        ids_po = self._acpm_ids_punto_operativo(planes)
        for line in self.filtered('acpm_es'):
            vals = {}
            if not line.acpm_galones:
                vals['acpm_galones'] = line._acpm_galones_propuestos()
            if not line.acpm_tipo:
                vals['acpm_tipo'] = 'finca'
            if (vals.get('acpm_tipo', line.acpm_tipo) == 'finca'
                    and not line.acpm_lugar_id and not line.acpm_equipment_id):
                lugar = line._acpm_lugar_desde_analitica(ids_po)
                if lugar:
                    vals['acpm_lugar_id'] = lugar.id
            if vals:
                super(AccountMoveLine, line).write(vals)

    def _acpm_lugar_desde_analitica(self, ids_po):
        """Lugar cuya cuenta de Punto operativo ya está en la analítica de la
        línea: por el enlace directo del lugar o, si no, por el nombre."""
        self.ensure_one()
        en_linea = self._acpm_ids_en_distribucion() & ids_po
        if not en_linea:
            return None
        Lugar = self.env['secadora.lugar'].sudo()
        lugar = Lugar.search([('analytic_account_id', 'in', list(en_linea))], order='id', limit=1)
        if lugar:
            return lugar
        cuentas = self.env['account.analytic.account'].sudo().browse(list(en_linea))
        for cuenta in cuentas:
            lugar = Lugar.search([('name', '=ilike', (cuenta.name or '').strip()),
                                  ('tipo', 'in', ('finca', 'planta'))], order='id', limit=1)
            if lugar:
                return lugar
        return None

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

    @api.model
    def _acpm_ids_punto_operativo(self, planes):
        if not planes:
            return set()
        return set(self.env['account.analytic.account'].sudo().with_context(active_test=False)
                   .search([('plan_id', 'in', planes.ids)]).ids)

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

    def _acpm_distribucion_sin_finca(self, ids_po):
        """La distribución de la línea sin las cuentas del plan Punto operativo."""
        self.ensure_one()
        nueva = {}
        for clave, pct in (self.analytic_distribution or {}).items():
            ids = [int(i) for i in str(clave).split(',') if i.strip().isdigit()]
            resto = [i for i in ids if i not in ids_po]
            if resto:
                k = ','.join(map(str, resto))
                nueva[k] = nueva.get(k, 0.0) + pct
        return nueva

    def _acpm_sincronizar_analitica(self, quitar_finca=False):
        """Finca: pone la finca en la analítica de la línea y conserva lo
        demás (Cultivo de arroz, cosecha, etc.), reemplazando cualquier otra
        cuenta del plan Punto operativo. Logística: quita la finca si la había.
        Con `quitar_finca`, las líneas de finca sin finca también la pierden
        en la analítica (el usuario la borró a propósito)."""
        planes = self._acpm_planes_punto_operativo()
        if not planes:
            return
        ids_po = self._acpm_ids_punto_operativo(planes)
        for line in self.filtered('acpm_es'):
            actual = line.analytic_distribution or {}
            if line.acpm_tipo == 'logistica' or (quitar_finca and not line.acpm_lugar_id):
                nueva = line._acpm_distribucion_sin_finca(ids_po)
            elif line.acpm_lugar_id:
                cuenta = line._acpm_cuenta_analitica(planes)
                if not cuenta:
                    _logger.info('ACPM: la finca %s no tiene cuenta analítica de Punto operativo '
                                 'en %s; la analítica de %s no se toca.',
                                 line.acpm_lugar_id.name, line.company_id.name, line.move_id.name)
                    continue
                nueva = line._acpm_distribucion_sin_finca(ids_po)
                nueva[str(cuenta.id)] = 100.0
            else:
                continue
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
        """Marca como ACPM de finca las líneas seleccionadas (botón de la lista)."""
        self._acpm_marcar('finca')
        return True

    def action_acpm_marcar_logistica(self):
        self._acpm_marcar('logistica')
        return True

    def _acpm_marcar(self, tipo):
        lineas = self.filtered(lambda l: l.display_type == 'product'
                               and l.move_id.move_type in ('in_invoice', 'in_refund'))
        lineas.write({'acpm_es': True, 'acpm_tipo': tipo})

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
