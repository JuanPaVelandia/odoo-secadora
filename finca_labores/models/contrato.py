# -*- coding: utf-8 -*-

from markupsafe import Markup, escape

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


def _fmt(valor):
    """Pesos sin decimales y con punto de miles, como en las hojas."""
    return '{:,.0f}'.format(valor or 0).replace(',', '.')


def _fmt_cantidad(valor):
    """Hectáreas o bultos: hasta dos decimales, con coma (12,5)."""
    texto = '{:,.2f}'.format(valor or 0).rstrip('0').rstrip('.')
    return texto.replace(',', '#').replace('.', ',').replace('#', '.')


class FincaContrato(models.Model):
    """Un bloque de la pestaña "Por contrato" de las hojas de finca: una labor
    en una finca, hecha por tramos (columnas de la hoja), cada uno con su lote,
    sus hectáreas y los operadores que lo trabajaron.

    Las verificaciones de la hoja se conservan: total de hectáreas contra el
    área de la finca, "Entre cuántos" digitado contra los operadores marcados,
    y la grilla operador x tramo con sus totales (pestaña Verificación).
    """
    _name = 'finca.contrato'
    _description = 'Labor por Contrato'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'fecha desc, name desc'

    name = fields.Char(
        string='Número',
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: 'Nuevo',
    )
    campana_id = fields.Many2one(
        'finca.campana',
        string='Campaña',
        required=True,
        index=True,
        default=lambda self: self.env['finca.campana']._get_campana(),
        tracking=True,
    )
    fecha = fields.Date(
        string='Fecha',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    finca_id = fields.Many2one(
        'secadora.lugar',
        string='Finca',
        required=True,
        index=True,
        domain=[('tipo', '=', 'finca')],
        tracking=True,
    )
    dueno_id = fields.Many2one(
        'res.partner',
        string='Dueño',
        compute='_compute_dueno_id',
        store=True,
        readonly=False,
        index=True,
        tracking=True,
        help='Se toma de la finca; se puede cambiar si esta labor la paga otro.',
    )
    labor_id = fields.Many2one(
        'finca.labor',
        string='Labor',
        required=True,
        domain=[('tipo', '=', 'contrato')],
        tracking=True,
    )
    unidad = fields.Selection(related='labor_id.unidad', string='Unidad')
    tarifa = fields.Float(
        string='Tarifa',
        digits=(12, 2),
        compute='_compute_tarifa',
        store=True,
        readonly=False,
        tracking=True,
        help='Se propone la de la labor y se copia a cada tramo.',
    )
    tramo_ids = fields.One2many(
        'finca.contrato.tramo',
        'contrato_id',
        string='Tramos',
        copy=True,
    )
    total_cantidad = fields.Float(
        string='Total registrado',
        digits=(12, 2),
        compute='_compute_totales',
        store=True,
    )
    total = fields.Float(
        string='Valor de la tarea',
        digits=(12, 2),
        compute='_compute_totales',
        store=True,
        tracking=True,
    )
    total_operadores = fields.Float(
        string='Total operadores',
        digits=(12, 2),
        compute='_compute_totales',
        store=True,
        help='Suma de lo que recibe cada operador. Debe ser igual al valor de la tarea.',
    )
    cantidad_operadores = fields.Integer(
        string='Operadores',
        compute='_compute_totales',
        store=True,
    )
    tramos_descuadrados = fields.Integer(
        string='Tramos sin cuadrar',
        compute='_compute_totales',
        store=True,
    )
    hectareas_finca = fields.Float(
        string='Hectáreas de la finca',
        digits=(12, 2),
        compute='_compute_hectareas_finca',
        help='Suma de las hectáreas de los lotes activos de la finca.',
    )
    diferencia_hectareas = fields.Float(
        string='Diferencia',
        digits=(12, 2),
        compute='_compute_hectareas_finca',
        help='Hectáreas registradas menos hectáreas de la finca.',
    )
    verificacion_html = fields.Html(
        string='Verificación',
        compute='_compute_verificacion_html',
        sanitize=False,
    )
    state = fields.Selection([
        ('borrador', 'Borrador'),
        ('confirmado', 'Confirmado'),
        ('cancelado', 'Cancelado'),
    ], string='Estado', default='borrador', required=True, index=True, tracking=True)
    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    observaciones = fields.Text(string='Observaciones')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('finca.contrato') or 'Nuevo'
        return super().create(vals_list)

    @api.depends('finca_id')
    def _compute_dueno_id(self):
        for rec in self:
            rec.dueno_id = rec.finca_id.dueno_id

    @api.depends('labor_id')
    def _compute_tarifa(self):
        for rec in self:
            rec.tarifa = rec.labor_id.valor_unitario

    @api.depends('tramo_ids.cantidad', 'tramo_ids.total', 'tramo_ids.total_operadores',
                 'tramo_ids.operador_ids', 'tramo_ids.cuadra')
    def _compute_totales(self):
        for rec in self:
            tramos = rec.tramo_ids
            rec.total_cantidad = sum(tramos.mapped('cantidad'))
            rec.total = sum(tramos.mapped('total'))
            rec.total_operadores = sum(tramos.mapped('total_operadores'))
            rec.cantidad_operadores = len(tramos.operador_ids)
            rec.tramos_descuadrados = len(tramos.filtered(lambda t: not t.cuadra))

    @api.depends('finca_id', 'unidad', 'total_cantidad')
    def _compute_hectareas_finca(self):
        for rec in self:
            if rec.unidad == 'ha' and rec.finca_id:
                lotes = self.env['secadora.lote'].search([('finca_id', '=', rec.finca_id.id)])
                rec.hectareas_finca = sum(lotes.mapped('hectareas'))
                rec.diferencia_hectareas = rec.total_cantidad - rec.hectareas_finca
            else:
                rec.hectareas_finca = 0.0
                rec.diferencia_hectareas = 0.0

    @api.depends('tramo_ids.lote_id', 'tramo_ids.detalle', 'tramo_ids.cantidad', 'tramo_ids.tarifa',
                 'tramo_ids.entre_cuantos', 'tramo_ids.operador_ids', 'tramo_ids.valor_persona',
                 'tramo_ids.total', 'tramo_ids.cuadra', 'tramo_ids.ajuste_ids.operador_id',
                 'tramo_ids.ajuste_ids.partes', 'tramo_ids.ajuste_ids.valor_fijo')
    def _compute_verificacion_html(self):
        """La grilla de la hoja, solo lectura: operadores en filas, tramos en
        columnas, totales por fila y por columna."""
        for rec in self:
            tramos = rec.tramo_ids.sorted(lambda t: (t.sequence, t.id or 0))
            if not tramos:
                rec.verificacion_html = False
                continue
            operadores = tramos.operador_ids.sorted('name')
            valores = {t: t._valores_por_operador() for t in tramos}
            td = Markup('<td class="text-end">%s</td>')
            th = Markup('<th class="text-end">%s</th>')

            def fila(etiqueta, celdas, total='', clase=''):
                return (Markup('<tr class="%s"><th>%s</th>') % (clase, etiqueta)
                        + th % total + Markup('').join(celdas) + Markup('</tr>'))

            def celda_cuadre(t):
                if not t.entre_cuantos or t.entre_cuantos == len(t.operador_ids):
                    return Markup('<td class="text-end">%s</td>') % (t.entre_cuantos or len(t.operador_ids))
                return Markup('<td class="text-end table-danger" title="Digitado %s, marcados %s">%s / %s</td>') % (
                    t.entre_cuantos, len(t.operador_ids), t.entre_cuantos, len(t.operador_ids))

            filas = [
                fila('Lote', [th % (t.lote_id.name or t.detalle or '') for t in tramos], 'Total'),
                fila('Cantidad', [td % _fmt_cantidad(t.cantidad) for t in tramos], _fmt_cantidad(rec.total_cantidad)),
                fila('Tarifa', [td % _fmt(t.tarifa) for t in tramos]),
                fila('Entre cuántos', [celda_cuadre(t) for t in tramos]),
                fila('Valor por persona',
                     [td % ('Especial' if t.reparto_especial else _fmt(t.valor_persona)) for t in tramos],
                     clase='table-light'),
            ]
            for op in operadores:
                celdas = [td % (_fmt(valores[t][op]) if op in valores[t] else '') for t in tramos]
                total_op = sum(valores[t].get(op, 0.0) for t in tramos)
                filas.append(fila(escape(op.name), celdas, _fmt(total_op)))
            filas.append(fila(
                'Total operadores',
                [(th if t.cuadra else Markup('<th class="text-end table-danger">%s</th>')) % _fmt(t.total_operadores)
                 for t in tramos],
                _fmt(rec.total_operadores), 'table-light'))
            filas.append(fila(
                'Valor de la tarea', [th % _fmt(t.total) for t in tramos], _fmt(rec.total), 'table-light'))
            rec.verificacion_html = (
                Markup('<div class="table-responsive"><table class="table table-sm table-bordered o_finca_grilla">')
                + Markup('').join(filas) + Markup('</table></div>'))

    def action_confirmar(self):
        for rec in self:
            if not rec.tramo_ids:
                raise UserError('Agregue al menos un tramo antes de confirmar %s.' % rec.name)
            sin_operador = rec.tramo_ids.filtered(lambda t: not t.operador_ids)
            if sin_operador:
                raise UserError('En %s hay tramos sin operadores: %s.' % (
                    rec.name, ', '.join(sin_operador.mapped('display_name'))))
            descuadrados = rec.tramo_ids.filtered(lambda t: not t.cuadra)
            if descuadrados:
                raise UserError('%s no cuadra:\n%s' % (rec.name, '\n'.join(
                    '- %s: %s' % (t.display_name, t.motivo_descuadre) for t in descuadrados)))
            if not rec.total:
                raise UserError('La labor %s no tiene valor.' % rec.name)
            if not rec.dueno_id:
                raise UserError(
                    'La labor %s no tiene dueño. Asigne el dueño en la finca %s o en la labor.'
                    % (rec.name, rec.finca_id.name))
            rec.tramo_ids.operador_ids._marcar_operador_finca()
            rec.state = 'confirmado'

    def action_borrador(self):
        self.write({'state': 'borrador'})

    def action_cancelar(self):
        self.write({'state': 'cancelado'})


class FincaContratoTramo(models.Model):
    """Una columna del bloque: un lote (o parte de él) con su cuadrilla."""
    _name = 'finca.contrato.tramo'
    _description = 'Tramo de Labor por Contrato'
    _order = 'contrato_id, sequence, id'

    contrato_id = fields.Many2one(
        'finca.contrato',
        string='Labor',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(default=10)
    # El tramo se abre en su propio formulario (flecha de la fila), donde no
    # existe `parent`: la finca y el estado de la labor se leen de aquí.
    finca_id = fields.Many2one(related='contrato_id.finca_id', string='Finca')
    contrato_state = fields.Selection(related='contrato_id.state', string='Estado de la labor')
    lote_id = fields.Many2one(
        'secadora.lote',
        string='Lote',
        index=True,
    )
    detalle = fields.Char(
        string='Detalle',
        help='Para distinguir partes del mismo lote (ej. "85p") o anotar algo del tramo.',
    )
    cantidad = fields.Float(
        string='Has / Bultos',
        digits=(12, 2),
        compute='_compute_cantidad',
        store=True,
        readonly=False,
        help='Se propone el área del lote; cámbiela si la cuadrilla hizo solo una parte.',
    )
    tarifa = fields.Float(
        string='Tarifa',
        digits=(12, 2),
        compute='_compute_tarifa',
        store=True,
        readonly=False,
    )
    total = fields.Float(
        string='Valor',
        digits=(12, 2),
        compute='_compute_valores',
        store=True,
    )
    operador_ids = fields.Many2many(
        'res.partner',
        'finca_contrato_tramo_operador_rel',
        'tramo_id',
        'operador_id',
        string='Operadores',
    )
    entre_cuantos = fields.Integer(
        string='Entre cuántos',
        help='Cuántos trabajaron según el reporte de campo. Si no coincide con '
             'los operadores marcados, el tramo queda en rojo y no se puede confirmar.',
    )
    num_operadores = fields.Integer(
        string='Marcados',
        compute='_compute_valores',
        store=True,
    )
    ajuste_ids = fields.One2many(
        'finca.contrato.tramo.ajuste',
        'tramo_id',
        string='Reparto especial',
        copy=True,
        help='Solo para quien no recibe la parte igual: partes distintas de 1 '
             '(ej. 0,5 por media jornada) o un monto fijo.',
    )
    reparto_especial = fields.Boolean(
        string='Con reparto especial',
        compute='_compute_valores',
        store=True,
    )
    valor_persona = fields.Float(
        string='Valor por persona',
        digits=(12, 2),
        compute='_compute_valores',
        store=True,
        help='Parte igual de cada operador. Con reparto especial es la parte '
             'de quien tiene 1 parte y no tiene monto fijo.',
    )
    total_operadores = fields.Float(
        string='Total operadores',
        digits=(12, 2),
        compute='_compute_valores',
        store=True,
    )
    cuadra = fields.Boolean(
        string='Cuadra',
        compute='_compute_valores',
        store=True,
    )
    motivo_descuadre = fields.Char(
        string='Por qué no cuadra',
        compute='_compute_valores',
        store=True,
    )
    reparto_html = fields.Html(
        string='Reparto',
        compute='_compute_reparto_html',
        sanitize=False,
    )
    excede_lote = fields.Boolean(
        string='Supera el lote',
        compute='_compute_excede_lote',
        help='Los tramos de este lote en la labor suman más hectáreas que el lote.',
    )

    @api.depends('lote_id', 'contrato_id.unidad')
    def _compute_cantidad(self):
        for rec in self:
            if rec.contrato_id.unidad == 'ha' and rec.lote_id.hectareas:
                rec.cantidad = rec.lote_id.hectareas
            else:
                rec.cantidad = rec.cantidad or 0.0

    @api.depends('contrato_id.tarifa')
    def _compute_tarifa(self):
        for rec in self:
            rec.tarifa = rec.contrato_id.tarifa

    def _ajustes_vigentes(self):
        """Ajustes de operadores que siguen marcados en el tramo."""
        self.ensure_one()
        return {a.operador_id: a for a in self.ajuste_ids if a.operador_id in self.operador_ids}

    def _valores_por_operador(self):
        """{operador: valor}. Los montos fijos se pagan tal cual; lo que queda
        del valor del tramo se reparte entre los demás según sus partes (1 si
        no tienen ajuste). La misma regla está en SQL en finca.labor.movimiento."""
        self.ensure_one()
        ajustes = self._ajustes_vigentes()
        valores = {op: a.valor_fijo for op, a in ajustes.items() if a.valor_fijo}
        partes = {op: (ajustes[op].partes if op in ajustes else 1.0)
                  for op in self.operador_ids if op not in valores}
        resto = self.total - sum(valores.values())
        suma_partes = sum(partes.values())
        for op, p in partes.items():
            valores[op] = resto * p / suma_partes if suma_partes else 0.0
        return valores

    @api.depends('cantidad', 'tarifa', 'operador_ids', 'entre_cuantos',
                 'ajuste_ids.operador_id', 'ajuste_ids.partes', 'ajuste_ids.valor_fijo')
    def _compute_valores(self):
        for rec in self:
            rec.total = rec.cantidad * rec.tarifa
            rec.num_operadores = len(rec.operador_ids)
            ajustes = rec._ajustes_vigentes()
            rec.reparto_especial = bool(ajustes)
            valores = rec._valores_por_operador()
            rec.total_operadores = sum(valores.values())
            iguales = [op for op in rec.operador_ids if op not in ajustes]
            rec.valor_persona = valores[iguales[0]] if iguales else 0.0

            motivo = False
            fijos = sum(a.valor_fijo for a in ajustes.values())
            if not rec.num_operadores:
                motivo = 'no tiene operadores'
            elif rec.entre_cuantos and rec.entre_cuantos != rec.num_operadores:
                motivo = 'dice entre %s y hay %s operadores marcados' % (
                    rec.entre_cuantos, rec.num_operadores)
            elif fijos > rec.total + 0.5:
                motivo = 'los montos fijos (%s) pasan el valor del tramo (%s)' % (
                    _fmt(fijos), _fmt(rec.total))
            elif abs(rec.total_operadores - rec.total) > 0.5:
                motivo = 'los operadores suman %s y el tramo vale %s' % (
                    _fmt(rec.total_operadores), _fmt(rec.total))
            rec.motivo_descuadre = motivo
            rec.cuadra = not motivo

    @api.depends('total', 'operador_ids', 'ajuste_ids.operador_id', 'ajuste_ids.partes',
                 'ajuste_ids.valor_fijo')
    def _compute_reparto_html(self):
        for rec in self:
            if not rec.operador_ids:
                rec.reparto_html = False
                continue
            valores = rec._valores_por_operador()
            filas = Markup('').join(
                Markup('<tr><td>%s</td><td class="text-end">%s</td></tr>') % (op.name, _fmt(valores[op]))
                for op in rec.operador_ids.sorted('name'))
            rec.reparto_html = (
                Markup('<table class="table table-sm"><tr><th>Operador</th><th class="text-end">Valor</th></tr>')
                + filas
                + Markup('<tr><th>Total</th><th class="text-end">%s</th></tr></table>') % _fmt(sum(valores.values())))

    @api.depends('lote_id', 'cantidad', 'contrato_id.tramo_ids.cantidad', 'contrato_id.unidad')
    def _compute_excede_lote(self):
        for rec in self:
            if rec.contrato_id.unidad != 'ha' or not rec.lote_id.hectareas:
                rec.excede_lote = False
                continue
            mismo_lote = rec.contrato_id.tramo_ids.filtered(lambda t: t.lote_id == rec.lote_id)
            rec.excede_lote = sum(mismo_lote.mapped('cantidad')) > rec.lote_id.hectareas + 0.001

    @api.depends('lote_id', 'detalle', 'cantidad')
    def _compute_display_name(self):
        for rec in self:
            nombre = 'Lote %s' % rec.lote_id.name if rec.lote_id else (rec.detalle or 'Tramo')
            if rec.lote_id and rec.detalle:
                nombre += ' (%s)' % rec.detalle
            rec.display_name = '%s - %s' % (nombre, _fmt_cantidad(rec.cantidad))


class FincaContratoTramoAjuste(models.Model):
    """Operador de un tramo que no recibe la parte igual."""
    _name = 'finca.contrato.tramo.ajuste'
    _description = 'Reparto Especial de Tramo'
    _order = 'tramo_id, id'

    _operador_unique = models.Constraint(
        'UNIQUE(tramo_id, operador_id)',
        'El operador ya tiene un ajuste en este tramo.',
    )

    tramo_id = fields.Many2one(
        'finca.contrato.tramo',
        string='Tramo',
        required=True,
        ondelete='cascade',
        index=True,
    )
    operador_id = fields.Many2one(
        'res.partner',
        string='Operador',
        required=True,
    )
    partes = fields.Float(
        string='Partes',
        default=1.0,
        digits=(6, 2),
        help='Los demás cuentan 1 parte cada uno. 0,5 = media parte, 2 = doble.',
    )
    valor_fijo = fields.Float(
        string='Monto fijo',
        digits=(12, 2),
        help='Si se llena, el operador recibe este valor y el resto del tramo se '
             'reparte entre los demás. Las partes no se usan.',
    )
    valor = fields.Float(
        string='Recibe',
        digits=(12, 2),
        compute='_compute_valor',
    )

    @api.depends('partes', 'valor_fijo', 'tramo_id.total', 'tramo_id.operador_ids',
                 'tramo_id.ajuste_ids.partes', 'tramo_id.ajuste_ids.valor_fijo')
    def _compute_valor(self):
        for rec in self:
            rec.valor = rec.tramo_id._valores_por_operador().get(rec.operador_id, 0.0) if rec.tramo_id else 0.0

    @api.constrains('partes', 'valor_fijo')
    def _check_partes(self):
        for rec in self:
            if rec.valor_fijo < 0:
                raise ValidationError('El monto fijo no puede ser negativo.')
            if not rec.valor_fijo and rec.partes <= 0:
                raise ValidationError('Las partes deben ser mayores que cero (o use un monto fijo).')
