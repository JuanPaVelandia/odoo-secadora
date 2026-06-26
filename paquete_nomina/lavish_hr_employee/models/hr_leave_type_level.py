# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class HrLeaveTypeLevel(models.Model):
    """
    Modelo para manejar niveles de ausencias con rangos de días y porcentajes.
    Reemplaza la lógica de rangos fijos por un sistema flexible de niveles.
    """
    _name = 'hr.leave.type.level'
    _description = 'Niveles de Ausencia'
    _order = 'leave_type_id, sequence, day_from'
    
    # ===============================================================================
    # CAMPOS BÁSICOS
    # ===============================================================================
    
    name = fields.Char(
        string='Descripción',
        required=True,
        help='Descripción del nivel (ej: "Días 1-2", "Días 3-90")'
    )
    note = fields.Char(
        string='Nota',
        required=True,
    )
    sequence = fields.Integer(
        string='Secuencia',
        default=10,
        help='Orden de evaluación del nivel'
    )
    
    active = fields.Boolean(
        string='Activo',
        default=True
    )
    
    # ===============================================================================
    # RELACIÓN CON TIPO DE AUSENCIA
    # ===============================================================================
    
    leave_type_id = fields.Many2one(
        'hr.leave.type',
        string='Tipo de Ausencia',
        required=True,
        ondelete='cascade'
    )
    
    # ===============================================================================
    # CONFIGURACIÓN DE RANGOS
    # ===============================================================================
    
    day_from = fields.Integer(
        string='Desde Día',
        required=True,
        default=1,
        help='Día inicial del rango (inclusive)'
    )
    
    day_to = fields.Integer(
        string='Hasta Día',
        help='Día final del rango (inclusive). Dejar en blanco para rango abierto'
    )
    
    is_open_range = fields.Boolean(
        string='Rango Abierto',
        compute='_compute_is_open_range',
        store=True,
        help='Indica si el rango no tiene límite superior'
    )
    
    range_display = fields.Char(
        string='Rango',
        compute='_compute_range_display',
        store=True,
        help='Representación del rango de días'
    )
    
    # ===============================================================================
    # CONFIGURACIÓN DE PORCENTAJES Y RESPONSABILIDAD
    # ===============================================================================
    
    percentage = fields.Float(
        string='Porcentaje (%)',
        required=True,
        default=100.0,
        help='Porcentaje del salario que se reconoce en este rango'
    )
    
    entity_type = fields.Selection([
        ('company', 'Empresa'),
        ('eps', 'EPS'),
        ('arl', 'ARL'),
        ('pension', 'Fondo de Pensión'),
        ('ccf', 'Caja de Compensación'),
        ('other', 'Otro')
    ], string='Entidad Responsable', default='company', required=True,
        help='Entidad que debe asumir el pago en este rango')
    
    # ===============================================================================
    # CONFIGURACIÓN CONTABLE Y SALARIAL
    # ===============================================================================
    
    account_id = fields.Many2one(
        'account.account',
        string='Cuenta Contable',
        help='Cuenta contable para este nivel de ausencia'
    )
    
    salary_rule_id = fields.Many2one(
        'hr.salary.rule',
        string='Regla Salarial',
        help='Regla salarial asociada a este nivel'
    )
    
    # ===============================================================================
    # CAMPOS TÉCNICOS
    # ===============================================================================
    
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        related='leave_type_id.company_id',
        store=True
    )
    
    # ===============================================================================
    # MÉTODOS COMPUTADOS
    # ===============================================================================
    
    @api.depends('day_to')
    def _compute_is_open_range(self):
        """Calcula si el rango es abierto (sin límite superior)."""
        for level in self:
            level.is_open_range = not level.day_to or level.day_to == 0
    
    @api.depends('day_from', 'day_to')
    def _compute_range_display(self):
        """Calcula la representación textual del rango."""
        for level in self:
            if level.is_open_range:
                level.range_display = f"Día {level.day_from} en adelante"
            elif level.day_from == level.day_to:
                level.range_display = f"Día {level.day_from}"
            else:
                level.range_display = f"Días {level.day_from}-{level.day_to}"
    
    # ===============================================================================
    # VALIDACIONES
    # ===============================================================================
    
    @api.constrains('day_from', 'day_to')
    def _check_day_range(self):
        """Valida que los rangos de días sean coherentes."""
        for level in self:
            if level.day_from <= 0:
                raise ValidationError(_("El día inicial debe ser mayor a 0."))
            
            if level.day_to and level.day_to < level.day_from:
                raise ValidationError(_(
                    "El día final (%s) no puede ser menor al día inicial (%s)."
                ) % (level.day_to, level.day_from))
    
    @api.constrains('percentage')
    def _check_percentage(self):
        """Valida que el porcentaje esté en un rango válido."""
        for level in self:
            if level.percentage < 0 or level.percentage > 100:
                raise ValidationError(_(
                    "El porcentaje debe estar entre 0 y 100. "
                    "Valor actual: %s"
                ) % level.percentage)
    
    @api.constrains('leave_type_id', 'day_from', 'day_to')
    def _check_overlapping_ranges(self):
        """Valida que no haya rangos superpuestos en el mismo tipo de ausencia."""
        for level in self:
            domain = [
                ('leave_type_id', '=', level.leave_type_id.id),
                ('id', '!=', level.id),
                ('active', '=', True)
            ]
            
            overlapping_levels = self.search(domain).filtered(
                lambda l: level._ranges_overlap(l)
            )
            
            if overlapping_levels:
                overlapping_names = ', '.join(overlapping_levels.mapped('name'))
                raise ValidationError(_(
                    "El rango %s se superpone con: %s"
                ) % (level.range_display, overlapping_names))
    
    def _ranges_overlap(self, other_level):
        """Verifica si dos rangos se superponen."""
        # Si alguno de los rangos es abierto
        if self.is_open_range:
            # Este rango es abierto, se superpone si el otro inicia antes o en el mismo punto
            return other_level.day_from >= self.day_from or (
                other_level.day_to and other_level.day_to >= self.day_from
            )
        
        if other_level.is_open_range:
            # El otro rango es abierto
            return self.day_to >= other_level.day_from
        
        # Ambos rangos son cerrados
        return not (self.day_to < other_level.day_from or other_level.day_to < self.day_from)
    
    # ===============================================================================
    # MÉTODOS DE NEGOCIO
    # ===============================================================================
    
    def get_applicable_level(self, day_sequence):
        """
        Obtiene el nivel aplicable para un día específico.
        
        Args:
            day_sequence (int): Número del día de ausencia
            
        Returns:
            hr.leave.type.level: Nivel aplicable o False si no hay coincidencia
        """
        self.ensure_one()
        
        if self.is_open_range:
            return self if day_sequence >= self.day_from else False
        else:
            return self if self.day_from <= day_sequence <= self.day_to else False
    
    @api.model
    def find_applicable_level(self, leave_type, day_sequence):
        """
        Busca el nivel aplicable para un tipo de ausencia y día específico.
        
        Args:
            leave_type (hr.leave.type): Tipo de ausencia
            day_sequence (int): Número del día de ausencia
            
        Returns:
            hr.leave.type.level: Nivel aplicable o False
        """
        levels = self.search([
            ('leave_type_id', '=', leave_type.id),
            ('active', '=', True)
        ], order='sequence, day_from')
        
        for level in levels:
            if level.get_applicable_level(day_sequence):
                return level
        
        return False
    
    # ===============================================================================
    # MÉTODOS DE UTILIDAD
    # ===============================================================================
    
    def _compute_display_name(self):
        """Personaliza el nombre mostrado en las relaciones."""
        for level in self:
            name = f"{level.name} ({level.range_display}, {level.percentage}%)"
            if level.entity_type != 'company':
                name += f" - {dict(self._fields['entity_type'].selection)[level.entity_type]}"
            level.display_name = name