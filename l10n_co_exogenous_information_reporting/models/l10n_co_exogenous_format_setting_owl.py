# -*- coding: utf-8 -*-
"""
Métodos RPC para las vistas OWL de exógena.
Se invoca desde los componentes JavaScript del frontend.
"""
import base64
import io
import logging

from odoo import api, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class L10ncoExogenousFormatSettingOwl(models.Model):
    _inherit = 'l10n_co.exogenous_format_setting'

    # =====================================================
    # VISTA 1: Dashboard de Terceros
    # =====================================================

    @api.model
    def action_analyze_partners_owl(self, setting_id):
        """Analiza terceros involucrados y sus datos faltantes para la vista OWL.

        Usa applies_to_company / applies_to_contact para diferenciar
        qué campos aplican a empresas vs personas naturales.
        Siempre valida ciudad, departamento y país.
        """
        setting = self.browse(setting_id)
        if not setting.exists():
            raise UserError(_("Configuración no encontrada"))

        format_fields = self.env['l10n_co.exogenous_format_field'].search([
            ('format_ids', 'in', setting.format_id.id),
            ('source', '=', 'contact'),
        ])

        # Separar campos según aplican a empresa, persona, o ambos
        company_fields = []  # Solo para empresas (is_company=True)
        person_fields = []   # Solo para personas (is_company=False)
        common_fields = []   # Para ambos

        field_labels = {}
        for ff in format_fields:
            if not ff.field_odoo_id:
                continue
            fname = ff.field_odoo_id.name
            field_labels[fname] = ff.name

            if ff.applies_to_company and ff.applies_to_contact:
                common_fields.append(fname)
            elif ff.applies_to_company and not ff.applies_to_contact:
                company_fields.append(fname)
            elif not ff.applies_to_company and ff.applies_to_contact:
                person_fields.append(fname)
            # Si ambos son False, no se valida

        all_odoo_fields = list(set(common_fields + company_fields + person_fields))

        # Campos que siempre se validan (ubicación)
        location_checks = {
            'city_id': 'Código municipio',
            'state_id': 'Código departamento',
            'country_id': 'País de Residencia o domicilio',
        }

        # Obtener partner_ids de los movimientos
        all_partner_ids = set()
        for sl in setting.format_setting_line_ids:
            accounts = setting._get_accounts(sl)
            if not accounts:
                continue
            _, move_lines = setting._get_information_by_account_move_line(
                accounts.ids, format_field=sl.format_field_id, setting_line=sl)
            for aml in move_lines:
                pid = aml.get('partner_id')
                if pid and isinstance(pid, (list, tuple)):
                    all_partner_ids.add(pid[0])
                elif pid:
                    all_partner_ids.add(pid)

        if not all_partner_ids:
            return {'partners': [], 'kpis': {
                'total': 0, 'complete': 0, 'incomplete': 0,
                'pct_complete': 0, 'pct_incomplete': 0,
            }}

        read_fields = list(set(all_odoo_fields + [
            'name', 'vat', 'is_company', 'email',
            'l10n_latam_identification_type_id',
            'city_id', 'state_id', 'country_id',
        ]))
        partners = self.env['res.partner'].browse(list(all_partner_ids)).read(read_fields)

        result = []
        complete = 0
        incomplete = 0

        for p in partners:
            is_company = p.get('is_company', False)
            missing = []

            # Campos comunes (aplican a ambos)
            for fname in common_fields:
                value = p.get(fname)
                if not value or (isinstance(value, str) and not value.strip()):
                    missing.append(field_labels.get(fname, fname))
                elif isinstance(value, (list, tuple)) and not value[0]:
                    missing.append(field_labels.get(fname, fname))

            # Campos específicos según tipo
            specific_fields = company_fields if is_company else person_fields
            for fname in specific_fields:
                value = p.get(fname)
                if not value or (isinstance(value, str) and not value.strip()):
                    missing.append(field_labels.get(fname, fname))
                elif isinstance(value, (list, tuple)) and not value[0]:
                    missing.append(field_labels.get(fname, fname))

            # Validar ubicación (siempre)
            for loc_field, loc_label in location_checks.items():
                if loc_field not in all_odoo_fields:
                    # Solo validar si el formato usa este campo de ubicación
                    loc_ff = format_fields.filtered(
                        lambda f: f.field_odoo_id and f.field_odoo_id.name == loc_field)
                    if not loc_ff:
                        continue
                value = p.get(loc_field)
                if not value or (isinstance(value, (list, tuple)) and not value[0]):
                    if loc_label not in [m for m in missing]:
                        missing.append(loc_label)

            status = 'incomplete' if missing else 'complete'
            if missing:
                incomplete += 1
            else:
                complete += 1

            id_type = p.get('l10n_latam_identification_type_id')
            city = p.get('city_id')
            state = p.get('state_id')
            country = p.get('country_id')
            result.append({
                'id': p['id'],
                'name': (p.get('name') or '')[:100],
                'vat': p.get('vat') or '',
                'email': p.get('email') or '',
                'is_company': is_company,
                'id_type': id_type[1] if isinstance(id_type, (list, tuple)) else '',
                'city': city[1] if isinstance(city, (list, tuple)) and city[0] else '',
                'state': state[1] if isinstance(state, (list, tuple)) and state[0] else '',
                'country': country[1] if isinstance(country, (list, tuple)) and country[0] else '',
                'status': status,
                'missing_fields': ', '.join(missing) if missing else '',
                'missing_count': len(missing),
                'selected': False,
            })

        total = len(result)
        pct_complete = round(complete / total * 100, 1) if total else 0
        pct_incomplete = round(incomplete / total * 100, 1) if total else 0

        return {
            'partners': result,
            'kpis': {
                'total': total,
                'complete': complete,
                'incomplete': incomplete,
                'pct_complete': pct_complete,
                'pct_incomplete': pct_incomplete,
            },
        }

    @api.model
    def action_send_partner_requests_owl(self, setting_id, partner_ids, template_id):
        """Envía solicitudes masivas de datos por email"""
        template = self.env['mail.template'].browse(template_id)
        if not template.exists():
            raise UserError(_("Plantilla no encontrada"))

        sent = 0
        errors = []
        for pid in partner_ids:
            partner = self.env['res.partner'].browse(pid)
            if not partner.email:
                errors.append(f"{partner.name}: sin email")
                continue
            try:
                template.send_mail(pid, force_send=False)
                sent += 1
            except Exception as e:
                errors.append(f"{partner.name}: {str(e)[:80]}")

        return {'sent': sent, 'errors': errors}

    @api.model
    def action_export_partner_data_owl(self, setting_id, partner_ids):
        """Exporta datos de terceros a Excel (retorna URL de descarga)"""
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill, Border, Side
        except ImportError:
            raise UserError(_("openpyxl no está instalado"))

        partners = self.env['res.partner'].browse(partner_ids).read([
            'name', 'vat', 'email', 'phone', 'street', 'city',
            'state_id', 'country_id', 'is_company',
            'l10n_latam_identification_type_id',
        ])

        wb = Workbook()
        ws = wb.active
        ws.title = "Terceros Exógena"

        header_font = Font(bold=True, color='FFFFFF')
        header_fill = PatternFill(start_color='3b82f6', end_color='3b82f6', fill_type='solid')
        thin_border = Border(
            left=Side(style='thin'), right=Side(style='thin'),
            top=Side(style='thin'), bottom=Side(style='thin'))

        headers = ['NIT/CC', 'Tipo doc.', 'Nombre', 'Email', 'Teléfono',
                   'Dirección', 'Ciudad', 'Departamento', 'País', 'Empresa']
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=h)
            cell.font = header_font
            cell.fill = header_fill
            cell.border = thin_border

        for idx, p in enumerate(partners, 2):
            ws.cell(row=idx, column=1, value=p.get('vat', '')).border = thin_border
            id_type = p.get('l10n_latam_identification_type_id')
            ws.cell(row=idx, column=2, value=id_type[1] if isinstance(id_type, (list, tuple)) else '').border = thin_border
            ws.cell(row=idx, column=3, value=p.get('name', '')).border = thin_border
            ws.cell(row=idx, column=4, value=p.get('email', '')).border = thin_border
            ws.cell(row=idx, column=5, value=p.get('phone', '')).border = thin_border
            ws.cell(row=idx, column=6, value=p.get('street', '')).border = thin_border
            ws.cell(row=idx, column=7, value=p.get('city', '')).border = thin_border
            state = p.get('state_id')
            ws.cell(row=idx, column=8, value=state[1] if isinstance(state, (list, tuple)) else '').border = thin_border
            country = p.get('country_id')
            ws.cell(row=idx, column=9, value=country[1] if isinstance(country, (list, tuple)) else '').border = thin_border
            ws.cell(row=idx, column=10, value='Sí' if p.get('is_company') else 'No').border = thin_border

        output = io.BytesIO()
        wb.save(output)

        setting = self.browse(setting_id)
        setting.binary_file = base64.b64encode(output.getvalue())
        setting.binary_file_name = 'terceros_exogena.xlsx'

        return {
            'url': '/web/content/?model=%s&id=%d&field=binary_file&filename_field=binary_file_name&download=true' % (
                setting._name, setting.id),
        }

    # =====================================================
    # VISTA 2: Auxiliar Resumido por Tercero
    # =====================================================

    @api.model
    def action_partner_summary_owl(self, setting_id):
        """Genera resumen condensado por tercero para la vista OWL"""
        setting = self.browse(setting_id)
        if not setting.exists():
            raise UserError(_("Configuración no encontrada"))

        summary_data = {}  # partner_id -> {info + concepts}

        for sl in setting.format_setting_line_ids:
            field = sl.format_field_id
            concept = sl.concept_id if setting.apply_concepts else False

            concept_code = concept.code if concept else ''
            field_name = field.name
            formula = field.nature_account or 'db_cr'

            accounts = setting._get_accounts(sl)
            if not accounts:
                continue

            partner_ids, move_lines = setting._get_information_by_account_move_line(
                accounts.ids, format_field=field, setting_line=sl)
            move_lines, partner_ids = setting._resolve_partner_grouping(move_lines, partner_ids)

            if not move_lines:
                continue

            for aml in move_lines:
                partner_info = aml.get('partner_id', [False, ''])
                pid = partner_info[0] if isinstance(partner_info, (list, tuple)) else partner_info
                pname = partner_info[1] if isinstance(partner_info, (list, tuple)) else str(partner_info)

                if not pid:
                    continue

                debit = aml.get('debit', 0) or 0
                credit = aml.get('credit', 0) or 0
                formula_value = setting._compute_formula(aml, formula)

                if pid not in summary_data:
                    summary_data[pid] = {
                        'partner_id': pid,
                        'name': pname[:100] if pname else '',
                        'vat': '',
                        'total_debit': 0,
                        'total_credit': 0,
                        'total_formula': 0,
                        'line_count': 0,
                        'concepts_dict': {},
                    }

                pd = summary_data[pid]
                pd['total_debit'] += debit
                pd['total_credit'] += credit
                pd['total_formula'] += formula_value
                pd['line_count'] += 1

                concept_key = f"{concept_code}|{field_name}"
                if concept_key not in pd['concepts_dict']:
                    pd['concepts_dict'][concept_key] = {
                        'key': concept_key,
                        'concept_code': concept_code,
                        'field_name': field_name,
                        'formula': formula,
                        'debit': 0, 'credit': 0,
                        'formula_value': 0, 'lines': 0,
                    }
                cd = pd['concepts_dict'][concept_key]
                cd['debit'] += debit
                cd['credit'] += credit
                cd['formula_value'] += formula_value
                cd['lines'] += 1

        # Obtener VATs
        all_pids = list(summary_data.keys())
        if all_pids:
            vat_data = self.env['res.partner'].browse(all_pids).read(['id', 'vat'])
            vat_map = {v['id']: v.get('vat', '') for v in vat_data}
            for pid, pd in summary_data.items():
                pd['vat'] = vat_map.get(pid, '')

        # Convertir diccionarios de conceptos a listas
        result = []
        for pd in summary_data.values():
            pd['concepts'] = list(pd['concepts_dict'].values())
            del pd['concepts_dict']
            result.append(pd)

        result.sort(key=lambda x: x.get('name', ''))

        total_debit = sum(p['total_debit'] for p in result)
        total_credit = sum(p['total_credit'] for p in result)
        total_formula = sum(p['total_formula'] for p in result)
        total_lines = sum(p['line_count'] for p in result)

        return {
            'data': result,
            'totals': {
                'partners': len(result),
                'lines': total_lines,
                'debit': total_debit,
                'credit': total_credit,
                'formula': total_formula,
            },
        }

    @api.model
    def action_export_partner_summary_excel_owl(self, setting_id):
        """Genera y descarga el Excel del auxiliar resumido"""
        setting = self.browse(setting_id)
        wizard = self.env['l10n_co.exogenous_partner_audit_wizard'].create({
            'format_setting_id': setting.id,
        })
        wizard.action_generate_partner_detail()
        result = wizard.action_export_excel()

        return {
            'url': '/web/content/?model=%s&id=%d&field=binary_file&filename_field=binary_file_name&download=true' % (
                wizard._name, wizard.id),
        }

    # =====================================================
    # VISTA 3: Plan jerárquico de Conceptos
    # =====================================================

    @api.model
    def action_concept_plan_tree_owl(self, format_id):
        """Construye el árbol jerárquico de conceptos para la vista OWL"""
        fmt = self.env['l10n_co.exogenous_format'].browse(format_id)
        if not fmt.exists():
            raise UserError(_("Formato no encontrado"))

        company = self.env.company
        tree = []
        total_concepts = 0
        total_columns = 0
        total_configured = 0
        total_accounts = 0

        if fmt.apply_concepts:
            Concept = self.env['l10n_co.exogenous_concept']
            concepts = Concept.search([
                *Concept._check_company_domain(company),
                ('format_id', '=', fmt.id),
                ('active', '=', True),
            ], order='code')

            format_fields = self.env['l10n_co.exogenous_format_field'].search([
                ('format_ids', 'in', fmt.id),
                ('source', '=', 'journal_items'),
            ], order='sequence')

            for concept in concepts:
                total_concepts += 1
                configured_count = 0
                concept_total_cols = len(format_fields)

                for field in format_fields:
                    total_columns += 1
                    field_account = concept.field_account_ids.filtered(
                        lambda fa: fa.format_field_id.id == field.id)

                    accounts = field_account[0].account_ids if field_account else self.env['account.account']
                    nature = field_account[0].nature_account if field_account else 'db_cr'
                    pattern = ''
                    if field_account and hasattr(field_account[0], 'account_pattern'):
                        pattern = field_account[0].account_pattern or ''
                    acc_count = len(accounts)
                    total_accounts += acc_count

                    if acc_count > 0:
                        configured_count += 1
                        total_configured += 1

                    tree.append({
                        'type': 'column',
                        'concept_id': concept.id,
                        'concept_code': concept.code,
                        'concept_name': concept.name or '',
                        'field_id': field.id,
                        'field_name': field.name,
                        'nature': nature,
                        'pattern': pattern,
                        'account_count': acc_count,
                        'status': 'configured' if acc_count > 0 else 'empty',
                    })

                # Agregar nodo concepto (al inicio)
                tree.append({
                    'type': 'concept',
                    'concept_id': concept.id,
                    'concept_code': concept.code,
                    'concept_name': concept.name or '',
                    'configured_count': configured_count,
                    'total_columns': concept_total_cols,
                })

        # Reordenar: conceptos primero, luego sus columnas
        reordered = []
        concept_nodes = [n for n in tree if n['type'] == 'concept']
        for cn in concept_nodes:
            reordered.append(cn)
            cols = [n for n in tree if n['type'] == 'column' and n['concept_id'] == cn['concept_id']]
            reordered.extend(cols)

        return {
            'tree': reordered,
            'kpis': {
                'concepts': total_concepts,
                'columns': total_columns,
                'configured': total_configured,
                'accounts': total_accounts,
            },
        }

    @api.model
    def action_apply_concept_node_owl(self, format_id, concept_id, field_id, config):
        """Aplica configuración a un nodo concepto+columna"""
        concept = self.env['l10n_co.exogenous_concept'].browse(concept_id)
        field = self.env['l10n_co.exogenous_format_field'].browse(field_id)

        if not concept.exists() or not field.exists():
            raise UserError(_("Concepto o campo no encontrado"))

        field_account = concept.field_account_ids.filtered(
            lambda fa: fa.format_field_id.id == field.id)

        vals = {
            'nature_account': config.get('nature', 'db_cr'),
        }
        if config.get('pattern'):
            vals['account_pattern'] = config['pattern']

        if field_account:
            field_account[0].write(vals)
        else:
            vals.update({
                'concept_id': concept.id,
                'format_field_id': field.id,
            })
            self.env['l10n_co.exogenous_format_field_account'].create(vals)

        return {'success': True}

    @api.model
    def action_suggest_all_patterns_owl(self, format_id):
        """Sugiere patrones para todos los conceptos"""
        try:
            from odoo.addons.l10n_co_exogenous_information_reporting.wizard.l10n_co_exogenous_account_config_wizard import (
                SUGGESTIONS_MAP, DEFAULT_NATURE_BY_ATTRIBUTE,
            )
        except ImportError:
            return {'applied': 0}

        fmt = self.env['l10n_co.exogenous_format'].browse(format_id)
        company = self.env.company
        applied = 0

        Concept = self.env['l10n_co.exogenous_concept']
        concepts = Concept.search([
            *Concept._check_company_domain(company),
            ('format_id', '=', fmt.id),
            ('active', '=', True),
        ])

        format_fields = self.env['l10n_co.exogenous_format_field'].search([
            ('format_ids', 'in', fmt.id),
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

        return {'applied': applied}

    @api.model
    def action_load_all_patterns_owl(self, format_id):
        """Carga cuentas desde patrones"""
        fmt = self.env['l10n_co.exogenous_format'].browse(format_id)
        company = self.env.company
        loaded = 0

        Concept = self.env['l10n_co.exogenous_concept']
        concepts = Concept.search([
            *Concept._check_company_domain(company),
            ('format_id', '=', fmt.id),
            ('active', '=', True),
        ])

        for concept in concepts:
            for fa in concept.field_account_ids:
                if fa.account_pattern and not fa.account_ids:
                    if hasattr(fa, 'action_load_accounts_from_pattern'):
                        fa.action_load_accounts_from_pattern()
                        loaded += len(fa.account_ids)

        return {'loaded': loaded}

    @api.model
    def action_sync_plan_to_setting_owl(self, format_id, setting_id):
        """Sincroniza el plan con un format_setting"""
        setting = self.browse(setting_id)
        if not setting.exists():
            raise UserError(_("Configuración no encontrada"))

        fmt = self.env['l10n_co.exogenous_format'].browse(format_id)
        company = self.env.company
        synced = 0

        Concept = self.env['l10n_co.exogenous_concept']
        concepts = Concept.search([
            *Concept._check_company_domain(company),
            ('format_id', '=', fmt.id),
            ('active', '=', True),
        ])

        format_fields = self.env['l10n_co.exogenous_format_field'].search([
            ('format_ids', 'in', fmt.id),
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

        return {'synced': synced}

    @api.model
    def action_test_domain_owl(self, domain_str):
        """Prueba un dominio personalizado"""
        try:
            domain = eval(domain_str, {"__builtins__": {}})
            if not isinstance(domain, list):
                raise UserError(_("El dominio debe ser una lista"))

            AML = self.env['account.move.line']
            base_domain = [
                *AML._check_company_domain(self.env.company),
                ('parent_state', '=', 'posted'),
            ]
            count = AML.search_count(base_domain + domain)
            return {'count': count}
        except Exception as e:
            raise UserError(str(e))
