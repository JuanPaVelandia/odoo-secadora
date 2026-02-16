# -*- coding: utf-8 -*-

from odoo import models, fields, api


class AnalisisLab(models.Model):
    _name = 'secadora.analisis.lab'
    _inherit = ['mail.thread']
    _description = 'Análisis de Laboratorio'
    _order = 'name desc'

    # === Información básica ===
    name = fields.Char(
        string='Número',
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: 'Nuevo'
    )
    numero_talonario = fields.Char(
        string='No. Talonario',
        help='Número del talonario físico de laboratorio'
    )
    fecha_hora = fields.Datetime(
        string='Fecha/Hora',
        required=True,
        default=fields.Datetime.now
    )
    usuario_id = fields.Many2one(
        'res.users',
        string='Analista',
        default=lambda self: self.env.user,
        required=True
    )
    state = fields.Selection([
        ('borrador', 'Borrador'),
        ('confirmado', 'Confirmado'),
    ], string='Estado', default='borrador', required=True, index=True)

    # === Vínculos ===
    pesaje_id = fields.Many2one(
        'secadora.pesaje',
        string='Pesaje',
        index=True,
        help='Pesaje vinculado (opcional)'
    )
    orden_servicio_id = fields.Many2one(
        'secadora.orden.servicio',
        string='Orden de Servicio',
        index=True,
        help='Orden de servicio vinculada (opcional)'
    )
    tercero_id = fields.Many2one(
        'res.partner',
        string='Tercero (Agricultor/Cliente)',
        index=True
    )
    variedad_id = fields.Many2one(
        'secadora.variedad.arroz',
        string='Variedad de Arroz'
    )
    tipo_operacion_id = fields.Many2one(
        'secadora.tipo.operacion',
        string='Tipo de Operación'
    )
    origen_muestra_id = fields.Many2one(
        'secadora.origen.muestra',
        string='Origen de Muestra',
        index=True,
        help='Categoría del origen de la muestra'
    )
    origen_muestra_codigo = fields.Char(
        related='origen_muestra_id.codigo',
        string='Código Origen',
    )
    sitio_muestra_id = fields.Many2one(
        'secadora.sitio.muestra',
        string='Sitio de Muestra',
        index=True,
        domain="[('origen_id', '=', origen_muestra_id)]",
        help='Sitio específico donde se tomó la muestra'
    )
    finca_id = fields.Many2one(
        'secadora.lugar',
        string='Finca',
        domain="[('tipo', '=', 'finca')]",
        help='Finca de origen (cuando el origen de muestra es Cultivo)'
    )

    # === Parámetros principales ===
    humedad = fields.Float(string='Humedad (%)', digits=(5, 2))
    impurezas = fields.Float(string='Impurezas (%)', digits=(5, 2))
    grano_partido = fields.Float(string='Grano Partido (%)', digits=(5, 2))
    grano_partido_verde = fields.Float(string='Grano Partido Verde (%)', digits=(5, 2))
    grano_rojo = fields.Float(string='Grano Rojo (%)', digits=(5, 2))
    infestacion = fields.Float(string='Infestación', digits=(5, 2))
    dispersion = fields.Float(string='Dispersión', digits=(5, 2))
    merma_estufa = fields.Float(string='Merma en Estufa', digits=(5, 2))

    # === Arroz integral ===
    integral_pct = fields.Float(string='Integral (%)', digits=(5, 2))
    cascarilla_pct = fields.Float(string='Cascarilla (%)', digits=(5, 2))
    grano_partido_integral_pct = fields.Float(string='Grano Partido Integral (%)', digits=(5, 2))
    rendimiento_pilada_pct = fields.Float(string='Rendimiento Pilada (%)', digits=(5, 2))

    # === Molinería ===
    harina_pct = fields.Float(string='Harina (%)', digits=(5, 2))
    grano_partido_blanco_pct = fields.Float(string='Grano Partido Blanco (%)', digits=(5, 2))
    indice_pilada_pct = fields.Float(string='Índice de Pilada (%)', digits=(5, 2))
    blancura_kett = fields.Float(string='Blancura (kett)', digits=(5, 2))
    transparencia = fields.Float(string='Transparencia', digits=(5, 2))
    grado_pulimento = fields.Float(string='Grado Pulimento', digits=(5, 2))
    grano_yesado_pct = fields.Float(string='Grano Yesado (%)', digits=(5, 2))
    grano_ambarino_pct = fields.Float(string='Grano Ambarino (%)', digits=(5, 2))
    grano_con_dano_pct = fields.Float(string='Grano con Daño (%)', digits=(5, 2))

    # === Otro ===
    otro = fields.Text(string='Comentarios')

    # === Campos computados de peso ===
    peso_neto_pesaje = fields.Float(
        string='Peso Neto del Pesaje (kg)',
        related='pesaje_id.peso_neto',
        readonly=True,
        digits=(12, 2)
    )

    peso_comercial = fields.Float(
        string='Peso Comercial (kg)',
        compute='_compute_peso_comercial',
        store=True,
        digits=(12, 2),
        help='Pc = Pb × ((100 - Hr) / (100 - He)) × ((100 - Ir) / (100 - Ie))'
    )

    diferencia_peso = fields.Float(
        string='Diferencia (kg)',
        compute='_compute_peso_comercial',
        store=True,
        digits=(12, 2),
        help='Peso neto - Peso comercial (kg descontados por humedad e impurezas)'
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('secadora.analisis.lab') or 'Nuevo'
        return super().create(vals_list)

    @api.onchange('origen_muestra_id')
    def _onchange_origen_muestra_id(self):
        """Limpiar sitio cuando cambia el origen"""
        if self.sitio_muestra_id and self.sitio_muestra_id.origen_id != self.origen_muestra_id:
            self.sitio_muestra_id = False

    @api.onchange('pesaje_id')
    def _onchange_pesaje_id(self):
        """Auto-llenar campos cuando se selecciona un pesaje"""
        if self.pesaje_id:
            self.tercero_id = self.pesaje_id.tercero_id
            self.variedad_id = self.pesaje_id.variedad_id
            self.tipo_operacion_id = self.pesaje_id.tipo_operacion_id
            if self.pesaje_id.orden_servicio_id:
                self.orden_servicio_id = self.pesaje_id.orden_servicio_id

    @api.depends('pesaje_id.peso_neto', 'humedad', 'impurezas')
    def _compute_peso_comercial(self):
        """Pc = Pb × ((100 - Hr) / (100 - He)) × ((100 - Ir) / (100 - Ie))"""
        ICP = self.env['ir.config_parameter'].sudo()
        activar = ICP.get_param('calidad.activar_peso_comercial', 'True')
        humedad_base = float(ICP.get_param('calidad.humedad_base', '13.0'))
        impurezas_base = float(ICP.get_param('calidad.impurezas_base', '3.0'))

        for record in self:
            if activar != 'True' or not record.pesaje_id:
                record.peso_comercial = 0.0
                record.diferencia_peso = 0.0
                continue

            peso_neto = record.pesaje_id.peso_neto
            if peso_neto <= 0 or (100.0 - humedad_base) <= 0 or (100.0 - impurezas_base) <= 0:
                record.peso_comercial = 0.0
                record.diferencia_peso = 0.0
                continue

            factor_humedad = (100.0 - (record.humedad or 0.0)) / (100.0 - humedad_base)
            factor_impurezas = (100.0 - (record.impurezas or 0.0)) / (100.0 - impurezas_base)
            record.peso_comercial = peso_neto * factor_humedad * factor_impurezas
            record.diferencia_peso = peso_neto - record.peso_comercial

    def action_confirmar(self):
        for record in self:
            record.state = 'confirmado'

    def action_borrador(self):
        for record in self:
            record.state = 'borrador'
