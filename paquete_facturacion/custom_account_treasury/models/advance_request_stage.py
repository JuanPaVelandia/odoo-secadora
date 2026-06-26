# -*- coding: utf-8 -*-
from odoo import models, fields, api


class AdvanceRequestStage(models.Model):
    """Etapas para solicitudes de anticipo"""
    _name = 'advance.request.stage'
    _description = 'Etapa de Solicitud de Anticipo'
    _order = 'sequence, id'

    name = fields.Char(
        string='Nombre',
        required=True
    )

    code = fields.Char(
        string='Código',
        help='Código interno de la etapa'
    )

    sequence = fields.Integer(
        string='Secuencia',
        default=10
    )

    # Control de tiempo en etapa
    max_days_in_stage = fields.Integer(
        string='Días Máximos en Etapa',
        default=0,
        help='Número máximo de días que puede permanecer en esta etapa (0 = sin límite)'
    )

    alert_before_days = fields.Integer(
        string='Alertar Antes (días)',
        default=1,
        help='Días antes del vencimiento para enviar alerta'
    )

    escalation_user_id = fields.Many2one(
        'res.users',
        string='Usuario de Escalamiento',
        help='Usuario al que se escala cuando se excede el tiempo'
    )

    color_time_normal = fields.Char(
        string='Color Normal',
        default='#28a745',
        help='Color cuando está dentro del tiempo'
    )

    color_time_warning = fields.Char(
        string='Color Advertencia',
        default='#ffc107',
        help='Color cuando se acerca al límite de tiempo'
    )

    color_time_danger = fields.Char(
        string='Color Peligro',
        default='#dc3545',
        help='Color cuando excede el tiempo límite'
    )

    # Asociación con tipos de préstamo/anticipo
    advance_type_ids = fields.Many2many(
        'advance.type',
        'stage_advance_type_rel',
        'stage_id',
        'type_id',
        string='Tipos de Anticipo',
        help='Tipos de anticipo que pueden usar esta etapa'
    )

    fold = fields.Boolean(
        string='Plegado en Kanban',
        help='Esta etapa está plegada en la vista kanban'
    )

    # Campos bool simples para control de flujo
    can_create_draft_payment = fields.Boolean(
        string='Crear Pago en Borrador',
        default=False,
        help='Permite crear pagos en borrador desde esta etapa'
    )

    can_post_payment = fields.Boolean(
        string='Publicar Pago',
        default=False,
        help='Permite publicar/confirmar pagos desde esta etapa'
    )
    is_default = fields.Boolean(
        string='¿Es por defecto?',
        default=False
    )

    is_done = fields.Boolean(
        string='Etapa Final',
        default=False,
        help='Indica si esta es una etapa final/completada'
    )

    # Control de aprobación
    approval_user_ids = fields.Many2many(
        'res.users',
        'stage_approval_user_rel',
        'stage_id',
        'user_id',
        string='Usuarios Aprobadores',
        help='Usuarios que pueden aprobar en esta etapa'
    )

    approval_amount_min = fields.Monetary(
        string='Monto Mínimo para Aprobación',
        currency_field='currency_id',
        help='Si el monto es mayor a este valor, requiere aprobación especial'
    )

    approval_group_id = fields.Many2one(
        'res.groups',
        string='Grupo de Aprobación Especial',
        help='Grupo para aprobación cuando el monto supera el límite'
    )

    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        default=lambda self: self.env.company.currency_id
    )

    # Plantillas de correo y notificaciones
    mail_template_id = fields.Many2one(
        'mail.template',
        string='Plantilla de Correo',
        domain="[('model', '=', 'advance.request')]",
        help='Plantilla de correo para enviar cuando se llega a esta etapa'
    )

    send_email_to = fields.Selection([
        ('none', 'No enviar'),
        ('customer', 'Al Cliente/Proveedor'),
        ('internal', 'Solo Interno'),
        ('both', 'Ambos')
    ],
        string='Enviar Correo a',
        default='none',
        help='A quién enviar el correo cuando se llega a esta etapa'
    )

    template_approved = fields.Text(
        string='Mensaje al Aprobar',
        default='Solicitud aprobada',
        help='Mensaje que se muestra cuando se aprueba en esta etapa'
    )

    template_rejected = fields.Text(
        string='Mensaje al Rechazar',
        default='Solicitud rechazada',
        help='Mensaje que se muestra cuando se rechaza en esta etapa'
    )

    # Configuración de portal
    show_in_portal = fields.Boolean(
        string='Mostrar en Portal',
        default=False,
        help='Las solicitudes en esta etapa se muestran en el portal del cliente'
    )

    portal_user_can_edit = fields.Boolean(
        string='Editable en Portal',
        default=False,
        help='El usuario del portal puede editar la solicitud en esta etapa'
    )

    portal_description = fields.Text(
        string='Descripción para Portal',
        help='Descripción que se muestra en el portal para esta etapa'
    )

    # Actividades predeterminadas
    activity_type_ids = fields.Many2many(
        'mail.activity.type',
        string='Actividades Predeterminadas',
        help='Actividades que se crearán automáticamente al entrar a esta etapa'
    )

    legend_blocked = fields.Char(
        string='Leyenda Bloqueado',
        default='Bloqueado'
    )

    legend_done = fields.Char(
        string='Leyenda Hecho',
        default='Listo'
    )

    legend_normal = fields.Char(
        string='Leyenda Normal',
        default='En progreso'
    )

    # Métricas calculadas dinámicamente
    avg_duration = fields.Float(
        string='Duración Promedio (horas)',
        compute='_compute_stage_metrics',
        help='Tiempo promedio que las solicitudes permanecen en esta etapa'
    )

    current_request_count = fields.Integer(
        string='Solicitudes Actuales',
        compute='_compute_stage_metrics',
        help='Número de solicitudes actualmente en esta etapa'
    )

    overdue_count = fields.Integer(
        string='Solicitudes Vencidas',
        compute='_compute_stage_metrics',
        help='Número de solicitudes que exceden el tiempo máximo'
    )

    success_rate = fields.Float(
        string='Tasa de Éxito (%)',
        compute='_compute_stage_metrics',
        help='Porcentaje de solicitudes que pasan exitosamente por esta etapa'
    )

    bottleneck_score = fields.Float(
        string='Índice de Cuello de Botella',
        compute='_compute_stage_metrics',
        help='Indicador de qué tan problemática es esta etapa (0-100)'
    )

    @api.depends('name')
    def _compute_stage_metrics(self):
        """Calcula métricas dinámicas para cada etapa usando el tracking nativo"""
        from datetime import timedelta

        for stage in self:
            # Obtener todas las solicitudes que tienen esta etapa
            current_requests = self.env['advance.request'].search([
                ('stage_id', '=', stage.id)
            ])

            stage.current_request_count = len(current_requests)

            # Calcular solicitudes vencidas
            overdue = 0
            if stage.max_days_in_stage > 0:
                for request in current_requests:
                    if request.date_last_stage_update:
                        days_in_stage = (fields.Datetime.now() - request.date_last_stage_update).days
                        if days_in_stage > stage.max_days_in_stage:
                            overdue += 1
            stage.overdue_count = overdue

            # Calcular duración promedio usando el sistema de tracking
            all_requests = self.env['advance.request'].search([])
            total_duration = 0
            count = 0

            for request in all_requests:
                if hasattr(request, 'duration_tracking') and request.duration_tracking:
                    stage_duration = request.duration_tracking.get(str(stage.id), 0)
                    if stage_duration > 0:
                        total_duration += stage_duration
                        count += 1

            if count > 0:
                stage.avg_duration = (total_duration / count) / 3600  # Convertir segundos a horas
            else:
                # Fallback al sistema legacy si existe
                histories = self.env['advance.request.stage.history'].search([
                    ('stage_id', '=', stage.id),
                    ('duration', '>', 0)
                ])
                if histories:
                    stage.avg_duration = sum(histories.mapped('duration')) / len(histories)
                else:
                    stage.avg_duration = 0

            # Calcular tasa de éxito (solicitudes que pasan a siguiente etapa vs canceladas)
            completed_requests = self.env['advance.request'].search_count([
                ('stage_id', '>', stage.id)
            ])
            total_passed = completed_requests + stage.current_request_count

            if total_passed > 0:
                stage.success_rate = (completed_requests / total_passed) * 100
            else:
                stage.success_rate = 0

            # Calcular índice de cuello de botella
            # Basado en: tiempo promedio, solicitudes vencidas y cantidad actual
            bottleneck = 0

            # Factor 1: Duración promedio vs esperado
            if stage.max_days_in_stage > 0:
                duration_factor = min((stage.avg_duration / 24) / stage.max_days_in_stage, 1) * 40
                bottleneck += duration_factor

            # Factor 2: Porcentaje de vencidas
            if stage.current_request_count > 0:
                overdue_factor = (stage.overdue_count / stage.current_request_count) * 40
                bottleneck += overdue_factor

            # Factor 3: Acumulación de solicitudes
            avg_count = self.env['advance.request'].search_count([]) / len(self.search([]))
            if avg_count > 0:
                accumulation_factor = min(stage.current_request_count / avg_count, 2) * 20
                bottleneck += accumulation_factor

            stage.bottleneck_score = min(bottleneck, 100)


class AdvanceRequestStageHistory(models.Model):
    """Historial de cambios de etapa para solicitudes de anticipo"""
    _name = 'advance.request.stage.history'
    _description = 'Historial de Etapas de Solicitud de Anticipo'
    _order = 'enter_date desc'
    _rec_name = 'stage_id'

    request_id = fields.Many2one(
        'advance.request',
        string='Solicitud',
        required=True,
        ondelete='cascade',
        index=True
    )
    stage_id = fields.Many2one(
        'advance.request.stage',
        string='Etapa',
        required=True
    )
    enter_date = fields.Datetime(string='Fecha Entrada', required=True)
    exit_date = fields.Datetime(string='Fecha Salida')
    duration = fields.Float(string='Duración (horas)', help='Tiempo que duró en esta etapa')
    duration_formatted = fields.Char(string='Duración', compute='_compute_duration_formatted')
    user_id = fields.Many2one('res.users', string='Usuario', help='Usuario que realizó el cambio')

    @api.depends('duration')
    def _compute_duration_formatted(self):
        """Formatea la duración en un formato legible"""
        for record in self:
            if record.duration:
                hours = int(record.duration)
                minutes = int((record.duration - hours) * 60)
                if hours > 24:
                    days = hours // 24
                    hours = hours % 24
                    record.duration_formatted = f"{days}d {hours}h {minutes}m"
                elif hours > 0:
                    record.duration_formatted = f"{hours}h {minutes}m"
                else:
                    record.duration_formatted = f"{minutes}m"
            else:
                record.duration_formatted = '0m'