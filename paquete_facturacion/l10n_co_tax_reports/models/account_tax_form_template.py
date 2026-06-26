# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class TaxFormTemplate(models.Model):
    _name = 'account.tax.form.template'
    _description = 'Plantilla de Formulario Fiscal DIAN'
    _order = 'code, year desc'

    name = fields.Char('Nombre Formulario', required=True)
    code = fields.Char('Código', required=True, help='Ej: F300, F350, ICA-BOG')
    year = fields.Integer('Año Vigencia', required=True, default=lambda s: fields.Date.today().year)
    active = fields.Boolean('Activo', default=True)
    description = fields.Text('Descripción')

    form_type = fields.Selection([
        ('300', 'Form. 300 - IVA'),
        ('350', 'Form. 350 - ReteFuente'),
        ('ica', 'ICA Municipal'),
    ], string='Tipo Formulario', required=True)

    period_type = fields.Selection([
        ('monthly', 'Mensual'),
        ('bimonthly', 'Bimestral'),
        ('quarterly', 'Trimestral'),
        ('yearly', 'Anual'),
    ], string='Periodicidad', default='monthly', required=True)

    line_ids = fields.One2many('account.tax.form.template.line', 'form_id', 'Líneas del Formulario')
    company_id = fields.Many2one('res.company', 'Compañía', default=lambda s: s.env.company)

    # Filtro por ciudad (para ICA)
    city_id = fields.Many2one(
        'res.city',
        'Ciudad',
        help='Filtrar por ciudad específica (útil para ICA municipal)'
    )

    # Prorrateo IVA (Form. 300)
    enable_proration = fields.Boolean(
        'Habilitar Prorrateo IVA',
        help='Activa el prorrateo de IVA para operaciones mixtas (gravadas + excluidas/exentas)'
    )
    proration_coefficient = fields.Float(
        'Coeficiente Prorrateo',
        digits=(5, 4),
        help='Coeficiente = Ventas Gravadas / Ventas Totales. Ejemplo: 0.6000 (60%)'
    )

    # Cierre contable
    tax_agency_partner_id = fields.Many2one(
        'res.partner',
        'Agencia de Impuestos',
        help='Tercero por defecto para cierre (DIAN, Municipio, etc). Usado si no hay cuenta/tercero específico en línea.'
    )
    use_same_partner_for_closing = fields.Boolean(
        'Usar Mismo Tercero en Cierre',
        default=True,
        help='Si activo, usa el mismo tercero (agencia) para todas las líneas de cierre'
    )
    closing_account_id = fields.Many2one(
        'account.account',
        'Cuenta de Cierre (Contrapartida)',
        help='Cuenta donde se genera la contrapartida para cuadrar el asiento (ej: Resultados del Ejercicio, Bancos, etc.)'
    )

    _sql_constraints = [
        ('code_year_unique', 'unique(code, year, company_id)',
         'Ya existe una plantilla con este código para este año!')
    ]

    def action_create_form_300(self):
        """Crea plantilla Form. 300 con todas las casillas usando shortcuts de fórmulas"""
        self.ensure_one()
        self.line_ids.unlink()

        lines = [
            # (code, name, type, person_type, tax_rate, sequence, formula, formula_tag)
            # INGRESOS GRAVADOS
            ('27', 'Por operaciones gravadas al 5%', 'base', 'both', 5.0, 10, None, 'ingresos'),
            ('28', 'Por operaciones gravadas tarifa general 19%', 'base', 'both', 19.0, 20, None, 'ingresos'),
            ('29', 'A.I.U. gravado', 'base', 'both', None, 30, None, 'ingresos'),
            ('30', 'Exportación de bienes', 'base', 'both', 0.0, 40, None, 'ingresos'),
            ('31', 'Exportación de servicios', 'base', 'both', 0.0, 50, None, 'ingresos'),
            ('32', 'Ventas a sociedades de comercialización internacional', 'base', 'both', 0.0, 60, None, 'ingresos'),
            ('33', 'Ventas a zona franca', 'base', 'both', 0.0, 70, None, 'ingresos'),
            ('34', 'Juegos de suerte y azar', 'base', 'both', 19.0, 80, None, 'ingresos'),
            ('35', 'Por operaciones exentas', 'base', 'both', 0.0, 90, None, 'ingresos'),
            ('39', 'Por operaciones excluidas', 'base', 'both', 0.0, 100, None, 'ingresos'),

            # TOTALES INGRESOS
            ('41', 'Total ingresos brutos', 'formula', 'both', None, 110, '27+28+29+30+31+32+33+34+35+39', None),
            ('42', 'Devoluciones en ventas', 'base', 'both', None, 120, None, None),
            ('43', 'Total ingresos netos', 'formula', 'both', None, 130, '41-42', None),

            # COMPRAS/IMPORTACIONES
            ('44', 'Importaciones gravadas 5%', 'base', 'both', 5.0, 140, None, 'compras'),
            ('45', 'Importaciones gravadas 19%', 'base', 'both', 19.0, 150, None, 'compras'),
            ('50', 'Compras nacionales gravadas 5%', 'base', 'both', 5.0, 160, None, 'compras'),
            ('51', 'Compras nacionales gravadas 19%', 'base', 'both', 19.0, 170, None, 'compras'),
            ('52', 'Servicios gravados 5%', 'base', 'both', 5.0, 180, None, 'compras'),
            ('53', 'Servicios gravados 19%', 'base', 'both', 19.0, 190, None, 'compras'),

            # TOTALES COMPRAS
            ('55', 'Total compras brutas', 'formula', 'both', None, 200, '44+45+50+51+52+53', None),
            ('56', 'Devoluciones en compras', 'base', 'both', None, 210, None, None),
            ('57', 'Total compras netas', 'formula', 'both', None, 220, '55-56', None),

            # IVA GENERADO
            ('58', 'IVA generado tarifa 5%', 'tax', 'both', 5.0, 230, None, 'iva_generado'),
            ('59', 'IVA generado tarifa 19%', 'tax', 'both', 19.0, 240, None, 'iva_generado'),
            ('67', 'Total IVA generado', 'formula', 'both', None, 250, '58+59', None),

            # IVA DESCONTABLE
            ('68', 'IVA importaciones 5%', 'tax', 'both', 5.0, 260, None, 'iva_descontable'),
            ('69', 'IVA importaciones 19%', 'tax', 'both', 19.0, 270, None, 'iva_descontable'),
            ('71', 'IVA compras nacionales 5%', 'tax', 'both', 5.0, 280, None, 'iva_descontable'),
            ('72', 'IVA compras nacionales 19%', 'tax', 'both', 19.0, 290, None, 'iva_descontable'),
            ('73', 'IVA compras activos fijos gravados 5%', 'tax', 'both', 5.0, 295, None, 'iva_descontable'),
            ('74', 'IVA compras activos fijos gravados 19%', 'tax', 'both', 19.0, 296, None, 'iva_descontable'),
            ('75', 'IVA servicios gravados 5%', 'tax', 'both', 5.0, 297, None, 'iva_descontable'),
            ('76', 'IVA servicios gravados 19%', 'tax', 'both', 19.0, 298, None, 'iva_descontable'),
            ('77', 'IVA importación activos fijos gravados 5%', 'tax', 'both', 5.0, 299, None, 'iva_descontable'),
            ('78', 'IVA importación activos fijos gravados 19%', 'tax', 'both', 19.0, 300, None, 'iva_descontable'),
            ('79', 'IVA servicio extranjero/residentes exterior', 'tax', 'both', None, 301, None, 'iva_descontable'),
            ('80', 'IVA juegos suerte y azar (descontable)', 'tax', 'both', None, 302, None, 'iva_descontable'),

            # PRORRATEO
            ('80A', 'IVA descontable ANTES de prorrateo', 'formula', 'both', None, 305, '68+69+71+72+73+74+75+76+77+78+79+80', None),
            ('80B', 'Ajuste por prorrateo (IVA no descontable)', 'formula', 'both', None, 306, "line_vals.get('80A', 0) * (1 - (template.proration_coefficient or 0)) if template.enable_proration else 0", None),

            # TOTALES FINALES
            ('81', 'Total impuestos descontables', 'formula', 'both', None, 310, '80A - 80B', None),
            ('82', 'Saldo a pagar', 'formula', 'both', None, 320, 'max(67 - 81, 0)', None),
            ('83', 'Saldo a favor', 'formula', 'both', None, 330, 'max(81 - 67, 0)', None),
        ]

        for code, name, ltype, ptype, rate, seq, formula, tag in lines:
            self.env['account.tax.form.template.line'].create({
                'form_id': self.id,
                'code': code,
                'name': name,
                'type': ltype,
                'person_type': ptype,
                'tax_rate': rate,
                'sequence': seq,
                'formula': formula,
                'formula_tag': tag,
            })

        return True

    def action_create_form_350(self):
        """Crea plantilla Form. 350 con todas las casillas usando shortcuts de fórmulas"""
        self.ensure_one()
        self.line_ids.unlink()

        lines = [
            # (code, name, type, person_type, tax_rate, sequence, formula, formula_tag)
            # RETENCIONES PJ - BASE
            ('29', 'Honorarios PJ - Base', 'base', 'PJ', 11.0, 10, None, None),
            ('30', 'Comisiones PJ - Base', 'base', 'PJ', 11.0, 20, None, None),
            ('31', 'Servicios PJ - Base', 'base', 'PJ', 4.0, 30, None, None),
            ('32', 'Rendimientos financieros PJ - Base', 'base', 'PJ', 7.0, 40, None, None),
            ('33', 'Arrendamientos PJ - Base', 'base', 'PJ', 3.5, 50, None, None),
            ('36', 'Compras PJ - Base', 'base', 'PJ', 2.5, 60, None, None),

            # RETENCIONES PJ - VALOR
            ('42', 'Honorarios PJ - Retención', 'tax', 'PJ', 11.0, 70, None, 'rete_pj'),
            ('43', 'Comisiones PJ - Retención', 'tax', 'PJ', 11.0, 80, None, 'rete_pj'),
            ('44', 'Servicios PJ - Retención', 'tax', 'PJ', 4.0, 90, None, 'rete_pj'),
            ('45', 'Rendimientos financieros PJ - Retención', 'tax', 'PJ', 7.0, 100, None, 'rete_pj'),
            ('46', 'Arrendamientos PJ - Retención', 'tax', 'PJ', 3.5, 110, None, 'rete_pj'),
            ('49', 'Compras PJ - Retención', 'tax', 'PJ', 2.5, 120, None, 'rete_pj'),

            # RETENCIONES PN - BASE
            ('79', 'Honorarios PN - Base', 'base', 'PN', 10.0, 130, None, None),
            ('80', 'Comisiones PN - Base', 'base', 'PN', 10.0, 140, None, None),
            ('81', 'Servicios PN - Base', 'base', 'PN', 4.0, 150, None, None),
            ('83', 'Arrendamientos PN - Base', 'base', 'PN', 3.5, 160, None, None),
            ('86', 'Compras PN - Base', 'base', 'PN', 2.5, 170, None, None),

            # RETENCIONES PN - VALOR
            ('95', 'Honorarios PN - Retención', 'tax', 'PN', 10.0, 180, None, 'rete_pn'),
            ('96', 'Comisiones PN - Retención', 'tax', 'PN', 10.0, 190, None, 'rete_pn'),
            ('97', 'Servicios PN - Retención', 'tax', 'PN', 4.0, 200, None, 'rete_pn'),
            ('99', 'Arrendamientos PN - Retención', 'tax', 'PN', 3.5, 210, None, 'rete_pn'),
            ('102', 'Compras PN - Retención', 'tax', 'PN', 2.5, 220, None, 'rete_pn'),

            # RETENCIONES IVA
            ('131', 'ReteIVA régimen común', 'tax', 'both', None, 230, None, 'rete_iva'),

            # TOTALES
            ('130', 'Total retenciones renta', 'formula', 'both', None, 240, '42+43+44+45+46+49+95+96+97+99+102', None),
            ('134', 'Total retenciones IVA', 'formula', 'both', None, 250, '131', None),
            ('136', 'Total retenciones', 'formula', 'both', None, 260, '130+134', None),
        ]

        for code, name, ltype, ptype, rate, seq, formula, tag in lines:
            self.env['account.tax.form.template.line'].create({
                'form_id': self.id,
                'code': code,
                'name': name,
                'type': ltype,
                'person_type': ptype,
                'tax_rate': rate,
                'sequence': seq,
                'formula': formula,
                'formula_tag': tag,
            })

        return True


class TaxFormTemplateLine(models.Model):
    _name = 'account.tax.form.template.line'
    _description = 'Línea Plantilla Formulario'
    _order = 'sequence, code'

    form_id = fields.Many2one('account.tax.form.template', 'Formulario', required=True, ondelete='cascade')
    name = fields.Char('Descripción', required=True)
    code = fields.Char('Casilla', required=True, help='Número de casilla en formulario DIAN')
    sequence = fields.Integer('Secuencia', default=10)

    type = fields.Selection([
        ('base', 'Base Gravable'),
        ('tax', 'Impuesto/Retención'),
        ('tax_base_seq', 'Impuesto (usa base de otra casilla)'),
        ('formula', 'Cálculo Automático'),
    ], string='Tipo', required=True, default='base')

    person_type = fields.Selection([
        ('PJ', 'Persona Jurídica'),
        ('PN', 'Persona Natural'),
        ('both', 'Ambos'),
    ], string='Tipo Persona', required=True, default='both')

    tax_rate = fields.Float('Tarifa (%)', help='Tarifa del impuesto para búsqueda automática')
    formula = fields.Char('Fórmula Cálculo', help='Expresión Python para líneas calculadas')
    formula_tag = fields.Char('Etiqueta Fórmula', help='Etiqueta para agrupar líneas en sumas (ej: iva_compras, honorarios)')

    # Campos para tax_base_seq
    base_sequence_code = fields.Char(
        'Código Casilla Base',
        help='Para tipo tax_base_seq: código de casilla base (ej: "29")'
    )

    # Filtros para búsqueda automática
    tax_group_ids = fields.Many2many('account.tax.group', string='Grupos Impuesto')
    tax_ids = fields.Many2many('account.tax', string='Impuestos Específicos')
    account_ids = fields.Many2many(
        'account.account',
        'tax_form_line_account_rel',
        'line_id',
        'account_id',
        string='Cuentas Contables',
        help='Cuentas específicas para buscar movimientos (opcional)'
    )
    activity_id = fields.Many2one(
        'lavish.ciiu',
        'Actividad CIIU',
        help='Actividad económica específica (para liquidación ICA por actividad)'
    )

    # Filtros adicionales
    journal_ids = fields.Many2many(
        'account.journal',
        'tax_form_line_journal_rel',
        'line_id',
        'journal_id',
        string='Diarios',
        help='Filtrar solo movimientos de estos diarios (ventas, compras, etc.)'
    )
    product_category_ids = fields.Many2many(
        'product.category',
        'tax_form_line_product_categ_rel',
        'line_id',
        'category_id',
        string='Categorías de Producto',
        help='Filtrar por categoría de producto (para gastos/ingresos específicos)'
    )

    # Campos para cierre contable
    label = fields.Char('Etiqueta', help='Etiqueta para identificar la línea en reportes')
    debit_account_id = fields.Many2one('account.account', 'Cuenta Débito Cierre')
    credit_account_id = fields.Many2one('account.account', 'Cuenta Crédito Cierre')
    partner_id = fields.Many2one(
        'res.partner',
        'Tercero Específico',
        help='Tercero específico para esta línea. Si está vacío, usa el de la agencia de impuestos del template.'
    )
    mark_as_payable = fields.Boolean('Marcar como Por Pagar', help='Indica si esta línea genera un saldo por pagar')

    help_text = fields.Text('Ayuda')
