# -*- coding: utf-8 -*-
from odoo import models, _


class ReportLineMixin(models.AbstractModel):
    """Mixin para generacion de lineas de reportes contables."""

    _name = 'report.line.mixin'
    _description = 'Mixin de Lineas de Reporte'

    # Configuracion base (sobrescribir en hijos)
    _report_css_class = 'generic_report'
    _report_line_template = 'account_reports.GeneralLedgerLineName'
    _report_filter_component = 'libros_contables_colombia.TrialBalancePartnerFilters'

    def _get_custom_display_config(self):
        """Configuracion de display - usa propiedades de clase."""
        return {
            'css_custom_class': self._report_css_class,
            'templates': {
                'AccountReportLineName': self._report_line_template,
            },
            'components': {
                'AccountReportFilters': self._report_filter_component,
            },
        }

    def _build_line(self, report, options, line_id, name, columns,
                    level=0, unfoldable=False, unfolded=False,
                    parent_id=None, class_name='', code=''):
        """
        Construye una linea de reporte con estructura estandar.

        Args:
            report: Objeto account.report
            options: Opciones del reporte
            line_id: ID unico de la linea
            name: Nombre/etiqueta de la linea
            columns: Lista de valores de columnas
            level: Nivel de indentacion (0-6)
            unfoldable: Si puede expandirse
            unfolded: Si esta expandida
            parent_id: ID de linea padre
            class_name: Clase CSS adicional
            code: Codigo de cuenta (opcional)

        Returns:
            dict: Estructura de linea compatible con account.report
        """
        line = {
            'id': report._get_generic_line_id(None, None, line_id),
            'name': name,
            'level': level,
            'columns': self._format_columns(columns, options),
            'unfoldable': unfoldable,
            'unfolded': unfolded,
            'class': class_name,
        }

        if parent_id:
            line['parent_id'] = report._get_generic_line_id(None, None, parent_id)

        if code:
            line['code'] = code

        return line

    def _format_columns(self, values, options):
        """
        Formatea valores para columnas del reporte.

        Args:
            values: Lista de valores (numeros o dicts)
            options: Opciones del reporte

        Returns:
            list: Lista de dicts con formato de columna
        """
        columns = []
        for value in values:
            if isinstance(value, dict):
                columns.append(value)
            elif isinstance(value, (int, float)):
                columns.append({
                    'name': self._format_number(value, options),
                    'no_format': value,
                    'figure_type': 'monetary',
                })
            else:
                columns.append({
                    'name': str(value) if value else '',
                    'no_format': value,
                })
        return columns

    def _format_number(self, value, options, precision=2):
        """Formatea numero con formato contable."""
        if value is None:
            return ''
        if value < 0:
            return f"({abs(value):,.{precision}f})"
        return f"{value:,.{precision}f}"

    def _get_section_header(self, report, options, name, section_id, level=0):
        """Genera linea de encabezado de seccion."""
        return self._build_line(
            report, options,
            line_id=f'section_{section_id}',
            name=name,
            columns=[],
            level=level,
            class_name='section_header o_account_reports_level0'
        )

    def _get_data_line(self, report, options, name, value, line_id,
                       level=2, code='', additional_columns=None):
        """Genera linea de datos."""
        columns = [value]
        if additional_columns:
            columns.extend(additional_columns)

        return self._build_line(
            report, options,
            line_id=line_id,
            name=name,
            columns=columns,
            level=level,
            code=code,
            class_name=f'data_line level_{level}'
        )

    def _get_subtotal_line(self, report, options, name, value, line_id, level=1):
        """Genera linea de subtotal."""
        return self._build_line(
            report, options,
            line_id=f'subtotal_{line_id}',
            name=name,
            columns=[value],
            level=level,
            class_name='subtotal o_account_reports_level1'
        )

    def _get_total_line(self, report, options, name, value, line_id='total'):
        """Genera linea de total general."""
        return self._build_line(
            report, options,
            line_id=f'total_{line_id}',
            name=name,
            columns=[value],
            level=0,
            class_name='total o_account_reports_level0'
        )

    def _get_label_line(self, report, options, name, line_id):
        """Genera linea de etiqueta sin valores."""
        return self._build_line(
            report, options,
            line_id=f'label_{line_id}',
            name=name,
            columns=[],
            level=2,
            class_name='label_line'
        )

    def _get_no_data_line(self, report, options):
        """Genera linea cuando no hay datos."""
        return self._build_line(
            report, options,
            line_id='no_data',
            name=_('No hay datos para mostrar'),
            columns=[],
            level=0,
            class_name='text-muted text-center'
        )

    def _get_error_line(self, report, options, error_msg):
        """Genera linea de error."""
        return self._build_line(
            report, options,
            line_id='error',
            name=f'Error: {error_msg}',
            columns=[],
            level=0,
            class_name='text-danger'
        )
