# -*- coding: utf-8 -*-

from collections import Counter, defaultdict

from odoo import models, fields, api
from odoo.exceptions import UserError


class SecadoraFlete(models.Model):
    _name = 'secadora.flete'
    _description = 'Flete de Transporte'
    _inherit = ['mail.thread']
    _order = 'fecha desc, id desc'
    _pesaje_unico = models.Constraint(
        'UNIQUE(pesaje_id)',
        'Este pesaje ya tiene un flete asociado. Un pesaje solo puede tener un flete.',
    )
    _peso_kg_positivo = models.Constraint(
        'CHECK(peso_kg >= 0)',
        'El peso del flete no puede ser negativo.',
    )
    _costo_total_positivo = models.Constraint(
        'CHECK(costo_total >= 0)',
        'El costo total del flete no puede ser negativo.',
    )

    name = fields.Char(
        string='Número',
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: 'Nuevo',
    )

    company_id = fields.Many2one(
        'res.company',
        string='Empresa que Paga',
        required=True,
        default=lambda self: self.env.company,
        index=True,
        tracking=True,
        help='Empresa responsable del pago del flete',
    )

    fecha = fields.Date(
        string='Fecha',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )

    # ==================== TERCERO ====================

    tercero_id = fields.Many2one(
        'res.partner',
        string='Tercero (Agricultor)',
        index=True,
        tracking=True,
        help='Agricultor o cliente responsable del flete',
    )
    pago_flete = fields.Selection([
        ('agricultor', 'Agricultor paga directo'),
        ('secadora', 'Secadora paga y descuenta'),
    ], string='Modalidad de Pago', default='agricultor',
       tracking=True,
       help='Quién asume el costo del flete')

    # ==================== RUTA ====================

    origen_id = fields.Many2one(
        'secadora.lugar',
        string='Origen',
        help='Lugar de origen del flete',
    )
    destino_id = fields.Many2one(
        'secadora.lugar',
        string='Destino',
        help='Lugar de destino del flete',
    )
    empresa_origen_id = fields.Many2one(
        'res.company',
        string='Empresa Origen',
        index=True,
        help='Empresa propietaria del lugar de origen (para visibilidad cross-company)',
    )
    empresa_destino_id = fields.Many2one(
        'res.company',
        string='Empresa Destino',
        index=True,
        help='Empresa propietaria del lugar de destino (para visibilidad cross-company)',
    )

    # ==================== TRANSPORTE ====================

    vehiculo_id = fields.Many2one(
        'secadora.vehiculo',
        string='Vehículo',
        required=True,
        tracking=True,
    )
    placa_texto = fields.Char(
        related='vehiculo_id.placa',
        string='Placa',
        store=True,
        readonly=True,
    )
    conductor_id = fields.Many2one(
        'secadora.conductor',
        string='Conductor',
    )
    transportadora_id = fields.Many2one(
        'secadora.transportadora',
        string='Transportadora',
    )

    # ==================== CARGA ====================

    producto_id = fields.Many2one(
        'product.product',
        string='Producto',
        domain=[('type', '=', 'consu')],
    )
    variedad_id = fields.Many2one(
        'secadora.variedad.arroz',
        string='Variedad',
    )
    peso_kg = fields.Float(
        string='Peso (Kg)',
        digits=(12, 2),
    )
    bultos = fields.Integer(
        string='Bultos',
    )
    humedad = fields.Float(
        string='Humedad (%)',
        digits=(5, 2),
    )
    impurezas = fields.Float(
        string='Impurezas (%)',
        digits=(5, 2),
    )

    # ==================== VÍNCULO ====================

    pesaje_id = fields.Many2one(
        'secadora.pesaje',
        string='Pesaje',
        index=True,
        help='Pesaje vinculado a este flete',
    )

    orden_servicio_id = fields.Many2one(
        'secadora.orden.servicio',
        string='Orden de Servicio',
        related='pesaje_id.orden_servicio_id',
        store=True,
        readonly=True,
    )

    pesaje_direccion = fields.Selection(
        related='pesaje_id.direccion',
        string='Dirección Pesaje',
    )

    # ==================== COSTOS ====================

    tarifa_id = fields.Many2one(
        'secadora.tarifa.flete',
        string='Tarifa Aplicada',
        help='Tarifa del catálogo. Se aplica automáticamente según origen/destino, o se puede seleccionar manualmente.',
    )

    tarifa_tipo = fields.Selection([
        ('por_kg', 'Por Kilogramo'),
        ('por_viaje', 'Por Viaje'),
        ('por_bulto', 'Por Bulto'),
    ], string='Tipo de Tarifa', default='por_kg')

    tarifa_unitaria = fields.Float(
        string='Tarifa Unitaria',
        digits='Product Price',
    )

    costo_total = fields.Float(
        string='Costo Total',
        compute='_compute_costo_total',
        store=True,
        digits='Product Price',
    )

    valor_adicional = fields.Float(
        string='Valor Adicional',
        digits='Product Price',
    )
    razon_adicional = fields.Char(
        string='Razón del Valor Adicional',
    )

    # ==================== PESO DESTINO ====================

    peso_destino_kg = fields.Float(
        string='Peso en Destino (Kg)',
        digits=(12, 2),
        help='Peso registrado en el tiquete del destino (ej: molino). Si se llena, el costo se calcula con este peso.',
    )
    usar_peso_destino = fields.Boolean(
        string='Usar Peso Destino para Costo',
        help='Si está marcado, el costo total se calcula con el peso del destino en vez del peso de la secadora.',
    )
    tiquete_destino = fields.Binary(
        string='Tiquete de Destino',
        help='Foto o PDF del tiquete de recibo en el destino.',
    )
    tiquete_destino_nombre = fields.Char(
        string='Nombre del Tiquete',
    )

    factura_transportadora_id = fields.Many2one(
        'account.move',
        string='Factura Transportadora',
        domain="[('move_type', '=', 'in_invoice'), ('state', '!=', 'cancel')]",
        tracking=True,
        copy=False,
    )
    factura_domain = fields.Binary(
        string='Dominio Factura Transportadora',
        compute='_compute_factura_domain',
        help='Filtra las facturas candidatas por el NIT de la transportadora '
             'y la empresa que paga, excluyendo las ya asociadas a otro flete.',
    )

    # Almacenados (store=True) a propósito: el filtro "Facturados por pagar"
    # busca sobre estos campos, y un related NO almacenado expande la búsqueda
    # a una subconsulta sobre account.move con las ACL del usuario — los
    # usuarios de transporte sin permisos contables recibirían AccessError.
    # Almacenados, la búsqueda queda sobre la tabla de fletes.
    factura_estado = fields.Selection(
        related='factura_transportadora_id.state',
        string='Estado Factura',
        store=True,
    )
    factura_estado_pago = fields.Selection(
        related='factura_transportadora_id.payment_state',
        string='Estado de Pago',
        store=True,
    )
    factura_saldo = fields.Monetary(
        related='factura_transportadora_id.amount_residual',
        string='Saldo Factura',
        currency_field='factura_currency_id',
    )
    factura_currency_id = fields.Many2one(
        related='factura_transportadora_id.currency_id',
        string='Moneda Factura',
    )

    # ==================== ESTADO ====================

    state = fields.Selection([
        ('borrador', 'Borrador'),
        ('confirmado', 'Confirmado'),
        ('en_ruta', 'En Ruta'),
        ('entregado', 'Entregado'),
        ('liquidado', 'Liquidado'),
        ('facturado', 'Facturado'),
        ('cancelado', 'Cancelado'),
    ], string='Estado', default='borrador', required=True, tracking=True, index=True)

    observaciones = fields.Text(string='Observaciones')

    # ==================== COMPUTED ====================

    @api.depends('tarifa_tipo', 'tarifa_unitaria', 'peso_kg', 'bultos',
                 'peso_destino_kg', 'usar_peso_destino', 'valor_adicional')
    def _compute_costo_total(self):
        for rec in self:
            peso = rec.peso_destino_kg if rec.usar_peso_destino and rec.peso_destino_kg else rec.peso_kg
            if rec.tarifa_tipo == 'por_kg':
                base = rec.tarifa_unitaria * peso
            elif rec.tarifa_tipo == 'por_bulto':
                base = rec.tarifa_unitaria * rec.bultos
            elif rec.tarifa_tipo == 'por_viaje':
                base = rec.tarifa_unitaria
            else:
                base = 0.0
            rec.costo_total = base + (rec.valor_adicional or 0.0)

    # ==================== FACTURAS ASOCIABLES ====================

    @api.model
    def _facturas_asociables_domain(self, partner, company, excluir_fletes=None):
        """Dominio de facturas de proveedor candidatas a asociarse a fletes.

        Fuente única del filtro que usan el campo del formulario de flete y
        el wizard "Asociar a Factura": facturas de proveedor no canceladas,
        no asociadas ya a otro flete, del NIT del contacto de la
        transportadora (si lo hay — así aparece cualquier factura cuyo
        proveedor tenga el mismo NIT aunque sea otro registro de contacto)
        y de la empresa que paga (si se conoce).

        excluir_fletes: fletes cuya factura actual NO debe descartarse
        (p.ej. el propio flete al editarlo, para que su factura asignada
        siga siendo seleccionable).

        La búsqueda se hace sobre TODAS las compañías del usuario y se fija
        el resultado como dominio por id, para saltar el filtro de la
        compañía activa sin exponer compañías fuera de su alcance.
        """
        fletes_con_factura = self.search([('factura_transportadora_id', '!=', False)])
        if excluir_fletes:
            fletes_con_factura -= excluir_fletes
        facturas_usadas_ids = fletes_con_factura.mapped('factura_transportadora_id').ids

        search_domain = [
            ('move_type', '=', 'in_invoice'),
            ('state', '!=', 'cancel'),
        ]
        if facturas_usadas_ids:
            search_domain.append(('id', 'not in', facturas_usadas_ids))
        nit = partner.vat if partner else False
        if nit:
            search_domain.append(('partner_id.vat', '=', nit))
        if company:
            search_domain.append(('company_id', '=', company.id))

        facturas = self.env['account.move'].with_context(
            allowed_company_ids=self.env.user.company_ids.ids,
        ).search(search_domain)
        return [('id', 'in', facturas.ids)]

    @api.depends('transportadora_id', 'company_id')
    def _compute_factura_domain(self):
        for rec in self:
            rec.factura_domain = self._facturas_asociables_domain(
                rec.transportadora_id.partner_id,
                rec.company_id,
                excluir_fletes=rec._origin,
            )

    # ==================== ONCHANGE ====================

    @api.model
    def _buscar_tarifa(self, origen_id, destino_id):
        """Busca tarifa activa para el par origen→destino."""
        if not origen_id or not destino_id:
            return False
        return self.env['secadora.tarifa.flete'].search([
            ('origen_id', '=', origen_id),
            ('destino_id', '=', destino_id),
            ('active', '=', True),
        ], limit=1)

    def _aplicar_tarifa(self):
        """Aplica tarifa encontrada a los campos del flete."""
        tarifa = self._buscar_tarifa(self.origen_id.id, self.destino_id.id)
        if tarifa:
            self.tarifa_id = tarifa
            self.tarifa_tipo = tarifa.tarifa_tipo
            self.tarifa_unitaria = tarifa.tarifa_unitaria

    @api.onchange('origen_id')
    def _onchange_origen_id(self):
        if self.origen_id and self.origen_id.company_id:
            self.empresa_origen_id = self.origen_id.company_id
        if self.origen_id and self.destino_id:
            self._aplicar_tarifa()

    @api.onchange('destino_id')
    def _onchange_destino_id(self):
        if self.destino_id and self.destino_id.company_id:
            self.empresa_destino_id = self.destino_id.company_id
        if self.origen_id and self.destino_id:
            self._aplicar_tarifa()

    @api.onchange('tarifa_id')
    def _onchange_tarifa_id(self):
        """Actualizar tipo y unitaria cuando se selecciona/cambia tarifa manualmente."""
        if self.tarifa_id:
            self.tarifa_tipo = self.tarifa_id.tarifa_tipo
            self.tarifa_unitaria = self.tarifa_id.tarifa_unitaria

    @api.onchange('vehiculo_id')
    def _onchange_vehiculo_id(self):
        if self.vehiculo_id:
            if self.vehiculo_id.conductor_habitual_id:
                self.conductor_id = self.vehiculo_id.conductor_habitual_id
            if self.vehiculo_id.transportadora_id:
                self.transportadora_id = self.vehiculo_id.transportadora_id

    @api.onchange('tercero_id')
    def _onchange_tercero_id(self):
        if self.tercero_id:
            # "Quién paga" lo lleva pago_flete (agricultor/secadora), NO
            # company_id. company_id es la propiedad del registro (la operadora)
            # y se deja en su default; asignarle la compañía del agricultor
            # rompía la regla multi-compañía (AccessError al leer/imprimir).
            self.pago_flete = self.tercero_id.flete_pago or 'agricultor'

    @api.onchange('pesaje_id')
    def _onchange_pesaje_id(self):
        if self.pesaje_id:
            self.vehiculo_id = self.pesaje_id.vehiculo_id
            self.conductor_id = self.pesaje_id.conductor_id
            self.transportadora_id = self.pesaje_id.transportadora_id
            self.producto_id = self.pesaje_id.producto_id
            self.variedad_id = self.pesaje_id.variedad_id
            if self.pesaje_id.peso_neto:
                self.peso_kg = self.pesaje_id.peso_neto
            self.bultos = self.pesaje_id.bultos
            self.humedad = self.pesaje_id.humedad
            self.impurezas = self.pesaje_id.impurezas
            if self.pesaje_id.origen_id:
                self.origen_id = self.pesaje_id.origen_id
            if self.pesaje_id.destino_id:
                self.destino_id = self.pesaje_id.destino_id
            if self.pesaje_id.tercero_id:
                self.tercero_id = self.pesaje_id.tercero_id
                self.pago_flete = self.pesaje_id.tercero_id.flete_pago or 'agricultor'
            if self.pesaje_id.empresa_arroz_id:
                self.company_id = self.pesaje_id.empresa_arroz_id

    # ==================== CRUD ====================

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('secadora.flete') or 'Nuevo'
            # Auto-aplicar tarifa si no viene tarifa_unitaria
            if not vals.get('tarifa_unitaria') and vals.get('origen_id') and vals.get('destino_id'):
                tarifa = self._buscar_tarifa(vals['origen_id'], vals['destino_id'])
                if tarifa:
                    vals['tarifa_id'] = tarifa.id
                    vals['tarifa_tipo'] = tarifa.tarifa_tipo
                    vals['tarifa_unitaria'] = tarifa.tarifa_unitaria
        return super().create(vals_list)

    def unlink(self):
        for rec in self:
            if rec.state not in ('borrador', 'cancelado'):
                raise UserError(
                    f'No se puede eliminar el flete {rec.name} en estado '
                    f'"{dict(self._fields["state"].selection).get(rec.state, rec.state)}". '
                    f'Solo se pueden eliminar fletes en borrador o cancelados.'
                )
        return super().unlink()

    # ==================== ACCIONES ====================

    def action_confirmar(self):
        for rec in self:
            if rec.state != 'borrador':
                raise UserError('Solo se pueden confirmar fletes en borrador.')
            rec.state = 'confirmado'

    def action_en_ruta(self):
        for rec in self:
            if rec.state != 'confirmado':
                raise UserError('Solo se pueden poner en ruta fletes confirmados.')
            rec.state = 'en_ruta'

    def action_entregar(self):
        for rec in self:
            if rec.state not in ('confirmado', 'en_ruta'):
                raise UserError('Solo se pueden entregar fletes confirmados o en ruta.')
            rec.state = 'entregado'

    def action_liquidar(self):
        for rec in self:
            if rec.state != 'entregado':
                raise UserError('Solo se pueden liquidar fletes entregados.')
            rec.state = 'liquidado'

    def action_facturar(self):
        for rec in self:
            if rec.state != 'liquidado':
                raise UserError('Solo se pueden facturar fletes liquidados.')
            if not rec.factura_transportadora_id:
                raise UserError(f'El flete {rec.name} no tiene factura de transportadora asociada.')
            if rec.factura_transportadora_id.state == 'cancel':
                raise UserError(
                    f'La factura {rec.factura_transportadora_id.name} asociada al flete '
                    f'{rec.name} está cancelada. Asocie una factura válida.'
                )
            rec.state = 'facturado'

    def action_cancelar(self):
        for rec in self:
            if rec.state in ('liquidado', 'facturado'):
                raise UserError('No se puede cancelar un flete liquidado o facturado.')
            rec.state = 'cancelado'

    def action_borrador(self):
        for rec in self:
            if rec.state != 'cancelado':
                raise UserError('Solo se puede volver a borrador desde cancelado.')
            rec.state = 'borrador'

    def action_ver_factura(self):
        self.ensure_one()
        if not self.factura_transportadora_id:
            raise UserError('Este flete no tiene factura de transportadora asociada.')
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.factura_transportadora_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ==================== TABLERO DE TRANSPORTE ====================

    @api.model
    def _domain_tablero(self, filtros):
        """Dominio de fletes según los filtros del tablero/wizard. Fuente
        única: el tablero, el wizard de impresión y el drill-down "Ver
        fletes" del frontend usan este mismo dominio."""
        domain = [('state', '!=', 'cancelado')]
        if filtros.get('fecha_desde'):
            domain.append(('fecha', '>=', filtros['fecha_desde']))
        if filtros.get('fecha_hasta'):
            domain.append(('fecha', '<=', filtros['fecha_hasta']))
        if filtros.get('transportadora_id'):
            domain.append(('transportadora_id', '=', int(filtros['transportadora_id'])))
        if filtros.get('company_id'):
            domain.append(('company_id', '=', int(filtros['company_id'])))
        if filtros.get('pago_flete') in ('secadora', 'agricultor'):
            domain.append(('pago_flete', '=', filtros['pago_flete']))
        return domain

    @api.model
    def get_tablero_transporte_data(self, filtros=None):
        """Datos agregados para el tablero de gestión de transporte.

        filtros: dict opcional con fecha_desde/fecha_hasta ('YYYY-MM-DD'),
        transportadora_id (int), company_id (int) y pago_flete
        ('todos'/'secadora'/'agricultor').

        Semántica:
        - Viaje: flete no cancelado.
        - Facturado: con factura asociada Y publicada (posted). Las facturas
          en borrador se cuentan aparte (viajes_factura_borrador); las
          canceladas no cuentan como facturadas ni como borrador.
        - Pagado: factura con payment_state paid/in_payment.
        - Saldo: amount_residual sumado SOLO sobre facturas distintas por
          pagar (ver account.move.es_por_pagar). Varios fletes comparten
          factura: sumar el residual por flete o por placa lo duplicaría.

        A nivel placa las cifras se expresan en valor de flete (costo_total);
        el saldo por pagar es contable y solo existe a nivel transportadora
        y totales.

        Alcance: compañías activas de la sesión — las mismas que verá el
        usuario al abrir listas desde el tablero, para que los conteos del
        tablero y el drill-down coincidan.
        """
        filtros = filtros or {}
        fletes = self.search(self._domain_tablero(filtros))

        # sudo acotado: solo se leen facturas ya referenciadas por fletes a
        # los que el usuario tiene acceso, para que usuarios de transporte
        # sin permisos contables vean estado y saldo.
        facturas = fletes.mapped('factura_transportadora_id').sudo()
        etiquetas_pago = dict(
            self.env['account.move']._fields['payment_state']
            ._description_selection(self.env)
        )
        info_facturas = {}
        for f in facturas:
            if f.state == 'posted':
                etiqueta = etiquetas_pago.get(f.payment_state, f.payment_state or '')
            elif f.state == 'cancel':
                etiqueta = 'Cancelada'
            else:
                etiqueta = 'Borrador'
            info_facturas[f.id] = {
                'name': f.name,
                'ref': f.ref or '',
                'fecha': str(f.invoice_date) if f.invoice_date else '',
                'estado': f.state,
                'estado_pago_raw': f.payment_state or 'not_paid',
                'estado_pago': etiqueta,
                'total': f.amount_total,
                'saldo': f.amount_residual if f.state == 'posted' else 0.0,
                'por_pagar': f.es_por_pagar(),
                'pagada': f.state == 'posted'
                and f.payment_state in ('paid', 'in_payment'),
            }

        def _info(flete):
            return info_facturas.get(flete.factura_transportadora_id.id)

        def _stats(grupo):
            """Agregados de una lista de fletes, en valor de flete."""
            stats = {
                'viajes': len(grupo),
                'valor_fletes': 0.0,
                'viajes_facturados': 0,
                'valor_facturado': 0.0,
                'viajes_pagados': 0,
                'valor_pagado': 0.0,
                'viajes_sin_facturar': 0,
                'valor_sin_facturar': 0.0,
                'viajes_factura_borrador': 0,
            }
            for x in grupo:
                info = _info(x)
                stats['valor_fletes'] += x.costo_total
                if info and info['estado'] == 'posted':
                    stats['viajes_facturados'] += 1
                    stats['valor_facturado'] += x.costo_total
                    if info['pagada']:
                        stats['viajes_pagados'] += 1
                        stats['valor_pagado'] += x.costo_total
                elif info and info['estado'] == 'draft':
                    stats['viajes_factura_borrador'] += 1
                else:
                    # Sin factura, o con factura cancelada (que en la práctica
                    # significa que hay que volver a facturar el viaje).
                    stats['viajes_sin_facturar'] += 1
                    stats['valor_sin_facturar'] += x.costo_total
            return stats

        def _bloque(grupo):
            """Bloque completo de una transportadora (o del grupo sin
            transportadora): stats + desglose por placa + facturas."""
            stats = _stats(grupo)

            por_placa = defaultdict(list)
            for x in grupo:
                por_placa[x.placa_texto or ''].append(x)
            stats['placas'] = [
                {'placa': placa or '(sin placa)', **_stats(sub)}
                for placa, sub in sorted(por_placa.items())
            ]

            conteo_fletes = Counter(
                x.factura_transportadora_id.id for x in grupo
                if x.factura_transportadora_id
            )
            detalle_facturas = []
            saldo_por_pagar = 0.0
            facturas_por_pagar = 0
            for factura_id, num_fletes in conteo_fletes.items():
                info = info_facturas[factura_id]
                if info['por_pagar']:
                    saldo_por_pagar += info['saldo']
                    facturas_por_pagar += 1
                detalle_facturas.append({
                    'id': factura_id,
                    'num_fletes': num_fletes,
                    **{k: info[k] for k in (
                        'name', 'ref', 'fecha', 'estado',
                        'estado_pago', 'estado_pago_raw', 'total', 'saldo',
                    )},
                })
            detalle_facturas.sort(key=lambda d: d['fecha'], reverse=True)
            stats['facturas'] = detalle_facturas
            stats['saldo_por_pagar'] = saldo_por_pagar
            stats['facturas_por_pagar'] = facturas_por_pagar
            return stats

        # Agrupar por transportadora en una sola pasada. Los fletes sin
        # transportadora entran como un grupo más con id 0.
        por_transportadora = defaultdict(list)
        for x in fletes:
            por_transportadora[x.transportadora_id.id or 0].append(x)

        # sudo acotado también aquí: las ACL de secadora.transportadora
        # viven en bascula (grupo basculero) y un usuario de solo transporte
        # no puede leer el catálogo, pero sí debe ver nombre y NIT de las
        # transportadoras de sus propios fletes.
        catalogo = {
            t.id: t for t in fletes.mapped('transportadora_id').sudo()
        }
        transportadoras = []
        orden = sorted(
            (tid for tid in por_transportadora if tid),
            key=lambda tid: catalogo[tid].name or '',
        )
        for tid in orden:
            transportadoras.append({
                'id': tid,
                'name': catalogo[tid].name,
                'nit': catalogo[tid].nit or '',
                **_bloque(por_transportadora[tid]),
            })
        if 0 in por_transportadora:
            transportadoras.append({
                'id': 0,
                'name': 'Sin transportadora asignada',
                'nit': '',
                **_bloque(por_transportadora[0]),
            })

        totales = _bloque(list(fletes))
        # El detalle por placa/factura no se muestra a nivel global.
        totales.pop('placas')
        totales.pop('facturas')

        return {
            'transportadoras': transportadoras,
            'totales': totales,
            'domain_fletes': self._domain_tablero(filtros),
            # El wizard de impresión requiere leer account.move: solo tiene
            # sentido para el rol pagador (mismo gate que el menú).
            'puede_imprimir': self.env.user.has_group('account.group_account_invoice'),
            'opciones': {
                'transportadoras': [
                    {'id': t.id, 'name': t.name}
                    for t in self.env['secadora.transportadora'].sudo().search([])
                ],
                'companias': [
                    {'id': c.id, 'name': c.name}
                    for c in self.env.companies
                ],
            },
        }
