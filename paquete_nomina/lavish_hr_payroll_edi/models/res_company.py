# -*- coding: utf-8 -*-
"""
Configuración de empresa para nómina electrónica DIAN.
"""
import base64
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = 'res.company'

    # ================================================================
    # CONFIGURACIÓN NÓMINA ELECTRÓNICA
    # ================================================================

    # Ambiente
    production_payroll = fields.Boolean(
        string='Ambiente Producción',
        default=False,
        help='Activa el ambiente de producción para nómina electrónica DIAN'
    )
    password_environment_payroll = fields.Char(
        string='Password Ambiente',
        help='Password para autenticación en servicios DIAN'
    )

    # Software
    software_identification_code_payroll = fields.Char(
        string='Software ID',
        help='Código de identificación del software registrado en DIAN'
    )
    software_pin_payroll = fields.Char(
        string='PIN Software',
        help='PIN del software de nómina electrónica'
    )
    seed_code_payroll = fields.Char(
        string='Seed Code',
        help='Código semilla para generación de documentos'
    )

    # Certificados
    certificate_file_payroll = fields.Binary(
        string='Certificado Digital (.p12)',
        help='Archivo del certificado digital PKCS12'
    )
    certificate_key_payroll = fields.Char(
        string='Clave Certificado',
        help='Contraseña del certificado digital'
    )
    digital_certificate_payroll = fields.Text(
        string='Certificado Público (Base64)',
        help='Certificado digital público en formato Base64'
    )
    serial_number_payroll = fields.Char(
        string='Número Serial Certificado',
        help='Número serial del certificado digital'
    )
    pem_file_payroll = fields.Binary(
        string='Archivo PEM',
        help='Certificado en formato PEM'
    )
    certificate_expiry_payroll = fields.Date(
        string='Vencimiento Certificado',
        help='Fecha de vencimiento del certificado digital'
    )
    certificate_issuer_payroll = fields.Char(
        string='Emisor Certificado',
        help='Entidad emisora del certificado digital'
    )

    # Repositorio
    document_repository_payroll = fields.Char(
        string='Repositorio Documentos',
        default='/tmp/nomina_electronica',
        help='Ruta donde se almacenan los archivos XML y ZIP generados'
    )

    # Set de pruebas
    identificador_set_pruebas_payroll = fields.Char(
        string='ID Set Pruebas',
        help='Identificador del set de pruebas para ambiente de habilitación'
    )

    # Secuencias
    sequence_payroll_id = fields.Many2one(
        'ir.sequence',
        string='Secuencia Nómina Electrónica',
        help='Secuencia para numeración de documentos de nómina electrónica'
    )
    sequence_payroll_note_id = fields.Many2one(
        'ir.sequence',
        string='Secuencia Nota Ajuste',
        help='Secuencia para notas de ajuste de nómina electrónica'
    )

    # ================================================================
    # ACCIONES CERTIFICADO
    # ================================================================

    def action_extract_certificate_payroll(self):
        """Extrae serial, certificado público y PEM desde el archivo P12."""
        self.ensure_one()

        if not self.certificate_file_payroll:
            raise UserError(_('Debe subir el archivo del certificado digital (.p12).'))
        if not self.certificate_key_payroll:
            raise UserError(_('Debe ingresar la clave del certificado.'))

        try:
            from cryptography.hazmat.primitives.serialization import (
                pkcs12, Encoding, PublicFormat
            )
            from cryptography.hazmat.backends import default_backend

            p12_data = base64.b64decode(self.certificate_file_payroll)
            password = self.certificate_key_payroll.encode('utf-8')

            private_key, cert, additional_certs = pkcs12.load_key_and_certificates(
                p12_data, password, default_backend()
            )

            if not cert:
                raise UserError(_('No se pudo extraer el certificado del archivo P12.'))

            # Serial number
            serial = str(cert.serial_number)

            # Certificado público en Base64 (DER)
            cert_der = cert.public_bytes(Encoding.DER)
            cert_b64 = base64.b64encode(cert_der).decode('utf-8')

            # PEM
            cert_pem = cert.public_bytes(Encoding.PEM)
            pem_b64 = base64.b64encode(cert_pem)

            # Issuer info
            issuer = cert.issuer.rfc4514_string()
            subject = cert.subject.rfc4514_string()

            try:
                valid_from = cert.not_valid_before_utc
                valid_to = cert.not_valid_after_utc
            except AttributeError:
                valid_from = cert.not_valid_before
                valid_to = cert.not_valid_after

            # Convertir fecha de vencimiento a date
            if hasattr(valid_to, 'date'):
                expiry_date = valid_to.date()
            else:
                expiry_date = valid_to

            self.write({
                'serial_number_payroll': serial,
                'digital_certificate_payroll': cert_b64,
                'pem_file_payroll': pem_b64,
                'certificate_expiry_payroll': expiry_date,
                'certificate_issuer_payroll': issuer,
            })

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Certificado extraído'),
                    'message': _(
                        'Serial: %s\n'
                        'Emisor: %s\n'
                        'Sujeto: %s\n'
                        'Válido: %s - %s'
                    ) % (serial, issuer, subject, valid_from, valid_to),
                    'type': 'success',
                    'sticky': True,
                }
            }

        except ImportError:
            raise UserError(_(
                'Falta la librería "cryptography". '
                'Instale con: pip install cryptography'
            ))
        except Exception as e:
            raise UserError(_(
                'Error extrayendo datos del certificado:\n\n%s'
            ) % str(e))

    # ================================================================
    # ASOCIAR REGLAS SALARIALES CON CONCEPTOS DIAN
    # ================================================================

    # Mapeo: código regla salarial -> código regla DIAN devengado
    SALARY_TO_DIAN_ACCRUED = {
        # Básicos
        'BASIC': 'Sueldo',
        'BASIC002': 'Sueldo',
        'BASIC003': 'ApoyoSost',
        'BASIC004': 'Sueldo',
        'BASIC005': 'Sueldo',
        # Horas extras y recargos
        'HEYREC001': 'HED',
        'HEYREC002': 'HEDDF',
        'HEYREC003': 'HEN',
        'HEYREC004': 'HRDDF',
        'HEYREC005': 'HRN',
        'HEYREC006': 'HENDF',
        'HEYREC007': 'HRDDF',
        'HEYREC008': 'HRNDF',
        'HEYREC009': 'HENDF',
        # Devengos salariales
        'BONIF': 'Bonificacion',
        'COMISIONES': 'Comision',
        'AUX128': 'Sueldo',
        'RETRO': 'Reintegro',
        'INTVIV': 'BonificacionNS',
        # Devengos no salariales
        'BONOPRI': 'BonificacionNS',
        'BONNS': 'BonificacionNS',
        'AUX110': 'Alimentacion',
        'AUX111': 'Alimentacion',
        'AUX112': 'BonificacionNS',
        'AUX120': 'BonificacionNS',
        # Auxilios
        'AUX000': 'Transporte',
        'AUX00C': 'Teletrabajo',
        # Vacaciones
        'VACDISFRUTADAS': 'VacacionesComunes',
        'VACANOVE': 'VacacionesComunes',
        'VACATIONS_MONEY': 'VacacionesCompensadas',
        'VACCONTRATO': 'VacacionesCompensadas',
        # Prestaciones
        'PRIMA': 'Primas',
        'CESANTIAS': 'Cesantias',
        'CES_YEAR': 'Cesantias',
        'INTCESANTIAS': 'IntCesantias',
        'INTCES_YEAR': 'IntCesantias',
        # Provisiones de prestaciones
        'PRV_PRIM': 'Primas',
        'PRV_CES': 'Cesantias',
        'PRV_ICES': 'IntCesantias',
        'PRV_VAC': 'VacacionesComunes',
        # Consolidaciones de prestaciones
        'CONS_CES': 'Cesantias',
        'CONS_INT': 'IntCesantias',
        'CONS_VAC': 'VacacionesComunes',
        # Dotación
        'DOTACION': 'Dotacion',
        'DOT': 'Dotacion',
        # Incapacidades
        'INCAPACIDAD001': 'IncapacidadComun',
        'INCAPACIDAD002': 'IncapacidadComun',
        'INCAPACIDAD007': 'IncapacidadComun',
        'EGH': 'IncapacidadComun',
        # Licencias / Ausencias
        'AT': 'IncapacidadLaboral',
        'EP': 'IncapacidadLaboral',
        'MAT': 'LicenciaMP',
        'PAT': 'LicenciaMP',
        'LICENCIA001': 'LicenciaR',
        'LUTO': 'LicenciaR',
        'LICENCIA_NO_REMUNERADA': 'LicenciaNR',
        'SUSP_CONTRATO': 'LicenciaNR',
        # Indemnizaciones
        'INDEM': 'Indemnizacion',
    }

    # Mapeo: código regla salarial -> código regla DIAN deducción (V1.0.6)
    SALARY_TO_DIAN_DEDUCT = {
        # Seguridad social
        'SSOCIAL001': 'Salud',
        'SSOCIAL002': 'FondoPension',
        # SSOCIAL003: Subsistencia se reporta como atributo DeduccionSub del nodo FondoSP,
        # se procesa via FondoSP en el generator. Se mantiene mapping a 'FondoSP'.
        'SSOCIAL003': 'FondoSP',
        'SSOCIAL004': 'FondoSP',
        # Retenciones
        'RT_MET_01': 'RetencionFuente',
        'RET_PRIMA': 'RetencionFuente',
        'RTF_INDEM': 'RetencionFuente',
        # Prestamos / Libranzas
        'P01': 'Deuda',
        'PRESTAMO': 'Deuda',
        'LIBRANZA': 'Libranza',
        # Embargos (DIAN: EmbargoFiscal)
        'EMBARGO001': 'EmbargoFiscal',
        'EMBARGO002': 'EmbargoFiscal',
        'EMBARGO003': 'EmbargoFiscal',
        'EMBARGO004': 'EmbargoFiscal',
        'EMBARGO005': 'EmbargoFiscal',
        'EMBARGO007': 'EmbargoFiscal',
        'EMBARGO009': 'EmbargoFiscal',
        # Salud complementaria (DIAN: PlanComplementarios plural)
        'MEDPRE': 'PlanComplementarios',
        # Voluntarios
        'AFC': 'AFC',
        'AVP': 'PensionVoluntaria',
        # Anticipos
        'ANTICIPO': 'Anticipo',
        # Sanciones
        'SANCION': 'SancionPrivada',
        'HORAS': 'SancionPrivada',
        'INAS_INJU': 'SancionPrivada',
        'INAS_INJU_D': 'SancionPrivada',
        # Otros descuentos
        'PREAVISO': 'OtraDeduccion',
        'VIATICOS': 'OtraDeduccion',
        'ERROR': 'OtraDeduccion',
        'DESCUENTO': 'OtraDeduccion',
        'DEV_AUX000': 'OtraDeduccion',
        'DEV_AUX00C': 'OtraDeduccion',
    }

    def _load_dian_data_from_xml(self, relative_path):
        """Lee un data XML del modulo y devuelve {code: {name, description}}.

        Usado por action_auto_assign_dian_concepts para crear conceptos
        faltantes con el name/description oficiales del data XML, no con
        un placeholder generico.
        """
        import os
        import re
        module_path = os.path.dirname(os.path.dirname(__file__))
        full_path = os.path.join(module_path, relative_path)
        if not os.path.isfile(full_path):
            return {}
        with open(full_path, 'r', encoding='utf-8') as fh:
            content = fh.read()
        # Cada record contiene name y code en cualquier orden
        records = re.findall(
            r'<record\s+id="[^"]+"[^>]*>(.*?)</record>',
            content, flags=re.DOTALL,
        )
        result = {}
        for body in records:
            name_m = re.search(r'<field\s+name="name">([^<]+)</field>', body)
            code_m = re.search(r'<field\s+name="code">([^<]+)</field>', body)
            desc_m = re.search(r'<field\s+name="description">([^<]+)</field>', body)
            if not code_m:
                continue
            result[code_m.group(1).strip()] = {
                'name': name_m.group(1).strip() if name_m else code_m.group(1).strip(),
                'description': desc_m.group(1).strip() if desc_m else '',
            }
        return result

    def action_auto_assign_dian_concepts(self):
        """Asocia automaticamente todas las reglas salariales con conceptos DIAN.

        Si el concepto DIAN destino no existe en la BD (upgrade parcial,
        data no cargado), se crea con name/description del propio data XML
        del modulo.
        """
        self.ensure_one()

        AccruedRule = self.env['hr.accrued.rule']
        DeductRule = self.env['hr.deduct.rule']
        SalaryRule = self.env['hr.salary.rule']

        accrued_by_code = {r.code: r for r in AccruedRule.search([])}
        deduct_by_code = {r.code: r for r in DeductRule.search([])}

        accrued_data = self._load_dian_data_from_xml('data/hr_accrued_rule_data.xml')
        deduct_data = self._load_dian_data_from_xml('data/hr_deduct_rule_data.xml')

        salary_rules = SalaryRule.search([])

        assigned = 0
        skipped = 0
        already = 0
        created = []

        for rule in salary_rules:
            code = rule.code
            if not code:
                continue
            if rule.devengado_rule_id or rule.deduccion_rule_id:
                already += 1
                continue

            if code in self.SALARY_TO_DIAN_ACCRUED:
                dian_code = self.SALARY_TO_DIAN_ACCRUED[code]
                dian_rule = accrued_by_code.get(dian_code)
                if not dian_rule:
                    info = accrued_data.get(dian_code, {})
                    dian_rule = AccruedRule.create({
                        'name': info.get('name') or dian_code,
                        'code': dian_code,
                        'description': info.get('description') or _('[Auto] Concepto DIAN'),
                    })
                    accrued_by_code[dian_code] = dian_rule
                    created.append('devengado:%s (%s)' % (dian_code, dian_rule.name))
                rule.devengado_rule_id = dian_rule.id
                assigned += 1
                continue

            if code in self.SALARY_TO_DIAN_DEDUCT:
                dian_code = self.SALARY_TO_DIAN_DEDUCT[code]
                dian_rule = deduct_by_code.get(dian_code)
                if not dian_rule:
                    info = deduct_data.get(dian_code, {})
                    dian_rule = DeductRule.create({
                        'name': info.get('name') or dian_code,
                        'code': dian_code,
                        'description': info.get('description') or _('[Auto] Concepto DIAN'),
                    })
                    deduct_by_code[dian_code] = dian_rule
                    created.append('deduccion:%s (%s)' % (dian_code, dian_rule.name))
                rule.deduccion_rule_id = dian_rule.id
                assigned += 1
                continue

            skipped += 1

        msg = _(
            'Asociacion completada:\n\n'
            '- Asignadas: %d\n'
            '- Ya tenian asignacion: %d\n'
            '- Sin mapeo DIAN: %d'
        ) % (assigned, already, skipped)
        if created:
            msg += _('\n\nConceptos DIAN creados al vuelo (%d):\n%s') % (len(created), '\n'.join(created))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Asociacion de Conceptos DIAN'),
                'message': msg,
                'type': 'success',
                'sticky': True,
            }
        }

    def action_audit_salary_rules_dian(self):
        """Audita reglas salariales con cuenta contable pero sin concepto DIAN.

        Retorna un aviso con las reglas que tienen salary_rule_accounting
        configurado (debit_account o credit_account) pero no tienen
        devengado_rule_id ni deduccion_rule_id asignado. Estas reglas generan
        movimientos contables pero no se reportan en el XML DIAN.
        """
        SalaryRule = self.env['hr.salary.rule']
        rules_with_accounting = SalaryRule.search([
            ('salary_rule_accounting', '!=', False),
        ])

        sin_concepto = []
        for rule in rules_with_accounting:
            # Tiene al menos una linea con cuenta?
            tiene_cuenta = any(
                a.debit_account or a.credit_account
                for a in rule.salary_rule_accounting
            )
            if not tiene_cuenta:
                continue
            if rule.devengado_rule_id or rule.deduccion_rule_id:
                continue
            sin_concepto.append(rule)

        if not sin_concepto:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Auditoria de reglas DIAN'),
                    'message': _('Todas las reglas con cuenta contable tienen concepto DIAN asignado.'),
                    'type': 'success',
                    'sticky': False,
                }
            }

        # Listar reglas problematicas
        lineas = '\n'.join(
            '- [%s] %s' % (r.code or '?', r.name or '?') for r in sin_concepto[:25]
        )
        extra = ''
        if len(sin_concepto) > 25:
            extra = _('\n... y %d mas') % (len(sin_concepto) - 25)

        msg = _(
            '%(count)d regla(s) tienen cuenta contable pero NO tienen concepto DIAN '
            '(devengado ni deduccion). Estas reglas generan movimiento contable pero '
            'NO se reportan en el XML DIAN:\n\n%(lineas)s%(extra)s'
        ) % {
            'count': len(sin_concepto),
            'lineas': lineas,
            'extra': extra,
        }

        return {
            'type': 'ir.actions.act_window',
            'name': _('Reglas con cuenta contable sin concepto DIAN'),
            'res_model': 'hr.salary.rule',
            'view_mode': 'list,form',
            'domain': [('id', 'in', [r.id for r in sin_concepto])],
            'context': {'create': False},
        }
