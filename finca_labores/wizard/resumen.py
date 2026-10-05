# -*- coding: utf-8 -*-

from markupsafe import Markup

from odoo import models, fields, api


def _fmt(valor):
    return '{:,.0f}'.format(valor or 0).replace(',', '.')


class FincaResumen(models.TransientModel):
    """Tablero de saldos, al estilo de la pestaña "Resumen total" de la hoja:
    por dueño, por operador, dueño x operador y costo por finca, todo en una
    pantalla. Se arma en el servidor (HTML) y se recalcula al cambiar los
    filtros.

    La pantalla va de lo general a lo particular: totales arriba, a la
    izquierda los resúmenes (dueño, finca, operador) y a la derecha el cruce
    dueño x operador, que es la tabla larga."""
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
        help='Vacío: todos. Solo aparecen los contactos con alguna labor confirmada.')
    solo_pendientes = fields.Boolean(
        string='Ocultar saldos en cero', default=True,
        help='Oculta los operadores con saldo cero en las tablas por operador y dueño x operador.')
    resumen_html = fields.Html(compute='_compute_resumen_html', sanitize=False)

    @api.depends('campana_id')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = 'Resumen de saldos %s' % (rec.campana_id.name or '')

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

    # --- Piezas del HTML -----------------------------------------------------

    @staticmethod
    def _txt(texto, clase=''):
        return Markup('<td class="%s">%s</td>') % (clase, texto)

    @staticmethod
    def _num(valor, clase=''):
        return Markup('<td class="text-end %s">%s</td>') % (clase, _fmt(valor))

    @staticmethod
    def _saldo(saldo, clase=''):
        # Positivo: se le debe al operador. Negativo: se le pagó de más.
        color = 'text-danger' if saldo > 0.5 else ('text-primary' if saldo < -0.5 else 'text-muted')
        return Markup('<td class="text-end %s %s">%s</td>') % (color, clase, _fmt(saldo))

    @staticmethod
    def _tabla(encabezados, filas, total=None):
        """Tabla con la primera columna de texto y las demás numéricas, todas
        del mismo ancho para que las cifras queden alineadas entre tablas.
        filas y total: listas de celdas ya armadas (<td>...</td>)."""
        ancho = 60.0 / (len(encabezados) - 1)
        columnas = Markup('<col style="width: 40%"/>') + Markup('').join(
            Markup('<col style="width: %s%%"/>') % ancho for _h in encabezados[1:])
        cabeza = Markup('').join(
            Markup('<th class="text-muted fw-normal small text-uppercase %s">%s</th>')
            % ('text-end' if i else '', h) for i, h in enumerate(encabezados))
        cuerpo = Markup('').join(Markup('<tr>') + Markup('').join(fila) + Markup('</tr>') for fila in filas)
        if not filas:
            cuerpo = Markup('<tr><td colspan="%s" class="text-muted text-center py-3">Sin movimientos</td></tr>'
                            ) % len(encabezados)
        pie = (Markup('<tfoot><tr class="fw-bold" style="border-top: 2px solid var(--bs-gray-500, #adb5bd);">')
               + Markup('').join(total) + Markup('</tr></tfoot>') if total and filas else Markup(''))
        return (Markup('<table class="table table-sm table-hover align-middle mb-0"><colgroup>') + columnas
                + Markup('</colgroup><thead><tr>') + cabeza + Markup('</tr></thead><tbody>') + cuerpo
                + Markup('</tbody>') + pie + Markup('</table>'))

    @staticmethod
    def _panel(titulo, tabla, nota=''):
        nota = Markup('<span class="text-muted small fw-normal ms-2">%s</span>') % nota if nota else Markup('')
        return (Markup('<div class="card mb-3"><div class="card-header py-2 fw-bold">%s') % titulo + nota
                + Markup('</div><div class="card-body px-3 pt-1 pb-2">') + tabla + Markup('</div></div>'))

    @staticmethod
    def _tarjeta(titulo, valor, detalle, color=''):
        # Franja de color a la izquierda; con las clases border-* de Bootstrap
        # se engrosa el borde completo de la tarjeta.
        borde = 'border-left: 4px solid var(--bs-%s);' % color if color else ''
        texto = 'text-%s' % color if color else ''
        return Markup(
            '<div class="col-6 col-lg-3"><div class="card h-100" style="%s"><div class="card-body py-3">'
            '<div class="text-muted small text-uppercase">%s</div>'
            '<div class="fs-2 fw-bold %s">$ %s</div>'
            '<div class="text-muted small">%s</div>'
            '</div></div></div>') % (borde, titulo, texto, _fmt(valor), detalle)

    def _aviso_borradores(self):
        """Lo que está en borrador no entra al resumen: se avisa para que un
        resumen en cero no parezca un error."""
        if self.operador_id:
            return Markup('')
        domain = [('campana_id', '=', self.campana_id.id), ('state', '=', 'borrador')]
        if self.dueno_id:
            domain.append(('dueno_id', '=', self.dueno_id.id))
        partes = []
        for modelo, uno, varios in (
            ('finca.contrato', 'labor por contrato', 'labores por contrato'),
            ('finca.jornal', 'jornal', 'jornales'),
            ('finca.maquinaria.trabajo', 'trabajo de maquinaria', 'trabajos de maquinaria'),
        ):
            cantidad = self.env[modelo].search_count(domain)
            if cantidad:
                partes.append('%s %s' % (cantidad, uno if cantidad == 1 else varios))
        if not partes:
            return Markup('')
        return Markup(
            '<div class="alert alert-warning py-2 mb-3" role="alert">'
            '<strong>En borrador, sin contar:</strong> %s. Entran al resumen al confirmarlos.</div>'
        ) % ', '.join(partes)

    def _plural(self, cantidad, uno, varios):
        return '%s %s' % (cantidad, uno if cantidad == 1 else varios)

    # --- Secciones -------------------------------------------------------------

    def _seccion_tarjetas(self, por_dueno, por_operador):
        deben = [r[3] for r in por_operador if r[3] > 0.5]
        de_mas = [-r[3] for r in por_operador if r[3] < -0.5]
        return (Markup('<div class="row g-3 mb-3">')
                + self._tarjeta('Trabajos', sum(r[1] for r in por_dueno), 'labores, jornales y maquinaria confirmados')
                + self._tarjeta('Pagos', sum(r[2] for r in por_dueno), 'pagos de contabilidad con campaña')
                + self._tarjeta('Se debe a operadores', sum(deben),
                                'a ' + self._plural(len(deben), 'operador', 'operadores'), 'danger')
                + self._tarjeta('Pagado de más', sum(de_mas),
                                self._plural(len(de_mas), 'operador', 'operadores') + ' con anticipo por descontar',
                                'primary')
                + Markup('</div>'))

    def _seccion_dueno(self, por_dueno):
        filas = [
            [self._txt(d.name or 'Sin dueño'), self._num(tr), self._num(pa), self._saldo(sa)]
            for d, tr, pa, sa in sorted(por_dueno, key=lambda r: r[0].name or 'zzz')]
        total = [self._txt('Total'), self._num(sum(r[1] for r in por_dueno)),
                 self._num(sum(r[2] for r in por_dueno)), self._saldo(sum(r[3] for r in por_dueno))]
        return self._panel('Por dueño', self._tabla(['Dueño', 'Trabajos', 'Pagos', 'Saldo'], filas, total))

    def _seccion_finca(self):
        # Los pagos no tienen finca: solo trabajos, por tipo.
        por_finca = self.env['finca.labor.movimiento']._read_group(
            self._domain() + [('tipo', '!=', 'pago')], ['finca_id', 'tipo'], ['trabajos:sum'])
        fincas = {}
        for finca, tipo, trabajos in por_finca:
            fincas.setdefault(finca, {})[tipo] = trabajos
        tipos = [('contrato', 'Contrato'), ('jornal', 'Jornales'), ('maquinaria', 'Maquinaria')]
        filas = [
            [self._txt(f.name or 'Sin finca')] + [self._num(v.get(t, 0.0)) for t, _n in tipos]
            + [self._num(sum(v.values()), 'fw-bold')]
            for f, v in sorted(fincas.items(), key=lambda i: i[0].name or 'zzz')]
        totales = [sum(v.get(t, 0.0) for v in fincas.values()) for t, _n in tipos]
        total = [self._txt('Total')] + [self._num(x) for x in totales] + [self._num(sum(totales))]
        return self._panel(
            'Trabajos por finca',
            self._tabla(['Finca'] + [n for _t, n in tipos] + ['Total'], filas, total),
            'sin pagos: no tienen finca')

    def _seccion_operador(self, por_operador):
        todos = sorted(por_operador, key=lambda r: r[0].name or '')
        visibles = [r for r in todos if not self.solo_pendientes or abs(r[3]) > 0.5]
        filas = [[self._txt(o.name), self._num(tr), self._num(pa), self._saldo(sa)] for o, tr, pa, sa in visibles]
        # El total es el de todos, para que coincida con las tarjetas aunque
        # se oculten los que están al día.
        total = [self._txt('Total'), self._num(sum(r[1] for r in todos)),
                 self._num(sum(r[2] for r in todos)), self._saldo(sum(r[3] for r in todos))]
        ocultos = len(todos) - len(visibles)
        nota = '%s al día, %s' % (ocultos, 'oculto' if ocultos == 1 else 'ocultos') if ocultos else ''
        return self._panel('Por operador', self._tabla(['Operador', 'Trabajos', 'Pagos', 'Saldo'], filas, total), nota)

    def _seccion_detalle(self):
        """Dueño x operador: una fila por dueño con su subtotal y debajo sus
        operadores."""
        detalle = self._agrupar(['dueno_id', 'operador_id'])
        filas = []
        for dueno in sorted({r[0] for r in detalle}, key=lambda p: p.name or 'zzz'):
            lineas = sorted((r for r in detalle if r[0] == dueno), key=lambda r: r[1].name or '')
            filas.append([
                self._txt(dueno.name or 'Sin dueño', 'fw-bold table-light'),
                self._num(sum(r[2] for r in lineas), 'fw-bold table-light'),
                self._num(sum(r[3] for r in lineas), 'fw-bold table-light'),
                self._saldo(sum(r[4] for r in lineas), 'fw-bold table-light')])
            filas += [[self._txt(o.name, 'ps-4'), self._num(tr), self._num(pa), self._saldo(sa)]
                      for _d, o, tr, pa, sa in lineas if not self.solo_pendientes or abs(sa) > 0.5]
        return self._panel(
            'Dueño x operador', self._tabla(['Dueño / operador', 'Trabajos', 'Pagos', 'Saldo'], filas),
            'la fila del dueño es su subtotal')

    def _render(self):
        self.ensure_one()
        aviso = self._aviso_borradores()
        por_dueno = self._agrupar(['dueno_id'])
        if not por_dueno:
            return aviso + Markup(
                '<div class="text-center text-muted py-5">'
                '<div class="fs-4">Sin movimientos</div>'
                '<div>No hay labores confirmadas ni pagos con campaña para estos filtros.</div></div>')
        por_operador = self._agrupar(['operador_id'])
        columna = Markup('<div class="col-12 col-lg-6">%s</div>')
        return (
            aviso
            + self._seccion_tarjetas(por_dueno, por_operador)
            + Markup('<div class="row g-3">')
            + columna % (self._seccion_dueno(por_dueno) + self._seccion_finca()
                         + self._seccion_operador(por_operador))
            + columna % self._seccion_detalle()
            + Markup('</div>')
            + Markup(
                '<p class="text-muted small mb-0">Saldo = trabajos confirmados − pagos con campaña. '
                '<span class="text-danger">Rojo</span>: se le debe al operador. '
                '<span class="text-primary">Azul</span>: se le pagó de más (anticipo por descontar).</p>'))

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
