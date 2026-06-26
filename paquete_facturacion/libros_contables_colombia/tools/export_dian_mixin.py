# -*- coding: utf-8 -*-
"""Mixin para exportacion a formatos DIAN Colombia."""

from odoo import models
from datetime import datetime, date
import io


class ExportDIANMixin(models.AbstractModel):
    """Mixin para formatos especificos DIAN Colombia."""

    _name = 'export.dian.mixin'
    _description = 'Mixin de Exportacion DIAN Colombia'

    DIAN_FORMATS = {
        '300': {
            'name': 'Formulario 300 - IVA',
            'version': '10.0',
            'root_element': 'DocumentoXML',
        },
        '350': {
            'name': 'Formulario 350 - Retencion en la Fuente',
            'version': '10.0',
            'root_element': 'DocumentoXML',
        },
        '1001': {
            'name': 'Formato 1001 - Pagos o Abonos',
            'version': '10.0',
            'root_element': 'mas',
        },
        '1003': {
            'name': 'Formato 1003 - Retenciones Practicadas',
            'version': '10.0',
            'root_element': 'mas',
        },
        '1005': {
            'name': 'Formato 1005 - IVA Descontable',
            'version': '10.0',
            'root_element': 'mas',
        },
        '1006': {
            'name': 'Formato 1006 - IVA Generado',
            'version': '10.0',
            'root_element': 'mas',
        },
        '1007': {
            'name': 'Formato 1007 - Ingresos',
            'version': '10.0',
            'root_element': 'mas',
        },
        '1008': {
            'name': 'Formato 1008 - Saldo Cuentas por Cobrar',
            'version': '10.0',
            'root_element': 'mas',
        },
        '1009': {
            'name': 'Formato 1009 - Saldo Cuentas por Pagar',
            'version': '10.0',
            'root_element': 'mas',
        },
        '1012': {
            'name': 'Formato 1012 - Declaraciones Tributarias',
            'version': '10.0',
            'root_element': 'mas',
        },
        'ica': {
            'name': 'ICA - Industria y Comercio',
            'version': '1.0',
            'root_element': 'DeclaracionICA',
        },
    }

    CONCEPTO_RETENCION = {
        'salarios': '5001',
        'honorarios': '5002',
        'comisiones': '5003',
        'servicios': '5004',
        'arrendamientos': '5005',
        'compras': '5006',
        'otros': '5099',
    }

    TIPO_DOCUMENTO = {
        'cc': '13',
        'ce': '22',
        'nit': '31',
        'pasaporte': '41',
        'pep': '47',
    }

    def _get_company_vat(self):
        """Obtiene NIT de la compania sin DV."""
        vat = self.env.company.vat or ''
        if '-' in vat:
            return vat.split('-')[0]
        return vat.replace('.', '').strip()

    def _get_company_dv(self):
        """Obtiene digito de verificacion."""
        vat = self.env.company.vat or ''
        if '-' in vat:
            return vat.split('-')[1]
        return self._calculate_dv(self._get_company_vat())

    def _calculate_dv(self, nit):
        """Calcula digito de verificacion DIAN."""
        if not nit:
            return '0'
        try:
            nit = str(nit).replace('.', '').replace('-', '').strip()
            primos = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]
            total = 0
            nit_reversed = nit[::-1]
            for i, digit in enumerate(nit_reversed):
                if i < len(primos):
                    total += int(digit) * primos[i]
            residuo = total % 11
            if residuo == 0:
                return '0'
            elif residuo == 1:
                return '1'
            else:
                return str(11 - residuo)
        except (ValueError, TypeError):
            return '0'

    def _format_money_dian(self, value, decimals=0):
        """Formatea valor monetario para DIAN (sin separadores, sin decimales por defecto)."""
        if value is None:
            return '0'
        try:
            if decimals > 0:
                return str(int(float(value) * (10 ** decimals)))
            return str(int(round(float(value))))
        except (ValueError, TypeError):
            return '0'

    def _format_date_dian(self, value, format_type='YYYYMMDD'):
        """Formatea fecha para DIAN."""
        if not value:
            return ''
        if isinstance(value, str):
            try:
                value = datetime.strptime(value[:10], '%Y-%m-%d')
            except ValueError:
                return ''
        if isinstance(value, datetime):
            value = value.date()

        if format_type == 'YYYYMMDD':
            return value.strftime('%Y%m%d')
        elif format_type == 'YYYY-MM-DD':
            return value.strftime('%Y-%m-%d')
        elif format_type == 'DDMMYYYY':
            return value.strftime('%d%m%Y')
        return value.strftime('%Y%m%d')

    def _escape_xml(self, text):
        """Escapa caracteres XML."""
        if not text:
            return ''
        text = str(text)
        text = text.replace('&', '&amp;')
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')
        text = text.replace('"', '&quot;')
        return text

    def export_formulario_300(self, data, options=None):
        """
        Genera XML Formulario 300 - IVA Bimestral.

        Args:
            data: Dict con casillas del formulario
            options: {year, period, version}

        Returns:
            bytes: XML del formulario
        """
        options = options or {}
        year = options.get('year', datetime.now().year)
        period = options.get('period', 1)

        xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<DocumentoXML xmlns="http://www.dian.gov.co/contratos/facturaelectronica/v1">
    <Encabezado>
        <NumeroFormulario>300</NumeroFormulario>
        <FraccionAnyo>00</FraccionAnyo>
        <AnioGravable>{year}</AnioGravable>
        <Periodo>{str(period).zfill(2)}</Periodo>
        <TipoDocInformante>31</TipoDocInformante>
        <NumeroIdentificacion>{self._get_company_vat()}</NumeroIdentificacion>
        <DV>{self._get_company_dv()}</DV>
        <RazonSocial>{self._escape_xml(self.env.company.name)}</RazonSocial>
    </Encabezado>
    <Cuerpo>
'''
        casillas_300 = [
            ('24', 'ingresos_brutos_operacionales'),
            ('25', 'ingresos_brutos_no_operacionales'),
            ('26', 'ingresos_no_gravados'),
            ('27', 'total_ingresos_brutos'),
            ('28', 'devoluciones_ventas'),
            ('29', 'ingresos_netos'),
            ('30', 'compras_gravadas'),
            ('31', 'compras_no_gravadas'),
            ('32', 'importaciones_gravadas'),
            ('33', 'importaciones_no_gravadas'),
            ('37', 'iva_generado_5'),
            ('38', 'iva_generado_19'),
            ('39', 'total_iva_generado'),
            ('40', 'iva_descontable_compras'),
            ('41', 'iva_descontable_importaciones'),
            ('42', 'total_iva_descontable'),
            ('43', 'saldo_favor_periodo_anterior'),
            ('44', 'retenciones_practicadas'),
            ('45', 'saldo_a_pagar'),
            ('46', 'saldo_a_favor'),
        ]

        for casilla, key in casillas_300:
            value = data.get(key, 0)
            xml += f'        <Casilla{casilla}>{self._format_money_dian(value)}</Casilla{casilla}>\n'

        xml += '''    </Cuerpo>
</DocumentoXML>'''

        return xml.encode('utf-8')

    def export_formulario_350(self, data, options=None):
        """
        Genera XML Formulario 350 - Retencion en la Fuente.

        Args:
            data: Dict con casillas del formulario
            options: {year, period}

        Returns:
            bytes: XML del formulario
        """
        options = options or {}
        year = options.get('year', datetime.now().year)
        period = options.get('period', 1)

        xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<DocumentoXML xmlns="http://www.dian.gov.co/contratos/facturaelectronica/v1">
    <Encabezado>
        <NumeroFormulario>350</NumeroFormulario>
        <AnioGravable>{year}</AnioGravable>
        <Periodo>{str(period).zfill(2)}</Periodo>
        <TipoDocInformante>31</TipoDocInformante>
        <NumeroIdentificacion>{self._get_company_vat()}</NumeroIdentificacion>
        <DV>{self._get_company_dv()}</DV>
        <RazonSocial>{self._escape_xml(self.env.company.name)}</RazonSocial>
    </Encabezado>
    <Cuerpo>
'''
        casillas_350 = [
            ('27', 'pagos_salarios'),
            ('28', 'retencion_salarios'),
            ('29', 'pagos_honorarios'),
            ('30', 'retencion_honorarios'),
            ('31', 'pagos_comisiones'),
            ('32', 'retencion_comisiones'),
            ('33', 'pagos_servicios'),
            ('34', 'retencion_servicios'),
            ('35', 'pagos_arrendamientos'),
            ('36', 'retencion_arrendamientos'),
            ('37', 'pagos_rendimientos'),
            ('38', 'retencion_rendimientos'),
            ('39', 'pagos_compras'),
            ('40', 'retencion_compras'),
            ('41', 'otros_pagos'),
            ('42', 'retencion_otros'),
            ('43', 'total_retenciones'),
        ]

        for casilla, key in casillas_350:
            value = data.get(key, 0)
            xml += f'        <Casilla{casilla}>{self._format_money_dian(value)}</Casilla{casilla}>\n'

        xml += '''    </Cuerpo>
</DocumentoXML>'''

        return xml.encode('utf-8')

    def export_medios_magneticos(self, data, formato, options=None):
        """
        Genera XML para Medios Magneticos DIAN.

        Args:
            data: Lista de registros
            formato: Codigo formato ('1001', '1003', '1005', etc)
            options: {year, version}

        Returns:
            bytes: XML de medios magneticos
        """
        options = options or {}
        year = options.get('year', datetime.now().year)
        version = options.get('version', '10')

        format_info = self.DIAN_FORMATS.get(formato, {})

        xml = f'''<?xml version="1.0" encoding="ISO-8859-1"?>
<mas xmlns="http://www.dian.gov.co/contratos/facturaelectronica/v1">
    <Cab>
        <Ano>{year}</Ano>
        <CodCpt>{formato}</CodCpt>
        <Formato>{formato}</Formato>
        <Version>{version}</Version>
        <NumEnvio>1</NumEnvio>
        <FecEnvio>{self._format_date_dian(datetime.now())}</FecEnvio>
        <FecInicial>{year}0101</FecInicial>
        <FecFinal>{year}1231</FecFinal>
        <ValorTotal>{self._format_money_dian(sum(r.get('valor', 0) for r in data))}</ValorTotal>
        <CantReg>{len(data)}</CantReg>
    </Cab>
'''
        for i, row in enumerate(data, 1):
            xml += self._build_medios_row(row, formato, i)

        xml += '</mas>'
        return xml.encode('iso-8859-1')

    def _build_medios_row(self, row, formato, seq):
        """Construye fila de medios magneticos segun formato."""
        tipo_doc = row.get('tipo_documento', '31')
        nit = row.get('nit', '')
        dv = row.get('dv', self._calculate_dv(nit))
        nombre = self._escape_xml(row.get('nombre', ''))

        if formato == '1001':
            return f'''    <Pai>
        <Sec>{seq}</Sec>
        <Tdoc>{tipo_doc}</Tdoc>
        <Nid>{nit}</Nid>
        <Dv>{dv}</Dv>
        <Ape1>{self._escape_xml(row.get('apellido1', ''))}</Ape1>
        <Ape2>{self._escape_xml(row.get('apellido2', ''))}</Ape2>
        <Nom1>{self._escape_xml(row.get('nombre1', ''))}</Nom1>
        <Nom2>{self._escape_xml(row.get('nombre2', ''))}</Nom2>
        <Rsoc>{nombre}</Rsoc>
        <Dir>{self._escape_xml(row.get('direccion', ''))}</Dir>
        <Dpto>{row.get('departamento', '')}</Dpto>
        <Mun>{row.get('municipio', '')}</Mun>
        <Pais>{row.get('pais', '169')}</Pais>
        <Cpt>{row.get('concepto', '')}</Cpt>
        <Vlr>{self._format_money_dian(row.get('valor', 0))}</Vlr>
        <VlrRet>{self._format_money_dian(row.get('retencion', 0))}</VlrRet>
    </Pai>
'''
        elif formato in ('1003', '1005', '1006'):
            return f'''    <Reg>
        <Sec>{seq}</Sec>
        <Tdoc>{tipo_doc}</Tdoc>
        <Nid>{nit}</Nid>
        <Dv>{dv}</Dv>
        <Rsoc>{nombre}</Rsoc>
        <Cpt>{row.get('concepto', '')}</Cpt>
        <Vlr>{self._format_money_dian(row.get('valor', 0))}</Vlr>
    </Reg>
'''
        elif formato == '1007':
            return f'''    <Ing>
        <Sec>{seq}</Sec>
        <Tdoc>{tipo_doc}</Tdoc>
        <Nid>{nit}</Nid>
        <Dv>{dv}</Dv>
        <Rsoc>{nombre}</Rsoc>
        <Ing>{self._format_money_dian(row.get('ingreso_bruto', 0))}</Ing>
        <Dev>{self._format_money_dian(row.get('devoluciones', 0))}</Dev>
        <IngNeto>{self._format_money_dian(row.get('ingreso_neto', 0))}</IngNeto>
    </Ing>
'''
        elif formato in ('1008', '1009'):
            return f'''    <Sal>
        <Sec>{seq}</Sec>
        <Tdoc>{tipo_doc}</Tdoc>
        <Nid>{nit}</Nid>
        <Dv>{dv}</Dv>
        <Rsoc>{nombre}</Rsoc>
        <SalIni>{self._format_money_dian(row.get('saldo_inicial', 0))}</SalIni>
        <SalFin>{self._format_money_dian(row.get('saldo_final', 0))}</SalFin>
    </Sal>
'''
        else:
            return f'''    <Reg>
        <Sec>{seq}</Sec>
        <Nid>{nit}</Nid>
        <Dv>{dv}</Dv>
        <Rsoc>{nombre}</Rsoc>
        <Vlr>{self._format_money_dian(row.get('valor', 0))}</Vlr>
    </Reg>
'''

    def export_ica(self, data, options=None):
        """
        Genera XML para declaracion ICA.

        Args:
            data: Dict con informacion de ICA
            options: {year, period, municipio}

        Returns:
            bytes: XML de ICA
        """
        options = options or {}
        year = options.get('year', datetime.now().year)
        period = options.get('period', 1)
        municipio = options.get('municipio', 'bogota')

        xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<DeclaracionICA xmlns="http://www.bogota.gov.co/ica/v1">
    <Encabezado>
        <Municipio>{municipio}</Municipio>
        <AnioGravable>{year}</AnioGravable>
        <Periodo>{period}</Periodo>
        <TipoDocumento>31</TipoDocumento>
        <NumeroIdentificacion>{self._get_company_vat()}</NumeroIdentificacion>
        <RazonSocial>{self._escape_xml(self.env.company.name)}</RazonSocial>
    </Encabezado>
    <Cuerpo>
        <IngresosBrutos>{self._format_money_dian(data.get('ingresos_brutos', 0))}</IngresosBrutos>
        <MenosExclusiones>{self._format_money_dian(data.get('exclusiones', 0))}</MenosExclusiones>
        <MenosExenciones>{self._format_money_dian(data.get('exenciones', 0))}</MenosExenciones>
        <MenosDevoluciones>{self._format_money_dian(data.get('devoluciones', 0))}</MenosDevoluciones>
        <BaseGravable>{self._format_money_dian(data.get('base_gravable', 0))}</BaseGravable>
        <Tarifa>{data.get('tarifa', '0')}</Tarifa>
        <ImpuestoICA>{self._format_money_dian(data.get('impuesto_ica', 0))}</ImpuestoICA>
        <Avisos>{self._format_money_dian(data.get('avisos', 0))}</Avisos>
        <TotalImpuesto>{self._format_money_dian(data.get('total_impuesto', 0))}</TotalImpuesto>
        <ReteFuente>{self._format_money_dian(data.get('retefuente', 0))}</ReteFuente>
        <ReteICA>{self._format_money_dian(data.get('reteica', 0))}</ReteICA>
        <SaldoAPagar>{self._format_money_dian(data.get('saldo_pagar', 0))}</SaldoAPagar>
    </Cuerpo>
</DeclaracionICA>'''

        return xml.encode('utf-8')

    def export_exogena(self, data, formato, options=None):
        """
        Exporta informacion exogena (wrapper de medios magneticos).
        """
        return self.export_medios_magneticos(data, formato, options)

    def validate_nit(self, nit):
        """
        Valida formato y digito de verificacion de NIT.

        Args:
            nit: NIT con o sin DV

        Returns:
            dict: {valid, nit, dv, error}
        """
        if not nit:
            return {'valid': False, 'error': 'NIT vacio'}

        nit_clean = str(nit).replace('.', '').replace('-', '').strip()

        if len(nit_clean) > 11:
            return {'valid': False, 'error': 'NIT demasiado largo'}

        if not nit_clean.isdigit():
            return {'valid': False, 'error': 'NIT debe ser numerico'}

        if '-' in str(nit):
            parts = str(nit).split('-')
            nit_base = parts[0].replace('.', '')
            dv_provided = parts[1] if len(parts) > 1 else ''
            dv_calculated = self._calculate_dv(nit_base)
            if dv_provided != dv_calculated:
                return {
                    'valid': False,
                    'nit': nit_base,
                    'dv_provided': dv_provided,
                    'dv_calculated': dv_calculated,
                    'error': f'DV incorrecto: esperado {dv_calculated}'
                }
            return {'valid': True, 'nit': nit_base, 'dv': dv_calculated}

        return {
            'valid': True,
            'nit': nit_clean,
            'dv': self._calculate_dv(nit_clean)
        }

    def get_available_formats(self):
        """Retorna formatos DIAN disponibles."""
        return self.DIAN_FORMATS
