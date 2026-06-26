from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare

class AccountPayment(models.Model):
	_name = 'account.payment'
	_inherit = ['account.payment', 'payment.tax.mixin']

	@api.depends('payment_line_ids.invoice_id')
	def _compute_domain_move_line(self):
		for pay in self:
			invoices = pay.mapped('payment_line_ids.invoice_id')
			pay.domain_move_lines = [(6,0,invoices.ids)]

	@api.depends('payment_line_ids.move_line_id')
	def _compute_domain_accountmove_line(self):
		for pay in self:
			invoices = pay.mapped('payment_line_ids.move_line_id')
			pay.domain_account_move_lines = [(6,0,invoices.ids)]


	move_diff_ids = fields.Many2many('account.move', 'account_move_payment_rel_ids', 'move_id', 'payment_id', copy=False)
	payment_line_ids = fields.One2many('account.payment.detail', 'payment_id', copy=False, string="Detalle de pago", help="detalle de pago")
	currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        compute='_compute_currency_id', store=True, readonly=False, precompute=True, default=lambda self: self.env.company.currency_id,
        help="The payment's currency.")
	destination_account_id = fields.Many2one(
		comodel_name='account.account',
		string='Destination Account',
		store=True, readonly=False,
		compute='_compute_destination_account_id',
		domain="[('account_type', 'in', ('asset_receivable', 'liability_payable'))]",
		check_company=True)
	change_destination_account = fields.Char(string="cambio de cuenta destino")

	# === Outstanding account override with fallback === #
	outstanding_account_id = fields.Many2one(
		comodel_name='account.account',
		string="Outstanding Account",
		store=True,
		compute='_compute_outstanding_account_id',
		check_company=True)

	# === Multi-partner fields (siempre activo) === #
	enable_multi_partner = fields.Boolean(
		string='Habilitar Multi-Tercero',
		default=True,
		help='Permite asignar diferentes terceros por línea de pago'
	)

	# === Multiple payment methods === #
	use_multiple_payment_methods = fields.Boolean(
		string='Usar Múltiples Métodos de Pago',
		default=False,
		help='Permite usar diferentes métodos de pago en un mismo documento'
	)

	# === Saldos del tercero (computed) === #
	partner_receivable_balance = fields.Monetary(
		string='Por Cobrar',
		compute='_compute_partner_balances',
		currency_field='currency_id',
		help='Saldo pendiente por cobrar del tercero'
	)
	partner_payable_balance = fields.Monetary(
		string='Por Pagar',
		compute='_compute_partner_balances',
		currency_field='currency_id',
		help='Saldo pendiente por pagar al tercero'
	)
	partner_advance_balance = fields.Monetary(
		string='Anticipos',
		compute='_compute_partner_balances',
		currency_field='currency_id',
		help='Saldo de anticipos del tercero'
	)

	# === Subtotales de líneas de pago === #
	total_documents_amount = fields.Monetary(
		string='Total Saldo Documentos',
		compute='_compute_payment_line_totals',
		currency_field='currency_id',
		help='Suma del saldo residual de todos los documentos seleccionados'
	)
	total_payment_amount = fields.Monetary(
		string='Total a Pagar',
		compute='_compute_payment_line_totals',
		currency_field='currency_id',
		help='Suma del monto a pagar de todas las líneas seleccionadas'
	)
	payment_difference = fields.Monetary(
		string='Diferencia',
		compute='_compute_payment_line_totals',
		currency_field='currency_id',
		help='Diferencia entre el monto del pago y el total a pagar'
	)

	# Campo para asignar cuenta masivamente
	mass_account_id = fields.Many2one(
		'account.account',
		string='Cuenta Masiva',
		domain="[('account_type', 'in', ['asset_receivable', 'liability_payable'])]",
		help='Cuenta para asignar a todas las líneas sin documento'
	)

	# === Saldos del Diario/Banco === #
	journal_balance = fields.Monetary(
		string='Saldo Contable',
		compute='_compute_journal_balances',
		currency_field='currency_id',
		help='Saldo contable total del diario'
	)
	journal_balance_reconciled = fields.Monetary(
		string='Saldo Conciliado',
		compute='_compute_journal_balances',
		currency_field='currency_id',
		help='Saldo conciliado (transacciones bancarias conciliadas)'
	)
	journal_balance_pending = fields.Monetary(
		string='Pendiente Conciliar',
		compute='_compute_journal_balances',
		currency_field='currency_id',
		help='Movimientos pendientes de conciliar'
	)

	@api.depends('journal_id', 'date')
	def _compute_journal_balances(self):
		for payment in self:
			balance = reconciled = pending = 0.0
			if payment.journal_id and payment.journal_id.default_account_id:
				account = payment.journal_id.default_account_id
				date_filter = payment.date or fields.Date.today()
				# Saldo contable total
				lines = self.env['account.move.line'].search([
					('account_id', '=', account.id),
					('parent_state', '=', 'posted'),
					('date', '<=', date_filter),
				])
				balance = sum(lines.mapped('balance'))
				# Saldo conciliado (líneas con statement_line_id)
				reconciled_lines = lines.filtered(lambda l: l.statement_line_id or l.full_reconcile_id)
				reconciled = sum(reconciled_lines.mapped('balance'))
				# Pendiente de conciliar
				pending = balance - reconciled
			payment.journal_balance = balance
			payment.journal_balance_reconciled = reconciled
			payment.journal_balance_pending = pending

	@api.depends('payment_line_ids', 'payment_line_ids.amount_residual', 'payment_line_ids.payment_amount', 'payment_line_ids.to_pay', 'payment_line_ids.is_main', 'payment_line_ids.display_type', 'amount')
	def _compute_payment_line_totals(self):
		for payment in self:
			lines = payment.payment_line_ids.filtered(
				lambda l: not l.is_main and not l.display_type and l.to_pay
			)
			payment.total_documents_amount = sum(lines.mapped('amount_residual'))
			payment.total_payment_amount = sum(lines.mapped('payment_amount'))
			payment.payment_difference = payment.amount - payment.total_payment_amount

	def action_apply_mass_account(self):
		"""Aplica la cuenta seleccionada a todas las líneas sin documento"""
		self.ensure_one()
		if not self.mass_account_id:
			raise UserError(_("Seleccione una cuenta primero."))
		lines_to_update = self.payment_line_ids.filtered(
			lambda l: not l.is_main and not l.display_type and not l.move_line_id
		)
		if not lines_to_update:
			raise UserError(_("No hay líneas sin documento para actualizar."))
		lines_to_update.write({'account_id': self.mass_account_id.id})
		return True

	def action_select_all_lines(self):
		"""Selecciona todas las líneas de pago"""
		self.ensure_one()
		lines = self.payment_line_ids.filtered(
			lambda l: not l.is_main and not l.display_type
		)
		lines.write({'to_pay': True})
		return True

	def action_deselect_all_lines(self):
		"""Deselecciona todas las líneas de pago"""
		self.ensure_one()
		lines = self.payment_line_ids.filtered(
			lambda l: not l.is_main and not l.display_type
		)
		lines.write({'to_pay': False})
		return True

	@api.depends('partner_id', 'partner_type')
	def _compute_partner_balances(self):
		for payment in self:
			receivable = payable = advance = 0.0
			if payment.partner_id:
				# Obtener saldos usando account.move.line
				domain_base = [
					('partner_id', '=', payment.partner_id.id),
					('parent_state', '=', 'posted'),
					('reconciled', '=', False),
					('amount_residual', '!=', 0),
				]
				# Por cobrar (asset_receivable)
				receivable_lines = self.env['account.move.line'].search(
					domain_base + [('account_id.account_type', '=', 'asset_receivable')]
				)
				receivable = sum(receivable_lines.mapped('amount_residual'))
				# Por pagar (liability_payable)
				payable_lines = self.env['account.move.line'].search(
					domain_base + [('account_id.account_type', '=', 'liability_payable')]
				)
				payable = abs(sum(payable_lines.mapped('amount_residual')))
				# Anticipos (buscar en cuentas marcadas como anticipo)
				advance_accounts = self.env['account.account'].search([
					('used_for_advance_payment', '=', True),
				])
				if advance_accounts:
					advance_lines = self.env['account.move.line'].search(
						domain_base + [('account_id', 'in', advance_accounts.ids)]
					)
					advance = sum(advance_lines.mapped('amount_residual'))
			payment.partner_receivable_balance = receivable
			payment.partner_payable_balance = payable
			payment.partner_advance_balance = advance

	# === Multi-payment method fields (siempre activo) === #
	enable_multi_payment_method = fields.Boolean(
		string='Habilitar Múltiples Formas de Pago',
		default=True,
		help='Permite utilizar múltiples formas de pago en un mismo pago/cobro'
	)

	# === Check number field === #
	check_number = fields.Char(
		string='Número de Cheque',
		copy=False,
		help='Número de cheque para pagos con este método'
	)

	# === Campos de registro de pago/cobro === #
	received_by_id = fields.Many2one(
		'res.users',
		string='Recibido por',
		default=lambda self: self.env.user,
		tracking=True,
		help='Usuario que recibió el cobro'
	)
	paid_by = fields.Char(
		string='Pagado por',
		help='Nombre de quien realizó el pago (persona física que entrega el dinero)'
	)
	bank_reference = fields.Char(
		string='Referencia Bancaria',
		copy=False,
		tracking=True,
		help='Número de registro, referencia de transferencia o comprobante bancario'
	)

	# === Payment method lines === #
	payment_method_line_ids = fields.One2many(
		'account.payment.method.line.detail',
		'payment_id',
		string='Formas de Pago',
		copy=False,
		help='Detalle de formas de pago utilizadas'
	)

	payment_method_total = fields.Monetary(
		string='Total Formas de Pago',
		currency_field='currency_id',
		compute='_compute_payment_method_total',
		store=True,
		help='Suma total de las formas de pago'
	)

	@api.depends('payment_method_line_ids', 'payment_method_line_ids.amount')
	def _compute_payment_method_total(self):
		for payment in self:
			payment.payment_method_total = sum(payment.payment_method_line_ids.mapped('amount'))

	# === Adjustment fields === #
	adjustment_amount = fields.Monetary(
		string='Ajuste',
		currency_field='currency_id',
		default=0.0,
		help='Monto de ajuste al pago'
	)

	adjustment_peso = fields.Boolean(
		string='Ajuste al Peso',
		default=False,
		help='Permite ajustar la diferencia al peso más cercano'
	)

	adjustment_account_id = fields.Many2one(
		'account.account',
		string='Cuenta de Ajuste',
		domain="[('active', '=', True)]",
		help='Cuenta contable para registrar el ajuste'
	)

	# === Early payment discount fields === #
	early_payment_discount = fields.Boolean(
		string='Descuento Pronto Pago',
		default=False,
		help='Aplicar descuento por pronto pago'
	)
	early_payment_discount_percent = fields.Float(
		string='% Descuento',
		digits=(5, 2),
		default=0.0,
		help='Porcentaje de descuento por pronto pago'
	)
	early_payment_discount_account_id = fields.Many2one(
		'account.account',
		string='Cuenta Descuento Pronto Pago',
		domain="[('active', '=', True)]",
		help='Cuenta contable para registrar el descuento por pronto pago'
	)

	# === Revert taxes (retention) fields === #
	revert_taxes = fields.Boolean(
		string='Revertir Impuestos',
		default=False,
		help='Permite revertir impuestos (retención) del pago'
	)
	revert_tax_ids = fields.Many2many(
		'account.tax',
		'payment_revert_tax_rel',
		'payment_id',
		'tax_id',
		string='Impuestos a Revertir',
		domain="[('type_tax_use', 'in', ['purchase', 'sale'])]",
		help='Seleccione los impuestos que desea revertir del pago'
	)

	# === Cash receipt fields === #
	is_cash_receipt = fields.Boolean(
		string='Es Recibo de Caja',
		compute='_compute_is_cash_receipt',
		store=True,
		help='Indica si este documento es un recibo de caja (cruce sin pago)'
	)

	cash_receipt_number = fields.Char(
		string='Número de Recibo de Caja',
		copy=False,
		readonly=True,
		help='Número consecutivo para recibos de caja (prefijo RC-)'
	)

	is_document_cross = fields.Boolean(
		string='Es Cruce de Documentos',
		default=False,
		help='Indica si este pago es un cruce de documentos (anticipo contra factura)'
	)

	# === Payment numbering (different from accounting entry) === #
	payment_number = fields.Char(
		string='Número de Pago/Cobro',
		copy=False,
		readonly=True,
		help='Número único de pago/cobro (RC- para Recibos de Cobro, CE- para Comprobantes de Egreso) diferente al número del asiento contable'
	)

	# === Subtotales por concepto === #
	subtotal_invoices = fields.Monetary(
		string='Subtotal Facturas',
		compute='_compute_payment_subtotals',
		currency_field='currency_id'
	)
	subtotal_taxes = fields.Monetary(
		string='Subtotal Impuestos',
		compute='_compute_payment_subtotals',
		currency_field='currency_id'
	)
	subtotal_advances = fields.Monetary(
		string='Subtotal Anticipos',
		compute='_compute_payment_subtotals',
		currency_field='currency_id'
	)
	subtotal_other = fields.Monetary(
		string='Otros Conceptos',
		compute='_compute_payment_subtotals',
		currency_field='currency_id'
	)
	total_to_pay = fields.Monetary(
		string='Total a Pagar',
		compute='_compute_payment_subtotals',
		currency_field='currency_id'
	)

	# === Widget HTML de totales detallados === #
	payment_totals = fields.Json(
		string='Totales de Pago',
		compute='_compute_payment_totals',
		help='JSON con totales agrupados por concepto para el widget'
	)

	payment_totals_html = fields.Html(
		string='Resumen de Totales',
		compute='_compute_payment_totals_html',
		help='HTML con totales agrupados por tipo de cuenta y concepto'
	)

	# === Resumen de facturas por rangos === #
	invoice_summary_note = fields.Html(
		string='Resumen de Documentos',
		compute='_compute_invoice_summary_note',
		help='Resumen de los documentos por rangos de monto y promedio'
	)

	# === Default analytic distribution for new lines === #
	default_analytic_distribution = fields.Json(
		string='Cuenta Analítica por Defecto',
		help='Distribución analítica que se aplicará a las nuevas líneas de pago'
	)

	invoice_cash_rounding_id = fields.Many2one(
		comodel_name='account.cash.rounding',
		string='Cash Rounding Method',
		readonly=True,
		help='Defines the smallest coinage of the currency that can be used to pay by cash.',
	)


	# === Buscar Documentos fields === #
	customer_invoice_ids = fields.Many2many(
		"account.move",
		"customer_invoice_payment_rel",
		'invoice_id',
		'payment_id',
		string="Buscar Documentos Clientes",
		domain="""[
			('state', '=', 'posted'),
			('payment_state', 'in', ['not_paid', 'partial']),
			('move_type', 'in', ['out_invoice', 'out_refund', 'out_receipt']),
			('amount_residual', '!=', 0)
		]"""
	)
	supplier_invoice_ids = fields.Many2many(
		"account.move",
		"supplier_invoice_payment_rel",
		'invoice_id',
		'payment_id',
		string="Buscar Documentos Proveedores",
		domain="""[
			('state', '=', 'posted'),
			('payment_state', 'in', ['not_paid', 'partial']),
			('move_type', 'in', ['in_invoice', 'in_refund', 'in_receipt']),
			('amount_residual', '!=', 0)
		]"""
	)
	account_move_payment_ids = fields.Many2many(
		"account.move.line",
		"account_move_payment_rel",
		'moe_line_id',
		'payment_id',
		string="Buscar Otros Documentos",
		domain="""[
			('amount_residual', '!=', 0),
			('parent_state', '=', 'posted'),
			('reconciled', '=', False),
			('account_id.account_type', 'in', ['asset_receivable', 'liability_payable']),
			('payment_id', '=', False)
		]"""
	)

	# === Widget de selección de facturas (campo dummy para el widget) === #
	invoice_selector = fields.Boolean(
		string="Selector de Facturas",
		default=False,
		store=False,
		help="Widget para seleccionar facturas pendientes estilo SAP"
	)
	
	invoice_id = fields.Many2one(
		comodel_name='account.move',
		string='Factura',
		required=False)

	# === Filtrar Documentos fields === #
	domain_account_move_lines = fields.Many2many("account.move.line", 'domain_account_move_line_pay_rel', string="restriccion de campos Lineas", compute="_compute_domain_accountmove_line")
	domain_move_lines = fields.Many2many("account.move", 'domain_move_line_pay_rel', string="restriccion de campos", compute="_compute_domain_move_line")

	# === Filtro de tipo de cuenta para documentos === #
	document_account_type = fields.Selection([
		('all', 'Todos'),
		('receivable', 'Por Cobrar'),
		('payable', 'Por Pagar'),
		('advance', 'Anticipos'),
	], string='Tipo de Cuenta', default='all',
	   help='Filtra los documentos según el tipo de cuenta: Por Cobrar, Por Pagar o Anticipos')

	# Documentos filtrados por tipo de cuenta
	filtered_document_ids = fields.Many2many(
		'account.move.line',
		'payment_filtered_document_rel',
		'payment_id',
		'move_line_id',
		string='Documentos Filtrados',
		compute='_compute_filtered_documents',
		help='Documentos del tercero filtrados por tipo de cuenta'
	)

	@api.depends('partner_id', 'document_account_type', 'payment_type')
	def _compute_filtered_documents(self):
		"""Filtra documentos del tercero según tipo de cuenta seleccionado"""
		for payment in self:
			if not payment.partner_id:
				payment.filtered_document_ids = [(5, 0, 0)]
				continue

			domain = [
				('partner_id', '=', payment.partner_id.id),
				('parent_state', '=', 'posted'),
				('reconciled', '=', False),
				('amount_residual', '!=', 0),
			]

			# Filtrar por tipo de cuenta
			if payment.document_account_type == 'receivable':
				domain.append(('account_id.account_type', '=', 'asset_receivable'))
			elif payment.document_account_type == 'payable':
				domain.append(('account_id.account_type', '=', 'liability_payable'))
			elif payment.document_account_type == 'advance':
				# Buscar cuentas de anticipo
				advance_accounts = self.env['account.account'].search([
					('used_for_advance_payment', '=', True),
				])
				if advance_accounts:
					domain.append(('account_id', 'in', advance_accounts.ids))
				else:
					domain.append(('id', '=', False))  # Sin resultados si no hay cuentas
			else:  # 'all'
				domain.append(('account_id.account_type', 'in', ['asset_receivable', 'liability_payable']))

			documents = self.env['account.move.line'].search(domain, limit=100)
			payment.filtered_document_ids = [(6, 0, documents.ids)]

	# === advance fields === #
	advance_type_id = fields.Many2one('advance.type', string="Tipo de anticipo")
	advance = fields.Boolean('Anticipo', default=False)
	code_advance = fields.Char(string="Número de anticipo", copy=False)
	partner_type = fields.Selection(selection_add=[
		('employee', 'Empleado'),
	], ondelete={'employee': 'set default'})

	# === writeoff fields === #
	writeoff_account_id = fields.Many2one('account.account', string="Cuenta de diferencia", copy=False,
		domain="[('active', '=', True)]")
	writeoff_label = fields.Char(string='Journal Item Label', default='Diferencia',
		help='Change label of the counterpart that will hold the payment difference')
	payment_difference_line = fields.Monetary(string="Diferencia de pago",
		store=True, readonly=True,
		tracking=True)
	current_exchange_rate = fields.Float(
		string='Current exchange rate',
		readonly=False,
		default=1
	)
	manual_currency_rate_active = fields.Boolean('Aplicar TRM Manual')
	manual_currency_rate = fields.Float('Rate', digits=(12, 12),readonly=True)
	exchange_diff_type = fields.Selection([
		('native', 'Diferencia Nativa'),
		('custom', 'Diferencia por Pago')
	], string='Tipo de Diferencia Cambiaria', default='native')

	# === Comisiones Bancarias === #
	bank_commission_id = fields.Many2one(
		'treasury.bank.commission',
		string='Configuración Comisión',
		compute='_compute_bank_commission',
		store=True,
		readonly=False,
		help='Configuración de comisión bancaria aplicable'
	)
	service_category = fields.Selection([
		('ach', 'Pagos ACH'),
		('ach_same_bank', 'Transferencia Mismo Banco'),
		('pse', 'PSE'),
		('cheque', 'Cheques'),
		('cheque_gerencia', 'Cheque Gerencia'),
		('consignacion', 'Consignaciones'),
		('recaudo_fisico', 'Recaudo Fisico'),
		('recaudo_digital', 'Recaudo Digital'),
		('pila', 'PILA'),
		('sebra', 'SEBRA'),
		('swift', 'Swift Internacional'),
		('qr', 'Pago QR'),
		('boton', 'Boton de Pagos'),
		('cuota_manejo', 'Cuota de Manejo'),
		('extracto', 'Extracto Bancario'),
		('certificacion', 'Certificacion Bancaria'),
		('chequera', 'Chequera'),
		('otro', 'Otro')
	], string='Categoria Servicio',
	   help='Categoria del servicio bancario para determinar comision')
	commission_mode = fields.Selection([
		('none', 'Sin Comisión'),
		('same_entry', 'En el Mismo Asiento'),
		('separate_entry', 'Asiento Separado')
	], string='Modo Comisión', default='none',
	   help='Cómo registrar la comisión bancaria')
	commission_amount = fields.Monetary(
		string='Comisión Base',
		currency_field='currency_id',
		compute='_compute_commission_amount',
		store=True,
		readonly=False
	)
	commission_tax_amount = fields.Monetary(
		string='Impuestos Comisión',
		currency_field='currency_id',
		compute='_compute_commission_amount',
		store=True
	)
	commission_total = fields.Monetary(
		string='Total Comisión',
		currency_field='currency_id',
		compute='_compute_commission_amount',
		store=True
	)
	commission_move_id = fields.Many2one(
		'account.move',
		string='Asiento Comisión',
		copy=False,
		readonly=True,
		help='Asiento contable de la comisión bancaria (modo separado)'
	)
	apply_bank_commission = fields.Boolean(
		string='Aplicar Comisión',
		default=False,
		help='Marcar para aplicar comisión bancaria a este pago'
	)

	@api.depends('journal_id', 'payment_method_line_id', 'payment_type', 'service_category')
	def _compute_bank_commission(self):
		"""Busca la configuración de comisión bancaria aplicable con fallback por banco"""
		Commission = self.env['treasury.bank.commission']
		for payment in self:
			commission = False
			if payment.journal_id:
				base_domain = [
					('payment_type', '=', payment.payment_type),
					('company_id', '=', payment.company_id.id),
					('active', '=', True),
					('is_exempt', '=', False),
					('charge_frequency', '=', 'transaction')
				]
				if payment.service_category:
					base_domain.append(('service_category', '=', payment.service_category))

				bank_id = payment.journal_id.bank_id.id if payment.journal_id.bank_id else False
				method_id = payment.payment_method_line_id.payment_method_id.id if payment.payment_method_line_id else False

				# 1. Buscar config específica (diario + método)
				if method_id:
					specific_domain = base_domain + [
						('journal_id', '=', payment.journal_id.id),
						('payment_method_id', '=', method_id)
					]
					commission = Commission.search(specific_domain, limit=1)

				# 2. Fallback: solo diario (sin método)
				if not commission:
					journal_domain = base_domain + [
						('journal_id', '=', payment.journal_id.id),
						('payment_method_id', '=', False)
					]
					commission = Commission.search(journal_domain, limit=1)

				# 3. Fallback: banco (res.bank) + método
				if not commission and bank_id and method_id:
					bank_method_domain = base_domain + [
						('bank_id', '=', bank_id),
						('journal_id', '=', False),
						('payment_method_id', '=', method_id)
					]
					commission = Commission.search(bank_method_domain, limit=1)

				# 4. Fallback: solo banco (res.bank)
				if not commission and bank_id:
					bank_domain = base_domain + [
						('bank_id', '=', bank_id),
						('journal_id', '=', False),
						('payment_method_id', '=', False)
					]
					commission = Commission.search(bank_domain, limit=1)

				# 5. Fallback: configuración genérica (sin banco ni diario ni método)
				if not commission:
					generic_domain = base_domain + [
						('bank_id', '=', False),
						('journal_id', '=', False),
						('payment_method_id', '=', False)
					]
					commission = Commission.search(generic_domain, limit=1)

			payment.bank_commission_id = commission

	@api.depends('amount', 'bank_commission_id', 'apply_bank_commission')
	def _compute_commission_amount(self):
		"""Calcula el monto de la comisión bancaria"""
		for payment in self:
			commission_amount = tax_amount = total = 0.0
			if payment.apply_bank_commission and payment.bank_commission_id:
				result = payment.bank_commission_id.calculate_commission(payment.amount)
				commission_amount = result.get('commission', 0.0)
				tax_amount = result.get('total_taxes', 0.0)
				total = result.get('total', 0.0)
			payment.commission_amount = commission_amount
			payment.commission_tax_amount = tax_amount
			payment.commission_total = total

	def action_calculate_commission(self):
		"""Botón para calcular y mostrar la comisión"""
		self.ensure_one()
		if not self.bank_commission_id:
			raise UserError(_("No hay configuración de comisión para este banco/método de pago."))
		self.apply_bank_commission = True
		return {
			'type': 'ir.actions.client',
			'tag': 'display_notification',
			'params': {
				'title': _('Comisión Calculada'),
				'message': _('Comisión: %s, Impuestos: %s, Total: %s') % (
					self.commission_amount, self.commission_tax_amount, self.commission_total
				),
				'type': 'success',
				'sticky': False,
			}
		}

	def _create_commission_move_lines(self):
		"""Crea las líneas de asiento para la comisión bancaria (modo same_entry)"""
		self.ensure_one()
		if not self.apply_bank_commission or not self.bank_commission_id:
			return []

		lines = []
		commission = self.bank_commission_id
		result = commission.calculate_commission(self.amount)
		base_amount = result.get('commission', 0.0)
		taxes = result.get('taxes', [])

		if base_amount <= 0:
			return []

		# Línea de gasto por comisión
		expense_account = commission.expense_account_id
		if not expense_account:
			raise UserError(_("Configure la cuenta de gasto bancario en la comisión: %s") % commission.name)

		lines.append({
			'name': _('Comisión Bancaria - %s') % commission.name,
			'account_id': expense_account.id,
			'debit': base_amount,
			'credit': 0.0,
			'partner_id': self.partner_id.id if self.partner_id else False,
		})

		# Líneas de impuestos
		for tax_vals in taxes:
			tax_account = tax_vals.get('account_id')
			if tax_account:
				lines.append({
					'name': tax_vals.get('name', 'Impuesto'),
					'account_id': tax_account,
					'debit': tax_vals.get('amount', 0.0),
					'credit': 0.0,
					'partner_id': self.partner_id.id if self.partner_id else False,
				})

		# Contrapartida al banco
		total = result.get('total', 0.0)
		bank_account = self.journal_id.default_account_id
		if bank_account:
			lines.append({
				'name': _('Cargo Comisión Bancaria'),
				'account_id': bank_account.id,
				'debit': 0.0,
				'credit': total,
				'partner_id': self.partner_id.id if self.partner_id else False,
			})

		return lines

	def _create_separate_commission_entry(self):
		"""Crea un asiento separado para la comisión bancaria"""
		self.ensure_one()
		if not self.apply_bank_commission or not self.bank_commission_id:
			return False

		commission = self.bank_commission_id
		result = commission.calculate_commission(self.amount)
		total = result.get('total', 0.0)

		if total <= 0:
			return False

		expense_account = commission.expense_account_id
		if not expense_account:
			raise UserError(_("Configure la cuenta de gasto bancario en la comisión: %s") % commission.name)

		bank_account = self.journal_id.default_account_id

		move_vals = {
			'move_type': 'entry',
			'date': self.date,
			'journal_id': self.journal_id.id,
			'ref': _('Comisión - %s') % (self.name or self.payment_number or ''),
			'line_ids': []
		}

		# Línea de gasto
		base_amount = result.get('commission', 0.0)
		move_vals['line_ids'].append((0, 0, {
			'name': _('Comisión Bancaria - %s') % commission.name,
			'account_id': expense_account.id,
			'debit': base_amount,
			'credit': 0.0,
			'partner_id': self.partner_id.id if self.partner_id else False,
		}))

		# Líneas de impuestos
		for tax_vals in result.get('taxes', []):
			tax_account = tax_vals.get('account_id')
			if tax_account:
				move_vals['line_ids'].append((0, 0, {
					'name': tax_vals.get('name', 'Impuesto'),
					'account_id': tax_account,
					'debit': tax_vals.get('amount', 0.0),
					'credit': 0.0,
					'partner_id': self.partner_id.id if self.partner_id else False,
				}))

		# Contrapartida banco
		if bank_account:
			move_vals['line_ids'].append((0, 0, {
				'name': _('Cargo Comisión Bancaria'),
				'account_id': bank_account.id,
				'debit': 0.0,
				'credit': total,
				'partner_id': self.partner_id.id if self.partner_id else False,
			}))

		move = self.env['account.move'].create(move_vals)
		move.action_post()
		self.commission_move_id = move.id
		return move

	@api.onchange('date', 'currency_id')
	def _onchange_date_aux(self):
		for record in self:
			amount = 0
			rate = 0
			if record.manual_currency_rate_active:
				break
			if record.currency_id:
				rate = self.env['res.currency']._get_conversion_rate(
					from_currency=record.company_currency_id,
					to_currency=record.currency_id,
					company=record.company_id,
					date=record.date or record.date or fields.Date.context_today(record),
				)
				amount = 1 / rate
			else:
				amount = 1
			record.current_exchange_rate = amount or 1
			record.manual_currency_rate = rate or 1

	@api.constrains("manual_currency_rate")
	def _check_manual_currency_rate(self):
		for record in self:
			if record.manual_currency_rate_active:
				if record.manual_currency_rate == 0:
					raise UserError(_('El campo tipo de cambio es obligatorio, complételo.'))

	@api.onchange('manual_currency_rate_active', 'currency_id','current_exchange_rate')
	def check_currency_id(self):
		if self.manual_currency_rate_active:
			if self.currency_id == self.company_id.currency_id:
				self.manual_currency_rate_active = False
				raise UserError(
					_('La moneda de la empresa y la moneda de la factura son las mismas. No se puede agregar el tipo de cambio manual para la misma moneda.'
						))
			else:
				self.manual_currency_rate = 1 / self.current_exchange_rate or 1

	@api.onchange('manual_currency_rate_active')
	def _onchange_manual_currency_rate_active(self):
		if self.manual_currency_rate_active:
			self.exchange_diff_type = 'custom'
		else:
			self.exchange_diff_type = 'native'

	@api.depends('payment_line_ids', 'payment_line_ids.move_line_id', 'amount')
	def _compute_is_cash_receipt(self):
		"""
		Determina si este pago es un recibo de caja.
		Un recibo de caja es un cruce de documentos sin movimiento de efectivo.
		"""
		for payment in self:
			# Es recibo de caja si todas las líneas son cruces de documentos
			# y no hay movimiento de banco/caja (amount = 0 o solo cruces)
			if payment.payment_line_ids:
				has_document_crosses = any(
					line.move_line_id and not line.is_main
					for line in payment.payment_line_ids
				)
				# Si tiene documentos cruzados y el monto es solo cruces
				payment.is_cash_receipt = has_document_crosses and not payment.paired_internal_transfer_payment_id
			else:
				payment.is_cash_receipt = False

	@api.depends('payment_line_ids', 'payment_line_ids.payment_amount', 'payment_line_ids.display_type', 'payment_line_ids.to_pay', 'payment_line_ids.account_id')
	def _compute_payment_subtotals(self):
		"""Calcula subtotales agrupados por tipo de línea."""
		for payment in self:
			all_lines = payment.payment_line_ids.filtered(lambda l: not l.is_main)

			# Función helper para detectar líneas de impuestos
			def is_tax_line(l):
				if l.display_type == 'tax' or l.auto_tax_line:
					return True
				# Detectar por cuenta de impuestos (código 2408* es IVA en Colombia)
				if l.account_id and l.account_id.code:
					code = l.account_id.code
					# 2408 = IVA Generado, 2404 = IVA Descontable, 1355 = Anticipo IVA, 240810 = IVA Descontable
					if code.startswith('2408') or code.startswith('2404') or code.startswith('1355'):
						return True
				return False

			# Líneas activas para pago (to_pay=True)
			active_lines = all_lines.filtered(lambda l: l.to_pay)

			# Facturas (bill, invoice, entry, reverse) - solo activas
			invoice_lines = active_lines.filtered(lambda l: l.display_type in ('bill', 'invoice', 'entry', 'reverse') and not is_tax_line(l))
			payment.subtotal_invoices = sum(invoice_lines.mapped('payment_amount'))

			# Impuestos - SIEMPRE incluir, independiente de to_pay
			tax_lines = all_lines.filtered(is_tax_line)
			payment.subtotal_taxes = sum(tax_lines.mapped('payment_amount'))

			# Anticipos - solo activos
			advance_lines = active_lines.filtered(lambda l: l.display_type == 'advance')
			payment.subtotal_advances = sum(advance_lines.mapped('payment_amount'))

			# Otros (excluyendo impuestos detectados) - solo activos
			other_lines = active_lines.filtered(lambda l: l.display_type not in ('bill', 'invoice', 'entry', 'reverse', 'tax', 'advance') and not is_tax_line(l))
			payment.subtotal_other = sum(other_lines.mapped('payment_amount'))

			# Total
			payment.total_to_pay = payment.subtotal_invoices + payment.subtotal_taxes + payment.subtotal_advances + payment.subtotal_other

	@api.depends('payment_line_ids', 'payment_line_ids.payment_amount', 'payment_line_ids.account_id', 'payment_line_ids.to_pay', 'currency_id', 'amount', 'payment_difference_line')
	def _compute_payment_totals(self):
		"""
		Genera JSON con totales agrupados por concepto para el widget.
		Similar a tax_totals de account.move.
		"""
		for payment in self:
			currency = payment.currency_id or self.env.company.currency_id
			all_lines = payment.payment_line_ids.filtered(lambda l: not l.is_main)

			# Helper para detectar líneas de impuestos
			def is_tax_line(l):
				if l.display_type == 'tax' or l.auto_tax_line:
					return True
				if l.account_id and l.account_id.code:
					code = l.account_id.code
					if code.startswith('2408') or code.startswith('2404') or code.startswith('1355'):
						return True
				return False

			# Helper para obtener tipo de cuenta
			def get_account_type(account):
				if not account or not account.code:
					return 'otros'
				code = account.code
				if code.startswith('1'):
					return 'activo'
				elif code.startswith('2'):
					return 'pasivo'
				elif code.startswith('3'):
					return 'patrimonio'
				elif code.startswith('4'):
					return 'ingreso'
				elif code.startswith('5') or code.startswith('6') or code.startswith('7'):
					return 'gasto'
				return 'otros'

			# Agrupar por tipo de cuenta
			by_account_type = {
				'activo': {'name': 'Activos', 'icon': 'fa-building', 'color': 'primary', 'accounts': {}, 'total': 0},
				'pasivo': {'name': 'Pasivos', 'icon': 'fa-credit-card', 'color': 'danger', 'accounts': {}, 'total': 0},
				'patrimonio': {'name': 'Patrimonio', 'icon': 'fa-bank', 'color': 'info', 'accounts': {}, 'total': 0},
				'ingreso': {'name': 'Ingresos', 'icon': 'fa-arrow-up', 'color': 'success', 'accounts': {}, 'total': 0},
				'gasto': {'name': 'Gastos', 'icon': 'fa-arrow-down', 'color': 'warning', 'accounts': {}, 'total': 0},
				'otros': {'name': 'Otros', 'icon': 'fa-question', 'color': 'secondary', 'accounts': {}, 'total': 0},
			}

			# Agrupar impuestos por cuenta
			tax_lines = all_lines.filtered(is_tax_line)
			taxes_by_account = {}
			for line in tax_lines:
				account_name = line.account_id.display_name if line.account_id else 'Sin cuenta'
				if account_name not in taxes_by_account:
					taxes_by_account[account_name] = 0.0
				taxes_by_account[account_name] += line.payment_amount

			# Líneas activas
			active_lines = all_lines.filtered(lambda l: l.to_pay)

			# Agrupar todas las líneas por tipo de cuenta
			for line in all_lines:
				account_type = get_account_type(line.account_id)
				account_name = line.account_id.display_name if line.account_id else 'Sin cuenta'

				if account_name not in by_account_type[account_type]['accounts']:
					by_account_type[account_type]['accounts'][account_name] = 0.0
				by_account_type[account_type]['accounts'][account_name] += line.payment_amount
				by_account_type[account_type]['total'] += line.payment_amount

			# Calcular subtotales tradicionales
			invoice_lines = active_lines.filtered(lambda l: l.display_type in ('bill', 'invoice', 'entry', 'reverse') and not is_tax_line(l))
			subtotal_invoices = sum(invoice_lines.mapped('payment_amount'))

			advance_lines = active_lines.filtered(lambda l: l.display_type == 'advance')
			subtotal_advances = sum(advance_lines.mapped('payment_amount'))

			other_lines = active_lines.filtered(lambda l: l.display_type not in ('bill', 'invoice', 'entry', 'reverse', 'tax', 'advance') and not is_tax_line(l))
			subtotal_other = sum(other_lines.mapped('payment_amount'))

			subtotal_taxes = sum(tax_lines.mapped('payment_amount'))

			# Construir grupos por concepto
			concept_groups = []

			if subtotal_invoices:
				concept_groups.append({
					'name': 'Documentos',
					'amount': subtotal_invoices,
					'formatted_amount': currency.format(subtotal_invoices),
					'icon': 'fa-file-text-o',
					'color': 'primary',
				})

			if subtotal_taxes:
				tax_details = []
				for account_name, amount in taxes_by_account.items():
					tax_details.append({
						'name': account_name,
						'amount': amount,
						'formatted_amount': currency.format(amount),
					})
				concept_groups.append({
					'name': 'Impuestos',
					'amount': subtotal_taxes,
					'formatted_amount': currency.format(subtotal_taxes),
					'icon': 'fa-percent',
					'color': 'info',
					'details': tax_details,
				})

			if subtotal_advances:
				concept_groups.append({
					'name': 'Anticipos',
					'amount': subtotal_advances,
					'formatted_amount': currency.format(subtotal_advances),
					'icon': 'fa-clock-o',
					'color': 'warning',
				})

			if subtotal_other:
				concept_groups.append({
					'name': 'Otros',
					'amount': subtotal_other,
					'formatted_amount': currency.format(subtotal_other),
					'icon': 'fa-ellipsis-h',
					'color': 'secondary',
				})

			# Construir grupos por tipo de cuenta
			account_groups = []
			for type_key, type_data in by_account_type.items():
				if type_data['total'] != 0:
					details = []
					for account_name, amount in type_data['accounts'].items():
						if amount != 0:
							details.append({
								'name': account_name,
								'amount': amount,
								'formatted_amount': currency.format(amount),
							})
					account_groups.append({
						'name': type_data['name'],
						'amount': type_data['total'],
						'formatted_amount': currency.format(type_data['total']),
						'icon': type_data['icon'],
						'color': type_data['color'],
						'details': details,
					})

			total = subtotal_invoices + subtotal_taxes + subtotal_advances + subtotal_other
			difference = payment.payment_difference_line or 0.0

			payment.payment_totals = {
				'currency_id': currency.id,
				'currency_symbol': currency.symbol,
				'currency_position': currency.position,
				'concept_groups': concept_groups,
				'account_groups': account_groups,
				'total': total,
				'formatted_total': currency.format(total),
				'amount_payment': payment.amount,
				'formatted_amount_payment': currency.format(payment.amount),
				'difference': difference,
				'formatted_difference': currency.format(difference),
				'has_difference': abs(difference) > 0.01,
			}

	@api.depends('payment_totals')
	def _compute_payment_totals_html(self):
		"""Genera HTML estilo nativo Odoo con totales agrupados."""
		for payment in self:
			totals = payment.payment_totals or {}
			concept_groups = totals.get('concept_groups', [])
			account_groups = totals.get('account_groups', [])
			formatted_total = totals.get('formatted_total', '$ 0')
			formatted_difference = totals.get('formatted_difference', '$ 0')
			has_difference = totals.get('has_difference', False)

			html = '<div class="oe_subtotal_footer o_tax_total oe_right">'
			html += '<table class="table table-sm mb-0" style="width: auto; min-width: 400px;">'

			# Subtotales por concepto
			for group in concept_groups:
				html += '<tr class="border-bottom">'
				html += f'<td class="text-end text-muted py-1">{group.get("name", "")}:</td>'
				html += f'<td class="text-end fw-semibold py-1" style="width: 150px;">{group.get("formatted_amount", "")}</td>'
				html += '</tr>'

				# Detalles (impuestos desglosados)
				for detail in group.get('details', []):
					html += '<tr class="border-bottom bg-light">'
					html += f'<td class="text-end text-muted small fst-italic py-1 ps-4">{detail.get("name", "")}</td>'
					html += f'<td class="text-end small py-1">{detail.get("formatted_amount", "")}</td>'
					html += '</tr>'

			# Separador
			html += '<tr><td colspan="2" class="py-1"></td></tr>'

			# Por tipo de cuenta
			html += '<tr class="bg-secondary-subtle"><td colspan="2" class="text-center small fw-bold py-1">Por Tipo de Cuenta</td></tr>'
			for group in account_groups:
				color = group.get('color', 'secondary')
				html += f'<tr class="border-bottom">'
				html += f'<td class="text-end py-1"><span class="badge bg-{color} me-1">{group.get("name", "")}</span></td>'
				html += f'<td class="text-end fw-semibold py-1">{group.get("formatted_amount", "")}</td>'
				html += '</tr>'

				# Detalles por cuenta
				for detail in group.get('details', []):
					html += '<tr class="border-bottom">'
					html += f'<td class="text-end text-muted small py-1 ps-4" style="max-width: 250px;">{detail.get("name", "")}</td>'
					html += f'<td class="text-end small py-1">{detail.get("formatted_amount", "")}</td>'
					html += '</tr>'

			# Total
			html += '<tr class="bg-primary text-white">'
			html += '<td class="text-end fw-bold fs-5 py-2">TOTAL:</td>'
			html += f'<td class="text-end fw-bold fs-5 py-2">{formatted_total}</td>'
			html += '</tr>'

			# Diferencia
			if has_difference:
				html += '<tr class="bg-warning-subtle">'
				html += '<td class="text-end text-danger fw-semibold py-1"><i class="fa fa-exclamation-triangle me-1"></i>Diferencia:</td>'
				html += f'<td class="text-end text-danger fw-bold py-1">{formatted_difference}</td>'
				html += '</tr>'

			html += '</table></div>'

			payment.payment_totals_html = html

	@api.depends('payment_line_ids', 'payment_line_ids.payment_amount', 'currency_id')
	def _compute_invoice_summary_note(self):
		"""
		Calcula un resumen de los documentos por rangos de monto y el promedio.
		Rangos en COP (ajustar según moneda):
		- Pequeño: < 500,000
		- Mediano: 500,000 - 5,000,000
		- Grande: 5,000,000 - 50,000,000
		- Muy Grande: > 50,000,000
		"""
		for payment in self:
			# Solo considerar líneas de documentos (no las líneas main/counterpart)
			doc_lines = payment.payment_line_ids.filtered(
				lambda l: not l.is_main and l.move_line_id
			)

			if not doc_lines:
				payment.invoice_summary_note = False
				continue

			# Obtener montos absolutos
			amounts = [abs(line.payment_amount) for line in doc_lines]
			total_docs = len(amounts)
			total_amount = sum(amounts)
			avg_amount = total_amount / total_docs if total_docs > 0 else 0

			# Definir rangos (en COP)
			ranges = {
				'pequeño': {'min': 0, 'max': 500000, 'count': 0, 'total': 0, 'label': '< $500K'},
				'mediano': {'min': 500000, 'max': 5000000, 'count': 0, 'total': 0, 'label': '$500K - $5M'},
				'grande': {'min': 5000000, 'max': 50000000, 'count': 0, 'total': 0, 'label': '$5M - $50M'},
				'muy_grande': {'min': 50000000, 'max': float('inf'), 'count': 0, 'total': 0, 'label': '> $50M'},
			}

			# Clasificar cada documento
			for amount in amounts:
				for key, range_data in ranges.items():
					if range_data['min'] <= amount < range_data['max']:
						range_data['count'] += 1
						range_data['total'] += amount
						break

			# Construir HTML
			currency = payment.currency_id or payment.company_id.currency_id
			html = '<div style="font-size: 12px;">'
			html += f'<p><strong>📊 Resumen de {total_docs} documento(s)</strong></p>'
			html += '<table style="width:100%; border-collapse: collapse;">'
			html += '<tr style="background: #f5f5f5;"><th style="text-align:left; padding:4px;">Rango</th><th style="text-align:center; padding:4px;">Cant.</th><th style="text-align:right; padding:4px;">Subtotal</th></tr>'

			for key, range_data in ranges.items():
				if range_data['count'] > 0:
					subtotal_fmt = '{:,.0f}'.format(range_data['total']).replace(',', '.')
					html += f'<tr><td style="padding:4px;">{range_data["label"]}</td>'
					html += f'<td style="text-align:center; padding:4px;">{range_data["count"]}</td>'
					html += f'<td style="text-align:right; padding:4px;">${subtotal_fmt}</td></tr>'

			html += '</table>'

			# Promedio
			avg_fmt = '{:,.0f}'.format(avg_amount).replace(',', '.')
			total_fmt = '{:,.0f}'.format(total_amount).replace(',', '.')
			html += f'<hr style="margin: 8px 0;"/>'
			html += f'<p><strong>💰 Total:</strong> ${total_fmt} {currency.name}</p>'
			html += f'<p><strong>📈 Promedio:</strong> ${avg_fmt} {currency.name}</p>'
			html += '</div>'

			payment.invoice_summary_note = html

	@api.onchange('enable_multi_partner')
	def _onchange_enable_multi_partner(self):
		"""
		Al activar multi-tercero, actualiza el contexto para las líneas
		"""
		if self.enable_multi_partner:
			# Permitir editar partner_id en las líneas
			return {
				'context': {
					'enable_multi_partner': True
				}
			}

	@api.onchange('adjustment_peso')
	def _onchange_adjustment_peso(self):
		"""
		Al activar ajuste al peso, calcula el ajuste automáticamente
		"""
		if self.adjustment_peso and self.currency_id:
			# Calcular el redondeo al peso más cercano
			total_payment = sum(line.payment_amount for line in self.payment_line_ids if not line.is_main and line.display_type != 'rounding')
			rounded_amount = self.currency_id.round(total_payment)
			self.adjustment_amount = rounded_amount - total_payment

			# Asignar cuenta de ajuste según si es ganancia o pérdida
			if not self.adjustment_account_id:
				company = self.company_id or self.env.company
				if self.adjustment_amount > 0:
					self.adjustment_account_id = company.income_currency_exchange_account_id
				else:
					self.adjustment_account_id = company.expense_currency_exchange_account_id
		else:
			# Limpiar valores cuando se desactiva
			self.adjustment_amount = 0.0

	def open_reconcile_view(self):
		return self.move_id.line_ids.open_reconcile_view()

	@api.depends('payment_method_line_id', 'journal_id')
	def _compute_outstanding_account_id(self):
		"""
		Compute outstanding_account_id con fallback al default_account_id del journal.

		Prioridad:
		1. payment_method_line_id.payment_account_id (cuenta específica del método de pago)
		2. journal_id.default_account_id (cuenta por defecto del diario banco/caja)
		"""
		for pay in self:
			# Prioridad 1: Cuenta del método de pago
			if pay.payment_method_line_id and pay.payment_method_line_id.payment_account_id:
				pay.outstanding_account_id = pay.payment_method_line_id.payment_account_id
			# Prioridad 2: Cuenta por defecto del diario
			elif pay.journal_id and pay.journal_id.default_account_id:
				pay.outstanding_account_id = pay.journal_id.default_account_id
			else:
				pay.outstanding_account_id = False

	@api.depends('journal_id')
	def _compute_currency_id(self):
		for pay in self:
			pay.currency_id = pay.journal_id.currency_id or pay.journal_id.company_id.currency_id or self.env.company.currency_id.id


	@api.onchange('payment_line_ids','payment_line_ids.tax_ids')
	def _onchange_matched_manual_ids(self, force_update = False):
		in_draft_mode = self != self._origin
		
		def need_update():
			amount = 0
			for line in self.payment_line_ids:
				if line.auto_tax_line:
					amount -= line.balance
					continue
				if line.tax_ids:
					balance_taxes_res = line.tax_ids._origin.compute_all(
						line.invoice_id.amount_untaxed  or line.payment_amount or line.balance,
						currency=line.currency_id,
						quantity=1,
						product=line.product_id,
						partner=line.partner_id,
						is_refund=False,
						handle_price_include=True,
					)
					for tax_res in balance_taxes_res.get("taxes"):
						amount += tax_res['amount']
			return amount 
		
		if not force_update and not need_update():
			return
		
		to_remove = self.env['account.payment.detail']
		if self.payment_line_ids:
			for line in list(self.payment_line_ids):
				if line.auto_tax_line:
					to_remove += line
					continue
				if line.tax_ids:
					balance_taxes_res = line.tax_ids._origin.compute_all(
						line.invoice_id.amount_untaxed or line.payment_amount or line.balance,
						currency=line.currency_id,
						quantity=1,
						product=line.product_id,
						partner=line.partner_id,
						is_refund=False,
						handle_price_include=True,
					)
					for tax_res in balance_taxes_res.get("taxes"):
						create_method = in_draft_mode and line.new or line.create
						create_method({
							'payment_id' : self.id,
							'partner_id' : line.partner_id.id,
							'account_id' : tax_res['account_id'],
							'name' : tax_res['name'],
							'payment_amount' : tax_res['amount'],
							'tax_repartition_line_id' : tax_res['tax_repartition_line_id'],
							'tax_tag_ids' : tax_res['tag_ids'],
							'auto_tax_line' : True,
							'tax_line_id2' :tax_res['id'],
							'tax_base_amount' : line.invoice_id.amount_untaxed or line.payment_amount or line.balance,
							'tax_line_id' : line.id,
							})
			
			if in_draft_mode:
				self.payment_line_ids -=to_remove
			else:
				to_remove.unlink()

	def _prepare_move_line_default_vals(self, write_off_line_vals=None, force_balance=None):
		if not self.payment_line_ids:
			return super()._prepare_move_line_default_vals(write_off_line_vals,force_balance)

		return [
			{
				'debit': line.debit,
				'credit': line.credit,
				'balance': line.debit - line.credit,
				'amount_currency': line.amount_currency or (line.debit - line.credit),
				'journal_id': self.journal_id.id,
				'account_id': line.account_id.id,
				'analytic_distribution': line.analytic_distribution or False,
				'tax_ids': [(6, 0, line.tax_ids.ids)],
				'tax_tag_ids': [(6, 0, line.tax_tag_ids.ids)],
				'tax_repartition_line_id': line.tax_repartition_line_id.id,
				'tax_base_amount': line.tax_base_amount,
				#'inv_id': line.invoice_id.id,
				'line_pay': line.move_line_id.id,
				'date_maturity': self.date,
				'partner_id': line.partner_id.id,  # RESPETA el partner_id de la línea, NO usa commercial_partner_id
				'currency_id': self.currency_id.id,
				'payment_id': self.id,
                **line._get_counterpart_move_name()
			}
			for line in self.payment_line_ids
		]


	@api.onchange('advance_type_id')
	def _onchange_advance_type_id(self):
		self._onchange_payment_type()

	@api.onchange('advance')
	def _onchange_advance(self):
		res = {}
		if not self.reconciled_invoice_ids:
			if not self.advance:
				self.advance_type_id = False
		if self.advance:
			self.advance_type_id = False
			res['domain'] = {'advance_type_id': [('internal_type','=', self.payment_type == 'outbound' and 'asset_receivable' or 'liability_payable')]}
		return res

	def _get_moves_domain(self):
		domain = [
			("amount_residual", "!=", 0.0),
			("state", "=", "posted"),
			("company_id", "=", self.company_id.id),
			(
				"commercial_partner_id",
				"=",
				self.partner_id.commercial_partner_id.id,
			),
		]
		if self.partner_type == "supplier":
			if self.payment_type == "outbound":
				domain.append(("move_type", "in", ("in_invoice", "in_receipt")))
			if self.payment_type == "inbound":
				domain.append(("move_type", "=", "in_refund"))
		elif self.partner_type == "customer":
			if self.payment_type == "outbound":
				domain.append(("move_type", "=", "out_refund"))
			if self.payment_type == "inbound":
				domain.append(("move_type", "in", ("out_invoice", "out_receipt")))
		return domain

	def _filter_amls(self, amls):
		return amls.filtered(
			lambda x: x.partner_id.commercial_partner_id.id
			== self.partner_id.commercial_partner_id.id
			and x.amount_residual != 0
			and x.account_id.account_type in ("asset_receivable", "liability_payable")
		)

	def _hook_create_new_line(self, invoice, aml, amount_to_apply,amount_residual):
		line_model = self.env["account.payment.detail"]
		if amount_residual > 0:
			amount_to_apply *= -1
		self.ensure_one()
		return line_model.create(
			{
				"payment_id": self.id,
				"name": invoice.name + str(aml.ref),
				"move_id": invoice.id,
				"move_line_id": aml.id,
				"account_id": aml.account_id.id,
				"partner_id": self.partner_id.commercial_partner_id.id,
				"payment_amount": amount_to_apply,
			}
		)

	def action_propose_payment_distribution(self):
		move_model = self.env["account.move"]
		for rec in self:
			if self.paired_internal_transfer_payment_id:
				continue
			domain = self._get_moves_domain()
			pending_invoices = move_model.search(domain, order="invoice_date_due ASC")
			pending_amount = rec.amount
			rec.payment_line_ids.filtered(lambda line: not line.is_main or line.display_type == 'asset_cash').unlink()
			for invoice in pending_invoices:
				for aml in self._filter_amls(invoice.line_ids):
					amount_to_apply = 0
					amount_residual = rec.company_id.currency_id._convert(
						aml.amount_residual,
						rec.currency_id,
						rec.company_id,
						date=rec.date,
					)
					if pending_amount >= 0:
						amount_to_apply = min(abs(amount_residual), pending_amount)
						pending_amount -= abs(amount_residual)
						# Check if both amounts are negative to adjust the sign

					rec._hook_create_new_line(invoice, aml, amount_to_apply,amount_residual)
			rec._recompute_dynamic_lines_payment()

	def action_delete_counterpart_lines(self):
		if self.payment_line_ids and self.state == "draft":
			self.payment_line_ids = [(5, 0, 0)]
			self._recompute_dynamic_lines_payment()

	def action_post(self):
		for rec in self:
			# ========== GENERAR NÚMEROS ÚNICOS PARA PAGOS/COBROS ==========
			# Estos números son independientes del número del asiento contable

			# Si es recibo de caja (cruce sin movimiento de efectivo)
			if rec.is_cash_receipt and not rec.cash_receipt_number:
				sequence_code = ''
				if rec.partner_type == 'customer':
					sequence_code = 'account.cash.receipt.customer'
				elif rec.partner_type == 'supplier':
					sequence_code = 'account.cash.receipt.supplier'
				elif rec.partner_type == 'employee':
					sequence_code = 'account.cash.receipt.employee'

				if sequence_code:
					rec.cash_receipt_number = self.env['ir.sequence'].with_context(ir_sequence_date=rec.date).next_by_code(sequence_code)
					if not rec.cash_receipt_number:
						raise UserError(_("Debe definir una secuencia para %s en su compañía.") % (sequence_code,))

			# Si es pago/cobro con movimiento de efectivo (no es recibo de caja ni anticipo)
			elif not rec.is_cash_receipt and not rec.advance and not rec.payment_number:
				sequence_code = ''

				# INGRESOS (Cobros)
				if rec.payment_type == 'inbound' and rec.partner_type == 'customer':
					sequence_code = 'account.payment.inbound.customer'

				# EGRESOS (Pagos)
				elif rec.payment_type == 'outbound':
					if rec.partner_type == 'supplier':
						sequence_code = 'account.payment.outbound.supplier'
					elif rec.partner_type == 'employee':
						sequence_code = 'account.payment.outbound.employee'

				if sequence_code:
					rec.payment_number = self.env['ir.sequence'].with_context(ir_sequence_date=rec.date).next_by_code(sequence_code)
					if not rec.payment_number:
						raise UserError(_("Debe definir una secuencia para %s en su compañía.") % (sequence_code,))

			if not rec.code_advance:
				sequence_code = ''
				if rec.advance:
					if rec.partner_type == 'customer':
						sequence_code = 'account.payment.advance.customer'
					if rec.partner_type == 'supplier':
						sequence_code = 'account.payment.advance.supplier'
					if rec.partner_type == 'employee':
						sequence_code = 'account.payment.advance.employee'

				rec.code_advance = self.env['ir.sequence'].with_context(ir_sequence_date=rec.date).next_by_code(sequence_code)
				if not rec.code_advance and rec.advance:
					raise UserError(_("You have to define a sequence for %s in your company.") % (sequence_code,))
			if not rec.name:
				if rec.partner_type == 'employee':
					sequence_code = 'account.payment.employee'
					rec.name = self.env['ir.sequence'].with_context(ir_sequence_date=rec.date).next_by_code(sequence_code)
					if not rec.name:
						raise UserError(_("You have to define a sequence for %s in your company.") % (sequence_code,))
			if rec.payment_line_ids and not rec.paired_internal_transfer_payment_id:
				# Procesar diferencias en cambio antes de confirmar (modo same_entry)
				config = rec._get_exchange_diff_config()
				if config['mode'] == 'same_entry':
					rec._create_grouped_exchange_diff_lines()

				rec.move_id.line_ids.unlink()
				rec.move_id.line_ids = [
					(0, 0, line_vals) for line_vals in rec._prepare_move_line_default_vals()
				]
				super().action_post()
				for line in rec.move_id.line_ids:
					invoice_line = line.line_pay
					if line and invoice_line:
						if (invoice_line.account_id == line.account_id and
							invoice_line.partner_id == line.partner_id and
							not invoice_line.reconciled):
							(line + invoice_line).with_context(skip_account_move_synchronization=True).reconcile()

				# Procesar diferencias en cambio después de confirmar (modo separate_entry)
				if config['mode'] == 'separate_entry':
					rec._process_exchange_differences_after_post()
			else:
				super(AccountPayment, rec).action_post()

			# === Procesar comisión bancaria después de confirmar ===
			if rec.apply_bank_commission and rec.bank_commission_id and rec.commission_mode == 'separate_entry':
				rec._create_separate_commission_entry()

	@api.onchange('payment_type')
	def _onchange_payment_type(self):
		self.change_destination_account = None

	@api.onchange('reconciled_invoice_ids', 'payment_type', 'partner_type', 'partner_id', 'journal_id', 'destination_account_id')
	def _change_destination_account(self):
		change_destination_account = '0'
		account_id = None
		partner = self.partner_id.with_context(company_id=self.company_id.id)
		if self.reconciled_invoice_ids:
			self.change_destination_account = self.reconciled_invoice_ids[0].account_id.id
			return
		elif self.paired_internal_transfer_payment_id:
			#self._onchange_amount()
			if not self.company_id.transfer_account_id.id:
				raise UserError(_('There is no Transfer Account defined in the accounting settings. Please define one to be able to confirm this transfer.'))
			account_id = self.company_id.transfer_account_id.id
		elif self.partner_id:
			if self.partner_type == 'customer':
				account_id = partner.property_account_receivable_id.id
			else:
				account_id = partner.property_account_payable_id.id
		elif self.partner_type == 'customer':
			default_account = partner.property_account_receivable_id
			account_id = default_account.id
		elif self.partner_type == 'supplier':
			default_account = partner.property_account_payable_id
			account_id = default_account.id
		if self.destination_account_id.id != account_id:
			change_destination_account = self.destination_account_id.id
		self.change_destination_account = change_destination_account

	@api.depends('journal_id','partner_id','paired_internal_transfer_payment_id','reconciled_invoice_ids','journal_id','payment_type', 'partner_type', 'partner_id', 'change_destination_account', 'advance_type_id')
	def _compute_destination_account_id(self):
		for val in self:
			if val.change_destination_account not in (False,'0') :
				val.destination_account_id = int(val.change_destination_account)
			if val.advance_type_id:
				val.destination_account_id = val.advance_type_id.account_id.id
			else:
				super(AccountPayment, self)._compute_destination_account_id()
			if val.partner_type == 'employee':
				val.destination_account_id = int(val.change_destination_account)

	def _get_liquidity_move_line_vals(self, amount):
		res = super(AccountPayment, self)._get_liquidity_move_line_vals(amount)
		res.update(
			account_id = self.outstanding_account_id and self.outstanding_account_id.id or res.get('account_id'),
			name = self.advance and self.code_advance or res.get('name')
			)
		return res

	def button_journal_difference_entries(self):
		return {
			'name': _('Diarios'),
			'view_type': 'form',
			'view_mode': 'list,form',
			'res_model': 'account.move',
			'view_id': False,
			'type': 'ir.actions.act_window',
			'domain': [('id', 'in', self.move_diff_ids.ids)],
		}

	# =========================================================================
	# MÉTODOS PARA DIFERENCIA EN CAMBIO CONFIGURABLE
	# =========================================================================

	def _get_exchange_diff_config(self):
		"""Obtiene la configuración de diferencia en cambio de la compañía."""
		company = self.company_id or self.env.company
		return {
			'mode': company.exchange_diff_mode or 'separate_entry',
			'group_mode': company.exchange_diff_group_mode or 'per_line',
			'link_document': company.exchange_diff_link_document,
			'handle_manual_iva': company.exchange_diff_handle_manual_iva,
			'iva_account_id': company.exchange_diff_iva_account_id,
			'auto_reconcile': company.exchange_diff_auto_reconcile,
		}

	def _create_grouped_exchange_diff_lines(self):
		"""
		Crea líneas de diferencia en cambio agrupadas según la configuración.
		Se ejecuta antes de action_post cuando el modo es 'same_entry'.

		Modos de agrupación:
		- per_line: No agrupa, deja que cada línea cree su propia diferencia
		- grouped: Agrupa por documento/factura
		- general: Una sola línea con el total de diferencias
		"""
		self.ensure_one()
		config = self._get_exchange_diff_config()

		if config['mode'] != 'same_entry':
			return

		# Obtener líneas con diferencia en cambio
		lines_with_diff = self.payment_line_ids.filtered(
			lambda l: not l.is_main
			and not l.is_diff
			and l.move_line_id
			and l.exchange_diff_amount
			and not float_compare(l.exchange_diff_amount, 0, precision_rounding=l.company_currency_id.rounding) != 0
		)

		if not lines_with_diff:
			return

		if config['group_mode'] == 'per_line':
			# Cada línea crea su propia diferencia
			for line in lines_with_diff:
				line.create_exchange_diff_line()

		elif config['group_mode'] == 'grouped':
			# Agrupar por documento/factura
			grouped_diffs = {}
			for line in lines_with_diff:
				doc_key = line.move_line_id.move_id.id if line.move_line_id.move_id else 'no_doc'
				if doc_key not in grouped_diffs:
					grouped_diffs[doc_key] = {
						'lines': self.env['account.payment.detail'],
						'total_diff': 0.0,
						'doc_name': line.move_line_id.move_id.name if line.move_line_id.move_id else 'Sin documento',
					}
				grouped_diffs[doc_key]['lines'] |= line
				grouped_diffs[doc_key]['total_diff'] += line.exchange_diff_amount

			self._create_grouped_diff_entries(grouped_diffs, config)

		elif config['group_mode'] == 'general':
			# Una sola línea con el total
			total_diff = sum(lines_with_diff.mapped('exchange_diff_amount'))
			if not float_compare(total_diff, 0, precision_rounding=self.company_id.currency_id.rounding) == 0:
				self._create_general_diff_entry(total_diff, lines_with_diff, config)

	def _create_grouped_diff_entries(self, grouped_diffs, config):
		"""
		Crea líneas de diferencia agrupadas por documento.
		"""
		company = self.company_id

		for doc_key, data in grouped_diffs.items():
			total_diff = data['total_diff']
			if float_compare(total_diff, 0, precision_rounding=company.currency_id.rounding) == 0:
				continue

			is_gain = total_diff > 0
			exchange_account = company.income_currency_exchange_account_id if is_gain else company.expense_currency_exchange_account_id

			if not exchange_account:
				raise UserError(_('Configure las cuentas de diferencia en cambio en la compañía.'))

			# Usar el primer line para obtener datos comunes
			first_line = data['lines'][0]

			diff_line_vals = {
				'payment_id': self.id,
				'name': f'Dif. Cambio Agrupada - {data["doc_name"]}',
				'account_id': exchange_account.id,
				'partner_id': first_line.partner_id.id,
				'currency_id': self.currency_id.id,
				'company_currency_id': company.currency_id.id,
				'payment_amount': -total_diff if is_gain else total_diff,
				'display_type': 'diff',
				'is_diff': True,
			}

			self.env['account.payment.detail'].create(diff_line_vals)

	def _create_general_diff_entry(self, total_diff, lines_with_diff, config):
		"""
		Crea una única línea de diferencia con el total consolidado.
		"""
		company = self.company_id
		is_gain = total_diff > 0
		exchange_account = company.income_currency_exchange_account_id if is_gain else company.expense_currency_exchange_account_id

		if not exchange_account:
			raise UserError(_('Configure las cuentas de diferencia en cambio en la compañía.'))

		# Usar el partner del pago principal
		partner = self.partner_id

		diff_line_vals = {
			'payment_id': self.id,
			'name': f'Diferencia en Cambio Consolidada - {self.name or "Pago"}',
			'account_id': exchange_account.id,
			'partner_id': partner.id if partner else False,
			'currency_id': self.currency_id.id,
			'company_currency_id': company.currency_id.id,
			'payment_amount': -total_diff if is_gain else total_diff,
			'display_type': 'diff',
			'is_diff': True,
		}

		self.env['account.payment.detail'].create(diff_line_vals)

	def _process_exchange_differences_after_post(self):
		"""
		Procesa las diferencias en cambio después de confirmar el pago.
		Se usa cuando el modo es 'separate_entry'.
		"""
		self.ensure_one()
		config = self._get_exchange_diff_config()

		if config['mode'] != 'separate_entry':
			return

		# Obtener líneas con diferencia en cambio que necesitan asiento separado
		lines_with_diff = self.payment_line_ids.filtered(
			lambda l: not l.is_main
			and not l.is_diff
			and l.move_line_id
			and l.exchange_diff_amount
			and not float_compare(l.exchange_diff_amount, 0, precision_rounding=l.company_currency_id.rounding) == 0
		)

		if not lines_with_diff:
			return

		if config['group_mode'] == 'per_line':
			# Cada línea crea su propio asiento separado
			for line in lines_with_diff:
				exchange_move = line.create_exchange_diff_line()
				if exchange_move:
					self.move_diff_ids = [(4, exchange_move.id)]

		elif config['group_mode'] in ('grouped', 'general'):
			# Crear un asiento agrupado
			exchange_move = self._create_grouped_separate_exchange_move(lines_with_diff, config)
			if exchange_move:
				self.move_diff_ids = [(4, exchange_move.id)]

	def _create_grouped_separate_exchange_move(self, lines_with_diff, config):
		"""
		Crea un asiento separado con las diferencias agrupadas.
		"""
		company = self.company_id
		journal = company.exchange_diff_separate_journal_id or company.currency_exchange_journal_id

		if not journal:
			raise UserError(_('Configure el diario para diferencias en cambio en la compañía.'))

		# Calcular total y preparar líneas
		if config['group_mode'] == 'grouped':
			# Agrupar por documento
			grouped_diffs = {}
			for line in lines_with_diff:
				doc_key = line.move_line_id.move_id.id if line.move_line_id.move_id else 'no_doc'
				if doc_key not in grouped_diffs:
					grouped_diffs[doc_key] = {
						'total_diff': 0.0,
						'doc_name': line.move_line_id.move_id.name if line.move_line_id.move_id else 'Sin documento',
						'partner_id': line.partner_id.id,
						'account_id': line.move_line_id.account_id.id,
					}
				grouped_diffs[doc_key]['total_diff'] += line.exchange_diff_amount
		else:
			# Una sola agrupación general
			total_diff = sum(lines_with_diff.mapped('exchange_diff_amount'))
			grouped_diffs = {
				'general': {
					'total_diff': total_diff,
					'doc_name': self.name or 'Pago',
					'partner_id': self.partner_id.id if self.partner_id else False,
					'account_id': lines_with_diff[0].move_line_id.account_id.id,
				}
			}

		# Crear asiento
		exchange_date = self.date or fields.Date.today()
		exchange_move = self.env['account.move'].create({
			'move_type': 'entry',
			'date': exchange_date,
			'journal_id': journal.id,
			'company_id': company.id,
			'ref': f'Dif. Cambio - {self.name or "Pago"}',
			'currency_id': self.currency_id.id,
		})

		line_ids = []
		for key, data in grouped_diffs.items():
			total_diff = data['total_diff']
			if float_compare(total_diff, 0, precision_rounding=company.currency_id.rounding) == 0:
				continue

			is_gain = total_diff > 0
			exchange_account = company.income_currency_exchange_account_id if is_gain else company.expense_currency_exchange_account_id

			if not exchange_account:
				raise UserError(_('Configure las cuentas de diferencia en cambio en la compañía.'))

			# Línea de diferencia (ganancia/pérdida)
			line_ids.append((0, 0, {
				'name': f'Diferencia en cambio - {data["doc_name"]}',
				'account_id': exchange_account.id,
				'partner_id': data['partner_id'],
				'move_id': exchange_move.id,
				'currency_id': self.currency_id.id,
				'debit': abs(total_diff) if not is_gain else 0.0,
				'credit': abs(total_diff) if is_gain else 0.0,
			}))

			# Contrapartida
			line_ids.append((0, 0, {
				'name': f'Contrapartida dif. cambio - {data["doc_name"]}',
				'account_id': data['account_id'],
				'partner_id': data['partner_id'],
				'move_id': exchange_move.id,
				'currency_id': self.currency_id.id,
				'debit': abs(total_diff) if is_gain else 0.0,
				'credit': abs(total_diff) if not is_gain else 0.0,
			}))

		if line_ids:
			exchange_move.write({'line_ids': line_ids})
			exchange_move.action_post()

			# Conciliar si está configurado
			if config['auto_reconcile']:
				for line in lines_with_diff:
					lines_to_reconcile = self.env['account.move.line']
					payment_line = self.move_id.line_ids.filtered(
						lambda l: l.line_pay.id == line.move_line_id.id
					)
					lines_to_reconcile |= payment_line
					lines_to_reconcile |= line.move_line_id
					exchange_counterpart = exchange_move.line_ids.filtered(
						lambda l: l.account_id == line.move_line_id.account_id
						and l.partner_id.id == line.partner_id.id
					)
					lines_to_reconcile |= exchange_counterpart
					if lines_to_reconcile and len(lines_to_reconcile) >= 2:
						try:
							lines_to_reconcile.reconcile()
						except Exception:
							pass  # Ignorar errores de conciliación

			return exchange_move

		return False

	### END manual account ###
	def _compute_payment_difference_line(self):
		for val in self:
			amount = 0.0
			if not val.paired_internal_transfer_payment_id:
				for line in val.payment_line_ids:
					amount += line.payment_amount
			val.payment_difference_line = val.currency_id.round(amount)

	@api.onchange('currency_id')
	def _onchange_currency(self):
		for line in self.payment_line_ids:
			line.payment_currency_id = self.currency_id.id or False
			line._onchange_to_pay()
			line._onchange_payment_amount()
	def copy(self, default=None):
		default = dict(default or {})
		default.update(payment_line_ids=[])
		return super(AccountPayment, self).copy(default)

	@api.onchange('account_move_payment_ids', 'customer_invoice_ids', 'supplier_invoice_ids')
	def _onchange_invoice_field(self):
		"""Agrega líneas de pago cuando se seleccionan documentos."""
		fields_to_check = ['account_move_payment_ids', 'customer_invoice_ids', 'supplier_invoice_ids']

		for field_name in fields_to_check:
			field_ids = self[field_name]
			if field_ids:
				if field_name == "account_move_payment_ids":
					where_clause = "account_move_line.amount_residual != 0 AND ac.reconcile AND account_move_line.id in %s"
				else:  # Para 'customer_invoice_ids' y 'supplier_invoice_ids'
					where_clause = "account_move_line.amount_residual != 0 AND ac.reconcile AND am.id in %s"

				where_params = [tuple(field_ids.ids)]

				self._cr.execute('''
				SELECT account_move_line.id
				FROM account_move_line
				LEFT JOIN account_move am ON (account_move_line.move_id = am.id)
				LEFT JOIN account_account ac ON (account_move_line.account_id = ac.id)
				WHERE ''' + where_clause, where_params
				)

				res = self._cr.fetchall()

				if res:
					for r in res:
						moves = self.env['account.move.line'].browse(r)
						self._change_and_add_payment_detail(moves)

				self[field_name] = None
				break

	def _change_and_add_payment_detail(self, moves):
		SelectPaymentLine = self.env['account.payment.detail']
		current_payment_lines = self.payment_line_ids.filtered(lambda line: line.is_main == False)
		move_lines = moves - current_payment_lines.mapped('move_line_id')
		payment_lines_to_create = []
		for line in move_lines:
			data = self._get_data_move_lines_payment(line)
			pay = SelectPaymentLine.new(data)
			pay._onchange_move_lines()
			pay._onchange_to_pay()
			pay._onchange_payment_amount()
			values_to_create = pay._convert_to_write(pay._cache)
			payment_lines_to_create.append(values_to_create)
		# Crear todas las líneas de pago en una sola operación en la base de datos
		SelectPaymentLine.create(payment_lines_to_create)

	def _get_data_move_lines_payment(self, line):
		data = {
			'move_line_id': line.id,
			'account_id': line.account_id.id,
			'analytic_distribution' : line.analytic_distribution and line.analytic_distribution or False,
			'tax_ids' : [(6, 0, line.tax_ids.ids)],
			'tax_repartition_line_id' : line.tax_repartition_line_id.id,
			'tax_base_amount': line.tax_base_amount,
			'tax_tag_ids' : [(6, 0, line.tax_tag_ids.ids)],
			'payment_id': self.id,
			'payment_currency_id': self.currency_id.id,
			'payment_difference_handling': 'open',
			'writeoff_account_id': False,
			'to_pay': True
			}
		return data

	# =====================================================
	# MÉTODOS PARA WIDGET DE SELECCIÓN DE FACTURAS
	# =====================================================

	def action_add_invoices_to_payment(self, invoice_ids):
		"""
		Agrega facturas seleccionadas desde el widget de selección.
		Similar a SAP: seleccionar y marcar facturas que se agregan.
		"""
		self.ensure_one()
		if not invoice_ids:
			return False

		invoices = self.env['account.move'].browse(invoice_ids)

		# Obtener líneas de movimiento reconciliables de las facturas
		move_lines = invoices.line_ids.filtered(
			lambda l: l.account_id.reconcile
			and l.amount_residual != 0
			and not l.reconciled
		)

		if move_lines:
			self._change_and_add_payment_detail(move_lines)
			# Recalcular líneas dinámicas
			self._recompute_dynamic_lines_payment()

		return True

	# =====================================================
	# WIZARD SELECCIÓN DE DOCUMENTOS
	# =====================================================

	def action_open_select_documents_wizard(self, filter_due_status='all'):
		"""Abre el wizard para seleccionar documentos a pagar/cobrar"""
		self.ensure_one()
		return {
			'name': _('Seleccionar Documentos'),
			'type': 'ir.actions.act_window',
			'res_model': 'select.documents.wizard',
			'view_mode': 'form',
			'target': 'new',
			'context': {
				'default_payment_id': self.id,
				'default_document_type': 'receivable' if self.partner_type == 'customer' else 'payable',
				'default_filter_due_status': filter_due_status,
			}
		}

	def action_open_wizard_overdue(self):
		"""Abre el wizard filtrado por documentos vencidos"""
		return self.action_open_select_documents_wizard(filter_due_status='overdue')

	def action_open_wizard_due_soon(self):
		"""Abre el wizard filtrado por documentos por vencer"""
		return self.action_open_select_documents_wizard(filter_due_status='due_soon')

	def action_open_wizard_all(self):
		"""Abre el wizard con todos los documentos"""
		return self.action_open_select_documents_wizard(filter_due_status='all')

	def action_open_destination_transfer(self):
		"""Abre el pago de transferencia interna vinculado (destino)"""
		self.ensure_one()
		if not self.paired_internal_transfer_payment_id:
			return False
		return {
			'name': _('Transferencia Destino'),
			'type': 'ir.actions.act_window',
			'res_model': 'account.payment',
			'view_mode': 'form',
			'res_id': self.paired_internal_transfer_payment_id.id,
			'target': 'current',
		}

	# =====================================================
	# MÉTODOS PARA IMPUESTOS (REVERTIR/APLICAR)
	# =====================================================

	def action_revert_taxes(self, line_ids=None):
		"""
		Revierte los impuestos de las líneas seleccionadas.
		Elimina las líneas de impuesto automáticas asociadas.
		"""
		self.ensure_one()
		if self.state != 'draft':
			raise UserError(_("Solo puede revertir impuestos en pagos en borrador."))

		if line_ids:
			lines = self.payment_line_ids.filtered(lambda l: l.id in line_ids and not l.auto_tax_line)
		else:
			lines = self.payment_line_ids.filtered(lambda l: not l.auto_tax_line and l.tax_ids)

		# Eliminar líneas de impuesto automáticas relacionadas
		tax_lines_to_remove = self.payment_line_ids.filtered(
			lambda l: l.auto_tax_line and l.tax_line_id in lines
		)
		tax_lines_to_remove.unlink()

		# Limpiar impuestos de las líneas
		for line in lines:
			line.write({
				'tax_ids': [(5, 0, 0)],
				'tax_tag_ids': [(5, 0, 0)],
				'tax_repartition_line_id': False,
				'tax_base_amount': 0,
			})

		return True

	def action_apply_taxes(self, line_ids=None, tax_ids=None):
		"""
		Aplica impuestos a las líneas seleccionadas.
		Crea las líneas de impuesto automáticas correspondientes.
		"""
		self.ensure_one()
		if self.state != 'draft':
			raise UserError(_("Solo puede aplicar impuestos en pagos en borrador."))

		if line_ids:
			lines = self.payment_line_ids.filtered(lambda l: l.id in line_ids and not l.auto_tax_line)
		else:
			lines = self.payment_line_ids.filtered(lambda l: not l.auto_tax_line and not l.is_main)

		if not lines:
			return False

		taxes = self.env['account.tax'].browse(tax_ids) if tax_ids else False

		for line in lines:
			if taxes:
				line.write({'tax_ids': [(6, 0, taxes.ids)]})

		# Recalcular impuestos
		self._onchange_matched_manual_ids(force_update=True)

		return True

	# =====================================================
	# MEJORAS DE MONEDA Y REDONDEO
	# =====================================================

	def _round_currency(self, amount, currency=None):
		"""
		Redondea un monto según la precisión de la moneda.
		"""
		if currency is None:
			currency = self.currency_id or self.company_id.currency_id
		return currency.round(amount)

	def _get_currency_rate(self, from_currency, to_currency, date=None):
		"""
		Obtiene la tasa de cambio entre dos monedas para una fecha.
		"""
		if date is None:
			date = self.date or fields.Date.context_today(self)

		if from_currency == to_currency:
			return 1.0

		return from_currency._get_conversion_rate(
			from_currency, to_currency, self.company_id, date
		)

	def _convert_amount(self, amount, from_currency, to_currency, date=None):
		"""
		Convierte un monto de una moneda a otra con redondeo.
		"""
		if from_currency == to_currency:
			return amount

		rate = self._get_currency_rate(from_currency, to_currency, date)
		converted = amount * rate
		return self._round_currency(converted, to_currency)

	def _compute_payment_with_rounding(self):
		"""
		Calcula el monto de pago aplicando redondeo según configuración.
		Implementa lógica similar a SAP para ajuste al peso.
		"""
		self.ensure_one()

		if not self.adjustment_peso:
			return self.amount

		# Obtener la unidad mínima de la moneda (ej: 1 para COP, 0.01 para USD)
		currency = self.currency_id or self.company_id.currency_id
		rounding = currency.rounding

		# Redondear al entero más cercano si es moneda sin decimales (COP)
		if rounding >= 1:
			rounded_amount = round(self.amount)
			self.adjustment_amount = rounded_amount - self.amount
			return rounded_amount

		return self.amount

	@api.onchange('currency_id')
	def _onchange_payment_amount_currency(self):
		self.writeoff_account_id = self._get_account_diff_currency(self.payment_difference_line)
		self._recompute_dynamic_lines_payment()

	def _get_account_diff_currency(self, amount):
		account = False
		company = self.env.company
		account = amount > 0 and company.expense_currency_exchange_account_id 
		if not account:
			account = company.income_currency_exchange_account_id
		return account

	@api.onchange('date')
	def _onchange_payment_date(self):
		for line in self.payment_line_ids.filtered(lambda line: line.is_main == False):
			line._onchange_to_pay()
			line._onchange_payment_amount()
			line._compute_payment_difference()
			line._compute_debit_credit_balance()
		self._recompute_dynamic_lines_payment()

	@api.onchange('payment_line_ids', 'outstanding_account_id','payment_type', 'destination_account_id','amount','journal_id','currency_id', 'adjustment_peso', 'adjustment_amount', 'adjustment_account_id')
	def _onchange_recompute_dynamic_line(self):
		self._recompute_dynamic_lines_payment()

	def _recompute_dynamic_lines_payment(self):
		self.ensure_one()
		diff_cash = self.payment_line_ids.filtered(lambda line: line.is_counterpart and line.is_main)
		if len(diff_cash) > 1:
			diff_cash.unlink()
		amount = self.amount * (self.payment_type in ('outbound', 'transfer') and 1 or -1)
		self._onchange_accounts(-amount, account_id=self.outstanding_account_id.id , display_type='asset_cash', is_main=True, is_counterpart=False)
		if self.advance:
			amount = self.amount * (self.payment_type in ('outbound', 'transfer') and -1 or 1)
			self._onchange_accounts(-amount, account_id=self.destination_account_id.id , display_type='advance', is_main=True, is_counterpart=False)
		if not self.advance:
			manual_entries_total = sum(line.payment_amount for line in self.payment_line_ids.filtered(lambda l: l.display_type not in ['asset_cash', 'rounding'] and l.is_main == False))
			counter_part_amount = amount - manual_entries_total
			amount_diff = counter_part_amount - amount
			display_type = 'counterpart'
			account_id = self.destination_account_id.id
			self._compute_payment_difference_line()
			diif_amount =self.payment_difference_line
			if (self.payment_type == 'outbound' and diif_amount != 0) or (self.payment_type == 'inbound' and diif_amount != 0):
				account_id =  self.writeoff_account_id
				display_type = 'counterpart'
			counter_part_amount = amount - manual_entries_total
			self._onchange_accounts(counter_part_amount, account_id, display_type=display_type, is_main=True, is_counterpart=True)

		# ========== LÍNEA DE AJUSTE DE REDONDEO ==========
		# Eliminar línea de redondeo existente
		rounding_lines = self.payment_line_ids.filtered(lambda l: l.display_type == 'rounding')
		if rounding_lines:
			rounding_lines.unlink()

		# Crear línea de redondeo si está activo y hay monto de ajuste
		if self.adjustment_peso and self.adjustment_amount and self.adjustment_account_id:
			# El signo del ajuste depende del tipo de pago
			rounding_amount = self.adjustment_amount
			if self.payment_type == 'outbound':
				rounding_amount = -rounding_amount

			self._onchange_accounts(
				rounding_amount,
				account_id=self.adjustment_account_id.id,
				display_type='rounding',
				is_main=True,
				is_counterpart=False
			)

	def _recompute_multi_payment_method_lines(self, total_amount):
		"""
		Crea líneas de pago separadas para cada forma de pago cuando
		enable_multi_payment_method está activo.

		Args:
			total_amount: Monto total con signo (negativo para egresos)
		"""
		self.ensure_one()
		in_draft_mode = self != self._origin
		PaymentDetail = self.env['account.payment.detail']

		# Eliminar líneas asset_cash existentes (las que representan banco/caja)
		existing_cash_lines = self.payment_line_ids.filtered(
			lambda l: l.display_type == 'asset_cash' and l.is_main
		)
		if existing_cash_lines:
			existing_cash_lines.unlink()

		# Crear una línea por cada forma de pago
		for method_line in self.payment_method_line_ids:
			if not method_line.amount or not method_line.account_id:
				continue

			# El monto de la línea tiene el mismo signo que el total
			line_amount = method_line.amount * (self.payment_type in ('outbound', 'transfer') and -1 or 1)

			# Generar nombre descriptivo
			line_name = f"{method_line.payment_method_id.name} - {method_line.journal_id.name}"
			if method_line.check_number:
				line_name += f" (Cheque: {method_line.check_number})"

			line_values = {
				'payment_amount': line_amount,
				'partner_id': self.partner_id.id or False,
				'payment_id': self.id,
				'company_currency_id': self.env.company.currency_id.id,
				'display_type': 'asset_cash',
				'is_transfer': False,
				'is_main': True,
				'is_counterpart': False,
				'name': line_name,
				'currency_id': self.currency_id.id,
				'account_id': method_line.account_id.id,
				'ref': self.name or '/',
				'payment_currency_id': self.currency_id.id,
				'amount_currency': line_amount,
				# Campos adicionales para rastrear el método de pago
				'journal_id': method_line.journal_id.id,
			}

			if in_draft_mode:
				PaymentDetail.new(line_values)
			else:
				PaymentDetail.create(line_values)

	def _onchange_accounts(self, amount, account_id=None, is_transfer=False, display_type=None, is_main=False, is_counterpart=False):
		self.ensure_one()
		in_draft_mode = self != self._origin
		existing_line = is_main and self.payment_line_ids.filtered(lambda line: line.display_type == display_type and line.is_main) or None
		if not account_id or self.currency_id.is_zero(amount):
			if existing_line:
				self.payment_line_ids -= existing_line
			return
		line_values = self._set_fields_detail(amount, account_id, is_transfer, display_type, is_main, is_counterpart)

		if existing_line:
			existing_line.update(line_values)
		else:
			if in_draft_mode:
				self.env['account.payment.detail'].new(line_values)
			else:
				self.env['account.payment.detail'].create(line_values)

	def _set_fields_detail(self, total_balance, account, is_transfer, display_type,is_main,is_counterpart):
		line_values = {
			'payment_amount': total_balance,
			'partner_id': self.partner_id.id or False,
			'payment_id': self.id,
			'company_currency_id': self.env.company.currency_id.id,
			'display_type': display_type,
			'is_transfer': is_transfer,
			'is_main': is_main,
			'is_counterpart': is_counterpart,
			'name': self.memo or '/',
			'currency_id': self.currency_id.id,
			'account_id': account,
			'ref': self.name or '/',
			'payment_currency_id': self.currency_id.id,
			'amount_currency': total_balance,
		}
		# if self.currency_id and self.currency_id != self.company_currency_id:
		# 	amount_currency = self.company_currency_id._convert(
		# 		total_balance,
		# 		self.currency_id,
		# 		self.company_id,
		# 		self.date or fields.Date.today()
		# 	) 
		# 	line_values.update({
		# 		'amount_currency': amount_currency
		# 	})
		return line_values


	def _cleanup_lines(self):
		""" 
		Limpiar lineas aplica para evitar errores, comunes dentro del ORM evita:
		--> Si hay más de una línea que cumple el criterio de 'diff_cash', elimínalas todas (Para cuando se vuelva a computar el asiento quede cuadrado)
		---> Encuentra y elimina las líneas con cantidad de pago igual a cero evita crear en la base de datos datos inecesaro
		"""
		diff_cash = self.payment_line_ids.filtered(lambda line: line.display_type != 'asset_cash' and line.is_main)
		if len(diff_cash) > 1:
			diff_cash.unlink()
		zero_lines = self.payment_line_ids.filtered(lambda l: self.currency_id.is_zero(l.payment_amount))
		zero_lines.unlink()

	def _is_advance(self):
		return self.advance

	def _get_counterpart_move_line_vals(self, invoice=False):
		res = super(AccountPayment, self)._get_counterpart_move_line_vals(invoice=invoice)

		# ========== NOMENCLATURA SEGÚN TIPO DE DOCUMENTO ==========

		# 1. RECIBO DE CAJA (Cruce sin movimiento de efectivo)
		if self.is_cash_receipt:
			name = 'Recibo de Caja'
			if self.cash_receipt_number:
				name = f'Recibo de Caja {self.cash_receipt_number}'
			if self.partner_type == 'employee':
				name += ' - Empleado'
			elif self.partner_type == 'customer':
				name += ' - Cliente'
			elif self.partner_type == 'supplier':
				name += ' - Proveedor'
			res.update(name=name)

		# 2. PAGO/COBRO REGULAR (Con movimiento de efectivo)
		# RC = Recibo de Cobro (inbound), CE = Comprobante de Egreso (outbound)
		elif self.payment_number:
			if self.payment_type == 'inbound':
				name = f'Recibo de Cobro {self.payment_number}'
			else:
				name = f'Comprobante de Egreso {self.payment_number}'

			if self.partner_type == 'employee':
				name += ' - Empleado'
			elif self.partner_type == 'customer':
				name += ' - Cliente'
			elif self.partner_type == 'supplier':
				name += ' - Proveedor'
			res.update(name=name)

		# 3. ANTICIPO
		elif self.advance:
			name = ''
			if self.partner_type == 'employee':
				name += _('Employee Payment Advance')
			elif self.partner_type == 'customer':
				name += _('Customer Payment Advance')
			elif self.partner_type == 'supplier':
				name += _('Vendor Payment Advance')
			name += f' {self.code_advance}' if self.code_advance else ''
			res.update(name=name)

		return res

	def _get_shared_move_line_vals(self, line_debit, line_credit, line_amount_currency, move, invoice_id=False):
		""" Returns values common to both move lines (except for debit, credit and amount_currency which are reversed)
		"""
		return {
			'partner_id': self.payment_type in ('inbound', 'outbound') and self.env['res.partner']._find_accounting_partner(self.partner_id).id or False,
			# 'inv_id' eliminado - no es campo válido en account.move.line (Odoo 18)
			'move_id': move,
			'debit': line_debit,
			'credit': line_credit,
			'amount_currency': line_amount_currency or False,
			'payment_id': self.id,
			'journal_id': self.journal_id.id,
		}
	def _create_payment_entry_line(self, move):
		aml_obj = self.env['account.move.line'].with_context(check_move_validity=False, skip_account_move_synchronization=True)
		self.line_ids.unlink()
		# Usamos una lista de comprensión para construir los diccionarios
		aml_dicts = [{
			'partner_id': self.payment_type in ('inbound', 'outbound') and self.env['res.partner']._find_accounting_partner(self.partner_id).id or False,
			'move_id': move.id,
			'debit': line.debit,
			'credit': line.credit,
			'amount_currency': line.amount_currency if line.amount_currency != 0.0 else line.balance,
			'payment_id': self.id,
			'journal_id': self.journal_id.id,
			'account_id': line.account_id.id,
			'analytic_distribution': line.analytic_distribution or False,
			'tax_ids': [(6, 0, line.tax_ids.ids)],
			'tax_tag_ids': [(6, 0, line.tax_tag_ids.ids)],
			'tax_repartition_line_id': line.tax_repartition_line_id.id,
			'tax_base_amount': line.tax_base_amount,
			# 'inv_id' y 'line_pay' eliminados - no son campos válidos en account.move.line (Odoo 18)
			**line._get_counterpart_move_line_vals()  # Merging the dictionary directly
		} for line in self.payment_line_ids]

		# Crear entradas de una vez, sin bucle for
		aml_obj.create(aml_dicts)

		return True


	def get_accounts_summary(self):
		"""
		Computes an accounts summary for the payment voucher report.
		Returns a list of dictionaries with account information aggregated.
		This method is called from QWeb template to avoid dict manipulation errors.

		Returns:
			list: List of dicts with keys:
				- account_code: Account code
				- account_name: Account name
				- entry: Total debit amount
				- exit: Total credit amount
				- balance: Entry - Exit
		"""
		self.ensure_one()
		if not self.move_id or not self.move_id.line_ids:
			return []

		accounts_data = {}
		for line in self.move_id.line_ids.sorted(key=lambda l: l.account_id.code):
			account_id = line.account_id.id
			if account_id not in accounts_data:
				accounts_data[account_id] = {
					'account_code': line.account_id.code,
					'account_name': line.account_id.name,
					'entry': 0.0,
					'exit': 0.0,
					'balance': 0.0,
				}
			accounts_data[account_id]['entry'] += line.debit
			accounts_data[account_id]['exit'] += line.credit
			accounts_data[account_id]['balance'] = accounts_data[account_id]['entry'] - accounts_data[account_id]['exit']

		# Convert to list and sort by account code
		result = list(accounts_data.values())
		result.sort(key=lambda x: x['account_code'])
		return result

	def _synchronize_from_moves(self, changed_fields):
		if self._context.get('skip_account_move_synchronization'):
			return
		to_change = self.filtered(lambda l: not l.payment_line_ids)
		if to_change:
			res = super(AccountPayment, to_change)._synchronize_from_moves(changed_fields)
		else:
			res = True
		return res

	def _synchronize_to_moves(self, changed_fields):
		if self._context.get('skip_account_move_synchronization'):
			return
		to_change = self.filtered(lambda l: not l.payment_line_ids)
		if to_change:
			res = super(AccountPayment, to_change)._synchronize_to_moves(changed_fields)
		else:
			res = True
		return res

	@api.constrains('payment_line_ids')
	def _check_payment_balance(self):
		for payment in self:
			if payment.payment_line_ids:
				debit_sum = sum(payment.payment_line_ids.mapped('debit'))
				credit_sum = sum(payment.payment_line_ids.mapped('credit'))

				if float_compare(debit_sum, credit_sum, precision_rounding=payment.currency_id.rounding) != 0:
					difference = (debit_sum - credit_sum)
					#raise ValidationError(_("Los montos totales de débito y crédito deben ser iguales para el pago %s. (%s)") % (payment.name, difference))

	# =========================================================================
	# CAMPOS DE TESORERÍA (consolidado de account_payment_treasury.py)
	# =========================================================================

	treasury_receipt_number = fields.Char(
		string='Número Recibo Tesorería',
		readonly=True,
		copy=False,
		help='Número consecutivo único de tesorería por tipo de pago'
	)

	treasury_payment_method_number = fields.Char(
		string='Número por Método de Pago',
		readonly=True,
		copy=False,
		help='Número consecutivo según el método de pago utilizado'
	)

	use_treasury_numbering = fields.Boolean(
		string='Usar Numeración de Tesorería',
		default=True,
		help='Si está activo, genera números consecutivos especiales de tesorería'
	)

	treasury_code_prefix = fields.Char(
		string='Código Prefijo',
		compute='_compute_treasury_code_prefix',
		store=True,
		help='Código prefijo basado en el método de pago'
	)

	@api.depends('payment_method_line_id', 'payment_method_line_id.payment_method_id')
	def _compute_treasury_code_prefix(self):
		for payment in self:
			if payment.payment_method_line_id and payment.payment_method_line_id.payment_method_id:
				payment_method = payment.payment_method_line_id.payment_method_id
				if hasattr(payment_method, 'treasury_code') and payment_method.treasury_code:
					payment.treasury_code_prefix = payment_method.treasury_code
				else:
					payment_code = payment_method.code or ''
					if payment_code == 'manual':
						payment.treasury_code_prefix = 'EFE'
					elif payment_code == 'check_printing':
						payment.treasury_code_prefix = 'CHQ'
					elif payment_code in ['electronic', 'batch_payment']:
						payment.treasury_code_prefix = 'TRANSF'
					else:
						payment.treasury_code_prefix = payment_code[:3].upper() if payment_code else 'PAG'
			else:
				payment.treasury_code_prefix = 'PAG'

	def _generate_treasury_numbers(self):
		"""Genera los números consecutivos de tesorería según el tipo y método de pago"""
		for payment in self:
			if payment.treasury_receipt_number:
				continue

			if payment.payment_type == 'inbound':
				sequence_code = 'treasury.receipt.inbound'
			elif payment.payment_type == 'outbound':
				sequence_code = 'treasury.receipt.outbound'
			else:
				sequence_code = 'treasury.receipt.transfer'

			sequence = self.env['ir.sequence'].sudo().search([
				('code', '=', sequence_code),
				'|',
				('company_id', '=', payment.company_id.id),
				('company_id', '=', False)
			], limit=1)

			if sequence:
				payment.treasury_receipt_number = sequence.next_by_id()

			payment_method_code = payment.payment_method_line_id.payment_method_id.code
			method_sequence_code = False
			if payment_method_code == 'manual':
				method_sequence_code = 'treasury.payment.cash'
			elif payment_method_code == 'check_printing':
				method_sequence_code = 'treasury.payment.check'
			elif payment_method_code in ['electronic', 'batch_payment']:
				method_sequence_code = 'treasury.payment.transfer'

			if method_sequence_code:
				method_sequence = self.env['ir.sequence'].sudo().search([
					('code', '=', method_sequence_code),
					'|',
					('company_id', '=', payment.company_id.id),
					('company_id', '=', False)
				], limit=1)
				if method_sequence:
					payment.treasury_payment_method_number = method_sequence.next_by_id()

	# =========================================================================
	# CAMPOS DE ANTICIPOS (consolidado de account_payment_advance.py)
	# =========================================================================

	advance_request_id = fields.Many2one(
		'advance.request',
		string='Solicitud de Anticipo',
		readonly=True,
		ondelete='restrict'
	)

	is_advance = fields.Boolean(
		string='Es Anticipo',
		help='Indica si este pago es un anticipo'
	)

	purchase_order_ids = fields.Many2many(
		'purchase.order',
		'account_payment_purchase_order_rel',
		'payment_id',
		'order_id',
		string='Órdenes de Compra',
		help='Órdenes de compra asociadas a este anticipo'
	)

	sale_order_ids = fields.Many2many(
		'sale.order',
		'account_payment_sale_order_rel',
		'payment_id',
		'order_id',
		string='Órdenes de Venta',
		help='Órdenes de venta asociadas a este anticipo'
	)

	advance_balance = fields.Monetary(
		string='Saldo de Anticipo',
		currency_field='currency_id',
		compute='_compute_advance_balance',
		store=True,
		help='Saldo disponible del anticipo'
	)

	advance_reconciled_amount = fields.Monetary(
		string='Monto Aplicado',
		currency_field='currency_id',
		compute='_compute_advance_balance',
		store=True,
		help='Monto del anticipo aplicado a facturas'
	)

	advance_selection_ids = fields.Many2many(
		'account.payment',
		'payment_advance_rel',
		'payment_id',
		'advance_id',
		string='Anticipos a Aplicar',
		domain="[('partner_id', '=', partner_id), ('is_advance', '=', True), ('advance_balance', '>', 0)]",
		help='Seleccione anticipos existentes para aplicar'
	)

	show_advance_widget = fields.Boolean(
		string='Mostrar Widget Anticipos',
		compute='_compute_show_advance_widget'
	)

	@api.depends('partner_id', 'payment_type')
	def _compute_show_advance_widget(self):
		for payment in self:
			if payment.partner_id and not payment.is_advance:
				domain = [
					('partner_id', '=', payment.partner_id.id),
					('is_advance', '=', True),
					('state', '=', 'posted'),
					('advance_balance', '>', 0)
				]
				payment.show_advance_widget = bool(self.search(domain, limit=1))
			else:
				payment.show_advance_widget = False

	@api.depends('amount', 'advance_request_id.reconciliation_ids')
	def _compute_advance_balance(self):
		for payment in self:
			if payment.is_advance and payment.state == 'posted':
				if payment.advance_request_id:
					reconciliations = payment.advance_request_id.reconciliation_ids
					payment.advance_reconciled_amount = sum(reconciliations.mapped('amount'))
				else:
					payment.advance_reconciled_amount = 0
				payment.advance_balance = payment.amount - payment.advance_reconciled_amount
			else:
				payment.advance_balance = 0
				payment.advance_reconciled_amount = 0

	def action_apply_advances(self):
		"""Aplica anticipos seleccionados a facturas"""
		self.ensure_one()
		if not self.advance_selection_ids:
			raise UserError(_('Por favor seleccione al menos un anticipo para aplicar'))
		wizard = self.env['advance.reconciliation.wizard'].create({
			'payment_id': self.id,
			'advance_ids': [(6, 0, self.advance_selection_ids.ids)]
		})
		return {
			'name': _('Aplicar Anticipos'),
			'type': 'ir.actions.act_window',
			'res_model': 'advance.reconciliation.wizard',
			'res_id': wizard.id,
			'view_mode': 'form',
			'target': 'new'
		}

	def action_view_advance_details(self):
		"""Ver detalles del anticipo"""
		self.ensure_one()
		if self.advance_request_id:
			return {
				'name': _('Solicitud de Anticipo'),
				'type': 'ir.actions.act_window',
				'res_model': 'advance.request',
				'res_id': self.advance_request_id.id,
				'view_mode': 'form',
				'target': 'current'
			}

	# =========================================================================
	# CAMPOS DE SECUENCIA (consolidado de treasury_sequence_config.py)
	# =========================================================================

	treasury_sequence_config_id = fields.Many2one(
		'treasury.sequence.config',
		string='Config. Secuencia',
		readonly=True,
		help='Configuración de secuencia usada para generar el número.',
	)

	treasury_number = fields.Char(
		string='Número Tesorería',
		readonly=True,
		copy=False,
		help='Número generado por la configuración de secuencia de tesorería.',
	)

	display_treasury_number = fields.Char(
		string='Número',
		compute='_compute_display_treasury_number',
		store=False,
	)

	@api.depends('treasury_number', 'payment_number', 'cash_receipt_number', 'name')
	def _compute_display_treasury_number(self):
		for payment in self:
			if payment.treasury_number:
				payment.display_treasury_number = payment.treasury_number
			elif payment.is_cash_receipt and payment.cash_receipt_number:
				payment.display_treasury_number = payment.cash_receipt_number
			elif payment.payment_number:
				payment.display_treasury_number = payment.payment_number
			else:
				payment.display_treasury_number = payment.name

	def _generate_treasury_number(self):
		"""Genera el número de tesorería usando la configuración apropiada."""
		self.ensure_one()
		config = self.env['treasury.sequence.config'].get_sequence_for_payment(self)
		if config:
			number = config.get_next_number(self)
			self.write({
				'treasury_sequence_config_id': config.id,
				'treasury_number': number,
			})
			return number
		return False

	def unlink(self):
		for payment in self:
			if payment.advance_request_id:
				payment.advance_request_id = False
			if payment.amount:
				payment.with_context(skip_recalc=True).write({'amount': 0})
			if payment.payment_line_ids:
				payment.payment_line_ids.with_context(skip_recalc=True).unlink()
			if payment.payment_method_line_ids:
				payment.payment_method_line_ids.unlink()
		return super().unlink()


class ResPartner(models.Model):
	_inherit = 'res.partner'

	def _find_accounting_partner(self, partner):
		''' Find the partner for which the accounting entries will be created '''
		return partner.commercial_partner_id
