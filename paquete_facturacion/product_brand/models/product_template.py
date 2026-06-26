# Copyright 2009 NetAndCo (<http://www.netandco.net>).
# Copyright 2011 Akretion Benoît Guillot <benoit.guillot@akretion.com>
# Copyright 2014 prisnet.ch Seraphine Lantible <s.lantible@gmail.com>
# Copyright 2016 Serpent Consulting Services Pvt. Ltd.
# Copyright 2018 Daniel Campos <danielcampos@avanzosc.es>
# Copyright 2019 Kaushal Prajapati <kbprajapati@live.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from odoo import fields, models, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = "product.template"

    product_brand_id = fields.Many2one(
        "product.brand", string="Brand", help="Select a brand for this product"
    )

    def action_assign_brand_from_attribute(self):
        """Busca el atributo Marca y asocia al campo product_brand_id"""
        # Buscar atributo de marca
        brand_attr = self.env['product.attribute'].search([
            ('name', 'ilike', 'marca')
        ], limit=1)

        if not brand_attr:
            raise UserError(_('No se encontro el atributo "Marca"'))

        updated = 0
        not_found = []

        for product in self:
            # Buscar valor del atributo marca en las lineas de atributo
            brand_value = None
            for line in product.attribute_line_ids:
                if line.attribute_id == brand_attr:
                    if line.value_ids:
                        brand_value = line.value_ids[0].name
                        break

            if not brand_value:
                continue

            # Buscar marca en product.brand
            brand = self.env['product.brand'].search([
                ('name', '=ilike', brand_value)
            ], limit=1)

            if brand:
                product.product_brand_id = brand
                updated += 1
                _logger.info(f'Producto {product.name} -> Marca {brand.name}')
            else:
                not_found.append(brand_value)

        msg = f'Actualizados: {updated} productos'
        if not_found:
            unique_not_found = list(set(not_found))
            msg += f'\nMarcas no encontradas: {", ".join(unique_not_found)}'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Asignar Marca'),
                'message': msg,
                'type': 'success' if updated else 'warning',
                'sticky': True,
            }
        }
