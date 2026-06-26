# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

# Template HTML por defecto actualizado para Odoo 19
DEFAULT_HTML_TEMPLATE = '''
<div class="container-fluid p-0">
    <table class="table table-bordered table-sm" style="font-size: 0.75rem; margin: 0;">
        <thead>
            <tr>
                <th colspan="2" class="border-0"></th>
                <th colspan="8" class="text-center border-0">
                    <h5 class="fw-bold mb-0">
                        Certificado de Ingresos y Retenciones por Rentas de Trabajo y Pensiones
                        <br/>año Gravable {year}
                    </h5>
                </th>
                <th colspan="2" class="border-0"></th>
            </tr>
            <tr>
                <th colspan="7" class="text-center">
                    <strong>Antes de diligenciar este formulario lea cuidadosamente las instrucciones</strong>
                </th>
                <th colspan="5">
                    4. Número de formulario
                    <div class="fw-normal">{val4}</div>
                </th>
            </tr>
        </thead>
        <tbody>
            <!-- Retenedor -->
            <tr>
                <td rowspan="2" class="align-middle bg-light"><strong>Retenedor</strong></td>
                <td colspan="2">5. NIT<div class="fw-normal">{val5}</div></td>
                <td>6. D.V<div class="fw-normal">{val6}</div></td>
                <td colspan="2">7. Primer Apellido<div class="fw-normal">{val7}</div></td>
                <td colspan="2">8. Segundo Apellido<div class="fw-normal">{val8}</div></td>
                <td colspan="2">9. Primer Nombre<div class="fw-normal">{val9}</div></td>
                <td colspan="2">10. Otros Nombres<div class="fw-normal">{val10}</div></td>
            </tr>
            <tr>
                <td colspan="11">11. Razón Social<div class="fw-normal">{val11}</div></td>
            </tr>

            <!-- Empleado -->
            <tr>
                <td class="align-middle bg-light"><strong>Empleado</strong></td>
                <td>24. Tipo Documento<div class="fw-normal">{val24}</div></td>
                <td colspan="3">25. Identificación<div class="fw-normal">{val25}</div></td>
                <td colspan="2">26. Primer Apellido<div class="fw-normal">{val26}</div></td>
                <td colspan="2">27. Segundo Apellido<div class="fw-normal">{val27}</div></td>
                <td colspan="2">28. Primer Nombre<div class="fw-normal">{val28}</div></td>
                <td colspan="2">29. Otros Nombres<div class="fw-normal">{val29}</div></td>
            </tr>

            <!-- Periodo -->
            <tr>
                <td colspan="5">Período de Certificación: DE {val30} A {val31}</td>
                <td colspan="2">32. Fecha expedición<div class="fw-normal">{val32}</div></td>
                <td colspan="3">33. Lugar retención<div class="fw-normal">{val33}</div></td>
                <td>34. Cód.Dpto<div class="fw-normal">{val34}</div></td>
                <td>35. Cód.Ciudad<div class="fw-normal">{val35}</div></td>
            </tr>
        </tbody>
    </table>

    <!-- Concepto de Ingresos -->
    <table class="table table-bordered table-striped table-sm" style="font-size: 0.75rem; margin: 0;">
        <thead class="table-secondary">
            <tr>
                <th colspan="9" class="text-center"><strong>Concepto de los Ingresos</strong></th>
                <th class="text-center"></th>
                <th colspan="2" class="text-center"><strong>Valor</strong></th>
            </tr>
        </thead>
        <tbody>
            <tr><td colspan="9">Pagos por salarios o emolumentos eclesiásticos</td><td>36</td><td colspan="2" class="text-end">{val36}</td></tr>
            <tr><td colspan="9">Pagos realizados con bonos electrónicos o de papel</td><td>37</td><td colspan="2" class="text-end">{val37}</td></tr>
            <tr><td colspan="9">Pagos por honorarios</td><td>38</td><td colspan="2" class="text-end">{val38}</td></tr>
            <tr><td colspan="9">Pagos por servicios</td><td>39</td><td colspan="2" class="text-end">{val39}</td></tr>
            <tr><td colspan="9">Pagos por comisiones</td><td>40</td><td colspan="2" class="text-end">{val40}</td></tr>
            <tr><td colspan="9">Pagos por prestaciones sociales</td><td>41</td><td colspan="2" class="text-end">{val41}</td></tr>
            <tr><td colspan="9">Pagos por viáticos</td><td>42</td><td colspan="2" class="text-end">{val42}</td></tr>
            <tr><td colspan="9">Pagos por gastos de representación</td><td>43</td><td colspan="2" class="text-end">{val43}</td></tr>
            <tr><td colspan="9">Pagos por compensaciones por el trabajo asociado cooperativo</td><td>44</td><td colspan="2" class="text-end">{val44}</td></tr>
            <tr><td colspan="9">Otros pagos</td><td>45</td><td colspan="2" class="text-end">{val45}</td></tr>
            <tr><td colspan="9">Cesantías e intereses efectivamente pagadas</td><td>46</td><td colspan="2" class="text-end">{val46}</td></tr>
            <tr><td colspan="9">Cesantías consignadas al fondo</td><td>47</td><td colspan="2" class="text-end">{val47}</td></tr>
            <tr><td colspan="9">Pensiones de jubilación, vejez o invalidez</td><td>48</td><td colspan="2" class="text-end">{val48}</td></tr>
            <tr class="table-primary"><td colspan="9"><strong>Total ingresos brutos (Sume 36 a 48)</strong></td><td>49</td><td colspan="2" class="text-end"><strong>{val49}</strong></td></tr>
        </tbody>
    </table>

    <!-- Concepto de Aportes -->
    <table class="table table-bordered table-striped table-sm" style="font-size: 0.75rem; margin: 0;">
        <thead class="table-secondary">
            <tr>
                <th colspan="9" class="text-center"><strong>Concepto de los Aportes</strong></th>
                <th class="text-center"></th>
                <th colspan="2" class="text-center"><strong>Valor</strong></th>
            </tr>
        </thead>
        <tbody>
            <tr><td colspan="9">Aportes obligatorios por salud a cargo del trabajador</td><td>50</td><td colspan="2" class="text-end">{val50}</td></tr>
            <tr><td colspan="9">Aportes obligatorios a fondos de pensiones y solidaridad pensional</td><td>51</td><td colspan="2" class="text-end">{val51}</td></tr>
            <tr><td colspan="9">Cotizaciones voluntarias al RAIS</td><td>52</td><td colspan="2" class="text-end">{val52}</td></tr>
            <tr><td colspan="9">Aportes voluntarios a fondos de pensiones</td><td>53</td><td colspan="2" class="text-end">{val53}</td></tr>
            <tr><td colspan="9">Aportes a cuentas AFC</td><td>54</td><td colspan="2" class="text-end">{val54}</td></tr>
            <tr class="table-info"><td colspan="9"><strong>Retención en la fuente por ingresos laborales y pensiones</strong></td><td>55</td><td colspan="2" class="text-end"><strong>{val55}</strong></td></tr>
        </tbody>
    </table>

    <!-- Datos a cargo del trabajador -->
    <table class="table table-bordered table-sm" style="font-size: 0.75rem; margin: 0;">
        <thead class="table-secondary">
            <tr>
                <th colspan="12" class="text-center"><strong>Datos a cargo del trabajador o pensionado</strong></th>
            </tr>
            <tr>
                <th colspan="6" class="text-center"><strong>Concepto de otros ingresos</strong></th>
                <th></th>
                <th colspan="2" class="text-center"><strong>Valor Recibido</strong></th>
                <th></th>
                <th colspan="2" class="text-center"><strong>Valor Retenido</strong></th>
            </tr>
        </thead>
        <tbody>
            <tr><td colspan="6">Arrendamientos</td><td>56</td><td colspan="2" class="text-end">{val56}</td><td>63</td><td colspan="2" class="text-end">{val63}</td></tr>
            <tr><td colspan="6">Honorarios, comisiones y servicios</td><td>57</td><td colspan="2" class="text-end">{val57}</td><td>64</td><td colspan="2" class="text-end">{val64}</td></tr>
            <tr><td colspan="6">Intereses y rendimientos financieros</td><td>58</td><td colspan="2" class="text-end">{val58}</td><td>65</td><td colspan="2" class="text-end">{val65}</td></tr>
            <tr><td colspan="6">Enajenación de activos fijos</td><td>59</td><td colspan="2" class="text-end">{val59}</td><td>66</td><td colspan="2" class="text-end">{val66}</td></tr>
            <tr><td colspan="6">Loterías, rifas, apuestas y similares</td><td>60</td><td colspan="2" class="text-end">{val60}</td><td>67</td><td colspan="2" class="text-end">{val67}</td></tr>
            <tr><td colspan="6">Otros</td><td>61</td><td colspan="2" class="text-end">{val61}</td><td>68</td><td colspan="2" class="text-end">{val68}</td></tr>
            <tr class="table-primary"><td colspan="6"><strong>Totales</strong></td><td>62</td><td colspan="2" class="text-end"><strong>{val62}</strong></td><td>69</td><td colspan="2" class="text-end"><strong>{val69}</strong></td></tr>
            <tr class="table-warning"><td colspan="9"><strong>Total retenciones año gravable {year} (Sume 55 + 69)</strong></td><td>70</td><td colspan="2" class="text-end"><strong>{val70}</strong></td></tr>
        </tbody>
    </table>

    <!-- Patrimonio -->
    <table class="table table-bordered table-sm" style="font-size: 0.75rem; margin: 0;">
        <thead class="table-secondary">
            <tr>
                <th class="text-center">Item</th>
                <th colspan="9" class="text-center"><strong>71. Identificación de los bienes y derechos poseídos</strong></th>
                <th colspan="2" class="text-center"><strong>72. Valor patrimonial</strong></th>
            </tr>
        </thead>
        <tbody>
            <tr><td class="text-center">1</td><td colspan="9">{val71_1}</td><td colspan="2" class="text-end">{val72_1}</td></tr>
            <tr><td class="text-center">2</td><td colspan="9">{val71_2}</td><td colspan="2" class="text-end">{val72_2}</td></tr>
            <tr><td class="text-center">3</td><td colspan="9">{val71_3}</td><td colspan="2" class="text-end">{val72_3}</td></tr>
            <tr><td class="text-center">4</td><td colspan="9">{val71_4}</td><td colspan="2" class="text-end">{val72_4}</td></tr>
            <tr><td class="text-center">5</td><td colspan="9">{val71_5}</td><td colspan="2" class="text-end">{val72_5}</td></tr>
            <tr><td class="text-center">6</td><td colspan="9">{val71_6}</td><td colspan="2" class="text-end">{val72_6}</td></tr>
            <tr class="table-info"><td colspan="9"><strong>Deudas vigentes a 31 de diciembre de {year}</strong></td><td>73</td><td colspan="2" class="text-end"><strong>{val73}</strong></td></tr>
        </tbody>
    </table>

    <!-- Dependientes -->
    <table class="table table-bordered table-sm" style="font-size: 0.75rem; margin: 0;">
        <thead class="table-secondary">
            <tr>
                <th colspan="12" class="text-center"><strong>Identificación del dependiente económico (Parágrafo 2 Art. 387 ET)</strong></th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td colspan="2">74. Tipo documento<div class="fw-normal">{val74}</div></td>
                <td colspan="2">75. No. Documento<div class="fw-normal">{val75}</div></td>
                <td colspan="6">76. Apellidos y Nombres<div class="fw-normal">{val76}</div></td>
                <td colspan="2">77. Parentesco<div class="fw-normal">{val77}</div></td>
            </tr>
            <tr>
                <td colspan="8">
                    <strong>Certifico que durante el año gravable {year}:</strong><br/>
                    1. Mi patrimonio bruto no excedió de 4.500 UVT ({uvt_4500})<br/>
                    2. Mis ingresos brutos fueron inferiores a 1.400 UVT ({uvt_1400})<br/>
                    3. No fui responsable del impuesto sobre las ventas<br/>
                    4. Mis consumos mediante tarjeta de crédito no excedieron 1.400 UVT ({uvt_1400})<br/>
                    5. Total de compras y consumos no superaron 1.400 UVT ({uvt_1400})<br/>
                    6. Consignaciones bancarias, depósitos o inversiones no excedieron 1.400 UVT ({uvt_1400})<br/>
                    <br/>
                    Por lo tanto, manifiesto que no estoy obligado a presentar declaración de renta por el año gravable {year}
                </td>
                <td colspan="4" class="text-center align-middle">
                    <strong>Firma del Trabajador o Pensionado</strong>
                    <div style="height: 60px;"></div>
                </td>
            </tr>
        </tbody>
    </table>

    <p class="small mt-2">
        <strong>Nota:</strong> Este certificado sustituye para todos los efectos legales la declaración de Renta y Complementario
        para el trabajador o pensionado que lo firme. Para trabajadores independientes contribuyentes del impuesto unificado deberán
        presentar la declaración anual consolidada del Régimen Simple de Tributación (SIMPLE).
    </p>
</div>
'''


class HrCertificateIncomeHeader(models.Model):
    """Configuración principal del certificado de ingresos y retenciones"""
    _name = 'hr.certificate.income.header'
    _description = 'Configuración de Certificado de Ingresos y Retenciones'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'year desc, name'

    # Información básica
    name = fields.Char(
        string='Nombre',
        required=True,
        tracking=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
        tracking=True
    )
    year = fields.Integer(
        string='Año',
        required=True,
        tracking=True,
        default=lambda self: fields.Date.today().year
    )
    active = fields.Boolean(
        string='Activo',
        default=True,
        tracking=True
    )
    description = fields.Text(
        string='Descripción'
    )

    # Datos del formulario
    form_number = fields.Char(
        string='Número de Formulario',
        tracking=True
    )
    issue_date = fields.Date(
        string='Fecha de Expedición',
        tracking=True,
        default=fields.Date.today
    )

    # Valores UVT
    uvt_value = fields.Float(
        string='Valor UVT',
        required=True,
        tracking=True,
        help='Valor de la Unidad de Valor Tributario para el año'
    )
    patrimony_uvt = fields.Float(
        string='UVT Patrimonio',
        default=4500,
        tracking=True,
        help='UVT para límite de patrimonio bruto (típicamente 4.500 UVT)'
    )
    income_uvt = fields.Float(
        string='UVT Ingresos',
        default=1400,
        tracking=True,
        help='UVT para límite de ingresos brutos (típicamente 1.400 UVT)'
    )

    # Valores computados en COP
    patrimony_cop = fields.Monetary(
        string='Patrimonio en COP',
        compute='_compute_cop_values',
        store=True,
        currency_field='currency_id',
        help='Patrimonio bruto en COP (UVT Patrimonio * Valor UVT)'
    )
    income_cop = fields.Monetary(
        string='Ingresos en COP',
        compute='_compute_cop_values',
        store=True,
        currency_field='currency_id',
        help='Ingresos brutos en COP (UVT Ingresos * Valor UVT)'
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        default=lambda self: self.env.company.currency_id
    )

    # Configuración de cuentas contables
    account_ids = fields.Many2many(
        'account.account',
        'certificate_income_header_account_rel',
        'header_id',
        'account_id',
        string='Cuentas Contables',
        domain="[('company_ids', 'in', [company_id])]",
        help="Cuentas contables a considerar en el cálculo"
    )
    excluded_journal_ids = fields.Many2many(
        'account.journal',
        'certificate_income_header_journal_rel',
        'header_id',
        'journal_id',
        string='Diarios Excluidos',
        domain="[('company_id', '=', company_id)]",
        help="Diarios que se excluirán del cálculo"
    )

    # Líneas de configuración
    line_ids = fields.One2many(
        'hr.conf.certificate.income',
        'header_id',
        string='Líneas de Configuración',
        copy=True
    )

    # Template HTML
    report_template = fields.Html(
        string='Plantilla del Certificado',
        default=DEFAULT_HTML_TEMPLATE,
        sanitize=False,
        help='Plantilla HTML del certificado. Use {valNN} para valores dinámicos'
    )

    # Control de completitud
    configuration_complete = fields.Boolean(
        string='Configuración Completa',
        compute='_compute_configuration_status',
        store=True
    )
    missing_items_count = fields.Integer(
        string='Items Faltantes',
        compute='_compute_configuration_status',
        store=True
    )

    # Constraints
    _unique_year_company = models.Constraint('unique(year, company_id)',
                                             'Ya existe una configuración para este año y compañía')

    @api.model_create_multi
    def create(self, vals_list):
        """
        Override para auto-llenar desde parámetros anuales y asociar líneas al crear
        SIEMPRE crea con todas las líneas de configuración
        """
        records = super().create(vals_list)
        for record in records:
            # 1. Si no tiene valor UVT, intentar cargar desde parámetros anuales
            if not record.uvt_value:
                annual_params = self.env['hr.annual.parameters'].get_for_year(
                    record.year,
                    company_id=record.company_id.id,
                    raise_if_not_found=False,
                )

                if annual_params and annual_params.value_uvt:
                    record.write({
                        'uvt_value': annual_params.value_uvt,
                    })

            # 2. SIEMPRE asociar líneas de configuración si no 
            if not record.line_ids:
                # Buscar líneas XML sin encabezado
                orphan_lines = self.env['hr.conf.certificate.income'].search([
                    ('header_id', '=', False),
                    ('annual_parameters_id', '=', False)
                ])

                if orphan_lines:
                    # Asociar líneas huérfanas con este encabezado
                    orphan_lines.write({'header_id': record.id})
                else:
                    # Si no hay líneas huérfanas, crear estructura básica
                    record._create_default_lines()

        return records

    def _create_default_lines(self):
        """
        Crea las líneas de configuración por defecto si no existen
        Define las 30+ líneas estándar del certificado
        """
        self.ensure_one()

        # Definir líneas básicas (las mismas del XML data)
        default_lines = [
            # Líneas de Ingresos (36-49)
            {'sequence': 36, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 37, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 38, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 39, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 40, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 41, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 42, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 43, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 44, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 45, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 46, 'calculation': 'sum_rule', 'type_partner': 'employee', 'origin_severance_pay': 'employee'},
            {'sequence': 47, 'calculation': 'sum_rule', 'type_partner': 'employee', 'origin_severance_pay': 'fund'},
            {'sequence': 48, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 49, 'calculation': 'sum_sequence', 'sequence_list_sum': '36,37,38,39,40,41,42,43,44,45,46,47,48'},
            # Líneas de Aportes (50-54)
            {'sequence': 50, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 51, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 52, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 53, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 54, 'calculation': 'sum_sequence', 'sequence_list_sum': '50,51,52,53'},
            # Línea de Retención (55)
            {'sequence': 55, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            # Líneas de Información del Retenedor (5, 11)
            {'sequence': 5, 'calculation': 'info', 'type_partner': 'company'},
            {'sequence': 11, 'calculation': 'info', 'type_partner': 'company'},
            # Líneas de Información del Empleado (24-29)
            {'sequence': 24, 'calculation': 'info', 'type_partner': 'employee'},
            {'sequence': 25, 'calculation': 'info', 'type_partner': 'employee'},
            {'sequence': 26, 'calculation': 'info', 'type_partner': 'employee'},
            {'sequence': 27, 'calculation': 'info', 'type_partner': 'employee'},
            {'sequence': 28, 'calculation': 'info', 'type_partner': 'employee'},
            {'sequence': 29, 'calculation': 'info', 'type_partner': 'employee'},
            # Líneas de Fechas (30-32)
            {'sequence': 30, 'calculation': 'start_date_year'},
            {'sequence': 31, 'calculation': 'end_date_year'},
            {'sequence': 32, 'calculation': 'date_issue'},
        ]

        # Nombre (requerido) por secuencia: conceptos del formulario 220 DIAN
        concept_names = {
            5: 'Número de Identificación Tributaria (NIT)',
            11: 'Razón Social',
            24: 'Tipo de Documento',
            25: 'Número de Identificación',
            26: 'Primer Apellido',
            27: 'Segundo Apellido',
            28: 'Primer Nombre',
            29: 'Otros Nombres',
            30: 'Período de Certificación - DE',
            31: 'Período de Certificación - A',
            32: 'Fecha de expedición',
            36: 'Pagos por salarios o emolumentos eclesiásticos',
            37: 'Pagos realizados con bonos electrónicos o de papel de servicio, cheques, tarjetas, vales, etc.',
            38: 'Pagos por honorarios',
            39: 'Pagos por servicios',
            40: 'Pagos por comisiones',
            41: 'Pagos por prestaciones sociales',
            42: 'Pagos por viáticos',
            43: 'Pagos por gastos de representación',
            44: 'Pagos por compensaciones por el trabajo asociado cooperativo',
            45: 'Otros pagos',
            46: 'Cesantías e intereses de cesantías efectivamente pagadas al empleado',
            47: 'Cesantías consignadas al fondo de cesantías',
            48: 'Pensiones de jubilación, vejez o invalidez',
            49: 'Total de ingresos brutos (Sume 36 a 48)',
            50: 'Aportes obligatorios por salud a cargo del trabajador',
            51: 'Aportes obligatorios a fondos de pensiones y solidaridad pensional a cargo del trabajador',
            52: 'Cotizaciones voluntarias al régimen de ahorro individual con solidaridad - RAIS',
            53: 'Aportes voluntarios a fondos de pensiones',
            54: 'Aportes a cuentas AFC',
            55: 'Valor de la retención en la fuente por ingresos laborales y de pensiones',
        }

        # Crear líneas
        for line_vals in default_lines:
            line_vals['header_id'] = self.id
            line_vals.setdefault(
                'name',
                concept_names.get(line_vals['sequence'], f"Concepto {line_vals['sequence']}")
            )
            line_vals.setdefault('code', f"val{line_vals['sequence']}")
            self.env['hr.conf.certificate.income'].create(line_vals)

    @api.depends('uvt_value', 'patrimony_uvt', 'income_uvt')
    def _compute_cop_values(self):
        """Calcula los valores en COP basados en UVT"""
        for record in self:
            record.patrimony_cop = record.uvt_value * record.patrimony_uvt
            record.income_cop = record.uvt_value * record.income_uvt

    @api.depends('line_ids', 'line_ids.salary_rule_id', 'line_ids.information_fields_id')
    def _compute_configuration_status(self):
        """Determina si la configuración está completa"""
        for record in self:
            # Verificar que existan líneas
            if not record.line_ids:
                record.configuration_complete = False
                record.missing_items_count = 100
                continue

            # Contar líneas sin configuración completa
            incomplete = record.line_ids.filtered(
                lambda l: l.calculation in ['sum_rule', 'info'] and
                not (l.salary_rule_id or l.information_fields_id)
            )

            record.missing_items_count = len(incomplete)
            record.configuration_complete = len(incomplete) == 0

    @api.constrains('year')
    def _check_year(self):
        """Valida que el año esté en un rango razonable"""
        for record in self:
            current_year = fields.Date.today().year
            if record.year < 2000 or record.year > current_year + 2:
                raise ValidationError(
                    f'El año debe estar entre 2000 y {current_year + 2}'
                )

    @api.constrains('uvt_value')
    def _check_uvt_value(self):
        """Valida que el valor de la UVT sea positivo"""
        for record in self:
            if record.uvt_value <= 0:
                raise ValidationError('El valor de la UVT debe ser mayor que 0')

    @api.depends('year', 'company_id', 'company_id.name')
    def _compute_display_name(self):
        """Retorna nombre descriptivo"""
        for record in self:
            company_name = record.company_id.name if record.company_id else ''
            record.display_name = f"Certificado {record.year} - {company_name}"

    def copy(self, default=None):
        """Copia la configuración incrementando el año"""
        default = dict(default or {})
        default.update({
            'name': f"{self.name} (Copia)",
            'year': self.year + 1,
        })
        return super().copy(default)

    def action_open_wizard(self):
        """Abre el wizard para generar certificados"""
        self.ensure_one()
        return {
            'name': _('Generar Certificado de Ingresos y Retenciones'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.certificate.income.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_header_id': self.id,
                'default_year': self.year,
            }
        }

    def action_compute_from_parameters(self):
        """Calcula y completa la configuración desde los parámetros anuales"""
        self.ensure_one()

        # Buscar parámetros anuales
        annual_params = self.env['hr.annual.parameters'].get_for_year(
            self.year,
            company_id=self.company_id.id,
            raise_if_not_found=False,
        )

        if not annual_params:
            raise UserError(_(
                f'No se encontraron parámetros anuales para el año {self.year}. '
                'Por favor créelos primero.'
            ))

        # Actualizar UVT si está en los parámetros
        if annual_params.value_uvt:
            self.uvt_value = annual_params.value_uvt

        # Aquí se pueden agregar más cálculos automáticos
        # basados en los parámetros anuales

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Valores Actualizados'),
                'message': _('Se actualizaron los valores desde los parámetros anuales'),
                'sticky': False,
                'type': 'success',
            }
        }

    def action_load_default_configuration(self):
        """
        Carga configuración por defecto con toda la lógica automática:
        - Crea líneas desde XML si no existen
        - Asocia reglas salariales automáticamente
        - Configura cuentas contables
        - Actualiza valores UVT
        """
        self.ensure_one()

        # 1. Actualizar valores UVT desde parámetros anuales
        annual_params = self.env['hr.annual.parameters'].get_for_year(
            self.year,
            company_id=self.company_id.id,
            raise_if_not_found=False,
        )

        if annual_params and annual_params.value_uvt:
            self.uvt_value = annual_params.value_uvt

        # 2. Buscar líneas de data XML huérfanas y asociarlas
        orphan_lines = self.env['hr.conf.certificate.income'].search([
            ('header_id', '=', False),
            ('annual_parameters_id', '=', False)
        ])

        if orphan_lines:
            orphan_lines.write({'header_id': self.id})

        # 3. Si no hay líneas, crear estructura básica desde XML data
        if not self.line_ids:
            # Las líneas se crearán automáticamente desde el XML data
            # al actualizar el módulo
            pass

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Configuración Cargada'),
                'message': _('Se cargó la configuración por defecto exitosamente'),
                'sticky': False,
                'type': 'success',
            }
        }

    def action_view_configuration_status(self):
        """Muestra el estado de la configuración"""
        self.ensure_one()
        incomplete_lines = self.line_ids.filtered(
            lambda l: l.calculation in ['sum_rule', 'info'] and
            not (l.salary_rule_id or l.information_fields_id)
        )

        return {
            'name': _('Estado de Configuración'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.conf.certificate.income',
            'view_mode': 'list,form',
            'domain': [('id', 'in', incomplete_lines.ids)],
            'context': {'create': False}
        }


class HrConfCertificateIncome(models.Model):
    """Líneas de configuración para el certificado de ingresos"""
    _name = 'hr.conf.certificate.income'
    _description = 'Líneas de Configuración para Certificado de Ingresos'
    _order = 'header_id, sequence'

    # Relaciones principales
    header_id = fields.Many2one(
        'hr.certificate.income.header',
        string='Configuración',
        ondelete='cascade',
        index=True
    )
    annual_parameters_id = fields.Many2one(
        'hr.annual.parameters',
        string='Parámetro Anual',
        ondelete='cascade',
        index=True
    )

    # Secuencia y nombre
    sequence = fields.Integer(
        string='Secuencia',
        required=True,
        help='Número de campo en el certificado (ej: 36, 37, etc.)'
    )
    name = fields.Char(
        string='Nombre',
        compute='_compute_name',
        store=True
    )

    # Tipo de cálculo
    calculation = fields.Selection([
        ('info', 'Información'),
        ('sum_rule', 'Sumatoria de Reglas Salariales'),
        ('sum_sequence', 'Sumatoria de Secuencias Anteriores'),
        ('date_issue', 'Fecha de Expedición'),
        ('start_date_year', 'Fecha Inicial de Certificación'),
        ('end_date_year', 'Fecha Final de Certificación'),
        ('dependents_type_vat', 'Dependiente - Tipo Documento'),
        ('dependents_vat', 'Dependiente - Número Documento'),
        ('dependents_name', 'Dependiente - Apellidos y Nombres'),
        ('dependents_type', 'Dependiente - Parentesco'),
    ], string='Tipo de Cálculo', default='info', required=True)

    # Origen de información
    type_partner = fields.Selection([
        ('employee', 'Empleado'),
        ('company', 'Compañía')
    ], string='Origen de Información')

    # Campo de información
    information_fields_id = fields.Many2one(
        'ir.model.fields',
        string="Campo de Información",
        domain="[('model_id.model', 'in', ['hr.employee','res.partner','hr.contract'])]"
    )
    information_fields_relation = fields.Char(
        related='information_fields_id.relation',
        string='Relación del Campo',
        store=True
    )
    related_field_id = fields.Many2one(
        'ir.model.fields',
        string='Campo Relacionado',
        domain="[('model_id.model', '=', information_fields_relation)]"
    )

    # Reglas salariales
    salary_rule_id = fields.Many2many(
        'hr.salary.rule',
        'conf_certificate_salary_rule_rel',
        'config_id',
        'rule_id',
        string='Reglas Salariales'
    )

    # Configuración para cesantías
    origin_severance_pay = fields.Selection([
        ('employee', 'Pagado al Empleado'),
        ('fund', 'Consignado a Fondo')
    ], string='Origen Pago de Cesantías')

    # Configuración para acumulados
    accumulated_previous_year = fields.Boolean(
        string='Incluir Año Anterior',
        help='Incluye valores acumulados del año anterior'
    )
    sequence_list_sum = fields.Char(
        string='Secuencias a Sumar',
        help='Números de secuencia separados por coma (ej: 36,37,38)'
    )

    # Configuración para cesantías pagadas año anterior
    severance_paid_previous_year = fields.Boolean(
        string='Cesantías Pagadas Año Anterior',
        default=False,
        help='Marca si las cesantías fueron pagadas en el año anterior'
    )

    # Configuración contable específica
    account_ids = fields.Many2many(
        'account.account',
        'conf_certificate_account_rel',
        'config_id',
        'account_id',
        string='Cuentas Contables Específicas',
        help="Cuentas contables específicas para esta línea (opcional)"
    )

    # Tipo de movimiento contable
    account_move_type = fields.Selection([
        ('debit', 'Débito'),
        ('credit', 'Crédito'),
        ('both', 'Ambos (Débito + Crédito)')
    ], string='Tipo de Movimiento',
       default='both',
       help='Define si se toman movimientos de débito, crédito o ambos')

    # Diarios excluidos
    excluded_journal_ids = fields.Many2many(
        'account.journal',
        'conf_certificate_journal_rel',
        'config_id',
        'journal_id',
        string='Diarios Excluidos Específicos',
        help="Diarios excluidos específicos para esta línea (opcional)"
    )

    # Filtros adicionales de movimientos contables
    move_state_filter = fields.Selection([
        ('posted', 'Solo Publicados'),
        ('all', 'Todos'),
        ('draft', 'Solo Borradores')
    ], string='Estado de Movimientos',
       default='posted',
       help='Estado de los movimientos contables a incluir')

    exclude_payroll_entries = fields.Boolean(
        string='Excluir Asientos de Nómina',
        default=True,
        help='Excluye automáticamente los asientos contables generados por nómina para evitar duplicados'
    )

    # Categorías de reglas salariales alternativas
    salary_rule_category_ids = fields.Many2many(
        'hr.salary.rule.category',
        'conf_certificate_category_rel',
        'config_id',
        'category_id',
        string='Categorías de Reglas Salariales',
        help='Categorías de reglas salariales asociadas a esta configuración'
    )

    # Dominio personalizado para movimientos contables
    account_move_domain = fields.Char(
        string='Dominio Adicional',
        help='Dominio Odoo adicional para filtrar movimientos contables (ej: [(\'ref\', \'like\', \'ING\')])'
    )

    # Estado de configuración
    is_configured = fields.Boolean(
        string='Configurado',
        compute='_compute_is_configured',
        store=True
    )

    # Constraints
    _unique_sequence_header = models.Constraint('unique(header_id, sequence)',
                                                'Ya existe esta secuencia en la configuración')

    @api.depends('sequence', 'calculation')
    def _compute_name(self):
        """Genera nombre descriptivo"""
        for record in self:
            record.name = f"Campo {record.sequence} - {dict(record._fields['calculation'].selection).get(record.calculation, '')}"

    @api.depends('calculation', 'salary_rule_id', 'information_fields_id')
    def _compute_is_configured(self):
        """Determina si la línea está correctamente configurada"""
        for record in self:
            if record.calculation == 'sum_rule':
                record.is_configured = bool(record.salary_rule_id)
            elif record.calculation == 'info':
                record.is_configured = bool(record.information_fields_id)
            elif record.calculation == 'sum_sequence':
                record.is_configured = bool(record.sequence_list_sum)
            else:
                record.is_configured = True

    @api.onchange('header_id')
    def _onchange_header(self):
        """Hereda configuración del encabezado si está vacío"""
        if self.header_id and not self.account_ids:
            self.account_ids = self.header_id.account_ids
        if self.header_id and not self.excluded_journal_ids:
            self.excluded_journal_ids = self.header_id.excluded_journal_ids

    def _get_accounting_value(self, employee, date_from, date_to):
        """
        Calcula el valor desde movimientos contables usando ORM optimizado (_read_group)

        :param employee: Registro de hr.employee
        :param date_from: Fecha inicial del periodo
        :param date_to: Fecha final del periodo
        :return: float con el valor calculado
        """
        self.ensure_one()

        if not self.account_ids:
            return 0.0

        # Construir dominio base
        domain = [
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('account_id', 'in', self.account_ids.ids),
        ]

        # Filtro de estado de movimientos
        if self.move_state_filter == 'posted':
            domain.append(('move_id.state', '=', 'posted'))
        elif self.move_state_filter == 'draft':
            domain.append(('move_id.state', '=', 'draft'))

        # Excluir diarios específicos
        if self.excluded_journal_ids:
            domain.append(('journal_id', 'not in', self.excluded_journal_ids.ids))

        # Excluir asientos de nómina
        if self.exclude_payroll_entries:
            # Buscar diarios de nómina usando search_read optimizado
            payroll_journals = self.env['account.journal'].search_read(
                [
                    ('type', '=', 'general'),
                    '|',
                    ('name', 'ilike', 'nomina'),
                    ('name', 'ilike', 'payroll')
                ],
                ['id']
            )
            if payroll_journals:
                payroll_journal_ids = [j['id'] for j in payroll_journals]
                domain.append(('journal_id', 'not in', payroll_journal_ids))

            # Excluir asientos con referencia a nómina
            domain.extend([
                ('move_id.ref', 'not ilike', 'payslip'),
                ('move_id.ref', 'not ilike', 'nomina')
            ])

        # Filtrar por empleado (si la cuenta tiene partner asociado)
        if employee.work_contact_id:
            domain.append(('partner_id', '=', employee.work_contact_id.id))

        # Dominio adicional personalizado
        if self.account_move_domain:
            try:
                additional_domain = eval(self.account_move_domain)
                if isinstance(additional_domain, list):
                    domain.extend(additional_domain)
            except (KeyError, AttributeError):
                pass

        # Usar _read_group para calcular suma de forma optimizada
        MoveLine = self.env['account.move.line']

        if self.account_move_type == 'debit':
            # Sumar solo débitos usando _read_group
            result = MoveLine._read_group(
                domain,
                ['debit:sum'],
                []
            )
            return result[0]['debit'] if result else 0.0

        elif self.account_move_type == 'credit':
            # Sumar solo créditos usando _read_group
            result = MoveLine._read_group(
                domain,
                ['credit:sum'],
                []
            )
            return result[0]['credit'] if result else 0.0

        elif self.account_move_type == 'both':
            # Sumar débitos + créditos usando _read_group
            result = MoveLine._read_group(
                domain,
                ['debit:sum', 'credit:sum'],
                []
            )
            if result:
                return result[0]['debit'] + result[0]['credit']
            return 0.0

        return 0.0

    def _get_payslip_value_by_categories(self, employee, date_from, date_to):
        """
        Calcula el valor desde líneas de nómina usando ORM optimizado (_read_group)

        :param employee: Registro de hr.employee
        :param date_from: Fecha inicial del periodo
        :param date_to: Fecha final del periodo
        :return: float con el valor calculado
        """
        self.ensure_one()

        if not self.salary_rule_category_ids:
            return 0.0

        # Construir dominio para líneas de nómina
        domain = [
            ('slip_id.employee_id', '=', employee.id),
            ('slip_id.date_from', '>=', date_from),
            ('slip_id.date_to', '<=', date_to),
            ('slip_id.state', 'in', ['done', 'paid']),
            ('category_id', 'in', self.salary_rule_category_ids.ids)
        ]

        # Usar _read_group para sumar totales de forma optimizada
        PayslipLine = self.env['hr.payslip.line']
        result = PayslipLine._read_group(
            domain,
            ['total:sum'],
            []
        )

        return result[0]['total'] if result else 0.0

    def _get_payslip_value_by_rules(self, employee, date_from, date_to):
        """
        Calcula el valor desde líneas de nómina usando reglas salariales directamente

        :param employee: Registro de hr.employee
        :param date_from: Fecha inicial del periodo
        :param date_to: Fecha final del periodo
        :return: float con el valor calculado
        """
        self.ensure_one()

        if not self.salary_rule_id:
            return 0.0

        # Construir dominio para líneas de nómina por regla salarial
        domain = [
            ('slip_id.employee_id', '=', employee.id),
            ('slip_id.date_from', '>=', date_from),
            ('slip_id.date_to', '<=', date_to),
            ('slip_id.state', 'in', ['done', 'paid']),
            ('salary_rule_id', 'in', self.salary_rule_id.ids)
        ]

        # Filtro adicional por origen de cesantías si aplica
        if self.origin_severance_pay:
            # Aquí se puede agregar lógica adicional para filtrar por origen
            pass

        # Usar _read_group para sumar totales
        PayslipLine = self.env['hr.payslip.line']
        result = PayslipLine._read_group(
            domain,
            ['total:sum'],
            []
        )

        return result[0]['total'] if result else 0.0

    def compute_line_value(self, employee, date_from, date_to):
        """
        Método integrador que calcula el valor de la línea según su configuración
        Usa la lógica contable, de nómina por reglas o categorías automáticamente

        :param employee: Registro de hr.employee
        :param date_from: Fecha inicial del periodo
        :param date_to: Fecha final del periodo
        :return: float con el valor calculado
        """
        self.ensure_one()

        # Si tiene configuración contable, usarla primero
        if self.account_ids and self.calculation == 'sum_rule':
            return self._get_accounting_value(employee, date_from, date_to)

        # Si tiene reglas salariales, calcular desde nómina
        if self.salary_rule_id and self.calculation == 'sum_rule':
            return self._get_payslip_value_by_rules(employee, date_from, date_to)

        # Si tiene categorías, calcular por categorías
        if self.salary_rule_category_ids and self.calculation == 'sum_rule':
            return self._get_payslip_value_by_categories(employee, date_from, date_to)

        # Para otros tipos de cálculo, retornar 0
        return 0.0
