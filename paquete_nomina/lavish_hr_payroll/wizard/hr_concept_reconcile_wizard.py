# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class HrConceptReconcileWizard(models.TransientModel):
    """Wizard para conciliar lineas de nomina con conceptos de contrato."""
    _name = 'hr.concept.reconcile.wizard'
    _description = 'Conciliar Novedades de Contrato'

    payslip_id = fields.Many2one(
        'hr.payslip',
        string='Nomina',
        required=True,
        default=lambda self: self.env.context.get('active_id') if self.env.context.get('active_model') == 'hr.payslip' else False
    )
    employee_id = fields.Many2one('hr.employee', string='Empleado', related='payslip_id.employee_id')
    contract_id = fields.Many2one('hr.contract', string='Contrato', related='payslip_id.contract_id')
    date_from = fields.Date(string='Desde', related='payslip_id.date_from')
    date_to = fields.Date(string='Hasta', related='payslip_id.date_to')

    line_ids = fields.One2many(
        'hr.concept.reconcile.line',
        'wizard_id',
        string='Lineas a Conciliar'
    )

    lines_found = fields.Integer(string='Lineas Encontradas', compute='_compute_summary')
    lines_matched = fields.Integer(string='Lineas con Coincidencia', compute='_compute_summary')

    @api.depends('line_ids', 'line_ids.concept_id')
    def _compute_summary(self):
        for rec in self:
            rec.lines_found = len(rec.line_ids)
            rec.lines_matched = len(rec.line_ids.filtered(lambda l: l.concept_id))

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self.env.context.get('active_model') == 'hr.payslip':
            payslip_id = self.env.context.get('active_id')
            if payslip_id:
                res['payslip_id'] = payslip_id
        return res

    def action_search_matches(self):
        """Busca coincidencias entre lineas de nomina y conceptos de contrato."""
        self.ensure_one()
        slip = self.payslip_id
        contract = slip.contract_id

        if not contract:
            raise UserError(_('La nomina no tiene contrato asignado.'))

        # Limpiar lineas anteriores
        self.line_ids.unlink()

        # Buscar lineas sin concept_id
        lines_without_concept = slip.line_ids.filtered(
            lambda l: not l.concept_id and l.salary_rule_id
        )

        # Obtener conceptos de contrato activos
        contract_concepts = contract.concepts_ids.filtered(
            lambda c: c.state in ('done', 'closed') and c.input_id
        )

        # Crear mapeo por codigo de regla
        concept_by_rule = {}
        for concept in contract_concepts:
            rule_code = concept.input_id.code
            if rule_code not in concept_by_rule:
                concept_by_rule[rule_code] = []
            concept_by_rule[rule_code].append(concept)

        # Crear lineas del wizard
        line_vals = []
        for line in lines_without_concept:
            rule_code = line.salary_rule_id.code

            # Buscar concepto coincidente
            matching_concept = False
            match_type = 'none'

            if rule_code in concept_by_rule:
                candidates = concept_by_rule[rule_code]

                # Intentar match exacto por monto
                for concept in candidates:
                    if abs(concept.amount - abs(line.total)) < 1:
                        matching_concept = concept.id
                        match_type = 'exact'
                        break

                # Si no hay match exacto, usar el primero por regla
                if not matching_concept and candidates:
                    matching_concept = candidates[0].id
                    match_type = 'rule'

            line_vals.append({
                'wizard_id': self.id,
                'payslip_line_id': line.id,
                'salary_rule_id': line.salary_rule_id.id,
                'rule_code': rule_code,
                'line_amount': line.total,
                'concept_id': matching_concept,
                'match_type': match_type,
                'apply_reconcile': bool(matching_concept),
            })

        if line_vals:
            self.env['hr.concept.reconcile.line'].create(line_vals)

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.concept.reconcile.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }

    def action_apply_reconcile(self):
        """Aplica la conciliacion a las lineas seleccionadas."""
        self.ensure_one()

        lines_to_apply = self.line_ids.filtered(lambda l: l.apply_reconcile and l.concept_id)

        if not lines_to_apply:
            raise UserError(_('No hay lineas seleccionadas para conciliar.'))

        updated = 0
        for line in lines_to_apply:
            line.payslip_line_id.write({
                'concept_id': line.concept_id.id,
                'object_type': 'novelty',
            })
            updated += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Conciliacion Completada'),
                'message': _('%d lineas actualizadas correctamente.') % updated,
                'type': 'success',
                'sticky': False,
            }
        }


class HrConceptReconcileLine(models.TransientModel):
    """Linea temporal para conciliacion de conceptos."""
    _name = 'hr.concept.reconcile.line'
    _description = 'Linea de Conciliacion'

    wizard_id = fields.Many2one(
        'hr.concept.reconcile.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade'
    )
    payslip_line_id = fields.Many2one(
        'hr.payslip.line',
        string='Linea de Nomina',
        required=True
    )
    salary_rule_id = fields.Many2one(
        'hr.salary.rule',
        string='Regla Salarial',
        readonly=True
    )
    rule_code = fields.Char(string='Codigo', readonly=True)
    line_amount = fields.Float(string='Monto Linea', readonly=True)

    concept_id = fields.Many2one(
        'hr.contract.concepts',
        string='Concepto Contrato',
        domain="[('contract_id', '=', parent.contract_id), ('state', 'in', ['done', 'closed'])]"
    )
    concept_amount = fields.Float(
        string='Monto Concepto',
        related='concept_id.amount',
        readonly=True
    )

    match_type = fields.Selection([
        ('none', 'Sin Coincidencia'),
        ('rule', 'Por Regla'),
        ('exact', 'Exacto'),
    ], string='Tipo Match', default='none', readonly=True)

    apply_reconcile = fields.Boolean(string='Aplicar', default=False)

    difference = fields.Float(string='Diferencia', compute='_compute_difference')

    @api.depends('line_amount', 'concept_id', 'concept_id.amount')
    def _compute_difference(self):
        for rec in self:
            if rec.concept_id:
                rec.difference = abs(rec.line_amount) - abs(rec.concept_id.amount)
            else:
                rec.difference = 0
