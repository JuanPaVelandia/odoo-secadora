# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError


class PosicionArroz(models.Model):
    _name = 'secadora.posicion.arroz'
    _description = 'Posición de Arroz en Planta'
    _inherit = ['mail.thread']
    _order = 'fecha_movimiento desc, id desc'
    _sql_constraints = [
        ('peso_kg_positivo', 'CHECK(peso_kg >= 0)',
         'El peso de la posición no puede ser negativo.'),
    ]

    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    name = fields.Char(
        string='Referencia',
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: 'Nuevo',
    )
    pesaje_id = fields.Many2one(
        'secadora.pesaje',
        string='Pesaje',
        required=True,
        ondelete='restrict',
        index=True,
        tracking=True,
    )
    sitio_id = fields.Many2one(
        'secadora.sitio.muestra',
        string='Ubicación',
        domain=[('es_contenedor', '=', True)],
        group_expand='_read_group_sitio_ids',
        index=True,
        tracking=True,
    )
    peso_kg = fields.Float(
        string='Peso (Kg)',
        digits=(12, 2),
        tracking=True,
    )
    peso_original = fields.Float(
        string='Peso Original (Kg)',
        digits=(12, 2),
        readonly=True,
        help='Peso neto original del pesaje',
    )
    fecha_ingreso = fields.Datetime(
        string='Fecha Ingreso',
        default=fields.Datetime.now,
        readonly=True,
    )
    fecha_movimiento = fields.Datetime(
        string='Último Movimiento',
        default=fields.Datetime.now,
    )
    state = fields.Selection([
        ('activo', 'Activo'),
        ('combinado', 'Combinado'),
        ('despachado', 'Despachado'),
        ('retirado', 'Retirado'),
    ], string='Estado', default='activo', required=True, tracking=True, index=True)

    # Relaciones de combinación
    posicion_combinada_id = fields.Many2one(
        'secadora.posicion.arroz',
        string='Posición Combinada',
        readonly=True,
        help='Posición resultado de la combinación',
    )
    posicion_origen_combinacion_ids = fields.One2many(
        'secadora.posicion.arroz',
        'posicion_combinada_id',
        string='Posiciones Origen (Combinación)',
    )

    permite_combinar = fields.Boolean(
        string='Permite Combinar',
        compute='_compute_permite_combinar',
        store=True,
    )

    es_preasignado = fields.Boolean(
        string='Pre-asignado (En Tránsito)',
        default=False,
        help='Posición creada desde el tablero cuando el vehículo aún está en tránsito. El peso se actualizará al completar el pesaje.',
    )

    # Relaciones de división
    posicion_origen_id = fields.Many2one(
        'secadora.posicion.arroz',
        string='Posición Origen',
        readonly=True,
        index=True,
        help='Posición de la cual fue dividida',
    )
    posicion_hija_ids = fields.One2many(
        'secadora.posicion.arroz',
        'posicion_origen_id',
        string='Posiciones Derivadas',
    )

    @api.constrains('posicion_origen_id')
    def _check_posicion_origen_no_circular(self):
        """Prevenir referencias circulares en posicion_origen_id."""
        for rec in self:
            if not rec.posicion_origen_id:
                continue
            visited = {rec.id}
            current = rec.posicion_origen_id
            while current:
                if current.id in visited:
                    raise UserError(
                        'Referencia circular detectada en posición origen. '
                        'Una posición no puede referenciarse a sí misma directa o indirectamente.'
                    )
                visited.add(current.id)
                current = current.posicion_origen_id

    es_comercial = fields.Boolean(
        string='Es Comercial',
        default=False,
        help='Posición resultado de combinación o derivada de una. Se muestra como "Comercial" en el tablero.',
    )

    humedad = fields.Float(
        string='Humedad (%)',
        digits=(5, 2),
    )
    impurezas = fields.Float(
        string='Impurezas (%)',
        digits=(5, 2),
    )

    notas = fields.Text(string='Notas')

    # Historial
    movimiento_ids = fields.One2many(
        'secadora.movimiento.arroz',
        'posicion_id',
        string='Historial de Movimientos',
    )

    # Campos related del pesaje (stored para búsqueda y kanban)
    tercero_id = fields.Many2one(
        related='pesaje_id.tercero_id',
        store=True,
        string='Tercero',
    )
    producto_id = fields.Many2one(
        related='pesaje_id.producto_id',
        store=True,
        string='Producto',
    )
    variedad_id = fields.Many2one(
        'secadora.variedad.arroz',
        string='Variedad',
        index=True,
    )
    placa_texto = fields.Char(
        related='pesaje_id.placa_texto',
        store=True,
        string='Placa',
    )
    orden_servicio_id = fields.Many2one(
        related='pesaje_id.orden_servicio_id',
        store=True,
        string='Orden de Servicio',
    )
    modalidad_salida = fields.Selection(
        related='orden_servicio_id.modalidad_salida',
        store=True,
        string='Modalidad de Salida',
    )
    pesaje_name = fields.Char(
        related='pesaje_id.name',
        store=True,
        string='Tiquete',
    )
    conductor_id = fields.Many2one(
        related='pesaje_id.conductor_id',
        store=True,
        string='Conductor',
    )
    tipo_operacion_id = fields.Many2one(
        related='pesaje_id.tipo_operacion_id',
        store=True,
        string='Tipo de Operación',
    )
    es_semilla = fields.Boolean(
        related='pesaje_id.es_semilla',
        store=True,
        string='Es Semilla',
    )

    es_division = fields.Boolean(
        string='Es División',
        compute='_compute_es_division',
        store=True,
    )

    @api.depends('posicion_origen_id', 'posicion_hija_ids')
    def _compute_es_division(self):
        for rec in self:
            rec.es_division = bool(rec.posicion_origen_id) or bool(rec.posicion_hija_ids)

    @api.depends('es_semilla', 'es_preasignado')
    def _compute_permite_combinar(self):
        for rec in self:
            rec.permite_combinar = not rec.es_semilla and not rec.es_preasignado

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('secadora.posicion.arroz') or 'Nuevo'
        return super().create(vals_list)

    def write(self, vals):
        # Detectar cambio de sitio_id (drag-and-drop en kanban)
        if 'sitio_id' in vals:
            for rec in self:
                old_sitio = rec.sitio_id
                new_sitio_id = vals['sitio_id']
                if old_sitio.id != new_sitio_id and new_sitio_id:
                    self.env['secadora.movimiento.arroz'].create({
                        'posicion_id': rec.id,
                        'sitio_origen_id': old_sitio.id if old_sitio else False,
                        'sitio_destino_id': new_sitio_id,
                        'peso_kg': rec.peso_kg,
                        'tipo': 'movimiento',
                        'notas': f'Movido de {old_sitio.name or "Sin ubicación"} a {self.env["secadora.sitio.muestra"].browse(new_sitio_id).name}',
                    })
            vals['fecha_movimiento'] = fields.Datetime.now()
        return super().write(vals)

    @api.model
    def _read_group_sitio_ids(self, sitios, domain):
        """Mostrar todas las columnas contenedoras en el kanban, incluso las vacías."""
        return self.env['secadora.sitio.muestra'].search(
            [('es_contenedor', '=', True)],
            order='sequence, id',
        )

    def action_dividir(self):
        """Abrir wizard de división."""
        self.ensure_one()
        if self.state != 'activo':
            raise UserError('Solo se pueden dividir posiciones activas.')
        return {
            'name': 'Dividir Posición',
            'type': 'ir.actions.act_window',
            'res_model': 'secadora.dividir.posicion.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_posicion_id': self.id,
                'default_peso_actual': self.peso_kg,
            },
        }

    def action_despachar(self):
        """Abrir wizard de despacho."""
        self.ensure_one()
        if self.state != 'activo':
            raise UserError('Solo se pueden despachar posiciones activas.')
        return {
            'name': 'Despachar Posición',
            'type': 'ir.actions.act_window',
            'res_model': 'secadora.despachar.posicion.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_sitio_id': self.sitio_id.id,
                'default_posicion_ids': [fields.Command.set([self.id])],
            },
        }

    @api.model
    def get_tablero_grid_data(self):
        """Retorna datos para la vista de grilla 2D del tablero."""
        sitios = self.env['secadora.sitio.muestra'].search(
            [('es_contenedor', '=', True)],
            order='fila, columna, sequence, id',
        )
        posiciones = self.search([('state', '=', 'activo')])

        sitio_data = []
        for s in sitios:
            sitio_data.append({
                'id': s.id,
                'name': s.name,
                'fila': s.fila,
                'columna': s.columna,
                'capacidad_kg': s.capacidad_kg,
                'es_punto_salida': s.es_punto_salida,
                'ocultar_calidad': s.ocultar_calidad,
            })

        modalidad_labels = dict(self.env['secadora.orden.servicio']._fields['modalidad_salida'].selection)

        posicion_data = []
        for p in posiciones:
            posicion_data.append({
                'id': p.id,
                'name': p.name,
                'sitio_id': p.sitio_id.id if p.sitio_id else False,
                'peso_kg': p.peso_kg,
                'tercero': p.tercero_id.name if p.tercero_id else '',
                'variedad': p.variedad_id.name if p.variedad_id else '',
                'pesaje_name': p.pesaje_name or '',
                'placa_texto': p.placa_texto or '',
                'conductor': p.conductor_id.name if p.conductor_id else '',
                'tipo_operacion': p.tipo_operacion_id.name if p.tipo_operacion_id else '',
                'modalidad_salida': modalidad_labels.get(p.modalidad_salida, '') if p.modalidad_salida else '',
                'modalidad_salida_raw': p.modalidad_salida or '',
                'es_division': p.es_division,
                'es_division_hija': bool(p.posicion_origen_id),
                'es_combinacion': p.es_comercial,
                'es_preasignado': p.es_preasignado,
                'es_semilla': p.es_semilla,
                'permite_combinar': p.permite_combinar,
                'humedad': p.humedad,
                'impurezas': p.impurezas,
            })

        filas_set = set(s.fila for s in sitios) or {1}
        columnas_set = set(s.columna for s in sitios) or {1}
        # Siempre agregar una fila y columna extra para poder expandir
        filas = sorted(filas_set) + [max(filas_set) + 1]
        columnas = sorted(columnas_set) + [max(columnas_set) + 1]

        # Pesajes en tránsito (primera pesada completada, vehículo en camino)
        # Excluir los que ya tienen posición pre-asignada desde el tablero
        pesajes_preasignados_ids = posiciones.filtered('es_preasignado').mapped('pesaje_id').ids
        pesajes_transito = self.env['secadora.pesaje'].search([
            ('state', '=', 'en_transito'),
            ('direccion', '=', 'entrada'),
            ('id', 'not in', pesajes_preasignados_ids),
        ], order='id asc')
        en_transito_data = []
        for pes in pesajes_transito:
            en_transito_data.append({
                'id': pes.id,
                'tercero': pes.tercero_id.name if pes.tercero_id else '',
                'variedad': pes.variedad_id.name if pes.variedad_id else '',
                'peso_bruto': pes.peso_bruto,
                'placa_texto': pes.placa_texto or '',
                'conductor': pes.conductor_id.name if pes.conductor_id else '',
                'tipo_operacion': pes.tipo_operacion_id.name if pes.tipo_operacion_id else '',
                'pesaje_name': pes.name or '',
                'humedad': pes.humedad,
                'impurezas': pes.impurezas,
            })

        return {
            'sitios': sitio_data,
            'posiciones': posicion_data,
            'filas': filas,
            'columnas': columnas,
            'en_transito': en_transito_data,
        }

    @api.model
    def preasignar_transito(self, pesaje_id, sitio_id):
        """Pre-asignar ubicación a un pesaje en tránsito desde el tablero."""
        pesaje = self.env['secadora.pesaje'].browse(pesaje_id)
        if pesaje.state != 'en_transito':
            raise UserError('El pesaje no está en tránsito.')
        if pesaje.direccion != 'entrada':
            raise UserError('Solo se pueden pre-asignar pesajes de entrada.')

        # Lock pesaje row to prevent duplicate pre-assignments
        self.env.cr.execute(
            'SELECT id FROM secadora_pesaje WHERE id = %s FOR UPDATE NOWAIT',
            [pesaje_id]
        )

        # Verificar que no exista ya una pre-asignación
        existente = self.search([
            ('pesaje_id', '=', pesaje_id),
            ('es_preasignado', '=', True),
            ('state', '=', 'activo'),
        ], limit=1)
        if existente:
            raise UserError('Este pesaje ya tiene una ubicación pre-asignada.')

        posicion = self.create({
            'pesaje_id': pesaje_id,
            'sitio_id': sitio_id,
            'peso_kg': pesaje.peso_bruto,
            'peso_original': pesaje.peso_bruto,
            'es_preasignado': True,
        })

        self.env['secadora.movimiento.arroz'].create({
            'posicion_id': posicion.id,
            'sitio_destino_id': sitio_id,
            'peso_kg': pesaje.peso_bruto,
            'tipo': 'creacion',
            'notas': f'Pre-asignado desde tablero (en tránsito). Peso bruto: {pesaje.peso_bruto:.2f} kg',
        })

        return posicion.id

    def deshacer_preasignacion(self):
        """Deshacer la pre-asignación de una posición en tránsito."""
        self.ensure_one()
        if not self.es_preasignado:
            raise UserError('Esta posición no es una pre-asignación.')

        self.env['secadora.movimiento.arroz'].create({
            'posicion_id': self.id,
            'sitio_origen_id': self.sitio_id.id if self.sitio_id else False,
            'peso_kg': self.peso_kg,
            'tipo': 'retiro',
            'notas': 'Pre-asignación deshecha desde tablero',
        })
        self.write({'state': 'retirado'})

    def action_revertir_division(self):
        """Revertir una división: devolver el peso a la posición madre."""
        self.ensure_one()
        if self.state != 'activo':
            raise UserError('Solo se pueden revertir posiciones activas.')
        if not self.posicion_origen_id:
            raise UserError('Esta posición no es resultado de una división.')
        madre = self.posicion_origen_id
        if madre.state != 'activo':
            raise UserError(
                'La posición origen (%s) no está activa. '
                'Debe reactivarla antes de revertir la división.' % madre.name
            )

        peso_devuelto = self.peso_kg
        MovimientoArroz = self.env['secadora.movimiento.arroz']

        # Sumar peso a la madre
        madre.write({'peso_kg': madre.peso_kg + peso_devuelto})

        # Registrar movimiento en la madre
        MovimientoArroz.create({
            'posicion_id': madre.id,
            'sitio_origen_id': madre.sitio_id.id if madre.sitio_id else False,
            'sitio_destino_id': madre.sitio_id.id if madre.sitio_id else False,
            'peso_kg': madre.peso_kg,
            'tipo': 'division',
            'notas': 'Reversión de división: +%.2f kg devueltos desde %s' % (peso_devuelto, self.name),
        })

        # Registrar movimiento en la hija
        MovimientoArroz.create({
            'posicion_id': self.id,
            'sitio_origen_id': self.sitio_id.id if self.sitio_id else False,
            'peso_kg': peso_devuelto,
            'tipo': 'retiro',
            'notas': 'Reversión de división: %.2f kg devueltos a %s' % (peso_devuelto, madre.name),
        })

        # Marcar la hija como retirada
        self.write({'state': 'retirado'})

    def action_retirar(self):
        """Marcar como retirado (arroz salió de la planta)."""
        for rec in self:
            if rec.state != 'activo':
                raise UserError('Solo se pueden retirar posiciones activas.')
            rec.state = 'retirado'
            self.env['secadora.movimiento.arroz'].create({
                'posicion_id': rec.id,
                'sitio_origen_id': rec.sitio_id.id if rec.sitio_id else False,
                'peso_kg': rec.peso_kg,
                'tipo': 'retiro',
                'notas': 'Arroz retirado de la planta',
            })

    def action_reactivar(self):
        """Reactivar una posición retirada o despachada."""
        for rec in self:
            if rec.state not in ('retirado', 'despachado'):
                raise UserError('Solo se pueden reactivar posiciones retiradas o despachadas.')
            rec.state = 'activo'
            self.env['secadora.movimiento.arroz'].create({
                'posicion_id': rec.id,
                'sitio_destino_id': rec.sitio_id.id if rec.sitio_id else False,
                'peso_kg': rec.peso_kg,
                'tipo': 'creacion',
                'notas': 'Posición reactivada',
            })
