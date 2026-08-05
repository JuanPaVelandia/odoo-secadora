# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _, Command

from odoo.addons.l10n_co_exogenous_information_reporting.models.l10n_co_exogenous_format_field_account import (
    NATURE_ACCOUNT_SELECTION, NATURE_ACCOUNT_HELP,
)

_logger = logging.getLogger(__name__)


class L10ncoExogenousFormatFields(models.Model):
    _name = "l10n_co.exogenous_format_field"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Plantilla para la creación de campos por formato"
    _check_company_auto = True
    _order = 'sequence asc, id'

    @api.model
    def _auto_init(self):
        res = super()._auto_init()
        self._cr.execute("""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'l10n_co_exogenous_format_field_attribute_idx') THEN
                    CREATE INDEX l10n_co_exogenous_format_field_attribute_idx ON l10n_co_exogenous_format_field (attribute);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'l10n_co_exogenous_format_field_source_idx') THEN
                    CREATE INDEX l10n_co_exogenous_format_field_source_idx ON l10n_co_exogenous_format_field (source);
                END IF;
            END $$;
        """)
        _logger.info("l10n_co.exogenous_format_field: _auto_init completed with custom indexes")
        return res

    @staticmethod
    def _get_sources():
        return [
            ('contact', _('Contacto')),
            ('journal_items', _('Apuntes contables')),
            ('resolution', _('Resolución')),
            ('hr_employee', _('Empleado (HR)')),
            ('hr_payslip', _('Nómina')),
        ]

    @staticmethod
    def _get_xsd_types():
        return [
            ('string', 'String'),
            ('int', 'Integer'),
            ('long', 'Long'),
            ('double', 'Double'),
            ('date', 'Date'),
            ('dateTime', 'DateTime'),
            ('gYear', 'Year'),
        ]

    name = fields.Text(string='Nombre', tracking=True)
    sequence = fields.Integer(string='Secuencia')
    max_length = fields.Integer(string='Longitud máxima', tracking=True)
    min_length = fields.Integer(string='Longitud mínima', default=0, tracking=True)
    attribute = fields.Char(string='Atributo', tracking=True)
    source = fields.Selection(selection="_get_sources", string='Fuente', tracking=True)

    xsd_type = fields.Selection(
        selection="_get_xsd_types",
        string='Tipo XSD',
        default='string',
        help='Tipo de dato según el esquema XSD')
    xsd_required = fields.Boolean(
        string='Requerido XSD',
        default=False,
        help='Indica si el campo es requerido según el XSD')
    xsd_pattern = fields.Char(
        string='Patrón XSD',
        help='Expresión regular de validación según XSD (ej: [0-9]{1,18})')
    xsd_slice = fields.Selection([
        ('none', 'Sin recorte'),
        ('last_2', 'Últimos 2 dígitos'),
        ('last_3', 'Últimos 3 dígitos'),
        ('last_4', 'Últimos 4 dígitos'),
        ('first_2', 'Primeros 2 dígitos'),
        ('first_3', 'Primeros 3 dígitos'),
    ], string='Recorte de valor', default='none',
       help='Recorta el valor antes de validar y exportar.\n'
            'Ej: Código DANE 08001 con "Últimos 3 dígitos" → 001')
    xsd_min_value = fields.Char(
        string='Valor mínimo',
        help='Valor mínimo permitido según XSD')
    xsd_max_value = fields.Char(
        string='Valor máximo',
        help='Valor máximo permitido según XSD')
    format_ids = fields.Many2many(
        comodel_name="l10n_co.exogenous_format",
        relation="l10n_co_exogenous_format_field_rel",
        column1="format_id",
        column2="field_id",
        string='Formatos',
        tracking=True
    )
    active = fields.Boolean(string='Activo', default=True, tracking=True)
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        default=lambda self: self.env.company.id
    )

    applies_to_company = fields.Boolean(
        string='¿Aplica a empresas?',
        default=True,
        help="Si está seleccionado, este campo aplica cuando el contacto es una empresa"
    )

    applies_to_contact = fields.Boolean(
        string='¿Aplica a personas naturales?',
        default=True,
        help="Si está seleccionado, este campo aplica cuando el contacto es una persona natural"
    )

    is_unique_key = fields.Boolean(
        string='¿Es clave única del formato?',
        default=False,
        help="Si está seleccionado, se usa para agrupar información"
    )

    format_applies_concepts = fields.Boolean(
        string='¿El formato aplica conceptos?',
        compute='_compute_format_applies_concepts',
        store=True,
        help="Calculado automaticamente: True si algun formato asociado usa conceptos"
    )

    @api.depends('format_ids', 'format_ids.apply_concepts')
    def _compute_format_applies_concepts(self):
        """Determina si alguno de los formatos asociados aplica conceptos"""
        for rec in self:
            rec.format_applies_concepts = any(f.apply_concepts for f in rec.format_ids)

    field_odoo_id = fields.Many2one(
        comodel_name='ir.model.fields',
        string='Campo Odoo',
        domain="[('model', '=', 'res.partner'), ('ttype', 'not in', ('one2many', 'many2many'))]"
    )
    ttype = fields.Selection(related='field_odoo_id.ttype', readonly=True)
    relation = fields.Char(related='field_odoo_id.relation', readonly=True)

    field_odoo_internal_id = fields.Many2one(
        comodel_name='ir.model.fields',
        string='Campo relacional Odoo',
        domain="[('model', '=', relation), ('ttype', 'not in', ('many2one', 'one2many', 'many2many'))]"
    )

    account_pattern = fields.Char(
        string='Patrón de cuentas',
        help="Patrones de cuenta separados por coma. Ej: 5105%, 5110%, 5115%\n"
             "Use % como comodín. Todas las cuentas coincidentes serán cargadas.",
        tracking=True
    )
    account_ids = fields.Many2many(
        comodel_name='account.account',
        relation='l10n_co_exogenous_format_field_account_direct_rel',
        column1='field_id',
        column2='account_id',
        string='Cuentas directas',
        check_company=True,
        tracking=True
    )
    account_count = fields.Integer(
        string='No. Cuentas',
        compute='_compute_account_count',
        store=True
    )
    nature_account = fields.Selection(
        selection=NATURE_ACCOUNT_SELECTION,
        string='Formula', default='db_cr', tracking=True,
        help=NATURE_ACCOUNT_HELP)

    corte = fields.Selection([
        ('year_movement', 'Movimiento del año'),
        ('final_balance', 'Saldo final'),
    ], string='Corte', default='year_movement', tracking=True,
       help="Corte de la información:\n"
            "- Movimiento del año: Toma movimientos del período fiscal\n"
            "- Saldo final: Toma el saldo acumulado al final del período")

    applies_smaller_amounts = fields.Boolean(
        string='Aplica cuantía',
        default=False,
        tracking=True,
        help="Si está activo, valida el valor mínimo a reportar en esta columna")
    principal_field_id = fields.Many2one('l10n_co.exogenous_format_field',
        string='Principal',
        tracking=True,
        help="Columna principal de la cual se toman los conceptos y cuentas. "
             "Si se asigna, esta columna NO requiere configuración propia de conceptos "
             "ya que usará los de la columna principal referenciada",
        check_company=True)
    sign_type = fields.Selection([
        ('as_is', 'Como está'),
        ('absolute', 'Valor absoluto'),
        ('positive_only', 'Solo positivos'),
        ('invert', 'Invertir signo'),
    ], string='Tratamiento de signo', default='as_is', tracking=True,
       help="Transformación post-cálculo del signo del valor")
    default_value = fields.Char(
        string='Valor por defecto',
        tracking=True,
        help="Valor que se asigna cuando el campo está vacío o es cero")
    rounding_type = fields.Selection([
        ('none', 'Sin redondeo'),
        ('round', 'Redondear'),
        ('ceil', 'Redondear arriba'),
        ('floor', 'Redondear abajo'),
        ('truncate', 'Truncar decimales'),
    ], string='Tipo de redondeo', default='round', tracking=True,
       help="Cómo redondear los valores numéricos al generar el reporte")

    formula_limit_type = fields.Selection([
        ('none', 'Sin límite'),
        ('fixed_amount', 'Monto fijo (COP)'),
        ('uvt', 'Valor en UVT'),
    ], string='Tipo de límite', default='none', tracking=True,
       help="Tipo de límite a aplicar sobre el valor calculado:\n"
            "- Sin límite: Se reporta el valor completo\n"
            "- Monto fijo: Se limita al monto en COP configurado\n"
            "- Valor en UVT: Se limita al equivalente en UVT (requiere valor UVT en configuración)")
    formula_limit_value = fields.Float(
        string='Valor límite',
        digits=(16, 2),
        tracking=True,
        help="Valor máximo en COP o cantidad de UVT según el tipo de límite seleccionado")
    formula_percentage = fields.Float(
        string='Porcentaje aplicado',
        digits=(5, 2),
        default=100.0,
        tracking=True,
        help="Porcentaje a aplicar sobre el valor calculado. "
             "Ej: 50.0 = se reporta solo el 50%% del valor. "
             "Por defecto 100%% (valor completo)")
    formula_source_field_id = fields.Many2one('l10n_co.exogenous_format_field',
        string='Columna origen',
        tracking=True,
        check_company=True,
        help="Si se configura, esta columna NO calcula su valor desde los apuntes contables "
             "sino que toma el valor ya calculado de la columna origen y le aplica las "
             "transformaciones configuradas (porcentaje, límite, signo, redondeo). "
             "Útil para columnas derivadas como 'Mayor Valor' = 50%% de otra columna")

    line_tax_filter = fields.Selection([
        ('all', 'Todas las líneas'),
        ('tax_lines_only', 'Solo líneas de impuesto'),
        ('base_lines_only', 'Solo líneas base'),
    ], string='Filtro líneas impuesto', default='all', tracking=True,
       help="Filtra las líneas de asiento según su relación con impuestos:\n"
            "- Todas: incluye todas las líneas (por defecto)\n"
            "- Solo líneas de impuesto: líneas generadas por un impuesto (tax_line_id)\n"
            "- Solo líneas base: líneas que tienen impuestos aplicados pero no son línea de impuesto")
    tax_group_ids = fields.Many2many(
        comodel_name='account.tax.group',
        relation='l10n_co_exogenous_format_field_tax_group_rel',
        column1='field_id',
        column2='tax_group_id',
        string='Grupos de impuesto',
        tracking=True,
        help="Filtra solo líneas asociadas a estos grupos de impuesto (IVA, Retención, ICA, etc.). "
             "Para mayor valor: seleccione el grupo de IVA y filtre por líneas de impuesto")
    tax_ids_filter = fields.Many2many(
        comodel_name='account.tax',
        relation='l10n_co_exogenous_format_field_tax_filter_rel',
        column1='field_id',
        column2='tax_id',
        string='Impuestos específicos',
        tracking=True,
        help="Filtra solo líneas asociadas a estos impuestos específicos. "
             "Útil para retenciones asociadas o impuestos de mayor valor")

    filter_domain = fields.Char(
        string='Filtro adicional (dominio)',
        help='Dominio Odoo adicional aplicado sobre account.move.line al construir '
             'el reporte para este campo. Ej: '
             '[("move_id.move_type","=","out_invoice")]. '
             'Se combina con AND a los demás filtros (cuentas, impuestos, exclusiones).')

    @api.depends('account_ids')
    def _compute_account_count(self):
        for rec in self:
            rec.account_count = len(rec.account_ids)

    @api.onchange('account_pattern')
    def _onchange_account_pattern(self):
        """Carga cuentas automáticamente cuando cambia el patrón"""
        if self.account_pattern:
            accounts = self._get_accounts_from_pattern()
            if accounts:
                self.account_ids = [Command.set(accounts.ids)]

    def _get_accounts_from_pattern(self):
        """Obtiene cuentas basadas en el patrón definido (Odoo 14: company_id Many2one)"""
        self.ensure_one()
        if not self.account_pattern:
            return self.env['account.account']

        patterns = [p.strip() for p in self.account_pattern.split(',') if p.strip()]
        if not patterns:
            return self.env['account.account']

        company = self.company_id or self.env.company
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

    def action_load_accounts_from_pattern(self):
        """Acción para cargar cuentas desde el patrón definido"""
        loaded = 0
        for rec in self:
            if rec.account_pattern:
                accounts = rec._get_accounts_from_pattern()
                rec.account_ids = [Command.set(accounts.ids)]
                loaded += len(accounts)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Cuentas cargadas'),
                'message': _('%d cuentas cargadas desde el patrón.') % loaded,
                'sticky': False,
                'type': 'success',
            }
        }

    def action_clear_accounts(self):
        """Limpia las cuentas asignadas"""
        self.account_ids = [Command.clear()]
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Cuentas eliminadas'),
                'message': _('Todas las cuentas eliminadas del campo.'),
                'sticky': False,
                'type': 'info',
            }
        }

    def action_view_accounts(self):
        """Abre vista de las cuentas asignadas"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Cuentas - %s') % self.name,
            'res_model': 'account.account',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.account_ids.ids)],
            'context': {'create': False},
        }

    def get_accounts_for_report(self):
        """Obtiene cuentas para el reporte"""
        self.ensure_one()
        return self.account_ids or self.env['account.account']

    def get_nature_for_report(self):
        """Obtiene la fórmula de acumulación para el reporte

        Mapea la fórmula seleccionada al campo de account.move.line correspondiente.
        Para fórmulas compuestas (DB-CR, CR-DB) se usa un identificador especial
        que el método compute_formula_value() resuelve.
        """
        self.ensure_one()
        return self.nature_account or 'db_cr'

    def compute_formula_value(self, row):
        """Calcula el valor según la fórmula configurada

        Args:
            row: dict o Series con los campos debit, credit, balance, tax_base_amount

        Returns:
            float: valor calculado según la fórmula
        """
        self.ensure_one()
        formula = self.nature_account or 'db_cr'

        debit = row.get('debit', 0) or 0
        credit = row.get('credit', 0) or 0
        balance = row.get('balance', 0) or 0
        tax_base = row.get('tax_base_amount', 0) or 0

        if formula == 'debit':
            return debit
        elif formula == 'credit':
            return credit
        elif formula == 'db_cr':
            return debit - credit
        elif formula == 'cr_db':
            return credit - debit
        elif formula == 'base_calc_db':
            return tax_base if debit > 0 else 0
        elif formula == 'base_calc_cr':
            return tax_base if credit > 0 else 0
        elif formula == 'base_calc_db_cr':
            return tax_base if (debit - credit) != 0 else 0
        elif formula == 'base_calc_cr_db':
            return tax_base if (credit - debit) != 0 else 0
        elif formula == 'tax_base_amount':
            return tax_base

        return balance

    def apply_slice(self, value):
        """Recorta el valor segun la configuracion xsd_slice.

        Retorna siempre string. Para last_X, aplica zfill para preservar ceros
        a la izquierda (ej: 8001 con last_3 -> '001', 1 con last_3 -> '001').
        """
        self.ensure_one()
        if not self.xsd_slice or self.xsd_slice == 'none':
            return value
        if value is None or value is False or value == '':
            return ''
        if isinstance(value, float):
            import math
            if math.isnan(value):
                return ''
            if value == int(value):
                str_val = str(int(value))
            else:
                str_val = str(value)
        else:
            str_val = str(value).strip()
        if not str_val or str_val.lower() in ('false', 'none', 'nan'):
            return ''
        if self.xsd_slice == 'last_2':
            return str_val[-2:].zfill(2)
        if self.xsd_slice == 'last_3':
            return str_val[-3:].zfill(3)
        if self.xsd_slice == 'last_4':
            return str_val[-4:].zfill(4)
        if self.xsd_slice == 'first_2':
            return str_val[:2]
        if self.xsd_slice == 'first_3':
            return str_val[:3]
        return str_val

    def apply_value_transformations(self, value, uvt_value=0):
        """Aplica transformaciones completas: porcentaje, limite, signo, redondeo

        Orden de aplicacion:
        1. Porcentaje (ej: 50% del valor)
        2. Limite por monto o UVT
        3. Tratamiento de signo
        4. Redondeo
        5. Valor por defecto si es cero

        Args:
            value: valor numerico a transformar
            uvt_value: valor de la UVT del periodo fiscal (para limites en UVT)
        """
        self.ensure_one()
        import math

        if value is None or (isinstance(value, (int, float)) and value == 0):
            if self.default_value:
                try:
                    return float(self.default_value)
                except (ValueError, TypeError):
                    return self.default_value
            return value

        if not isinstance(value, (int, float)):
            return value

        # 1. Porcentaje
        if self.formula_percentage and self.formula_percentage != 100.0:
            value = value * (self.formula_percentage / 100.0)

        # 2. Limite por monto o UVT
        if self.formula_limit_type == 'fixed_amount' and self.formula_limit_value:
            if abs(value) > self.formula_limit_value:
                value = self.formula_limit_value if value > 0 else -self.formula_limit_value
        elif self.formula_limit_type == 'uvt' and self.formula_limit_value and uvt_value:
            limit_cop = self.formula_limit_value * uvt_value
            if abs(value) > limit_cop:
                value = limit_cop if value > 0 else -limit_cop

        # 3. Tratamiento de signo
        if self.sign_type == 'absolute':
            value = abs(value)
        elif self.sign_type == 'positive_only':
            value = max(value, 0)
        elif self.sign_type == 'invert':
            value = -value

        # 4. Redondeo
        if self.rounding_type == 'ceil':
            value = math.ceil(value)
        elif self.rounding_type == 'floor':
            value = math.floor(value)
        elif self.rounding_type == 'truncate':
            value = int(value)
        elif self.rounding_type == 'round':
            value = round(value)

        return value