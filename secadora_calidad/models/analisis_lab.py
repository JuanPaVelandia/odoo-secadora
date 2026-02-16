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
        help='Peso neto ajustado por descuentos de calidad',
    )

    diferencia_peso = fields.Float(
        string='Diferencia (kg)',
        compute='_compute_peso_comercial',
        store=True,
        digits=(12, 2),
        help='Peso neto - Peso comercial (kg descontados)',
    )

    detalle_descuento = fields.Text(
        string='Detalle del Descuento',
        compute='_compute_peso_comercial',
        store=True,
        help='Desglose paso a paso del cálculo de peso comercial',
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

    @api.depends(
        'pesaje_id.peso_neto', 'pesaje_id.tipo_operacion_id', 'pesaje_id.producto_id',
        'tipo_operacion_id',
        'humedad', 'impurezas', 'grano_partido', 'grano_partido_verde',
        'grano_rojo', 'infestacion', 'cascarilla_pct', 'harina_pct',
        'grano_yesado_pct', 'grano_ambarino_pct', 'grano_con_dano_pct',
    )
    def _compute_peso_comercial(self):
        ICP = self.env['ir.config_parameter'].sudo()
        activar = ICP.get_param('calidad.activar_peso_comercial', 'True')
        Descuento = self.env['secadora.descuento.calidad']

        for record in self:
            if activar != 'True' or not record.pesaje_id:
                record.peso_comercial = 0.0
                record.diferencia_peso = 0.0
                record.detalle_descuento = ''
                continue

            peso_neto = record.pesaje_id.peso_neto
            if peso_neto <= 0:
                record.peso_comercial = 0.0
                record.diferencia_peso = 0.0
                record.detalle_descuento = ''
                continue

            tipo_op = record.tipo_operacion_id or record.pesaje_id.tipo_operacion_id
            producto = record.pesaje_id.producto_id

            if not tipo_op:
                record.peso_comercial = peso_neto
                record.diferencia_peso = 0.0
                record.detalle_descuento = 'Sin tipo de operación — sin descuentos'
                continue

            # Buscar reglas: producto específico + genéricas
            domain = [
                ('tipo_operacion_id', '=', tipo_op.id),
                ('active', '=', True),
            ]
            todas_reglas = Descuento.search(domain)

            # Para cada parámetro, elegir la regla más específica
            reglas_a_aplicar = {}
            for regla in todas_reglas:
                param = regla.parametro
                if regla.producto_id and producto and regla.producto_id == producto:
                    # Producto específico: siempre tiene prioridad
                    reglas_a_aplicar[param] = regla
                elif not regla.producto_id:
                    # Genérica: solo si no hay específica ya asignada
                    if param not in reglas_a_aplicar or not reglas_a_aplicar[param].producto_id:
                        reglas_a_aplicar[param] = regla

            factores = []
            kg_descuentos = []
            detalles = []
            detalles.append(f"Peso neto: {peso_neto:.2f} kg")
            detalles.append(f"Tipo operación: {tipo_op.name}")
            if producto:
                detalles.append(f"Producto: {producto.display_name}")
            detalles.append("---")

            for regla in sorted(reglas_a_aplicar.values(), key=lambda r: r.sequence):
                resultado = regla.calcular_descuento(record)
                if not resultado['detalle']:
                    continue
                if resultado['tipo'] == 'factor':
                    factores.append(resultado['valor'])
                    detalles.append(f"× {resultado['detalle']}")
                elif resultado['tipo'] == 'kg':
                    kg_descuentos.append(resultado['valor'])
                    detalles.append(f"- {resultado['detalle']}")

            # peso_comercial = peso_neto × (∏ factores) - (∑ kg)
            producto_factores = 1.0
            for f in factores:
                producto_factores *= f

            suma_kg = sum(kg_descuentos)

            peso_comercial = peso_neto * producto_factores - suma_kg

            if factores or kg_descuentos:
                detalles.append("---")
                if factores:
                    detalles.append(
                        f"Factor total: {' × '.join(f'{f:.6f}' for f in factores)} = {producto_factores:.6f}"
                    )
                detalles.append(
                    f"Peso comercial: {peso_neto:.2f} × {producto_factores:.6f}"
                    + (f" - {suma_kg:.2f}" if suma_kg else "")
                    + f" = {peso_comercial:.2f} kg"
                )
            else:
                detalles.append("Sin descuentos aplicables")

            record.peso_comercial = peso_comercial
            record.diferencia_peso = peso_neto - peso_comercial
            record.detalle_descuento = '\n'.join(detalles)

    def action_confirmar(self):
        for record in self:
            record.state = 'confirmado'

    def action_borrador(self):
        for record in self:
            record.state = 'borrador'
