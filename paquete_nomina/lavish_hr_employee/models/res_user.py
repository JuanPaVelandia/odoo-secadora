from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

# Se hereda res.users debido a un error al seleccionar un usuario como gerente en el que en realidad no deberia
# haber error pero lo hay. El cambio esta hecho entre la línea 39 y 44
class ResUser(models.Model):
    _inherit = "res.users"

    @api.constrains('groups_id')
    def _check_one_user_type(self):
        """We check that no users are both portal and users (same with public).
           This could typically happen because of implied groups.
        """
        user_types_category = self.env.ref('base.module_category_user_type', raise_if_not_found=False)
        user_types_groups = self.env['res.groups'].search(
            [('category_id', '=', user_types_category.id)]) if user_types_category else False
        if user_types_groups:  # needed at install
            if self._has_multiple_groups(user_types_groups.ids):
                raise ValidationError(_('The user cannot have more than one user types.'))

    def _has_multiple_groups(self, group_ids):
        """The method is not fast if the list of ids is very long;
           so we rather check all users than limit to the size of the group
        :param group_ids: list of group ids
        :return: boolean: is there at least a user in at least 2 of the provided groups
        """
        if group_ids:
            args = [tuple(group_ids)]
            if len(self.ids) == 1:
                where_clause = "AND r.uid = %s"
                args.append(self.id)
            else:
                where_clause = ""  # default; we check ALL users (actually pretty efficient)
            query = """
                    SELECT 1 FROM res_groups_users_rel WHERE EXISTS(
                        SELECT r.uid
                        FROM res_groups_users_rel r
                        WHERE r.gid IN %s""" + where_clause + """
                        GROUP BY r.uid HAVING COUNT(r.gid) > 1
                    )
            """
            result = self.env.cr.execute(query, args)
            if not result:
                return False
            else:
                return True
            #return bool(self.env.cr.fetchall())
        else:
            return False

class ResCompany(models.Model):
    _inherit = 'res.company'

    # Campo comentado - 'documents.tag' es del módulo Enterprise 'documents'
    # validated_certificate = fields.Many2one('documents.tag', string='Certificado validado')
    validated_certificate = fields.Char(string='Certificado validado', help='ID del tag de documentos si está instalado el módulo documents')
    simple_provisions = fields.Boolean('Calculo de provisiones simple',
                                       help="Permite calcular las provisiones basados en el metodo de porcentaje y no "
                                            "en consolidacion")
    aux_apr_prod = fields.Boolean('Auxilio de transporte a aprendices en etapa productiva')
    fragment_vac = fields.Boolean('Vacaciones fragmentadas')
    prv_vac_cpt = fields.Boolean('Provision de vacaciones por conceptos')
    init_vac_date = fields.Date('Fecha de corte libro de vacaciones')
    aus_prev = fields.Boolean('Pago de ausencias de periodos anteriores')
    prst_wo_susp = fields.Boolean('No descontar suspensiones de prima')

    # Campos de Seguridad Social (antes en lavish_hr_social_security)
    exonerated_law_1607 = fields.Boolean(
        string='Exonerado Ley 1607',
        help='Exoneración de aportes parafiscales SENA, ICBF y Salud empresa para empleados con salario < 10 SMMLV'
    )
    entity_arp_id = fields.Many2one(
        'hr.employee.entities',
        string='Entidad ARL',
        help='Administradora de Riesgos Laborales de la empresa'
    )
    type_contributor = fields.Selection([
        ('01', 'Empleador'),
        ('02', 'Independiente'),
        ('03', 'Entidades o universidades públicas con régimen especial en Salud'),
        ('04', 'Agremiación o Asociación'),
        ('05', 'Cooperativa o Precooperativa de trabajo asociado'),
        ('06', 'Misión Diplomática'),
        ('07', 'Organización administradora de programa de hogares de bienestar'),
        ('08', 'Pagador de aportes de los concejales, municipales o distritales'),
        ('09', 'Pagador de aportes contrato sindical'),
        ('10', 'Pagador programa de reincorporación'),
        ('11', 'Pagador aportes parafiscales del Magisterio'),
    ], string='Tipo de Aportante', default='01')
    include_absences_1393 = fields.Boolean(
        string='Incluir Ausencias en Ley 1393',
        default=False,
        help='Si está activo, las ausencias (vacaciones, incapacidades) participan en el cálculo del límite 40% de Ley 1393. '
             'Si está desactivado (recomendado), las ausencias se suman directamente al IBC sin participar en el límite 40%.'
    )

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    validated_certificate = fields.Char(related='company_id.validated_certificate',string='Certificado validado', readonly=False)
    simple_provisions = fields.Boolean(related='company_id.simple_provisions', string='Calculo de provisiones simple',
                                       help="Permite calcular las provisiones basados en el metodo de porcentaje y no "
                                            "en consolidacion", readonly=False)
    aux_apr_prod = fields.Boolean(related='company_id.aux_apr_prod', string='Auxilio de transporte a aprendices en etapa productiva', readonly=False)
    fragment_vac = fields.Boolean(related='company_id.fragment_vac', string='Vacaciones fragmentadas', readonly=False)
    prv_vac_cpt = fields.Boolean(related='company_id.prv_vac_cpt', string='Provision de vacaciones por conceptos', readonly=False)
    init_vac_date = fields.Date(related='company_id.init_vac_date', string='Fecha de corte libro de vacaciones', readonly=False)
    aus_prev = fields.Boolean(related='company_id.aus_prev', string='Pago de ausencias de periodos anteriores', readonly=False)
    prst_wo_susp = fields.Boolean(related='company_id.prst_wo_susp',string='No descontar suspensiones de prima', readonly=False)
