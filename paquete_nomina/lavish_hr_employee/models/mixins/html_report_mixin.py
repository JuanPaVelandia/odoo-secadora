# -*- coding: utf-8 -*-
"""
Mixin para generación de reportes HTML en nómina usando Bootstrap 5.3.3
Separa la lógica de presentación de la lógica de negocio
Todos los reportes usan Bootstrap 5.3.3 nativo y Bootstrap Icons
"""

from odoo import models, api
from odoo.tools import format_date, formatLang
from ..builders.html_builders import (
    ProvisionHTMLBuilder,
    SocialSecurityHTMLBuilder,
    LeaveHTMLBuilder
)
from typing import List, Dict, Any, Optional


class PayrollHTMLReportMixin(models.AbstractModel):
    """
    Mixin abstracto para generar reportes HTML de nómina con Bootstrap 5.3.3
    Usa builders para separar construcción de HTML
    Todos los reportes generados incluyen estilos de Bootstrap y iconos
    """
    _name = 'payroll.html.report.mixin'
    _description = 'Mixin para Reportes HTML de Nómina con Bootstrap'

    # ============================================
    # MÉTODOS DE FORMATEO
    # ============================================

    def _format_money(self, amount: float, currency_id=None) -> str:
        """Formatea cantidad como dinero"""
        self.ensure_one()
        currency = currency_id or self.env.company.currency_id
        return formatLang(self.env, amount, currency_obj=currency)

    def _format_number(self, number: float, digits: int = 2) -> str:
        """Formatea número con decimales"""
        self.ensure_one()
        return formatLang(self.env, number, digits=digits)

    def _format_date(self, date_value) -> str:
        """Formatea fecha"""
        self.ensure_one()
        return format_date(self.env, date_value) if date_value else ''

    def _format_percentage(self, value: float) -> str:
        """Formatea porcentaje"""
        return f"{value:.2f}%"

    # ============================================
    # BUILDERS DE PROVISIONES
    # ============================================

    def _build_provision_html(
        self,
        provision_type: str,
        periodo: str,
        steps: List[Dict[str, str]],
        total: float,
        applied: bool = True
    ) -> str:
        """
        Construye HTML para provisiones (vacaciones, prima, cesantías, intereses)

        Args:
            provision_type: Tipo de provisión ('vacaciones', 'prima', 'cesantias', 'intereses')
            periodo: Texto del periodo
            steps: Lista de pasos del cálculo [{'concepto': 'X', 'valor': 'Y'}, ...]
            total: Valor total calculado
            applied: Si se aplicó o no

        Returns:
            HTML string
        """
        builder = ProvisionHTMLBuilder(provision_type)
        builder.add_header(periodo)

        if steps:
            builder.add_steps_table(steps)

        total_formatted = self._format_money(total)
        builder.add_result(total_formatted, applied)

        return builder.build()

    # ============================================
    # BUILDERS DE SEGURIDAD SOCIAL
    # ============================================

    def _build_ssocial_html_log(
        self,
        periodo: str,
        aplicado: bool,
        descripcion: str,
        titulo: Optional[str] = None,
        pasos: Optional[List[str]] = None,
        detalles: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        Construye HTML para logs de seguridad social y conceptos

        Args:
            periodo: Periodo de la nómina
            aplicado: Si el concepto se aplicó
            descripcion: Descripción del cálculo
            titulo: Título opcional (por defecto usa descripcion)
            pasos: Lista opcional de pasos del cálculo
            detalles: Lista opcional de detalles {'campo': 'X', 'valor': 'Y', 'highlight': bool}

        Returns:
            HTML string
        """
        builder = SocialSecurityHTMLBuilder()
        builder.add_header(titulo or descripcion, periodo, aplicado)
        builder.add_description(descripcion)

        if pasos:
            builder.add_steps_list(pasos)

        if detalles:
            builder.add_details_table(detalles)

        return builder.build()

    # ============================================
    # BUILDERS DE VACACIONES
    # ============================================

    def _build_leave_html(
        self,
        tipo: str,
        periodo: str,
        summary: Dict[str, str],
        pasos: Optional[List[str]] = None
    ) -> str:
        """
        Construye HTML para reportes de vacaciones

        Args:
            tipo: Tipo de ausencia
            periodo: Periodo
            summary: Resumen con información {'campo': 'valor'}
            pasos: Pasos opcionales del cálculo

        Returns:
            HTML string
        """
        builder = LeaveHTMLBuilder()
        builder.add_leave_header(tipo, periodo)
        builder.add_leave_summary(summary)

        if pasos:
            builder.add_steps_list(pasos)

        return builder.build()

    # ============================================
    # HELPERS DE PERIODO
    # ============================================

    def _get_periodo(self, payslip) -> str:
        """
        Obtiene string formateado del periodo de nómina

        Args:
            payslip: Registro de hr.payslip

        Returns:
            String como "01/01/2024 - 15/01/2024"
        """
        self.ensure_one()
        fecha_desde = self._format_date(payslip.date_from)
        fecha_hasta = self._format_date(payslip.date_to)
        return f"{fecha_desde} - {fecha_hasta}"

    def _get_periodo_mes_anio(self, payslip) -> str:
        """
        Obtiene periodo como "Enero 2024"

        Args:
            payslip: Registro de hr.payslip

        Returns:
            String como "Enero 2024"
        """
        self.ensure_one()
        from babel.dates import format_date
        locale = self.env.context.get('lang', 'es_ES')
        mes = format_date(payslip.date_from, "MMMM", locale=locale).capitalize()
        anio = payslip.date_from.year
        return f"{mes} {anio}"

    # ============================================
    # MÉTODOS DE UTILIDAD
    # ============================================

    def _build_simple_html_table(
        self,
        headers: List[str],
        rows: List[List[str]],
        table_class: str = "table table-sm table-bordered"
    ) -> str:
        """
        Construye una tabla HTML simple

        Args:
            headers: Lista de encabezados
            rows: Lista de listas con datos de filas
            table_class: Clase CSS para la tabla

        Returns:
            HTML string
        """
        header_html = "".join([f"<th>{h}</th>" for h in headers])
        rows_html = "\n".join([
            f"<tr>{''.join([f'<td>{cell}</td>' for cell in row])}</tr>"
            for row in rows
        ])

        return f"""
        <table class="{table_class}">
            <thead><tr>{header_html}</tr></thead>
            <tbody>{rows_html}</tbody>
        </table>
        """

    def _build_alert_box(
        self,
        message: str,
        alert_type: str = 'info',
        title: Optional[str] = None
    ) -> str:
        """
        Construye un alert box HTML

        Args:
            message: Mensaje a mostrar
            alert_type: Tipo de alerta ('info', 'warning', 'success', 'danger')
            title: Título opcional

        Returns:
            HTML string
        """
        title_html = f"<strong>{title}</strong><br>" if title else ""
        return f'<div class="alert-{alert_type}">{title_html}{message}</div>'
