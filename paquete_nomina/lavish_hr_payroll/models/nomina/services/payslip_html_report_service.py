# -*- coding: utf-8 -*-
"""
Servicio de Reportes HTML de Nómina
===================================

Genera reportes HTML formateados para nómina.
Incluye:
- Reporte de retención en la fuente
- Reporte de prestaciones sociales
- Combinación de múltiples reportes
"""

import logging

_logger = logging.getLogger(__name__)


class PayslipHtmlReportService:
    """
    Servicio para generar reportes HTML de nómina.
    Extrae la lógica de generación HTML de hr.payslip.
    """

    @staticmethod
    def format_currency(value):
        """Formatea un valor como moneda colombiana."""
        try:
            return f"${value:,.0f}" if value else "$0"
        except (KeyError, AttributeError):
            return "$0"

    @staticmethod
    def format_section(title, content):
        """Genera una sección HTML con título y contenido."""
        return f"""
            <div class="section-container" style="margin-bottom: 15px;">
                <div class="section-title" style="background-color: #C41E3A; color: white; padding: 8px; font-weight: bold;">
                    {title}
                </div>
                <div class="section-content" style="border: 1px solid #ddd; padding: 10px;">
                    {content}
                </div>
            </div>
        """

    @staticmethod
    def format_row(label, value, observation=None, limit=None):
        """Genera una fila HTML con label, valor y opcionalmente observación y límite."""
        limit_text = f'<div style="color: #0066cc; text-align: right; font-size: 0.9em;">Límite: {limit}</div>' if limit else ''
        obs_text = f'<div style="color: #C41E3A; font-size: 0.9em;">{observation}</div>' if observation else ''
        return f"""
            <div style="display: flex; justify-content: space-between; padding: 5px 0; border-bottom: 1px solid #eee;">
                <div style="flex: 2;">
                    {label}
                    {obs_text}
                    {limit_text}
                </div>
                <div style="flex: 1; text-align: right; font-weight: bold;">
                    {value}
                </div>
            </div>
        """

    @classmethod
    def format_retencion_html(cls, data):
        """
        Genera un reporte HTML detallado de la retención en la fuente.

        Args:
            data: Diccionario con los datos del reporte

        Returns:
            str: Reporte HTML formateado
        """
        if isinstance(data, list):
            data = data[0] if data else {}

        if not data:
            return "<div>No hay datos disponibles para mostrar</div>"

        fc = cls.format_currency
        fr = cls.format_row
        fs = cls.format_section

        html = f"""
        <div style="font-family: Arial, sans-serif; font-size: 13px;">
            <div style="background-color: #C41E3A; color: white; padding: 10px; display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                <div style="font-size: 16px; font-weight: bold;">RETENCIÓN EN LA FUENTE MENSUAL</div>
                <div>Valor UVT: {fc(data.get('uvt', 0))}</div>
            </div>
        """

        # Sección 1: Pagos Laborales
        ingresos = data.get('ingresos', {})
        ingresos_content = "".join([
            fr("Sueldo básico", fc(ingresos.get('salario', 0))),
            fr("Comisiones", fc(ingresos.get('comisiones', 0))),
            fr("Otros pagos laborales", fc(ingresos.get('otros_ingresos', 0))),
            fr("Total Ingresos Laborales", fc(ingresos.get('total', 0)))
        ])
        html += fs("1. PAGOS LABORALES DEL MES", ingresos_content)

        # Sección 2: Ingresos No Constitutivos
        aportes = data.get('aportes_obligatorios', {})
        no_renta_content = "".join([
            fr("Aportes obligatorios a Pensión", fc(aportes.get('pension', 0))),
            fr("Aportes obligatorios a Salud", fc(aportes.get('salud', 0))),
            fr("Total Ingresos No Constitutivos", fc(aportes.get('total', 0))),
            fr("Subtotal 1", fc(data.get('base_calculo', {}).get('subtotal_1', 0)))
        ])
        html += fs("2. INGRESOS NO CONSTITUTIVOS DE RENTA", no_renta_content)

        # Sección 3: Deducciones
        deducciones = data.get('deducciones', {})
        deducciones_content = "".join([
            fr(
                "Intereses de vivienda",
                fc(data.get('ded_vivienda', 0)),
                "Límite máximo 100 UVT Mensuales",
                fc(deducciones.get('limite_vivienda', 0))
            ),
            fr(
                "Dependientes",
                fc(deducciones.get('dependientes', 0)),
                "No puede exceder del 10% del ingreso bruto y máximo 32 UVT mensuales",
                fc(deducciones.get('limite_dependientes', 0))
            ),
            fr(
                "Medicina prepagada",
                fc(deducciones.get('salud_prepagada', 0)),
                "No puede exceder 16 UVT Mensuales",
                fc(deducciones.get('limite_salud', 0))
            ),
            fr("Total Deducciones", fc(deducciones.get('total', 0)))
        ])
        html += fs("3. DEDUCCIONES", deducciones_content)

        # Sección 4: Rentas Exentas
        rentas = data.get('rentas_exentas', {})
        rentas_content = "".join([
            fr(
                "Aportes AFC",
                fc(rentas.get('afc', 0)),
                "Límite del 30% del ingreso laboral y hasta 3.800 UVT anuales",
                fc(rentas.get('limite_afc', 0))
            ),
            fr(
                "Renta Exenta 25%",
                fc(rentas.get('renta_exenta_25', 0)),
                None,
                fc(rentas.get('limite_renta_25', 0))
            ),
            fr("Total Rentas Exentas", fc(rentas.get('total', 0)))
        ])
        html += fs("4. RENTAS EXENTAS", rentas_content)

        # Sección 5: Base Gravable
        base_calculo = data.get('base_calculo', {})
        base_content = "".join([
            fr("Base Gravable en UVTs", f"{base_calculo.get('base_uvts', 0):,.2f}"),
            fr("Porcentaje de Retención", f"{data.get('rate', 0)}%"),
            fr("Retención calculada", fc(data.get('valor', 0))),
            fr("Retención anterior", fc(data.get('anterior', 0))),
            fr("Retención definitiva", fc(data.get('definitiva', 0)))
        ])
        html += fs("5. BASE GRAVABLE Y RETENCIÓN", base_content)

        # Nota importante
        html += f"""
            <div style="background-color: #fff3cd; border: 1px solid #ffeeba; padding: 10px; margin-top: 15px; font-size: 0.9em;">
                <strong>NOTA IMPORTANTE:</strong><br>
                La sumatoria de las Deducciones, Rentas exentas y el 25% de la renta de trabajo exenta,
                no podrá superar el 40% del ingreso señalado en el subtotal 1 hasta 1340 UVT
            </div>
        """

        html += "</div>"
        return html

    @classmethod
    def format_prestaciones_report(cls, line, computation_data):
        """
        Genera un reporte HTML formateado para prestaciones sociales.

        Args:
            line: hr.payslip.line record
            computation_data: Diccionario con los datos del cómputo

        Returns:
            str: Reporte HTML formateado
        """
        fc = cls.format_currency

        def format_value(value):
            if isinstance(value, (int, float)):
                return fc(value)
            elif isinstance(value, dict):
                return format_dict(value)
            elif isinstance(value, list):
                return format_list(value)
            else:
                return str(value)

        def format_dict(data, level=0):
            html = '<div style="margin-left: 15px;">'
            for key, value in data.items():
                if isinstance(value, dict):
                    html += f'<div style="margin: 5px 0;"><strong>{key}:</strong></div>'
                    html += format_dict(value, level + 1)
                elif isinstance(value, list):
                    html += f'<div style="margin: 5px 0;"><strong>{key}:</strong></div>'
                    html += format_list(value, level + 1)
                else:
                    html += f'<div style="display: flex; justify-content: space-between; padding: 3px 0; border-bottom: 1px solid #eee;">'
                    html += f'<span>{key}:</span><span style="font-weight: bold;">{format_value(value)}</span></div>'
            html += '</div>'
            return html

        def format_list(items, level=0):
            html = '<ul style="margin: 5px 0; padding-left: 20px;">'
            for item in items:
                if isinstance(item, dict):
                    html += '<li>' + format_dict(item, level + 1) + '</li>'
                else:
                    html += f'<li>{format_value(item)}</li>'
            html += '</ul>'
            return html

        html = f"""
        <div style="font-family: Arial, sans-serif; font-size: 13px; margin-bottom: 20px;">
            <div style="background-color: #C41E3A; color: white; padding: 10px; margin-bottom: 10px;">
                <div style="font-size: 16px; font-weight: bold;">{line.name}</div>
                <div style="font-size: 12px;">Código: {line.code or 'N/A'}</div>
            </div>
            <div style="border: 1px solid #ddd; padding: 15px; background-color: #f9f9f9;">
                <div style="display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 2px solid #C41E3A; margin-bottom: 10px;">
                    <span style="font-weight: bold;">Total:</span>
                    <span style="font-weight: bold; font-size: 16px; color: #C41E3A;">{fc(line.total)}</span>
                </div>
        """

        if computation_data:
            html += '<div style="margin-top: 15px;"><strong>Detalle del Cálculo:</strong></div>'
            html += format_dict(computation_data)
        else:
            html += '<div style="color: #666; font-style: italic;">No hay datos de cálculo disponibles</div>'

        html += """
            </div>
        </div>
        """

        return html

    @classmethod
    def combine_reports(cls, reports):
        """
        Combina múltiples reportes HTML en uno solo.

        Args:
            reports: Lista de strings HTML

        Returns:
            str: HTML combinado
        """
        combined_html = '<div class="prestaciones-sociales-combined-report">'
        combined_html += '<h1>Reporte de Prestaciones Sociales</h1>'
        for report in reports:
            combined_html += report
            combined_html += '<hr>'
        combined_html += '</div>'
        return combined_html

    @classmethod
    def empty_prestaciones_report(cls):
        """Retorna mensaje HTML cuando no hay prestaciones."""
        return '<p>No hay datos de prestaciones sociales disponibles.</p>'
