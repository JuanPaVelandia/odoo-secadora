# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import models, fields, api
from odoo.exceptions import UserError


class ProduccionLoteWizard(models.TransientModel):
    _name = 'secadora.produccion.lote.wizard'
    _description = 'Imprimir Producción por Finca y Lote'

    finca_id = fields.Many2one(
        'secadora.lugar',
        string='Finca',
        domain=[('tipo', '=', 'finca')],
        help='Vacío = todas las fincas',
    )
    lote_ids = fields.Many2many(
        'secadora.lote',
        string='Lotes',
        domain="[('finca_id', '=?', finca_id)]",
        help='Vacío = todos los lotes de la finca',
    )
    fecha_desde = fields.Date(string='Desde')
    fecha_hasta = fields.Date(string='Hasta')
    incluir_detalle = fields.Boolean(
        string='Incluir detalle de mulas',
        default=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        default=lambda self: self.env.company,
        help='Vacío = todas las empresas',
    )

    @api.onchange('finca_id')
    def _onchange_finca_id(self):
        if self.finca_id:
            self.lote_ids = self.lote_ids.filtered(
                lambda l: l.finca_id == self.finca_id)

    def _get_domain(self):
        domain = []
        if self.finca_id:
            domain.append(('finca_id', '=', self.finca_id.id))
        if self.lote_ids:
            domain.append(('lote_id', 'in', self.lote_ids.ids))
        if self.fecha_desde:
            domain.append(('fecha', '>=', self.fecha_desde))
        if self.fecha_hasta:
            domain.append(('fecha', '<=', self.fecha_hasta))
        if self.company_id:
            domain.append(('company_id', '=', self.company_id.id))
        return domain

    def _get_grupos(self):
        """Agrupa las filas del reporte por (finca, lote) y calcula totales,
        fechas de corta y promedios ponderados por peso.

        Regla del negocio: la corta empieza un día antes de la primera mula
        y termina un día antes de la última (el arroz cortado hoy se lleva a
        la secadora al día siguiente).

        Ponderados: sum(métrica × peso) / sum(peso) SOLO sobre filas con la
        métrica medida (la vista SQL ya convierte los 0 en NULL/False).
        """
        self.ensure_one()
        rows = self.env['secadora.produccion.lote.report'].search(
            self._get_domain(), order='finca_id, lote_id, fecha')

        grupos = {}
        for row in rows:
            clave = (row.finca_id.id, row.lote_id.id)
            grupos.setdefault(clave, self.env['secadora.produccion.lote.report'])
            grupos[clave] |= row

        resultado = []
        for (finca_id, lote_id), grupo in grupos.items():
            fechas = grupo.mapped('fecha')
            total_kg = sum(grupo.mapped('peso_kg'))
            total_kg_corregido = sum(grupo.mapped('peso_kg_corregido'))
            hectareas = self._hectareas_lote(grupo[0].lote_id)
            resultado.append({
                'finca': grupo[0].finca_id,
                'lote': grupo[0].lote_id,  # vacío = pesajes viejos sin lote
                'fecha_inicio_corta': min(fechas) - timedelta(days=1),
                'fecha_fin_corta': max(fechas) - timedelta(days=1),
                'total_kg': total_kg,
                'total_kg_corregido': total_kg_corregido,
                'hectareas': hectareas,
                'produccion_ha': total_kg / hectareas if hectareas else False,
                'produccion_ha_corregida': total_kg_corregido / hectareas if hectareas else False,
                'bultos_ha': total_kg / 62.5 / hectareas if hectareas else False,
                'bultos_ha_corregido': total_kg_corregido / 62.5 / hectareas if hectareas else False,
                'total_bultos': sum(grupo.mapped('bultos')),
                'num_mulas': len(set(grupo.mapped('pesaje_id').ids)),
                'agricultores': ', '.join(sorted(set(
                    grupo.mapped('tercero_id.name')))),
                'variedades': ', '.join(sorted(set(
                    grupo.mapped('variedad_id.name')))),
                'humedad': self._ponderado(grupo, 'humedad'),
                'impurezas': self._ponderado(grupo, 'impurezas'),
                'grano_partido': self._ponderado(grupo, 'grano_partido'),
                'temperatura': self._ponderado(grupo, 'temperatura'),
                'detalle': grupo.sorted('fecha') if self.incluir_detalle else [],
            })

        resultado.sort(key=lambda g: (g['finca'].name or '', g['lote'].name or ''))
        return resultado

    @staticmethod
    def _hectareas_lote(lote):
        """Hectáreas del lote: campo del catálogo, o el nombre si es numérico
        (convención de la secadora: lote "180" = 180 ha)."""
        if not lote:
            return 0.0
        if lote.hectareas:
            return lote.hectareas
        try:
            return float((lote.name or '').strip().replace(',', '.'))
        except ValueError:
            return 0.0

    @staticmethod
    def _ponderado(grupo, campo):
        """Promedio ponderado por peso, solo sobre filas con la métrica medida.
        Retorna False si ninguna fila la tiene (el QWeb imprime N/D)."""
        filas = [r for r in grupo if r[campo] and r.peso_kg > 0]
        total_peso = sum(r.peso_kg for r in filas)
        if not total_peso:
            return False
        return sum(r[campo] * r.peso_kg for r in filas) / total_peso

    def action_imprimir(self):
        self.ensure_one()
        if not self.env['secadora.produccion.lote.report'].search_count(
                self._get_domain()):
            raise UserError(
                'No hay entradas de arroz que cumplan los filtros. '
                'Verifica la finca, los lotes y el rango de fechas.')
        return self.env.ref(
            'secadora_calidad.action_report_produccion_lote'
        ).report_action(self)
