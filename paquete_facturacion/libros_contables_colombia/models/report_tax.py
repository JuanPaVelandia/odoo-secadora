# -*- coding: utf-8 -*-
"""
Reportes de Impuestos Colombianos - Versión Completa con 4 Niveles
================================================================
Versión que implementa la jerarquía completa de navegación:

NIVEL 0: Tributo (ej: [01] IVA)
├── NIVEL 1: Impuesto específico (ej: IVA VENTAS 19%)
    ├── NIVEL 2: Movimiento contable (ej: FACTURA FAC/2024/0001)
        ├── NIVEL 3: Línea base que originó el impuesto (ej: Producto vendido)

Esta estructura permite rastrear completamente el origen de cada impuesto.
"""

import re
from collections import defaultdict
from odoo import api, models, fields, _
from odoo.tools import get_lang, format_date, SQL
from odoo.tools.misc import formatLang
import logging

_logger = logging.getLogger(__name__)

class AccountTaxReportCOBase(models.AbstractModel):
    _name = 'account.tax.report.co.base'
    _inherit = ['account.tax.report.handler', 'sql.helper.mixin']
    _description = 'Base Colombian Tax Report Handler'

    def _get_tax_tributes(self):
        """Override este método en clases hijas para filtrar tributos específicos"""
        return []

    def _get_concept_types(self):
        """Override en clases hijas para filtrar por concept_type de withholding.concept"""
        return []

    def _get_report_name(self):
        """Override para establecer el nombre del reporte"""
        return _("Reporte de Impuestos")

    def _custom_options_initializer(self, report, options, previous_options=None):
        """Inicializa opciones personalizadas"""
        super()._custom_options_initializer(report, options, previous_options)

        # Agregar botón de exportación
        options['buttons'].append({
            'name': _('Exportar Detalle CO'),
            'sequence': 50,
            'action': 'export_detailed_tax_report_co',
        })

        # Forzar actualización de columnas
        self._ensure_columns_updated(report, options)

        # ========== FILTROS DE RETENCIÓN (tax_base_threshold) ==========
        # Inicializar filtros de concepto de retención
        self._init_withholding_filters(options, previous_options)

        # ========== OPCIÓN DE SALDO INICIAL ==========
        # Permite mostrar saldo de períodos anteriores
        options['include_tax_initial_balance'] = (previous_options or {}).get('include_tax_initial_balance', False)
        options['tax_initial_balance_date'] = (previous_options or {}).get('tax_initial_balance_date', False)

    def _init_withholding_filters(self, options, previous_options=None):
        """Inicializa los filtros de conceptos de retención desde tax_base_threshold"""

        # ========== FILTRO POR TIPO DE OPERACIÓN (Compra/Venta) ==========
        operation_types = [
            {'id': 'all', 'name': _('Todas las operaciones'), 'selected': True},
            {'id': 'purchase_all', 'name': _('Compras (Facturas + NC)'), 'selected': False},
            {'id': 'sale_all', 'name': _('Ventas (Facturas + NC)'), 'selected': False},
            {'id': 'purchase', 'name': _('Solo Facturas Proveedor'), 'selected': False},
            {'id': 'sale', 'name': _('Solo Facturas Cliente'), 'selected': False},
            {'id': 'purchase_refund', 'name': _('Solo NC Proveedor'), 'selected': False},
            {'id': 'sale_refund', 'name': _('Solo NC Cliente'), 'selected': False},
        ]

        # Restaurar selección previa de tipo de operación
        if previous_options and previous_options.get('operation_type_filter'):
            prev_op = previous_options['operation_type_filter']
            for ot in operation_types:
                ot['selected'] = (ot['id'] == prev_op)

        options['operation_type_filter'] = next(
            (ot['id'] for ot in operation_types if ot['selected']), 'all'
        )
        options['operation_types'] = operation_types

        # ========== FILTRO POR TIPO DE BIEN (Servicio/Bienes) ==========
        product_types = [
            {'id': 'all', 'name': _('Todos'), 'selected': True},
            {'id': 'service', 'name': _('Servicios'), 'selected': False},
            {'id': 'consu', 'name': _('Bienes (Consumibles)'), 'selected': False},
            {'id': 'product', 'name': _('Bienes (Almacenables)'), 'selected': False},
        ]

        if previous_options and previous_options.get('product_type_filter'):
            prev_pt = previous_options['product_type_filter']
            for pt in product_types:
                pt['selected'] = (pt['id'] == prev_pt)

        options['product_type_filter'] = next(
            (pt['id'] for pt in product_types if pt['selected']), 'all'
        )
        options['product_types'] = product_types

        # ========== FILTRO POR TIPO DE PERSONA (PJ/PN) ==========
        person_types = [
            {'id': 'all', 'name': _('Todos'), 'selected': True},
            {'id': 'company', 'name': _('Persona Jurídica (PJ)'), 'selected': False},
            {'id': 'person', 'name': _('Persona Natural (PN)'), 'selected': False},
        ]

        if previous_options and previous_options.get('person_type_filter'):
            prev_person = previous_options['person_type_filter']
            for pt in person_types:
                pt['selected'] = (pt['id'] == prev_person)

        options['person_type_filter'] = next(
            (pt['id'] for pt in person_types if pt['selected']), 'all'
        )
        options['person_types'] = person_types

        # ========== FILTRO POR CIUDAD ==========
        # Obtener ciudades disponibles para el filtro
        cities = self._get_cities_for_filter()

        # Restaurar selección previa de ciudades
        if previous_options and previous_options.get('city_ids'):
            prev_city_ids = previous_options['city_ids']
            for city in cities:
                city['selected'] = city['id'] in prev_city_ids

        options['cities'] = cities
        options['city_ids'] = [c['id'] for c in cities if c['selected']]

        # ========== FILTRO DE CUENTAS (Many2many dinámico) ==========
        accounts = self._get_accounts_for_filter(options)
        if previous_options and previous_options.get('account_ids'):
            prev_account_ids = previous_options['account_ids']
            for account in accounts:
                account['selected'] = account['id'] in prev_account_ids
        options['accounts'] = accounts
        options['account_ids'] = [a['id'] for a in accounts if a['selected']]

        # ========== FILTRO DE ETIQUETAS DE CUENTA ==========
        account_tags = self._get_account_tags_for_filter()
        if previous_options and previous_options.get('account_tag_ids'):
            prev_tag_ids = previous_options['account_tag_ids']
            for tag in account_tags:
                tag['selected'] = tag['id'] in prev_tag_ids
        options['account_tags'] = account_tags
        options['account_tag_ids'] = [t['id'] for t in account_tags if t['selected']]

        # ========== FILTRO DE NIVELES ==========
        levels = self._get_levels_for_filter()
        if previous_options and previous_options.get('level_ids') is not None:
            prev_level_ids = previous_options['level_ids']
            for level in levels:
                level['selected'] = level['id'] in prev_level_ids
        options['levels'] = levels
        options['level_ids'] = [l['id'] for l in levels if l['selected']]

        # ========== FILTRO POR CUENTA CONTABLE ==========
        options['account_filter'] = previous_options.get('account_filter', '') if previous_options else ''

        # ========== AGRUPACIÓN POR CUENTA ==========
        options['group_by_account'] = previous_options.get('group_by_account', False) if previous_options else False

        # ========== AGRUPACION POR TIPO DE PERSONA ==========
        options['group_by_person_type'] = previous_options.get('group_by_person_type', False) if previous_options else False

        # ========== SALDO INICIAL ==========
        options['show_initial_balance'] = previous_options.get('show_initial_balance', False) if previous_options else False

        # ========== FILTRO POR TIPO DE CONCEPTO ==========
        # Filtro por tipo de concepto (concept_type)
        concept_types = [
            {'id': 'all', 'name': _('Todos los tipos'), 'selected': True},
            {'id': 'retefuente', 'name': _('Retención en la Fuente'), 'selected': False},
            {'id': 'reteiva', 'name': _('Retención de IVA'), 'selected': False},
            {'id': 'reteica', 'name': _('Retención de ICA'), 'selected': False},
            {'id': 'inc', 'name': _('Impuesto Nacional al Consumo'), 'selected': False},
            {'id': 'iva', 'name': _('IVA'), 'selected': False},
            {'id': 'other', 'name': _('Otro'), 'selected': False},
        ]

        # Restaurar selección previa
        if previous_options and previous_options.get('concept_type_filter'):
            prev_type = previous_options['concept_type_filter']
            for ct in concept_types:
                ct['selected'] = (ct['id'] == prev_type)

        options['concept_type_filter'] = next(
            (ct['id'] for ct in concept_types if ct['selected']), 'all'
        )
        options['concept_types'] = concept_types

        # Filtro por concepto de retención específico
        withholding_concepts = self._get_withholding_concepts_for_filter()

        # Restaurar selección previa de conceptos
        if previous_options and previous_options.get('withholding_concept_ids'):
            prev_ids = previous_options['withholding_concept_ids']
            for wc in withholding_concepts:
                wc['selected'] = wc['id'] in prev_ids

        options['withholding_concepts'] = withholding_concepts
        options['withholding_concept_ids'] = [
            wc['id'] for wc in withholding_concepts if wc['selected']
        ]

        # Habilitar filtros en la UI
        options['show_withholding_filters'] = True

    def _get_withholding_concepts_for_filter(self):
        """Obtiene los conceptos de retención para el filtro"""
        concepts = []

        # Buscar conceptos de withholding.concept
        WithholdingConcept = self.env['withholding.concept']
        all_concepts = WithholdingConcept.search([('active', '=', True)], order='sequence, code')

        for concept in all_concepts:
            concepts.append({
                'id': concept.id,
                'code': concept.code,
                'name': f"[{concept.code}] {concept.name}",
                'concept_type': concept.concept_type,
                'selected': False,  # Por defecto no seleccionado (mostrar todos)
            })

        return concepts

    def _get_accounts_for_filter(self, options):
        """Obtiene cuentas con movimientos de impuestos para el filtro."""
        date_from = options.get('date', {}).get('date_from')
        date_to = options.get('date', {}).get('date_to')
        company_id = self.env.company.id

        # En Odoo 18, code está en code_store (JSONB) y name también es JSONB
        query = """
            SELECT DISTINCT aa.id,
                   COALESCE(aa.code_store->>%s, '') as code,
                   aa.name
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            JOIN account_account aa ON aa.id = aml.account_id
            WHERE am.state = 'posted'
              AND aml.tax_line_id IS NOT NULL
              AND am.company_id = %s
        """
        params = [str(company_id), company_id]

        if date_from:
            query += " AND aml.date >= %s"
            params.append(date_from)
        if date_to:
            query += " AND aml.date <= %s"
            params.append(date_to)

        query += " ORDER BY code"

        self._cr.execute(query, params)
        results = self._cr.fetchall()

        accounts = []
        lang = self.env.user.lang or 'en_US'
        for row in results:
            account_id, code, name = row
            # name es jsonb en Odoo 18
            if isinstance(name, dict):
                name = name.get(lang) or name.get('en_US') or list(name.values())[0] if name else ''
            accounts.append({
                'id': account_id,
                'name': f'{code} - {name}',
                'code': code,
                'selected': False
            })
        return accounts

    def _get_account_tags_for_filter(self):
        """Obtiene etiquetas de cuenta para el filtro."""
        tags = self.env['account.account.tag'].search([
            ('applicability', '=', 'accounts'),
            '|',
            ('country_id', '=', False),
            ('country_id', '=', self.env.company.country_id.id)
        ], order='name')

        return [{
            'id': tag.id,
            'name': tag.name,
            'selected': False
        } for tag in tags]

    def _get_levels_for_filter(self):
        """Obtiene niveles de agrupación disponibles."""
        return [
            {'id': 0, 'name': 'Grupos/Tributos', 'selected': True},
            {'id': 1, 'name': 'Impuestos', 'selected': True},
            {'id': 2, 'name': 'Cuentas', 'selected': True},
            {'id': 3, 'name': 'Movimientos', 'selected': True},
            {'id': 4, 'name': 'Líneas Base', 'selected': False},
        ]

    def _get_cities_for_filter(self):
        """Obtiene las ciudades disponibles para el filtro desde los partners con movimientos"""
        cities = []

        # Buscar ciudades únicas de partners que tienen movimientos contables
        query = """
            SELECT DISTINCT rc.id, rc.name, rcs.name as state_name
            FROM res_city rc
            JOIN res_partner rp ON rp.city_id = rc.id
            JOIN account_move_line aml ON aml.partner_id = rp.id
            LEFT JOIN res_country_state rcs ON rcs.id = rc.state_id
            WHERE aml.tax_line_id IS NOT NULL
            ORDER BY rcs.name, rc.name
        """
        self._cr.execute(query)

        for row in self._cr.dictfetchall():
            state_name = row.get('state_name', '')
            city_name = row.get('name', '')
            display_name = f"{city_name} ({state_name})" if state_name else city_name

            cities.append({
                'id': row['id'],
                'name': display_name,
                'selected': False,  # Por defecto no seleccionado (mostrar todos)
            })

        return cities

    def _build_city_filter(self, options):
        """Construye el filtro SQL para ciudades.

        Filtra movimientos contables donde el partner pertenece a las ciudades seleccionadas.
        """
        city_ids = options.get('city_ids', [])

        if not city_ids:
            return SQL("")

        # Filtrar por city_id del partner
        return SQL("AND rp.city_id IN %s", tuple(city_ids))

    def _build_account_ids_filter(self, options):
        """Construye el filtro SQL para IDs de cuentas específicas."""
        account_ids = options.get('account_ids', [])

        if not account_ids:
            return SQL("")

        # Filtrar por account_id de la línea de impuesto
        return SQL("AND account_move_line.account_id IN %s", tuple(account_ids))

    def _build_account_tag_filter(self, options):
        """Construye el filtro SQL para etiquetas de cuenta."""
        tag_ids = options.get('account_tag_ids', [])

        if not tag_ids:
            return SQL("")

        # Filtrar cuentas que tengan las etiquetas especificadas
        return SQL("""
            AND EXISTS (
                SELECT 1 FROM account_account_account_tag rel
                WHERE rel.account_account_id = account_move_line.account_id
                AND rel.account_account_tag_id IN %s
            )
        """, tuple(tag_ids))

    def _build_level_filter(self, options):
        """Obtiene los niveles permitidos para mostrar en el reporte.

        Returns:
            set: Conjunto de IDs de niveles permitidos (0-4)
        """
        level_ids = options.get('level_ids', [])

        # Si no hay filtro, mostrar todos los niveles por defecto
        if not level_ids:
            return {0, 1, 2, 3}  # Por defecto: Tributos, Impuestos, Cuentas, Movimientos

        return set(level_ids)

    def _build_withholding_filter(self, options):
        """Construye el filtro SQL para conceptos de retención"""
        filters = []

        # Filtro por tipo de concepto
        concept_type = options.get('concept_type_filter', 'all')
        if concept_type and concept_type != 'all':
            # Obtener los IDs de impuestos que tienen ese tipo de concepto
            tax_ids = self._get_tax_ids_by_concept_type(concept_type)
            if tax_ids:
                filters.append(SQL("at.id IN %s", tuple(tax_ids)))
            else:
                # Si no hay impuestos para ese tipo, retornar filtro que no muestre nada
                filters.append(SQL("1=0"))

        # Filtro por conceptos específicos
        concept_ids = options.get('withholding_concept_ids', [])
        if concept_ids:
            # Obtener los IDs de impuestos relacionados con esos conceptos
            tax_ids = self._get_tax_ids_by_concept_ids(concept_ids)
            if tax_ids:
                filters.append(SQL("at.id IN %s", tuple(tax_ids)))
            else:
                filters.append(SQL("1=0"))

        if filters:
            return SQL(" AND ").join(filters)
        return SQL("")

    def _build_operation_type_filter(self, options):
        """Construye el filtro SQL para tipo de operación (compra/venta)"""
        operation_type = options.get('operation_type_filter', 'all')

        if operation_type == 'all':
            return SQL("")

        # Mapeo de tipos de operación a move_type de Odoo
        move_type_mapping = {
            'purchase': ['in_invoice'],                    # Facturas de proveedor
            'sale': ['out_invoice'],                       # Facturas de cliente
            'purchase_refund': ['in_refund'],              # NC de proveedor
            'sale_refund': ['out_refund'],                 # NC de cliente
            'purchase_all': ['in_invoice', 'in_refund'], # Compras (Facturas + NC)
            'sale_all': ['out_invoice', 'out_refund'],   # Ventas (Facturas + NC)
        }

        move_types = move_type_mapping.get(operation_type, [])
        if move_types:
            return SQL("account_move.move_type IN %s", tuple(move_types))

        return SQL("")

    def _build_product_type_filter(self, options):
        """Construye el filtro SQL para tipo de producto (servicio/bienes).

        Filtra por el tipo de producto en las líneas base que generaron el impuesto.
        En Odoo 18, el campo es 'type' en product_template.
        """
        product_type = options.get('product_type_filter', 'all')

        if product_type == 'all':
            return SQL("")

        # Mapeo de tipos de producto
        # En Odoo 18: 'service', 'consu' (consumible), 'product' (almacenable)
        product_types_mapping = {
            'service': ['service'],
            'consu': ['consu'],
            'product': ['product'],
        }

        product_types = product_types_mapping.get(product_type, [])
        if product_types:
            # Subconsulta para verificar si el movimiento tiene líneas con productos del tipo especificado
            return SQL("""
                EXISTS (
                    SELECT 1 FROM account_move_line base_line
                    JOIN product_product pp ON pp.id = base_line.product_id
                    JOIN product_template pt ON pt.id = pp.product_tmpl_id
                    WHERE base_line.move_id = account_move.id
                    AND pt.type IN %s
                )
            """, tuple(product_types))

        return SQL("")

    def _build_person_type_filter(self, options):
        """Construye el filtro SQL para tipo de persona (PJ/PN).

        PJ = Persona Jurídica (is_company = True)
        PN = Persona Natural (is_company = False)
        """
        person_type = options.get('person_type_filter', 'all')

        if person_type == 'all':
            return SQL("")

        if person_type == 'company':
            return SQL("rp.is_company = true")
        elif person_type == 'person':
            return SQL("(rp.is_company = false OR rp.is_company IS NULL)")

        return SQL("")

    def _build_account_filter(self, options, account_code_sql=None, account_name_sql=None):
        """Construye el filtro SQL para filtrar por cuenta contable.

        Permite filtrar por código o nombre de cuenta.
        Este método necesita recibir las expresiones SQL de account_code y account_name
        generadas por _field_to_sql.

        Args:
            options: Opciones del reporte
            account_code_sql: Expresión SQL para código de cuenta (opcional)
            account_name_sql: Expresión SQL para nombre de cuenta (opcional)

        Returns:
            SQL: Condición de filtro o SQL vacío si no hay filtro
        """
        account_filter = options.get('account_filter', '').strip()

        if not account_filter:
            return SQL("")

        # Si no tenemos las expresiones SQL, usar la tabla directamente
        if account_code_sql and account_name_sql:
            return SQL("""
                (%(account_code)s ILIKE %(pattern)s OR %(account_name)s ILIKE %(pattern)s)
            """, account_code=account_code_sql, account_name=account_name_sql, pattern=f'%{account_filter}%')
        else:
            # Fallback: buscar en account_account directamente
            # Este filtro busca en cuentas relacionadas con el movimiento
            return SQL("""
                EXISTS (
                    SELECT 1 FROM account_account aa_filter
                    WHERE aa_filter.id = account_move_line.account_id
                    AND (aa_filter.code ILIKE %(pattern)s OR aa_filter.name::text ILIKE %(pattern)s)
                )
            """, pattern=f'%{account_filter}%')

    def _build_concept_type_filter(self):
        """Construye el filtro SQL para filtrar por tipo de impuesto.

        Usa el campo l10n_co_tax_type del impuesto (account.tax) como fuente principal.
        Si no está configurado, hace fallback al concept_type del concepto de retención.
        """
        concept_types = self._get_concept_types()

        if not concept_types:
            return SQL("")

        # Filtrar por l10n_co_tax_type del impuesto o concept_type del concepto
        if len(concept_types) == 1:
            return SQL("""(
                at.l10n_co_tax_type = %(tax_type)s
                OR wc.concept_type = %(tax_type)s
            )""", tax_type=concept_types[0])
        else:
            return SQL("""(
                at.l10n_co_tax_type IN %(tax_types)s
                OR wc.concept_type IN %(tax_types)s
            )""", tax_types=tuple(concept_types))

    def _get_tax_ids_by_concept_type(self, concept_type):
        """Obtiene los IDs de impuestos que tienen un tipo de concepto específico"""
        # Buscar conceptos de ese tipo
        concepts = self.env['withholding.concept'].search([
            ('concept_type', '=', concept_type),
            ('active', '=', True)
        ])

        if not concepts:
            return []

        # Buscar impuestos relacionados con esos conceptos
        taxes = self.env['account.tax'].search([
            ('withholding_concept_id', 'in', concepts.ids)
        ])

        return taxes.ids if taxes else []

    def _get_tax_ids_by_concept_ids(self, concept_ids):
        """Obtiene los IDs de impuestos relacionados con conceptos específicos"""
        taxes = self.env['account.tax'].search([
            ('withholding_concept_id', 'in', concept_ids)
        ])
        return taxes.ids if taxes else []

    def _ensure_columns_updated(self, report, options):
        """Asegurar que las columnas estén correctamente configuradas"""
        # Verificar que las columnas base existan (columnas numéricas obligatorias)
        required_columns = ['base', 'percentage', 'tax']

        existing_labels = [col.get('expression_label') for col in options.get('columns', [])]

        # Obtener column_group_key de forma segura
        column_groups = options.get('column_groups', {})
        if isinstance(column_groups, dict) and column_groups:
            column_group_key = list(column_groups.keys())[0]
        elif isinstance(column_groups, list) and column_groups:
            column_group_key = column_groups[0].get('key', 'default')
        else:
            column_group_key = 'default'

        # Si faltan columnas numéricas, agregarlas
        for req_col in required_columns:
            if req_col not in existing_labels:
                new_column = {
                    'name': self._get_column_name(req_col),
                    'expression_label': req_col,
                    'figure_type': 'percentage' if req_col == 'percentage' else 'monetary',
                    'column_group_key': column_group_key,
                    'sortable': True,
                }
                options.setdefault('columns', []).append(new_column)

    def _get_column_name(self, column_label):
        """Obtener nombre de columna traducido"""
        column_names = {
            # Columnas de identificación
            'date': _('Fecha'),
            'move_name': _('Documento'),
            'doc_type_number': _('Tipo/Número'),
            'doc_type_short': _('Tipo Doc'),
            'partner_name': _('Tercero'),
            'partner_vat': _('NIT/CC'),
            'doc_type': _('Tipo Doc'),
            'ref': _('Referencia'),
            'person_type': _('Tipo'),
            'city': _('Ciudad'),
            'city_state': _('Ciudad (Depto)'),
            'concept_code': _('Concepto'),
            'person_type': _('Tipo Persona'),
            'cufe': _('CUFE'),
            'invoice_origin': _('Origen Factura'),
            'is_refund': _('Es Devolucion'),
            'reversed_doc': _('Doc. Original'),
            'account': _('Cuenta'),
            'account_type': _('Tipo Cuenta'),
            'retention_direction': _('Dirección'),
            'retention_direction_short': _('Dir'),
            # Columnas numéricas
            'base': _('Base Gravable'),
            'percentage': _('Tarifa %'),
            'tax': _('Valor Impuesto'),
            'amount_pj': _('Monto PJ'),
            'amount_pn': _('Monto PN'),
        }
        return column_names.get(column_label, column_label)

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        """Genera las líneas dinámicas del reporte.

        IMPORTANTE: En Odoo 18, las líneas hijas de líneas expandidas (unfolded)
        son manejadas por el método expand_function, NO por este método.
        Solo generamos las líneas de nivel 0 (tributos) aquí.
        """
        lines = []

        # Obtener datos de impuestos agrupados
        tax_data = self._get_tax_data_grouped(report, options)

        if not tax_data:
            return [(0, {
                'id': report._get_generic_line_id(None, None, markup='no_data'),
                'name': _('No se encontraron datos de impuestos para el período seleccionado'),
                'columns': [{'name': ''} for _ in options['columns']],
                'level': 0,
            })]

        # Generar líneas del reporte - SOLO nivel 0 (tributos)
        # Obtener niveles permitidos
        allowed_levels = self._build_level_filter(options)

        for tribute_code, tribute_name, tax_groups in tax_data:
            # Total del tributo
            tribute_total_base = sum(group['total_base'] for group in tax_groups.values())
            tribute_total_tax = sum(group['total_tax'] for group in tax_groups.values())

            # Línea principal del tributo
            tribute_line_id = report._get_generic_line_id(None, None, markup=f'tribute_{tribute_code}')
            _logger.warning(f"Creating tribute line with expand_function=_report_expand_unfoldable_line_co_tax, id={tribute_line_id}")
            tribute_line = {
                'id': tribute_line_id,
                'name': f'[{tribute_code}] {tribute_name}',
                'columns': self._build_columns(report, options, tribute_total_base, tribute_total_tax),
                'level': 0,
                'unfoldable': True,
                'unfolded': tribute_line_id in options.get('unfolded_lines', []),
                'expand_function': '_report_expand_unfoldable_line_co_tax',
                'class': 'total o_account_reports_totals_below_sections',
            }
            lines.append((0, tribute_line))

        # Línea de total general
        if lines:
            lines.append((0, self._get_total_line(report, options, tax_data)))

        return lines

    def _get_tax_data_grouped(self, report, options):
        """Obtener datos de impuestos agrupados por tributo y luego por tax_id"""
        # Obtener datos raw
        raw_data = self._get_raw_tax_data(report, options)
        
        # Agrupar por tributo
        tribute_groups = defaultdict(lambda: defaultdict(lambda: {
            'total_base': 0,
            'total_tax': 0,
            'details': [],
            'tax_name': '',
            'tax_rate': 0,
            'amount_type': 'percent'
        }))
        
        for row in raw_data:
            tribute_code = row['tributes']
            tax_id = row['tax_id']
            
            base_amount = row['tax_base_amount'] or 0
            tax_amount = abs(row['balance'])
            
            # Agregar al grupo
            tax_group = tribute_groups[tribute_code][tax_id]
            tax_group['total_base'] += base_amount
            tax_group['total_tax'] += tax_amount
            tax_group['details'].append(row)
            tax_group['tax_name'] = row['tax_name']
            tax_group['tax_rate'] = row['tax_rate'] or 0
            tax_group['amount_type'] = row['amount_type']

            # Agrupar por cuenta dentro del impuesto
            account_id = row.get('account_id')
            if account_id:
                if 'accounts' not in tax_group:
                    tax_group['accounts'] = {}
                if account_id not in tax_group['accounts']:
                    tax_group['accounts'][account_id] = {
                        'account_id': account_id,
                        'account_code': row.get('account_code', ''),
                        'account_name': row.get('account_name', ''),
                        'total_base': 0,
                        'total_tax': 0,
                        'details': []
                    }
                tax_group['accounts'][account_id]['total_base'] += base_amount
                tax_group['accounts'][account_id]['total_tax'] += tax_amount
                tax_group['accounts'][account_id]['details'].append(row)
        
        # Convertir a formato final
        tribute_names = dict(self._get_all_tributes())
        result = []

        # Obtener nombres de tax_groups para cuando tribute_code es un ID numérico
        tax_group_names = {}
        tax_group_ids = [code for code in tribute_groups.keys() if isinstance(code, int) and code > 0]
        if tax_group_ids:
            tax_groups_records = self.env['account.tax.group'].browse(tax_group_ids)
            tax_group_names = {tg.id: tg.name for tg in tax_groups_records}

        for tribute_code, tax_groups in sorted(tribute_groups.items(), key=lambda x: str(x[0])):
            # Obtener nombre del tributo/grupo
            if isinstance(tribute_code, int):
                tribute_name = tax_group_names.get(tribute_code, f'Grupo {tribute_code}')
            else:
                tribute_name = tribute_names.get(tribute_code, str(tribute_code))
            result.append((tribute_code, tribute_name, dict(tax_groups)))
        
        return result

    def _get_raw_tax_data(self, report, options):
        """Obtener datos raw de impuestos con consulta SQL optimizada usando Odoo 18 API"""
        # Manejo de traducciones
        lang = self.env.user.lang or get_lang(self.env).code
        # Dominio base
        query_domain = [
            ('tax_line_id', '!=', False),
        ]

        # ========== FILTROS DE RETENCIÓN (tax_base_threshold) ==========
        # Construir filtro por concepto de retención
        withholding_filter = self._build_withholding_filter(options)

        # Construir filtro por tipo de operación (compra/venta)
        operation_filter = self._build_operation_type_filter(options)

        # Filtro por concept_type del handler (retefuente, reteiva, reteica, inc, iva, other)
        concept_type_filter = self._build_concept_type_filter()

        # Filtro por tipo de producto (servicio/bienes)
        product_type_filter = self._build_product_type_filter(options)

        # Filtro por tipo de persona (PJ/PN)
        person_type_filter = self._build_person_type_filter(options)

        # Filtro por ciudad
        city_filter = self._build_city_filter(options)

        # Filtro de tributos - deshabilitado hasta configurar l10n_co_edi_type
        tribute_filter = SQL("")

        queries = []
        for column_group_key, options_group in report._split_options_per_column_group(options).items():
            query = report._get_report_query(options_group, 'strict_range', domain=query_domain)

            # Usar patrón nativo Odoo 18: query.join + _field_to_sql
            account_alias = query.join(
                lhs_alias='account_move_line',
                lhs_column='account_id',
                rhs_table='account_account',
                rhs_column='id',
                link='account_id'
            )
            account_code = self.env['account.account']._field_to_sql(account_alias, 'code', query)
            account_name = self.env['account.account']._field_to_sql(account_alias, 'name')
            tax_name = self.env['account.tax']._field_to_sql('at', 'name')

            # Filtro por cuenta contable (necesita account_code y account_name)
            account_filter = self._build_account_filter(options, account_code, account_name)

            # Construir condiciones de filtro usando SQL con placeholders
            # En Odoo 18, SQL no soporta concatenación directa con +
            withholding_condition = SQL("")
            if withholding_filter and str(withholding_filter):
                withholding_condition = SQL(" AND %(filter)s", filter=withholding_filter)

            # Construir condición de filtro de operación
            operation_condition = SQL("")
            if operation_filter and str(operation_filter):
                operation_condition = SQL(" AND %(filter)s", filter=operation_filter)

            # Construir condición de filtro por concept_type del handler
            concept_type_condition = SQL("")
            if concept_type_filter and str(concept_type_filter):
                concept_type_condition = SQL(" AND %(filter)s", filter=concept_type_filter)

            # Construir condición de filtro por tipo de producto
            product_type_condition = SQL("")
            if product_type_filter and str(product_type_filter):
                product_type_condition = SQL(" AND %(filter)s", filter=product_type_filter)

            # Construir condición de filtro por tipo de persona
            person_type_condition = SQL("")
            if person_type_filter and str(person_type_filter):
                person_type_condition = SQL(" AND %(filter)s", filter=person_type_filter)

            # Construir condición de filtro por cuenta contable
            account_condition = SQL("")
            if account_filter and str(account_filter):
                account_condition = SQL(" AND %(filter)s", filter=account_filter)

            # Construir condición de filtro por ciudad
            city_condition = SQL("")
            if city_filter and str(city_filter):
                city_condition = SQL(" AND %(filter)s", filter=city_filter)

            queries.append(SQL(
                """
                SELECT
                    account_move_line.id as line_id,
                    account_move_line.move_id,
                    account_move_line.account_id,
                    account_move_line.partner_id,
                    account_move_line.name as line_name,
                    account_move_line.balance,
                    account_move_line.tax_base_amount,
                    account_move.name as move_name,
                    account_move.move_type,
                    account_move.ref,
                    account_move.date,
                    account_move.state,
                    account_move.invoice_origin,
                    COALESCE(account_move.l10n_co_edi_cufe_cude_ref, '') as cufe,
                    at.id as tax_id,
                    %(tax_name)s as tax_name,
                    COALESCE(at.tax_group_id, 0) as tributes,
                    COALESCE(at.amount, 0) as tax_rate,
                    COALESCE(at.amount_type, 'percent') as amount_type,
                    at.withholding_concept_id,
                    COALESCE(wc.code, '') as concept_code,
                    COALESCE(wc.concept_type, '') as concept_type,
                    %(account_code)s as account_code,
                    %(account_name)s as account_name,
                    COALESCE(rp.name, '') as partner_name,
                    COALESCE(rp.vat, '') as partner_vat,
                    COALESCE(rc.name, '') as city_name,
                    COALESCE(rcs.name, '') as state_name,
                    COALESCE(rp.is_company, false) as is_company,
                    CASE WHEN rp.is_company = true THEN 'PJ' ELSE 'PN' END as person_type,
                    -- Tipo de documento largo
                    CASE
                        WHEN account_move.move_type = 'entry' THEN 'ASIENTO'
                        WHEN account_move.move_type = 'out_invoice' THEN 'FACTURA'
                        WHEN account_move.move_type = 'out_refund' THEN 'NC CLIENTE'
                        WHEN account_move.move_type = 'in_invoice' THEN 'FAC PROVEEDOR'
                        WHEN account_move.move_type = 'in_refund' THEN 'NC PROVEEDOR'
                        ELSE 'OTRO'
                    END as doc_type_name,
                    -- Tipo de documento corto (2-3 caracteres)
                    CASE
                        WHEN account_move.move_type = 'entry' THEN 'AS'
                        WHEN account_move.move_type = 'out_invoice' THEN 'FV'
                        WHEN account_move.move_type = 'out_refund' THEN 'NCV'
                        WHEN account_move.move_type = 'in_invoice' THEN 'FC'
                        WHEN account_move.move_type = 'in_refund' THEN 'NCC'
                        ELSE 'OT'
                    END as doc_type_short,
                    -- Columna combinada: [TipoCorto] Número
                    CASE
                        WHEN account_move.move_type = 'entry' THEN '[AS] ' || account_move.name
                        WHEN account_move.move_type = 'out_invoice' THEN '[FV] ' || account_move.name
                        WHEN account_move.move_type = 'out_refund' THEN '[NCV] ' || account_move.name
                        WHEN account_move.move_type = 'in_invoice' THEN '[FC] ' || account_move.name
                        WHEN account_move.move_type = 'in_refund' THEN '[NCC] ' || account_move.name
                        ELSE '[OT] ' || account_move.name
                    END as doc_type_number,
                    -- Montos separados por tipo de persona (PJ/PN)
                    CASE WHEN rp.is_company = true THEN ABS(account_move_line.balance) ELSE 0 END as amount_pj,
                    CASE WHEN rp.is_company = false OR rp.is_company IS NULL THEN ABS(account_move_line.balance) ELSE 0 END as amount_pn,
                    -- Indicador de devolucion (NC)
                    CASE WHEN account_move.move_type IN ('out_refund', 'in_refund') THEN true ELSE false END as is_refund,
                    -- Documento original de la devolucion
                    COALESCE(rev_move.name, '') as reversed_doc,
                    -- Tipo de cuenta contable (activo/pasivo/ingreso/gasto)
                    COALESCE(%(account_alias)s.account_type, '') as account_type,
                    -- Indicador si es retención practicada o recibida
                    -- Activo (13xx) = Retención recibida/a favor (nos retuvieron en compras)
                    -- Pasivo (23xx, 28xx) = Retención practicada/por pagar (retenemos a terceros en compras)
                    -- Ingreso (41xx) con retención = Retención que nos practicaron en ventas
                    -- Gasto (51xx) con retención = Retención que practicamos en compras
                    CASE
                        WHEN %(account_alias)s.account_type IN ('asset_receivable', 'asset_current', 'asset_non_current', 'asset_fixed', 'asset_prepayments') THEN 'A FAVOR'
                        WHEN %(account_alias)s.account_type IN ('liability_payable', 'liability_current', 'liability_non_current') THEN 'POR PAGAR'
                        WHEN %(account_alias)s.account_type IN ('income', 'income_other') THEN 'EN VENTA'
                        WHEN %(account_alias)s.account_type IN ('expense', 'expense_depreciation', 'expense_direct_cost') THEN 'EN COMPRA'
                        ELSE 'OTRO'
                    END as retention_direction,
                    -- Código corto de dirección retención
                    CASE
                        WHEN %(account_alias)s.account_type IN ('asset_receivable', 'asset_current', 'asset_non_current', 'asset_fixed', 'asset_prepayments') THEN 'FAV'
                        WHEN %(account_alias)s.account_type IN ('liability_payable', 'liability_current', 'liability_non_current') THEN 'PAG'
                        WHEN %(account_alias)s.account_type IN ('income', 'income_other') THEN 'VTA'
                        WHEN %(account_alias)s.account_type IN ('expense', 'expense_depreciation', 'expense_direct_cost') THEN 'CMP'
                        ELSE 'OTR'
                    END as retention_direction_short
                FROM %(table_references)s
                JOIN account_move account_move ON account_move.id = account_move_line.move_id
                LEFT JOIN account_tax at ON at.id = account_move_line.tax_line_id
                LEFT JOIN withholding_concept wc ON wc.id = at.withholding_concept_id
                LEFT JOIN res_partner rp ON rp.id = account_move_line.partner_id
                LEFT JOIN res_city rc ON rc.id = rp.city_id
                LEFT JOIN account_move rev_move ON rev_move.id = account_move.reversed_entry_id
                LEFT JOIN res_country_state rcs ON rcs.id = rc.state_id
                WHERE %(search_condition)s
                    %(tribute_filter)s
                    %(withholding_filter)s
                    %(operation_filter)s
                    %(concept_type_filter)s
                    %(product_type_filter)s
                    %(person_type_filter)s
                    %(account_filter)s
                    %(city_filter)s
                    %(account_ids_filter)s
                    %(account_tag_filter)s
                ORDER BY at.tax_group_id, at.id, account_move.date DESC
                """,
                tax_name=tax_name,
                account_name=account_name,
                account_code=account_code,
                account_alias=SQL.identifier(account_alias),
                table_references=query.from_clause,
                search_condition=query.where_clause,
                tribute_filter=tribute_filter,
                withholding_filter=withholding_condition,
                operation_filter=operation_condition,
                concept_type_filter=concept_type_condition,
                product_type_filter=product_type_condition,
                person_type_filter=person_type_condition,
                account_filter=account_condition,
                city_filter=city_condition,
                account_ids_filter=self._build_account_ids_filter(options),
                account_tag_filter=self._build_account_tag_filter(options),
            ))

        full_query = SQL(" UNION ALL ").join(queries)

        _logger.info("Executing tax query")
        self._cr.execute(full_query)
        results = self._cr.dictfetchall()
        _logger.info(f"Found {len(results)} tax records")

        return results

    def _build_columns(self, report, options, base_amount, tax_amount, line_data=None):
        """Construir columnas para una línea

        Args:
            report: Reporte
            options: Opciones del reporte
            base_amount: Monto base gravable
            tax_amount: Monto del impuesto
            line_data: Dict con datos adicionales para las columnas de texto:
                - move_name: Nombre del asiento
                - date: Fecha del movimiento
                - partner_name: Nombre del tercero
                - partner_vat: NIT/CC del tercero
                - concept_code: Código del concepto de retención
                - account: Código de cuenta
                - ref: Referencia
                - label: Etiqueta/descripción
                - person_type: Tipo de persona (PJ/PN)
                - cufe: CUFE de factura electrónica
                - invoice_origin: Origen de la factura
                - amount_pj: Monto Persona Jurídica
                - amount_pn: Monto Persona Natural
        """
        columns = []
        line_data = line_data or {}

        for column in options['columns']:
            col_value = None
            expr_label = column['expression_label']

            # Columnas de identificación
            if expr_label == 'date':
                col_value = line_data.get('date', '')
            elif expr_label == 'move_name':
                col_value = line_data.get('move_name', '')
            elif expr_label == 'doc_type':
                col_value = line_data.get('doc_type_name', '')
            elif expr_label == 'ref':
                col_value = line_data.get('ref', '')
            elif expr_label == 'person_type':
                is_company = line_data.get('is_company', True)
                col_value = 'PJ' if is_company else 'PN'
            elif expr_label == 'doc_type_number':
                col_value = line_data.get('doc_type_number', '')
            elif expr_label == 'doc_type_short':
                col_value = line_data.get('doc_type_short', '')
            elif expr_label == 'partner_name':
                col_value = line_data.get('partner_name', '')
            elif expr_label == 'city':
                col_value = line_data.get('city_name', '')
            elif expr_label == 'city_state':
                city = line_data.get('city_name', '')
                state = line_data.get('state_name', '')
                col_value = f"{city} ({state})" if state and city else city
            elif expr_label == 'partner_vat':
                col_value = line_data.get('partner_vat', '')
            elif expr_label == 'concept_code':
                col_value = line_data.get('concept_code', '')
            elif expr_label == 'account':
                col_value = line_data.get('account', '')
            elif expr_label == 'ref':
                col_value = line_data.get('ref', '')
            elif expr_label == 'label':
                col_value = line_data.get('label', '')
            # Nuevas columnas de identificación (PJ/PN y factura electrónica)
            elif expr_label == 'person_type':
                col_value = line_data.get('person_type', '')
            elif expr_label == 'cufe':
                col_value = line_data.get('cufe', '')
            elif expr_label == 'invoice_origin':
                col_value = line_data.get('invoice_origin', '')
            elif expr_label == 'is_refund':
                is_ref = line_data.get('is_refund', False)
                col_value = 'Si' if is_ref else 'No'
            elif expr_label == 'reversed_doc':
                col_value = line_data.get('reversed_doc', '')
            # Columnas de cuenta del impuesto
            elif expr_label in ('account_code', 'tax_account_code'):
                col_value = line_data.get('account_code', '')
            elif expr_label == 'tax_account_name':
                col_value = line_data.get('account_name', '')
            # Columnas de tipo de cuenta y dirección retención
            elif expr_label == 'account_type':
                col_value = line_data.get('account_type', '')
            elif expr_label == 'retention_direction':
                col_value = line_data.get('retention_direction', '')
            elif expr_label == 'retention_direction_short':
                col_value = line_data.get('retention_direction_short', '')
            # Columnas numéricas
            elif expr_label == 'base':
                col_value = base_amount
            elif expr_label == 'percentage':
                if base_amount and base_amount != 0:
                    col_value = (tax_amount / base_amount) * 100
                else:
                    col_value = 0
            elif expr_label == 'tax':
                col_value = tax_amount
            # Nuevas columnas numéricas (separación PJ/PN)
            elif expr_label == 'amount_pj':
                col_value = line_data.get('amount_pj', 0)
            elif expr_label == 'amount_pn':
                col_value = line_data.get('amount_pn', 0)

            columns.append(report._build_column_dict(col_value, column, options=options))

        return columns

    def _get_tax_line(self, report, options, tax_id, tax_group, tribute_code):
        """Generar línea de impuesto específico"""
        parent_line_id = report._get_generic_line_id(None, None, markup=f'tribute_{tribute_code}')
        line_id = report._get_generic_line_id("account.tax", tax_id, markup=f"tribute_{tribute_code}", parent_line_id=parent_line_id)
        
        # Construir nombre del impuesto con tarifa
        tax_name = tax_group['tax_name']
        if tax_group['amount_type'] == 'percent' and tax_group['tax_rate']:
            tax_name += f" {tax_group['tax_rate']}%"
        
        return {
            'id': line_id,
            'name': tax_name,
            'columns': self._build_columns(report, options, tax_group['total_base'], tax_group['total_tax']),
            'level': 1,
            'parent_id': parent_line_id,
            'unfoldable': True,
            'unfolded': line_id in options.get('unfolded_lines', []),
            'expand_function': '_report_expand_unfoldable_line_co_tax_account',
            'caret_options': 'account.tax',
        }

    def _group_by_move(self, details):
        """Agrupar detalles por movimiento contable"""
        move_groups = defaultdict(lambda: {
            'move_name': '',
            'date': None,
            'ref': '',
            'state': '',
            'move_type': '',
            'doc_type_name': '',
            'doc_type_short': '',
            'doc_type_number': '',
            'invoice_origin': '',
            'is_refund': False,
            'reversed_doc': '',
            'cufe': '',
            'account_type': '',
            'retention_direction': '',
            'retention_direction_short': '',
            'total_base': 0,
            'total_tax': 0,
            'total_pj': 0,  # Total Persona Jurídica
            'total_pn': 0,  # Total Persona Natural
            'city_name': '',
            'state_name': '',
            'tax_details': []
        })

        for detail in details:
            move_id = detail['move_id']
            move_data = move_groups[move_id]

            # Datos del movimiento (tomar del primer detalle)
            if not move_data['move_name']:
                move_data['move_name'] = detail['move_name']
                move_data['date'] = detail['date']
                move_data['ref'] = detail['ref']
                move_data['state'] = detail['state']
                move_data['move_type'] = detail['move_type']
                move_data['doc_type_name'] = detail['doc_type_name']
                move_data['doc_type_short'] = detail.get('doc_type_short', '')
                move_data['doc_type_number'] = detail.get('doc_type_number', '')
                move_data['invoice_origin'] = detail.get('invoice_origin', '')
                move_data['is_refund'] = detail.get('is_refund', False)
                move_data['reversed_doc'] = detail.get('reversed_doc', '')
                move_data['cufe'] = detail.get('cufe', '')
                move_data['account_type'] = detail.get('account_type', '')
                move_data['retention_direction'] = detail.get('retention_direction', '')
                move_data['retention_direction_short'] = detail.get('retention_direction_short', '')

            # Acumular totales
            move_data['total_base'] += detail['tax_base_amount'] or 0
            move_data['total_tax'] += abs(detail['balance'])
            # Acumular por tipo de persona (PJ/PN)
            move_data['total_pj'] += detail.get('amount_pj', 0)
            move_data['total_pn'] += detail.get('amount_pn', 0)
            move_data['tax_details'].append(detail)

        return move_groups


    def _get_account_line(self, report, options, account_data, tribute_code, tax_id):
        """Generar linea de cuenta (NIVEL 2)"""
        account_id = account_data['account_id']
        account_code = account_data.get('account_code', '')
        account_name = account_data.get('account_name', '')

        # Parent es la linea del impuesto
        parent_id = report._get_generic_line_id(
            'account.tax', tax_id,
            markup=f'tribute_{tribute_code}'
        )

        line_id = report._get_generic_line_id(
            'account.account', account_id,
            markup=f'tribute_{tribute_code}~tax_{tax_id}',
            parent_line_id=parent_id
        )

        return {
            'id': line_id,
            'name': f'{account_code} - {account_name}',
            'parent_id': parent_id,
            'columns': self._build_columns(
                report, options,
                account_data['total_base'],
                account_data['total_tax'],
                line_data={'account_code': account_code, 'account_name': account_name}
            ),
            'level': 2,
            'unfoldable': True,
            'unfolded': line_id in options.get('unfolded_lines', []),
            'expand_function': '_report_expand_unfoldable_line_co_tax',
            'class': '',
        }

    def _get_move_line(self, report, options, move_data, tribute_code, tax_id):
        """Generar línea de movimiento contable"""
        move_id = move_data['tax_details'][0]['move_id'] if move_data['tax_details'] else 0
        parent_line_id = report._get_generic_line_id('account.tax', tax_id,
                        parent_line_id=report._get_generic_line_id(None, None, markup=f'tribute_{tribute_code}'))
        line_id = report._get_generic_line_id('account.move', move_id, parent_line_id=parent_line_id)

        # Obtener datos del primer detalle
        first_detail = move_data['tax_details'][0] if move_data['tax_details'] else {}
        account_code = first_detail.get('account_code', '')

        # Determinar tipo de persona (PJ/PN)
        person_type = first_detail.get('person_type', '')
        person_type_label = _('PJ') if first_detail.get('is_company') else _('PN')

        # Nombre de linea = solo numero de documento
        # El resto de info va en columnas separadas
        name_parts = [move_data['move_name']]

        # Datos para las columnas de texto (incluyendo nuevas columnas)
        line_data = {
            'move_name': move_data['move_name'],
            'doc_type_name': move_data.get('doc_type_name', ''),
            'is_company': first_detail.get('is_company', True),
            'date': move_data['date'],
            'doc_type_short': move_data.get('doc_type_short', ''),
            'doc_type_number': move_data.get('doc_type_number', ''),
            'partner_name': first_detail.get('partner_name', ''),
            'partner_vat': first_detail.get('partner_vat', ''),
            'person_type': person_type,
            'concept_code': first_detail.get('concept_code', ''),
            'account': account_code,
            'ref': move_data['ref'] or '',
            'label': first_detail.get('line_name', ''),
            'cufe': move_data.get('cufe', ''),
            'invoice_origin': move_data.get('invoice_origin', ''),
            'is_refund': move_data.get('is_refund', False),
            'reversed_doc': move_data.get('reversed_doc', ''),
            # Cuenta del impuesto (código y nombre)
            'account_code': first_detail.get('account_code', ''),
            'account_name': first_detail.get('account_name', ''),
            # Tipo de cuenta y dirección retención
            'account_type': move_data.get('account_type', ''),
            'retention_direction': move_data.get('retention_direction', ''),
            'retention_direction_short': move_data.get('retention_direction_short', ''),
            # Montos separados por tipo de persona (PJ/PN)
            'amount_pj': move_data.get('total_pj', 0),
            'amount_pn': move_data.get('total_pn', 0),
        }

        return {
            'id': line_id,
            'name': ' | '.join(name_parts),
            'columns': self._build_columns(report, options, move_data['total_base'], move_data['total_tax'], line_data),
            'level': 2,
            'parent_id': parent_line_id,
            'unfoldable': True,
            'unfolded': line_id in options.get('unfolded_lines', []),
            'expand_function': '_report_expand_unfoldable_line_co_tax',
            'caret_options': 'account.move',
            'class': 'text-muted' if move_data['state'] == 'draft' else '',
        }

    def _get_base_lines_for_move(self, report, options, move_id, tax_id):
        """Obtener líneas base que generaron el impuesto para un movimiento específico"""
        # Manejo de traducciones
        lang = self.env.user.lang or get_lang(self.env).code
        company_id = str(self.env.company.id)

        # Expresiones optimizadas para Odoo 18
        account_name = f"COALESCE(aa.name->>'{lang}', aa.name->>'en_US', '')"
        account_code = f"COALESCE(aa.code_store->>'{company_id}', '')"

        # Consulta para obtener líneas base usando la relación many2many tax_ids
        query = f"""
            SELECT DISTINCT
                aml.id as line_id,
                aml.name as line_name,
                aml.debit,
                aml.credit,
                aml.balance,
                aml.account_id,
                {account_code} as account_code,
                {account_name} as account_name,
                aml.partner_id,
                COALESCE(rp.name, '') as partner_name,
                COALESCE(rp.vat, '') as partner_vat,
                COALESCE(rp.is_company, false) as is_company,
                aml.quantity,
                aml.price_unit,
                COALESCE(aml.tax_base_amount, ABS(aml.balance)) as tax_base_amount
            FROM account_move_line aml
            JOIN account_account aa ON aa.id = aml.account_id
            LEFT JOIN res_partner rp ON rp.id = aml.partner_id
            WHERE aml.move_id = %s
                AND aml.tax_line_id IS NULL
                AND aml.display_type NOT IN ('line_section', 'line_note')
                AND EXISTS (
                    SELECT 1 FROM account_move_line_account_tax_rel rel
                    WHERE rel.account_move_line_id = aml.id
                    AND rel.account_tax_id = %s
                )
            ORDER BY aml.id
        """

        self._cr.execute(query, [move_id, tax_id])
        result = self._cr.dictfetchall()

        # Si no hay líneas con relación directa, buscar todas las líneas base del movimiento
        if not result:
            query_fallback = f"""
                SELECT DISTINCT
                    aml.id as line_id,
                    aml.name as line_name,
                    aml.debit,
                    aml.credit,
                    aml.balance,
                    aml.account_id,
                    {account_code} as account_code,
                    {account_name} as account_name,
                    aml.partner_id,
                    COALESCE(rp.name, '') as partner_name,
                    COALESCE(rp.vat, '') as partner_vat,
                    COALESCE(rp.is_company, false) as is_company,
                    aml.quantity,
                    aml.price_unit,
                    COALESCE(aml.tax_base_amount, ABS(aml.balance)) as tax_base_amount
                FROM account_move_line aml
                JOIN account_account aa ON aa.id = aml.account_id
                LEFT JOIN res_partner rp ON rp.id = aml.partner_id
                WHERE aml.move_id = %s
                    AND aml.tax_line_id IS NULL
                    AND aml.display_type NOT IN ('line_section', 'line_note', 'tax', 'payment_term')
                    AND (aml.debit > 0 OR aml.credit > 0)
                ORDER BY aml.id
            """
            self._cr.execute(query_fallback, [move_id])
            result = self._cr.dictfetchall()

        return result

    def _get_base_line(self, report, options, base_line_data, tribute_code, tax_id, move_id):
        """Generar línea base que originó el impuesto"""
        parent_line_id = report._get_generic_line_id('account.move', move_id,
                        parent_line_id=report._get_generic_line_id('account.tax', tax_id,
                        parent_line_id=report._get_generic_line_id(None, None, markup=f'tribute_{tribute_code}')))

        # Construir nombre de la línea base
        name_parts = []

        # Cuenta
        account_code = base_line_data['account_code']
        account_name = base_line_data['account_name']
        name_parts.append(f"Cta: {account_code} - {account_name}")

        # Detalles de cantidad y precio si existen
        if base_line_data['quantity'] and base_line_data['price_unit']:
            detail_info = f"Cant: {base_line_data['quantity']} x {base_line_data['price_unit']:.2f}"
            name_parts.append(detail_info)

        # Partner si existe
        if base_line_data['partner_name']:
            partner_info = base_line_data['partner_name']
            if base_line_data['partner_vat']:
                partner_info += f" [NIT: {base_line_data['partner_vat']}]"
            name_parts.append(f"Partner: {partner_info}")

        # Descripción de la línea
        line_name = base_line_data.get('line_name', '')
        if line_name:
            name_parts.append(f"Desc: {line_name}")

        # Para líneas base, mostrar el balance de la línea original como base
        base_amount = base_line_data['tax_base_amount'] or abs(base_line_data['balance'])

        # Datos para las columnas de texto
        line_data = {
            'move_name': '',  # El move_name se muestra en nivel superior
            'account': f"{account_code} - {account_name}",
            'ref': '',
            'label': line_name,
        }

        return {
            'id': report._get_generic_line_id('account.move.line', base_line_data['line_id'], parent_line_id=parent_line_id),
            'name': ' | '.join(name_parts),
            'columns': self._build_columns(report, options, base_amount, 0, line_data),  # Tax amount es 0 para líneas base
            'level': 3,
            'parent_id': parent_line_id,
            'caret_options': 'account.move.line',
            'class': 'o_account_reports_base_line',
        }

    def _get_total_line(self, report, options, tax_data):
        """Generar línea de total"""
        total_base = 0
        total_tax = 0
        
        # Obtener niveles permitidos
        allowed_levels = self._build_level_filter(options)

        for tribute_code, tribute_name, tax_groups in tax_data:
            for tax_group in tax_groups.values():
                total_base += tax_group['total_base']
                total_tax += tax_group['total_tax']
        
        return {
            'id': report._get_generic_line_id(None, None, markup='total'),
            'name': _('TOTAL GENERAL'),
            'columns': self._build_columns(report, options, total_base, total_tax),
            'level': 0,
            'class': 'total o_account_reports_totals_below_sections',
        }


    def _report_expand_unfoldable_line_co_tax_account(self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None):
        """Expandir impuesto para mostrar cuentas (NIVEL 1 -> NIVEL 2)"""
        report = self.env['account.report'].browse(options['report_id'])
        lines = []

        # Extraer tax_id y tribute_code del line_dict_id
        model, model_id = report._get_model_info_from_id(line_dict_id)

        tribute_match = None
        if 'tribute_' in line_dict_id:
            match = re.search(r'tribute_(\d+|[A-Za-z]+)', line_dict_id)
            if match:
                tribute_match = match.group(1)
                try:
                    tribute_match = int(tribute_match)
                except ValueError:
                    pass

        if model == 'account.tax' and tribute_match is not None:
            tax_id = model_id
            tribute_code = tribute_match

            # Obtener datos agrupados
            tax_data = self._get_tax_data_grouped(report, options)

            for tc, tn, tax_groups in tax_data:
                # Normalizar para comparacion
                tc_check = tc
                if isinstance(tc, int) and isinstance(tribute_code, str):
                    try:
                        tribute_code = int(tribute_code)
                    except ValueError:
                        tc_check = str(tc)

                if tc_check == tribute_code and tax_id in tax_groups:
                    tax_group = tax_groups[tax_id]
                    accounts = tax_group.get('accounts', {})

                    # Generar linea por cada cuenta
                    for account_id, account_data in sorted(accounts.items(), key=lambda x: x[1].get('account_code', '')):
                        account_line = self._get_account_line(report, options, account_data, tc, tax_id)
                        lines.append(account_line)
                    break

        return {
            'lines': lines,
            'offset_increment': 0,
            'has_more': False,
            'progress': progress,
        }

    def _report_expand_unfoldable_line_co_tax(self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None):
        """Método de expansión para líneas unfoldable - Jerarquía completa"""
        _logger.warning(f"=== CO TAX EXPAND CALLED === line_dict_id: {line_dict_id}")

        report = self.env['account.report'].browse(options['report_id'])
        lines = []

        # Parsear el line_dict_id para determinar el tipo de línea
        # Formato Odoo 18: puede ser "~markup~tribute_CODE" o "account.model~ID|parent_info"

        # Detectar si es una línea de tributo (NIVEL 0)
        tribute_match = None
        if 'tribute_' in line_dict_id:
            # Extraer el código del tributo
            match = re.search(r'tribute_(\d+|[A-Za-z]+)', line_dict_id)
            if match:
                tribute_match = match.group(1)
                # Convertir a int si es numérico (tax_group_id)
                try:
                    tribute_match = int(tribute_match)
                except ValueError:
                    pass  # Mantener como string si no es numérico

        # Verificar modelo usando el método de Odoo
        model, model_id = report._get_model_info_from_id(line_dict_id)
        _logger.info(f"Parsed line - model: {model}, model_id: {model_id}, tribute_match: {tribute_match}")

        if model is None and tribute_match is not None:
            # NIVEL 1: Expandir tributo → mostrar impuestos
            tribute_code = tribute_match
            _logger.info(f"Expanding tribute (NIVEL 0→1): {tribute_code}")

            tax_data = self._get_tax_data_grouped(report, options)

            for tc, tn, tax_groups in tax_data:
                # Comparar considerando tipo (int vs string)
                tc_normalized = tc
                tribute_normalized = tribute_code

                # Normalizar para comparación
                if isinstance(tc, int) and isinstance(tribute_code, str):
                    try:
                        tribute_normalized = int(tribute_code)
                    except ValueError:
                        pass
                elif isinstance(tc, str) and isinstance(tribute_code, int):
                    tc_normalized = str(tc)
                    tribute_normalized = str(tribute_code)

                if tc_normalized == tribute_normalized:
                    _logger.info(f"Found tribute data with {len(tax_groups)} tax groups")
                    for tax_id, tax_group in sorted(tax_groups.items()):
                        tax_line = self._get_tax_line(report, options, tax_id, tax_group, tc)
                        lines.append(tax_line)
                    break

        elif model == 'account.tax':
            # NIVEL 2: Expandir impuesto → mostrar movimientos
            _logger.info(f"Expanding tax (NIVEL 1→2): {model_id}")

            # Extraer tribute_code del line_dict_id completo
            tribute_code = tribute_match

            if tribute_code is not None:
                _logger.info(f"Parent tribute: {tribute_code}")
                tax_data = self._get_tax_data_grouped(report, options)

                for tc, tn, tax_groups in tax_data:
                    # Normalizar para comparación
                    tc_check = tc
                    if isinstance(tc, int) and isinstance(tribute_code, str):
                        try:
                            tribute_code = int(tribute_code)
                        except ValueError:
                            tc_check = str(tc)

                    if tc_check == tribute_code and model_id in tax_groups:
                        tax_group = tax_groups[model_id]
                        _logger.info(f"Found {len(tax_group['details'])} details for tax {model_id}")

                        # Agrupar por movimiento
                        move_groups = self._group_by_move(tax_group['details'])
                        for move_id, move_data in sorted(move_groups.items(), key=lambda x: (x[1]['date'], x[1]['move_name']), reverse=True):
                            move_line = self._get_move_line(report, options, move_data, tc, model_id)
                            lines.append(move_line)
                        break

        elif model == 'account.account':
            # NIVEL 3: Expandir cuenta -> mostrar movimientos
            _logger.info(f"Expanding account (NIVEL 2->3): {model_id}")

            tribute_code = tribute_match
            tax_id = None

            # Buscar tax_id en el line_dict_id
            tax_match = re.search(r'tax_(\d+)', line_dict_id)
            if tax_match:
                tax_id = int(tax_match.group(1))

            if tribute_code is not None and tax_id is not None:
                tax_data = self._get_tax_data_grouped(report, options)

                for tc, tn, tax_groups in tax_data:
                    tc_check = tc
                    if isinstance(tc, int) and isinstance(tribute_code, str):
                        try:
                            tribute_code = int(tribute_code)
                        except ValueError:
                            tc_check = str(tc)

                    if tc_check == tribute_code and tax_id in tax_groups:
                        tax_group = tax_groups[tax_id]
                        accounts = tax_group.get('accounts', {})

                        if model_id in accounts:
                            account_data = accounts[model_id]
                            # Agrupar por movimiento
                            move_groups = self._group_by_move(account_data['details'])

                            for move_id, move_data in sorted(move_groups.items(), key=lambda x: (x[1]['date'], x[1]['move_name']), reverse=True):
                                move_line = self._get_move_line(report, options, move_data, tc, tax_id)
                                # Ajustar parent_id para que apunte a la cuenta
                                move_line['parent_id'] = line_dict_id
                                move_line['level'] = 3
                                lines.append(move_line)
                        break

        elif model == 'account.move':
            # NIVEL 4: Expandir movimiento -> mostrar lineas base
            _logger.info(f"Expanding move (NIVEL 2→3): {model_id}")

            # Extraer tribute_code y tax_id del line_dict_id
            tribute_code = tribute_match
            tax_id = None

            # Buscar tax_id en el line_dict_id
            tax_match = re.search(r'account\.tax~(\d+)', line_dict_id)
            if tax_match:
                tax_id = int(tax_match.group(1))

            _logger.info(f"Extracted - tribute_code: {tribute_code}, tax_id: {tax_id}")

            if tribute_code is not None and tax_id is not None:
                _logger.info(f"Expanding move {model_id} for tax {tax_id} in tribute {tribute_code}")

                # Obtener líneas base
                base_lines = self._get_base_lines_for_move(report, options, model_id, tax_id)
                _logger.info(f"Found {len(base_lines)} base lines for move {model_id}")

                for base_line_data in base_lines:
                    base_line = self._get_base_line(report, options, base_line_data, tribute_code, tax_id, model_id)
                    lines.append(base_line)

        _logger.info(f"Returning {len(lines)} expanded lines")
        return {
            'lines': lines,
            'offset_increment': 0,
            'has_more': False,
            'progress': progress,
        }

    def _get_all_tributes(self):
        """Lista completa de tributos"""
        return [
            ('01', 'IVA'),
            ('02', 'IC - Impuesto al Consumo'),
            ('03', 'ICA'),
            ('04', 'INC'),
            ('05', 'ReteIVA'),
            ('06', 'ReteFuente'),
            ('07', 'ReteICA'),
            ('08', 'ReteCREE'),
            ('20', 'FtoHorticultura'),
            ('21', 'Timbre'),
            ('22', 'Bolsas'),
            ('23', 'INCarbono'),
            ('24', 'INCombustibles'),
            ('25', 'Sobretasa Combustibles'),
            ('26', 'Sordicom'),
            ('ZY', 'No causa'),
            ('ZZ', 'Otros')
        ]

    def export_detailed_tax_report_co(self, options):
        """Exportar reporte detallado de impuestos a Excel con todos los filtros aplicados"""
        import io
        from odoo.tools.misc import xlsxwriter

        report = self.env['account.report'].browse(options['report_id'])
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet(report.name[:31])  # Max 31 caracteres

        # Definir formatos
        formats = self._get_xlsx_formats_tax(workbook)

        # Configurar anchos de columna
        column_widths = [12, 18, 35, 15, 12, 18, 12, 18]
        for col, width in enumerate(column_widths):
            sheet.set_column(col, col, width)

        # Encabezado del reporte
        row = 0
        sheet.merge_range(row, 0, row, 7, report.name, formats['title'])
        row += 1

        # Información de filtros
        date_from = options.get('date', {}).get('date_from', '')
        date_to = options.get('date', {}).get('date_to', '')
        sheet.write(row, 0, f"Período: {date_from} - {date_to}", formats['subtitle'])
        row += 2

        # Encabezados de columnas
        headers = ['Fecha', 'Documento', 'Tercero', 'NIT/CC', 'Concepto', 'Base Gravable', 'Tarifa %', 'Valor Impuesto']
        for col, header in enumerate(headers):
            sheet.write(row, col, header, formats['header'])
        row += 1

        # Obtener datos con filtros aplicados
        tax_data = self._get_tax_data_grouped(report, options)

        total_base = 0
        total_tax = 0

        # Obtener niveles permitidos
        allowed_levels = self._build_level_filter(options)

        for tribute_code, tribute_name, tax_groups in tax_data:
            # Línea de tributo (grupo)
            sheet.write(row, 0, f'[{tribute_code}] {tribute_name}', formats['group'])
            sheet.merge_range(row, 1, row, 4, '', formats['group'])

            tribute_base = sum(tg['total_base'] for tg in tax_groups.values())
            tribute_tax = sum(tg['total_tax'] for tg in tax_groups.values())

            sheet.write_number(row, 5, tribute_base, formats['group_num'])
            sheet.write(row, 6, '', formats['group'])
            sheet.write_number(row, 7, tribute_tax, formats['group_num'])
            row += 1

            for tax_id, tax_group in tax_groups.items():
                # Línea de impuesto
                tax_name = tax_group['tax_name']
                if tax_group['amount_type'] == 'percent' and tax_group['tax_rate']:
                    tax_name += f" {tax_group['tax_rate']}%"

                sheet.write(row, 0, f'  {tax_name}', formats['tax'])
                sheet.merge_range(row, 1, row, 4, '', formats['tax'])
                sheet.write_number(row, 5, tax_group['total_base'], formats['tax_num'])
                sheet.write(row, 6, '', formats['tax'])
                sheet.write_number(row, 7, tax_group['total_tax'], formats['tax_num'])
                row += 1

                # Detalles por movimiento
                for detail in tax_group['details']:
                    # Fecha
                    if detail.get('date'):
                        sheet.write(row, 0, detail['date'], formats['date'])
                    else:
                        sheet.write(row, 0, '', formats['detail'])

                    # Documento
                    sheet.write(row, 1, detail.get('move_name', ''), formats['detail'])

                    # Tercero
                    sheet.write(row, 2, detail.get('partner_name', ''), formats['detail'])

                    # NIT/CC
                    sheet.write(row, 3, detail.get('partner_vat', ''), formats['detail'])

                    # Concepto
                    sheet.write(row, 4, detail.get('concept_code', ''), formats['detail'])

                    # Base Gravable
                    base_amount = detail.get('tax_base_amount', 0) or 0
                    sheet.write_number(row, 5, base_amount, formats['detail_num'])

                    # Tarifa % (convertir a decimal para formato %)
                    tax_rate = (detail.get('tax_rate', 0) or 0) / 100.0
                    sheet.write_number(row, 6, tax_rate, formats['detail_percent'])

                    # Valor Impuesto
                    tax_amount = abs(detail.get('balance', 0) or 0)
                    sheet.write_number(row, 7, tax_amount, formats['detail_num'])

                    row += 1

            total_base += tribute_base
            total_tax += tribute_tax

        # Línea de total general
        row += 1
        sheet.write(row, 0, 'TOTAL GENERAL', formats['total'])
        sheet.merge_range(row, 1, row, 4, '', formats['total'])
        sheet.write_number(row, 5, total_base, formats['total_num'])
        sheet.write(row, 6, '', formats['total'])
        sheet.write_number(row, 7, total_tax, formats['total_num'])

        workbook.close()
        output.seek(0)

        # Generar nombre del archivo
        file_name = f"{report.name.lower().replace(' ', '_')}_{date_from}_{date_to}.xlsx"

        return {
            'file_name': file_name,
            'file_content': output.read(),
            'file_type': 'xlsx',
        }

    def _get_xlsx_formats_tax(self, workbook):
        """Formatos para el Excel de impuestos"""
        formats = {}

        # Título
        formats['title'] = workbook.add_format({
            'bold': True,
            'font_size': 14,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#2c3e50',
            'font_color': 'white',
            'border': 1,
        })

        # Subtítulo
        formats['subtitle'] = workbook.add_format({
            'font_size': 10,
            'italic': True,
        })

        # Encabezados
        formats['header'] = workbook.add_format({
            'bold': True,
            'font_size': 10,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#34495e',
            'font_color': 'white',
            'border': 1,
        })

        # Grupo (tributo)
        formats['group'] = workbook.add_format({
            'bold': True,
            'font_size': 10,
            'bg_color': '#3498db',
            'font_color': 'white',
            'border': 1,
        })
        formats['group_num'] = workbook.add_format({
            'bold': True,
            'font_size': 10,
            'bg_color': '#3498db',
            'font_color': 'white',
            'border': 1,
            'num_format': '#,##0.00',
            'align': 'right',
        })

        # Impuesto
        formats['tax'] = workbook.add_format({
            'bold': True,
            'font_size': 9,
            'bg_color': '#ecf0f1',
            'font_color': '#2c3e50',
            'border': 1,
        })
        formats['tax_num'] = workbook.add_format({
            'bold': True,
            'font_size': 9,
            'bg_color': '#ecf0f1',
            'font_color': '#2c3e50',
            'border': 1,
            'num_format': '#,##0.00',
            'align': 'right',
        })

        # Detalle
        formats['detail'] = workbook.add_format({
            'font_size': 9,
            'border': 1,
        })
        formats['detail_num'] = workbook.add_format({
            'font_size': 9,
            'border': 1,
            'num_format': '#,##0.00',
            'align': 'right',
        })
        formats['detail_percent'] = workbook.add_format({
            'font_size': 9,
            'border': 1,
            'num_format': '0.00%',
            'align': 'right',
        })
        formats['date'] = workbook.add_format({
            'font_size': 9,
            'border': 1,
            'num_format': 'dd/mm/yyyy',
            'align': 'center',
        })

        # Total
        formats['total'] = workbook.add_format({
            'bold': True,
            'font_size': 11,
            'bg_color': '#2c3e50',
            'font_color': 'white',
            'border': 2,
        })
        formats['total_num'] = workbook.add_format({
            'bold': True,
            'font_size': 11,
            'bg_color': '#2c3e50',
            'font_color': 'white',
            'border': 2,
            'num_format': '#,##0.00',
            'align': 'right',
        })

        return formats

    def debug_hierarchy_test(self, options):
        """Método de debug para probar la jerarquía completa"""
        import logging
        _logger = logging.getLogger(__name__)
        
        report = self.env['account.report'].browse(options['report_id'])
        tax_data = self._get_tax_data_grouped(report, options)
        
        _logger.info(f"=== DEBUG HIERARCHY TEST ===")
        
        # Obtener niveles permitidos
        allowed_levels = self._build_level_filter(options)

        for tribute_code, tribute_name, tax_groups in tax_data:
            _logger.info(f"NIVEL 0 - Tributo: [{tribute_code}] {tribute_name}")
            
            for tax_id, tax_group in tax_groups.items():
                _logger.info(f"  NIVEL 1 - Impuesto: {tax_group['tax_name']} (ID: {tax_id})")
                
                move_groups = self._group_by_move(tax_group['details'])
                for move_id, move_data in move_groups.items():
                    _logger.info(f"    NIVEL 2 - Movimiento: {move_data['move_name']} (ID: {move_id})")
                    
                    base_lines = self._get_base_lines_for_move(report, options, move_id, tax_id)
                    for base_line in base_lines:
                        _logger.info(f"      NIVEL 3 - Línea Base: {base_line['account_code']} - {base_line.get('line_name', 'Sin descripción')}")
        
        return {"status": "debug_complete", "levels_tested": 4}


# ============================================
# REPORTES ESPECÍFICOS
# ============================================

class AccountTaxReportGeneral(models.AbstractModel):
    """Reporte General - Muestra todos los impuestos sin filtro por concept_type"""
    _name = 'account.tax.report.general.handler'
    _inherit = 'account.tax.report.co.base'
    _description = 'Colombian General Tax Report Handler'

    def _get_report_name(self):
        return _("Reporte General de Impuestos")

    # No define _get_concept_types() para mostrar todos


class AccountTaxReportIVA(models.AbstractModel):
    """Reporte de IVA - Filtra por concept_type = 'iva'"""
    _name = 'account.tax.report.iva.handler'
    _inherit = 'account.tax.report.co.base'
    _description = 'Colombian IVA Tax Report Handler'

    def _get_concept_types(self):
        return ['iva']

    def _get_report_name(self):
        return _("Reporte de IVA")


class AccountTaxReportReteFuente(models.AbstractModel):
    """Reporte de Retención en la Fuente - Filtra por concept_type = 'retefuente'"""
    _name = 'account.tax.report.retefuente.handler'
    _inherit = 'account.tax.report.co.base'
    _description = 'Colombian ReteFuente Report Handler'

    def _get_concept_types(self):
        return ['retefuente']

    def _get_report_name(self):
        return _("Reporte de Retención en la Fuente")


class AccountTaxReportReteIVA(models.AbstractModel):
    """Reporte de Retención de IVA - Filtra por concept_type = 'reteiva'"""
    _name = 'account.tax.report.reteiva.handler'
    _inherit = 'account.tax.report.co.base'
    _description = 'Colombian ReteIVA Report Handler'

    def _get_concept_types(self):
        return ['reteiva']

    def _get_report_name(self):
        return _("Reporte de Retención de IVA")


class AccountTaxReportReteICA(models.AbstractModel):
    """Reporte de Retención de ICA - Filtra por concept_type = 'reteica'"""
    _name = 'account.tax.report.reteica.handler'
    _inherit = 'account.tax.report.co.base'
    _description = 'Colombian ReteICA Report Handler'

    def _get_concept_types(self):
        return ['reteica']

    def _get_report_name(self):
        return _("Reporte de Retención ICA")


class AccountTaxReportINC(models.AbstractModel):
    """Reporte de Impuesto Nacional al Consumo - Filtra por concept_type = 'inc'"""
    _name = 'account.tax.report.inc.handler'
    _inherit = 'account.tax.report.co.base'
    _description = 'Colombian INC (National Consumption Tax) Report Handler'

    def _get_concept_types(self):
        return ['inc']

    def _get_report_name(self):
        return _("Reporte de Impuesto Nacional al Consumo")


class AccountTaxReportConsumo(models.AbstractModel):
    """Reporte de Impuesto al Consumo - Para compatibilidad con reportes existentes
    Nota: En tax_base_threshold solo existe 'inc', este handler es para legacy"""
    _name = 'account.tax.report.consumo.handler'
    _inherit = 'account.tax.report.co.base'
    _description = 'Colombian Consumption Tax Report Handler'

    def _get_concept_types(self):
        # Usar INC como equivalente al impuesto al consumo
        return ['inc']

    def _get_report_name(self):
        return _("Reporte de Impuesto al Consumo")


class AccountTaxReportOtros(models.AbstractModel):
    """Reporte de Otros Impuestos - Filtra por concept_type = 'other'"""
    _name = 'account.tax.report.otros.handler'
    _inherit = 'account.tax.report.co.base'
    _description = 'Colombian Other Taxes Report Handler'

    def _get_concept_types(self):
        return ['other']

    def _get_report_name(self):
        return _("Reporte de Otros Impuestos")