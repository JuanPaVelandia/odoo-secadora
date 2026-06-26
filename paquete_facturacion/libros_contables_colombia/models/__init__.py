# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

# Motor de calculos financieros
from . import engine

# Helpers SQL para Odoo 18 JSONB
from . import sql_helpers

# Extensiones de modelos base
from . import account_report_extend
from . import account_tax_extend

# Handlers de Libros Legales
from . import account_inventory_book
from . import account_journal_book
from . import account_ledger_book
from . import account_capital_difference
from . import account_auxiliary_book
from . import trial_balance_tercero
from . import trial_balance_puc
from . import report_tax

# Handlers de Estados Financieros
from . import cash_flow_handler
from . import financial_indicators_handler
from . import equity_changes_handler
from . import comparative_balance_handler
from . import comparative_income_handler

# Autoretenciones Colombia
from . import self_withholding

# Reportes de Auditoría Contable
from . import audit_reports

# Reportes Mensuales Comparativos
from . import monthly_reports_handler


# Balance de Movimientos del Periodo
from . import period_movements_handler
