# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from datetime import datetime, timedelta, date
from odoo.exceptions import UserError, ValidationError
from dateutil.relativedelta import relativedelta
from pytz import timezone
import time
import base64
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT

CONTRACT_GROUP_ID_HELP = """
Este campo permite agrupar los contratos, según se va a calcular la nómina.
Sirve para grupos que no sea por banco, centro de costo y/o ciudad de desempeño.
"""
ARL_ID_HELP = "ARL en el caso que el empleado sea independiente"
ANALYTIC_DISTRIBUTION_TOTAL_WARN = """: La suma de las distribuciones analíticas debe ser 100.0%%,
Valor actual: %s%%"""
CONTRACT_EXTENSION_NO_RECORD_WARN = """
Para prorrogar el contrato por favor registre una prorroga
"""
CONTRACT_EXTENSION_MAX_WARN = """
No es posible realizar una prórroga por un periodo inferior
a un año despues de tener 3 o más prórrogas
"""
NO_PARTNER_REF_WARN = """
No se encontró el numero de documento en el contacto
"""
IN_FORCE_CONTRACT_WARN = """
El empleado yá tiene un contrato activo: %s.
"""

NO_WAGE_HISTORY = """
El contrato %s no tiene un historial de salarios.
"""

MANY_WAGE_HISTORY = """
El contrato %s tiene %s cambios salariales en este rango %s a %s.
Solo se permite 1 por periodo.
"""

LAST_ONE = -1
import calendar
import logging
from typing import Dict, List, Union, Optional, Tuple, Any, TypeVar, cast
from odoo.tools.safe_eval import safe_eval
_logger = logging.getLogger(__name__)

PRECISION_TECHNICAL = 10
PRECISION_DISPLAY = 2

T = TypeVar('T')
def days360(start_date, end_date, method_eu=True):
    """Compute number of days between two dates regarding all months
    as 30-day months"""

    start_day = start_date.day
    start_month = start_date.month
    start_year = start_date.year
    end_day = end_date.day
    end_month = end_date.month
    end_year = end_date.year

    if (
            start_day == 31 or
            (
                method_eu is False and
                start_month == 2 and (
                    start_day == 29 or (
                        start_day == 28 and
                        calendar.isleap(start_year) is False
                    )
                )
            )
    ):
        start_day = 30

    if end_day == 31:
        if method_eu is False and start_day != 30:
            end_day = 1

            if end_month == 12:
                end_year += 1
                end_month = 1
            else:
                end_month += 1
        else:
            end_day = 30
    if end_month == 2 and end_day in (28, 29):
        end_day = 30

    return (
        end_day + end_month * 30 + end_year * 360 -
        start_day - start_month * 30 - start_year * 360 + 1
    )

class HrPayslipLine(models.Model):
    _inherit = 'hr.payslip.line'

    # v19 bridge: en v18 hr.payslip.line tenia contract_id propio; en v19 el modelo
    # nativo solo expone version_id. Lo recreamos como related stored hacia el
    # contract_id puente que vive en hr.payslip (ver lavish_hr_employee/.../hr_payslip_contract_bridge.py)
    # para que las queries y dominios heredados de v18 sigan funcionando.
    contract_id = fields.Many2one(
        'hr.contract',
        string='Contrato',
        related='slip_id.contract_id',
        store=True,
        index=True,
    )

    # Métodos adicionales
    def mark_as_reviewed(self) -> None:
        """Marca la línea como revisada"""
        self.ensure_one()
        self.write({
            'reviewed': True,
            'adjusted_by': self.env.user.id,
            'adjustment_date': fields.Datetime.now()
        })
        
    def reset_review_status(self) -> None:
        """Reinicia el estado de revisión"""
        self.ensure_one()
        self.write({
            'reviewed': False,
            'adjustment_reason': False
        })
    
    def apply_manual_adjustment(self, new_amount: float, reason: str) -> None:
        """
        Aplica un ajuste manual al monto de la línea
        
        Args:
            new_amount: Nuevo monto a aplicar
            reason: Razón del ajuste
        """
        self.ensure_one()
        if not self.manual_adjustment:
            original = self.amount
        else:
            original = self.original_amount
        self.write({
            'manual_adjustment': True,
            'original_amount': original,
            'amount': new_amount,
            'adjustment_reason': reason,
            'adjusted_by': self.env.user.id,
            'adjustment_date': fields.Datetime.now(),
            'reviewed': True
        })
        if self.slip_id:
            msg = _("""
                <div class="o_mail_notification">
                    <div><strong>Ajuste Manual en Línea de Nómina</strong></div>
                    <div>Concepto: %s</div>
                    <div>Valor Original: %s</div>
                    <div>Nuevo Valor: %s</div>
                    <div>Motivo: %s</div>
                </div>
            """) % (
                self.name or '',
                self.company_id.currency_id.symbol + ' ' + str(original),
                self.company_id.currency_id.symbol + ' ' + str(new_amount),
                reason or ''
            )
            self.slip_id.message_post(body=msg, subtype_xmlid="mail.mt_note")
            
    def revert_manual_adjustment(self) -> None:
        """Revierte el ajuste manual a los valores originales"""
        self.ensure_one()
        if not self.manual_adjustment:
            return
        self.write({
            'amount': self.original_amount,
            'manual_adjustment': False,
            'adjustment_reason': False,
            'reviewed': True
        })
        if self.slip_id:
            msg = _("""
                <div class="o_mail_notification">
                    <div><strong>Ajuste Manual Revertido</strong></div>
                    <div>Concepto: %s</div>
                    <div>Valor Restaurado: %s</div>
                </div>
            """) % (
                self.name or '',
                self.company_id.currency_id.symbol + ' ' + str(self.amount)
            )
            self.slip_id.message_post(body=msg, subtype_xmlid="mail.mt_note")
