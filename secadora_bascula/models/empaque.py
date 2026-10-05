# -*- coding: utf-8 -*-
"""Inventario de empaques de la secadora.

Es control de unidades, no contabilidad: los empaques entran por la factura de
compra (cualquier compañía del grupo los puede haber facturado), salen cuando
se empacan bultos con empaque de la secadora y se cuadran con un conteo físico.
Todo vive en la bodega principal de la secadora.

No se usa el `product_id` de la línea de factura a propósito: cambiarlo en una
factura publicada movería cuentas e impuestos. La línea lleva su propio campo
`empaque_id`, que solo mueve inventario.
"""

from datetime import datetime, time

from odoo import api, fields, models, tools
from odoo.exceptions import UserError
from odoo.tools import SQL, float_compare

EMPAQUE_TIPOS = [
    ('compra', 'Compra'),
    ('devolucion', 'Devolución a proveedor'),
    ('consumo', 'Consumo en empaque'),
    ('ajuste', 'Ajuste por conteo'),
    ('otro', 'Otro movimiento'),
]


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    es_empaque = fields.Boolean(
        string='Empaque de la secadora',
        help='Se lleva en el inventario de empaques: entra con las facturas de '
             'compra y sale al empacar bultos con empaque de la secadora. '
             'El producto debe controlar inventario.',
    )


class StockMove(models.Model):
    _inherit = 'stock.move'

    empaque_tipo = fields.Selection(
        EMPAQUE_TIPOS,
        string='Movimiento de empaques',
        readonly=True,
        copy=False,
        index='btree_not_null',
    )

    @api.model
    def _empaque_ubicaciones(self, producto, tipo, entrada):
        """(origen, destino, compañía) del movimiento en la bodega de la secadora."""
        # sudo: quien asigna una factura de otra compañía no ve las
        # ubicaciones de la secadora.
        self = self.sudo()
        bodega = self.env.ref('stock.stock_location_stock')
        compania = bodega.company_id
        if tipo in ('compra', 'devolucion'):
            otra = self.env.ref('stock.stock_location_suppliers')
        elif tipo == 'consumo':
            otra = self.env['stock.location']._get_produccion_secadora(compania)
        else:
            otra = producto.sudo().with_company(compania).property_stock_inventory
        if not otra:
            raise UserError('No se encontró la ubicación de inventario para registrar los empaques.')
        return (otra, bodega, compania) if entrada else (bodega, otra, compania)

    @api.model
    def _empaque_sincronizar(self, move, producto, cantidad, tipo, entrada, fecha, referencia):
        """Deja hecho un movimiento de `cantidad` empaques y lo devuelve.

        Si `move` ya existe se corrige su cantidad; si cambió el producto o el
        sentido, se anula y se hace uno nuevo. Con cantidad cero el movimiento
        se anula y no se devuelve ninguno.
        """
        move = move.sudo()
        cantidad = max(cantidad or 0.0, 0.0)
        if move and (not cantidad or move.product_id != producto or move.empaque_tipo != tipo
                     or (move.location_dest_id.usage == 'internal') != entrada):
            move._empaque_anular()
            move = move.browse()
        if not cantidad:
            return move
        if not move:
            origen, destino, compania = self._empaque_ubicaciones(producto, tipo, entrada)
            move = self.sudo().with_company(compania).create({
                'product_id': producto.id,
                'product_uom_qty': cantidad,
                'product_uom': producto.uom_id.id,
                'location_id': origen.id,
                'location_dest_id': destino.id,
                'company_id': compania.id,
                'origin': referencia,
                'empaque_tipo': tipo,
            })
            move._action_confirm()
            # En v19 un movimiento solo se valida si está "recogido"; sin esto
            # queda reservado y la existencia no cambia.
            move.quantity = cantidad
            move.picked = True
            move._action_done()
            if move.state != 'done':
                raise UserError('No se pudo registrar el movimiento de empaques (%s).' % referencia)
        elif float_compare(move.quantity, cantidad, precision_rounding=move.product_uom.rounding or 0.01):
            # Corregir un movimiento hecho ajusta la existencia por la diferencia.
            move.quantity = cantidad
        if move.origin != referencia:
            move.origin = referencia
        # A mediodía: en UTC cae el mismo día en Colombia.
        fecha_hora = datetime.combine(fecha or fields.Date.context_today(self), time(12))
        if move.date != fecha_hora:
            move.write({'date': fecha_hora})
            move.move_line_ids.write({'date': fecha_hora})
        return move

    def _empaque_anular(self):
        """Un movimiento hecho no se puede borrar ni cancelar: se deja en cero."""
        for move in self.sudo():
            if move.state == 'done' and move.quantity:
                move.quantity = 0
            elif move.state not in ('done', 'cancel'):
                move._action_cancel()


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    empaque_id = fields.Many2one(
        'product.product',
        string='Empaque',
        domain=[('es_empaque', '=', True)],
        copy=False,
        index='btree_not_null',
        help='Si esta línea es una compra de empaques, cuál. Al estar la '
             'factura publicada entran al inventario de empaques.',
    )
    empaque_cantidad = fields.Float(
        string='Cantidad de empaques',
        copy=False,
        help='Unidades que entran al inventario. Se propone la cantidad de la '
             'línea; cámbiela si la factura viene en pacas o rollos.',
    )
    empaque_move_id = fields.Many2one(
        'stock.move',
        string='Entrada de inventario',
        readonly=True,
        copy=False,
    )
    empaque_ingresado = fields.Boolean(
        string='En inventario',
        compute='_compute_empaque_ingresado',
    )

    @api.depends('empaque_move_id')
    def _compute_empaque_ingresado(self):
        for line in self:
            line.empaque_ingresado = bool(line.empaque_move_id)

    @api.onchange('empaque_id')
    def _onchange_empaque_id(self):
        if not self.empaque_id:
            self.empaque_cantidad = 0.0
        elif not self.empaque_cantidad:
            self.empaque_cantidad = self.quantity

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.filtered('empaque_id')._sincronizar_entrada_empaque()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if 'empaque_id' in vals or 'empaque_cantidad' in vals:
            if vals.get('empaque_id') and 'empaque_cantidad' not in vals:
                for line in self.filtered(lambda l: not l.empaque_cantidad):
                    super(AccountMoveLine, line).write({'empaque_cantidad': line.quantity})
            self._sincronizar_entrada_empaque()
        return res

    def unlink(self):
        self.sudo().empaque_move_id._empaque_anular()
        return super().unlink()

    def _sincronizar_entrada_empaque(self):
        """La entrada existe mientras la línea tenga empaque y la factura de
        proveedor esté publicada; en borrador o anulada se retira."""
        Move = self.env['stock.move']
        for line in self.sudo():
            factura = line.move_id
            vigente = (line.empaque_id and factura.state == 'posted'
                       and factura.move_type in ('in_invoice', 'in_refund'))
            cantidad = line.empaque_cantidad if vigente else 0.0
            if not cantidad and not line.empaque_move_id:
                continue
            devolucion = factura.move_type == 'in_refund'
            move = Move._empaque_sincronizar(
                line.empaque_move_id, line.empaque_id, cantidad,
                'devolucion' if devolucion else 'compra', not devolucion,
                factura.invoice_date or factura.date,
                ' - '.join(filter(None, [factura.name, factura.partner_id.name])))
            if move != line.empaque_move_id:
                line.empaque_move_id = move

    def action_abrir_factura_empaque(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'views': [(False, 'form')],
            'target': 'current',
        }


class AccountMove(models.Model):
    _inherit = 'account.move'

    def write(self, vals):
        res = super().write(vals)
        if 'state' in vals:
            # Publicar, pasar a borrador o anular: la entrada sigue a la factura.
            self.sudo().invoice_line_ids.filtered(
                lambda l: l.empaque_id or l.empaque_move_id)._sincronizar_entrada_empaque()
        return res


class EmpaqueMovimiento(models.Model):
    """Kardex de empaques: una fila por movimiento de inventario hecho. La
    suma de `saldo` es la existencia."""
    _name = 'secadora.empaque.movimiento'
    _description = 'Movimiento de Inventario de Empaques'
    _auto = False
    _order = 'fecha desc, id desc'
    _rec_name = 'referencia'

    fecha = fields.Date(string='Fecha', readonly=True)
    product_id = fields.Many2one('product.product', string='Empaque', readonly=True)
    tipo = fields.Selection(EMPAQUE_TIPOS, string='Tipo', readonly=True)
    referencia = fields.Char(string='Referencia', readonly=True)
    entrada = fields.Float(string='Entradas', readonly=True)
    salida = fields.Float(string='Salidas', readonly=True)
    saldo = fields.Float(string='Saldo', readonly=True)
    company_id = fields.Many2one('res.company', string='Empresa', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(SQL("""
            CREATE OR REPLACE VIEW %(table)s AS (
                SELECT sm.id,
                       (sm.date AT TIME ZONE 'UTC' AT TIME ZONE 'America/Bogota')::date AS fecha,
                       sm.product_id,
                       COALESCE(sm.empaque_tipo,
                                CASE WHEN 'inventory' IN (ori.usage, des.usage) THEN 'ajuste'
                                     ELSE 'otro' END) AS tipo,
                       sm.origin AS referencia,
                       CASE WHEN des.usage = 'internal' THEN sm.quantity ELSE 0 END AS entrada,
                       CASE WHEN ori.usage = 'internal' THEN sm.quantity ELSE 0 END AS salida,
                       CASE WHEN des.usage = 'internal' THEN sm.quantity ELSE -sm.quantity END AS saldo,
                       sm.company_id
                  FROM stock_move sm
                  JOIN product_product pp ON pp.id = sm.product_id
                  JOIN product_template pt ON pt.id = pp.product_tmpl_id
                  JOIN stock_location ori ON ori.id = sm.location_id
                  JOIN stock_location des ON des.id = sm.location_dest_id
                 WHERE sm.state = 'done'
                   AND pt.es_empaque
                   AND sm.quantity <> 0
                   AND (ori.usage = 'internal') <> (des.usage = 'internal')
            )
        """, table=SQL.identifier(self._table)))

    @api.model
    def _existencia(self, producto, fecha=None):
        """Existencia del empaque (hasta `fecha` inclusive), sin importar las
        compañías activas de quien consulta."""
        self.env.flush_all()
        domain = [('product_id', '=', producto.id)]
        if fecha:
            domain.append(('fecha', '<=', fecha))
        return self.sudo()._read_group(domain, [], ['saldo:sum'])[0][0] or 0.0


class EmpaqueAjuste(models.TransientModel):
    """Cuadra la existencia con un conteo físico."""
    _name = 'secadora.empaque.ajuste'
    _description = 'Ajuste de Empaques por Conteo'

    producto_id = fields.Many2one(
        'product.product',
        string='Empaque',
        required=True,
        domain=[('es_empaque', '=', True)],
        default=lambda self: self._producto_por_defecto(),
    )
    fecha = fields.Date(
        string='Fecha del conteo',
        required=True,
        default=fields.Date.context_today,
    )
    existencia = fields.Float(
        string='Existencia en el sistema',
        compute='_compute_existencia',
        help='Lo que debería haber a la fecha del conteo según compras y consumos.',
    )
    cantidad_contada = fields.Float(string='Cantidad contada', required=True)
    diferencia = fields.Float(string='Ajuste', compute='_compute_existencia')
    motivo = fields.Char(string='Observación')

    @api.model
    def _producto_por_defecto(self):
        productos = self.env['product.product'].search([('es_empaque', '=', True)], limit=2)
        return productos if len(productos) == 1 else False

    @api.depends('producto_id', 'fecha', 'cantidad_contada')
    def _compute_existencia(self):
        Movimiento = self.env['secadora.empaque.movimiento']
        for rec in self:
            rec.existencia = Movimiento._existencia(rec.producto_id, rec.fecha) if rec.producto_id else 0.0
            rec.diferencia = rec.cantidad_contada - rec.existencia

    def action_aplicar(self):
        self.ensure_one()
        if self.cantidad_contada < 0:
            raise UserError('La cantidad contada no puede ser negativa.')
        if not self.producto_id.is_storable:
            raise UserError('%s no controla inventario: active "Rastrear inventario" en el producto.'
                            % self.producto_id.display_name)
        diferencia = self.diferencia
        if diferencia:
            self.env['stock.move']._empaque_sincronizar(
                self.env['stock.move'], self.producto_id, abs(diferencia), 'ajuste', diferencia > 0,
                self.fecha, ' - '.join(filter(None, ['Conteo físico', self.motivo])))
        return self.env['ir.actions.act_window']._for_xml_id('secadora_bascula.action_empaque_movimiento')
