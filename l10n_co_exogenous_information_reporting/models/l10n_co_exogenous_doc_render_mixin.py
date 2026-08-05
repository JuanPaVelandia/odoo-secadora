# -*- coding: utf-8 -*-
"""
Mixin genérico para renderizado de documentos HR con placeholders.

Este mixin proporciona funcionalidades comunes para:
- Certificados laborales
- Cartas de recomendación
- Certificados de ingresos
- Otros documentos HR

Uso:
    class MiModelo(models.Model):
        _inherit = ['l10n_co.exogenous_doc_render_mixin']

    # En el modelo:
    content = self.render_document_content(template_text, contract, extra_values)
"""
import re
from datetime import datetime, date
from odoo import models, fields, api, _


# Diccionario maestro de placeholders disponibles
DOCUMENT_PLACEHOLDERS = {
    # =========================================
    # DATOS DEL EMPLEADO
    # =========================================
    'empleado': {
        'description': 'Nombre completo del empleado',
        'path': 'employee_id.name',
        'category': 'empleado',
    },
    'identificacion': {
        'description': 'Número de identificación',
        'path': 'employee_id.identification_id',
        'category': 'empleado',
    },
    'tipo_documento': {
        'description': 'Tipo de documento (CC, CE, etc.)',
        'path': 'employee_id.l10n_latam_identification_type_id.name',
        'default': 'C.C.',
        'category': 'empleado',
    },
    'genero': {
        'description': 'Género del empleado',
        'path': 'employee_id.gender',
        'category': 'empleado',
    },
    'tratamiento': {
        'description': 'Tratamiento según género (El señor/La señora)',
        'computed': '_get_tratamiento',
        'category': 'empleado',
    },
    'email_trabajo': {
        'description': 'Email de trabajo',
        'path': 'employee_id.work_email',
        'category': 'empleado',
    },
    'telefono_trabajo': {
        'description': 'Teléfono de trabajo',
        'path': 'employee_id.work_phone',
        'category': 'empleado',
    },
    # ---- Cuenta bancaria del empleado (Odoo 14: hr.employee.bank_account_id) ----
    'cuenta_empleado': {
        'description': 'Número de cuenta bancaria del empleado',
        'computed': '_get_cuenta_empleado',
        'category': 'empleado',
    },
    'banco_empleado': {
        'description': 'Banco al que pertenece la cuenta del empleado',
        'computed': '_get_banco_empleado',
        'category': 'empleado',
    },
    'tipo_cuenta_empleado': {
        'description': 'Tipo de cuenta del empleado (Ahorros / Corriente)',
        'computed': '_get_tipo_cuenta_empleado',
        'category': 'empleado',
    },

    # =========================================
    # DATOS DEL CONTRATO
    # =========================================
    'cargo': {
        'description': 'Cargo del empleado',
        'path': 'job_id.name',
        'category': 'contrato',
    },
    'departamento': {
        'description': 'Departamento',
        'path': 'department_id.name',
        'category': 'contrato',
    },
    'fecha_inicio': {
        'description': 'Fecha de inicio del contrato',
        'path': 'date_start',
        'format': 'date_text',
        'category': 'contrato',
    },
    'fecha_inicio_corta': {
        'description': 'Fecha de inicio (formato corto)',
        'path': 'date_start',
        'format': 'date_short',
        'category': 'contrato',
    },
    'fecha_retiro': {
        'description': 'Fecha de retiro',
        'path': 'retirement_date',
        'format': 'date_text',
        'category': 'contrato',
    },
    'fecha_fin_contrato': {
        'description': 'Fecha fin del contrato',
        'path': 'date_end',
        'format': 'date_text',
        'category': 'contrato',
    },
    'salario': {
        'description': 'Salario básico mensual (número)',
        'path': 'wage',
        'format': 'currency',
        'category': 'contrato',
    },
    'salario_letras': {
        'description': 'Salario en letras',
        'computed': '_get_salario_letras',
        'category': 'contrato',
    },
    'tipo_contrato': {
        'description': 'Tipo de contrato',
        'computed': '_get_tipo_contrato',
        'category': 'contrato',
    },
    'estado_contrato': {
        'description': 'Estado del contrato (activo/terminado)',
        'computed': '_get_estado_contrato',
        'category': 'contrato',
    },

    # =========================================
    # DATOS DE LA EMPRESA
    # =========================================
    'empresa': {
        'description': 'Nombre de la empresa',
        'path': 'company_id.name',
        'category': 'empresa',
    },
    'nit_empresa': {
        'description': 'NIT de la empresa',
        'path': 'company_id.vat',
        'category': 'empresa',
    },
    'ciudad_empresa': {
        'description': 'Ciudad de la empresa',
        'computed': '_get_ciudad_empresa',
        'category': 'empresa',
    },
    'direccion_empresa': {
        'description': 'Dirección de la empresa',
        'path': 'company_id.street',
        'category': 'empresa',
    },
    'telefono_empresa': {
        'description': 'Teléfono de la empresa',
        'path': 'company_id.phone',
        'category': 'empresa',
    },
    'email_empresa': {
        'description': 'Email de la empresa',
        'path': 'company_id.email',
        'category': 'empresa',
    },

    # =========================================
    # DATOS DEL DOCUMENTO
    # =========================================
    'fecha_actual': {
        'description': 'Fecha actual en texto',
        'computed': '_get_fecha_actual',
        'category': 'documento',
    },
    'fecha_actual_corta': {
        'description': 'Fecha actual (formato corto)',
        'computed': '_get_fecha_actual_corta',
        'category': 'documento',
    },
    'anio_actual': {
        'description': 'Año actual',
        'computed': '_get_anio_actual',
        'category': 'documento',
    },
}


class HrDocumentRenderMixin(models.AbstractModel):
    """Mixin para renderizado de documentos HR con placeholders"""
    _name = 'l10n_co.exogenous_doc_render_mixin'
    _description = 'Mixin para Renderizado de Documentos HR'

    # =========================================================================
    # MÉTODOS PRINCIPALES DE RENDERIZADO
    # =========================================================================

    def render_document_content(self, template_text, contract, extra_values=None):
        """
        Renderiza el contenido de un documento reemplazando placeholders.

        Args:
            template_text: Texto con placeholders %(variable)s
            contract: Registro hr.contract
            extra_values: dict con valores adicionales

        Returns:
            str: Texto con placeholders reemplazados
        """
        if not template_text:
            return ''

        values = self._get_placeholder_values(contract, extra_values)

        try:
            return template_text % values
        except (KeyError, ValueError) as e:
            # Si hay error, intentar reemplazar solo los placeholders válidos
            return self._safe_render(template_text, values)

    def _safe_render(self, template_text, values):
        """Renderizado seguro que ignora placeholders no encontrados"""
        def replace_match(match):
            key = match.group(1)
            return str(values.get(key, match.group(0)))

        pattern = r'%\(([^)]+)\)s'
        return re.sub(pattern, replace_match, template_text)

    def _get_placeholder_values(self, contract, extra_values=None):
        """
        Obtiene todos los valores de placeholders para un contrato.

        Args:
            contract: Registro hr.contract
            extra_values: dict con valores adicionales (ej: datos del documento)

        Returns:
            dict: Valores para reemplazo de placeholders
        """
        values = {}

        for key, config in DOCUMENT_PLACEHOLDERS.items():
            if 'computed' in config:
                # Valor computado por método. getattr con default 'None' evita
                # el patrón hasattr() y mantiene flujo lineal.
                method = getattr(self, config['computed'], None)
                values[key] = method(contract) if method else ''
            elif 'path' in config:
                # Valor obtenido de un campo
                raw_value = self._get_field_value(contract, config['path'])
                values[key] = self._format_value(
                    raw_value,
                    config.get('format'),
                    contract,
                    config.get('default', '')
                )

        # Agregar valores extra
        if extra_values:
            values.update(extra_values)

        return values

    def _get_field_value(self, record, field_path):
        """Obtiene el valor de un campo siguiendo un path (ej: employee_id.name)"""
        try:
            obj = record
            for part in field_path.split('.'):
                if obj is None:
                    return None
                obj = getattr(obj, part, None)
            return obj
        except Exception:
            return None

    def _format_value(self, value, format_type, contract, default=''):
        """Formatea un valor según su tipo"""
        if value is None:
            return default

        if format_type == 'date_text':
            return self._format_date_text(value, contract)
        elif format_type == 'date_short':
            return self._format_date_short(value)
        elif format_type == 'currency':
            return self._format_currency(value, contract)
        else:
            return str(value) if value else default

    # =========================================================================
    # MÉTODOS DE FORMATEO
    # =========================================================================

    def _format_date_text(self, date_value, contract):
        """Formatea fecha como texto (ej: 15 de enero de 2024).

        Si el contrato es de lavish_hr_employee, ya trae el helper
        get_date_text() — lo usamos directo. Si no (caso raro), formateamos
        manualmente.
        """
        if not date_value:
            return ''
        # lavish_hr_employee define get_date_text en hr.contract.
        # Acceso directo: el modulo es dependencia declarada del exogeno.
        get_date_text = getattr(contract, 'get_date_text', None)
        if get_date_text:
            return get_date_text(date_value)

        if isinstance(date_value, str):
            date_value = fields.Date.from_string(date_value)
        if isinstance(date_value, (date, datetime)):
            months = [
                '', 'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
                'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'
            ]
            return f"{date_value.day} de {months[date_value.month]} de {date_value.year}"
        return str(date_value)

    def _format_date_short(self, date_value):
        """Formatea fecha corta (ej: 15/01/2024)"""
        if not date_value:
            return ''
        if isinstance(date_value, str):
            date_value = fields.Date.from_string(date_value)
        if isinstance(date_value, (date, datetime)):
            return date_value.strftime('%d/%m/%Y')
        return str(date_value)

    def _format_currency(self, value, contract):
        """Formatea valor como moneda"""
        if not value:
            return '$0'
        try:
            return "${:,.0f}".format(float(value)).replace(',', '.')
        except (ValueError, TypeError):
            return str(value)

    # =========================================================================
    # MÉTODOS COMPUTADOS PARA PLACEHOLDERS
    # =========================================================================

    def _get_tratamiento(self, contract):
        """Retorna tratamiento según género"""
        gender = contract.employee_id.gender if contract.employee_id else None
        if gender == 'male':
            return 'El señor'
        elif gender == 'female':
            return 'La señora'
        return 'El/La'

    def _get_salario_letras(self, contract):
        """Retorna salario en letras.

        get_amount_text() lo aporta lavish_hr_employee (dependencia obligatoria
        del módulo exógeno). Acceso directo sin hasattr.
        """
        if not (contract and contract.wage):
            return ''
        get_amount_text = getattr(contract, 'get_amount_text', None)
        return get_amount_text(contract.wage) if get_amount_text else ''

    # =========================================================================
    # Cuenta bancaria del empleado
    # =========================================================================
    # En Odoo 14, hr.employee.bank_account_id es un Many2one a res.partner.bank
    # con los campos `acc_number` (número de cuenta), `bank_id` (banco) y
    # `acc_type`/`type_account` (tipo: Ahorros/Corriente — añadido por
    # custom_account_treasury en este sistema).

    def _get_employee_bank_account(self, contract):
        """Retorna el res.partner.bank principal del empleado, o False."""
        emp = contract.employee_id if contract else None
        if not emp:
            return False
        return emp.bank_account_id or False

    def _get_cuenta_empleado(self, contract):
        """Número de cuenta bancaria del empleado (acc_number)."""
        bank = self._get_employee_bank_account(contract)
        return bank.acc_number if bank else ''

    def _get_banco_empleado(self, contract):
        """Nombre del banco asociado a la cuenta del empleado."""
        bank = self._get_employee_bank_account(contract)
        return (bank.bank_id.name if bank and bank.bank_id else '') or ''

    def _get_tipo_cuenta_empleado(self, contract):
        """Tipo de cuenta: Ahorros / Corriente.

        custom_account_treasury (presente en el sistema) agrega un Selection
        `type_account` en res.partner.bank con valores [('A','Ahorros'),
        ('C','Corriente')]. Si el campo no estuviera disponible en algún entorno
        más limitado, caemos al `acc_type` del core de Odoo. _fields.get() es un
        acceso de diccionario normal — no usamos hasattr ni `in obj._fields`.
        """
        bank = self._get_employee_bank_account(contract)
        if not bank:
            return ''
        type_field = bank._fields.get('type_account')
        if type_field and bank.type_account:
            return dict(type_field.selection or {}).get(bank.type_account, bank.type_account) or ''
        return bank.acc_type or ''

    def _get_tipo_contrato(self, contract):
        """Retorna tipo de contrato en texto.

        Adaptación a Odoo 14: en lavish_hr_employee `hr.contract.contract_type`
        es un Selection (no el Many2one `contract_type_id` de v18). El módulo
        define el helper get_contract_type() que devuelve el label en mayúsculas.

        Como lavish_hr_employee es dependencia obligatoria, accedemos directo.
        Si por alguna razón el helper no estuviera disponible, leemos el label
        del Selection vía el _fields del propio contrato.
        """
        if not contract:
            return ''
        get_contract_type = getattr(contract, 'get_contract_type', None)
        if get_contract_type:
            return get_contract_type()
        ct = contract.contract_type if 'contract_type' in contract._fields else None
        if not ct:
            return ''
        mapping = dict(contract._fields['contract_type'].selection or [])
        return (mapping.get(ct, ct) or '').upper()

    def _get_estado_contrato(self, contract):
        """Retorna estado del contrato"""
        if contract.state == 'open':
            return 'activo'
        elif contract.state == 'close':
            return 'terminado'
        return contract.state or ''

    def _get_ciudad_empresa(self, contract):
        """Retorna ciudad de la empresa"""
        company = contract.company_id
        if company.partner_id.city_id:
            return company.partner_id.city_id.name
        return company.city or ''

    def _get_fecha_actual(self, contract):
        """Retorna fecha actual en texto"""
        get_date_text = getattr(contract, 'get_date_text', None)
        if get_date_text:
            return get_date_text(datetime.now())
        return self._format_date_text(datetime.now().date(), contract)

    def _get_fecha_actual_corta(self, contract):
        """Retorna fecha actual en formato corto"""
        return datetime.now().strftime('%d/%m/%Y')

    def _get_anio_actual(self, contract):
        """Retorna año actual"""
        return str(datetime.now().year)

    # =========================================================================
    # MÉTODOS UTILITARIOS
    # =========================================================================

    @api.model
    def get_available_placeholders(self, category=None):
        """
        Retorna lista de placeholders disponibles.

        Args:
            category: Filtrar por categoría (empleado, contrato, empresa, documento)

        Returns:
            list: Lista de diccionarios con información de placeholders
        """
        result = []
        for key, config in DOCUMENT_PLACEHOLDERS.items():
            if category and config.get('category') != category:
                continue
            result.append({
                'key': key,
                'placeholder': f'%({key})s',
                'description': config.get('description', ''),
                'category': config.get('category', 'otros'),
            })
        return sorted(result, key=lambda x: (x['category'], x['key']))

    @api.model
    def get_placeholders_help_text(self):
        """Retorna texto de ayuda con todos los placeholders disponibles"""
        lines = ["Variables disponibles para usar en plantillas:\n"]
        lines.append("=" * 60)

        categories = {
            'empleado': 'DATOS DEL EMPLEADO',
            'contrato': 'DATOS DEL CONTRATO',
            'empresa': 'DATOS DE LA EMPRESA',
            'documento': 'DATOS DEL DOCUMENTO',
        }

        for cat_key, cat_name in categories.items():
            lines.append(f"\n{cat_name}:")
            lines.append("-" * 40)
            placeholders = self.get_available_placeholders(category=cat_key)
            for p in placeholders:
                lines.append(f"  {p['placeholder']:25} - {p['description']}")

        return '\n'.join(lines)

    def get_document_preview(self, template_text, contract):
        """
        Genera una vista previa del documento renderizado.

        Args:
            template_text: Texto con placeholders
            contract: Registro hr.contract

        Returns:
            str: Texto renderizado para vista previa
        """
        return self.render_document_content(template_text, contract)


class HrDocumentTemplateMixin(models.AbstractModel):
    """Mixin para modelos de plantilla de documentos"""
    _name = 'l10n_co.exogenous_doc_template_mixin'
    _description = 'Mixin para Plantillas de Documentos HR'
    _inherit = ['l10n_co.exogenous_doc_render_mixin']

    # =========================================================================
    # CAMPOS COMUNES DE PLANTILLAS
    # =========================================================================

    # Estilo del documento
    document_style = fields.Selection([
        ('classic', 'Clásico'),
        ('modern', 'Moderno'),
        ('formal', 'Formal / Ejecutivo'),
        ('minimal', 'Minimalista'),
        ('elegant', 'Elegante'),
        ('corporate', 'Corporativo'),
    ], string='Estilo del Documento', default='formal', required=True,
        help='Estilo visual del documento')

    # Encabezado
    use_custom_header = fields.Boolean(
        string='Usar encabezado personalizado', default=False)
    custom_header_image = fields.Binary(string='Imagen de encabezado')
    custom_header_filename = fields.Char(string='Nombre archivo encabezado')

    # Firma
    show_signature = fields.Boolean(string='Mostrar firma', default=True)
    signer_name = fields.Char(string='Nombre del firmante')
    signer_position = fields.Char(
        string='Cargo del firmante',
        default='Dirección de Talento Humano')
    signature_image = fields.Binary(string='Imagen de firma')
    signature_filename = fields.Char(string='Nombre archivo firma')

    # Pie de página
    show_footer = fields.Boolean(string='Mostrar pie de página', default=True)
    footer_show_phone = fields.Boolean(string='Mostrar teléfono', default=True)
    footer_show_email = fields.Boolean(string='Mostrar email', default=True)
    footer_show_address = fields.Boolean(string='Mostrar dirección', default=False)
    footer_show_document_number = fields.Boolean(
        string='Mostrar número de documento', default=True)
    custom_footer_text = fields.Text(
        string='Texto personalizado del pie',
        help='Texto adicional para mostrar en el pie de página')
    custom_footer_image = fields.Binary(string='Imagen de pie de página')
    custom_footer_filename = fields.Char(string='Nombre archivo pie de página')

    # Notas
    show_notes = fields.Boolean(string='Mostrar notas', default=True)
    default_notes = fields.Text(string='Notas por defecto')

    # Campo de ayuda de placeholders
    placeholders_help = fields.Text(
        string='Variables disponibles',
        compute='_compute_placeholders_help',
        store=False)

    @api.depends_context('lang')
    def _compute_placeholders_help(self):
        """Calcula el texto de ayuda de placeholders"""
        help_text = self.get_placeholders_help_text()
        for record in self:
            record.placeholders_help = help_text
