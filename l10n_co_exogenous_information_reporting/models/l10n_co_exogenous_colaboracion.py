# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class L10ncoExogenousColaboracionContractType(models.Model):
    _name = "l10n_co.exogenous_colaboracion_contract_type"
    _description = "Tipo de contrato de colaboración (DIAN)"
    _check_company_auto = True
    _order = "code"

    code = fields.Char(string='Código', required=True, size=2, index=True)
    name = fields.Char(string='Nombre', required=True)
    active = fields.Boolean(default=True)
    concept_5251_id = fields.Many2one('l10n_co.exogenous_concept',
        string='Concepto 5251 (saldos cobrar)',
        check_company=True,
        help='Concepto a usar al reportar saldo por cobrar para este tipo de contrato.')
    concept_5252_id = fields.Many2one('l10n_co.exogenous_concept',
        string='Concepto 5252 (saldos pagar)',
        check_company=True,
        help='Concepto a usar al reportar saldo por pagar para este tipo de contrato.')

    _uniq_code = models.Constraint(
        'UNIQUE(code)',
        'El código debe ser único')


class L10ncoExogenousColaboracionContract(models.Model):
    _name = "l10n_co.exogenous_colaboracion_contract"
    _description = "Contrato de colaboración empresarial (DIAN)"
    _order = "code"

    name = fields.Char(string='Nombre', required=True, tracking=True)
    code = fields.Char(string='Identificador fiscal (idfi)', required=True, size=14, tracking=True,
                       help='Identificador único del contrato. Va al atributo XML idfi.')
    contract_type_id = fields.Many2one(
        'l10n_co.exogenous_colaboracion_contract_type',
        string='Tipo de contrato', required=True, tracking=True,
        help='Va al atributo XML tcon.')
    contract_type_code = fields.Char(related='contract_type_id.code', store=True, readonly=True)
    operator_company_id = fields.Many2one(
        'res.company', string='Compañía operadora', required=True, tracking=True,
        default=lambda self: self.env.company,
        help='Compañía que opera el contrato y reporta la información.')
    company_id = fields.Many2one(
        related='operator_company_id', store=True, readonly=True)
    participant_ids = fields.One2many(
        'l10n_co.exogenous_colaboracion_participant',
        'contract_id', string='Partícipes')
    participant_count = fields.Integer(compute='_compute_participant_count')
    account_ids = fields.Many2many(
        'account.account',
        'l10n_co_exo_colab_contract_account_rel',
        'contract_id', 'account_id',
        string='Cuentas asociadas',
        help='Cuentas contables cuyos movimientos pertenecen a este contrato. '
             'Se usan al filtrar los apuntes para los reportes 5247-5252.')
    active = fields.Boolean(default=True)
    note = fields.Text(string='Notas')

    _uniq_code_company = models.Constraint(
        'UNIQUE(code, operator_company_id)',
        'El identificador fiscal debe ser único por compañía.')

    @api.depends('participant_ids')
    def _compute_participant_count(self):
        for c in self:
            c.participant_count = len(c.participant_ids)

    @api.constrains('participant_ids')
    def _check_participation_pct(self):
        for c in self:
            if not c.participant_ids:
                continue
            total = sum(p.participation_pct for p in c.participant_ids)
            if abs(total - 100.0) > 0.01:
                raise ValidationError(_(
                    'La suma de los porcentajes de participación de "%s" debe ser 100. Actual: %.2f'
                ) % (c.name, total))


class L10ncoExogenousColaboracionParticipant(models.Model):
    _name = "l10n_co.exogenous_colaboracion_participant"
    _description = "Partícipe de contrato de colaboración"
    _order = "contract_id, sequence, id"

    contract_id = fields.Many2one(
        'l10n_co.exogenous_colaboracion_contract',
        string='Contrato', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    partner_id = fields.Many2one(
        'res.partner', string='Partícipe', required=True,
        help='Partner del partícipe — su tipo de documento (tdopa) y NIT (nidpa) se leen de aquí.')
    participation_pct = fields.Float(
        string='% Participación', required=True, default=0.0,
        help='Porcentaje del contrato que corresponde a este partícipe. La suma de % debe ser 100.')
    is_operator = fields.Boolean(
        string='Es operador',
        help='Indica si este partícipe es el operador del contrato (puede ser la propia compañía).')
