# -*- coding: utf-8 -*-

import logging
from psycopg2 import IntegrityError
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class SecadoraPesajeTransporte(models.Model):
    _inherit = 'secadora.pesaje'

    flete_ids = fields.One2many(
        'secadora.flete',
        'pesaje_id',
        string='Fletes',
    )

    flete_count = fields.Integer(
        string='Nº Fletes',
        compute='_compute_flete_count',
    )

    generar_flete = fields.Boolean(
        string='Generar Flete al Completar',
        help='Si está marcado, se creará un flete automáticamente al completar el pesaje.',
    )

    def _compute_flete_count(self):
        for rec in self:
            rec.flete_count = len(rec.flete_ids)

    @api.onchange('tercero_id')
    def _onchange_tercero_id_flete(self):
        if self.tercero_id and self.tercero_id.generar_flete_automatico:
            self.generar_flete = True
        else:
            self.generar_flete = False

    def action_segunda_pesada(self):
        res = super().action_segunda_pesada()
        for record in self:
            if record.state != 'completado':
                continue
            if record.generar_flete or (record.tercero_id and record.tercero_id.generar_flete_automatico):
                try:
                    record._crear_flete_automatico()
                except Exception as e:
                    _logger.error(
                        'Error creando flete automático para pesaje %s: %s',
                        record.name, str(e)
                    )
        return res

    def write(self, vals):
        res = super().write(vals)
        # Sincronizar campos del pesaje a fletes vinculados
        # Mapeo: campo_pesaje -> campo_flete (None = mismo nombre)
        campos_sync = {
            'origen_id': 'origen_id',
            'destino_id': 'destino_id',
            'vehiculo_id': 'vehiculo_id',
            'conductor_id': 'conductor_id',
            'transportadora_id': 'transportadora_id',
            'producto_id': 'producto_id',
            'variedad_id': 'variedad_id',
            'peso_neto': 'peso_kg',
            'bultos': 'bultos',
            'humedad': 'humedad',
            'impurezas': 'impurezas',
            'tercero_id': 'tercero_id',
        }
        campos_changed = set(vals) & set(campos_sync)
        if campos_changed:
            for record in self:
                for flete in record.flete_ids.filtered(lambda f: f.state in ('borrador', 'confirmado')):
                    sync_vals = {}
                    for campo_pesaje in campos_changed:
                        campo_flete = campos_sync[campo_pesaje]
                        value = record[campo_pesaje]
                        if hasattr(value, 'id'):
                            sync_vals[campo_flete] = value.id or False
                        else:
                            sync_vals[campo_flete] = value
                    # Derivar empresa_origen/destino de los lugares
                    if 'origen_id' in campos_changed:
                        if record.origen_id and record.origen_id.company_id:
                            sync_vals['empresa_origen_id'] = record.origen_id.company_id.id
                    if 'destino_id' in campos_changed:
                        if record.destino_id and record.destino_id.company_id:
                            sync_vals['empresa_destino_id'] = record.destino_id.company_id.id
                    # Sincronizar modalidad de pago si cambia el tercero
                    if 'tercero_id' in campos_changed and record.tercero_id:
                        sync_vals['pago_flete'] = record.tercero_id.flete_pago or 'agricultor'
                    if sync_vals:
                        flete.write(sync_vals)
        return res

    def _crear_flete_automatico(self):
        """Crea un flete automáticamente con datos del pesaje. Evita duplicados."""
        self.ensure_one()
        if self.flete_ids:
            return
        if not self.vehiculo_id:
            return
        vals = {
            'pesaje_id': self.id,
            'vehiculo_id': self.vehiculo_id.id,
            'conductor_id': self.conductor_id.id if self.conductor_id else False,
            'transportadora_id': self.transportadora_id.id if self.transportadora_id else False,
            'producto_id': self.producto_id.id if self.producto_id else False,
            'variedad_id': self.variedad_id.id if self.variedad_id else False,
            'peso_kg': self.peso_neto or 0.0,
            'bultos': self.bultos or 0,
            'humedad': self.humedad,
            'impurezas': self.impurezas,
            'origen_id': self.origen_id.id if self.origen_id else False,
            'destino_id': self.destino_id.id if self.destino_id else False,
            'tercero_id': self.tercero_id.id if self.tercero_id else False,
            'pago_flete': (self.tercero_id.flete_pago or 'agricultor') if self.tercero_id else 'agricultor',
        }
        if self.empresa_arroz_id:
            vals['company_id'] = self.empresa_arroz_id.id
        if self.origen_id and self.origen_id.company_id:
            vals['empresa_origen_id'] = self.origen_id.company_id.id
        if self.destino_id and self.destino_id.company_id:
            vals['empresa_destino_id'] = self.destino_id.company_id.id
        try:
            with self.env.cr.savepoint():
                self.env['secadora.flete'].create(vals)
        except IntegrityError:
            _logger.info('Flete duplicado evitado para pesaje %s (race condition)', self.name)

    def action_crear_flete(self):
        """Crear un flete pre-llenado con datos de este pesaje"""
        self.ensure_one()
        from odoo.exceptions import UserError
        if self.flete_ids:
            raise UserError('Este pesaje ya tiene un flete asociado.')
        if not self.vehiculo_id:
            raise UserError('Debe asignar un vehículo al pesaje antes de crear el flete.')

        vals = {
            'pesaje_id': self.id,
            'vehiculo_id': self.vehiculo_id.id,
            'conductor_id': self.conductor_id.id if self.conductor_id else False,
            'transportadora_id': self.transportadora_id.id if self.transportadora_id else False,
            'producto_id': self.producto_id.id if self.producto_id else False,
            'variedad_id': self.variedad_id.id if self.variedad_id else False,
            'peso_kg': self.peso_neto or 0.0,
            'bultos': self.bultos or 0,
            'humedad': self.humedad,
            'impurezas': self.impurezas,
            'origen_id': self.origen_id.id if self.origen_id else False,
            'destino_id': self.destino_id.id if self.destino_id else False,
            'tercero_id': self.tercero_id.id if self.tercero_id else False,
            'pago_flete': (self.tercero_id.flete_pago or 'agricultor') if self.tercero_id else 'agricultor',
        }

        # Auto-detectar empresa que paga desde el tercero
        if self.empresa_arroz_id:
            vals['company_id'] = self.empresa_arroz_id.id

        # Auto-detectar empresa origen/destino desde los lugares
        if self.origen_id and self.origen_id.company_id:
            vals['empresa_origen_id'] = self.origen_id.company_id.id
        if self.destino_id and self.destino_id.company_id:
            vals['empresa_destino_id'] = self.destino_id.company_id.id

        flete = self.env['secadora.flete'].create(vals)

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'secadora.flete',
            'res_id': flete.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_ver_fletes(self):
        self.ensure_one()
        action = {
            'type': 'ir.actions.act_window',
            'name': f'Fletes - {self.name}',
            'res_model': 'secadora.flete',
            'view_mode': 'list,form',
            'domain': [('pesaje_id', '=', self.id)],
            'context': {'default_pesaje_id': self.id},
        }
        if self.flete_count == 1:
            action['view_mode'] = 'form'
            action['res_id'] = self.flete_ids[0].id
        return action
