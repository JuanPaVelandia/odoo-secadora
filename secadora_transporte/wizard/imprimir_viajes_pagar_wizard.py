# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError


class ImprimirViajesPagarWizard(models.TransientModel):
    _name = 'secadora.imprimir.viajes.pagar.wizard'
    _description = 'Imprimir Viajes Facturados por Pagar'

    transportadora_id = fields.Many2one(
        'secadora.transportadora',
        string='Transportadora',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Empresa que Paga',
    )
    fecha_desde = fields.Date(string='Desde')
    fecha_hasta = fields.Date(string='Hasta')
    pago_flete = fields.Selection([
        ('secadora', 'Secadora paga y descuenta'),
        ('agricultor', 'Agricultor paga directo'),
    ], string='Modalidad de Pago',
       help='Vacío = todas las modalidades')

    factura_ids = fields.Many2many(
        'account.move',
        string='Facturas a Pagar',
        domain="factura_domain",
        help='Facturas de transportadora publicadas y con saldo pendiente. '
             'Quite las que no se vayan a pagar en este giro.',
    )
    factura_domain = fields.Binary(
        string='Dominio Facturas',
        compute='_compute_factura_domain',
    )
    total_girar = fields.Monetary(
        string='Total a Girar',
        compute='_compute_total_girar',
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id,
    )

    def _buscar_facturas_candidatas(self):
        """Facturas de transportadora publicadas con saldo pendiente que
        tengan al menos un flete que pase los filtros del wizard.

        Alcance: compañías activas de la sesión (mismo alcance que el
        tablero). No se amplía a todas las compañías del usuario porque las
        facturas precargadas deben ser legibles por la regla multi-compañía
        de account.move en el contexto actual.
        """
        Flete = self.env['secadora.flete']
        fletes = Flete.search(Flete._domain_tablero({
            'transportadora_id': self.transportadora_id.id,
            'company_id': self.company_id.id,
            'fecha_desde': self.fecha_desde,
            'fecha_hasta': self.fecha_hasta,
            'pago_flete': self.pago_flete,
        }) + [('factura_transportadora_id', '!=', False)])

        return fletes.mapped('factura_transportadora_id').filtered(
            lambda f: f.es_por_pagar()
        )

    @api.depends('transportadora_id', 'company_id', 'fecha_desde',
                 'fecha_hasta', 'pago_flete')
    def _compute_factura_domain(self):
        for rec in self:
            rec.factura_domain = [('id', 'in', rec._buscar_facturas_candidatas().ids)]

    @api.depends('factura_ids.amount_residual')
    def _compute_total_girar(self):
        for rec in self:
            rec.total_girar = sum(rec.factura_ids.mapped('amount_residual'))

    # Precarga: al abrir el formulario, el cliente dispara el onchange
    # inicial con los default_* del contexto, así que este único método
    # puebla la selección tanto al abrir como al cambiar cualquier filtro.
    @api.onchange('transportadora_id', 'company_id', 'fecha_desde',
                  'fecha_hasta', 'pago_flete')
    def _onchange_filtros(self):
        self.factura_ids = [Command.set(self._buscar_facturas_candidatas().ids)]

    def action_imprimir(self):
        self.ensure_one()
        if not self.factura_ids:
            raise UserError('No hay facturas seleccionadas para imprimir.')

        # Revalidar: entre abrir el wizard e imprimir, alguna factura pudo
        # pagarse o cambiar de estado.
        invalidas = self.factura_ids.filtered(lambda f: not f.es_por_pagar())
        if invalidas:
            raise UserError(
                'Las siguientes facturas ya no están pendientes de pago '
                '(fueron pagadas o cambiaron de estado): %s. '
                'Quítelas de la selección.' % ', '.join(invalidas.mapped('name'))
            )

        monedas = self.factura_ids.mapped('currency_id')
        if len(monedas) > 1:
            raise UserError(
                'Las facturas seleccionadas están en monedas distintas (%s): '
                'el total a girar no puede sumarse. Imprima cada moneda por '
                'separado.' % ', '.join(monedas.mapped('name'))
            )

        return self.env.ref(
            'secadora_transporte.action_report_viajes_por_pagar'
        ).report_action(self.factura_ids)
