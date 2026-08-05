# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError, ValidationError
from odoo.addons.l10n_co_exogenous_information_reporting.models.l10n_co_exogenous_format_field_account import (
    NATURE_ACCOUNT_SELECTION, NATURE_ACCOUNT_HELP,
)

_logger = logging.getLogger(__name__)


class L10nCoExogenousConceptPlanWizard(models.TransientModel):
    """Wizard para plan jerárquico de conceptos-cuentas.

    Muestra el árbol completo de un formato:
      Formato → Conceptos → Columnas → Cuentas
    con panel lateral para editar dominio y exclusiones por nodo.
    """
    _name = 'l10n_co.exogenous_concept_plan_wizard'
    _description = 'Plan de configuración de conceptos'

    format_id = fields.Many2one(
        'l10n_co.exogenous_format',
        string='Formato',
        required=True)
    format_setting_id = fields.Many2one(
        'l10n_co.exogenous_format_setting',
        string='Configuración asociada',
        help='Si se selecciona, permite sincronizar parámetros con el setting')
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        default=lambda self: self.env.company,
        required=True)
    apply_concepts = fields.Boolean(
        related='format_id.apply_concepts',
        readonly=True)

    # Árbol jerárquico
    tree_line_ids = fields.One2many(
        'l10n_co.exogenous_concept_plan_wizard.tree',
        'wizard_id',
        string='Árbol de configuración')

    # Panel de detalle (nodo seleccionado)
    selected_concept_id = fields.Many2one(
        'l10n_co.exogenous_concept',
        string='Concepto seleccionado')
    selected_field_id = fields.Many2one(
        'l10n_co.exogenous_format_field',
        string='Columna seleccionada')
    selected_account_pattern = fields.Char(string='Patrón de cuentas')
    selected_nature = fields.Selection(
        selection=NATURE_ACCOUNT_SELECTION,
        string='Fórmula DIAN')
    selected_custom_domain = fields.Text(
        string='Dominio personalizado',
        help='Dominio Odoo para filtrar account.move.line de este concepto')
    selected_account_count = fields.Integer(
        string='Cuentas cargadas', readonly=True)
    selected_corte = fields.Selection([
        ('year_movement', 'Movimiento del año'),
        ('final_balance', 'Saldo final'),
    ], string='Corte')
    selected_line_tax_filter = fields.Selection([
        ('all', 'Todas las líneas'),
        ('tax_lines_only', 'Solo líneas de impuesto'),
        ('base_lines_only', 'Solo líneas base'),
    ], string='Filtro impuesto', default='all')

    # Exclusiones por nodo
    exclude_partner_ids = fields.Many2many(
        'res.partner',
        'l10n_co_concept_plan_partner_rel',
        'wizard_id', 'partner_id',
        string='Excluir terceros')
    exclude_journal_ids = fields.Many2many(
        'account.journal',
        'l10n_co_concept_plan_journal_rel',
        'wizard_id', 'journal_id',
        string='Excluir diarios')
    exclude_move_type = fields.Selection([
        ('all', 'Todos'),
        ('entry', 'Asientos contables'),
        ('out_invoice', 'Facturas de venta'),
        ('in_invoice', 'Facturas de compra'),
        ('out_refund', 'Notas crédito venta'),
        ('in_refund', 'Notas crédito compra'),
    ], string='Tipo de movimiento', default='all')

    # Totales
    total_concepts = fields.Integer(string='Total conceptos', readonly=True)
    total_columns = fields.Integer(string='Total columnas', readonly=True)
    total_accounts = fields.Integer(string='Total cuentas', readonly=True)
    total_configured = fields.Integer(string='Configurados', readonly=True)

    @api.onchange('format_id')
    def _onchange_format_id(self):
        """Al cambiar formato, reconstruye el árbol"""
        if self.format_id:
            self._build_tree()

    def action_build_tree(self):
        """Botón para reconstruir el árbol"""
        self.ensure_one()
        self._build_tree()
        return self._reload()

    def _build_tree(self):
        """Construye el árbol jerárquico Formato → Concepto → Columna → Cuentas"""
        self.tree_line_ids = [Command.clear()]

        if not self.format_id:
            return

        lines = []
        seq = 0
        total_concepts = 0
        total_columns = 0
        total_accounts = 0
        total_configured = 0

        if self.format_id.apply_concepts:
            Concept = self.env['l10n_co.exogenous_concept']
            concepts = Concept.search([
                *Concept._check_company_domain(self.company_id),
                ('format_id', '=', self.format_id.id),
                ('active', '=', True),
            ], order='code')

            format_fields = self.env['l10n_co.exogenous_format_field'].search([
                ('format_ids', 'in', self.format_id.id),
                ('source', '=', 'journal_items'),
            ], order='sequence')

            for concept in concepts:
                total_concepts += 1
                seq += 1
                concept_has_config = False

                # Nodo concepto
                lines.append(Command.create({
                    'sequence': seq,
                    'level': 0,
                    'node_type': 'concept',
                    'concept_id': concept.id,
                    'display_name_computed': f'[{concept.code}] {concept.name or ""}',
                    'icon': '▸',
                }))

                for field in format_fields:
                    total_columns += 1
                    seq += 1

                    # Buscar configuración existente
                    field_account = concept.field_account_ids.filtered(
                        lambda fa: fa.format_field_id.id == field.id)

                    accounts = field_account[0].account_ids if field_account else self.env['account.account']
                    nature = field_account[0].nature_account if field_account else 'db_cr'
                    pattern = field_account[0].account_pattern if field_account and hasattr(field_account[0], 'account_pattern') else ''
                    acc_count = len(accounts)
                    total_accounts += acc_count

                    has_config = acc_count > 0
                    if has_config:
                        concept_has_config = True
                        total_configured += 1

                    status = 'configured' if has_config else 'empty'

                    lines.append(Command.create({
                        'sequence': seq,
                        'level': 1,
                        'node_type': 'column',
                        'concept_id': concept.id,
                        'format_field_id': field.id,
                        'display_name_computed': f'  └ {field.name}',
                        'nature_display': nature,
                        'account_pattern_display': pattern or '',
                        'account_count_display': acc_count,
                        'status': status,
                        'icon': '●' if has_config else '○',
                    }))

                # Actualizar ícono del concepto padre si tiene config
                if concept_has_config and lines:
                    for i in range(len(lines) - 1, -1, -1):
                        if lines[i][2].get('concept_id') == concept.id and lines[i][2].get('node_type') == 'concept':
                            lines[i][2]['icon'] = '▾'
                            break

        else:
            # Formato sin conceptos → solo columnas
            format_fields = self.env['l10n_co.exogenous_format_field'].search([
                ('format_ids', 'in', self.format_id.id),
                ('source', '=', 'journal_items'),
            ], order='sequence')

            for field in format_fields:
                total_columns += 1
                seq += 1
                acc_count = len(field.account_ids)
                total_accounts += acc_count
                if acc_count > 0:
                    total_configured += 1

                lines.append(Command.create({
                    'sequence': seq,
                    'level': 0,
                    'node_type': 'column',
                    'format_field_id': field.id,
                    'display_name_computed': f'{field.name}',
                    'nature_display': field.nature_account or 'db_cr',
                    'account_pattern_display': field.account_pattern or '',
                    'account_count_display': acc_count,
                    'status': 'configured' if acc_count > 0 else 'empty',
                    'icon': '●' if acc_count > 0 else '○',
                }))

        self.write({
            'tree_line_ids': lines,
            'total_concepts': total_concepts,
            'total_columns': total_columns,
            'total_accounts': total_accounts,
            'total_configured': total_configured,
        })

    def action_select_node(self):
        """Carga el detalle del nodo seleccionado en el panel lateral"""
        self.ensure_one()
        # Se invoca desde el cliente OWL con el tree_line_id seleccionado
        return self._reload()

    def action_apply_node_config(self):
        """Aplica la configuración del panel al nodo seleccionado"""
        self.ensure_one()

        if not self.selected_concept_id or not self.selected_field_id:
            raise UserError(_('Seleccione un concepto y una columna primero'))

        concept = self.selected_concept_id
        field = self.selected_field_id

        # Buscar o crear field_account
        field_account = concept.field_account_ids.filtered(
            lambda fa: fa.format_field_id.id == field.id)

        vals = {
            'nature_account': self.selected_nature or 'db_cr',
        }

        if self.selected_account_pattern:
            vals['account_pattern'] = self.selected_account_pattern

        if field_account:
            field_account[0].write(vals)
        else:
            vals.update({
                'concept_id': concept.id,
                'format_field_id': field.id,
            })
            self.env['l10n_co.exogenous_format_field_account'].create(vals)

        # Sincronizar con setting_line si existe
        if self.format_setting_id:
            self._sync_to_setting_line(concept, field)

        self._build_tree()
        return self._reload()

    def _sync_to_setting_line(self, concept, field):
        """Sincroniza la config del plan con la setting_line correspondiente"""
        if not self.format_setting_id:
            return

        setting = self.format_setting_id
        existing = setting.format_setting_line_ids.filtered(
            lambda sl: sl.concept_id.id == concept.id and sl.format_field_id.id == field.id)

        sync_vals = {}
        if self.selected_nature:
            sync_vals['nature_account'] = self.selected_nature
        if self.exclude_move_type and self.exclude_move_type != 'all':
            sync_vals['move_type_filter'] = self.exclude_move_type
        if self.selected_custom_domain:
            sync_vals['custom_line_domain'] = self.selected_custom_domain

        if existing and sync_vals:
            existing[0].write(sync_vals)
        elif not existing:
            # Crear nueva setting_line
            create_vals = {
                'format_setting_id': setting.id,
                'concept_id': concept.id,
                'format_field_id': field.id,
            }
            create_vals.update(sync_vals)
            self.env['l10n_co.exogenous_format_setting_line'].create(create_vals)

    def action_test_domain(self):
        """Prueba el dominio personalizado del nodo seleccionado"""
        self.ensure_one()
        if not self.selected_custom_domain:
            return self._show_notification(
                _('Sin dominio'), _('Escriba un dominio para probar'), 'warning')

        try:
            domain = eval(self.selected_custom_domain, {"__builtins__": {}})
            if not isinstance(domain, list):
                raise ValidationError(_('El dominio debe ser una lista'))

            AML = self.env['account.move.line']
            base_domain = [
                *AML._check_company_domain(self.company_id),
                ('parent_state', '=', 'posted'),
            ]
            count = AML.search_count(base_domain + domain)

            return self._show_notification(
                _('Dominio válido'),
                _('El dominio encontraría %d líneas de asiento') % count,
                'success')
        except Exception as e:
            return self._show_notification(
                _('Error en dominio'), str(e), 'danger')

    def action_suggest_all_patterns(self):
        """Sugiere patrones para todos los conceptos del formato"""
        self.ensure_one()
        from odoo.addons.l10n_co_exogenous_information_reporting.wizard.l10n_co_exogenous_account_config_wizard import (
            SUGGESTIONS_MAP, DEFAULT_NATURE_BY_ATTRIBUTE,
        )

        applied = 0
        Concept = self.env['l10n_co.exogenous_concept']
        concepts = Concept.search([
            *Concept._check_company_domain(self.company_id),
            ('format_id', '=', self.format_id.id),
            ('active', '=', True),
        ])

        format_fields = self.env['l10n_co.exogenous_format_field'].search([
            ('format_ids', 'in', self.format_id.id),
            ('source', '=', 'journal_items'),
        ])

        for concept in concepts:
            suggestions = SUGGESTIONS_MAP.get(concept.code, {})
            if not suggestions:
                continue

            for field in format_fields:
                attr = field.attribute or ''
                if attr not in suggestions:
                    continue

                pattern, nature = suggestions[attr]

                # Buscar o crear field_account
                field_account = concept.field_account_ids.filtered(
                    lambda fa: fa.format_field_id.id == field.id)

                vals = {'nature_account': nature}
                if pattern:
                    vals['account_pattern'] = pattern

                if field_account:
                    if not field_account[0].account_pattern:
                        field_account[0].write(vals)
                        applied += 1
                else:
                    vals.update({
                        'concept_id': concept.id,
                        'format_field_id': field.id,
                    })
                    self.env['l10n_co.exogenous_format_field_account'].create(vals)
                    applied += 1

        self._build_tree()
        return self._show_notification(
            _('Sugerencias aplicadas'),
            _('%d configuraciones sugeridas') % applied,
            'success')

    def action_load_all_patterns(self):
        """Carga cuentas desde patrones para todos los conceptos"""
        self.ensure_one()
        loaded = 0

        Concept = self.env['l10n_co.exogenous_concept']
        concepts = Concept.search([
            *Concept._check_company_domain(self.company_id),
            ('format_id', '=', self.format_id.id),
            ('active', '=', True),
        ])

        for concept in concepts:
            for fa in concept.field_account_ids:
                if fa.account_pattern and not fa.account_ids:
                    fa.action_load_accounts_from_pattern()
                    loaded += len(fa.account_ids)

        self._build_tree()
        return self._show_notification(
            _('Cuentas cargadas'),
            _('%d cuentas cargadas desde patrones') % loaded,
            'success')

    def action_sync_all_to_setting(self):
        """Sincroniza todo el plan con el format_setting asociado"""
        self.ensure_one()
        if not self.format_setting_id:
            raise UserError(_('Seleccione una configuración de formato asociada'))

        setting = self.format_setting_id
        synced = 0

        Concept = self.env['l10n_co.exogenous_concept']
        concepts = Concept.search([
            *Concept._check_company_domain(self.company_id),
            ('format_id', '=', self.format_id.id),
            ('active', '=', True),
        ])

        format_fields = self.env['l10n_co.exogenous_format_field'].search([
            ('format_ids', 'in', self.format_id.id),
            ('source', '=', 'journal_items'),
        ])

        for concept in concepts:
            for field in format_fields:
                existing = setting.format_setting_line_ids.filtered(
                    lambda sl: sl.concept_id.id == concept.id and sl.format_field_id.id == field.id)

                if not existing:
                    self.env['l10n_co.exogenous_format_setting_line'].create({
                        'format_setting_id': setting.id,
                        'concept_id': concept.id,
                        'format_field_id': field.id,
                    })
                    synced += 1

        return self._show_notification(
            _('Sincronización completada'),
            _('%d líneas creadas en la configuración') % synced,
            'success')

    def _reload(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Plan de conceptos - %s') % (self.format_id.code if self.format_id else ''),
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': {'dialog_size': 'extra-large'},
        }

    def _show_notification(self, title, message, ntype='info'):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title, 'message': message,
                'type': ntype, 'sticky': ntype == 'danger',
            }
        }


class L10nCoExogenousConceptPlanTree(models.TransientModel):
    """Línea del árbol jerárquico del plan"""
    _name = 'l10n_co.exogenous_concept_plan_wizard.tree'
    _description = 'Nodo del árbol de conceptos'
    _order = 'sequence'

    wizard_id = fields.Many2one(
        'l10n_co.exogenous_concept_plan_wizard',
        required=True, ondelete='cascade')
    sequence = fields.Integer(string='Seq.')
    level = fields.Integer(string='Nivel', default=0)
    node_type = fields.Selection([
        ('concept', 'Concepto'),
        ('column', 'Columna'),
    ], string='Tipo')
    concept_id = fields.Many2one(
        'l10n_co.exogenous_concept', string='Concepto')
    format_field_id = fields.Many2one(
        'l10n_co.exogenous_format_field', string='Columna')
    display_name_computed = fields.Char(string='Nombre')
    icon = fields.Char(string='Icono')
    nature_display = fields.Char(string='Fórmula')
    account_pattern_display = fields.Char(string='Patrón')
    account_count_display = fields.Integer(string='# Ctas')
    status = fields.Selection([
        ('configured', 'Configurado'),
        ('empty', 'Sin configurar'),
    ], string='Estado')
