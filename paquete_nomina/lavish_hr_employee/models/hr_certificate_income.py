# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from datetime import datetime, timedelta, date
from odoo.exceptions import UserError, ValidationError
import time

# Template HTML por defecto para el certificado
DEFAULT_HTML_TEMPLATE = '''
<table class="table border_report col-12" style="font-size: x-small;margin: 0px;">
    <tr>
        <td colspan="2"></td>
        <td colspan="8">
            <b>
                <center>
                    <h5>Certificado de Ingresos y Retenciones por Rentas de Trabajo y Pensiones
                        año
                        Agravable {year}
                    </h5>
                </center>
            </b>
        </td>
        <td colspan="2"></td>
    </tr>
    <tr>
        <td colspan="7">
            <br/>
            <center>
                <b>Antes de diligenciar este formulario lea
                    cuidadosamente
                    las instrucciones
                </b>
            </center>
        </td>
        <td colspan="5">4. Número de formulario
            <br/>
            $_val4_$
        </td>
    </tr>
    <tr>
        <td class="th_report rotate" rowspan="2">
            <div style="padding-right: 60px !important;">
                <b>Retenedor</b>
            </div>
        </td>
        <td colspan="2">
            5. Número de Identificación Tributaria (NIT)
            <br/>
            $_val5_$
        </td>
        <td class="width_items" colspan="1">6. D.V
            <br/>
            $_val6_$
        </td>

        <td colspan="2">7. Primer Apellido
            <br/>
            $_val7_$
        </td>

        <td colspan="2">8. Segundo Apellido
            <br/>
            $_val8_$
        </td>
        <td colspan="2">9. Primer Nombre
            <br/>
            $_val9_$
        </td>
        <td colspan="2">10. Otros Nombres
            <br/>
            $_val10_$
        </td>
    </tr>
    <tr>
        <td colspan="11">11. Razón Social
            <br/>
            $_val11_$
        </td>
    </tr>
    <tr>
        <td class="rotate">
            <div style="padding-right: 30px !important;">
                <b>Empleado</b>
            </div>
        </td>
        <td colspan="1">24. Tipo de Documento
            <br/>
            $_val24_$
        </td>
        <td colspan="3">25. Número de Identificación
            <br/>
            $_val25_$
        </td>
        <td colspan="2">26. Primer Apellido
            <br/>
            $_val26_$
        </td>
        <td colspan="2">27. Segundo Apellido
            <br/>
            $_val27_$
        </td>
        <td colspan="2">28. Primer Nombre
            <br/>
            $_val28_$
        </td>
        <td colspan="2">29. Otros Nombres
            <br/>
            $_val29_$
        </td>
    </tr>
    <tr>
        <td colspan="5">Período de Certificación
            <br/>
            30. DE $_val30_$ 31. A $_val31_$
        </td>
        <td colspan="2">32. Fecha de expedición
            <br/>
            $_val32_$
        </td>
        <td colspan="3">33. Lugar donde se practicó la retención
            <br/>
            $_val33_$
        </td>
        <td  colspan="1">34. Cód.Dpto
            <br/>
            $_val34_$
        </td>
        <td colspan="1">35. Cód.Ciudad/Municipio
            <br/>
            $_val35_$
        </td>
    </tr>
</table>
<table class="table table-striped border_report col-12" style="font-size: x-small;margin: 0px;">
    <tr>
        <td colspan="9">
            <center>
                <b>Concepto de los Ingresos</b>
            </center>
        </td>
        <td colspan="1" class="width_items">
            <b></b>
        </td>
        <td colspan="2" class="width_values">
            <center>
                <b>Valor</b>
            </center>
        </td>
    </tr>
    <tr>
        <td colspan="9">Pagos por salarios o emolumentos eclesiásticos</td>
        <td colspan="1" class="width_items">36</td>
        <td colspan="2" class="width_values">$_val36_$</td>
    </tr>
    <tr>
        <td colspan="9">Pagos realizados con bonos electrónicos o de papel de servicio, cheques,
            tarjetas,
            vales, etc.
        </td>
        <td colspan="1" class="width_items">37</td>
        <td colspan="2" class="width_values">$_val37_$</td>
    </tr>
    <tr>
        <td colspan="9">Pagos por honorarios</td>
        <td colspan="1" class="width_items">38</td>
        <td colspan="2" class="width_values">$_val38_$</td>
    </tr>
    <tr>
        <td colspan="9">Pagos por servicios</td>
        <td colspan="1" class="width_items">39</td>
        <td colspan="2" class="width_values">$_val39_$</td>
    </tr>
    <tr>
        <td colspan="9">Pagos por comisiones</td>
        <td colspan="1" class="width_items">40</td>
        <td colspan="2" class="width_values">$_val40_$</td>
    </tr>
    <tr>
        <td colspan="9">Pagos por prestaciones sociales</td>
        <td colspan="1" class="width_items">41</td>
        <td colspan="2" class="width_values">$_val41_$</td>
    </tr>
    <tr>
        <td colspan="9">Pagos por viáticos</td>
        <td colspan="1" class="width_items">42</td>
        <td colspan="2" class="width_values">$_val42_$</td>
    </tr>
    <tr>
        <td colspan="9">Pagos por gastos de representación</td>
        <td colspan="1" class="width_items">43</td>
        <td colspan="2" class="width_values">$_val43_$</td>
    </tr>
    <tr>
        <td colspan="9">Pagos por compensaciones por el trabajo asociado cooperativo</td>
        <td colspan="1" class="width_items">44</td>
        <td colspan="2" class="width_values">$_val44_$</td>
    </tr>
    <tr>
        <td colspan="9">Otros pagos</td>
        <td colspan="1" class="width_items">45</td>
        <td colspan="2" class="width_values">$_val45_$</td>
    </tr>
    <tr>
        <td colspan="9">Cesantías e intereses de cesantías efectivamente pagadas al empleado</td>
        <td colspan="1" class="width_items">46</td>
        <td colspan="2" class="width_values">$_val46_$</td>
    </tr>
    <tr>
        <td colspan="9">Cesantías consignadas al fondo de cesantias</td>
        <td colspan="1" class="width_items">47</td>
        <td colspan="2" class="width_values">$_val47_$</td>
    </tr>
    <tr>
        <td colspan="9">Pensiones de jubilación, vejez o invalidez</td>
        <td colspan="1" class="width_items">48</td>
        <td colspan="2" class="width_values">$_val48_$</td>
    </tr>
    <tr>
        <td colspan="9">Total de ingresos brutos (Sume 36 a 48)</td>
        <td colspan="1" class="width_items">49</td>
        <td colspan="2" class="width_values">$_val49_$</td>
    </tr>
    <!--Concepto de los Aportes-->
    <tr>
        <td colspan="9">
            <center>
                <b>Concepto de los Aportes</b>
            </center>
        </td>
        <td colspan="1" class="width_items">
            <b></b>
        </td>
        <td colspan="2" class="width_values">
            <center>
                <b>Valor</b>
            </center>
        </td>
    </tr>
    <tr>
        <td colspan="9">Aportes obligatorios por salud a cargo del trabajador</td>
        <td colspan="1" class="width_items">50</td>
        <td colspan="2" class="width_values">$_val50_$</td>
    </tr>
    <tr>
        <td colspan="9">Aportes obligatorios a fondos de pensiones y solidaridad pensional a
            cargo del
            trabajador
        </td>
        <td colspan="1" class="width_items">51</td>
        <td colspan="2" class="width_values">$_val51_$</td>
    </tr>
    <tr>
        <td colspan="9">Cotizaciones voluntarias al régimen de ahorro individual con solidaridad
            - RAIS
        </td>
        <td colspan="1" class="width_items">52</td>
        <td colspan="2" class="width_values">$_val52_$</td>
    </tr>
    <tr>
        <td colspan="9">Aportes voluntarios a fondos de pensiones</td>
        <td colspan="1" class="width_items">53</td>
        <td colspan="2" class="width_values">$_val53_$</td>
    </tr>
    <tr>
        <td colspan="9">Aportes a cuentas AFC</td>
        <td colspan="1" class="width_items">54</td>
        <td colspan="2" class="width_values">$_val54_$</td>
    </tr>
    <tr>
        <td colspan="9" style="background:#335E8B; color: white">Valor de la retención en la
            fuente por ingresos laborales y de pensiones
        </td>
        <td colspan="1" class="width_items">55</td>
        <td colspan="2" class="width_values">$_val55_$</td>
    </tr>
    <tr>
        <td colspan="12">Nombre del pagador o agente retenedor</td>
    </tr>
    <!--                            Datos a cargo del trabajador o pensionado-->
    <tr>
        <td colspan="12">
            <center>
                <b>Datos a cargo del trabajador o pensionado</b>
            </center>
        </td>
    </tr>
    <tr>
        <td colspan="6">
            <center>
                <b>Concepto de otros ingresos</b>
            </center>
        </td>
        <td colspan="1" class="width_items"></td>
        <td colspan="2" class="width_values">
            <center>
                <b>Valor Recibido</b>
            </center>
        </td>
        <td colspan="1" class="width_items"></td>
        <td colspan="2" class="width_values">
            <center>
                <b>Valor Retenido</b>
            </center>
        </td>
    </tr>
    <tr>
        <td colspan="6">Arrendamientos</td>
        <td colspan="1" class="width_items">56</td>
        <td colspan="2" class="width_values">$_val56_$</td>
        <td colspan="1" class="width_items">63</td>
        <td colspan="2" class="width_values">$_val63_$</td>
    </tr>
    <tr>
        <td colspan="6">Honorarios, comisiones y servicios</td>
        <td colspan="1" class="width_items">57</td>
        <td colspan="2" class="width_values">$_val57_$</td>
        <td colspan="1" class="width_items">64</td>
        <td colspan="2" class="width_values">$_val64_$</td>
    </tr>
    <tr>
        <td colspan="6">Intereses y rendimientos financieros</td>
        <td colspan="1" class="width_items">58</td>
        <td colspan="2" class="width_values">$_val58_$</td>
        <td colspan="1" class="width_items">65</td>
        <td colspan="2" class="width_values">$_val65_$</td>
    </tr>
    <tr>
        <td colspan="6">Enajenación de activos fijos</td>
        <td colspan="1" class="width_items">59</td>
        <td colspan="2" class="width_values">$_val59_$</td>
        <td colspan="1" class="width_items">66</td>
        <td colspan="2" class="width_values">$_val66_$</td>
    </tr>
    <tr>
        <td colspan="6">Loterías, rifas, apuestas y similares</td>
        <td colspan="1" class="width_items">60</td>
        <td colspan="2" class="width_values">$_val60_$</td>
        <td colspan="1" class="width_items">67</td>
        <td colspan="2" class="width_values">$_val67_$</td>
    </tr>
    <tr>
        <td colspan="6">Otros</td>
        <td colspan="1" class="width_items">61</td>
        <td colspan="2" class="width_values">$_val61_$</td>
        <td colspan="1" class="width_items">68</td>
        <td colspan="2" class="width_values">$_val68_$</td>
    </tr>
    <tr>
        <td colspan="6">Totales: (Valor recibido: Sume 57 a 61), (Valor retenido: Sume 63 a 68)</td>
        <td colspan="1" class="width_items">62</td>
        <td colspan="2" class="width_values">$_val62_$</td>
        <td colspan="1" class="width_items">69</td>
        <td colspan="2" class="width_values">$_val69_$</td>
    </tr>
    <tr>
        <td colspan="9">Total retenciones año gravable {year} (Sume 55 + 69)</td>
        <td colspan="1" class="width_items">70</td>
        <td colspan="2" class="width_values">$_val70_$</td>
    </tr>
    <!--Identificación de los bienes y derechos poseídos-->
    <tr>
        <td colspan="1" class="width_items">
            <center>
                <b>Item</b>
            </center>
        </td>
        <td colspan="9">
            <center>
                <b>71. Identificación de los bienes y derechos poseídos</b>
            </center>
        </td>
        <td colspan="2" class="width_values">
            <center>
                <b>72. Valor patrimonial</b>
            </center>
        </td>
    </tr>
    <tr>
        <td colspan="1" class="width_items">1</td>
        <td colspan="9">$_val71.1_$</td>
        <td colspan="2" class="width_values">$_val72.1_$</td>
    </tr>
    <tr>
        <td colspan="1" class="width_items">2</td>
        <td colspan="9">$_val71.2_$</td>
        <td colspan="2" class="width_values">$_val72.2_$</td>
    </tr>
    <tr>
        <td colspan="1" class="width_items">3</td>
        <td colspan="9">$_val71.3_$</td>
        <td colspan="2" class="width_values">$_val72.3_$</td>
    </tr>
    <tr>
        <td colspan="1" class="width_items">4</td>
        <td colspan="9">$_val71.4_$</td>
        <td colspan="2" class="width_values">$_val72.4_$</td>
    </tr>
    <tr>
        <td colspan="1" class="width_items">5</td>
        <td colspan="9">$_val71.5_$</td>
        <td colspan="2" class="width_values">$_val72.5_$</td>
    </tr>
    <tr>
        <td colspan="1" class="width_items">6</td>
        <td colspan="9">$_val71.6_$</td>
        <td colspan="2" class="width_values">$_val72.6_$</td>
    </tr>
    <tr>
        <td colspan="9" style="background:#335E8B; color: white">Deudas vigentes a 31 de
            diciembre de {year}
        </td>
        <td colspan="1" class="width_items">73</td>
        <td colspan="2" class="width_values">$_val73_$</td>
    </tr>
</table>
<table class="table border_report col-12" style="font-size: x-small;margin: 0px;">
    <!--Identificación del dependiente económico de acuerdo al parágrafo 2 del artículo 387 del Estatuto Tributario-->
    <tr>
        <td colspan="12">
            <center>
                <b>Identificación del dependiente económico de acuerdo al parágrafo 2 del
                    artículo
                    387 del Estatuto Tributario
                </b>
            </center>
        </td>
    </tr>
    <tr>
        <td colspan="2" class="th_report">74. Tipo documento
            <br/>
            $_val74_$
        </td>
        <td colspan="2" class="th_report">75. No. Documento
            <br/>
            $_val75_$
        </td>
        <td colspan="6" class="th_report">76. Apellidos y Nombres
            <br/>
            $_val76_$
        </td>
        <td colspan="2" class="th_report">77. Parentesco
            <br/>
            $_val77_$
        </td>
    </tr>
    <tr>
        <td colspan="8">
            Certifico que durante el año gravable {year}:
            <br/>
            1. Mi patrimonio bruto no excedió de 4.500 UVT ({uvt_4500}).
            <br/>
            2. Mis ingresos brutos fueron inferiores a 1.400 UVT ({uvt_1400}).
            <br/>
            3. No fui responsable del impuesto sobre las ventas.
            <br/>
            4. Mis consumos mediante tarjeta de crédito no excedieron la suma de 1.400 UVT
            ({uvt_1400}).
            <br/>
            5. Que el total de mis compras y consumos no superaron la suma de 1.400 UVT
            ({uvt_1400}).
            <br/>
            6. Que el valor total de mis consignaciones bancarias, depósitos o inversiones
            financieras no excedieron los 1.400 UVT ({uvt_1400}).
            <br/>
            Por lo tanto, manifiesto que no estoy obligado a presentar declaración de renta y
            complementario por el año gravable {year}
        </td>
        <td colspan="4">
            Firma del Trabajador o Pensionado
        </td>
    </tr>
</table>
<p style="font-size: x-small">
    <b>Nota:</b>
    este certificado sustituye para todos los efectos legales la declaración de Renta y
    Complementario para el trabajador o pensionado que lo firme.
    <br/>
    Para aquellos trabajadores independientes contribuyentes del impuesto unificado deberán
    presentar la declaración anual consolidada del Régimen Simple de Tributación (SIMPLE).
</p>
'''


class HrCertificateIncomeHeader(models.Model):
    """
    Modelo principal para la configuración del certificado de ingresos y retenciones.
    Gestiona la configuración maestra del certificado para un año fiscal específico.
    """
    _inherit = 'hr.certificate.income.header'
    _order = 'year desc, company_id'
    _rec_name = 'display_name'

    # Campos de identificación
    name = fields.Char(
        string='Nombre', 
        required=True, 
        tracking=True,
        help="Nombre descriptivo de la configuración"
    )
    display_name = fields.Char(
        string='Nombre Completo',
        compute='_compute_display_name',
        store=True
    )
    company_id = fields.Many2one(
        'res.company', 
        string='Compañía', 
        default=lambda self: self.env.company, 
        tracking=True,
        required=True
    )
    year = fields.Integer(
        string='Año Fiscal', 
        required=True, 
        tracking=True,
        help="Año fiscal para el cual aplica esta configuración"
    )
    active = fields.Boolean(
        default=True,
        help="Si está desactivado, esta configuración no se usará"
    )
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('confirmed', 'Confirmado'),
        ('done', 'Procesado'),
        ('cancelled', 'Cancelado')
    ], string='Estado', default='draft', tracking=True)
    
    # Campos de configuración general
    description = fields.Text(
        string='Descripción',
        help="Descripción detallada del propósito de esta configuración"
    )
    form_number = fields.Char(
        string='Número de Formulario', 
        tracking=True,
        help="Número único del formulario según DIAN"
    )
    issue_date = fields.Date(
        string='Fecha de Expedición', 
        tracking=True,
        default=fields.Date.today
    )
    
    # Configuración UVT
    uvt_value = fields.Float(
        string='Valor UVT', 
        required=True, 
        tracking=True,
        help="Valor de la Unidad de Valor Tributario para el año"
    )
    patrimony_uvt = fields.Float(
        string='UVT Patrimonio', 
        default=4500, 
        tracking=True,
        help='UVT para límite de patrimonio bruto'
    )
    income_uvt = fields.Float(
        string='UVT Ingresos', 
        default=1400, 
        tracking=True,
        help='UVT para límite de ingresos brutos'
    )
    
    # Campos computados para valores en pesos
    patrimony_value = fields.Float(
        string='Valor Patrimonio',
        compute='_compute_uvt_values',
        store=True,
        help="Valor del límite de patrimonio en pesos"
    )
    income_value = fields.Float(
        string='Valor Ingresos',
        compute='_compute_uvt_values',
        store=True,
        help="Valor del límite de ingresos en pesos"
    )
    
    # Configuración de integración contable
    account_config_type = fields.Selection([
        ('manual', 'Configuración Manual'),
        ('account_group', 'Por Grupo de Cuentas'),
        ('account_type', 'Por Tipo de Cuenta'),
        ('tax_group', 'Por Grupo de Impuestos')
    ], string='Tipo de Configuración Contable', 
       default='manual',
       help="Define cómo se seleccionarán las cuentas contables"
    )
    
    account_ids = fields.Many2many(
        'account.account',
        'certificate_header_account_rel',
        'header_id',
        'account_id',
        string='Cuentas Contables',
        domain="[('company_ids', 'in', [company_id])]",
        help="Cuentas contables a considerar en el cálculo"
    )
    
    account_group_ids = fields.Many2many(
        'account.group',
        string='Grupos de Cuentas',
        help="Grupos de cuentas contables para filtrar automáticamente"
    )
    
    account_type_ids = fields.Many2many(
        'account.account.type',
        string='Tipos de Cuenta',
        help="Tipos de cuenta para filtrar automáticamente"
    )
    
    excluded_journal_ids = fields.Many2many(
        'account.journal',
        'certificate_header_journal_rel',
        'header_id',
        'journal_id',
        string='Diarios Excluidos',
        domain="[('company_id', 'in', [company_id])]",
        help="Diarios que se excluirán del cálculo"
    )
    
    # Configuración de período contable
    date_from = fields.Date(
        string='Fecha Desde',
        required=True,
        help="Fecha de inicio del período a certificar"
    )
    date_to = fields.Date(
        string='Fecha Hasta',
        required=True,
        help="Fecha de fin del período a certificar"
    )
    
    # Relación con líneas de configuración
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
        help="Plantilla HTML para generar el certificado"
    )
    
    # Estadísticas
    certificate_count = fields.Integer(
        string='Certificados Generados',
        compute='_compute_certificate_count'
    )
    
    _unique_year_company = models.Constraint('unique(year, company_id, active)',
                                              'Ya existe una configuración activa para este año y compañía')
    _check_dates = models.Constraint('CHECK(date_from <= date_to)',
                                     'La fecha inicial debe ser menor o igual a la fecha final')
    _check_year = models.Constraint('CHECK(year >= 2000 AND year <= 2100)',
                                    'El año debe estar entre 2000 y 2100')
    _check_uvt_positive = models.Constraint('CHECK(uvt_value > 0)',
                                            'El valor UVT debe ser positivo')
    
    @api.depends('name', 'year', 'company_id')
    def _compute_display_name(self):
        for record in self:
            record.display_name = f"{record.name} - {record.year} ({record.company_id.name})"
    
    @api.depends('uvt_value', 'patrimony_uvt', 'income_uvt')
    def _compute_uvt_values(self):
        for record in self:
            record.patrimony_value = record.uvt_value * record.patrimony_uvt
            record.income_value = record.uvt_value * record.income_uvt
    
    def _compute_certificate_count(self):
        """Calcula el número de certificados generados con esta configuración"""
        for record in self:
            # Este método deberá implementarse cuando se cree el modelo de certificados
            record.certificate_count = 0
    
    @api.onchange('year')
    def _onchange_year(self):
        """Actualiza las fechas por defecto basadas en el año"""
        if self.year:
            self.date_from = fields.Date.from_string(f'{self.year}-01-01')
            self.date_to = fields.Date.from_string(f'{self.year}-12-31')

    @api.model_create_multi
    def create(self, vals_list):
        """Rellena date_from/date_to desde el año si no se proporcionan.

        Los onchange no disparan en creaciones programáticas (post_init_hook,
        wizard de copia, data), por lo que estos campos requeridos quedaban en
        NULL -> NotNullViolation. Aquí se calculan a partir de `year`.
        """
        for vals in vals_list:
            year = vals.get('year')
            if year:
                vals.setdefault('date_from', fields.Date.from_string(f'{year}-01-01'))
                vals.setdefault('date_to', fields.Date.from_string(f'{year}-12-31'))
        return super().create(vals_list)

    @api.onchange('account_config_type')
    def _onchange_account_config_type(self):
        """Limpia los campos no relevantes cuando cambia el tipo de configuración"""
        if self.account_config_type != 'manual':
            self.account_ids = False
        if self.account_config_type != 'account_group':
            self.account_group_ids = False
        if self.account_config_type != 'account_type':
            self.account_type_ids = False
    
    def action_confirm(self):
        """Confirma la configuración"""
        self.ensure_one()
        if not self.line_ids:
            raise ValidationError(_('Debe agregar al menos una línea de configuración'))
        self.state = 'confirmed'
        return True
    
    def action_cancel(self):
        """Cancela la configuración"""
        self.state = 'cancelled'
        return True
    
    def action_draft(self):
        """Vuelve a borrador"""
        self.state = 'draft'
        return True
    
    def action_compute_values(self):
        """Acción para calcular los valores del certificado basado en contabilidad"""
        self.ensure_one()
        
        # Obtener cuentas según el tipo de configuración
        accounts = self._get_configured_accounts()
        
        # Obtener movimientos contables del período
        domain = [
            ('account_id', 'in', accounts.ids),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('company_id', '=', self.company_id.id),
            ('parent_state', '=', 'posted')
        ]
        
        if self.excluded_journal_ids:
            domain.append(('journal_id', 'not in', self.excluded_journal_ids.ids))
        
        move_lines = self.env['account.move.line'].search(domain)
        
        # Procesar valores según las líneas de configuración
        for line in self.line_ids:
            line.compute_value(move_lines)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Cálculo Completado'),
                'message': _('Los valores han sido calculados exitosamente'),
                'sticky': False,
                'type': 'success',
            }
        }
    
    def _get_configured_accounts(self):
        """Obtiene las cuentas según el tipo de configuración"""
        self.ensure_one()
        
        if self.account_config_type == 'manual':
            return self.account_ids
        
        domain = [('company_id', '=', self.company_id.id)]
        
        if self.account_config_type == 'account_group':
            if self.account_group_ids:
                domain.append(('group_id', 'in', self.account_group_ids.ids))
        
        elif self.account_config_type == 'account_type':
            if self.account_type_ids:
                domain.append(('account_type', 'in', self.account_type_ids.mapped('code')))
        
        return self.env['account.account'].search(domain)
    
    def copy(self, default=None):
        default = dict(default or {})
        default.update({
            'name': f"{self.name} (Copia)",
            'year': self.year + 1,
            'state': 'draft',
            'date_from': fields.Date.from_string(f'{self.year + 1}-01-01'),
            'date_to': fields.Date.from_string(f'{self.year + 1}-12-31'),
        })
        return super().copy(default)
    
    def action_view_certificates(self):
        """Abre la vista de certificados generados"""
        self.ensure_one()
        # Este método deberá implementarse cuando se cree el modelo de certificados
        return {
            'type': 'ir.actions.act_window',
            'name': _('Certificados Generados'),
            'res_model': 'hr.certificate.income',
            'view_mode': 'tree,form',
            'domain': [('header_id', '=', self.id)],
            'context': {'default_header_id': self.id}
        }


class HrConfCertificateIncome(models.Model):
    """
    Líneas de configuración detallada para cada concepto del certificado.
    Define cómo se calculará cada valor del certificado.
    """
    _inherit = 'hr.conf.certificate.income'
    _order = 'sequence, id'

    header_id = fields.Many2one(
        'hr.certificate.income.header',
        string='Encabezado',
        ondelete='cascade',
        required=True
    )
    
    sequence = fields.Integer(
        string='Secuencia',
        default=10,
        help="Número de secuencia para el orden de procesamiento"
    )
    
    name = fields.Char(
        string='Descripción',
        required=True,
        help="Descripción del concepto a calcular"
    )
    
    code = fields.Char(
        string='Código',
        help="Código del campo en el formulario (ej: val36, val37, etc.)"
    )
    
    # Tipo de cálculo
    calculation = fields.Selection([
        ('info', 'Información'),
        ('sum_rule', 'Sumatoria Reglas Salariales'),
        ('sum_account', 'Sumatoria Cuentas Contables'),
        ('sum_sequence', 'Sumatoria Secuencias Anteriores'),
        ('date_issue', 'Fecha Expedición'),
        ('start_date_year', 'Fecha Certificación Inicial'),
        ('end_date_year', 'Fecha Certificación Final'),
        ('dependents_type_vat', 'Dependientes - Tipo Documento'),
        ('dependents_vat', 'Dependientes - No. Documento'),
        ('dependents_name', 'Dependientes - Apellidos y Nombres'),
        ('dependents_type', 'Dependientes - Parentesco'),
        ('tax_calculation', 'Cálculo de Impuestos'),
        ('accounting_balance', 'Balance Contable'),
    ], string='Tipo Cálculo', default='info', required=True)
    
    # Origen de información
    type_partner = fields.Selection([
        ('employee', 'Empleado'),
        ('company', 'Compañía'),
        ('partner', 'Tercero')
    ], string='Origen Información')
    
    # Campos para información de empleado/partner
    information_fields_id = fields.Many2one(
        'ir.model.fields',
        string="Campo de Información",
        domain="[('model_id.model', 'in', ['hr.employee','res.partner','hr.contract','res.company'])]",
        help="Campo del modelo de donde se tomará la información"
    )
    
    information_fields_relation = fields.Char(
        related='information_fields_id.relation',
        string='Relación del Objeto',
        store=True
    )
    
    related_field_id = fields.Many2one(
        'ir.model.fields',
        string='Campo Relacionado',
        domain="[('model_id.model', '=', information_fields_relation)]",
        help="Campo adicional cuando hay relación"
    )
    
    # Configuración para reglas salariales
    salary_rule_ids = fields.Many2many(
        'hr.salary.rule',
        'certificate_line_rule_rel',
        'line_id',
        'rule_id',
        string='Reglas Salariales',
        help="Reglas salariales a sumar para este concepto"
    )
    
    # Configuración específica para cuentas contables
    account_ids = fields.Many2many(
        'account.account',
        'certificate_line_account_rel',
        'line_id',
        'account_id',
        string='Cuentas Contables',
        domain="[('company_ids', 'in', [header_id.company_id])]",
        help="Cuentas contables específicas para esta línea"
    )
    
    account_tag_ids = fields.Many2many(
        'account.account.tag',
        string='Etiquetas de Cuenta',
        help="Etiquetas para filtrar cuentas contables"
    )
    
    excluded_journal_ids = fields.Many2many(
        'account.journal',
        'certificate_line_journal_rel',
        'line_id',
        'journal_id',
        string='Diarios Excluidos',
        help="Diarios excluidos específicos para esta línea"
    )
    
    # Configuración adicional
    origin_severance_pay = fields.Selection([
        ('employee', 'Empleado'),
        ('fund', 'Fondo')
    ], string='Origen Pago Cesantías')
    
    accumulated_previous_year = fields.Boolean(
        string='Acumulado Año Anterior',
        help="Incluir valores acumulados del año anterior"
    )
    
    sequence_list_sum = fields.Char(
        string='Secuencias a Sumar',
        help="Lista de secuencias separadas por comas (ej: 36,37,38)"
    )
    
    # Configuración de balance contable
    balance_type = fields.Selection([
        ('debit', 'Débito'),
        ('credit', 'Crédito'),
        ('balance', 'Balance')
    ], string='Tipo de Balance', default='balance')
    
    # Campos para cálculo de impuestos
    tax_group_id = fields.Many2one(
        'account.tax.group',
        string='Grupo de Impuesto',
        help="Grupo de impuesto para cálculos tributarios"
    )
    
    # Resultado del cálculo
    computed_value = fields.Float(
        string='Valor Calculado',
        readonly=True,
        help="Último valor calculado para esta línea"
    )
    
    last_compute_date = fields.Datetime(
        string='Última Actualización',
        readonly=True
    )
    
    _unique_sequence_header = models.Constraint('unique(header_id, sequence)',
                                                'Ya existe esta secuencia en el encabezado, por favor verificar')
    _unique_code_header = models.Constraint('unique(header_id, code)',
                                            'Ya existe este código en el encabezado')
    
    @api.onchange('header_id')
    def _onchange_header(self):
        """Hereda configuración del encabezado si está vacía"""
        if self.header_id:
            if not self.account_ids and self.calculation == 'sum_account':
                self.account_ids = self.header_id.account_ids
            if not self.excluded_journal_ids:
                self.excluded_journal_ids = self.header_id.excluded_journal_ids
    
    @api.onchange('calculation')
    def _onchange_calculation(self):
        """Limpia campos no relevantes según el tipo de cálculo"""
        if self.calculation != 'sum_rule':
            self.salary_rule_ids = False
        if self.calculation not in ['sum_account', 'accounting_balance']:
            self.account_ids = False
            self.account_tag_ids = False
        if self.calculation != 'sum_sequence':
            self.sequence_list_sum = False
        if self.calculation != 'tax_calculation':
            self.tax_group_id = False
    
    def compute_value(self, move_lines=None):
        """
        Calcula el valor de esta línea según su configuración
        
        Args:
            move_lines: Líneas de movimientos contables pre-filtradas
        
        Returns:
            float: Valor calculado
        """
        self.ensure_one()
        value = 0.0
        
        if self.calculation == 'sum_account':
            value = self._compute_account_sum(move_lines)
        elif self.calculation == 'accounting_balance':
            value = self._compute_accounting_balance(move_lines)
        elif self.calculation == 'sum_rule':
            value = self._compute_salary_rules_sum()
        elif self.calculation == 'sum_sequence':
            value = self._compute_sequence_sum()
        elif self.calculation == 'tax_calculation':
            value = self._compute_tax_value(move_lines)
        elif self.calculation in ['date_issue', 'start_date_year', 'end_date_year']:
            value = self._compute_date_value()
        elif self.calculation == 'info':
            value = self._compute_info_value()
        
        self.computed_value = value
        self.last_compute_date = fields.Datetime.now()
        
        return value
    
    def _compute_account_sum(self, move_lines):
        """Calcula la suma de movimientos contables"""
        if not move_lines:
            return 0.0
        
        # Filtrar por cuentas específicas si están configuradas
        if self.account_ids:
            move_lines = move_lines.filtered(lambda l: l.account_id in self.account_ids)
        
        # Filtrar por etiquetas si están configuradas
        if self.account_tag_ids:
            move_lines = move_lines.filtered(
                lambda l: any(tag in l.account_id.tag_ids for tag in self.account_tag_ids)
            )
        
        # Calcular según el tipo de balance
        if self.balance_type == 'debit':
            return sum(move_lines.mapped('debit'))
        elif self.balance_type == 'credit':
            return sum(move_lines.mapped('credit'))
        else:
            return sum(move_lines.mapped('balance'))
    
    def _compute_accounting_balance(self, move_lines):
        """Calcula el balance contable"""
        if not self.account_ids:
            return 0.0
        
        domain = [
            ('account_id', 'in', self.account_ids.ids),
            ('date', '>=', self.header_id.date_from),
            ('date', '<=', self.header_id.date_to),
            ('company_id', '=', self.header_id.company_id.id),
            ('parent_state', '=', 'posted')
        ]
        
        if self.excluded_journal_ids:
            domain.append(('journal_id', 'not in', self.excluded_journal_ids.ids))
        
        lines = self.env['account.move.line'].search(domain)
        
        return self._compute_account_sum(lines)
    
    def _compute_salary_rules_sum(self):
        """Calcula la suma de reglas salariales"""
        if not self.salary_rule_ids:
            return 0.0
        
        # Buscar líneas de nómina para el período
        domain = [
            ('salary_rule_id', 'in', self.salary_rule_ids.ids),
            ('slip_id.date_from', '>=', self.header_id.date_from),
            ('slip_id.date_to', '<=', self.header_id.date_to),
            ('slip_id.company_id', '=', self.header_id.company_id.id),
            ('slip_id.state', '=', 'done')
        ]
        
        payslip_lines = self.env['hr.payslip.line'].search(domain)
        return sum(payslip_lines.mapped('total'))
    
    def _compute_sequence_sum(self):
        """Calcula la suma de otras secuencias"""
        if not self.sequence_list_sum:
            return 0.0
        
        sequences = [int(s.strip()) for s in self.sequence_list_sum.split(',') if s.strip().isdigit()]
        
        lines = self.header_id.line_ids.filtered(lambda l: l.sequence in sequences)
        
        total = 0.0
        for line in lines:
            if line.computed_value:
                total += line.computed_value
            else:
                total += line.compute_value()
        
        return total
    
    def _compute_tax_value(self, move_lines):
        """Calcula valores relacionados con impuestos"""
        if not self.tax_group_id:
            return 0.0
        
        # Buscar líneas de impuestos
        tax_lines = move_lines.filtered(
            lambda l: l.tax_group_id == self.tax_group_id
        )
        
        return abs(sum(tax_lines.mapped('balance')))
    
    def _compute_date_value(self):
        """Retorna fechas formateadas como string"""
        if self.calculation == 'date_issue':
            return self.header_id.issue_date.strftime('%Y-%m-%d') if self.header_id.issue_date else ''
        elif self.calculation == 'start_date_year':
            return self.header_id.date_from.strftime('%Y-%m-%d') if self.header_id.date_from else ''
        elif self.calculation == 'end_date_year':
            return self.header_id.date_to.strftime('%Y-%m-%d') if self.header_id.date_to else ''
        return ''
    
    def _compute_info_value(self):
        """Obtiene valores de información de campos relacionados"""
        if not self.information_fields_id or not self.type_partner:
            return ''
        
        # Implementar lógica para obtener información según el tipo
        # Este método debe personalizarse según las necesidades específicas
        return ''
    
    @api.model
    def create(self, vals):
        """Asigna secuencia automáticamente si no se proporciona"""
        if 'sequence' not in vals and 'header_id' in vals:
            header = self.env['hr.certificate.income.header'].browse(vals['header_id'])
            max_sequence = header.line_ids.mapped('sequence')
            vals['sequence'] = max(max_sequence) + 10 if max_sequence else 10
        
        return super().create(vals)


class AccountAccountType(models.Model):
    _name = 'account.account.type'
    _description = 'Account Type Compatibility'
    _order = 'sequence, name'
    _rec_name = 'name'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
