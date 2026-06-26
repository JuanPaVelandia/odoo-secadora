# -*- coding: utf-8 -*-
"""
Modelo hr.labor.certificate.template - Plantilla de certificado laboral con bloques editables.
"""
from odoo import fields, models, api

# Diccionario de placeholders en español para el certificado laboral
PLACEHOLDERS_ES = {
    # ===========================================
    # DATOS DEL EMPLEADO
    # ===========================================
    'empleado': ('Nombre completo del empleado', 'employee_id.name'),
    'empleado_id': ('ID interno del empleado', 'employee_id.id'),
    'identificacion': ('Número de identificación', 'employee_id.identification_id'),
    'tipo_documento': ('Tipo de documento', 'employee_id.type_document_id.name'),
    'genero': ('Género (male/female)', 'employee_id.gender'),
    'fecha_nacimiento': ('Fecha de nacimiento', 'employee_id.birthday'),
    'lugar_nacimiento': ('Lugar de nacimiento', 'employee_id.place_of_birth'),
    'nacionalidad': ('Nacionalidad', 'employee_id.country_id.name'),
    'estado_civil': ('Estado civil', 'employee_id.marital'),

    # ===========================================
    # CONTACTO DEL EMPLEADO
    # ===========================================
    'email_trabajo': ('Email de trabajo', 'employee_id.work_email'),
    'email_personal': ('Email personal', 'employee_id.private_email'),
    'telefono_trabajo': ('Teléfono de trabajo', 'employee_id.work_phone'),
    'telefono_movil': ('Teléfono móvil', 'employee_id.mobile_phone'),
    'telefono_personal': ('Teléfono personal/privado', 'employee_id.phone'),

    # ===========================================
    # DIRECCIÓN DEL EMPLEADO
    # ===========================================
    'direccion_empleado': ('Dirección del empleado', 'employee_id.private_street'),
    'ciudad_empleado': ('Ciudad del empleado', 'employee_id.private_city'),
    'departamento_geo': ('Departamento/Estado del empleado', 'employee_id.private_state_id.name'),
    'pais_empleado': ('País del empleado', 'employee_id.private_country_id.name'),
    'codigo_postal': ('Código postal', 'employee_id.private_zip'),

    # ===========================================
    # DATOS BANCARIOS
    # ===========================================
    'banco': ('Nombre del banco', 'employee_id.bank_account_id.bank_id.name'),
    'numero_cuenta': ('Número de cuenta bancaria', 'employee_id.bank_account_id.acc_number'),
    'tipo_cuenta': ('Tipo de cuenta bancaria', 'employee_id.bank_account_id.acc_type'),

    # ===========================================
    # DATOS DEL CONTRATO
    # ===========================================
    'cargo': ('Cargo del empleado', 'job_id.name'),
    'departamento': ('Departamento', 'department_id.name'),
    'fecha_inicio': ('Fecha de inicio del contrato', 'date_start'),
    'fecha_retiro': ('Fecha de retiro', 'retirement_date'),
    'fecha_fin_contrato': ('Fecha fin del contrato', 'date_end'),
    'salario': ('Salario básico mensual', 'wage'),
    'tipo_contrato': ('Tipo de contrato', 'contract_type'),
    'modalidad_salario': ('Modalidad de salario', 'modality_salary'),
    'contrato_nombre': ('Nombre/Referencia del contrato', 'name'),

    # ===========================================
    # DATOS DE LA EMPRESA
    # ===========================================
    'empresa': ('Nombre de la empresa', 'company_id.name'),
    'nit_empresa': ('NIT de la empresa', 'company_id.vat'),
    'ciudad_empresa': ('Ciudad de la empresa', 'company_id.partner_id.city_id.name'),
    'direccion_empresa': ('Dirección de la empresa', 'company_id.street'),
    'telefono_empresa': ('Teléfono de la empresa', 'company_id.phone'),
    'email_empresa': ('Email de la empresa', 'company_id.email'),

    # ===========================================
    # DATOS DEL CERTIFICADO
    # ===========================================
    'dirigido_a': ('Solicitante/Dirigido a', 'info_to'),
    'tercero': ('Nombre del tercero/destinatario', 'partner_id.name'),
    'tercero_nit': ('NIT del tercero', 'partner_id.vat'),
    'tercero_direccion': ('Dirección del tercero', 'partner_id.street'),
    'tercero_ciudad': ('Ciudad del tercero', 'partner_id.city'),
    'secuencia': ('Número de certificado', 'sequence'),

    # ===========================================
    # DATOS ADICIONALES DEL EMPLEADO (campos comunes en Odoo HR Colombia)
    # ===========================================
    'eps': ('EPS del empleado', 'employee_id.eps_id.name'),
    'afp': ('Fondo de pensiones', 'employee_id.afp_id.name'),
    'afc': ('Fondo de cesantías', 'employee_id.afc_id.name'),
    'arl': ('ARL', 'employee_id.arl_id.name'),
    'caja_compensacion': ('Caja de compensación', 'employee_id.ccf_id.name'),
}


class HrLaborCertificateTemplate(models.Model):
    _name = 'hr.labor.certificate.template'
    _description = 'Configuración plantilla certificado laboral'

    company_id = fields.Many2one('res.company', string='Compañía', default=lambda self: self.env.company)

    # ============================================
    # ESTILO DEL CERTIFICADO
    # ============================================
    certificate_style = fields.Selection([
        ('classic', 'Clásico'),
        ('modern', 'Moderno'),
        ('formal', 'Formal / Ejecutivo'),
        ('minimal', 'Minimalista'),
        ('elegant', 'Elegante'),
        ('corporate', 'Corporativo'),
    ], string='Estilo del Certificado', default='classic', required=True,
        help='Seleccione el estilo visual para el certificado laboral')

    # ============================================
    # BLOQUE 1: Encabezado y Pie de Página
    # ============================================
    type_header_footer = fields.Selection([
        ('default', 'Por defecto'),
        ('custom', 'Personalizado')
    ], 'Tipo de encabezado y pie de página', required=True, default='default')
    img_header_file = fields.Binary('Encabezado')
    img_header_filename = fields.Char('Encabezado filename')
    img_footer_file = fields.Binary('Pie de página')
    img_footer_filename = fields.Char('Pie de página filename')

    # ============================================
    # BLOQUE 2: Identificación del Empleado
    # ============================================
    show_identification = fields.Boolean('Mostrar identificación', default=True,
        help='Muestra el número de identificación del empleado')
    show_gender_treatment = fields.Boolean('Mostrar tratamiento (Sr./Sra.)', default=True,
        help='Muestra "El señor" o "La señora" según el género')
    show_document_type = fields.Boolean('Mostrar tipo de documento', default=True,
        help='Muestra "cédula de ciudadanía", "pasaporte", etc.')

    # ============================================
    # BLOQUE 3: Información Laboral
    # ============================================
    show_contract_dates = fields.Boolean('Mostrar fechas del contrato', default=True,
        help='Muestra fecha de inicio y fin del contrato')
    show_contract_type = fields.Boolean('Mostrar tipo de contrato', default=True,
        help='Muestra el tipo de contrato (término fijo, indefinido, etc.)')
    show_job_position = fields.Boolean('Mostrar cargo', default=True,
        help='Muestra el cargo del empleado')
    show_department = fields.Boolean('Mostrar departamento', default=False,
        help='Muestra el departamento al que pertenece')

    # ============================================
    # BLOQUE 4: Información Salarial
    # ============================================
    show_base_salary = fields.Boolean('Mostrar salario básico', default=True,
        help='Muestra el salario básico mensual')
    show_salary_in_words = fields.Boolean('Mostrar salario en letras', default=True,
        help='Muestra el salario escrito en letras')
    salary_display_mode = fields.Selection([
        ('text', 'Integrado en el texto'),
        ('table', 'En tabla separada'),
        ('both', 'Ambos'),
    ], string='Modo de visualización salarial', default='text',
        help='Cómo mostrar la información salarial en el certificado')

    # ============================================
    # BLOQUE 5: Promedios de Reglas Salariales
    # ============================================
    show_average_overtime = fields.Boolean('Mostrar promedio de horas extras', default=True,
        help='Muestra el promedio de horas extras de los últimos 3 meses')
    show_variable_salary = fields.Boolean('Mostrar salario variable', default=True,
        help='Muestra el total o detalle del salario variable')
    variable_salary_mode = fields.Selection([
        ('total', 'Total consolidado'),
        ('detail', 'Detalle por concepto'),
    ], string='Modo de salario variable', default='total',
        help='Mostrar un total o el detalle de cada concepto variable')
    # Campo legacy para compatibilidad
    show_total_rules = fields.Boolean('Mostrar total de reglas variables/fijas',
        compute='_compute_show_total_rules', store=True)

    # ============================================
    # BLOQUE 6: Párrafo de Expedición
    # ============================================
    show_requestor = fields.Boolean('Mostrar solicitante', default=True,
        help='Muestra "A solicitud del interesado" con el nombre del solicitante')
    show_city_date = fields.Boolean('Mostrar ciudad y fecha', default=True,
        help='Muestra la ciudad y fecha de expedición')
    custom_closing_text = fields.Html('Texto de cierre personalizado',
        help='Texto adicional antes de la firma (opcional)')

    # ============================================
    # BLOQUE 7: Firma
    # ============================================
    show_signature = fields.Boolean('Mostrar firma', default=True,
        help='Muestra la imagen de firma del autorizado')
    show_signature_name = fields.Boolean('Mostrar nombre del firmante', default=True,
        help='Muestra el nombre del firmante autorizado')
    show_signature_position = fields.Boolean('Mostrar cargo del firmante', default=True,
        help='Muestra el cargo del firmante (Ej: Dirección de Talento Humano)')

    # ============================================
    # BLOQUE 8: Notas y Pie
    # ============================================
    show_notes = fields.Boolean('Mostrar notas', default=True,
        help='Muestra las notas adicionales configuradas')
    show_certificate_number = fields.Boolean('Mostrar número de certificado', default=True,
        help='Muestra el número de secuencia del certificado en el pie')
    notes = fields.Text(string='Notas')

    # ============================================
    # Contenido Personalizado (campos legacy)
    # ============================================
    model_fields = fields.Many2many('ir.model.fields',
        domain="[('model', 'in', ('hr.employee','hr.contract')),('ttype','not in',['one2many','many2many'])]",
        string='Campos de las tablas de empleado y contrato a utilizar')
    txt_model_fields = fields.Text(string='Nemotecnia de los campos',
        compute='_compute_txt_model_fields', store=False)
    body_labor_certificate = fields.Html(string='Contenido personalizado', translate=False,
        help='Contenido HTML adicional que se puede agregar al certificado')

    # ============================================
    # Placeholders en Español
    # ============================================
    available_placeholders = fields.Text(string='Variables disponibles',
        compute='_compute_available_placeholders', store=False)

    # ============================================
    # Detalle de Reglas Salariales
    # ============================================
    certificate_template_detail_ids = fields.One2many(
        'hr.labor.certificate.template.detail',
        'certificate_template_id',
        string='Reglas salariales para el certificado')

    _company_certificate_template = models.Constraint('UNIQUE (company_id)',
                                                      'Ya existe una configuración de plantilla de certificado laboral para esta compañía, por favor verificar')

    @api.model
    def create_default_template(self, company_id=None):
        """
        Crea una plantilla de certificado laboral con valores por defecto.

        Args:
            company_id: ID de la compañía (opcional, usa la compañía actual si no se especifica)

        Returns:
            Registro de hr.labor.certificate.template creado
        """
        company_id = company_id or self.env.company.id

        # Verificar si ya existe una plantilla para la compañía
        existing = self.search([('company_id', '=', company_id)], limit=1)
        if existing:
            return existing

        # Crear plantilla con valores por defecto
        template = self.create({
            'company_id': company_id,
            'certificate_style': 'formal',
            'type_header_footer': 'default',
            'show_identification': True,
            'show_gender_treatment': True,
            'show_document_type': True,
            'show_contract_dates': True,
            'show_contract_type': True,
            'show_job_position': True,
            'show_department': False,
            'show_base_salary': True,
            'show_salary_in_words': True,
            'salary_display_mode': 'text',
            'show_average_overtime': True,
            'show_variable_salary': True,
            'variable_salary_mode': 'total',
            'show_requestor': True,
            'show_city_date': True,
            'show_signature': True,
            'show_signature_name': True,
            'show_signature_position': True,
            'show_notes': True,
            'show_certificate_number': True,
            'notes': 'Este certificado se expide a solicitud del interesado para los fines que estime convenientes.',
        })

        return template

    @api.model
    def action_create_default_template(self):
        """
        Acción para crear plantilla por defecto desde res.config.settings.
        Retorna la acción para abrir el formulario de la plantilla.
        """
        template = self.create_default_template()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Plantilla de Certificado Laboral',
            'res_model': 'hr.labor.certificate.template',
            'res_id': template.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.depends('company_id', 'company_id.name')
    def _compute_display_name(self):
        for record in self:
            company_name = record.company_id.name if record.company_id else ''
            record.display_name = "Plantilla certificado laboral de {}".format(company_name)

    @api.depends('show_variable_salary')
    def _compute_show_total_rules(self):
        """Compatibilidad con el campo legacy show_total_rules"""
        for record in self:
            record.show_total_rules = record.show_variable_salary

    @api.depends('model_fields')
    def _compute_txt_model_fields(self):
        """Genera la nemotecnia de campos seleccionados"""
        for record in self:
            text = ''
            for field in sorted(record.model_fields, key=lambda x: x.model):
                name_field = field.name
                name_public_field = field.field_description
                text += f'Tabla origen {field.model_id.name}, Para el campo {name_public_field} digitar %({field.model}.{name_field})s\n'
            record.txt_model_fields = text

    @api.depends('company_id')
    def _compute_available_placeholders(self):
        """Genera la lista de placeholders disponibles en español"""
        for record in self:
            lines = ["Variables disponibles para usar en el contenido personalizado:\n"]
            lines.append("=" * 60)
            lines.append("\nDatos del Empleado y Contrato:")
            lines.append("-" * 40)

            for key, (description, field_path) in PLACEHOLDERS_ES.items():
                lines.append(f"  %(o.{key})s  ->  {description}")

            lines.append("\n" + "=" * 60)
            lines.append("\nFunciones especiales:")
            lines.append("-" * 40)
            lines.append("  %(salario_letras)s  ->  Salario en letras")
            lines.append("  %(fecha_actual)s  ->  Fecha actual en texto")
            lines.append("  %(fecha_inicio_texto)s  ->  Fecha de inicio en texto")
            lines.append("  %(promedio_horas_extras)s  ->  Promedio de horas extras")
            lines.append("  %(total_salario_variable)s  ->  Total salario variable")

            record.available_placeholders = '\n'.join(lines)

    def get_placeholder_values(self, contract, history_record):
        """
        Retorna un diccionario con los valores de los placeholders para un contrato.

        Args:
            contract: Registro de hr.contract
            history_record: Registro de hr.labor.certificate.history

        Returns:
            dict: Diccionario con los valores para reemplazar placeholders
        """
        import datetime

        emp = contract.employee_id
        company = contract.company_id

        # Helper para obtener atributos de forma segura
        def safe_get(obj, attr, default=''):
            try:
                for part in attr.split('.'):
                    obj = getattr(obj, part, None)
                    if obj is None:
                        return default
                return obj or default
            except Exception:
                return default

        values = {
            # ===========================================
            # DATOS DEL EMPLEADO
            # ===========================================
            'empleado': emp.name or '',
            'empleado_id': emp.id or '',
            'identificacion': emp.identification_id or '',
            'tipo_documento': safe_get(emp, 'type_document_id.name', 'cédula de ciudadanía'),
            'genero': emp.gender or '',
            'fecha_nacimiento': str(emp.birthday) if emp.birthday else '',
            'lugar_nacimiento': emp.place_of_birth or '',
            'nacionalidad': safe_get(emp, 'country_id.name'),
            'estado_civil': emp.marital or '',

            # ===========================================
            # CONTACTO DEL EMPLEADO
            # ===========================================
            'email_trabajo': emp.work_email or '',
            'email_personal': emp.private_email or '',
            'telefono_trabajo': emp.work_phone or '',
            'telefono_movil': emp.mobile_phone or '',
            'telefono_personal': emp.phone or '',

            # ===========================================
            # DIRECCIÓN DEL EMPLEADO
            # ===========================================
            'direccion_empleado': safe_get(emp, 'private_street'),
            'ciudad_empleado': safe_get(emp, 'private_city'),
            'departamento_geo': safe_get(emp, 'private_state_id.name'),
            'pais_empleado': safe_get(emp, 'private_country_id.name'),
            'codigo_postal': safe_get(emp, 'private_zip'),

            # ===========================================
            # DATOS BANCARIOS
            # ===========================================
            'banco': safe_get(emp, 'bank_account_id.bank_id.name'),
            'numero_cuenta': safe_get(emp, 'bank_account_id.acc_number'),
            'tipo_cuenta': safe_get(emp, 'bank_account_id.acc_type'),

            # ===========================================
            # DATOS DEL CONTRATO
            # ===========================================
            'cargo': safe_get(contract, 'job_id.name'),
            'departamento': safe_get(contract, 'department_id.name'),
            'fecha_inicio': str(contract.date_start) if contract.date_start else '',
            'fecha_retiro': str(contract.retirement_date) if contract.retirement_date else '',
            'fecha_fin_contrato': str(contract.date_end) if contract.date_end else '',
            'salario': contract.wage or 0,
            'tipo_contrato': contract.get_contract_type(),
            'modalidad_salario': contract.modality_salary or '',
            'contrato_nombre': contract.name or '',

            # ===========================================
            # DATOS DE LA EMPRESA
            # ===========================================
            'empresa': company.name or '',
            'nit_empresa': company.vat or '',
            'ciudad_empresa': safe_get(company, 'partner_id.city_id.name'),
            'direccion_empresa': company.street or '',
            'telefono_empresa': company.phone or '',
            'email_empresa': company.email or '',

            # ===========================================
            # DATOS DEL CERTIFICADO
            # ===========================================
            'dirigido_a': history_record.info_to or '',
            'tercero': safe_get(history_record, 'partner_id.name'),
            'tercero_nit': safe_get(history_record, 'partner_id.vat'),
            'tercero_direccion': safe_get(history_record, 'partner_id.street'),
            'tercero_ciudad': safe_get(history_record, 'partner_id.city'),
            'secuencia': history_record.sequence or '',

            # ===========================================
            # DATOS ADICIONALES (HR Colombia)
            # ===========================================
            'eps': safe_get(emp, 'eps_id.name'),
            'afp': safe_get(emp, 'afp_id.name'),
            'afc': safe_get(emp, 'afc_id.name'),
            'arl': safe_get(emp, 'arl_id.name'),
            'caja_compensacion': safe_get(emp, 'ccf_id.name'),

            # ===========================================
            # FUNCIONES ESPECIALES
            # ===========================================
            'salario_letras': contract.get_amount_text(contract.wage),
            'fecha_actual': contract.get_date_text(datetime.datetime.now()),
            'fecha_inicio_texto': contract.get_date_text(contract.date_start) if contract.date_start else '',
            'promedio_horas_extras': contract.get_average_concept_heyrec(),
        }

        # Calcular total de salario variable
        total_variable = 0
        for detail in self.certificate_template_detail_ids.filtered(lambda d: d.include_in_average):
            total_variable += contract.get_average_concept_certificate(
                detail.rule_salary_id,
                detail.last_month,
                detail.average_last_months,
                detail.value_contract,
                detail.payment_frequency
            )
        values['total_salario_variable'] = total_variable

        return values


class HrLaborCertificateTemplateDetail(models.Model):
    _name = 'hr.labor.certificate.template.detail'
    _description = 'Configuración plantilla certificado laboral detalle'
    _order = 'sequence, id'

    certificate_template_id = fields.Many2one(
        'hr.labor.certificate.template',
        string='Plantilla del certificado',
        ondelete='cascade')
    rule_salary_id = fields.Many2one(
        'hr.salary.rule',
        string='Regla Salarial',
        required=True)
    sequence = fields.Integer(string='Secuencia', default=10)

    # Opciones de cálculo
    calculation_mode = fields.Selection([
        ('last_month', 'Último mes'),
        ('average_3', 'Promedio últimos 3 meses'),
        ('average_6', 'Promedio últimos 6 meses'),
        ('average_12', 'Promedio últimos 12 meses'),
        ('custom_range', 'Rango personalizado'),
        ('value_contract', 'Valor del contrato'),
    ], string='Modo de cálculo', default='average_3', required=True,
        help='Método para calcular el valor de esta regla salarial')

    # Campos legacy (se mantienen para compatibilidad)
    last_month = fields.Boolean(string='Último mes',
        compute='_compute_legacy_fields', store=True,
        help='Toma el valor del último mes de nómina')
    average_last_months = fields.Boolean(string='Promedio últimos 3 meses',
        compute='_compute_legacy_fields', store=True,
        help='Calcula el promedio de los últimos 3 meses')
    value_contract = fields.Boolean(string='Valor del contrato',
        compute='_compute_legacy_fields', store=True,
        help='Toma el valor configurado en el contrato')

    # Campos de rango personalizado
    custom_months = fields.Integer(
        string='Meses para promediar',
        default=3,
        help='Número de meses hacia atrás para calcular el promedio (solo aplica en modo rango personalizado)')
    date_range_start = fields.Date(
        string='Fecha inicio',
        help='Fecha de inicio del rango (opcional, si está vacío usa custom_months)')
    date_range_end = fields.Date(
        string='Fecha fin',
        help='Fecha de fin del rango (opcional, si está vacío usa la fecha actual)')

    payment_frequency = fields.Selection([
        ('biweekly', 'Quincenal'),
        ('monthly', 'Mensual')
    ], string='Frecuencia de pago', default='biweekly', required=True,
        help='Frecuencia de pago para ajustar el cálculo del promedio')

    @api.depends('calculation_mode')
    def _compute_legacy_fields(self):
        """Calcula los campos legacy basándose en calculation_mode"""
        for record in self:
            record.last_month = record.calculation_mode == 'last_month'
            record.average_last_months = record.calculation_mode in ['average_3', 'average_6', 'average_12', 'custom_range']
            record.value_contract = record.calculation_mode == 'value_contract'

    # Nuevos campos para control de visualización
    include_in_average = fields.Boolean(
        string='Incluir en promedio',
        default=True,
        help='Incluir este concepto en el total del salario variable')
    show_individually = fields.Boolean(
        string='Mostrar individualmente',
        default=True,
        help='Mostrar este concepto como línea separada en el certificado')
    label_custom = fields.Char(
        string='Etiqueta personalizada',
        help='Etiqueta personalizada para mostrar en el certificado (si está vacío usa el nombre de la regla)')

    # Campo computado para el nombre a mostrar
    display_label = fields.Char(
        string='Etiqueta',
        compute='_compute_display_label',
        store=False)

    _rule_certificate_template_detail = models.Constraint('UNIQUE (certificate_template_id, rule_salary_id)',
                                                          'Ya existe esta regla para la configuración de certificado laboral, por favor verificar')

    @api.depends('label_custom', 'rule_salary_id', 'rule_salary_id.name')
    def _compute_display_label(self):
        for record in self:
            if record.label_custom:
                record.display_label = record.label_custom
            elif record.rule_salary_id:
                record.display_label = record.rule_salary_id.name
            else:
                record.display_label = ''

    def get_calculated_value(self, contract):
        """
        Calcula el valor de esta regla salarial para un contrato.

        Args:
            contract: Registro de hr.contract

        Returns:
            float: Valor calculado según la configuración
        """
        self.ensure_one()

        # Usar método mejorado v2 si existe, sino usar legacy
        try:
            return contract.get_average_concept_certificate_v2(
                salary_rule_id=self.rule_salary_id,
                calculation_mode=self.calculation_mode,
                custom_months=self.custom_months,
                date_range_start=self.date_range_start,
                date_range_end=self.date_range_end,
                payment_frequency=self.payment_frequency
            )
        except AttributeError:
            # Fallback al método legacy
            return contract.get_average_concept_certificate(
                self.rule_salary_id,
                self.last_month,
                self.average_last_months,
                self.value_contract,
                self.payment_frequency
            )

    def get_months_for_mode(self):
        """Retorna el número de meses según el modo de cálculo"""
        self.ensure_one()
        mode_months = {
            'last_month': 1,
            'average_3': 3,
            'average_6': 6,
            'average_12': 12,
            'custom_range': self.custom_months or 3,
            'value_contract': 0,
        }
        return mode_months.get(self.calculation_mode, 3)
