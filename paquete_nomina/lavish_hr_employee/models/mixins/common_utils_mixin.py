# -*- coding: utf-8 -*-
"""
Mixin de utilidades comunes para nómina colombiana.
Centraliza métodos frecuentemente usados para evitar duplicación.
"""

from odoo import models, api


class CommonUtilsMixin(models.AbstractModel):
    """
    Mixin abstracto con utilidades comunes.

    Proporciona:
    - _get_company_data(): Datos de la empresa para reportes
    - _get_month_name(): Nombre del mes en español
    - _format_period(): Formateo de período para reportes
    - _format_currency(): Formateo de moneda
    """
    _name = 'common.utils.mixin'
    _description = 'Mixin de Utilidades Comunes'

    def _get_company_data(self, company=None):
        """
        Obtiene los datos de la empresa actual o especificada.

        Args:
            company: Objeto res.company opcional. Si no se especifica,
                    usa self.env.company

        Returns:
            dict: Diccionario con datos de la empresa
        """
        company = company or self.env.company
        return {
            'name': company.name,
            'vat': company.vat,
            'nit': company.vat,  # Alias para compatibilidad
            'phone': company.phone,
            'email': company.email,
            'website': company.website,
            'street': company.street,
            'city': company.city,
            'state': company.state_id.name if company.state_id else '',
            'country': company.country_id.name if company.country_id else '',
            'zip': company.zip,
            'logo': company.logo,
        }

    def _get_month_name(self, month_number):
        """
        Obtiene el nombre del mes en español a partir de su número.

        Args:
            month_number: Número del mes (1-12)

        Returns:
            str: Nombre del mes en español
        """
        meses = {
            1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
            5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
            9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
        }
        return meses.get(month_number, f"Mes {month_number}")

    def _format_period(self, year, month, quincena='0'):
        """
        Formatea el periodo para mostrar en reportes.

        Args:
            year: Año
            month: Mes (1-12)
            quincena: '0' = mensual, '1' = Q1, '2' = Q2

        Returns:
            str: Período formateado (ej: "Enero 2024", "Q1 Enero 2024")
        """
        mes = self._get_month_name(month)
        if quincena == '0':
            return f"{mes} {year}"
        else:
            quincena_str = 'Q1' if quincena == '1' else 'Q2'
            return f"{quincena_str} {mes} {year}"

    def _format_currency(self, value, symbol='$', decimals=0):
        """
        Formatea un valor como moneda.

        Args:
            value: Valor numérico
            symbol: Símbolo de moneda (default: '$')
            decimals: Cantidad de decimales (default: 0)

        Returns:
            str: Valor formateado (ej: "$1,234,567")
        """
        try:
            if decimals == 0:
                return f"{symbol}{value:,.0f}" if value else f"{symbol}0"
            else:
                return f"{symbol}{value:,.{decimals}f}" if value else f"{symbol}0"
        except (ValueError, TypeError):
            return f"{symbol}0"

    def _get_periodo_label(self, payslip):
        """
        Genera etiqueta de período para un payslip.

        Args:
            payslip: Objeto hr.payslip

        Returns:
            str: Etiqueta del período (ej: "ENERO 2024")
        """
        if not payslip or not payslip.date_to:
            return ''
        return f"{self._get_month_name(payslip.date_to.month).upper()} {payslip.date_to.year}"
