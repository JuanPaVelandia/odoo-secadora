# -*- coding: utf-8 -*-
from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError
from odoo.addons.l10n_co_exogenous_information_reporting.models.l10n_co_exogenous_format_field_account import (
    NATURE_ACCOUNT_SELECTION,
)

# ============================================================
# Mapa de sugerencias por concepto y atributo de columna
# Estructura: {concepto: {atributo_campo: (patrón_cuentas, fórmula_DIAN)}}
# ============================================================

SUGGESTIONS_MAP = {
    # ==================== FORMATO 1001 ====================
    '5002': {
        'pago': ('5105%, 5110%, 5115%', 'db_cr'),
        'pnded': ('5105%, 5110%, 5115%', 'db_cr'),
        'ided': ('', 'debit'),
        'retp': ('2365%', 'cr_db'),
        'reta': ('2367%', 'cr_db'),
    },
    '5003': {
        'pago': ('5135%, 5140%', 'db_cr'),
        'pnded': ('5135%, 5140%', 'db_cr'),
        'ided': ('', 'debit'),
        'retp': ('2365%', 'cr_db'),
        'reta': ('2367%', 'cr_db'),
    },
    '5004': {
        'pago': ('5120%, 5125%, 5130%, 5195%', 'db_cr'),
        'pnded': ('5120%, 5125%, 5130%, 5195%', 'db_cr'),
        'ided': ('', 'debit'),
        'retp': ('2365%', 'cr_db'),
        'reta': ('2367%', 'cr_db'),
    },
    '5005': {
        'pago': ('5120%, 5220%', 'db_cr'),
        'pnded': ('5120%, 5220%', 'db_cr'),
        'ided': ('', 'debit'),
        'retp': ('2365%', 'cr_db'),
        'reta': ('2367%', 'cr_db'),
    },
    '5006': {
        'pago': ('5305%, 5310%, 4210%, 4215%', 'db_cr'),
        'pnded': ('5305%, 5310%', 'db_cr'),
        'ided': ('', 'debit'),
        'retp': ('2365%', 'cr_db'),
        'reta': ('2367%', 'cr_db'),
    },
    '5007': {
        'pago': ('6135%, 6140%, 6145%, 6150%, 6205%', 'db_cr'),
        'pnded': ('6135%, 6140%', 'db_cr'),
        'ided': ('', 'debit'),
        'retp': ('2365%', 'cr_db'),
        'reta': ('2367%', 'cr_db'),
    },
    '5008': {
        'pago': ('1504%, 1508%, 1512%, 1516%, 1520%, 1524%', 'db_cr'),
        'pnded': ('1504%, 1508%', 'db_cr'),
        'ided': ('', 'debit'),
        'retp': ('2365%', 'cr_db'),
        'reta': ('2367%', 'cr_db'),
    },
    '5009': {
        'pago': ('7105%, 7205%', 'db_cr'),
        'pnded': ('7105%, 7205%', 'db_cr'),
        'ided': ('', 'debit'),
        'retp': ('2365%', 'cr_db'),
    },
    '5010': {
        'pago': ('5105%, 5205%, 5110%, 5210%, 7105%, 7205%', 'debit'),
    },
    '5011': {
        'pago': ('5105%, 5205%, 5110%, 5210%, 7105%, 7205%', 'debit'),
    },
    '5012': {
        'pago': ('5105%, 5205%, 5110%, 5210%, 7105%, 7205%', 'debit'),
    },
    '5013': {
        'pago': ('5160%, 5165%, 5260%', 'db_cr'),
        'pnded': ('5160%, 5165%', 'db_cr'),
        'retp': ('2365%', 'cr_db'),
    },
    '5014': {
        'pago': ('5115%, 5215%, 5245%', 'db_cr'),
        'pnded': ('5115%, 5215%', 'db_cr'),
    },
    '5015': {
        'pago': ('5195%, 5295%, 5395%', 'db_cr'),
        'pnded': ('5195%, 5295%', 'db_cr'),
        'ided': ('', 'debit'),
        'retp': ('2365%', 'cr_db'),
        'reta': ('2367%', 'cr_db'),
    },
    '5016': {
        'pago': ('2365%, 2368%, 2370%, 2404%', 'db_cr'),
    },
    '5023': {
        'pago': ('5305%, 5310%', 'db_cr'),
        'retp': ('2365%', 'cr_db'),
    },
    '5024': {
        'pago': ('5305%, 5310%', 'db_cr'),
        'retp': ('2365%', 'cr_db'),
    },
    '5025': {
        'pago': ('5305%, 5310%', 'db_cr'),
        'retp': ('2365%', 'cr_db'),
    },
    '5026': {
        'pago': ('5305%, 5310%', 'db_cr'),
        'retp': ('2365%', 'cr_db'),
    },
    '5027': {
        'pago': ('6135%, 6140%, 6145%, 6150%, 6155%', 'db_cr'),
        'pnded': ('6135%, 6140%', 'db_cr'),
        'ided': ('', 'debit'),
        'retp': ('2365%', 'cr_db'),
        'reta': ('2367%', 'cr_db'),
    },
    '5028': {
        'pago': ('5130%, 5230%', 'db_cr'),
        'retp': ('2365%', 'cr_db'),
    },
    '5029': {
        'pago': ('5140%, 5240%', 'db_cr'),
        'retp': ('2365%', 'cr_db'),
    },
    '5030': {
        'pago': ('5150%, 5250%', 'db_cr'),
        'retp': ('2365%', 'cr_db'),
    },
    '5031': {
        'pago': ('5145%, 5245%', 'db_cr'),
        'retp': ('2365%', 'cr_db'),
    },
    '5032': {
        'pago': ('5160%, 5260%', 'db_cr'),
        'retp': ('2365%', 'cr_db'),
    },
    '5033': {
        'pago': ('5155%, 5255%', 'db_cr'),
        'retp': ('2365%', 'cr_db'),
    },
    '5034': {
        'pago': ('5135%, 5235%', 'db_cr'),
        'retp': ('2365%', 'cr_db'),
    },
    '5035': {
        'pago': ('1705%, 1710%', 'db_cr'),
        'retp': ('2365%', 'cr_db'),
    },
    '5044': {
        'pago': ('5195%', 'db_cr'),
        'retp': ('2365%', 'cr_db'),
    },
    '5055': {
        'pago': ('5105%, 5205%, 7105%, 7205%', 'debit'),
        'retp': ('2365%', 'cr_db'),
    },
    '5056': {
        'pago': ('5110%, 5210%', 'db_cr'),
        'retp': ('2365%', 'cr_db'),
    },
    '5058': {
        'pago': ('5105%, 5205%, 2510%', 'debit'),
    },
    '5059': {
        'pago': ('5105%, 5205%, 5110%, 5210%', 'debit'),
    },
    '5060': {
        'pago': ('5105%, 5205%, 5110%, 5210%', 'debit'),
    },
    '5068': {
        'pago': ('2355%, 2360%', 'cr_db'),
        'retp': ('2365%', 'cr_db'),
    },
    '5069': {
        'pago': ('2355%, 2360%', 'cr_db'),
        'retp': ('2365%', 'cr_db'),
    },
    '5070': {
        'pago': ('2355%, 2360%', 'cr_db'),
        'retp': ('2365%', 'cr_db'),
    },
    '5071': {
        'pago': ('2355%, 2360%', 'cr_db'),
        'retp': ('2365%', 'cr_db'),
    },
    '5079': {
        'pago': ('5305%, 5310%', 'db_cr'),
        'retp': ('2365%', 'cr_db'),
    },
    '5080': {
        'pago': ('5120%, 5125%', 'db_cr'),
        'ided': ('', 'debit'),
        'retp': ('2365%', 'cr_db'),
        'reta': ('2367%', 'cr_db'),
    },
    '5088': {
        'pago': ('5305%, 4210%', 'db_cr'),
    },
    # ==================== FORMATO 1003 ====================
    '1301': {'ret': ('1355%, 1365%', 'db_cr'), 'valor': ('', 'tax_base_amount')},
    '1302': {'ret': ('1355%', 'db_cr'), 'valor': ('', 'tax_base_amount')},
    '1303': {'ret': ('1355%', 'db_cr'), 'valor': ('', 'tax_base_amount')},
    '1304': {'ret': ('1355%', 'db_cr'), 'valor': ('', 'tax_base_amount')},
    '1305': {'ret': ('1355%', 'db_cr'), 'valor': ('', 'tax_base_amount')},
    '1306': {'ret': ('1355%', 'db_cr'), 'valor': ('', 'tax_base_amount')},
    '1307': {'ret': ('1355%', 'db_cr'), 'valor': ('', 'tax_base_amount')},
    '1308': {'ret': ('1355%', 'db_cr'), 'valor': ('', 'tax_base_amount')},
    '1309': {'ret': ('1355%', 'db_cr'), 'valor': ('', 'tax_base_amount')},
    '1310': {'ret': ('1355%', 'db_cr'), 'valor': ('', 'tax_base_amount')},
    '1311': {'ret': ('1355%', 'db_cr'), 'valor': ('', 'tax_base_amount')},
    '1312': {'ret': ('1355%', 'db_cr'), 'valor': ('', 'tax_base_amount')},
    '1313': {'ret': ('1355%', 'db_cr'), 'valor': ('', 'tax_base_amount')},
    '1314': {'ret': ('1355%', 'db_cr'), 'valor': ('', 'tax_base_amount')},
    '1320': {'ret': ('1355%', 'db_cr'), 'valor': ('', 'tax_base_amount')},
    # ==================== FORMATO 1007 ====================
    '4001': {'valor': ('4135%, 4140%, 4145%, 4150%, 4155%, 4160%, 4170%, 4175%', 'cr_db')},
    '4002': {'valor': ('4210%, 4215%, 4220%, 4225%, 4230%, 4235%, 4240%, 4245%, 4250%', 'cr_db')},
    '4003': {'valor': ('4210%, 4215%', 'cr_db')},
    '4004': {'valor': ('4210%', 'cr_db')},
    '4014': {'valor': ('4250%, 4255%', 'cr_db')},
    '4015': {'valor': ('4210%, 4215%', 'cr_db')},
    # ==================== FORMATO 1008/1009 ====================
    '8001': {'sal': ('13%', 'db_cr')},
    '8002': {'sal': ('13%', 'db_cr')},
    '9001': {'sal': ('22%, 23%, 24%, 25%', 'cr_db')},
    '9002': {'sal': ('22%, 23%, 24%, 25%', 'cr_db')},
}

DEFAULT_NATURE_BY_ATTRIBUTE = {
    'pago': 'db_cr', 'pnded': 'db_cr',
    'ided': 'debit', 'inded': 'debit',
    'retp': 'cr_db', 'reta': 'cr_db',
    'ret': 'db_cr', 'valor': 'cr_db',
    'sal': 'db_cr', 'comun': 'db_cr',
    'ndom': 'db_cr', 'ibru': 'cr_db',
    'dred': 'db_cr', 'vdesc': 'db_cr',
}

ATTRIBUTE_LABELS = {
    'pago': 'Pago deducible',
    'pnded': 'Pago NO deducible',
    'ided': 'IVA mayor valor',
    'inded': 'IVA descontable',
    'retp': 'Ret. practicada renta',
    'reta': 'Ret. practicada IVA',
    'ret': 'Retención que le practicaron',
    'comun': 'Aporte comunero',
    'ndom': 'No domiciliado',
    'valor': 'Valor operación',
    'sal': 'Saldo dic 31',
    'ibru': 'Ingreso bruto',
    'dred': 'Deducción/Renta exenta',
    'vdesc': 'Valor descuento',
    'vimp': 'Valor impuesto',
    'ivade': 'IVA descontable',
    'imp': 'Impuesto',
    'iva': 'IVA generado',
    'icon': 'Impuesto al consumo',
    'ing': 'Ingreso tercero',
    'ppart': '% Participación',
    'vpatr': 'Valor patrimonial',
    'vded': 'Deducción víctima',
    'ide': 'Identificación declarante',
}


class L10nCoExogenousAccountConfigWizard(models.TransientModel):
    """Wizard maestro-detalle para configuración de cuentas exógenas.

    Arriba: selección de formato y concepto (navegable).
    Abajo: columnas del formato para el concepto seleccionado.
    """
    _name = 'l10n_co.exogenous_account_config_wizard'
    _description = 'Asistente de configuración de cuentas exógenas'

    # --- Cabecera ---
    format_id = fields.Many2one(
        'l10n_co.exogenous_format',
        string='Formato',
        required=True,
        help='Seleccione el formato DIAN a configurar'
    )
    apply_concepts = fields.Boolean(
        string='Usa conceptos',
        related='format_id.apply_concepts',
        readonly=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        default=lambda self: self.env.company,
        required=True
    )

    # --- Navegación de concepto ---
    concept_id = fields.Many2one(
        'l10n_co.exogenous_concept',
        string='Concepto',
        help='Seleccione el concepto a configurar'
    )
    concept_code = fields.Char(related='concept_id.code', string='Código', readonly=True)
    concept_name = fields.Text(related='concept_id.name', string='Nombre del concepto', readonly=True)
    concept_count = fields.Integer(
        string='Total conceptos',
        compute='_compute_concept_nav',
    )
    concept_index = fields.Integer(
        string='Concepto #',
        compute='_compute_concept_nav',
    )
    concept_configured = fields.Integer(
        string='Conceptos configurados',
        compute='_compute_concept_nav',
    )

    # --- Detalle: columnas del formato para el concepto seleccionado ---
    line_ids = fields.One2many(
        'l10n_co.exogenous_account_config_wizard.line',
        'wizard_id',
        string='Configuración de columnas'
    )

    # --- Resumen: todos los conceptos del formato ---
    summary_ids = fields.One2many(
        'l10n_co.exogenous_account_config_wizard.summary',
        'wizard_id',
        string='Resumen de conceptos'
    )

    # --- Opciones ---
    show_configured = fields.Boolean('Mostrar solo configurados', default=False)
    show_unconfigured = fields.Boolean('Mostrar solo sin configurar', default=True)

    @api.depends('format_id', 'concept_id')
    def _compute_concept_nav(self):
        for wiz in self:
            if not wiz.format_id:
                wiz.concept_count = 0
                wiz.concept_index = 0
                wiz.concept_configured = 0
                continue
            Concept = self.env['l10n_co.exogenous_concept']
            concepts = Concept.search([
                *Concept._check_company_domain(wiz.company_id),
                ('format_id', '=', wiz.format_id.id),
            ], order='code')
            wiz.concept_count = len(concepts)
            wiz.concept_configured = len(concepts.filtered(lambda c: c.account_count > 0))
            if wiz.concept_id and wiz.concept_id in concepts:
                wiz.concept_index = list(concepts.ids).index(wiz.concept_id.id) + 1
            else:
                wiz.concept_index = 0

    @api.onchange('format_id')
    def _onchange_format_id(self):
        """Al cambiar formato, seleccionar el primer concepto y cargar resumen"""
        self.concept_id = False
        self.line_ids = [Command.clear()]
        self.summary_ids = [Command.clear()]
        if not self.format_id:
            return

        if self.format_id.apply_concepts:
            Concept = self.env['l10n_co.exogenous_concept']
            concepts = Concept.search([
                *Concept._check_company_domain(self.company_id),
                ('format_id', '=', self.format_id.id),
            ], order='code', limit=1)
            if concepts:
                self.concept_id = concepts[0]
            self._load_summary()
        else:
            self._load_field_lines()

    @api.onchange('concept_id')
    def _onchange_concept_id(self):
        """Al cambiar concepto, cargar las columnas del formato"""
        self.line_ids = [Command.clear()]
        if not self.concept_id or not self.format_id:
            return
        self._load_concept_lines()

    def _load_concept_lines(self):
        """Carga las columnas del formato para el concepto seleccionado"""
        format_fields = self.env['l10n_co.exogenous_format_field'].search([
            ('format_ids', 'in', self.format_id.id),
            ('source', '=', 'journal_items'),
            ('format_applies_concepts', '=', True),
        ], order='sequence')

        existing_fas = {
            fa.format_field_id.id: fa
            for fa in self.concept_id.field_account_ids
            if fa.format_field_id
        }

        lines = []
        for ff in format_fields:
            fa = existing_fas.get(ff.id)
            attr = ff.attribute or ''
            default_nature = DEFAULT_NATURE_BY_ATTRIBUTE.get(attr, 'db_cr')

            lines.append(Command.create({
                'config_type': 'concept',
                'concept_id': self.concept_id.id,
                'format_field_id': ff.id,
                'field_attribute': attr,
                'field_label': ATTRIBUTE_LABELS.get(attr, ff.name or attr),
                'account_pattern': fa.account_pattern if fa else '',
                'account_ids': [Command.set(fa.account_ids.ids)] if fa else [],
                'nature_account': fa.nature_account if fa else default_nature,
            }))

        self.line_ids = lines

    def _load_field_lines(self):
        """Carga campos directos (formatos sin conceptos)"""
        format_fields = self.env['l10n_co.exogenous_format_field'].search([
            ('format_ids', 'in', self.format_id.id),
            ('source', '=', 'journal_items'),
            ('format_applies_concepts', '=', False),
        ], order='sequence')

        lines = []
        for field in format_fields:
            attr = field.attribute or ''
            lines.append(Command.create({
                'config_type': 'field',
                'concept_id': False,
                'format_field_id': field.id,
                'field_attribute': attr,
                'field_label': ATTRIBUTE_LABELS.get(attr, field.name or attr),
                'account_pattern': field.account_pattern or '',
                'account_ids': [Command.set(field.account_ids.ids)],
                'nature_account': field.nature_account or DEFAULT_NATURE_BY_ATTRIBUTE.get(attr, 'db_cr'),
            }))

        self.line_ids = lines

    def _load_summary(self):
        """Carga el resumen de todos los conceptos del formato"""
        Concept = self.env['l10n_co.exogenous_concept']
        concepts = Concept.search([
            *Concept._check_company_domain(self.company_id),
            ('format_id', '=', self.format_id.id),
        ], order='code')

        format_fields = self.env['l10n_co.exogenous_format_field'].search([
            ('format_ids', 'in', self.format_id.id),
            ('source', '=', 'journal_items'),
            ('format_applies_concepts', '=', True),
        ], order='sequence')
        total_columns = len(format_fields)

        summary = []
        for concept in concepts:
            configured = len(concept.field_account_ids.filtered(
                lambda fa: fa.account_ids
            ))
            summary.append(Command.create({
                'concept_id': concept.id,
                'code': concept.code,
                'name': concept.name[:100] if concept.name else '',
                'configured_columns': configured,
                'total_columns': total_columns,
                'account_count': concept.account_count,
            }))

        self.summary_ids = summary

    # --- Navegación ---
    def action_next_concept(self):
        """Ir al siguiente concepto"""
        self.ensure_one()
        Concept = self.env['l10n_co.exogenous_concept']
        concepts = Concept.search([
            *Concept._check_company_domain(self.company_id),
            ('format_id', '=', self.format_id.id),
        ], order='code')
        if not concepts:
            return self._reopen()

        ids_list = concepts.ids
        if self.concept_id and self.concept_id.id in ids_list:
            idx = ids_list.index(self.concept_id.id)
            next_idx = (idx + 1) % len(ids_list)
        else:
            next_idx = 0

        self.concept_id = ids_list[next_idx]
        return self._reopen()

    def action_prev_concept(self):
        """Ir al concepto anterior"""
        self.ensure_one()
        Concept = self.env['l10n_co.exogenous_concept']
        concepts = Concept.search([
            *Concept._check_company_domain(self.company_id),
            ('format_id', '=', self.format_id.id),
        ], order='code')
        if not concepts:
            return self._reopen()

        ids_list = concepts.ids
        if self.concept_id and self.concept_id.id in ids_list:
            idx = ids_list.index(self.concept_id.id)
            prev_idx = (idx - 1) % len(ids_list)
        else:
            prev_idx = len(ids_list) - 1

        self.concept_id = ids_list[prev_idx]
        return self._reopen()

    def action_goto_concept(self):
        """Navegar al concepto desde el resumen (llamado desde summary line)"""
        self.ensure_one()
        return self._reopen()

    def _reopen(self):
        """Reabre el wizard manteniendo estado"""
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # --- Acciones de configuración ---
    def action_apply_current(self):
        """Aplica la configuración del concepto actual"""
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('No hay líneas para configurar.'))

        created = 0
        updated = 0
        for line in self.line_ids:
            if line.config_type == 'concept' and line.concept_id and line.format_field_id:
                fa = line.concept_id.field_account_ids.filtered(
                    lambda x, fid=line.format_field_id.id: x.format_field_id.id == fid
                )[:1]

                if fa:
                    vals_changed = (
                        set(fa.account_ids.ids) != set(line.account_ids.ids) or
                        fa.nature_account != line.nature_account or
                        (fa.account_pattern or '') != (line.account_pattern or '')
                    )
                    if vals_changed:
                        fa.write({
                            'account_ids': [Command.set(line.account_ids.ids)],
                            'nature_account': line.nature_account,
                            'account_pattern': line.account_pattern or False,
                        })
                        updated += 1
                elif line.account_ids or line.account_pattern:
                    self.env['l10n_co.exogenous_format_field_account'].create({
                        'concept_id': line.concept_id.id,
                        'format_field_id': line.format_field_id.id,
                        'account_ids': [Command.set(line.account_ids.ids)],
                        'nature_account': line.nature_account or 'db_cr',
                        'account_pattern': line.account_pattern or False,
                        'company_id': self.company_id.id,
                    })
                    created += 1

            elif line.config_type == 'field' and line.format_field_id:
                vals_changed = (
                    set(line.format_field_id.account_ids.ids) != set(line.account_ids.ids) or
                    line.format_field_id.nature_account != line.nature_account or
                    (line.format_field_id.account_pattern or '') != (line.account_pattern or '')
                )
                if vals_changed:
                    line.format_field_id.write({
                        'account_ids': [Command.set(line.account_ids.ids)],
                        'nature_account': line.nature_account,
                        'account_pattern': line.account_pattern or False,
                    })
                    updated += 1

        # Recargar resumen
        self._load_summary()

        label = self.concept_id.code if self.concept_id else _('campos')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Concepto %s guardado') % label,
                'message': _('%d creados, %d actualizados.') % (created, updated),
                'sticky': False,
                'type': 'success',
                'next': self._reopen(),
            }
        }

    def action_apply_and_next(self):
        """Aplica la configuración y avanza al siguiente concepto"""
        self.ensure_one()
        self.action_apply_current()
        return self.action_next_concept()

    def action_suggest_current(self):
        """Sugiere patrones para el concepto actual"""
        self.ensure_one()
        if not self.concept_id:
            return self._reopen()

        code = self.concept_id.code or ''
        concept_suggestions = SUGGESTIONS_MAP.get(code, {})
        suggested = 0

        for line in self.line_ids:
            attr = line.field_attribute or ''
            suggestion = concept_suggestions.get(attr)
            if suggestion:
                pattern, nature = suggestion
                if pattern and not line.account_pattern:
                    line.account_pattern = pattern
                if nature:
                    line.nature_account = nature
                suggested += 1
            elif attr in DEFAULT_NATURE_BY_ATTRIBUTE:
                line.nature_account = DEFAULT_NATURE_BY_ATTRIBUTE[attr]

        return self._reopen()

    def action_suggest_all(self):
        """Sugiere patrones para TODOS los conceptos del formato y los aplica"""
        self.ensure_one()
        if not self.format_id:
            return self._reopen()

        Concept = self.env['l10n_co.exogenous_concept']
        concepts = Concept.search([
            *Concept._check_company_domain(self.company_id),
            ('format_id', '=', self.format_id.id),
        ], order='code')

        format_fields = self.env['l10n_co.exogenous_format_field'].search([
            ('format_ids', 'in', self.format_id.id),
            ('source', '=', 'journal_items'),
            ('format_applies_concepts', '=', True),
        ], order='sequence')

        FieldAccount = self.env['l10n_co.exogenous_format_field_account']
        total_created = 0

        for concept in concepts:
            code = concept.code or ''
            concept_suggestions = SUGGESTIONS_MAP.get(code, {})
            if not concept_suggestions:
                continue

            existing_fas = {
                fa.format_field_id.id: fa
                for fa in concept.field_account_ids
                if fa.format_field_id
            }

            for ff in format_fields:
                attr = ff.attribute or ''
                suggestion = concept_suggestions.get(attr)
                if not suggestion:
                    continue

                pattern, nature = suggestion
                fa = existing_fas.get(ff.id)

                if fa:
                    update_vals = {}
                    if pattern and not fa.account_pattern:
                        update_vals['account_pattern'] = pattern
                    if nature and fa.nature_account != nature:
                        update_vals['nature_account'] = nature
                    if update_vals:
                        fa.write(update_vals)
                elif pattern:
                    FieldAccount.create({
                        'concept_id': concept.id,
                        'format_field_id': ff.id,
                        'nature_account': nature or DEFAULT_NATURE_BY_ATTRIBUTE.get(attr, 'db_cr'),
                        'account_pattern': pattern,
                        'company_id': self.company_id.id,
                    })
                    total_created += 1

        self._load_summary()
        if self.concept_id:
            self._load_concept_lines()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Sugerencias aplicadas'),
                'message': _('%d configuraciones creadas para todos los conceptos.') % total_created,
                'sticky': False,
                'type': 'success',
                'next': self._reopen(),
            }
        }

    def action_load_patterns_current(self):
        """Carga cuentas desde patrones para el concepto actual"""
        self.ensure_one()
        loaded = 0
        for line in self.line_ids:
            if line.account_pattern:
                accounts = line._get_accounts_from_pattern()
                if accounts:
                    line.account_ids = [Command.set(accounts.ids)]
                    loaded += 1

        return self._reopen()

    def action_load_patterns_all(self):
        """Carga cuentas desde patrones para TODOS los conceptos configurados"""
        self.ensure_one()
        FieldAccount = self.env['l10n_co.exogenous_format_field_account']
        fas = FieldAccount.search([
            *FieldAccount._check_company_domain(self.company_id),
            ('concept_id.format_id', '=', self.format_id.id),
            ('account_pattern', '!=', False),
        ])

        loaded = 0
        for fa in fas:
            accounts = fa._get_accounts_from_pattern()
            if accounts:
                fa.account_ids = [Command.set(accounts.ids)]
                loaded += 1

        self._load_summary()
        if self.concept_id:
            self._load_concept_lines()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Cuentas cargadas'),
                'message': _('Cuentas resueltas para %d columnas con patrón.') % loaded,
                'sticky': False,
                'type': 'success',
                'next': self._reopen(),
            }
        }


class L10nCoExogenousAccountConfigWizardLine(models.TransientModel):
    """Línea del wizard: una columna del formato para un concepto"""
    _name = 'l10n_co.exogenous_account_config_wizard.line'
    _description = 'Columna de configuración de cuentas exógenas'

    wizard_id = fields.Many2one(
        'l10n_co.exogenous_account_config_wizard',
        string='Asistente',
        required=True,
        ondelete='cascade'
    )
    config_type = fields.Selection([
        ('concept', 'Concepto'),
        ('field', 'Campo')
    ], string='Tipo', default='concept')

    concept_id = fields.Many2one('l10n_co.exogenous_concept', string='Concepto')
    format_field_id = fields.Many2one('l10n_co.exogenous_format_field', string='Campo de formato')

    field_attribute = fields.Char(string='Atributo', readonly=True)
    field_label = fields.Char(string='Columna', readonly=True)

    account_pattern = fields.Char(
        string='Patrón de cuentas',
        help='Patrones separados por coma. Ej: 5105%, 5110%'
    )
    account_ids = fields.Many2many(
        'account.account',
        'l10n_co_exogenous_config_wizard_account_rel',
        'line_id',
        'account_id',
        string='Cuentas'
    )
    nature_account = fields.Selection(
        selection=NATURE_ACCOUNT_SELECTION,
        string='Fórmula DIAN',
        default='db_cr'
    )
    account_count = fields.Integer(
        string='No. Cuentas',
        compute='_compute_account_count'
    )

    @api.depends('account_ids')
    def _compute_account_count(self):
        for line in self:
            line.account_count = len(line.account_ids)

    @api.onchange('account_pattern')
    def _onchange_account_pattern(self):
        if self.account_pattern:
            accounts = self._get_accounts_from_pattern()
            if accounts:
                self.account_ids = [Command.set(accounts.ids)]

    def _get_accounts_from_pattern(self):
        self.ensure_one()
        if not self.account_pattern:
            return self.env['account.account']

        patterns = [p.strip() for p in self.account_pattern.split(',') if p.strip()]
        if not patterns:
            return self.env['account.account']

        company = self.wizard_id.company_id or self.env.company
        Account = self.env['account.account']
        domain = [*Account._check_company_domain(company)]
        pattern_domain = []

        for pattern in patterns:
            if '%' in pattern:
                pattern_domain.append(('code', '=like', pattern))
            else:
                pattern_domain.append(('code', '=', pattern))

        if len(pattern_domain) == 1:
            domain.append(pattern_domain[0])
        elif len(pattern_domain) > 1:
            or_domain = ['|'] * (len(pattern_domain) - 1)
            domain = domain + or_domain + pattern_domain

        return Account.search(domain, order='code')


class L10nCoExogenousAccountConfigWizardSummary(models.TransientModel):
    """Resumen de conceptos en el wizard"""
    _name = 'l10n_co.exogenous_account_config_wizard.summary'
    _description = 'Resumen de concepto en asistente de configuración'

    wizard_id = fields.Many2one(
        'l10n_co.exogenous_account_config_wizard',
        string='Asistente',
        required=True,
        ondelete='cascade'
    )
    concept_id = fields.Many2one('l10n_co.exogenous_concept', string='Concepto')
    code = fields.Char(string='Código', readonly=True)
    name = fields.Char(string='Nombre', readonly=True)
    configured_columns = fields.Integer(string='Columnas config.', readonly=True)
    total_columns = fields.Integer(string='Total columnas', readonly=True)
    account_count = fields.Integer(string='No. Cuentas', readonly=True)
