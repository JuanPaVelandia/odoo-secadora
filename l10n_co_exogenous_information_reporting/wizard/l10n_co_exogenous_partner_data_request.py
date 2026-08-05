# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class L10nCoExogenousPartnerDataRequest(models.TransientModel):
    """Wizard para revisar datos de terceros y enviar solicitudes masivas.

    Usa los campos applies_to_company / applies_to_contact del formato
    para diferenciar qué campos se validan según tipo de tercero.
    """
    _name = 'l10n_co.exogenous_partner_data_request'
    _description = 'Solicitud de datos de terceros para exógena'

    format_setting_id = fields.Many2one(
        'l10n_co.exogenous_format_setting',
        string='Configuración',
        required=True)
    format_id = fields.Many2one(
        'l10n_co.exogenous_format',
        related='format_setting_id.format_id',
        readonly=True)
    company_id = fields.Many2one(
        'res.company',
        related='format_setting_id.company_id',
        readonly=True)
    mail_template_id = fields.Many2one(
        'mail.template',
        string='Plantilla de correo',
        domain="[('model_id.model', '=', 'res.partner')]",
        help='Plantilla para enviar solicitud de datos a terceros')

    line_ids = fields.One2many(
        'l10n_co.exogenous_partner_data_request.line',
        'wizard_id',
        string='Terceros')

    total_partners = fields.Integer(string='Total terceros', readonly=True)
    total_complete = fields.Integer(string='Datos completos', readonly=True)
    total_incomplete = fields.Integer(string='Datos incompletos', readonly=True)
    pct_complete = fields.Float(string='% completos', readonly=True, digits=(5, 1))
    pct_incomplete = fields.Float(string='% incompletos', readonly=True, digits=(5, 1))
    total_selected = fields.Integer(
        string='Seleccionados',
        compute='_compute_total_selected')

    @api.depends('line_ids.selected')
    def _compute_total_selected(self):
        for rec in self:
            rec.total_selected = len(rec.line_ids.filtered('selected'))

    def action_analyze_partners(self):
        """Analiza los terceros involucrados en la exógena y sus datos faltantes.

        Usa applies_to_company / applies_to_contact para diferenciar
        qué campos se validan según tipo de tercero (empresa vs persona).
        Siempre valida ciudad, departamento y país cuando el formato los requiere.
        """
        self.ensure_one()
        self.line_ids = [Command.clear()]
        setting = self.format_setting_id

        # Obtener campos requeridos según el formato
        format_fields = self.env['l10n_co.exogenous_format_field'].search([
            ('format_ids', 'in', setting.format_id.id),
            ('source', '=', 'contact'),
        ])

        # Separar campos según aplican a empresa, persona o ambos
        company_fields = []
        person_fields = []
        common_fields = []
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

        all_odoo_fields = list(set(common_fields + company_fields + person_fields))

        # Campos de ubicación que siempre se validan si el formato los usa
        location_checks = {
            'city_id': 'Código municipio',
            'state_id': 'Código departamento',
            'country_id': 'País de Residencia o domicilio',
        }

        # Obtener todos los partner_ids involucrados
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
            return self._show_notification(
                _('Sin terceros'),
                _('No se encontraron terceros con movimientos para este formato'),
                'warning')

        # Leer datos de todos los partners
        read_fields = list(set(all_odoo_fields + [
            'name', 'vat', 'is_company', 'email',
            'l10n_latam_identification_type_id',
            'city_id', 'state_id', 'country_id',
        ]))
        partners = self.env['res.partner'].browse(list(all_partner_ids)).read(read_fields)

        lines = []
        total_complete = 0
        total_incomplete = 0

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

            # Validar ubicación
            for loc_field, loc_label in location_checks.items():
                if loc_field not in all_odoo_fields:
                    loc_ff = format_fields.filtered(
                        lambda f: f.field_odoo_id and f.field_odoo_id.name == loc_field)
                    if not loc_ff:
                        continue
                value = p.get(loc_field)
                if not value or (isinstance(value, (list, tuple)) and not value[0]):
                    if loc_label not in missing:
                        missing.append(loc_label)

            if missing:
                status = 'incomplete'
                total_incomplete += 1
            else:
                status = 'complete'
                total_complete += 1

            pid = p['id']
            id_type = p.get('l10n_latam_identification_type_id')
            city = p.get('city_id')
            state = p.get('state_id')
            country = p.get('country_id')
            lines.append(Command.create({
                'partner_id': pid,
                'partner_name': (p.get('name') or '')[:100],
                'partner_vat': p.get('vat') or '',
                'partner_email': p.get('email') or '',
                'is_company': is_company,
                'id_type_display': id_type[1] if isinstance(id_type, (list, tuple)) else '',
                'city_display': city[1] if isinstance(city, (list, tuple)) and city[0] else '',
                'state_display': state[1] if isinstance(state, (list, tuple)) and state[0] else '',
                'country_display': country[1] if isinstance(country, (list, tuple)) and country[0] else '',
                'status': status,
                'missing_fields': ', '.join(missing) if missing else '',
                'missing_count': len(missing),
            }))

        total = len(partners)
        pct_complete = round(total_complete / total * 100, 1) if total else 0
        pct_incomplete = round(total_incomplete / total * 100, 1) if total else 0

        self.write({
            'line_ids': lines,
            'total_partners': total,
            'total_complete': total_complete,
            'total_incomplete': total_incomplete,
            'pct_complete': pct_complete,
            'pct_incomplete': pct_incomplete,
        })

        return {
            'type': 'ir.actions.act_window',
            'name': _('Terceros - %s') % self.format_id.code,
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': {'dialog_size': 'extra-large'},
        }

    def action_select_all_incomplete(self):
        """Selecciona todos los terceros con datos incompletos"""
        self.ensure_one()
        for line in self.line_ids:
            line.selected = (line.status == 'incomplete')
        return self._reload()

    def action_select_all(self):
        """Selecciona todos los terceros"""
        self.ensure_one()
        self.line_ids.write({'selected': True})
        return self._reload()

    def action_deselect_all(self):
        """Deselecciona todos"""
        self.ensure_one()
        self.line_ids.write({'selected': False})
        return self._reload()

    def action_send_mass_request(self):
        """Envía solicitud masiva de datos usando la plantilla seleccionada"""
        self.ensure_one()
        if not self.mail_template_id:
            raise UserError(_('Seleccione una plantilla de correo primero'))

        selected = self.line_ids.filtered('selected')
        if not selected:
            raise UserError(_('Seleccione al menos un tercero'))

        partner_ids = selected.mapped('partner_id')
        sent = 0
        errors = []

        for pid in partner_ids:
            partner = self.env['res.partner'].browse(pid)
            if not partner.email:
                errors.append(f"{partner.name}: sin email")
                continue
            try:
                self.mail_template_id.send_mail(partner.id, force_send=False)
                sent += 1
            except Exception as e:
                errors.append(f"{partner.name}: {str(e)[:80]}")

        msg = _('%d correos programados para envío.') % sent
        if errors:
            msg += _('\n\nErrores (%d):\n') % len(errors) + '\n'.join(errors[:10])

        return self._show_notification(
            _('Solicitudes enviadas'),
            msg,
            'success' if not errors else 'warning')

    def action_open_partner(self):
        """Abre el formulario del tercero seleccionado"""
        self.ensure_one()
        selected = self.line_ids.filtered('selected')
        if not selected:
            raise UserError(_('Seleccione un tercero'))

        if len(selected) == 1:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Tercero'),
                'res_model': 'res.partner',
                'view_mode': 'form',
                'res_id': selected[0].partner_id,
                'target': 'current',
            }
        else:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Terceros seleccionados'),
                'res_model': 'res.partner',
                'view_mode': 'list,form',
                'domain': [('id', 'in', selected.mapped('partner_id'))],
                'target': 'current',
            }

    def _reload(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Terceros - %s') % self.format_id.code,
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


class L10nCoExogenousPartnerDataRequestLine(models.TransientModel):
    """Línea del wizard de datos de tercero con datos de ubicación"""
    _name = 'l10n_co.exogenous_partner_data_request.line'
    _description = 'Línea de solicitud de datos'
    _order = 'status desc, partner_name'

    wizard_id = fields.Many2one(
        'l10n_co.exogenous_partner_data_request',
        required=True, ondelete='cascade')
    selected = fields.Boolean(string='Sel.', default=False)
    partner_id = fields.Integer(string='ID')
    partner_name = fields.Char(string='Tercero', readonly=True)
    partner_vat = fields.Char(string='NIT/CC', readonly=True)
    partner_email = fields.Char(string='Email', readonly=True)
    is_company = fields.Boolean(string='Empresa', readonly=True)
    id_type_display = fields.Char(string='Tipo doc.', readonly=True)
    city_display = fields.Char(string='Ciudad', readonly=True)
    state_display = fields.Char(string='Departamento', readonly=True)
    country_display = fields.Char(string='País', readonly=True)
    status = fields.Selection([
        ('complete', 'Completo'),
        ('incomplete', 'Incompleto'),
    ], string='Estado', readonly=True)
    missing_fields = fields.Text(string='Campos faltantes', readonly=True)
    missing_count = fields.Integer(string='# Faltantes', readonly=True)
