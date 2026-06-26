# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Migración 1.31: Actualizar ir_model_fields con nombres de columna correctos
    para campos Many2many y prevenir eliminación de estructuras de nómina.

    Esta migración NO elimina datos, solo actualiza metadatos para que coincidan
    con la estructura existente de la base de datos.
    """
    _logger.info("Iniciando migración 1.31: Actualización de metadatos Many2many...")

    # Prevenir que Odoo intente eliminar estructuras de nómina que tienen reglas asociadas
    # Marcar como noupdate=True los registros de hr.payroll.structure
    _logger.info("Marcando estructuras de nómina como noupdate=True...")
    cr.execute("""
        UPDATE ir_model_data
        SET noupdate = TRUE
        WHERE model = 'hr.payroll.structure'
        AND module = 'lavish_hr_employee'
    """)
    if cr.rowcount:
        _logger.info(f"  Actualizados {cr.rowcount} registros de hr.payroll.structure a noupdate=True")

    # También marcar las categorías de reglas salariales
    cr.execute("""
        UPDATE ir_model_data
        SET noupdate = TRUE
        WHERE model = 'hr.salary.rule.category'
        AND module = 'lavish_hr_employee'
    """)
    if cr.rowcount:
        _logger.info(f"  Actualizados {cr.rowcount} registros de hr.salary.rule.category a noupdate=True")

    # Marcar las reglas salariales
    cr.execute("""
        UPDATE ir_model_data
        SET noupdate = TRUE
        WHERE model = 'hr.salary.rule'
        AND module = 'lavish_hr_employee'
    """)
    if cr.rowcount:
        _logger.info(f"  Actualizados {cr.rowcount} registros de hr.salary.rule a noupdate=True")

    # Actualizar ir_model_fields con nombres de columna correctos
    field_updates = [
        # EPP
        ('hr.epp.request', 'stock_move_ids', 'hr_epp_request_stock_move_rel', 'request_id', 'move_id'),
        ('wizard.epp.batch.generate', 'department_ids', 'wizard_epp_batch_department_rel', 'wizard_id', 'department_id'),
        ('wizard.epp.batch.generate', 'job_ids', 'wizard_epp_batch_job_rel', 'wizard_id', 'job_id'),
        ('wizard.epp.batch.generate', 'employee_ids', 'wizard_epp_batch_employee_rel', 'wizard_id', 'employee_id'),
        ('wizard.epp.batch.generate', 'employee_preview_ids', 'wizard_epp_batch_preview_rel', 'wizard_id', 'employee_id'),
        ('hr.epp.configuration', 'department_ids', 'hr_department_hr_epp_configuration_rel', 'hr_epp_configuration_id', 'hr_department_id'),
        ('hr.epp.configuration', 'job_ids', 'hr_epp_configuration_hr_job_rel', 'hr_epp_configuration_id', 'hr_job_id'),
        ('hr.epp.configuration', 'supplier_ids', 'hr_epp_configuration_res_partner_rel', 'hr_epp_configuration_id', 'res_partner_id'),

        # Medical
        ('hr.medical.certificate', 'attachment_ids', 'hr_medical_certificate_ir_attachment_rel', 'hr_medical_certificate_id', 'ir_attachment_id'),
        ('hr.medical.certificate', 'service_ids', 'hr_medical_certificate_service_rel', 'certificate_id', 'service_id'),
        ('hr.medical.certificate.result', 'attachment_ids', 'hr_medical_certificate_result_ir_attachment_rel', 'hr_medical_certificate_result_id', 'ir_attachment_id'),
        ('hr.medical.provider', 'service_ids', 'hr_medical_provider_hr_medical_service_rel', 'hr_medical_provider_id', 'hr_medical_service_id'),
        ('hr.medical.template', 'service_ids', 'hr_medical_service_hr_medical_template_rel', 'hr_medical_template_id', 'hr_medical_service_id'),

        # Contract Concepts
        ('hr.contract.concepts', 'payslip_ids', 'hr_contract_concepts_hr_payslip_rel', 'hr_contract_concepts_id', 'hr_payslip_id'),
        ('hr.contract.concepts', 'discount_rule', 'hr_contract_concepts_hr_salary_rule_rel', 'hr_contract_concepts_id', 'hr_salary_rule_id'),
        ('hr.contract.concepts', 'payroll_structure_ids', 'hr_contract_concepts_hr_payroll_structure_rel', 'hr_contract_concepts_id', 'hr_payroll_structure_id'),
        ('hr.contract.concepts', 'discount_categoria', 'hr_contract_concepts_hr_salary_rule_category_rel', 'hr_contract_concepts_id', 'hr_salary_rule_category_id'),

        # Contract Actions
        ('contract.actions', 'department_ids', 'contract_actions_hr_department_rel', 'contract_actions_id', 'hr_department_id'),
        ('contract.actions', 'job_ids', 'contract_actions_hr_job_rel', 'contract_actions_id', 'hr_job_id'),
        ('contract.actions', 'additional_contract_ids', 'contract_actions_additional_rel', 'contract_actions_id', 'hr_contract_id'),
        ('contract.actions', 'additional_employee_ids', 'contract_actions_employee_rel', 'contract_actions_id', 'hr_employee_id'),
        ('contract.actions', 'attachment_ids', 'contract_actions_ir_attachment_rel', 'contract_actions_id', 'ir_attachment_id'),

        # Birthday
        ('hr.birthday.tree', 'company', 'hr_birthday_tree_res_company_rel', 'hr_birthday_tree_id', 'res_company_id'),

        # Wizard Mass EPP Request
        ('wizard.mass.epp.request', 'department_ids', 'wizard_mass_epp_request_hr_department_rel', 'wizard_id', 'hr_department_id'),
        ('wizard.mass.epp.request', 'job_ids', 'wizard_mass_epp_request_hr_job_rel', 'wizard_id', 'hr_job_id'),
        ('wizard.mass.epp.request', 'employee_ids', 'wizard_mass_epp_request_hr_employee_rel', 'wizard_id', 'hr_employee_id'),

        # Parameterization - Employee Entities
        ('hr.employee.entities', 'types_entities', 'hr_employee_entities_hr_contribution_register_rel', 'hr_employee_entities_id', 'hr_contribution_register_id'),
    ]

    for model, field, rel_table, col1, col2 in field_updates:
        cr.execute("""
            UPDATE ir_model_fields
            SET relation_table = %s, column1 = %s, column2 = %s
            WHERE model = %s AND name = %s
        """, (rel_table, col1, col2, model, field))
        if cr.rowcount:
            _logger.info(f"  Actualizado ir_model_fields: {model}.{field}")

    _logger.info("Migración 1.31 completada exitosamente")
