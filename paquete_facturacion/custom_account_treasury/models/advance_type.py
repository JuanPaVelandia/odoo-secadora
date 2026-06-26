from odoo import fields, models, api, _

class AdvanceType(models.Model):
	_name = "advance.type"
	_description = "Tipo de anticipo"
	_order = "sequence, name"

	name = fields.Char(string="Name", required=True)
	sequence = fields.Integer(string="Secuencia", default=10)
	account_id = fields.Many2one('account.account', string="Cuenta de anticipo", required=True, domain=[('account_type','in',('asset_receivable', 'liability_payable'))])
	internal_type = fields.Selection(related='account_id.account_type', string="Internal Type", store=True, readonly=True)
	company_id = fields.Many2one('res.company',  string='Company', store=True, readonly=True,default=lambda self: self.env.company)

	# ========== TIPO DE DOCUMENTO ==========
	document_type = fields.Selection([
		('supplier', 'Proveedor'),
		('customer', 'Cliente'),
		('employee', 'Empleado'),
		('other', 'Otro'),
	], string='Tipo de Documento', required=True, default='supplier')

	# ========== CONTROL Y VALIDACIONES ==========
	require_approval = fields.Boolean(
		string='Requiere Aprobación',
		default=True,
		help='Si está marcado, los anticipos de este tipo requieren aprobación'
	)

	max_amount = fields.Monetary(
		string='Monto Máximo',
		currency_field='currency_id',
		help='Monto máximo permitido para este tipo (0 = sin límite)'
	)

	currency_id = fields.Many2one(
		'res.currency',
		string='Moneda',
		default=lambda self: self.env.company.currency_id
	)

	allow_sale_orders = fields.Boolean(
		string='Permitir Órdenes de Venta',
		default=False,
		help='Permite asociar órdenes de venta a solicitudes de este tipo'
	)

	allow_purchase_orders = fields.Boolean(
		string='Permitir Órdenes de Compra',
		default=False,
		help='Permite asociar órdenes de compra a solicitudes de este tipo'
	)

	require_orders = fields.Boolean(
		string='Requiere Órdenes',
		default=False,
		help='Obliga a asociar al menos una orden para crear la solicitud'
	)

	auto_fill_amount = fields.Boolean(
		string='Auto-llenar Monto',
		default=True,
		help='Calcula automáticamente el monto desde las órdenes asociadas'
	)

	percentage_advance = fields.Float(
		string='% Anticipo',
		default=100.0,
		help='Porcentaje del total de órdenes a solicitar como anticipo'
	)

	# ========== CAMPOS PARA CÁLCULOS AUTOMÁTICOS ==========
	operation_code = fields.Char(
		string='Código de Operación',
		help='Código único para identificar el tipo de operación (ej: ANT_CLI, ANT_PROV, ANT_EMP)'
	)

	default_percentage = fields.Float(
		string='Porcentaje por Defecto',
		default=100.0,
		help='Porcentaje por defecto para calcular el monto sugerido del anticipo'
	)

	min_amount = fields.Monetary(
		string='Monto Mínimo',
		currency_field='currency_id',
		help='Monto mínimo permitido para este tipo de anticipo (0 = sin mínimo)'
	)

	active = fields.Boolean(string='Activo', default=True)

	# ========== APROBADORES FIJOS ==========
	approval_limit_ids = fields.Many2many(
		'advance.approval.limit',
		'advance_type_approval_limit_rel',
		'advance_type_id',
		'approval_limit_id',
		string='Límites de Aprobación',
		help='Límites de aprobación específicos para este tipo de anticipo'
	)

	# ========== SECUENCIAS (consolidado de treasury_sequence_config.py) ==========
	sequence_id = fields.Many2one(
		'ir.sequence',
		string='Secuencia',
		help='Secuencia para generar números de anticipos de este tipo.',
	)

	sequence_prefix = fields.Char(
		string='Prefijo Secuencia',
		help='Prefijo para los números de anticipo (ej: ANT-CLI, ANT-PROV)',
	)

	def get_next_advance_number(self):
		"""Genera el siguiente número de anticipo para este tipo."""
		self.ensure_one()
		if not self.sequence_id:
			return False
		number = self.sequence_id.next_by_id()
		if self.sequence_prefix:
			number = f"{self.sequence_prefix}-{number}"
		return number

	# ========== CONSTRAINTS ==========
	@api.constrains('percentage_advance')
	def _check_percentage(self):
		for record in self:
			if record.percentage_advance < 0 or record.percentage_advance > 100:
				raise models.ValidationError(_('El porcentaje debe estar entre 0 y 100'))

	@api.constrains('max_amount')
	def _check_max_amount(self):
		for record in self:
			if record.max_amount < 0:
				raise models.ValidationError(_('El monto máximo no puede ser negativo'))

	@api.constrains('min_amount')
	def _check_min_amount(self):
		for record in self:
			if record.min_amount < 0:
				raise models.ValidationError(_('El monto mínimo no puede ser negativo'))

	@api.constrains('default_percentage')
	def _check_default_percentage(self):
		for record in self:
			if record.default_percentage < 0 or record.default_percentage > 100:
				raise models.ValidationError(_('El porcentaje por defecto debe estar entre 0 y 100'))

