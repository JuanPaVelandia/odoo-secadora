# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError


class AsociarFacturaWizard(models.TransientModel):
    _name = 'secadora.asociar.factura.wizard'
    _description = 'Asociar Fletes a Factura de Transportadora'

    flete_ids = fields.Many2many(
        'secadora.flete',
        string='Fletes',
    )
    transportadora_id = fields.Many2one(
        'secadora.transportadora',
        string='Transportadora',
        compute='_compute_transportadora_id',
    )
    partner_transportadora_id = fields.Many2one(
        'res.partner',
        string='Contacto Transportadora',
        related='transportadora_id.partner_id',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Empresa que Paga',
        compute='_compute_company_id',
    )
    costo_total_fletes = fields.Float(
        string='Costo Total Fletes',
        compute='_compute_costo_total_fletes',
        digits='Product Price',
    )
    modo = fields.Selection([
        ('existente', 'Factura Existente'),
        ('nueva', 'Crear Nueva Factura'),
    ], string='Modo', required=True, default='nueva')

    factura_id = fields.Many2one(
        'account.move',
        string='Factura Existente',
        domain="factura_domain",
    )
    factura_domain = fields.Binary(
        string='Dominio Factura',
        compute='_compute_factura_domain',
        help='Filtra las facturas por proveedor (contacto de la transportadora) '
             'y por la empresa que paga.',
    )
    partner_factura_id = fields.Many2one(
        'res.partner',
        string='Proveedor (Transportadora)',
        help='Partner para la nueva factura de proveedor',
    )

    @api.depends('flete_ids.transportadora_id')
    def _compute_transportadora_id(self):
        for rec in self:
            transportadoras = rec.flete_ids.mapped('transportadora_id')
            rec.transportadora_id = transportadoras[0] if len(transportadoras) == 1 else False

    @api.depends('flete_ids.company_id')
    def _compute_company_id(self):
        for rec in self:
            companies = rec.flete_ids.mapped('company_id')
            rec.company_id = companies[0] if len(companies) == 1 else False

    @api.depends('partner_transportadora_id', 'company_id')
    def _compute_factura_domain(self):
        """Dominio dinámico: facturas de proveedor (borrador o validadas, no
        canceladas) filtradas por el NIT del dueño de la transportadora y la
        empresa que paga, excluyendo las ya asociadas a algún flete.

        Se filtra por el NIT (vat) del contacto de la transportadora, no por el
        contacto exacto: así aparece cualquier factura cuyo proveedor tenga el
        mismo NIT, aunque sea otro registro de contacto. Si la transportadora no
        tiene contacto o el contacto no tiene NIT cargado, no se puede filtrar
        por proveedor y se muestran todas las facturas de la empresa.

        La búsqueda se hace sobre TODAS las compañías del usuario (no solo la
        activa en la sesión), para que aparezca la factura aunque la empresa que
        paga no esté seleccionada en el conmutador de compañías. El filtro por
        company_id (empresa que paga del flete) evita mezclar empresas.
        """
        # Compañías a las que el usuario tiene acceso (aunque no estén activas).
        allowed_company_ids = self.env.user.company_ids.ids

        # Facturas ya vinculadas a algún flete (para no ofrecerlas de nuevo).
        facturas_usadas_ids = self.env['secadora.flete'].search(
            [('factura_transportadora_id', '!=', False)]
        ).mapped('factura_transportadora_id').ids

        for rec in self:
            search_domain = [
                ('move_type', '=', 'in_invoice'),
                ('state', '!=', 'cancel'),
            ]
            if facturas_usadas_ids:
                search_domain.append(('id', 'not in', facturas_usadas_ids))
            nit = rec.partner_transportadora_id.vat
            if nit:
                search_domain.append(('partner_id.vat', '=', nit))
            if rec.company_id:
                search_domain.append(('company_id', '=', rec.company_id.id))

            # Buscar en todas las compañías permitidas del usuario y fijar el
            # resultado como dominio por id, para saltar el filtro de la compañía
            # activa sin exponer compañías fuera del alcance del usuario.
            facturas = self.env['account.move'].with_context(
                allowed_company_ids=allowed_company_ids,
            ).search(search_domain)
            rec.factura_domain = [('id', 'in', facturas.ids)]

    @api.depends('flete_ids.costo_total')
    def _compute_costo_total_fletes(self):
        for rec in self:
            rec.costo_total_fletes = sum(rec.flete_ids.mapped('costo_total'))

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_ids = self.env.context.get('active_ids', [])
        if active_ids:
            fletes = self.env['secadora.flete'].browse(active_ids)
            res['flete_ids'] = [(6, 0, fletes.ids)]
            # Precargar el proveedor de la nueva factura con el contacto de la
            # transportadora, si todos los fletes son de la misma.
            transportadoras = fletes.mapped('transportadora_id')
            if len(transportadoras) == 1 and transportadoras.partner_id:
                res['partner_factura_id'] = transportadoras.partner_id.id
        return res

    def action_asociar(self):
        self.ensure_one()
        if not self.flete_ids:
            raise UserError('Debe seleccionar al menos un flete.')

        # Validar que no haya fletes ya asociados a OTRA factura
        for flete in self.flete_ids:
            if flete.factura_transportadora_id:
                raise UserError(
                    f'El flete {flete.name} ya está asociado a la factura '
                    f'{flete.factura_transportadora_id.name}. '
                    f'Desvinculelo primero si desea reasignarlo.'
                )

        if self.modo == 'existente':
            if not self.factura_id:
                raise UserError('Debe seleccionar una factura existente.')
            factura = self.factura_id
        else:
            if not self.partner_factura_id:
                raise UserError('Debe seleccionar un proveedor para la nueva factura.')
            # Use company_id from first flete for the new invoice
            company = self.flete_ids[0].company_id if self.flete_ids else self.env.company
            factura = self.env['account.move'].create({
                'move_type': 'in_invoice',
                'partner_id': self.partner_factura_id.id,
                'company_id': company.id,
            })

        self.flete_ids.write({'factura_transportadora_id': factura.id})

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': factura.id,
            'view_mode': 'form',
            'target': 'current',
        }
