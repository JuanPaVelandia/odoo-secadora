# -*- coding: utf-8 -*-
from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError


COLUMN_SELECTION = [
    ('pago', 'pago - Pago o abono deducible'),
    ('pnded', 'pnded - Pago o abono NO deducible'),
    ('ided', 'ided - IVA mayor valor costo/gasto deducible'),
    ('inded', 'inded - IVA mayor valor costo/gasto NO deducible'),
    ('retp', 'retp - Retención renta practicada'),
    ('reta', 'reta - Retención renta asumida'),
    ('comun', 'comun - Retefuente IVA régimen común'),
    ('ndom', 'ndom - Retefuente IVA no domiciliados'),
]


class L10ncoExogenousLineColumnWizard(models.TransientModel):
    _name = 'l10n_co.exogenous_line_column_wizard'
    _description = 'Wizard para ubicar líneas del auxiliar en columnas del formato 1001'

    format_id = fields.Many2one(
        comodel_name='l10n_co.exogenous_format',
        string='Formato',
        required=True,
        domain=[('code', '=', '1001')],
        default=lambda self: self._default_format_id(),
    )
    concept_id = fields.Many2one(
        comodel_name='l10n_co.exogenous_concept',
        string='Concepto DIAN',
        domain="[('format_id', '=', format_id)]",
        help="Concepto opcional a asignar a todas las líneas")
    target_column = fields.Selection(
        selection=COLUMN_SELECTION,
        string='Columna destino',
        help="Columna primaria a aplicar. Si se deja vacío, se respeta la sugerencia por línea.")
    target_percentage = fields.Float(
        string='% a columna primaria',
        default=100.0,
        help="Porcentaje del valor que va a la columna primaria. "
             "El residuo (100 - %) va a la columna secundaria. Uso típico: prorrateo IVA Art. 490 E.T.")
    secondary_column = fields.Selection(
        selection=COLUMN_SELECTION,
        string='Columna secundaria (residuo)',
        help="Columna para el residuo (100 - %). Requerida si porcentaje < 100")
    auto_detect = fields.Boolean(
        string='Detección automática',
        default=True,
        help="Analiza cada línea usando tax_line_id, tax_ids y cuenta para sugerir la columna")
    line_ids = fields.One2many(
        comodel_name='l10n_co.exogenous_line_column_wizard_line',
        inverse_name='wizard_id',
        string='Líneas a asignar')

    @api.model
    def _default_format_id(self):
        fmt = self.env['l10n_co.exogenous_format'].search(
            [('code', '=', '1001')], order='year desc', limit=1)
        return fmt.id if fmt else False

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        active_ids = self.env.context.get('active_ids') or []
        active_model = self.env.context.get('active_model')
        if active_model != 'account.move.line' or not active_ids:
            return vals
        lines = self.env['account.move.line'].browse(active_ids)
        wizard_lines = []
        for line in lines:
            suggested, reason = self._suggest_column_for_line(line)
            wizard_lines.append(Command.create({
                'move_line_id': line.id,
                'suggested_column': suggested,
                'target_column': line.l10n_co_exogenous_format_field_id.attribute or suggested,
                'target_percentage': line.l10n_co_exogenous_percentage or 100.0,
                'secondary_column': line.l10n_co_exogenous_secondary_field_id.attribute or False,
                'reason': reason,
                'selected': True,
            }))
        vals['line_ids'] = wizard_lines
        return vals

    @api.model
    def _suggest_column_for_line(self, line):
        """Sugiere columna del 1001 usando lógica nativa de Odoo."""
        account = line.account_id
        tax_line = line.tax_line_id
        taxes = line.tax_ids

        if tax_line:
            type_use = tax_line.type_tax_use
            name_upper = (tax_line.name or '').upper()
            if 'RETEFUENTE' in name_upper or 'RETE FUENTE' in name_upper or 'RENTA' in name_upper:
                if 'ASUMIDA' in name_upper or 'ASUMIDO' in name_upper:
                    return 'reta', _('Impuesto %s: retención renta asumida') % tax_line.name
                return 'retp', _('Impuesto %s: retención renta practicada') % tax_line.name
            if 'RETEIVA' in name_upper or 'RETE IVA' in name_upper or 'RETENCION IVA' in name_upper:
                if 'NO DOMICILIAD' in name_upper or 'NDOM' in name_upper or 'EXTERIOR' in name_upper:
                    return 'ndom', _('Impuesto %s: retefuente IVA no domiciliados') % tax_line.name
                return 'comun', _('Impuesto %s: retefuente IVA régimen común') % tax_line.name
            if type_use == 'purchase' and 'IVA' in name_upper:
                if getattr(account, 'l10n_co_exo_is_mayor_valor', False):
                    return 'inded', _('IVA mayor valor SIN cuenta (tax_line_id %s)') % tax_line.name
                return 'ided', _('IVA deducible por tax_line_id %s') % tax_line.name

        if getattr(account, 'l10n_co_exo_is_retention', False):
            return 'retp', _('Cuenta %s marcada como retención') % account.code

        if getattr(account, 'l10n_co_exo_is_mayor_valor', False):
            if account.account_type in ('expense', 'expense_depreciation', 'expense_direct_cost'):
                return 'ided', _('IVA mayor valor CON cuenta gasto %s (Art. 490 E.T.)') % account.code
            return 'inded', _('IVA mayor valor con cuenta %s (no gasto)') % account.code

        if account.account_type in ('expense', 'expense_depreciation', 'expense_direct_cost'):
            if taxes:
                return 'pago', _('Gasto %s con impuestos → base deducible') % account.code
            return 'pago', _('Gasto %s sin impuestos → deducible') % account.code

        if account.account_type == 'asset_fixed':
            return 'pago', _('Activo fijo %s (compra activo)') % account.code

        if account.account_type in ('asset_current', 'asset_non_current'):
            return 'pago', _('Activo %s') % account.code

        return 'pnded', _('Sin regla clara; no deducible por defecto')

    def _get_field_by_attr(self, attrs):
        """Resuelve format_field por attribute para el formato actual"""
        self.ensure_one()
        if not attrs:
            return {}
        FormatField = self.env['l10n_co.exogenous_format_field']
        fields_found = FormatField.search([
            ('attribute', 'in', list(attrs)),
            ('format_ids', 'in', self.format_id.id),
        ])
        mapping = {f.attribute: f.id for f in fields_found}
        missing = set(attrs) - set(mapping.keys())
        if missing:
            raise UserError(_(
                "El formato %s no tiene campos para: %s. Use 'Cargar campos XSD' primero."
            ) % (self.format_id.display_name, ', '.join(missing)))
        return mapping

    def action_apply(self):
        """Aplica la asignación a las líneas marcadas en el wizard"""
        self.ensure_one()
        lines_to_apply = self.line_ids.filtered('selected')
        if not lines_to_apply:
            raise UserError(_("No hay líneas seleccionadas para aplicar"))

        attrs_needed = set()
        for wl in lines_to_apply:
            col = wl.target_column or self.target_column
            sec = wl.secondary_column or (self.secondary_column if self.target_column else False)
            if col:
                attrs_needed.add(col)
            if sec:
                attrs_needed.add(sec)

        field_by_attr = self._get_field_by_attr(attrs_needed)
        updated = 0
        for wl in lines_to_apply:
            col = wl.target_column or self.target_column
            if not col:
                continue
            pct = wl.target_percentage if wl.target_percentage is not None else self.target_percentage
            sec = wl.secondary_column or (self.secondary_column if self.target_column else False)
            if pct < 100 and not sec:
                raise UserError(_(
                    "Línea %s tiene %% %s pero no columna secundaria"
                ) % (wl.move_line_id.display_name, pct))

            vals = {
                'l10n_co_exogenous_format_field_id': field_by_attr[col],
                'l10n_co_exogenous_percentage': pct,
                'l10n_co_exogenous_secondary_field_id': field_by_attr[sec] if sec else False,
                'l10n_co_exogenous_assignment_reason': wl.reason or _('Asignación manual'),
            }
            if self.concept_id:
                vals['l10n_co_exogenous_concept_id'] = self.concept_id.id
            wl.move_line_id.write(vals)
            updated += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Asignación completada'),
                'message': _('%d líneas actualizadas') % updated,
                'type': 'success',
                'sticky': False,
            }
        }

    def action_apply_header_to_selected(self):
        """Propaga columna/porcentaje/secundaria de la cabecera a todas las líneas marcadas"""
        self.ensure_one()
        if not self.target_column:
            raise UserError(_("Fije la columna destino en la cabecera antes de propagar"))
        updated = 0
        for wl in self.line_ids.filtered('selected'):
            wl.target_column = self.target_column
            wl.target_percentage = self.target_percentage
            wl.secondary_column = self.secondary_column
            updated += 1
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_reapply_detection(self):
        """Re-ejecuta detección automática sobre las líneas actuales"""
        self.ensure_one()
        for wl in self.line_ids:
            suggested, reason = self._suggest_column_for_line(wl.move_line_id)
            wl.suggested_column = suggested
            wl.target_column = suggested
            wl.reason = reason
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_select_all(self):
        self.ensure_one()
        self.line_ids.write({'selected': True})
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_unselect_all(self):
        self.ensure_one()
        self.line_ids.write({'selected': False})
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }


class L10ncoExogenousLineColumnWizardLine(models.TransientModel):
    _name = 'l10n_co.exogenous_line_column_wizard_line'
    _description = 'Línea del wizard de ubicación en columnas 1001'

    wizard_id = fields.Many2one(
        comodel_name='l10n_co.exogenous_line_column_wizard',
        required=True,
        ondelete='cascade')
    move_line_id = fields.Many2one(
        comodel_name='account.move.line',
        string='Línea contable',
        required=True,
        ondelete='cascade')
    selected = fields.Boolean(string='Aplicar', default=True)
    partner_id = fields.Many2one(related='move_line_id.partner_id', string='Tercero')
    account_id = fields.Many2one(related='move_line_id.account_id', string='Cuenta')
    date = fields.Date(related='move_line_id.date')
    debit = fields.Monetary(related='move_line_id.debit', currency_field='currency_id')
    credit = fields.Monetary(related='move_line_id.credit', currency_field='currency_id')
    currency_id = fields.Many2one(related='move_line_id.currency_id')
    tax_line_id = fields.Many2one(related='move_line_id.tax_line_id', string='Impuesto (línea)')
    suggested_column = fields.Selection(
        selection=COLUMN_SELECTION,
        string='Sugerencia',
        readonly=True)
    target_column = fields.Selection(
        selection=COLUMN_SELECTION,
        string='Columna destino',
        help="Columna final a aplicar. Editable por línea.")
    target_percentage = fields.Float(
        string='% primaria',
        default=100.0,
        help="Porcentaje del valor a la columna primaria. Residuo va a la secundaria.")
    secondary_column = fields.Selection(
        selection=COLUMN_SELECTION,
        string='Secundaria',
        help="Columna para el residuo (100 - %)")
    reason = fields.Char(string='Motivo')
