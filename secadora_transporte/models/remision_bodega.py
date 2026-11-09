# -*- coding: utf-8 -*-
"""Remisión de despacho desde una bodega del agricultor.

En la bodega (p. ej. Duitama) llenan una remisión física y aquí alguien la
transcribe. Un viaje suele llevar varias variedades para destinatarios
distintos —parte se vende a un tercero, parte va a una finca propia—, algo que
el flete no sabe expresar: tiene una sola variedad y un solo destino. Por eso
la remisión tiene líneas, y es ella, no el flete, la que descuenta el saldo.
"""

import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class RemisionBodega(models.Model):
    _name = 'secadora.remision.bodega'
    _description = 'Remisión de Despacho desde Bodega'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'fecha desc, id desc'

    name = fields.Char(
        string='Número',
        required=True,
        copy=False,
        readonly=True,
        default='Nuevo',
    )
    numero_fisico = fields.Char(
        string='Remisión física N°',
        tracking=True,
        help='El número de la remisión en papel que hicieron en la bodega. '
             'Es lo que permite cruzar este registro con el original.',
    )
    fecha = fields.Date(
        string='Fecha de salida',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    bodega_id = fields.Many2one(
        'secadora.lugar',
        string='Bodega de origen',
        required=True,
        domain=[('tipo', '=', 'bodega')],
        tracking=True,
    )
    destino_id = fields.Many2one(
        'secadora.lugar',
        string='Destino del viaje',
        tracking=True,
        help='A dónde llega el camión. Cada línea puede tener luego su '
             'propio destinatario o destino final.',
    )

    vehiculo_id = fields.Many2one(
        'secadora.vehiculo',
        string='Vehículo',
        tracking=True,
    )
    conductor_id = fields.Many2one(
        'secadora.conductor',
        string='Conductor',
    )
    flete_id = fields.Many2one(
        'secadora.flete',
        string='Flete',
        copy=False,
        help='El flete con el que se paga el transporte. Un flete enlazado a '
             'una remisión no descuenta bultos: ya los descuenta la remisión.',
    )

    linea_ids = fields.One2many(
        'secadora.remision.bodega.linea',
        'remision_id',
        string='Carga',
        copy=True,
    )
    total_bultos = fields.Integer(
        string='Total bultos',
        compute='_compute_total_bultos',
        store=True,
    )
    movimiento_bultos_ids = fields.One2many(
        'secadora.movimiento.bultos',
        'remision_id',
        string='Movimientos de bultos',
    )

    state = fields.Selection([
        ('borrador', 'Borrador'),
        ('confirmado', 'Despachado'),
        ('cancelado', 'Cancelado'),
    ], string='Estado', default='borrador', required=True, tracking=True,
       index=True, copy=False)
    observaciones = fields.Text(string='Observaciones')

    @api.depends('linea_ids.bultos')
    def _compute_total_bultos(self):
        for rec in self:
            rec.total_bultos = sum(rec.linea_ids.mapped('bultos'))

    @api.onchange('bodega_id')
    def _onchange_bodega_id(self):
        # Los bultos de la bodega son del agricultor dueño de la bodega; la
        # remisión queda a su nombre para que la vea con sus reglas.
        if self.bodega_id.company_id:
            self.company_id = self.bodega_id.company_id

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'secadora.remision.bodega') or 'Nuevo'
        return super().create(vals_list)

    def unlink(self):
        if any(r.state == 'confirmado' for r in self):
            raise UserError('Una remisión despachada no se borra: cancélela '
                            'primero para devolver los bultos a la bodega.')
        return super().unlink()

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def action_confirmar(self):
        for rem in self:
            if rem.state != 'borrador':
                continue
            if not rem.linea_ids:
                raise UserError('La remisión no tiene carga.')
            if any(l.bultos <= 0 for l in rem.linea_ids):
                raise UserError('Todas las líneas deben tener bultos.')
            if rem.flete_id.movimiento_bultos_ids:
                raise UserError(
                    f'El flete {rem.flete_id.name} ya descontó bultos de la '
                    f'bodega por su cuenta. Quítelo de la remisión o cancele '
                    f'ese flete; si no, los bultos se descontarían dos veces.')
            faltantes = rem.linea_ids._descontar_de_bodega()
            rem.state = 'confirmado'
            if faltantes:
                # Igual que en el flete: no se bloquea, porque el camión ya
                # salió; se deja constancia para revisar el inventario.
                rem.message_post(body=(
                    'Faltó saldo en la bodega para: '
                    + '; '.join(faltantes)
                    + '. Se descontó solo lo que había; revise el inventario.'))
        return True

    def action_cancelar(self):
        for rem in self:
            if rem.state == 'confirmado':
                movs = rem.movimiento_bultos_ids.filtered(
                    lambda m: m.tipo == 'salida_flete')
                # Se borran exactamente los despachos que creó esta remisión,
                # y con eso el pendiente vuelve a lo que era.
                movs.mapped('despacho_id').sudo().unlink()
                movs.sudo().unlink()
            rem.state = 'cancelado'
        return True

    def action_borrador(self):
        self.filtered(lambda r: r.state == 'cancelado').write(
            {'state': 'borrador'})
        return True

    def action_imprimir(self):
        return self.env.ref(
            'secadora_transporte.action_report_remision_bodega'
        ).report_action(self)


class RemisionBodegaLinea(models.Model):
    _name = 'secadora.remision.bodega.linea'
    _description = 'Línea de Remisión desde Bodega'
    _order = 'remision_id, sequence, id'

    remision_id = fields.Many2one(
        'secadora.remision.bodega',
        string='Remisión',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(default=10)
    bodega_id = fields.Many2one(related='remision_id.bodega_id')
    state = fields.Selection(related='remision_id.state')

    variedad_id = fields.Many2one(
        'secadora.variedad.arroz',
        string='Variedad',
        required=True,
    )
    codigo_variedad = fields.Char(
        related='variedad_id.codigo',
        string='Código',
    )
    es_semilla = fields.Boolean(
        string='Semilla',
        default=True,
        help='Si se marca, sale solo de los bultos de semilla de la bodega; '
             'si no, solo de los que no son semilla. Sin esta distinción el '
             'descuento tomaría los más antiguos, sean o no semilla.',
    )
    bultos = fields.Integer(string='Bultos', required=True)
    disponible = fields.Integer(
        string='Disponible en bodega',
        compute='_compute_disponible',
        help='Bultos de esta variedad (semilla o no) que la bodega tiene hoy.',
    )
    destinatario_id = fields.Many2one(
        'res.partner',
        string='Para',
        help='A quién va esta parte de la carga: el comprador, o el '
             'responsable de la finca que la recibe.',
    )
    destino_final_id = fields.Many2one(
        'secadora.lugar',
        string='Destino final',
        help='Si esta parte sigue más allá del destino del viaje (p. ej. se '
             'deja en Yopal y sigue en camioneta a la finca del Pauto).',
    )
    nota = fields.Char(string='Nota')

    @api.depends('variedad_id', 'es_semilla', 'remision_id.bodega_id')
    def _compute_disponible(self):
        Registro = self.env['secadora.registro.bultos'].sudo()
        for linea in self:
            if not (linea.variedad_id and linea.bodega_id):
                linea.disponible = 0
                continue
            regs = Registro.search(linea._dominio_saldo())
            linea.disponible = sum(regs.mapped('cantidad_pendiente'))

    def _dominio_saldo(self):
        self.ensure_one()
        return [
            ('bodega_id', '=', self.bodega_id.id),
            ('variedad_id', '=', self.variedad_id.id),
            ('es_semilla', '=', self.es_semilla),
            ('cantidad_pendiente', '>', 0),
        ]

    def _descontar_de_bodega(self):
        """Descuenta cada línea FIFO por fecha de empaque.

        Devuelve la lista de faltantes (texto) para que la remisión los deje
        en el chatter.
        """
        Mov = self.env['secadora.movimiento.bultos'].sudo()
        Despacho = self.env['secadora.despacho.bultos'].sudo()
        Registro = self.env['secadora.registro.bultos'].sudo()
        faltantes = []
        for linea in self:
            rem = linea.remision_id
            candidatos = Registro.search(
                linea._dominio_saldo(), order='fecha asc, id asc')
            por_descontar = linea.bultos
            for reg in candidatos:
                if por_descontar <= 0:
                    break
                toma = min(reg.cantidad_pendiente, por_descontar)
                despacho = Despacho.create({
                    'registro_bultos_id': reg.id,
                    'cantidad': toma,
                    'confirmado': True,
                })
                destino = linea.destino_final_id or rem.destino_id
                Mov.create({
                    'registro_bultos_id': reg.id,
                    'tipo': 'salida_flete',
                    'bodega_origen_id': rem.bodega_id.id,
                    'bodega_destino_id': (
                        destino.id if destino.tipo == 'bodega' else False),
                    'cantidad': toma,
                    'fecha': fields.Datetime.to_datetime(rem.fecha),
                    'flete_id': rem.flete_id.id or False,
                    'despacho_id': despacho.id,
                    'remision_id': rem.id,
                    'remision_linea_id': linea.id,
                    'notas': ' · '.join(filter(None, [
                        f'Remisión {rem.name}',
                        rem.numero_fisico and f'física {rem.numero_fisico}',
                        linea.destinatario_id.name
                        and f'para {linea.destinatario_id.name}',
                    ])),
                })
                por_descontar -= toma
            if por_descontar > 0:
                faltantes.append(
                    f'{linea.variedad_id.name} '
                    f'({"semilla" if linea.es_semilla else "no semilla"}): '
                    f'{por_descontar} de {linea.bultos} bultos')
                _logger.warning(
                    'Remisión %s: la bodega %s no tenía saldo para %s de los '
                    '%s bultos de %s.', rem.name, rem.bodega_id.name,
                    por_descontar, linea.bultos, linea.variedad_id.name)
        return faltantes


class MovimientoBultosRemision(models.Model):
    _inherit = 'secadora.movimiento.bultos'

    remision_id = fields.Many2one(
        'secadora.remision.bodega',
        string='Remisión',
        ondelete='set null',
        index=True,
    )
    remision_linea_id = fields.Many2one(
        'secadora.remision.bodega.linea',
        string='Línea de remisión',
        ondelete='set null',
    )


class FleteRemision(models.Model):
    _inherit = 'secadora.flete'

    remision_ids = fields.One2many(
        'secadora.remision.bodega',
        'flete_id',
        string='Remisiones',
    )

    def _aplica_a_bultos(self):
        # Si el viaje tiene remisión, es ella la que descuenta por línea; el
        # flete solo lleva el costo del transporte.
        return super()._aplica_a_bultos().filtered(lambda f: not f.remision_ids)
