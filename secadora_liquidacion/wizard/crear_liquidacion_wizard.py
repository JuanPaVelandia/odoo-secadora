# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError


class CrearLiquidacionWizard(models.TransientModel):
    _name = 'secadora.crear.liquidacion.wizard'
    _description = 'Agregar Pesajes a Liquidación'

    liquidacion_id = fields.Many2one(
        'secadora.liquidacion',
        string='Liquidación',
        help='Liquidación existente (vacío para crear nueva)',
    )
    tercero_id = fields.Many2one(
        'res.partner',
        string='Agricultor',
        required=True,
    )
    fecha_desde = fields.Date(
        string='Fecha Desde',
    )
    fecha_hasta = fields.Date(
        string='Fecha Hasta',
    )
    pesaje_ids = fields.Many2many(
        'secadora.pesaje',
        string='Pesajes',
    )

    @api.onchange('tercero_id', 'fecha_desde', 'fecha_hasta')
    def _onchange_buscar_pesajes(self):
        """Busca pesajes elegibles según filtros."""
        if not self.tercero_id:
            self.pesaje_ids = False
            return

        domain = [
            ('state', '=', 'completado'),
            ('direccion', '=', 'entrada'),
            ('tipo_operacion_id.codigo', '=', 'COMPRA'),
            ('liquidacion_id', '=', False),
            ('tercero_id', '=', self.tercero_id.id),
        ]
        if self.fecha_desde:
            domain.append(('fecha', '>=', self.fecha_desde))
        if self.fecha_hasta:
            domain.append(('fecha', '<=', self.fecha_hasta))

        pesajes = self.env['secadora.pesaje'].search(domain)
        self.pesaje_ids = pesajes

    def action_crear(self):
        self.ensure_one()
        if not self.pesaje_ids:
            raise UserError('Debe seleccionar al menos un pesaje.')

        # Validar que todos los pesajes sean de compra
        no_compra = self.pesaje_ids.filtered(
            lambda p: p.tipo_operacion_id.codigo != 'COMPRA'
        )
        if no_compra:
            nombres = ', '.join(no_compra.mapped('name'))
            raise UserError(
                'Solo se pueden liquidar pesajes de tipo Compra. '
                'Los siguientes pesajes no son compras: %s' % nombres
            )

        Liquidacion = self.env['secadora.liquidacion']
        Linea = self.env['secadora.liquidacion.linea']
        AnalisisLab = self.env['secadora.analisis.lab']

        liquidacion = self.liquidacion_id
        if not liquidacion:
            liquidacion = Liquidacion.create({
                'tercero_id': self.tercero_id.id,
                'fecha_desde': self.fecha_desde,
                'fecha_hasta': self.fecha_hasta,
            })

        # Pesajes ya en la liquidación
        pesajes_existentes = liquidacion.linea_ids.mapped('pesaje_id').ids

        for pesaje in self.pesaje_ids:
            if pesaje.id in pesajes_existentes:
                continue

            # Buscar análisis confirmado
            analisis = AnalisisLab.search([
                ('pesaje_id', '=', pesaje.id),
                ('state', '=', 'confirmado'),
            ], limit=1, order='id desc')

            peso_comercial = analisis.peso_comercial if analisis and analisis.peso_comercial > 0 else pesaje.peso_neto
            # Prioridad de precio: agricultor > catálogo > pesaje
            tercero = liquidacion.tercero_id
            if tercero and tercero.precio_compra_kg > 0:
                precio = tercero.precio_compra_kg
            else:
                PrecioCompra = self.env['secadora.precio.compra']
                precio_catalogo = PrecioCompra._obtener_precio(
                    pesaje.variedad_id.id,
                    pesaje.fecha,
                    liquidacion.company_id.id,
                )
                precio = precio_catalogo if precio_catalogo else pesaje.precio

            Linea.create({
                'liquidacion_id': liquidacion.id,
                'pesaje_id': pesaje.id,
                'peso_comercial': peso_comercial,
                'precio': precio,
            })

        # Auto-cargar fletes
        liquidacion.action_cargar_fletes()

        # Auto-aplicar deducciones del agricultor
        try:
            liquidacion.action_aplicar_deducciones()
        except UserError:
            pass  # No hay deducciones configuradas, continuar

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'secadora.liquidacion',
            'res_id': liquidacion.id,
            'view_mode': 'form',
            'target': 'current',
        }
