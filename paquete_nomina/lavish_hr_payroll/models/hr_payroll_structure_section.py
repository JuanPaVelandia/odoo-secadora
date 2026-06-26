# -*- coding: utf-8 -*-
"""
Sistema de Secciones para Estructura Salarial
=============================================

Permite organizar las reglas salariales de una estructura en secciones:
- DEVENGOS: Ingresos del empleado
- DEDUCCIONES: Descuentos aplicados
- TOTALDEV: Total Devengos
- TOTALDED: Total Deducciones
- NET: Neto a Pagar
- PROVISIONES: Provisiones (cesantias, vacaciones, prima)
- IBD_SS: IBC Seguridad Social

Cada seccion puede tener:
- Orden de ejecucion (sequence)
- Configuracion contable propia
- Reglas filtradas por categoria
- Estado activo/inactivo
- Relacion con lineas de nomina

Flujo de Ejecucion:
1. Estructura define use_sections = True
2. Se crean secciones con action_create_default_sections()
3. En liquidacion, se ejecutan reglas por seccion ordenadas
4. Cada seccion calcula sus reglas y totaliza
5. La contabilizacion usa la configuracion de cada seccion
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging
from collections import defaultdict

_logger = logging.getLogger(__name__)


# =============================================================================
# TIPOS DE SECCION DISPONIBLES
# =============================================================================
SECTION_TYPES = [
    ('devengos', 'DEVENGOS - Ingresos'),
    ('deducciones', 'DEDUCCIONES - Descuentos'),
    ('totaldev', 'TOTALDEV - Total Devengos'),
    ('totalded', 'TOTALDED - Total Deducciones'),
    ('net', 'NET - Neto a Pagar'),
    ('provisiones', 'PROVISIONES - Provisiones'),
    ('ibd_ss', 'IBD_SS - IBC Seguridad Social'),
]

# Diccionario para acceso rapido
SECTION_TYPE_DICT = dict(SECTION_TYPES)

# Mapeo de tipo de seccion a codigos de categoria de reglas
SECTION_CATEGORY_MAP = {
    'devengos': ['BASIC', 'AUX', 'DEV', 'DEV_SALARIAL', 'DEV_NO_SALARIAL',
                 'HEYREC', 'COMISIONES', 'HED', 'HEN', 'REC', 'VACACIONES',
                 'INCAPACIDAD', 'LICENCIA_MATERNIDAD', 'LICENCIA_REMUNERADA',
                 'PRIMA', 'PRESTACIONES_SOCIALES', 'CESANTIAS'],
    'deducciones': ['DED', 'DEDUCCIONES', 'DESCUENTO_AFC', 'SANCIONES'],
    'totaldev': ['TOTALDEV', 'GROSS'],
    'totalded': ['TOTALDED'],
    'net': ['NET', 'NETO'],
    'provisiones': ['PROVISIONES', 'PROV_CES', 'PROV_VAC', 'PROV_PRIMA',
                    'PROV_INT_CES', 'PROVISION'],
    'ibd_ss': ['IBD', 'IBC', 'IBC_R', 'SSOCIAL', 'SSOCIAL001', 'SSOCIAL002',
               'DED_PENS', 'DED_EPS', 'FOND_SOL', 'FOND_SUB'],
}

# Orden de ejecucion por defecto
SECTION_DEFAULT_SEQUENCE = {
    'devengos': 10,
    'deducciones': 20,
    'ibd_ss': 30,
    'totaldev': 40,
    'totalded': 50,
    'net': 60,
    'provisiones': 70,
}

# Colores por tipo de seccion (para Kanban)
SECTION_COLORS = {
    'devengos': 10,      # Verde
    'deducciones': 1,    # Rojo
    'totaldev': 4,       # Azul claro
    'totalded': 9,       # Fucsia
    'net': 5,            # Morado
    'provisiones': 3,    # Amarillo
    'ibd_ss': 11,        # Cyan
}


class HrPayrollStructureSection(models.Model):
    """
    Seccion de Estructura Salarial

    Define una seccion dentro de una estructura salarial para organizar
    las reglas y su configuracion contable.

    Relaciones:
    - structure_id: Estructura salarial padre
    - rule_ids: Reglas salariales (M2M computado)
    - payslip_line_ids: Lineas de nomina de esta seccion
    - accounting_config_id: Configuracion contable
    """
    _name = 'hr.payroll.structure.section'
    _description = 'Seccion de Estructura Salarial'
    _order = 'structure_id, sequence, id'
    _rec_name = 'display_name'

    # =========================================================================
    # CAMPOS BASICOS
    # =========================================================================
    name = fields.Char(
        string='Nombre',
        required=True,
        translate=True,
        help='Nombre descriptivo de la seccion'
    )

    display_name = fields.Char(
        string='Nombre Completo',
        compute='_compute_display_name',
        store=True
    )

    structure_id = fields.Many2one(
        'hr.payroll.structure',
        string='Estructura Salarial',
        required=True,
        ondelete='cascade',
        index=True
    )

    # v19 fix: el source hr.payroll.structure.name es traducible. Un related
    # stored sin translate=True produce warning "Translated stored related
    # field will not be computed correctly in all languages". Quitamos store
    # para que se compute on-demand en el idioma activo.
    structure_name = fields.Char(
        related='structure_id.name',
        string='Nombre Estructura',
    )

    section_type = fields.Selection(
        selection=SECTION_TYPES,
        string='Tipo de Seccion',
        required=True,
        index=True,
        help='Tipo de seccion que agrupa las reglas salariales'
    )

    section_type_label = fields.Char(
        string='Etiqueta Tipo',
        compute='_compute_section_type_label',
        store=True
    )

    sequence = fields.Integer(
        string='Orden de Ejecucion',
        default=10,
        index=True,
        help='Orden en que se procesan las secciones (menor = primero)'
    )

    active = fields.Boolean(
        string='Activo',
        default=True,
        index=True,
        help='Si esta desactivado, las reglas de esta seccion no se procesan'
    )

    color = fields.Integer(
        string='Color',
        default=0,
        help='Color para vista Kanban'
    )

    # =========================================================================
    # CONFIGURACION DE REGLAS
    # =========================================================================
    category_codes = fields.Char(
        string='Codigos de Categoria',
        help='Codigos de categoria de reglas (separados por coma). '
             'Vacio = usa categorias por defecto del tipo.'
    )

    exclude_codes = fields.Char(
        string='Codigos a Excluir',
        help='Codigos de regla a excluir (separados por coma)'
    )

    rule_ids = fields.Many2many(
        'hr.salary.rule',
        'hr_structure_section_rule_rel',
        'section_id',
        'rule_id',
        string='Reglas Salariales',
        compute='_compute_rule_ids',
        store=True
    )

    rule_count = fields.Integer(
        string='Cantidad de Reglas',
        compute='_compute_rule_count',
        store=True
    )

    rule_codes = fields.Char(
        string='Codigos de Reglas',
        compute='_compute_rule_codes',
        help='Lista de codigos de reglas en esta seccion'
    )

    # =========================================================================
    # CONFIGURACION CONTABLE
    # =========================================================================
    accounting_config_id = fields.Many2one(
        'hr.accounting.structure.section',
        string='Configuracion Contable',
        help='Configuracion de estructura contable para esta seccion'
    )

    use_direct_accounts = fields.Boolean(
        string='Usar Cuentas Directas',
        default=True,
        help='Usar las cuentas definidas en las reglas salariales'
    )

    debit_account_id = fields.Many2one(
        'account.account',
        string='Cuenta Debito por Defecto',
        help='Cuenta debito para reglas sin cuenta asignada'
    )

    credit_account_id = fields.Many2one(
        'account.account',
        string='Cuenta Credito por Defecto',
        help='Cuenta credito para reglas sin cuenta asignada'
    )

    # =========================================================================
    # CAMPOS DE EJECUCION / ESTADISTICAS
    # =========================================================================
    is_total_section = fields.Boolean(
        string='Es Seccion de Totales',
        compute='_compute_is_total_section',
        store=True,
        help='Indica si es una seccion que calcula totales'
    )

    is_calculation_section = fields.Boolean(
        string='Es Seccion de Calculo',
        compute='_compute_is_calculation_section',
        store=True,
        help='Indica si es una seccion que requiere calculos especiales'
    )

    depends_on_sections = fields.Many2many(
        'hr.payroll.structure.section',
        'hr_section_dependency_rel',
        'section_id',
        'depends_on_id',
        string='Depende de Secciones',
        domain="[('structure_id', '=', structure_id), ('id', '!=', id)]",
        help='Secciones que deben ejecutarse antes de esta'
    )

    dependent_sections = fields.Many2many(
        'hr.payroll.structure.section',
        'hr_section_dependency_rel',
        'depends_on_id',
        'section_id',
        string='Secciones Dependientes',
        help='Secciones que dependen de esta (se saltan si esta no se ejecuta)'
    )

    skip_if_dependency_skipped = fields.Boolean(
        string='Omitir si Dependencia Omitida',
        default=True,
        help='Si una seccion de la que depende fue omitida, omitir esta tambien'
    )

    # =========================================================================
    # CAMPOS DE NOMINAS RELACIONADAS
    # =========================================================================
    payslip_line_ids = fields.Many2many(
        'hr.payslip.line',
        string='Lineas de Nomina',
        compute='_compute_payslip_stats',
        help='Lineas de nomina que pertenecen a esta seccion'
    )

    payslip_line_count = fields.Integer(
        string='Lineas de Nomina (conteo)',
        compute='_compute_payslip_stats'
    )

    total_amount = fields.Monetary(
        string='Total Acumulado',
        compute='_compute_payslip_stats',
        currency_field='currency_id',
        help='Suma total de lineas de nomina en el periodo actual'
    )

    last_month_total = fields.Monetary(
        string='Total Mes Anterior',
        compute='_compute_payslip_stats',
        currency_field='currency_id'
    )

    payslip_count = fields.Integer(
        string='Nominas',
        compute='_compute_payslip_stats',
        help='Cantidad de nominas que usan esta seccion'
    )

    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        default=lambda self: self.env.company.currency_id
    )

    # =========================================================================
    # CAMPOS INFORMATIVOS
    # =========================================================================
    notes = fields.Text(string='Notas')

    company_id = fields.Many2one(
        'res.company',
        string='Compania',
        default=lambda self: self.env.company
    )

    # =========================================================================
    # CAMPOS DE CONDICIONES
    # =========================================================================
    apply_condition = fields.Selection([
        ('always', 'Siempre Aplicar'),
        ('python', 'Condicion Python'),
        ('domain', 'Filtro de Empleados'),
    ], string='Tipo de Condicion', default='always',
       help='Determina cuando se aplica esta seccion')

    python_condition = fields.Text(
        string='Condicion Python',
        help="""Condicion Python que debe retornar True para aplicar la seccion.
Variables disponibles:
- employee: hr.employee
- contract: hr.contract
- payslip: hr.payslip
- date_from, date_to: fechas del periodo
- company: res.company
Ejemplo: employee.department_id.name == 'Ventas'"""
    )

    employee_domain = fields.Char(
        string='Filtro de Empleados',
        default='[]',
        help="""Dominio para filtrar empleados a los que aplica esta seccion.
Ejemplo: [('department_id.name', '=', 'Ventas')]"""
    )

    exclude_employee_domain = fields.Char(
        string='Excluir Empleados',
        default='[]',
        help="""Dominio para EXCLUIR empleados de esta seccion.
Ejemplo: [('job_id.name', 'ilike', 'Practicante')]"""
    )

    skip_on_leave = fields.Boolean(
        string='Saltar en Ausencia',
        default=False,
        help='No aplicar esta seccion si el empleado tiene ausencia todo el periodo'
    )

    skip_on_termination = fields.Boolean(
        string='Saltar en Liquidacion',
        default=False,
        help='No aplicar esta seccion en nominas de liquidacion'
    )

    only_on_termination = fields.Boolean(
        string='Solo en Liquidacion',
        default=False,
        help='Solo aplicar esta seccion en nominas de liquidacion'
    )

    min_days_worked = fields.Integer(
        string='Dias Minimos Trabajados',
        default=0,
        help='Dias minimos trabajados para aplicar esta seccion (0 = sin minimo)'
    )

    # =========================================================================
    # CAMPOS PARA VISUALIZACION DE FLUJO
    # =========================================================================
    icon = fields.Char(
        string='Icono',
        compute='_compute_icon',
        store=True,
        help='Icono FontAwesome para la vista de flujo'
    )

    # Posicionamiento manual en el flujo
    flow_row = fields.Integer(
        string='Fila en Flujo',
        default=0,
        help='Fila donde se muestra esta seccion en el flujo (0 = auto)'
    )

    flow_column = fields.Integer(
        string='Columna en Flujo',
        default=0,
        help='Columna dentro de la fila (0 = auto)'
    )

    flow_position = fields.Selection([
        ('auto', 'Automatico'),
        ('start', 'Inicio'),
        ('middle', 'Intermedio'),
        ('end', 'Final'),
        ('isolated', 'Aislado'),
    ], string='Posicion en Flujo', default='auto',
       help='Posicion de la seccion en el diagrama de flujo')

    # Conexiones manuales entre secciones
    connected_to_ids = fields.Many2many(
        'hr.payroll.structure.section',
        'hr_section_connection_rel',
        'from_section_id',
        'to_section_id',
        string='Conectado A',
        domain="[('structure_id', '=', structure_id), ('id', '!=', id)]",
        help='Secciones a las que se conecta visualmente (flujo de datos)'
    )

    connected_from_ids = fields.Many2many(
        'hr.payroll.structure.section',
        'hr_section_connection_rel',
        'to_section_id',
        'from_section_id',
        string='Conectado Desde',
        help='Secciones que se conectan a esta (inverso)'
    )

    show_in_flow = fields.Boolean(
        string='Mostrar en Flujo',
        default=True,
        help='Si se muestra esta seccion en el diagrama de flujo'
    )

    next_section_ids = fields.Many2many(
        'hr.payroll.structure.section',
        'hr_section_flow_rel',
        'section_id',
        'next_section_id',
        string='Secciones Siguientes',
        compute='_compute_next_sections',
        help='Secciones que se ejecutan despues de esta (auto-calculado)'
    )

    # =========================================================================
    # METODOS COMPUTADOS
    # =========================================================================
    @api.depends('name', 'section_type', 'structure_id.name')
    def _compute_display_name(self):
        for section in self:
            type_label = SECTION_TYPE_DICT.get(section.section_type, '')
            type_short = type_label.split(' - ')[0] if type_label else ''
            section.display_name = f"[{type_short}] {section.name}"

    @api.depends('section_type')
    def _compute_section_type_label(self):
        for section in self:
            section.section_type_label = SECTION_TYPE_DICT.get(
                section.section_type, ''
            )

    @api.depends('section_type')
    def _compute_is_total_section(self):
        total_types = ('totaldev', 'totalded', 'net')
        for section in self:
            section.is_total_section = section.section_type in total_types

    @api.depends('section_type')
    def _compute_is_calculation_section(self):
        calc_types = ('ibd_ss', 'provisiones')
        for section in self:
            section.is_calculation_section = section.section_type in calc_types

    @api.depends('structure_id', 'structure_id.rule_ids', 'section_type',
                 'category_codes', 'exclude_codes')
    def _compute_rule_ids(self):
        """Computar las reglas que pertenecen a esta seccion"""
        for section in self:
            if not section.structure_id:
                section.rule_ids = [(5, 0, 0)]
                continue

            categories = section._get_section_categories()
            rules = section.structure_id.rule_ids.filtered(
                lambda r: section._rule_matches_section(r, categories)
            )
            section.rule_ids = [(6, 0, rules.ids)]

    @api.depends('rule_ids')
    def _compute_rule_count(self):
        for section in self:
            section.rule_count = len(section.rule_ids)

    def _compute_rule_codes(self):
        for section in self:
            codes = section.rule_ids.mapped('code')
            section.rule_codes = ', '.join(filter(None, codes))

    def _compute_payslip_stats(self):
        """Calcular estadisticas de nominas para esta seccion"""
        from datetime import date
        from dateutil.relativedelta import relativedelta

        today = date.today()
        first_day_current = today.replace(day=1)
        first_day_last = first_day_current - relativedelta(months=1)
        last_day_last = first_day_current - relativedelta(days=1)

        PayslipLine = self.env['hr.payslip.line']

        sections_with_rules = self.filtered(lambda s: s.rule_ids)
        if not sections_with_rules:
            for section in self:
                section.payslip_line_ids = [(5, 0, 0)]
                section.payslip_line_count = 0
                section.total_amount = 0
                section.last_month_total = 0
                section.payslip_count = 0
            return

        rule_ids_by_section = {
            section.id: set(section.rule_ids.ids)
            for section in sections_with_rules
        }
        all_rule_ids = set()
        for rule_ids in rule_ids_by_section.values():
            all_rule_ids.update(rule_ids)

        current_lines = PayslipLine.search([
            ('salary_rule_id', 'in', list(all_rule_ids)),
            ('date_from', '>=', first_day_current),
            ('slip_id.state', 'in', ['done', 'paid']),
        ])

        current_line_ids_by_rule = defaultdict(list)
        current_totals_by_rule = defaultdict(float)
        current_slip_ids_by_rule = defaultdict(set)
        for line in current_lines:
            rule_id = line.salary_rule_id.id
            current_line_ids_by_rule[rule_id].append(line.id)
            current_totals_by_rule[rule_id] += line.total or 0.0
            if line.slip_id:
                current_slip_ids_by_rule[rule_id].add(line.slip_id.id)

        last_month_totals_by_rule = {}
        last_month_grouped = PayslipLine._read_group(
            domain=[
                ('salary_rule_id', 'in', list(all_rule_ids)),
                ('date_from', '>=', first_day_last),
                ('date_from', '<=', last_day_last),
                ('slip_id.state', 'in', ['done', 'paid']),
            ],
            groupby=['salary_rule_id'],
            aggregates=['total:sum'],
        )
        for rule_rec, total in last_month_grouped:
            if not rule_rec:
                continue
            last_month_totals_by_rule[rule_rec.id] = total or 0.0

        for section in self:
            rule_ids = rule_ids_by_section.get(section.id)
            if not rule_ids:
                section.payslip_line_ids = [(5, 0, 0)]
                section.payslip_line_count = 0
                section.total_amount = 0
                section.last_month_total = 0
                section.payslip_count = 0
                continue

            line_ids = []
            total_amount = 0.0
            last_month_total = 0.0
            slip_ids = set()
            for rule_id in rule_ids:
                line_ids.extend(current_line_ids_by_rule.get(rule_id, []))
                total_amount += current_totals_by_rule.get(rule_id, 0.0)
                last_month_total += last_month_totals_by_rule.get(rule_id, 0.0)
                slip_ids.update(current_slip_ids_by_rule.get(rule_id, set()))

            section.payslip_line_ids = [(6, 0, line_ids)]
            section.payslip_line_count = len(line_ids)
            section.total_amount = total_amount
            section.last_month_total = last_month_total
            section.payslip_count = len(slip_ids)

    def _compute_icon(self):
        """Asignar icono FontAwesome segun tipo de seccion"""
        SECTION_ICONS = {
            'devengos': 'fa-plus-circle',
            'deducciones': 'fa-minus-circle',
            'totaldev': 'fa-arrow-up',
            'totalded': 'fa-arrow-down',
            'net': 'fa-money',
            'provisiones': 'fa-database',
            'ibd_ss': 'fa-shield',
        }
        for section in self:
            section.icon = SECTION_ICONS.get(section.section_type, 'fa-circle')

    def _compute_flow_position(self):
        """Determinar posicion en el flujo de ejecucion"""
        for section in self:
            if section.section_type == 'devengos':
                section.flow_position = 'start'
            elif section.section_type == 'net':
                section.flow_position = 'end'
            else:
                section.flow_position = 'middle'

    def _compute_next_sections(self):
        """Calcular secciones que siguen en el flujo"""
        FLOW_ORDER = {
            'devengos': ['deducciones', 'ibd_ss'],
            'deducciones': ['totalded'],
            'ibd_ss': ['totaldev'],
            'totaldev': ['net'],
            'totalded': ['net'],
            'net': ['provisiones'],
            'provisiones': [],
        }
        for section in self:
            if not section.structure_id:
                section.next_section_ids = [(5, 0, 0)]
                continue

            next_types = FLOW_ORDER.get(section.section_type, [])
            next_sections = section.structure_id.section_ids.filtered(
                lambda s: s.section_type in next_types and s.active
            )
            section.next_section_ids = [(6, 0, next_sections.ids)]

    # =========================================================================
    # METODOS DE CONEXION DE SECCIONES
    # =========================================================================
    def action_connect_to(self, target_section_id):
        """
        Conectar esta seccion a otra seccion.

        Args:
            target_section_id: ID de la seccion destino
        """
        self.ensure_one()
        target = self.browse(target_section_id)
        if target and target.structure_id == self.structure_id:
            self.write({'connected_to_ids': [(4, target_section_id)]})
            return True
        return False

    def action_disconnect_from(self, target_section_id):
        """
        Desconectar esta seccion de otra seccion.

        Args:
            target_section_id: ID de la seccion a desconectar
        """
        self.ensure_one()
        self.write({'connected_to_ids': [(3, target_section_id)]})
        return True

    def action_toggle_connection(self, target_section_id):
        """
        Alternar conexion con otra seccion.

        Args:
            target_section_id: ID de la seccion objetivo
        """
        self.ensure_one()
        if target_section_id in self.connected_to_ids.ids:
            return self.action_disconnect_from(target_section_id)
        else:
            return self.action_connect_to(target_section_id)

    def get_flow_layout_data(self):
        """
        Obtener datos de layout para el flujo visual.

        Returns:
            dict con informacion de posicionamiento y conexiones
        """
        self.ensure_one()
        return {
            'id': self.id,
            'name': self.name,
            'section_type': self.section_type,
            'sequence': self.sequence,
            'active': self.active,
            'show_in_flow': self.show_in_flow,
            'flow_row': self.flow_row,
            'flow_column': self.flow_column,
            'flow_position': self.flow_position,
            'connected_to': self.connected_to_ids.ids,
            'connected_from': self.connected_from_ids.ids,
            'depends_on': self.depends_on_sections.ids,
            'dependents': self.dependent_sections.ids,
            'rule_count': self.rule_count,
            'icon': self.icon,
            'color': self.color,
        }

    @api.model
    def get_structure_flow_layout(self, structure_id):
        """
        Obtener layout completo del flujo para una estructura.

        Args:
            structure_id: ID de la estructura salarial

        Returns:
            dict con secciones, conexiones y layout
        """
        sections = self.search([
            ('structure_id', '=', structure_id),
            ('show_in_flow', '=', True),
        ], order='sequence')

        nodes = []
        connections = []

        for section in sections:
            nodes.append(section.get_flow_layout_data())

            # Agregar conexiones manuales
            for target in section.connected_to_ids:
                connections.append({
                    'from': section.id,
                    'to': target.id,
                    'type': 'manual',
                    'from_type': section.section_type,
                })

            # Agregar conexiones de dependencia
            for dep in section.depends_on_sections:
                connections.append({
                    'from': dep.id,
                    'to': section.id,
                    'type': 'dependency',
                    'from_type': dep.section_type,
                })

        # Organizar en filas si no hay posicionamiento manual
        rows = self._organize_nodes_in_rows(nodes)

        return {
            'nodes': nodes,
            'connections': connections,
            'rows': rows,
            'structure_id': structure_id,
        }

    def _organize_nodes_in_rows(self, nodes):
        """
        Organizar nodos en filas basado en tipo o posicion manual.
        """
        # Separar nodos con posicion manual vs automatica
        manual_nodes = [n for n in nodes if n['flow_row'] > 0]
        auto_nodes = [n for n in nodes if n['flow_row'] == 0]

        # Ordenar auto_nodes por tipo
        type_order = {
            'devengos': 1,
            'deducciones': 2,
            'ibd_ss': 2,
            'totaldev': 3,
            'totalded': 3,
            'net': 4,
            'provisiones': 5,
        }

        auto_nodes.sort(key=lambda n: (type_order.get(n['section_type'], 99), n['sequence']))

        # Agrupar por tipo similar
        rows = []
        current_row = []
        last_order = 0

        for node in auto_nodes:
            node_order = type_order.get(node['section_type'], 99)
            if current_row and node_order != last_order:
                rows.append(current_row)
                current_row = []
            current_row.append(node)
            last_order = node_order

        if current_row:
            rows.append(current_row)

        # Insertar nodos manuales en sus filas especificadas
        for node in manual_nodes:
            row_idx = node['flow_row'] - 1
            while len(rows) <= row_idx:
                rows.append([])
            # Insertar en posicion de columna
            col_idx = node['flow_column'] - 1 if node['flow_column'] > 0 else len(rows[row_idx])
            if col_idx >= len(rows[row_idx]):
                rows[row_idx].append(node)
            else:
                rows[row_idx].insert(col_idx, node)

        return rows

    def action_auto_connect_by_type(self):
        """
        Auto-conectar secciones basado en el flujo tipico de nomina.
        """
        self.ensure_one()
        FLOW_ORDER = {
            'devengos': ['totaldev'],
            'deducciones': ['totalded'],
            'ibd_ss': ['totaldev', 'totalded'],
            'totaldev': ['net'],
            'totalded': ['net'],
            'net': ['provisiones'],
        }

        target_types = FLOW_ORDER.get(self.section_type, [])
        if not target_types:
            return False

        targets = self.structure_id.section_ids.filtered(
            lambda s: s.section_type in target_types and s.active and s.id != self.id
        )
        if targets:
            self.write({'connected_to_ids': [(6, 0, targets.ids)]})
            return True
        return False

    def action_clear_connections(self):
        """Limpiar todas las conexiones de esta seccion."""
        self.ensure_one()
        self.write({'connected_to_ids': [(5, 0, 0)]})
        return True

    # =========================================================================
    # METODOS DE VALIDACION DE CONDICIONES
    # =========================================================================
    def should_apply(self, payslip):
        """
        Verificar si esta seccion debe aplicarse a una nomina especifica.

        Args:
            payslip: hr.payslip record

        Returns:
            bool: True si la seccion debe aplicarse
        """
        self.ensure_one()

        if not self.active:
            return False

        employee = payslip.employee_id
        contract = payslip.contract_id

        # Verificar condiciones de liquidacion
        is_termination = getattr(payslip, 'is_termination', False) or \
                         payslip.struct_id.name and 'liquidacion' in payslip.struct_id.name.lower()

        if self.skip_on_termination and is_termination:
            return False

        if self.only_on_termination and not is_termination:
            return False

        # Verificar dias minimos trabajados
        if self.min_days_worked > 0:
            worked_days = sum(payslip.worked_days_line_ids.mapped('number_of_days'))
            if worked_days < self.min_days_worked:
                return False

        # Verificar ausencia total
        if self.skip_on_leave:
            total_days = (payslip.date_to - payslip.date_from).days + 1
            leave_days = sum(
                payslip.worked_days_line_ids.filtered(
                    lambda w: w.work_entry_type_id.is_leave
                ).mapped('number_of_days')
            )
            if leave_days >= total_days:
                return False

        # Evaluar segun tipo de condicion
        if self.apply_condition == 'always':
            return True

        elif self.apply_condition == 'python':
            return self._evaluate_python_condition(payslip)

        elif self.apply_condition == 'domain':
            return self._evaluate_domain_condition(employee)

        return True

    def check_dependencies_satisfied(self, executed_sections=None, skipped_sections=None):
        """
        Verificar si las dependencias de esta seccion fueron satisfechas.

        Args:
            executed_sections: set/list de IDs de secciones ejecutadas
            skipped_sections: set/list de IDs de secciones omitidas

        Returns:
            tuple: (satisfied: bool, reason: str)
        """
        self.ensure_one()

        if not self.depends_on_sections:
            return (True, '')

        executed_sections = set(executed_sections or [])
        skipped_sections = set(skipped_sections or [])

        for dep in self.depends_on_sections:
            # Verificar si la dependencia fue ejecutada
            if dep.id not in executed_sections:
                # Verificar si fue omitida
                if dep.id in skipped_sections:
                    if self.skip_if_dependency_skipped:
                        return (False, f'Dependencia "{dep.name}" fue omitida')
                else:
                    # Aun no se ha procesado - debe ejecutarse primero
                    return (False, f'Dependencia "{dep.name}" aun no procesada')

        return (True, '')

    def should_apply_with_dependencies(self, payslip, executed_sections=None, skipped_sections=None):
        """
        Verificar si esta seccion debe aplicarse, incluyendo verificacion de dependencias.

        Args:
            payslip: hr.payslip record
            executed_sections: set de IDs de secciones ya ejecutadas
            skipped_sections: set de IDs de secciones omitidas

        Returns:
            tuple: (should_apply: bool, reason: str)
        """
        self.ensure_one()

        # Primero verificar condiciones normales
        if not self.should_apply(payslip):
            return (False, 'Condiciones de la seccion no cumplidas')

        # Luego verificar dependencias
        deps_ok, reason = self.check_dependencies_satisfied(
            executed_sections, skipped_sections
        )
        if not deps_ok:
            return (False, reason)

        return (True, '')

    def _evaluate_python_condition(self, payslip):
        """Evaluar condicion Python"""
        self.ensure_one()

        if not self.python_condition:
            return True

        try:
            localdict = {
                'employee': payslip.employee_id,
                'contract': payslip.contract_id,
                'payslip': payslip,
                'date_from': payslip.date_from,
                'date_to': payslip.date_to,
                'company': payslip.company_id,
                'env': self.env,
            }
            result = eval(self.python_condition, localdict)
            return bool(result)
        except Exception as e:
            _logger.warning(
                "Error evaluando condicion Python en seccion %s: %s",
                self.name, str(e)
            )
            return True  # Por defecto aplicar si hay error

    def _evaluate_domain_condition(self, employee):
        """Evaluar condicion de dominio de empleado"""
        self.ensure_one()

        try:
            # Verificar filtro de inclusion
            if self.employee_domain and self.employee_domain != '[]':
                domain = eval(self.employee_domain)
                domain.append(('id', '=', employee.id))
                if not self.env['hr.employee'].search_count(domain):
                    return False

            # Verificar filtro de exclusion
            if self.exclude_employee_domain and self.exclude_employee_domain != '[]':
                exclude_domain = eval(self.exclude_employee_domain)
                exclude_domain.append(('id', '=', employee.id))
                if self.env['hr.employee'].search_count(exclude_domain):
                    return False

            return True
        except Exception as e:
            _logger.warning(
                "Error evaluando dominio en seccion %s: %s",
                self.name, str(e)
            )
            return True

    def filter_employees_for_generation(self, employees):
        """
        Filtrar empleados para generacion de nomina segun condiciones.

        Args:
            employees: recordset de hr.employee

        Returns:
            recordset de hr.employee que aplican para esta seccion
        """
        self.ensure_one()

        if not self.active:
            return self.env['hr.employee']

        if self.apply_condition == 'always':
            return employees

        if self.apply_condition != 'domain':
            return employees

        try:
            result = employees

            # Aplicar filtro de inclusion
            if self.employee_domain and self.employee_domain != '[]':
                domain = eval(self.employee_domain)
                result = result.filtered_domain(domain)

            # Aplicar filtro de exclusion
            if self.exclude_employee_domain and self.exclude_employee_domain != '[]':
                exclude_domain = eval(self.exclude_employee_domain)
                excluded = result.filtered_domain(exclude_domain)
                result = result - excluded

            return result
        except Exception as e:
            _logger.warning(
                "Error filtrando empleados en seccion %s: %s",
                self.name, str(e)
            )
            return employees

    # =========================================================================
    # METODOS DE CATEGORIAS Y MATCHING
    # =========================================================================
    def _get_section_categories(self):
        """Obtener lista de categorias para esta seccion"""
        self.ensure_one()
        if self.category_codes:
            return [c.strip().upper() for c in self.category_codes.split(',')]
        return SECTION_CATEGORY_MAP.get(self.section_type, [])

    def _rule_matches_section(self, rule, categories=None):
        """
        Verificar si una regla pertenece a esta seccion.
        
        Args:
            rule: hr.salary.rule record
            categories: lista de codigos de categoria (opcional, se calcula si no se proporciona)
        
        Returns:
            bool: True si la regla pertenece a esta seccion
        """
        self.ensure_one()

        # Obtener categorias si no se proporcionan
        if categories is None:
            categories = self._get_section_categories()

        # Normalizar categorias a uppercase para comparacion
        categories_upper = [c.upper() if isinstance(c, str) else c for c in categories]

        # Verificar exclusiones primero
        if self.exclude_codes:
            exclude_list = [c.strip().upper() for c in self.exclude_codes.split(',')]
            rule_code_upper = (rule.code or '').upper()
            if rule_code_upper in exclude_list:
                return False

        # Verificar por codigo de regla
        rule_code_upper = (rule.code or '').upper()
        if rule_code_upper and rule_code_upper in categories_upper:
            return True

        # Verificar por codigo de categoria
        if rule.category_id:
            category_code = (rule.category_id.code or '').upper()
            if category_code and category_code in categories_upper:
                return True
            
            # Verificar categoria padre
            if rule.category_id.parent_id:
                parent_code = (rule.category_id.parent_id.code or '').upper()
                if parent_code and parent_code in categories_upper:
                    return True

        return False

    # =========================================================================
    # METODOS DE EJECUCION
    # =========================================================================
    def get_rules_sorted(self):
        """
        Obtener reglas de la seccion ordenadas por sequence.

        Returns:
            recordset de hr.salary.rule ordenado
        """
        self.ensure_one()
        return self.rule_ids.sorted('sequence')

    def get_rules_for_execution(self, payslip=None):
        """
        Obtener reglas listas para ejecutar en una nomina.

        Args:
            payslip: hr.payslip opcional para filtrar reglas aplicables

        Returns:
            recordset de hr.salary.rule
        """
        self.ensure_one()
        rules = self.get_rules_sorted()

        if payslip:
            # Filtrar reglas que aplican a este payslip
            applicable_rules = self.env['hr.salary.rule']
            for rule in rules:
                if rule._satisfy_condition(payslip):
                    applicable_rules |= rule
            return applicable_rules

        return rules

    def execute_section(self, payslip, localdict):
        """
        Ejecutar todas las reglas de esta seccion.

        Args:
            payslip: hr.payslip record
            localdict: diccionario local para evaluacion

        Returns:
            dict con resultados: {rule_code: amount, ...}
        """
        self.ensure_one()
        results = {}

        if not self.active:
            return results

        rules = self.get_rules_for_execution(payslip)
        for rule in rules:
            try:
                amount, qty, rate = rule._compute_rule(localdict)
                results[rule.code] = {
                    'amount': amount,
                    'quantity': qty,
                    'rate': rate,
                    'total': amount * qty * rate / 100,
                    'rule': rule,
                }
            except Exception as e:
                _logger.error(
                    "Error ejecutando regla %s en seccion %s: %s",
                    rule.code, self.name, str(e)
                )
                results[rule.code] = {
                    'amount': 0,
                    'quantity': 0,
                    'rate': 0,
                    'total': 0,
                    'rule': rule,
                    'error': str(e),
                }

        return results

    def get_section_total(self, payslip_lines):
        """
        Calcular total de lineas de nomina para esta seccion.

        Args:
            payslip_lines: recordset de hr.payslip.line

        Returns:
            float: suma de totales
        """
        self.ensure_one()
        rule_ids = self.rule_ids.ids
        section_lines = payslip_lines.filtered(
            lambda l: l.salary_rule_id.id in rule_ids
        )
        return sum(section_lines.mapped('total'))

    # =========================================================================
    # METODOS DE CONTABILIZACION
    # =========================================================================
    def get_account_for_rule(self, employee, salary_rule, account_type='debit'):
        """
        Obtener cuenta contable para una regla en esta seccion.

        Args:
            employee: hr.employee record
            salary_rule: hr.salary.rule record
            account_type: 'debit' o 'credit'

        Returns:
            account.account record o False
        """
        self.ensure_one()

        # Si tiene configuracion contable avanzada, usarla
        if self.accounting_config_id:
            return self.accounting_config_id.find_account(
                employee, salary_rule, account_type
            )

        # Buscar en configuracion de la regla
        if self.use_direct_accounts:
            account = self._find_rule_account(employee, salary_rule, account_type)
            if account:
                return account

        # Usar cuenta por defecto de la seccion
        if account_type == 'debit' and self.debit_account_id:
            return self.debit_account_id
        elif account_type == 'credit' and self.credit_account_id:
            return self.credit_account_id

        # Fallback a cuenta de la regla
        if account_type == 'debit':
            return salary_rule.account_debit
        return salary_rule.account_credit

    def _find_rule_account(self, employee, salary_rule, account_type):
        """Buscar cuenta en configuracion de la regla"""
        if not hasattr(salary_rule, 'salary_rule_accounting'):
            return False

        for account_rule in salary_rule.salary_rule_accounting:
            # Validar ubicacion de trabajo
            if account_rule.work_location:
                if account_rule.work_location.id != employee.address_id.id:
                    continue

            # Validar compania
            if account_rule.company:
                if account_rule.company.id != employee.company_id.id:
                    continue

            # Validar departamento (con jerarquia)
            if account_rule.department:
                dept = employee.department_id
                dept_match = False
                levels = 3
                while dept and levels > 0:
                    if account_rule.department.id == dept.id:
                        dept_match = True
                        break
                    dept = dept.parent_id
                    levels -= 1

                if not dept_match:
                    continue

            # Retornar cuenta
            if account_type == 'debit' and account_rule.debit_account:
                return account_rule.debit_account
            elif account_type == 'credit' and account_rule.credit_account:
                return account_rule.credit_account

        return False

    def prepare_move_lines(self, payslip, payslip_lines):
        """
        Preparar lineas de asiento contable para esta seccion.

        Args:
            payslip: hr.payslip record
            payslip_lines: lineas de nomina de esta seccion

        Returns:
            list de dict con datos para account.move.line
        """
        self.ensure_one()
        move_lines = []
        employee = payslip.employee_id

        for line in payslip_lines:
            if not line.total:
                continue

            rule = line.salary_rule_id
            debit_account = self.get_account_for_rule(employee, rule, 'debit')
            credit_account = self.get_account_for_rule(employee, rule, 'credit')

            if line.total > 0:
                if debit_account:
                    move_lines.append({
                        'name': line.name,
                        'account_id': debit_account.id,
                        'debit': abs(line.total),
                        'credit': 0,
                        'partner_id': employee.work_contact_id.id if employee.work_contact_id else False,
                    })
                if credit_account:
                    move_lines.append({
                        'name': line.name,
                        'account_id': credit_account.id,
                        'debit': 0,
                        'credit': abs(line.total),
                        'partner_id': employee.work_contact_id.id if employee.work_contact_id else False,
                    })
            else:
                # Monto negativo - invertir debito/credito
                if credit_account:
                    move_lines.append({
                        'name': line.name,
                        'account_id': credit_account.id,
                        'debit': abs(line.total),
                        'credit': 0,
                        'partner_id': employee.work_contact_id.id if employee.work_contact_id else False,
                    })
                if debit_account:
                    move_lines.append({
                        'name': line.name,
                        'account_id': debit_account.id,
                        'debit': 0,
                        'credit': abs(line.total),
                        'partner_id': employee.work_contact_id.id if employee.work_contact_id else False,
                    })

        return move_lines

    # =========================================================================
    # CONSTRAINS Y VALIDACIONES
    # =========================================================================
    @api.constrains('structure_id', 'section_type')
    def _check_unique_section_type(self):
        """Solo puede haber una seccion de cada tipo por estructura"""
        for section in self:
            existing = self.search([
                ('id', '!=', section.id),
                ('structure_id', '=', section.structure_id.id),
                ('section_type', '=', section.section_type)
            ])
            if existing:
                raise ValidationError(
                    _('Ya existe una seccion de tipo "%s" en esta estructura')
                    % SECTION_TYPE_DICT.get(section.section_type)
                )

    # =========================================================================
    # ONCHANGE
    # =========================================================================
    @api.onchange('section_type')
    def _onchange_section_type(self):
        """Establecer valores por defecto segun tipo de seccion"""
        if self.section_type:
            self.sequence = SECTION_DEFAULT_SEQUENCE.get(self.section_type, 50)
            self.color = SECTION_COLORS.get(self.section_type, 0)
            if not self.name:
                self.name = SECTION_TYPE_DICT.get(
                    self.section_type, ''
                ).split(' - ')[-1]

    # =========================================================================
    # ACCIONES
    # =========================================================================
    def action_view_rules(self):
        """Abrir vista de reglas de esta seccion"""
        self.ensure_one()
        return {
            'name': _('Reglas de %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'hr.salary.rule',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.rule_ids.ids)],
            'context': {'default_struct_id': self.structure_id.id},
        }

    def action_refresh_rules(self):
        """Refrescar reglas computadas"""
        self._compute_rule_ids()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Reglas Actualizadas'),
                'message': _('%d reglas en seccion %s') % (
                    self.rule_count, self.name
                ),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_view_payslip_lines(self):
        """Ver lineas de nomina de esta seccion"""
        self.ensure_one()
        return {
            'name': _('Lineas de Nomina - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payslip.line',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.payslip_line_ids.ids)],
            'context': {'search_default_group_employee': 1},
        }

    def action_view_payslips(self):
        """Ver nominas que usan esta seccion"""
        self.ensure_one()
        payslip_ids = self.payslip_line_ids.mapped('slip_id').ids
        return {
            'name': _('Nominas - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payslip',
            'view_mode': 'list,form',
            'domain': [('id', 'in', payslip_ids)],
        }

    # =========================================================================
    # METODOS API PARA VISUALIZACION DE FLUJO
    # =========================================================================
    @api.model
    def get_flow_data(self, structure_id):
        """
        Obtener datos para renderizar el flujo visual de secciones.

        Args:
            structure_id: ID de la estructura salarial

        Returns:
            dict con nodos (sections) y conexiones (edges)
        """
        structure = self.env['hr.payroll.structure'].browse(structure_id)
        if not structure.exists():
            return {'nodes': [], 'edges': []}

        sections = structure.section_ids.filtered('active').sorted('sequence')
        nodes = []
        edges = []

        for section in sections:
            nodes.append({
                'id': section.id,
                'name': section.name,
                'type': section.section_type,
                'type_label': section.section_type_label,
                'icon': section.icon,
                'color': section.color,
                'sequence': section.sequence,
                'rule_count': section.rule_count,
                'total_amount': section.total_amount,
                'last_month_total': section.last_month_total,
                'payslip_count': section.payslip_count,
                'is_total': section.is_total_section,
                'is_calculation': section.is_calculation_section,
                'position': section.flow_position,
            })

            # Crear conexiones
            for next_section in section.next_section_ids:
                edges.append({
                    'from': section.id,
                    'to': next_section.id,
                    'from_type': section.section_type,
                    'to_type': next_section.section_type,
                })

        return {
            'structure_id': structure_id,
            'structure_name': structure.name,
            'nodes': nodes,
            'edges': edges,
        }

    def get_section_summary(self):
        """Obtener resumen de la seccion para mostrar en cards"""
        self.ensure_one()
        return {
            'id': self.id,
            'name': self.name,
            'type': self.section_type,
            'type_label': self.section_type_label,
            'icon': self.icon,
            'color': self.color,
            'rule_count': self.rule_count,
            'total_amount': self.total_amount,
            'last_month_total': self.last_month_total,
            'payslip_count': self.payslip_count,
            'currency_symbol': self.currency_id.symbol or '$',
            'variation': self._get_variation_percentage(),
        }

    def _get_variation_percentage(self):
        """Calcular variacion porcentual respecto al mes anterior"""
        self.ensure_one()
        if not self.last_month_total:
            return 0
        return ((self.total_amount - self.last_month_total) / self.last_month_total) * 100


class HrPayrollStructure(models.Model):
    """Extension de Estructura Salarial para soportar secciones"""
    _inherit = 'hr.payroll.structure'

    # =========================================================================
    # CAMPOS DE SECCIONES
    # =========================================================================
    section_ids = fields.One2many(
        'hr.payroll.structure.section',
        'structure_id',
        string='Secciones',
        help='Secciones que organizan las reglas salariales'
    )

    use_sections = fields.Boolean(
        string='Usar Secciones',
        default=False,
        help='Organizar reglas en secciones con configuracion independiente'
    )

    section_count = fields.Integer(
        string='Cantidad de Secciones',
        compute='_compute_section_count'
    )

    has_all_sections = fields.Boolean(
        string='Tiene Todas las Secciones',
        compute='_compute_has_all_sections'
    )

    section_logic_valid = fields.Boolean(
        string='Logica de Secciones Valida',
        compute='_compute_section_logic_valid',
        help='Indica si la logica de secciones esta correctamente configurada'
    )

    # =========================================================================
    # METODOS COMPUTADOS
    # =========================================================================
    def _compute_section_count(self):
        for record in self:
            record.section_count = len(record.section_ids.filtered('active'))

    def _compute_has_all_sections(self):
        all_types = set(dict(SECTION_TYPES).keys())
        for record in self:
            existing_types = set(record.section_ids.filtered('active').mapped('section_type'))
            record.has_all_sections = all_types == existing_types

    def _compute_section_logic_valid(self):
        """Validar que la logica de secciones sea correcta"""
        for record in self:
            if not record.use_sections:
                record.section_logic_valid = True
                continue

            # Validacion rapida sin lanzar excepciones para evitar costo en cada calculo
            # La validacion completa se hace en action_validate_sections()
            sections = record.section_ids.filtered('active')
            if not sections:
                record.section_logic_valid = True
                continue

            # Validacion basica: verificar que no haya secciones con sequence igual
            sequences = sections.mapped('sequence')
            if len(sequences) != len(set(sequences)):
                record.section_logic_valid = False
                continue

            # Validacion basica: verificar que las dependencias existan
            all_section_ids = set(sections.ids)
            for section in sections:
                dep_ids = set(section.depends_on_sections.ids)
                if dep_ids and not dep_ids.issubset(all_section_ids):
                    record.section_logic_valid = False
                    break
            else:
                record.section_logic_valid = True

    # =========================================================================
    # ACCIONES
    # =========================================================================
    def action_create_default_sections(self):
        """Crear secciones por defecto para esta estructura"""
        self.ensure_one()

        if not self.use_sections:
            raise UserError(_('Debe activar "Usar Secciones" primero'))

        Section = self.env['hr.payroll.structure.section']
        existing_types = self.section_ids.mapped('section_type')

        created = 0
        for section_type, label in SECTION_TYPES:
            if section_type not in existing_types:
                Section.create({
                    'structure_id': self.id,
                    'section_type': section_type,
                    'name': label.split(' - ')[-1],
                    'sequence': SECTION_DEFAULT_SEQUENCE.get(section_type, 50),
                    'color': SECTION_COLORS.get(section_type, 0),
                    'active': True,
                })
                created += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Secciones Creadas'),
                'message': _('Se crearon %d secciones por defecto') % created,
                'type': 'success',
                'sticky': False,
            }
        }

    # =========================================================================
    # METODOS DE ACCESO A SECCIONES
    # =========================================================================
    def get_section(self, section_type):
        """
        Obtener seccion por tipo.

        Args:
            section_type: str ('devengos', 'deducciones', etc.)

        Returns:
            hr.payroll.structure.section record o False
        """
        self.ensure_one()
        return self.section_ids.filtered(
            lambda s: s.section_type == section_type and s.active
        )[:1]

    def get_section_for_rule(self, salary_rule):
        """
        Obtener la seccion correspondiente a una regla salarial.

        Args:
            salary_rule: hr.salary.rule record

        Returns:
            hr.payroll.structure.section record o False
        """
        self.ensure_one()

        if not self.use_sections:
            return False

        for section in self.section_ids.filtered('active').sorted('sequence'):
            if salary_rule in section.rule_ids:
                return section

        return False

    def get_sections_ordered(self):
        """
        Obtener secciones activas ordenadas por sequence.
        NOTA: Para respetar dependencias, usar get_sections_execution_order() en su lugar.

        Returns:
            recordset de hr.payroll.structure.section
        """
        self.ensure_one()
        return self.section_ids.filtered('active').sorted('sequence')

    def get_rules_by_section(self):
        """
        Obtener reglas organizadas por seccion respetando orden de ejecucion.

        Returns:
            dict: {section: rule_recordset, ...}
        """
        self.ensure_one()

        result = {}
        processed_rules = self.env['hr.salary.rule']

        if self.use_sections:
            # Usar orden de ejecucion que respeta dependencias
            for section in self.get_sections_execution_order():
                section_rules = section.get_rules_sorted()
                result[section] = section_rules
                processed_rules |= section_rules

        # Reglas sin seccion
        remaining = self.rule_ids - processed_rules
        if remaining:
            result[False] = remaining.sorted('sequence')

        return result

    def get_execution_order(self):
        """
        Obtener orden de ejecucion de reglas considerando secciones.

        Returns:
            list de hr.salary.rule ordenados
        """
        self.ensure_one()

        if not self.use_sections:
            return self.rule_ids.sorted('sequence')

        # Obtener secciones ordenadas respetando dependencias
        sections_ordered = self.get_sections_execution_order()
        
        ordered_rules = self.env['hr.salary.rule']
        for section in sections_ordered:
            ordered_rules |= section.get_rules_sorted()

        # Agregar reglas sin seccion al final
        remaining = self.rule_ids - ordered_rules
        if remaining:
            ordered_rules |= remaining.sorted('sequence')

        return ordered_rules

    def get_sections_execution_order(self):
        """
        Obtener secciones ordenadas respetando dependencias.
        Usa orden topologico para garantizar que las dependencias se ejecuten primero.

        Returns:
            recordset de hr.payroll.structure.section ordenado
        """
        self.ensure_one()

        if not self.use_sections:
            return self.env['hr.payroll.structure.section']

        sections = self.section_ids.filtered('active')
        if not sections:
            return self.env['hr.payroll.structure.section']

        # Orden topologico usando Kahn's algorithm
        # Construir grafo de dependencias
        in_degree = {s.id: 0 for s in sections}
        graph = {s.id: [] for s in sections}

        for section in sections:
            for dep in section.depends_on_sections:
                if dep.id in graph:
                    graph[dep.id].append(section.id)
                    in_degree[section.id] += 1

        # Cola de secciones sin dependencias pendientes
        queue = [s.id for s in sections if in_degree[s.id] == 0]
        # Si no hay ninguna sin dependencias, ordenar por sequence
        if not queue:
            return sections.sorted('sequence')

        result = []
        while queue:
            # Ordenar por sequence para mantener consistencia
            queue.sort(key=lambda sid: self.env['hr.payroll.structure.section'].browse(sid).sequence)
            current_id = queue.pop(0)
            result.append(current_id)

            # Reducir grado de dependientes
            for dependent_id in graph[current_id]:
                in_degree[dependent_id] -= 1
                if in_degree[dependent_id] == 0:
                    queue.append(dependent_id)

        # Si hay secciones que no se procesaron (ciclos), agregarlas al final
        remaining = [s.id for s in sections if s.id not in result]
        if remaining:
            remaining_sections = self.env['hr.payroll.structure.section'].browse(remaining)
            result.extend(remaining_sections.sorted('sequence').ids)

        return self.env['hr.payroll.structure.section'].browse(result)

    # =========================================================================
    # METODOS DE TOTALES
    # =========================================================================
    def get_section_totals(self, payslip_lines):
        """
        Obtener totales por seccion.

        Args:
            payslip_lines: recordset de hr.payslip.line

        Returns:
            dict: {section_type: total, ...}
        """
        self.ensure_one()

        totals = {}
        for section in self.section_ids.filtered('active'):
            totals[section.section_type] = section.get_section_total(payslip_lines)

        return totals

    def _validate_section_logic(self):
        """
        Validar la logica de secciones de forma completa:
        - No debe haber dependencias circulares
        - Todas las dependencias deben existir y estar activas
        - El orden de ejecucion debe ser consistente
        
        Este metodo es costoso y debe usarse solo cuando sea necesario (validacion manual).
        Para validacion rapida en tiempo real, usar _compute_section_logic_valid().
        """
        self.ensure_one()

        if not self.use_sections:
            return True

        sections = self.section_ids.filtered('active')
        if not sections:
            return True

        all_section_ids = set(sections.ids)
        section_by_id = {s.id: s for s in sections}

        # Validar que todas las dependencias existan y esten activas
        for section in sections:
            for dep in section.depends_on_sections:
                if dep.structure_id != self:
                    raise ValidationError(
                        _('La seccion "%s" depende de "%s" que pertenece a otra estructura')
                        % (section.name, dep.name)
                    )
                if not dep.active:
                    raise ValidationError(
                        _('La seccion "%s" depende de "%s" que esta inactiva')
                        % (section.name, dep.name)
                    )
                if dep.id not in all_section_ids:
                    raise ValidationError(
                        _('La seccion "%s" depende de "%s" que no existe')
                        % (section.name, dep.name)
                    )

        # Verificar dependencias circulares usando DFS
        visited = set()
        rec_stack = set()

        def has_cycle(section_id):
            if section_id in rec_stack:
                cycle_path = list(rec_stack) + [section_id]
                cycle_names = [section_by_id[sid].name for sid in cycle_path if sid in section_by_id]
                raise ValidationError(
                    _('Dependencia circular detectada: %s') % ' -> '.join(cycle_names)
                )
            if section_id in visited:
                return False

            visited.add(section_id)
            rec_stack.add(section_id)

            section = section_by_id.get(section_id)
            if section:
                for dep in section.depends_on_sections:
                    if dep.id in all_section_ids:
                        has_cycle(dep.id)

            rec_stack.remove(section_id)
            return False

        # Verificar ciclos empezando desde cada seccion
        for section in sections:
            if section.id not in visited:
                has_cycle(section.id)

        # Validar orden de ejecucion: las dependencias deben tener sequence menor
        for section in sections:
            for dep in section.depends_on_sections:
                if dep.sequence >= section.sequence:
                    raise ValidationError(
                        _('Orden de ejecucion incorrecto: La seccion "%s" (seq: %d) '
                          'depende de "%s" (seq: %d). Las dependencias deben ejecutarse primero.')
                        % (section.name, section.sequence, dep.name, dep.sequence)
                    )

        return True

    def action_validate_sections(self):
        """Accion para validar la logica de secciones"""
        self.ensure_one()
        try:
            self._validate_section_logic()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Validacion Exitosa'),
                    'message': _('La logica de secciones es correcta'),
                    'type': 'success',
                    'sticky': False,
                }
            }
        except (UserError, ValidationError) as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error de Validacion'),
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }
