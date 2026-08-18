# -*- coding: utf-8 -*-

import base64
import logging

import pytz

from datetime import datetime, time

from odoo import models, fields, api
from odoo.exceptions import UserError
from odoo.tools.misc import file_path

_logger = logging.getLogger(__name__)


class CertificadoInventario(models.Model):
    """Certificado diario del arroz almacenado en las silobolsas.

    Reemplaza el documento que se llenaba a mano y se enviaba por correo:
    una fila por silobolsa con lo embolsado, lo desembolsado y el saldo.
    """

    _name = 'secadora.certificado.inventario'
    _description = 'Certificado de Inventarios de Silobolsas'
    _inherit = ['mail.thread']
    _order = 'fecha desc, id desc'
    _rec_name = 'name'

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
    fecha = fields.Date(
        string='Fecha del Certificado',
        required=True,
        default=fields.Date.context_today,
        index=True,
        help='Fecha de corte: se cuenta todo lo embolsado hasta el final de este día.',
    )
    state = fields.Selection([
        ('borrador', 'Borrador'),
        ('emitido', 'Emitido'),
        ('enviado', 'Enviado'),
    ], string='Estado', default='borrador', required=True, tracking=True, index=True)
    linea_ids = fields.One2many(
        'secadora.certificado.inventario.linea',
        'certificado_id',
        string='Líneas',
    )
    total_embolsado_kg = fields.Float(
        string='Total Embolsado (Kg)',
        digits=(14, 3),
        compute='_compute_totales',
        store=True,
    )
    total_desembolsado_kg = fields.Float(
        string='Total Desembolsado (Kg)',
        digits=(14, 3),
        compute='_compute_totales',
        store=True,
    )
    total_saldo_kg = fields.Float(
        string='Saldo Total (Kg)',
        digits=(14, 3),
        compute='_compute_totales',
        store=True,
    )
    cantidad_silobolsas = fields.Integer(
        string='Nº de Silobolsas',
        compute='_compute_totales',
        store=True,
    )
    destinatarios = fields.Char(
        string='Destinatarios',
        help='Correos separados por coma a los que se envió o se enviará el certificado.',
    )
    fecha_envio = fields.Datetime(string='Fecha de Envío', readonly=True, copy=False)
    mail_id = fields.Many2one('mail.mail', string='Correo Enviado', readonly=True, copy=False)
    notas = fields.Text(string='Notas')

    _fecha_company_unique = models.Constraint(
        'unique(fecha, company_id)',
        'Ya existe un certificado de inventarios para esa fecha.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'secadora.certificado.inventario'
                ) or 'Nuevo'
        return super().create(vals_list)

    @api.depends('linea_ids.embolsado_kg', 'linea_ids.desembolsado_kg', 'linea_ids.saldo_kg')
    def _compute_totales(self):
        for rec in self:
            rec.total_embolsado_kg = sum(rec.linea_ids.mapped('embolsado_kg'))
            rec.total_desembolsado_kg = sum(rec.linea_ids.mapped('desembolsado_kg'))
            rec.total_saldo_kg = sum(rec.linea_ids.mapped('saldo_kg'))
            rec.cantidad_silobolsas = len(rec.linea_ids)

    # ------------------------------------------------------------------
    # Cálculo de las líneas
    # ------------------------------------------------------------------
    def _get_datos_silobolsas(self):
        """Devuelve [(silobolsa, embolsado, desembolsado)] hasta la fecha de corte.

        Solo entran las silobolsas con saldo distinto de cero. Hoy no existe
        desembolsado en el sistema: cuando se implemente, basta con alimentar
        el diccionario ``desembolsado`` desde ese modelo.
        """
        self.ensure_one()
        # Corte al final del día en hora local, pasado a UTC (que es como se
        # guardan los Datetime en la base).
        tz = pytz.timezone(self.env.user.tz or 'America/Bogota')
        fin_dia_local = tz.localize(
            datetime.combine(self.fecha, time(23, 59, 59))
        )
        corte = fin_dia_local.astimezone(pytz.utc).replace(tzinfo=None)

        # sudo: el certificado debe ver TODOS los viajes de la compañía, aunque
        # lo dispare el cron o un usuario con acceso restringido.
        viajes = self.env['secadora.embolsado.viaje'].sudo().search([
            ('state', '=', 'confirmado'),
            ('fecha', '<=', corte),
            ('company_id', '=', self.company_id.id),
        ])

        embolsado = {}
        for viaje in viajes:
            if not viaje.silobolsa_id:
                continue
            embolsado.setdefault(viaje.silobolsa_id, 0.0)
            embolsado[viaje.silobolsa_id] += viaje.peso_neto_kg

        # Por ahora no hay desembolsado registrado en el sistema.
        desembolsado = {}

        datos = []
        for silobolsa in sorted(embolsado, key=lambda s: (s.name or '', s.id)):
            emb = embolsado.get(silobolsa, 0.0)
            des = desembolsado.get(silobolsa, 0.0)
            saldo = emb - des
            if abs(saldo) < 0.001:
                continue
            datos.append((silobolsa, emb, des))
        return datos

    def action_calcular(self):
        """(Re)genera las líneas del certificado a partir de los viajes."""
        for rec in self:
            if rec.state == 'enviado':
                raise UserError(
                    'El certificado %s ya fue enviado. Cree uno nuevo si necesita '
                    'recalcular.' % rec.name
                )
            rec.linea_ids.unlink()
            lineas = []
            for silobolsa, emb, des in rec._get_datos_silobolsas():
                lineas.append((0, 0, {
                    'silobolsa_id': silobolsa.id,
                    'embolsado_kg': emb,
                    'desembolsado_kg': des,
                }))
            rec.linea_ids = lineas
        return True

    def action_emitir(self):
        for rec in self:
            if not rec.linea_ids:
                raise UserError(
                    'El certificado %s no tiene líneas. Calcúlelo antes de emitirlo.' % rec.name
                )
            rec.state = 'emitido'
        return True

    def action_volver_borrador(self):
        for rec in self:
            rec.state = 'borrador'
        return True

    # ------------------------------------------------------------------
    # Datos del certificado (parametrizables desde Ajustes > Parámetros)
    # ------------------------------------------------------------------
    def _get_param(self, clave, defecto):
        return (self.env['ir.config_parameter'].sudo().get_param(
            'secadora_embolsado.%s' % clave, defecto
        ) or defecto).strip()

    def _get_certificante_nombre(self):
        return self._get_param('certificado_certificante_nombre', 'JOSE EDUARDO VELANDIA OTALORA')

    def _get_certificante_cc(self):
        return self._get_param('certificado_certificante_cc', '74.750.290')

    def _get_firmante_nombre(self):
        return self._get_param('certificado_firmante_nombre', 'Juan Pablo Velandia Cala')

    def _get_firmante_cc(self):
        return self._get_param('certificado_firmante_cc', '1.026.297.343')

    def _get_firmante_cargo(self):
        return self._get_param('certificado_firmante_cargo', 'Administrador')

    def _get_firma_src(self):
        """Imagen de la firma para el reporte, como data URI.

        Se toma de la carpeta static del módulo. Para cambiar la firma basta con
        reemplazar ese archivo.
        """
        try:
            ruta = file_path(
                'secadora_embolsado/static/src/img/firma_administrador.png',
                filter_ext=('.png',),
            )
        except (FileNotFoundError, ValueError):
            _logger.warning('No se encontró la imagen de la firma del certificado.')
            return ''
        with open(ruta, 'rb') as archivo:
            return 'data:image/png;base64,%s' % base64.b64encode(archivo.read()).decode()

    # ------------------------------------------------------------------
    # Envío por correo
    # ------------------------------------------------------------------
    @api.model
    def _get_destinatarios_por_defecto(self):
        return (self.env['ir.config_parameter'].sudo().get_param(
            'secadora_embolsado.certificado_destinatarios', ''
        ) or '').strip()

    def _render_pdf(self):
        self.ensure_one()
        pdf, _dummy = self.env['ir.actions.report'].sudo()._render_qweb_pdf(
            'secadora_embolsado.action_report_certificado_inventario', res_ids=self.ids
        )
        return pdf

    def action_enviar_correo(self):
        """Genera el PDF y lo envía a los destinatarios configurados."""
        for rec in self:
            destinatarios = (rec.destinatarios or rec._get_destinatarios_por_defecto()).strip()
            if not destinatarios:
                raise UserError(
                    'No hay destinatarios configurados. Defina el parámetro de sistema '
                    '"secadora_embolsado.certificado_destinatarios" o llene el campo '
                    'Destinatarios.'
                )
            if not rec.linea_ids:
                raise UserError(
                    'El certificado %s no tiene líneas; no se envía vacío.' % rec.name
                )

            pdf = rec._render_pdf()
            nombre_archivo = 'Certificado de inventarios %s.pdf' % fields.Date.to_string(rec.fecha)
            adjunto = self.env['ir.attachment'].sudo().create({
                'name': nombre_archivo,
                'type': 'binary',
                'datas': base64.b64encode(pdf),
                'res_model': rec._name,
                'res_id': rec.id,
                'mimetype': 'application/pdf',
            })

            fecha_txt = rec.fecha.strftime('%d/%m/%Y')
            cuerpo = (
                '<p>Buenas noches,</p>'
                '<p>Adjunto el certificado de inventarios de arroz paddy seco almacenado '
                'en nuestras silobolsas con corte al <strong>%s</strong>.</p>'
                '<p>Saldo total: <strong>%s kgs</strong> en %s silobolsas.</p>'
                '<p>Cordialmente,<br/>Secadora La Gran Colombia S.A.S</p>'
                % (
                    fecha_txt,
                    '{:,.0f}'.format(rec.total_saldo_kg).replace(',', '.'),
                    rec.cantidad_silobolsas,
                )
            )

            correo = self.env['mail.mail'].sudo().create({
                'subject': 'Certificado de inventarios - %s' % fecha_txt,
                'body_html': cuerpo,
                'email_to': destinatarios,
                'attachment_ids': [(4, adjunto.id)],
                'auto_delete': False,
            })
            correo.send(raise_exception=True)

            rec.write({
                'state': 'enviado',
                'destinatarios': destinatarios,
                'fecha_envio': fields.Datetime.now(),
                'mail_id': correo.id,
            })
            rec.message_post(
                body='Certificado enviado a %s' % destinatarios,
                attachment_ids=[adjunto.id],
            )
        return True

    # ------------------------------------------------------------------
    # Cron diario
    # ------------------------------------------------------------------
    @api.model
    def _get_company_certificado(self):
        """Compañía del certificado: la de la báscula/silobolsas.

        El cron no corre con una compañía activa confiable, así que se ancla a
        la compañía 1 (la Secadora), que es la dueña de los pesajes y de las
        silobolsas. Ver la regla de negocio de pesajes/OS.
        """
        company = self.env['res.company'].sudo().browse(1).exists()
        return company or self.env.company

    @api.model
    def _cron_certificado_diario(self):
        """Crea, calcula y envía el certificado del día. Corre a las 9 pm."""
        hoy = fields.Date.context_today(self)
        company = self._get_company_certificado()

        self = self.with_company(company)
        certificado = self.sudo().search([
            ('fecha', '=', hoy),
            ('company_id', '=', company.id),
        ], limit=1)
        if certificado.state == 'enviado':
            _logger.info(
                'Certificado de inventarios de %s ya fue enviado; no se repite.', hoy
            )
            return True
        if not certificado:
            certificado = self.sudo().create({'fecha': hoy, 'company_id': company.id})

        certificado.action_calcular()
        if not certificado.linea_ids:
            _logger.warning(
                'Certificado de inventarios de %s sin silobolsas con saldo; no se envía.', hoy
            )
            return True

        certificado.action_emitir()
        try:
            certificado.action_enviar_correo()
        except Exception:
            _logger.exception('Falló el envío del certificado de inventarios de %s', hoy)
            raise
        return True


class CertificadoInventarioLinea(models.Model):
    _name = 'secadora.certificado.inventario.linea'
    _description = 'Línea del Certificado de Inventarios'
    _order = 'silobolsa_name, id'

    certificado_id = fields.Many2one(
        'secadora.certificado.inventario',
        string='Certificado',
        required=True,
        ondelete='cascade',
        index=True,
    )
    silobolsa_id = fields.Many2one(
        'secadora.silobolsa',
        string='Silobolsa',
        required=True,
        index=True,
    )
    silobolsa_name = fields.Char(
        string='Silo',
        related='silobolsa_id.name',
        store=True,
    )
    ubicacion = fields.Char(
        string='Ubicación',
        related='silobolsa_id.ubicacion',
    )
    variedad_id = fields.Many2one(
        'secadora.variedad.arroz',
        string='Variedad',
        related='silobolsa_id.variedad_id',
    )
    embolsado_kg = fields.Float(string='Embolsado (Kg)', digits=(14, 3))
    desembolsado_kg = fields.Float(string='Desembolsado (Kg)', digits=(14, 3))
    saldo_kg = fields.Float(
        string='Saldo (Kg)',
        digits=(14, 3),
        compute='_compute_saldo',
        store=True,
    )

    @api.depends('embolsado_kg', 'desembolsado_kg')
    def _compute_saldo(self):
        for rec in self:
            rec.saldo_kg = rec.embolsado_kg - rec.desembolsado_kg
