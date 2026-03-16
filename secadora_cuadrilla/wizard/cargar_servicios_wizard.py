# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError


class CargarServiciosWizard(models.TransientModel):
    _name = 'secadora.cuadrilla.cargar.servicios.wizard'
    _description = 'Cargar Servicios a Liquidación de Cuadrilla'

    liquidacion_id = fields.Many2one(
        'secadora.cuadrilla.liquidacion',
        string='Liquidación',
    )
    fecha_desde = fields.Date(string='Fecha Desde')
    fecha_hasta = fields.Date(string='Fecha Hasta')
    linea_ids = fields.Many2many(
        'secadora.orden.servicio.linea',
        'cuadrilla_wizard_os_linea_rel',
        'wizard_id',
        'linea_id',
        string='Líneas de Servicio',
    )

    @api.onchange('fecha_desde', 'fecha_hasta')
    def _onchange_buscar_servicios(self):
        if not self.fecha_desde or not self.fecha_hasta:
            self.linea_ids = False
            return

        domain = [
            ('orden_id.state', 'in', ('en_proceso', 'listo_liquidar', 'liquidado', 'facturado')),
            ('orden_id.fecha_inicio', '>=', self.fecha_desde),
            ('orden_id.fecha_inicio', '<=', self.fecha_hasta),
            ('cuadrilla_liquidacion_linea_id', '=', False),
        ]
        self.linea_ids = self.env['secadora.orden.servicio.linea'].search(domain)

    def action_cargar(self):
        self.ensure_one()
        if not self.linea_ids:
            raise UserError('No hay líneas de servicio para cargar.')

        liquidacion = self.liquidacion_id
        Tarifa = self.env['secadora.cuadrilla.tarifa']
        Linea = self.env['secadora.cuadrilla.liquidacion.linea']

        sin_tarifa = []
        lineas_existentes = liquidacion.linea_ids.mapped('orden_servicio_linea_id').ids

        for sl in self.linea_ids:
            if sl.id in lineas_existentes:
                continue

            # Buscar tarifa: primero por empresa, luego global
            tarifa = Tarifa.search([
                ('producto_id', '=', sl.producto_id.id),
                ('company_id', '=', liquidacion.company_id.id),
            ], limit=1)
            if not tarifa:
                tarifa = Tarifa.search([
                    ('producto_id', '=', sl.producto_id.id),
                    ('company_id', '=', False),
                ], limit=1)

            if not tarifa:
                if sl.producto_id.name not in sin_tarifa:
                    sin_tarifa.append(sl.producto_id.name)
                continue

            # Resolver peso según base_peso de la tarifa
            orden = sl.orden_id
            if tarifa.base_peso == 'peso_entrada':
                peso = orden.peso_entrada
            elif tarifa.base_peso == 'peso_salida':
                peso = orden.peso_salida_real
            elif tarifa.base_peso == 'peso_neto':
                peso = orden.peso_entrada - orden.peso_salida_real if orden.peso_salida_real else orden.peso_entrada
            elif tarifa.base_peso == 'bultos':
                peso = orden.total_bultos
            else:  # fijo
                peso = sl.cantidad

            Linea.create({
                'liquidacion_id': liquidacion.id,
                'orden_servicio_id': orden.id,
                'orden_servicio_linea_id': sl.id,
                'producto_id': sl.producto_id.id,
                'base_peso': tarifa.base_peso,
                'peso': peso,
                'tarifa': tarifa.tarifa,
            })

        if sin_tarifa:
            raise UserError(
                'No se encontró tarifa de cuadrilla para los siguientes servicios:\n- %s\n\n'
                'Configure las tarifas en Cuadrilla → Configuración → Tarifas.'
                % '\n- '.join(sin_tarifa)
            )

        return {'type': 'ir.actions.act_window_close'}
