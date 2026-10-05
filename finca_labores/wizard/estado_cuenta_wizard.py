# -*- coding: utf-8 -*-

from odoo import models, fields


class FincaEstadoCuentaWizard(models.TransientModel):
    _name = 'finca.estado.cuenta.wizard'
    _description = 'Estado de Cuenta de Operador'

    campana_id = fields.Many2one(
        'finca.campana',
        string='Campaña',
        required=True,
        default=lambda self: self.env['finca.campana']._get_campana(),
    )
    operador_id = fields.Many2one(
        'res.partner',
        string='Operador',
        required=True,
        domain=[('es_operador_finca', '=', True)],
    )
    dueno_id = fields.Many2one(
        'res.partner',
        string='Dueño',
        help='Vacío para ver todos los dueños.',
    )

    def _domain(self):
        domain = [
            ('campana_id', '=', self.campana_id.id),
            ('operador_id', '=', self.operador_id.id),
        ]
        if self.dueno_id:
            domain.append(('dueno_id', '=', self.dueno_id.id))
        return domain

    def _get_movimientos(self):
        """Movimientos agrupados por dueño: [(dueno, movimientos), ...]."""
        self.ensure_one()
        movimientos = self.env['finca.labor.movimiento'].search(self._domain(), order='fecha, id')
        grupos = {}
        for mov in movimientos:
            grupos.setdefault(mov.dueno_id, self.env['finca.labor.movimiento'])
            grupos[mov.dueno_id] |= mov
        # Los pagos sin dueño quedan al final, en su propio grupo.
        return sorted(grupos.items(), key=lambda g: (not g[0], g[0].name or ''))

    def action_imprimir(self):
        return self.env.ref('finca_labores.action_report_estado_cuenta').report_action(self)

    def action_ver(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Movimientos de %s' % self.operador_id.name,
            'res_model': 'finca.labor.movimiento',
            'view_mode': 'list,pivot',
            'domain': self._domain(),
            'context': {'group_by': ['dueno_id']},
        }
