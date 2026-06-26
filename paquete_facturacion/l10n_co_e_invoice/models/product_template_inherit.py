from odoo import fields, models


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    type = fields.Selection(
        selection_add=[("out_invoice", "Out Invoice"), ("out_refund", "Out Refund")],
        ondelete={"out_invoice": "set default", "out_refund": "set default"},
    )

class ProductUom(models.Model):
    _inherit = 'uom.uom'

    dian_country_code = fields.Char(
        'Country code',
        default=lambda self: self.env.company.country_id.code
    )
    dian_uom_id = fields.Many2one(
        'dian.uom.code', 'DIAN UoM'
    )



class ProductTemplate(models.Model):
    _inherit = "product.template"
    
    line_price_reference = fields.Float(string='Precio de referencia')
    operation_type = fields.Selection(
        [("09", "Servicios AIU"), ("10", "Estandar"), ("11", "Mandatos bienes")],
        string="Tipo de operación DIAN",
    )

    product_UNSPSC_id = fields.Many2one("dian.unspsc.product", string="Producto UNSPSC")
    segment_name = fields.Char(
        string="Segmento UNSPSC",
        readonly=True,
        related="product_UNSPSC_id.segment_id.name",
    )
    family_name = fields.Char(
        string="Familia UNSPSC",
        readonly=True,
        related="product_UNSPSC_id.family_id.name",
    )
    class_name = fields.Char(
        string="Class Segmento UNSPSC",
        readonly=True,
        related="product_UNSPSC_id.class_id.name",
    )
    brand_id = fields.Many2one("product.brand", "Marca")
    model_id = fields.Many2one("product.model", "Modelo")
    enable_charges = fields.Boolean(string='Cargo de Factura Electrónica')
    ref_nominal_tax = fields.Float(string='Referencia de Impuesto Nominal')
    has_health_taxes = fields.Boolean(string='Tiene Impuestos Saludables')
    has_icui = fields.Boolean(string='Aplica ICUI', help='Impuesto a productos comestibles ultraprocesados')
    has_ibua = fields.Boolean(string='Aplica IBUA', help='Impuesto a bebidas ultraprocesadas azucaradas')
    ml_ibua = fields.Float(string='Mililitros IBUA', help='Volumen en mililitros de la bebida')
    grams_ibua = fields.Float(string='Gramos azúcar IBUA', help='Gramos de azúcar por cada 100ml')
    has_inpp = fields.Boolean(string='Aplica INPP', help='Impuesto nacional productos plásticos')
    grams_inpp = fields.Float(string='Gramos INPP', help='Peso en gramos del empaque plástico')
