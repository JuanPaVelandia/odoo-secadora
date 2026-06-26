# -*- coding: utf-8 -*-
"""
MIXIN PARA VISUALIZACIÓN DE FLUJO EN HR.PAYSLIP
===============================================

Agrega campos y métodos para almacenar y renderizar
la visualización del flujo de cálculo de nómina.

Autor: SDT Ingeniería
Versión: 1.0
"""

from odoo import models, fields, api
import json
import base64
import logging

_logger = logging.getLogger(__name__)


class HrPayslipFlowMixin(models.AbstractModel):
    """
    Mixin para agregar funcionalidad de visualización de flujo a hr.payslip.

    Campos agregados:
    - flow_data: Binario con datos JSON del flujo
    - flow_html: HTML renderizado del flujo
    - flow_summary_json: Resumen en JSON

    Métodos:
    - generate_flow_visualization(): Genera la visualización
    - get_flow_data(): Obtiene datos del flujo
    - get_flow_html(): Obtiene HTML del flujo
    """

    _name = 'hr.payslip.flow.mixin'
    _description = 'Mixin para visualización de flujo de nómina'

    # ═══════════════════════════════════════════════════════════════════════════
    # CAMPOS
    # ═══════════════════════════════════════════════════════════════════════════

    flow_data = fields.Binary(
        string='Datos del Flujo',
        help='Datos JSON del flujo de cálculo almacenados en binario',
        attachment=False,
    )

    flow_html = fields.Html(
        string='Visualización del Flujo',
        compute='_compute_flow_html',
        sanitize=False,
        help='Visualización HTML del flujo de cálculo',
    )

    flow_summary = fields.Text(
        string='Resumen del Flujo',
        compute='_compute_flow_summary',
        help='Resumen JSON del flujo',
    )

    flow_type_display = fields.Char(
        string='Tipo de Flujo',
        compute='_compute_flow_type_display',
    )

    # Campos de resumen para vistas
    flow_total_devengos = fields.Float(
        string='Total Devengos',
        compute='_compute_flow_totals',
        digits=(16, 2),
    )

    flow_total_deducciones = fields.Float(
        string='Total Deducciones',
        compute='_compute_flow_totals',
        digits=(16, 2),
    )

    flow_neto = fields.Float(
        string='Neto Calculado',
        compute='_compute_flow_totals',
        digits=(16, 2),
    )

    # ═══════════════════════════════════════════════════════════════════════════
    # COMPUTED FIELDS
    # ═══════════════════════════════════════════════════════════════════════════

    @api.depends('flow_data')
    def _compute_flow_html(self):
        """Genera HTML desde los datos del flujo."""
        for record in self:
            if record.flow_data:
                try:
                    flow_dict = record.get_flow_data()
                    if flow_dict:
                        record.flow_html = record._render_flow_html(flow_dict)
                    else:
                        record.flow_html = '<p>Sin datos de flujo</p>'
                except Exception as e:
                    _logger.error(f"Error rendering flow HTML: {e}")
                    record.flow_html = f'<p>Error: {e}</p>'
            else:
                record.flow_html = '<p>Flujo no generado</p>'

    @api.depends('flow_data')
    def _compute_flow_summary(self):
        """Extrae resumen del flujo."""
        for record in self:
            if record.flow_data:
                try:
                    flow_dict = record.get_flow_data()
                    if flow_dict and 'summary' in flow_dict:
                        record.flow_summary = json.dumps(flow_dict['summary'], indent=2)
                    else:
                        record.flow_summary = '{}'
                except Exception as e:
                    _logger.warning("Error extrayendo resumen del flujo para %s: %s", record, e)
                    record.flow_summary = '{}'
            else:
                record.flow_summary = '{}'

    @api.depends('flow_data')
    def _compute_flow_type_display(self):
        """Muestra tipo de flujo."""
        for record in self:
            if record.flow_data:
                try:
                    flow_dict = record.get_flow_data()
                    if flow_dict and 'summary' in flow_dict:
                        record.flow_type_display = flow_dict['summary'].get('flow_label', '')
                    else:
                        record.flow_type_display = ''
                except Exception:  # noqa: BLE001 – campo de visualización, fallo no crítico
                    _logger.warning("Error calculando tipo de flujo para %s", record, exc_info=True)
                    record.flow_type_display = ''
            else:
                record.flow_type_display = ''

    @api.depends('flow_data')
    def _compute_flow_totals(self):
        """Calcula totales desde el flujo."""
        for record in self:
            if record.flow_data:
                try:
                    flow_dict = record.get_flow_data()
                    if flow_dict and 'summary' in flow_dict:
                        summary = flow_dict['summary']
                        record.flow_total_devengos = summary.get('total_devengos', 0)
                        record.flow_total_deducciones = summary.get('total_deducciones', 0)
                        record.flow_neto = summary.get('neto', 0)
                    else:
                        record.flow_total_devengos = 0
                        record.flow_total_deducciones = 0
                        record.flow_neto = 0
                except Exception:  # noqa: BLE001 – totales de flujo para UI, fallo no crítico
                    _logger.warning("Error calculando totales del flujo para %s", record, exc_info=True)
                    record.flow_total_devengos = 0
                    record.flow_total_deducciones = 0
                    record.flow_neto = 0
            else:
                record.flow_total_devengos = 0
                record.flow_total_deducciones = 0
                record.flow_neto = 0

    # ═══════════════════════════════════════════════════════════════════════════
    # MÉTODOS PÚBLICOS
    # ═══════════════════════════════════════════════════════════════════════════

    def generate_flow_visualization(self, localdict=None):
        """
        Genera y almacena la visualización del flujo.

        Args:
            localdict: Diccionario de contexto (opcional, se construye si no se provee)

        Returns:
            dict: Datos del flujo generado
        """
        self.ensure_one()

        from .reglas.payroll_flow_visualization import PayrollFlowVisualization

        # Si no hay localdict, construir uno básico
        if not localdict:
            localdict = self._build_basic_localdict()

        # Generar visualización
        viz = PayrollFlowVisualization(self, localdict)
        flow_data = viz.generate()

        # Almacenar en binario
        json_str = json.dumps(flow_data, ensure_ascii=False)
        self.flow_data = base64.b64encode(json_str.encode('utf-8'))

        return flow_data

    def get_flow_data(self):
        """
        Obtiene los datos del flujo.

        Returns:
            dict: Datos del flujo o None
        """
        self.ensure_one()

        if not self.flow_data:
            return None

        try:
            json_str = base64.b64decode(self.flow_data).decode('utf-8')
            return json.loads(json_str)
        except Exception as e:
            _logger.error(f"Error decoding flow data: {e}")
            return None

    def get_flow_html(self, include_styles=True):
        """
        Obtiene HTML del flujo.

        Args:
            include_styles: Si incluir CSS inline

        Returns:
            str: HTML del flujo
        """
        self.ensure_one()

        flow_dict = self.get_flow_data()
        if not flow_dict:
            return '<p>Sin datos de flujo</p>'

        return self._render_flow_html(flow_dict, include_styles)

    def get_flow_svg(self, width=800, height=600):
        """
        Obtiene SVG del flujo.

        Args:
            width: Ancho del SVG
            height: Alto del SVG

        Returns:
            str: SVG del flujo
        """
        self.ensure_one()

        from .reglas.payroll_flow_visualization import PayrollFlowVisualization

        flow_dict = self.get_flow_data()
        if not flow_dict:
            return ''

        # Crear visualización temporal para generar SVG
        localdict = self._build_basic_localdict()
        viz = PayrollFlowVisualization(self, localdict)
        viz.phases = flow_dict.get('phases', [])
        viz.nodes = flow_dict.get('nodes', [])
        viz.edges = flow_dict.get('edges', [])
        viz.summary = flow_dict.get('summary', {})
        viz.metadata = flow_dict.get('metadata', {})

        return viz.to_svg(width, height)

    def get_flow_for_report(self):
        """
        Obtiene datos formateados para reportes.

        Returns:
            dict: Datos estructurados para reportes
        """
        self.ensure_one()

        flow_dict = self.get_flow_data()
        if not flow_dict:
            return {
                'has_flow': False,
                'html': '<p>Sin datos de flujo</p>',
            }

        # Agrupar nodos por fase para el reporte
        nodes_by_phase = {}
        for node in flow_dict.get('nodes', []):
            phase = node.get('phase', 'other')
            if phase not in nodes_by_phase:
                nodes_by_phase[phase] = []
            nodes_by_phase[phase].append(node)

        return {
            'has_flow': True,
            'html': self._render_flow_html(flow_dict, include_styles=True),
            'svg': self.get_flow_svg(),
            'metadata': flow_dict.get('metadata', {}),
            'summary': flow_dict.get('summary', {}),
            'phases': flow_dict.get('phases', []),
            'nodes_by_phase': nodes_by_phase,
            'total_devengos': flow_dict.get('summary', {}).get('total_devengos', 0),
            'total_deducciones': flow_dict.get('summary', {}).get('total_deducciones', 0),
            'neto': flow_dict.get('summary', {}).get('neto', 0),
        }

    # ═══════════════════════════════════════════════════════════════════════════
    # MÉTODOS PRIVADOS
    # ═══════════════════════════════════════════════════════════════════════════

    def _build_basic_localdict(self):
        """Construye un localdict básico desde el payslip."""
        self.ensure_one()

        localdict = {
            'slip': self,
            'payslip': self,
            'employee': self.employee_id,
            'contract': self.contract_id,
            'rules': {},
            'categories': {},
        }

        # Agregar reglas desde líneas de nómina
        for line in self.line_ids:
            if line.salary_rule_id:
                code = line.salary_rule_id.code
                localdict['rules'][code] = type('RuleData', (), {
                    'rule': line.salary_rule_id,
                    'total': line.total,
                    'quantity': line.quantity,
                    'amount': line.amount,
                    'rate': line.rate,
                })()

        return localdict

    def _render_flow_html(self, flow_dict, include_styles=True):
        """
        Renderiza HTML desde diccionario de flujo.

        Args:
            flow_dict: Diccionario con datos del flujo
            include_styles: Si incluir CSS inline

        Returns:
            str: HTML renderizado
        """
        html_parts = []

        if include_styles:
            html_parts.append(self._get_flow_css())

        summary = flow_dict.get('summary', {})
        metadata = flow_dict.get('metadata', {})
        phases = flow_dict.get('phases', [])
        nodes = flow_dict.get('nodes', [])

        # Colores por fase
        phase_colors = {
            'base': '#4CAF50',
            'novelties': '#2196F3',
            'ibd': '#9C27B0',
            'social_security': '#FF9800',
            'brtf': '#E91E63',
            'retention': '#F44336',
            'provisions': '#00BCD4',
            'prestaciones': '#8BC34A',
            'other_deductions': '#795548',
            'indemnizacion': '#FF5722',
            'net': '#4CAF50',
            'default': '#9E9E9E',
        }

        html_parts.append(f'''
        <div class="payroll-flow-container">
            <div class="flow-header">
                <h3>{summary.get('flow_label', 'Flujo de Nómina')}</h3>
                <div class="flow-meta">
                    <span class="employee">{metadata.get('employee_name', '')}</span>
                    <span class="period">{metadata.get('date_from', '')} - {metadata.get('date_to', '')}</span>
                </div>
            </div>

            <div class="flow-diagram">
        ''')

        # Generar fases
        for phase in phases:
            phase_name = phase.get('name', '')
            phase_nodes = [n for n in nodes if n.get('phase') == phase_name]

            if not phase_nodes and phase_name not in ['base', 'ibd', 'net']:
                continue

            color = phase_colors.get(phase_name, phase_colors['default'])

            html_parts.append(f'''
                <div class="flow-phase" style="border-left: 4px solid {color}">
                    <div class="phase-header">
                        <span class="phase-name">{phase.get('label', phase_name)}</span>
                        {'<span class="phase-badge">Cache</span>' if phase.get('cache_result') else ''}
                    </div>
                    <div class="phase-nodes">
            ''')

            for node in phase_nodes:
                value_class = 'negative' if node.get('is_deduction') else 'positive'
                icon = node.get('icon', '📄')
                html_parts.append(f'''
                        <div class="flow-node {value_class}">
                            <span class="node-icon">{icon}</span>
                            <span class="node-name">{node.get('short_name', node.get('code', ''))}</span>
                            <span class="node-value">${node.get('total', 0):,.2f}</span>
                        </div>
                ''')

            html_parts.append('''
                    </div>
                </div>
            ''')

        # Summary
        html_parts.append(f'''
            </div>

            <div class="flow-summary">
                <div class="summary-row">
                    <span class="label">Total Devengos:</span>
                    <span class="value positive">${summary.get('total_devengos', 0):,.2f}</span>
                </div>
                <div class="summary-row">
                    <span class="label">Total Deducciones:</span>
                    <span class="value negative">${summary.get('total_deducciones', 0):,.2f}</span>
                </div>
                <div class="summary-row total">
                    <span class="label">NETO A PAGAR:</span>
                    <span class="value">${summary.get('neto', 0):,.2f}</span>
                </div>
            </div>
        </div>
        ''')

        return '\n'.join(html_parts)

    def _get_flow_css(self):
        """Retorna CSS para el flujo."""
        return '''
        <style>
        .payroll-flow-container {
            font-family: 'Segoe UI', Roboto, sans-serif;
            max-width: 100%;
            padding: 16px;
            background: #f5f5f5;
            border-radius: 8px;
        }
        .flow-header {
            margin-bottom: 16px;
            padding-bottom: 12px;
            border-bottom: 2px solid #e0e0e0;
        }
        .flow-header h3 {
            margin: 0 0 8px 0;
            color: #333;
            font-size: 18px;
        }
        .flow-meta {
            display: flex;
            gap: 16px;
            color: #666;
            font-size: 13px;
        }
        .flow-diagram {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        .flow-phase {
            background: white;
            border-radius: 6px;
            padding: 12px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        .phase-header {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 8px;
        }
        .phase-name {
            font-weight: 600;
            color: #333;
            font-size: 14px;
        }
        .phase-badge {
            font-size: 10px;
            padding: 2px 6px;
            border-radius: 10px;
            background: #e3f2fd;
            color: #1976d2;
        }
        .phase-nodes {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }
        .flow-node {
            display: flex;
            align-items: center;
            gap: 6px;
            padding: 6px 10px;
            border-radius: 4px;
            font-size: 12px;
            background: #f9f9f9;
            border: 1px solid #e0e0e0;
        }
        .flow-node.positive .node-value { color: #2e7d32; }
        .flow-node.negative .node-value { color: #c62828; }
        .node-icon { font-size: 14px; }
        .node-name { color: #555; max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .node-value { font-weight: 600; font-family: monospace; }
        .flow-summary {
            margin-top: 16px;
            padding: 12px;
            background: white;
            border-radius: 6px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        .summary-row {
            display: flex;
            justify-content: space-between;
            padding: 6px 0;
            border-bottom: 1px solid #f0f0f0;
        }
        .summary-row.total {
            border-bottom: none;
            padding-top: 10px;
            margin-top: 6px;
            border-top: 2px solid #333;
            font-size: 16px;
            font-weight: 700;
        }
        .summary-row .label { color: #666; }
        .summary-row .value { font-family: monospace; font-weight: 600; }
        .summary-row .value.positive { color: #2e7d32; }
        .summary-row .value.negative { color: #c62828; }
        @media print {
            .payroll-flow-container { background: white; box-shadow: none; }
            .flow-phase { box-shadow: none; border: 1px solid #ddd; }
            .flow-summary { box-shadow: none; border: 1px solid #ddd; }
        }
        </style>
        '''


class HrPayslipFlowExtension(models.Model):
    """
    Extensión de hr.payslip para incluir funcionalidad de flujo.
    """

    _name = 'hr.payslip'
    _inherit = ['hr.payslip', 'hr.payslip.flow.mixin']

    # Redeclared to ensure field exists when hr_payroll_account is loaded alongside this module
    move_id = fields.Many2one('account.move', 'Accounting Entry', readonly=True, copy=False, index='btree_not_null')

    def action_view_flow(self):
        """Acción para ver el flujo en una ventana modal."""
        self.ensure_one()

        # Regenerar flujo si no existe
        if not self.flow_data:
            self.generate_flow_visualization()

        return {
            'name': f'Flujo de Cálculo - {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payslip',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref('lavish_hr_employee.view_hr_payslip_flow_form', raise_if_not_found=False).id,
            'target': 'new',
            'context': {'show_flow_only': True},
        }

    def action_regenerate_flow(self):
        """Acción para regenerar el flujo."""
        self.ensure_one()
        self.generate_flow_visualization()
        return True
