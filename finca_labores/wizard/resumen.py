# -*- coding: utf-8 -*-

from markupsafe import Markup

from odoo import models, fields, api


def _fmt(valor):
    return '{:,.0f}'.format(valor or 0).replace(',', '.')


class FincaResumen(models.TransientModel):
    """Tablero de saldos, al estilo de la pestaña "Resumen total" de la hoja:
    por dueño, por operador, dueño x operador y costo por finca, todo en una
    pantalla. Se arma en el servidor (HTML) y se recalcula al cambiar los
    filtros."""
    _name = 'finca.resumen'
    _description = 'Resumen de Saldos de Labores'

    campana_id = fields.Many2one(
        'finca.campana',
        string='Campaña',
        required=True,
        default=lambda self: self.env['finca.campana']._get_campana(),
    )
    dueno_id = fields.Many2one('res.partner', string='Dueño', help='Vacío: todos.')
    operador_id = fields.Many2one(
        'res.partner', string='Operador', domain=[('es_operador_finca', '=', True)],
        help='Vacío: todos.')
    solo_pendientes = fields.Boolean(
        string='Ocultar saldos en cero', default=True,
        help='Oculta los operadores con saldo cero en las tablas por operador y dueño x operador.')
    resumen_html = fields.Html(compute='_compute_resumen_html', sanitize=False)

    def _domain(self):
        domain = [('campana_id', '=', self.campana_id.id)]
        if self.dueno_id:
            domain.append(('dueno_id', '=', self.dueno_id.id))
        if self.operador_id:
            domain.append(('operador_id', '=', self.operador_id.id))
        return domain

    def _agrupar(self, groupby):
        """[(claves..., trabajos, pagos, saldo)] agrupado por los campos dados."""
        return self.env['finca.labor.movimiento']._read_group(
            self._domain(), groupby, ['trabajos:sum', 'pagos:sum', 'saldo:sum'])

    @api.depends('campana_id', 'dueno_id', 'operador_id', 'solo_pendientes')
    def _compute_resumen_html(self):
        for rec in self:
            rec.resumen_html = rec._render() if rec.campana_id else False

    # --- Construcción del HTML ---------------------------------------------

    @staticmethod
    def _celda_saldo(saldo, tag='td'):
        # Positivo: se le debe al operador. Negativo: se le pagó de más.
        clase = 'text-danger' if saldo > 0.5 else ('text-primary' if saldo < -0.5 else 'text-muted')
        return Markup('<%s class="text-end %s">%s</%s>') % (tag, clase, _fmt(saldo), tag)

    def _tabla(self, titulo, encabezados, filas, total=None):
        """filas: listas de celdas ya armadas (<td>...</td>)."""
        th = Markup('').join(
            Markup('<th class="%s">%s</th>') % ('text-end' if i else '', h) for i, h in enumerate(encabezados))
        cuerpo = Markup('').join(
            Markup('<tr>') + Markup('').join(fila) + Markup('</tr>') for fila in filas)
        pie = (Markup('<tfoot><tr class="fw-bold">') + Markup('').join(total) + Markup('</tr></tfoot>')
               if total else Markup(''))
        if not filas:
            cuerpo = Markup('<tr><td colspan="%s" class="text-muted">Sin movimientos</td></tr>') % len(encabezados)
        return (Markup('<h5 class="mt-3">%s</h5>') % titulo
                + Markup('<table class="table table-sm table-hover o_finca_resumen"><thead><tr>')
                + th + Markup('</tr></thead><tbody>') + cuerpo + Markup('</tbody>') + pie + Markup('</table>'))

    def _txt(self, texto):
        return Markup('<td>%s</td>') % texto

    def _num(self, valor):
        return Markup('<td class="text-end">%s</td>') % _fmt(valor)

    def _render(self):
        self.ensure_one()
        sin_dueno = 'Sin dueño'

        # Tarjetas de totales
        por_dueno = self._agrupar(['dueno_id'])
        t_trab = sum(r[1] for r in por_dueno)
        t_pag = sum(r[2] for r in por_dueno)
        por_operador = self._agrupar(['operador_id'])
        se_debe = sum(r[3] for r in por_operador if r[3] > 0)
        de_mas = -sum(r[3] for r in por_operador if r[3] < 0)

        def tarjeta(titulo, valor, clase=''):
            return Markup(
                '<div class="col-6 col-md-3 mb-2"><div class="border rounded p-2 text-center">'
                '<div class="text-muted small">%s</div><div class="fs-4 %s">%s</div></div></div>'
            ) % (titulo, clase, _fmt(valor))

        tarjetas = (Markup('<div class="row">')
                    + tarjeta('Trabajos', t_trab)
                    + tarjeta('Pagos', t_pag)
                    + tarjeta('Se debe a operadores', se_debe, 'text-danger')
                    + tarjeta('Pagado de más', de_mas, 'text-primary')
                    + Markup('</div>'))

        # Por dueño
        filas_dueno = [
            [self._txt(d.name or sin_dueno), self._num(tr), self._num(pa), self._celda_saldo(sa)]
            for d, tr, pa, sa in sorted(por_dueno, key=lambda r: r[0].name or 'zzz')]
        tabla_dueno = self._tabla(
            'Por dueño', ['Dueño', 'Trabajos', 'Pagos', 'Saldo'], filas_dueno,
            [Markup('<td>Total</td>'), self._num(t_trab), self._num(t_pag), self._celda_saldo(t_trab - t_pag)])

        # Por operador
        ops = sorted(por_operador, key=lambda r: r[0].name or '')
        if self.solo_pendientes:
            ops = [r for r in ops if abs(r[3]) > 0.5]
        filas_op = [[self._txt(o.name), self._num(tr), self._num(pa), self._celda_saldo(sa)] for o, tr, pa, sa in ops]
        tabla_op = self._tabla(
            'Por operador', ['Operador', 'Trabajos', 'Pagos', 'Saldo'], filas_op,
            [Markup('<td>Total</td>'), self._num(sum(r[1] for r in ops)), self._num(sum(r[2] for r in ops)),
             self._celda_saldo(sum(r[3] for r in ops))])

        # Costo por finca (los pagos no tienen finca: solo trabajos, por tipo)
        por_finca = self.env['finca.labor.movimiento']._read_group(
            self._domain() + [('tipo', '!=', 'pago')], ['finca_id', 'tipo'], ['trabajos:sum'])
        fincas = {}
        for finca, tipo, trab in por_finca:
            fincas.setdefault(finca, {})[tipo] = trab
        tipos = [('contrato', 'Contrato'), ('jornal', 'Jornales'), ('maquinaria', 'Maquinaria')]
        filas_finca = [
            [self._txt(f.name or 'Sin finca')] + [self._num(v.get(t, 0.0)) for t, _n in tipos]
            + [Markup('<td class="text-end fw-bold">%s</td>') % _fmt(sum(v.values()))]
            for f, v in sorted(fincas.items(), key=lambda i: i[0].name or 'zzz')]
        totales_tipo = [sum(v.get(t, 0.0) for v in fincas.values()) for t, _n in tipos]
        tabla_finca = self._tabla(
            'Trabajos por finca', ['Finca'] + [n for _t, n in tipos] + ['Total'], filas_finca,
            [Markup('<td>Total</td>')] + [self._num(x) for x in totales_tipo] + [self._num(sum(totales_tipo))])

        # Dueño x operador, con subtotal por dueño
        detalle = self._agrupar(['dueno_id', 'operador_id'])
        filas_det = []
        for d in sorted({r[0] for r in detalle}, key=lambda p: p.name or 'zzz'):
            lineas = sorted((r for r in detalle if r[0] == d), key=lambda r: r[1].name or '')
            visibles = [r for r in lineas if not self.solo_pendientes or abs(r[4]) > 0.5]
            if not visibles:
                continue
            filas_det.append([Markup('<td colspan="4" class="table-light fw-bold">%s</td>') % (d.name or sin_dueno)])
            filas_det += [[self._txt(o.name), self._num(tr), self._num(pa), self._celda_saldo(sa)]
                          for _d, o, tr, pa, sa in visibles]
            filas_det.append([
                Markup('<td class="fst-italic">Subtotal</td>'),
                self._num(sum(r[2] for r in lineas)), self._num(sum(r[3] for r in lineas)),
                self._celda_saldo(sum(r[4] for r in lineas))])
        tabla_det = self._tabla('Dueño x operador', ['Operador', 'Trabajos', 'Pagos', 'Saldo'], filas_det)

        leyenda = Markup(
            '<p class="text-muted small mt-2">Saldo = trabajos confirmados − pagos con campaña. '
            '<span class="text-danger">Rojo</span>: se le debe al operador. '
            '<span class="text-primary">Azul</span>: se le pagó de más (anticipo por descontar).</p>')
        return (tarjetas + leyenda
                + Markup('<div class="row"><div class="col-lg-6">') + tabla_dueno + tabla_finca
                + Markup('</div><div class="col-lg-6">') + tabla_op + Markup('</div></div>')
                + tabla_det)

    # --- Acciones ------------------------------------------------------------

    def action_ver_pivote(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'finca_labores.action_finca_labor_movimiento_saldos')
        action['domain'] = self._domain()
        action['context'] = {}
        return action

    def action_ver_movimientos(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('finca_labores.action_finca_labor_movimiento')
        action['domain'] = self._domain()
        action['context'] = {'search_default_group_operador': 1}
        return action
