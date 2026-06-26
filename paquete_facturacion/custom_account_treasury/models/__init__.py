# -*- coding: utf-8 -*-
# =============================================================================
# CUSTOM ACCOUNT TREASURY - Modelos (Un archivo por modelo)
# =============================================================================

# Mixins
from . import payment_tax_mixin

# Configuración base
from . import account_account
from . import account_journal
from . import res_company
from . import res_config_settings

# Tipos de anticipo y aprobación
from . import advance_type
from . import advance_approval_limit

# Solicitudes de anticipo (incluye: AdvanceReconciliation, AdvanceRequestReconcileLine)
from . import advance_request
# Etapas de anticipo (incluye: AdvanceRequestStageHistory)
from . import advance_request_stage

# Solicitudes de pago (incluye: PaymentRequestStage, PaymentRequestAddOrders)
from . import payment_request

# Pagos (modelo principal consolidado)
from . import account_payment
from . import account_payment_detail
from . import account_payment_method_line_detail

# Extensiones de movimientos
from . import account_move
from . import account_move_line

# Integración con ventas/compras
from . import sale_order
from . import purchase_order
from . import sale_purchase_advance

# Dashboard
from . import treasury_dashboard

# Secuencias de tesorería
from . import treasury_sequence_config

# Comisiones bancarias y calendario de pagos
from . import treasury_bank_commission
from . import treasury_bank_charge_type

# Extensiones para cargos en extractos bancarios
from . import account_bank_statement_line
