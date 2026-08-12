# -*- coding: utf-8 -*-
"""El flete que sale de una bodega descuenta sus bultos del inventario.

El agricultor guarda en su bodega lo que la secadora le despachó; cuando manda
un flete desde allí, esos bultos dejan de estar. Sin esto el saldo solo subiría
y no serviría para saber qué queda.
"""

import logging

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class MovimientoBultosFlete(models.Model):
    _inherit = 'secadora.movimiento.bultos'

    # El enlace vive aquí y no en `bascula` porque es este módulo el que
    # conoce los fletes.
    flete_id = fields.Many2one(
        'secadora.flete',
        string='Flete',
        ondelete='set null',
        index=True,
        help='El flete que sacó estos bultos de la bodega.',
    )
    despacho_id = fields.Many2one(
        'secadora.despacho.bultos',
        string='Despacho',
        ondelete='set null',
        help='El despacho que descontó el saldo. Se guarda para poder '
             'deshacerlo exactamente si el flete se cancela.',
    )


class FleteBultos(models.Model):
    _inherit = 'secadora.flete'

    movimiento_bultos_ids = fields.One2many(
        'secadora.movimiento.bultos',
        'flete_id',
        string='Movimientos de bultos',
    )

    def action_confirmar(self):
        res = super().action_confirmar()
        self._descontar_bultos_de_bodega()
        return res

    def action_cancelar(self):
        # Se devuelve el saldo ANTES de cancelar: si el flete no salió, esos
        # bultos siguen en la bodega.
        self._devolver_bultos_a_bodega()
        return super().action_cancelar()

    # ------------------------------------------------------------------
    def _aplica_a_bultos(self):
        """Fletes que mueven bultos propios desde una bodega."""
        return self.filtered(
            lambda f: f.bultos > 0
            and f.origen_id
            and f.origen_id.tipo == 'bodega'
        )

    def _descontar_bultos_de_bodega(self):
        """Descuenta los bultos del flete, del más antiguo al más reciente.

        FIFO por fecha de empaque: sale primero lo que lleva más tiempo
        guardado. Si el flete pide más de lo que hay, se descuenta lo que
        haya y se avisa en el log — un camión cargado no puede quedarse
        esperando a que cuadre el inventario.
        """
        Mov = self.env['secadora.movimiento.bultos'].sudo()
        Registro = self.env['secadora.registro.bultos'].sudo()

        for flete in self._aplica_a_bultos():
            if flete.movimiento_bultos_ids:
                continue  # ya se descontó; no repetir al reconfirmar

            dominio = [
                ('bodega_id', '=', flete.origen_id.id),
                ('cantidad_pendiente', '>', 0),
            ]
            if flete.variedad_id:
                dominio.append(('variedad_id', '=', flete.variedad_id.id))

            candidatos = Registro.search(dominio, order='fecha asc, id asc')
            por_descontar = flete.bultos

            for reg in candidatos:
                if por_descontar <= 0:
                    break
                toma = min(reg.cantidad_pendiente, por_descontar)
                # El saldo se lleva en `secadora.despacho.bultos`, que ya
                # calcula pendiente = empacado - despachado. Su `pesaje_id` es
                # opcional justamente para casos como este.
                despacho = self.env['secadora.despacho.bultos'].sudo().create({
                    'registro_bultos_id': reg.id,
                    'cantidad': toma,
                    'confirmado': True,
                })
                Mov.create({
                    'registro_bultos_id': reg.id,
                    'tipo': 'salida_flete',
                    'bodega_origen_id': flete.origen_id.id,
                    'bodega_destino_id': (
                        flete.destino_id.id
                        if flete.destino_id and flete.destino_id.tipo == 'bodega'
                        else False
                    ),
                    'cantidad': toma,
                    'flete_id': flete.id,
                    'despacho_id': despacho.id,
                    'notas': f'Flete {flete.name}',
                })
                por_descontar -= toma

            if por_descontar > 0:
                _logger.warning(
                    'Flete %s: la bodega %s no tenía saldo para %s de los %s '
                    'bultos. Se descontó lo disponible.',
                    flete.name, flete.origen_id.name, por_descontar, flete.bultos)

    def _devolver_bultos_a_bodega(self):
        """Deshace el descuento cuando el flete se cancela."""
        for flete in self:
            movs = flete.movimiento_bultos_ids.filtered(
                lambda m: m.tipo == 'salida_flete')
            if not movs:
                continue
            # Se borran exactamente los despachos que creó este flete —de ahí
            # que el movimiento guarde su id—, y con eso el pendiente vuelve
            # solo a lo que era.
            movs.mapped('despacho_id').sudo().unlink()
            movs.sudo().unlink()
