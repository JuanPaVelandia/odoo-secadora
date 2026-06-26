# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.safe_eval import safe_eval
from datetime import date
import re
import math


class TaxFormDeclaration(models.Model):
    _name = 'account.tax.form.declaration'
    _description = 'Declaración Tributaria DIAN'
    _order = 'date_from desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char('Número Declaración', required=True, copy=False, default='Borrador')
    template_id = fields.Many2one('account.tax.form.template', 'Plantilla', required=True, tracking=True)
    company_id = fields.Many2one('res.company', 'Compañía', required=True, default=lambda s: s.env.company)

    # Periodo
    date_from = fields.Date('Fecha Desde', required=True, tracking=True)
    date_to = fields.Date('Fecha Hasta', required=True, tracking=True)

    # Líneas calculadas
    line_ids = fields.One2many('account.tax.form.declaration.line', 'declaration_id', 'Líneas')

    state = fields.Selection([
        ('draft', 'Borrador'),
        ('calculated', 'Calculado'),
        ('submitted', 'Presentado'),
        ('cancelled', 'Cancelado'),
    ], string='Estado', default='draft', tracking=True)

    # Información datos calculados
    form_type = fields.Selection(related='template_id.form_type', string='Tipo Formulario', store=True)
    total_amount = fields.Monetary('Total a Pagar/Favor', compute='_compute_totals', store=True)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')

    notes = fields.Text('Observaciones')

    @api.depends('line_ids.value_base', 'line_ids.value_tax')
    def _compute_totals(self):
        """Calcula totales según tipo de formulario"""
        for declaration in self:
            if declaration.form_type == '300':
                # Form 300: Diferencia IVA generado vs descontable
                line_82 = declaration.line_ids.filtered(lambda l: l.code == '82')
                line_83 = declaration.line_ids.filtered(lambda l: l.code == '83')
                declaration.total_amount = (line_82.value_tax if line_82 else 0.0) - (line_83.value_tax if line_83 else 0.0)
            elif declaration.form_type == '350':
                # Form 350: Total retenciones
                line_136 = declaration.line_ids.filtered(lambda l: l.code == '136')
                declaration.total_amount = line_136.value_tax if line_136 else 0.0
            else:
                declaration.total_amount = sum(declaration.line_ids.mapped('value_tax'))

    def action_calculate(self):
        """Calcula todas las líneas de la declaración"""
        self.ensure_one()

        if self.state != 'draft':
            raise UserError('Solo se pueden calcular declaraciones en borrador')

        # Eliminar líneas existentes
        self.line_ids.unlink()

        # Calcular cada línea de la plantilla
        line_vals_dict = {}  # {code: value} para fórmulas

        for template_line in self.template_id.line_ids.sorted('sequence'):
            values = self._calculate_line(template_line, line_vals_dict)

            # Crear línea de declaración
            declaration_line = self.env['account.tax.form.declaration.line'].create({
                'declaration_id': self.id,
                'template_line_id': template_line.id,
                'code': template_line.code,
                'name': template_line.name,
                'value_base': values.get('base', 0.0),
                'value_tax': values.get('tax', 0.0),
            })

            # Guardar valor para fórmulas posteriores
            line_vals_dict[template_line.code] = values.get('tax', 0.0) or values.get('base', 0.0)

        self.state = 'calculated'
        return True

    def _calculate_line(self, template_line, line_vals_dict):
        """
        Calcula valores para una línea específica

        Args:
            template_line: Línea de la plantilla
            line_vals_dict: Dict con valores calculados {code: value}

        Returns:
            dict: {'base': float, 'tax': float}
        """
        self.ensure_one()

        if template_line.type == 'base':
            return self._calculate_base_line(template_line)

        elif template_line.type == 'tax':
            return self._calculate_tax_line(template_line)

        elif template_line.type == 'tax_base_seq':
            return self._calculate_tax_base_seq_line(template_line, line_vals_dict)

        elif template_line.type == 'formula':
            return self._calculate_formula_line(template_line, line_vals_dict)

        return {'base': 0.0, 'tax': 0.0}

    def _calculate_base_line(self, template_line):
        """Calcula líneas tipo 'base' - Base gravable"""
        domain = self._get_base_domain(template_line)

        # Ejecutar query
        query = self._build_tax_query(template_line, 'base')
        self.env.cr.execute(query, {
            'date_from': self.date_from,
            'date_to': self.date_to,
            'company_id': self.company_id.id,
        })

        result = self.env.cr.fetchone()
        base_amount = result[0] if result and result[0] else 0.0

        return {'base': base_amount, 'tax': 0.0}

    def _calculate_tax_line(self, template_line):
        """Calcula líneas tipo 'tax' - Impuesto/Retención"""
        query = self._build_tax_query(template_line, 'tax')
        self.env.cr.execute(query, {
            'date_from': self.date_from,
            'date_to': self.date_to,
            'company_id': self.company_id.id,
        })

        result = self.env.cr.fetchone()
        tax_amount = result[0] if result and result[0] else 0.0

        return {'base': 0.0, 'tax': tax_amount}

    def _calculate_tax_base_seq_line(self, template_line, line_vals_dict):
        """Calcula líneas tipo 'tax_base_seq' - Impuesto que usa base de otra casilla"""
        if not template_line.base_sequence_code:
            return {'base': 0.0, 'tax': 0.0}

        # Buscar valor de la casilla base
        base_value = line_vals_dict.get(template_line.base_sequence_code, 0.0)

        # Calcular impuesto
        if template_line.tax_rate:
            tax_value = base_value * (template_line.tax_rate / 100.0)
        else:
            tax_value = 0.0

        return {'base': base_value, 'tax': tax_value}

    def _calculate_formula_line(self, template_line, line_vals_dict):
        """
        Calcula líneas tipo 'formula' - Calculadas con expresión Python

        Soporta shortcuts:
        - SUM_BASE[27,28,29] - Suma bases de casillas 27, 28, 29
        - SUM_TAX[68:80] - Suma impuestos de casillas 68 a 80
        - SUM_BASE[tag='iva_compras'] - Suma bases con etiqueta
        - Fórmulas Python normales: line_vals['27'] + line_vals['28']
        """
        if not template_line.formula:
            return {'base': 0.0, 'tax': 0.0}

        formula = template_line.formula.strip()

        try:
            # Procesar shortcuts
            result = self._process_formula_shortcuts(formula, line_vals_dict)

            # Si no se procesó como shortcut, evaluar como fórmula Python
            if result is None:
                # Contexto para safe_eval con funciones matemáticas
                eval_context = {
                    'line_vals': line_vals_dict,
                    # Funciones básicas Python
                    'sum': sum,
                    'abs': abs,
                    'max': max,
                    'min': min,
                    'round': round,
                    'int': int,
                    'float': float,
                    # Funciones matemáticas (math module)
                    'sqrt': math.sqrt,           # Raíz cuadrada
                    'pow': math.pow,             # Potencia
                    'exp': math.exp,             # Exponencial
                    'log': math.log,             # Logaritmo natural
                    'log10': math.log10,         # Logaritmo base 10
                    'ceil': math.ceil,           # Redondeo hacia arriba
                    'floor': math.floor,         # Redondeo hacia abajo
                    'trunc': math.trunc,         # Truncar decimales
                    # Trigonométricas
                    'sin': math.sin,
                    'cos': math.cos,
                    'tan': math.tan,
                    'asin': math.asin,
                    'acos': math.acos,
                    'atan': math.atan,
                    # Constantes matemáticas
                    'pi': math.pi,
                    'e': math.e,
                    # Contexto del formulario
                    'company': self.company_id,
                    'template': self.template_id,
                    # Helpers personalizados
                    'SUM_BASE': lambda codes: self._sum_by_codes(codes, 'base', line_vals_dict),
                    'SUM_TAX': lambda codes: self._sum_by_codes(codes, 'tax', line_vals_dict),
                }
                result = safe_eval(formula, eval_context, mode='eval', nocopy=True)

            return {'base': 0.0, 'tax': float(result) if result else 0.0}

        except Exception as e:
            raise UserError(f"Error al evaluar fórmula en casilla {template_line.code}: {str(e)}\nFórmula: {formula}")

    def _process_formula_shortcuts(self, formula, line_vals_dict):
        """
        Procesa shortcuts en fórmulas:
        - SUM_BASE[27,28,29] -> suma bases de casillas
        - SUM_TAX[68:80] -> suma impuestos de rango
        - SUM_BASE[tag='iva_compras'] -> suma bases con etiqueta
        - 50+51+52 -> suma simple de casillas

        Returns:
            float o None si no es un shortcut
        """
        import re

        # Pattern 1: SUM_BASE[...] o SUM_TAX[...]
        pattern_sum = r'(SUM_BASE|SUM_TAX)\[(.*?)\]'
        match = re.match(pattern_sum, formula)
        if match:
            sum_type = 'base' if match.group(1) == 'SUM_BASE' else 'tax'
            content = match.group(2).strip()

            # Procesar contenido
            codes = self._parse_code_list(content)
            return sum(line_vals_dict.get(code, 0.0) for code in codes)

        # Pattern 2: Fórmulas con códigos de casillas (50+51*52, etc)
        # Detectar si tiene códigos de casillas (números de 1-3 dígitos y letras opcionales)
        pattern_with_codes = r'[A-Z]?\d{1,3}[A-Z]?'
        if re.search(pattern_with_codes, formula):
            # Reemplazar códigos por valores usando mapeo
            formula_eval = self._map_codes_to_values(formula, line_vals_dict)
            try:
                # eval() respeta el orden de operaciones matemáticas
                return eval(formula_eval)
            except Exception as e:
                raise UserError(f"Error evaluando fórmula: {formula}\nError: {str(e)}")

        return None

    def _map_codes_to_values(self, formula, line_vals_dict):
        """
        Mapea códigos de casillas a sus valores en la fórmula

        Soporta códigos como:
        - Numéricos: 27, 28, 80A, 80B
        - Con prefijo: L5, A10

        Respeta orden de operaciones PEMDAS (Python nativo + math module):
        - Paréntesis: (2 + 3) * 4 = 20
        - Exponentes: 2 ** 3 = 8 o pow(2, 3) = 8
        - Multiplicación/División: 1 + 5 * 3 = 16 (no 18)
        - Adición/Sustracción: izquierda a derecha

        Ejemplos:
        - "27 + 28 * 1.19" → "1000 + 2000 * 1.19" → 3380.0 (no 3570.0)
        - "(27 + 28) * 1.19" → "(1000 + 2000) * 1.19" → 3570.0
        - "sqrt(27)" → "sqrt(1000)" → 31.62
        - "pow(28, 2)" → "pow(2000, 2)" → 4000000.0

        Args:
            formula: Fórmula con códigos (ej: "27+28*1.19")
            line_vals_dict: Dict con valores {code: value}

        Returns:
            str: Fórmula con valores (ej: "1000+2000*1.19")
        """
        formula_eval = formula

        # Ordenar códigos por longitud descendente para evitar reemplazos parciales
        # Ej: Reemplazar "80A" antes de "80"
        sorted_codes = sorted(line_vals_dict.keys(), key=lambda x: len(str(x)), reverse=True)

        for code in sorted_codes:
            value = line_vals_dict.get(code, 0.0)
            # Reemplazar solo si el código está como palabra completa
            # Soporta códigos alfanuméricos: 80A, L5, etc.
            pattern = r'\b' + re.escape(str(code)) + r'\b'
            formula_eval = re.sub(pattern, str(value), formula_eval)

        return formula_eval

    def _parse_code_list(self, content):
        """
        Parsea lista de códigos:
        - '27,28,29' -> ['27', '28', '29']
        - '68:80' -> ['68', '69', ..., '80']
        - "tag='iva_compras'" -> busca líneas con ese tag
        """
        codes = []

        # Tag filter
        if 'tag=' in content:
            tag_match = re.search(r"tag=['\"]([^'\"]+)['\"]", content)
            if tag_match:
                tag = tag_match.group(1)
                # Buscar líneas de plantilla con ese tag
                tagged_lines = self.template_id.line_ids.filtered(lambda l: l.formula_tag == tag)
                codes = [line.code for line in tagged_lines]
                return codes

        # Range (68:80)
        if ':' in content:
            parts = content.split(':')
            if len(parts) == 2:
                try:
                    start = int(parts[0].strip())
                    end = int(parts[1].strip())
                    codes = [str(i) for i in range(start, end + 1)]
                    return codes
                except:
                    pass

        # Comma separated (27,28,29)
        if ',' in content:
            codes = [c.strip() for c in content.split(',')]
            return codes

        # Single code
        codes = [content.strip()]
        return codes

    def _sum_by_codes(self, codes, value_type, line_vals_dict):
        """
        Helper para sumar valores por códigos

        Args:
            codes: lista de códigos o string separado por comas
            value_type: 'base' o 'tax' (no usado actualmente, line_vals_dict ya tiene los valores correctos)
            line_vals_dict: dict con valores calculados
        """
        if isinstance(codes, str):
            codes = [c.strip() for c in codes.split(',')]

        return sum(line_vals_dict.get(code, 0.0) for code in codes)

    def _build_tax_query(self, template_line, query_type):
        """
        Construye query SQL para buscar bases o impuestos

        Args:
            template_line: Línea de plantilla
            query_type: 'base' o 'tax'
        """
        # Base query
        if query_type == 'base':
            select_field = 'SUM(aml.balance * -1)'  # Invertir signo para bases
        else:
            select_field = 'SUM(aml.balance)'

        query = f"""
            SELECT {select_field}
            FROM account_move_line aml
            INNER JOIN account_move am ON am.id = aml.move_id
            INNER JOIN account_account aa ON aa.id = aml.account_id
            LEFT JOIN account_tax at ON at.id = aml.tax_line_id
            LEFT JOIN res_partner rp ON rp.id = aml.partner_id
            LEFT JOIN product_product pp ON pp.id = aml.product_id
            LEFT JOIN product_template pt ON pt.id = pp.product_tmpl_id
            WHERE am.state = 'posted'
                AND am.company_id = %(company_id)s
                AND am.date >= %(date_from)s
                AND am.date <= %(date_to)s
        """

        # Filtro por tarifa
        if template_line.tax_rate is not None:
            query += f" AND at.amount = {template_line.tax_rate}"

        # Filtro por cuentas específicas (Many2many)
        if template_line.account_ids:
            account_ids_str = ','.join(str(aid) for aid in template_line.account_ids.ids)
            query += f" AND aml.account_id IN ({account_ids_str})"

        # Filtro por tipo de persona (PJ/PN)
        if template_line.person_type == 'PJ':
            query += " AND rp.is_company = TRUE"
        elif template_line.person_type == 'PN':
            query += " AND (rp.is_company = FALSE OR rp.is_company IS NULL)"

        # Filtro por impuestos específicos
        if template_line.tax_ids:
            tax_ids_str = ','.join(str(tid) for tid in template_line.tax_ids.ids)
            query += f" AND aml.tax_line_id IN ({tax_ids_str})"

        # Filtro por grupos de impuestos
        if template_line.tax_group_ids:
            group_ids_str = ','.join(str(gid) for gid in template_line.tax_group_ids.ids)
            query += f" AND at.tax_group_id IN ({group_ids_str})"

        # Filtro por diarios
        if template_line.journal_ids:
            journal_ids_str = ','.join(str(jid) for jid in template_line.journal_ids.ids)
            query += f" AND am.journal_id IN ({journal_ids_str})"

        # Filtro por categorías de producto
        if template_line.product_category_ids:
            category_ids_str = ','.join(str(cid) for cid in template_line.product_category_ids.ids)
            query += f" AND pt.categ_id IN ({category_ids_str})"

        return query

    def _get_base_domain(self, template_line):
        """Construye dominio Odoo para búsqueda de bases"""
        domain = [
            ('move_id.state', '=', 'posted'),
            ('move_id.company_id', '=', self.company_id.id),
            ('move_id.date', '>=', self.date_from),
            ('move_id.date', '<=', self.date_to),
        ]

        if template_line.account_ids:
            domain.append(('account_id', 'in', template_line.account_ids.ids))

        if template_line.person_type == 'PJ':
            domain.append(('partner_id.is_company', '=', True))
        elif template_line.person_type == 'PN':
            domain.append(('partner_id.is_company', '=', False))

        return domain

    def action_create_closing_entry(self):
        """Crea asiento contable de cierre de la declaración"""
        self.ensure_one()

        if self.state != 'calculated':
            raise UserError('Debe calcular la declaración primero')

        # Crear asiento contable
        move_vals = {
            'move_type': 'entry',
            'journal_id': self._get_default_journal().id,
            'date': self.date_to,
            'ref': f"{self.name} - Cierre {self.template_id.name}",
            'company_id': self.company_id.id,
        }

        # Construir líneas del asiento
        line_vals = []
        total_debit = 0.0
        total_credit = 0.0

        # Determinar tercero por defecto
        default_partner = self.template_id.tax_agency_partner_id if self.template_id.use_same_partner_for_closing else False

        for dec_line in self.line_ids.filtered(lambda l: l.debit or l.credit):
            # Determinar tercero para esta línea
            line_partner = False
            if dec_line.mark_as_payable:
                # Prioridad: 1) Tercero específico de línea, 2) Agencia de impuestos, 3) Ninguno
                line_partner = dec_line.partner_id.id or default_partner.id if default_partner else False

            # Línea de débito
            if dec_line.debit and dec_line.debit_account_id:
                line_vals.append((0, 0, {
                    'name': f"{dec_line.code} - {dec_line.name}",
                    'account_id': dec_line.debit_account_id.id,
                    'debit': dec_line.debit,
                    'credit': 0.0,
                    'partner_id': line_partner,
                }))
                total_debit += dec_line.debit

            # Línea de crédito
            if dec_line.credit and dec_line.credit_account_id:
                line_vals.append((0, 0, {
                    'name': f"{dec_line.code} - {dec_line.name}",
                    'account_id': dec_line.credit_account_id.id,
                    'debit': 0.0,
                    'credit': dec_line.credit,
                    'partner_id': line_partner,
                }))
                total_credit += dec_line.credit

        # Generar línea de contrapartida si hay diferencia
        difference = total_debit - total_credit

        if abs(difference) > 0.01:
            # Verificar que exista cuenta de cierre configurada
            if not self.template_id.closing_account_id:
                raise UserError(
                    f'El asiento no cuadra y no hay cuenta de cierre configurada:\n'
                    f'Total Débito: ${total_debit:,.2f}\n'
                    f'Total Crédito: ${total_credit:,.2f}\n'
                    f'Diferencia: ${abs(difference):,.2f}\n\n'
                    f'Configure la "Cuenta de Cierre (Contrapartida)" en el template.'
                )

            # Crear línea de contrapartida
            if difference > 0:
                # Hay más débito que crédito → agregar crédito
                line_vals.append((0, 0, {
                    'name': f'Contrapartida Cierre - {self.template_id.name}',
                    'account_id': self.template_id.closing_account_id.id,
                    'debit': 0.0,
                    'credit': abs(difference),
                    'partner_id': False,
                }))
                total_credit += abs(difference)
            else:
                # Hay más crédito que débito → agregar débito
                line_vals.append((0, 0, {
                    'name': f'Contrapartida Cierre - {self.template_id.name}',
                    'account_id': self.template_id.closing_account_id.id,
                    'debit': abs(difference),
                    'credit': 0.0,
                    'partner_id': False,
                }))
                total_debit += abs(difference)

        # Verificación final
        if abs(total_debit - total_credit) > 0.01:
            raise UserError(
                f'Error crítico: El asiento aún no cuadra después de contrapartida:\n'
                f'Total Débito: ${total_debit:,.2f}\n'
                f'Total Crédito: ${total_credit:,.2f}\n'
                f'Diferencia: ${abs(total_debit - total_credit):,.2f}'
            )

        if not line_vals:
            raise UserError('No hay líneas configuradas para generar el asiento de cierre')

        move_vals['line_ids'] = line_vals

        # Crear asiento
        move = self.env['account.move'].create(move_vals)

        # Abrir el asiento creado
        return {
            'type': 'ir.actions.act_window',
            'name': 'Asiento de Cierre',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': move.id,
            'target': 'current',
        }

    def _get_default_journal(self):
        """Obtiene el diario por defecto para asientos de cierre"""
        journal = self.env['account.journal'].search([
            ('company_id', '=', self.company_id.id),
            ('type', '=', 'general'),
        ], limit=1)

        if not journal:
            raise UserError('No se encontró un diario contable de tipo "General" para crear el asiento')

        return journal

    def action_submit(self):
        """Marca declaración como presentada"""
        self.ensure_one()
        if self.state != 'calculated':
            raise UserError('Debe calcular la declaración antes de presentarla')
        self.state = 'submitted'

    def action_back_to_draft(self):
        """Regresa declaración a borrador"""
        self.ensure_one()
        self.state = 'draft'

    def action_cancel(self):
        """Cancela declaración"""
        self.ensure_one()
        self.state = 'cancelled'


class TaxFormDeclarationLine(models.Model):
    _name = 'account.tax.form.declaration.line'
    _description = 'Línea Declaración Tributaria'
    _order = 'sequence, code'

    declaration_id = fields.Many2one('account.tax.form.declaration', 'Declaración', required=True, ondelete='cascade')
    template_line_id = fields.Many2one('account.tax.form.template.line', 'Línea Plantilla')

    code = fields.Char('Casilla', required=True)
    name = fields.Char('Descripción', required=True)
    label = fields.Char('Etiqueta', related='template_line_id.label', store=True)
    sequence = fields.Integer('Secuencia', related='template_line_id.sequence', store=True)

    # Valores calculados
    value_base = fields.Monetary('Base Gravable', currency_field='currency_id')
    value_tax = fields.Monetary('Valor Impuesto', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', related='declaration_id.company_id.currency_id')

    # Campos para cierre contable
    debit = fields.Monetary('Débito', currency_field='currency_id', compute='_compute_debit_credit', store=True)
    credit = fields.Monetary('Crédito', currency_field='currency_id', compute='_compute_debit_credit', store=True)
    debit_account_id = fields.Many2one('account.account', 'Cuenta Débito', related='template_line_id.debit_account_id')
    credit_account_id = fields.Many2one('account.account', 'Cuenta Crédito', related='template_line_id.credit_account_id')
    partner_id = fields.Many2one('res.partner', 'Tercero', related='template_line_id.partner_id', store=True)
    mark_as_payable = fields.Boolean('Por Pagar', related='template_line_id.mark_as_payable', store=True)

    # Periodo (tomado de la declaración)
    date_from = fields.Date('Fecha Desde', related='declaration_id.date_from', store=True)
    date_to = fields.Date('Fecha Hasta', related='declaration_id.date_to', store=True)

    notes = fields.Text('Notas')

    @api.depends('value_tax', 'template_line_id.type')
    def _compute_debit_credit(self):
        """
        Calcula débito/crédito según tipo de línea:
        - Para líneas de impuesto: se invierte el signo
        - Para otras líneas: valor normal
        """
        for line in self:
            amount = line.value_tax or 0.0

            # Para líneas de impuesto, invertir el signo
            if line.template_line_id.type == 'tax':
                line.debit = abs(amount) if amount < 0 else 0.0
                line.credit = abs(amount) if amount > 0 else 0.0
            else:
                # Para líneas base y fórmulas, mantener signo normal
                line.debit = abs(amount) if amount > 0 else 0.0
                line.credit = abs(amount) if amount < 0 else 0.0
