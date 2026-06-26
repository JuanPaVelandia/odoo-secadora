# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class TreasurySequenceConfig(models.Model):
    """
    Configuración de secuencias de tesorería.
    Permite configurar secuencias diferentes para:
    - Egresos (pagos a proveedores)
    - Recibos de Caja (cobros de clientes)
    - Anticipos (por tipo de anticipo)
    """
    _name = 'treasury.sequence.config'
    _description = 'Configuración de Secuencias de Tesorería'
    _order = 'sequence, id'

    name = fields.Char(
        string='Nombre',
        required=True,
    )
    sequence = fields.Integer(
        string='Secuencia',
        default=10,
    )
    active = fields.Boolean(
        string='Activo',
        default=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        default=lambda self: self.env.company,
        required=True,
    )

    # Tipo de configuración
    config_type = fields.Selection([
        ('payment', 'Pago/Egreso'),
        ('receipt', 'Recibo de Caja'),
        ('advance', 'Anticipo'),
    ], string='Tipo', required=True, default='payment')

    # Filtros de aplicación
    journal_ids = fields.Many2many(
        'account.journal',
        string='Diarios',
        domain="[('type', 'in', ['bank', 'cash'])]",
        help='Diarios donde aplica esta secuencia. Vacío = todos los diarios.',
    )
    payment_type = fields.Selection([
        ('outbound', 'Pago (Egreso)'),
        ('inbound', 'Cobro (Ingreso)'),
    ], string='Tipo de Pago')

    advance_type_id = fields.Many2one(
        'advance.type',
        string='Tipo de Anticipo',
        help='Tipo de anticipo específico. Solo para config_type = advance.',
    )

    # Secuencia
    sequence_id = fields.Many2one(
        'ir.sequence',
        string='Secuencia',
        required=True,
        ondelete='restrict',
        help='Secuencia a usar para generar el número.',
    )

    # Formato
    prefix = fields.Char(
        string='Prefijo',
        help='Prefijo adicional para el número (ej: EGR, RC, ANT)',
    )
    suffix = fields.Char(
        string='Sufijo',
        help='Sufijo adicional para el número',
    )

    # Contadores de uso
    usage_count = fields.Integer(
        string='Veces Usado',
        compute='_compute_usage_count',
    )

    def _compute_usage_count(self):
        for record in self:
            # Contar pagos que usan esta configuración
            record.usage_count = self.env['account.payment'].search_count([
                ('treasury_sequence_config_id', '=', record.id)
            ])

    @api.model
    def get_sequence_for_payment(self, payment):
        """
        Obtiene la configuración de secuencia apropiada para un pago.
        Prioridad:
        1. Anticipo con tipo específico
        2. Configuración por diario y tipo de pago
        3. Configuración por tipo de pago
        4. Configuración por defecto
        """
        domain = [
            ('active', '=', True),
            ('company_id', '=', payment.company_id.id),
        ]

        # Si es anticipo, buscar configuración específica
        if payment.advance and payment.advance_type_id:
            config = self.search(domain + [
                ('config_type', '=', 'advance'),
                ('advance_type_id', '=', payment.advance_type_id.id),
            ], limit=1)
            if config:
                return config

        # Determinar tipo de config según tipo de pago
        if payment.payment_type == 'inbound':
            config_type = 'receipt'
        else:
            config_type = 'payment'

        # Buscar por diario específico
        if payment.journal_id:
            config = self.search(domain + [
                ('config_type', '=', config_type),
                ('journal_ids', 'in', [payment.journal_id.id]),
            ], limit=1)
            if config:
                return config

        # Buscar configuración general por tipo
        config = self.search(domain + [
            ('config_type', '=', config_type),
            ('journal_ids', '=', False),
        ], limit=1)

        return config

    def get_next_number(self, payment=None):
        """
        Genera el siguiente número usando esta configuración.
        """
        self.ensure_one()
        if not self.sequence_id:
            raise UserError(_('No se ha configurado una secuencia para %s') % self.name)

        number = self.sequence_id.next_by_id()

        # Agregar prefijo y sufijo si están configurados
        if self.prefix:
            number = f"{self.prefix}{number}"
        if self.suffix:
            number = f"{number}{self.suffix}"

        return number


class TreasurySequenceType(models.Model):
    """
    Tipos predefinidos de secuencias de tesorería.
    Facilita la creación de secuencias estándar.
    """
    _name = 'treasury.sequence.type'
    _description = 'Tipo de Secuencia de Tesorería'

    name = fields.Char(string='Nombre', required=True)
    code = fields.Char(string='Código', required=True)
    prefix = fields.Char(string='Prefijo Sugerido')
    description = fields.Text(string='Descripción')
