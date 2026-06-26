# -*- coding: utf-8 -*-
{
    'name': "lavish_hr_payroll",

    'summary': """
        Módulo de nómina para la localización colombiana | Liquidación de Nómina""",

    'description': """
        Módulo de nómina para la localización colombiana | Liquidación de Nómina
    """,

    'author': "Lavish S.A.S",

    'category': 'Human Resources',
    "version": "19.0.1.0.81",
    'license': 'OPL-1',
    'external_dependencies': {
        'python': ['dateutil', 'lxml', 'markupsafe', 'numpy', 'pandas', 'PyPDF2', 'pytz', 'reportlab', 'xlsxwriter'],
    },
    'depends': [
        'base',
        'hr',
        'hr_payroll',
        'hr_expense',
        'hr_holidays',
        'hr_attendance',
        'lavish_hr_work_entry_gantt',
        'account',
        'web',
        'lavish_erp',
        'lavish_hr_employee',
        'lavish_hr_social_security',
    ],

    # always loaded
   'data': [
        'data/mail_template_vacation.xml',
        'data/mail_template_payslip_smart.xml',
        'data/hr.leave.diagnostic.csv',
        'data/hr_payroll_novedades_tour.xml',
        'data/sequences.xml',
        'data/xml_generator_data.xml',
        #'data/rtf_ordinario.xml',
        #'data/rule.xml',
        #'data/rule_input.xml',
        'security/ir.model.access.csv',
        'views/res_config_settings_views.xml',

        # Menus raiz (contenedores sin acciones - DEBE ir primero)
        'views/menus_root.xml',

        # Dashboard
        'views/hr_payroll_dashboard_views.xml',
        'wizard/hr_dashboard_copy_wizard_views.xml',

        'views/hr_period_views.xml',
        'views/hr_loan_installment_views.xml',
        'views/wizard_loan_special_payment_views.xml',
        'views/actions_loans.xml',
        'views/actions_payslip.xml',
        'wizard/hr_payslip_employees_views.xml',
        'views/hr_payslip_run_full_form.xml',
        'wizard/hr_vacation_interruption_wizard_views.xml',  # Debe cargar antes de actions_leave.xml
        'views/actions_leave.xml',
        'views/hr_leave_line_views.xml',
        'views/hr_payslip_worked_days_views.xml',
        'views/actions_overtime.xml',
        'views/actions_payroll_flat_file.xml',
        'views/actions_payroll_flat_file_backup.xml',
        'views/actions_hr_payroll_posting.xml',
        'views/actions_payroll_report_lavish.xml',
        'views/actions_payroll_vacation.xml',
        'views/actions_voucher_sending.xml',
        'views/actions_novelties_different_concepts.xml',
        'views/actions_hr_novelties_independents.xml',
        'views/actions_hr_accumulated_payroll.xml',
        'views/hr_payslip_line_views.xml',
        'views/actions_hr_history_cesantias.xml',
        'views/actions_hr_history_prima.xml',
        'views/actions_hr_work_entry.xml',
        'views/actions_accumulated_reports.xml',
        'views/actions_hr_absence_history.xml',
        'views/actions_hr_consolidated_reports.xml',
        'views/actions_payslip_reports_template.xml',
        'views/actions_hr_transfers_of_entities.xml',
        'views/actions_hr_withholding_and_income_certificate.xml',
        'views/actions_payroll_detail_report.xml',
        'views/actions_hr_auditing_reports.xml',

        # Wizards
        'wizard/hr_ibc_audit_wizard_views.xml',
        # 'wizard/hr_payslip_employees_test_views.xml',  # Test - deshabilitado

        # Reports
        'report/reports_payslip_header_footer_template.xml',
        'report/report_payslip.xml',
        'report/report_payslip_hide_fields.xml',
        'report/report_payslip_vacations_templates.xml',
        'report/report_payslip_contrato_templates.xml',
        'report/reports_payslip_header_footer.xml',
        'report/report_payslip_cesantias_prima_templates.xml',
        'report/report_book_vacation.xml',
        'report/report_book_vacation_template.xml',
        'report/report_book_cesantias.xml',
        'report/report_book_cesantias_template.xml',
        'report/hr_report_absenteeism_history.xml',
        'report/hr_report_absenteeism_history_template.xml',
        'report/hr_report_income_and_withholdings.xml',
        'report/hr_report_income_and_withholdings_template.xml',
        'report/report_payroll_lavish.xml',
        'report/report_payslip_lines_grid.xml',
        'report/report_vacation_certificate.xml',
        'report/report_leave_certificate.xml',

        # Actions finales y menus
        'views/actions_report_2276.xml',
        'views/actions_vacation_book_reports.xml',
        'views/actions_account_journal.xml',
        'views/actions_res_partner.xml',
        'views/actions_hr_absenteeism_history.xml',
        'views/hr_payroll_epp_views.xml',
        'views/hr_vacation_interruption_reason_views.xml',
        'views/hr_vacation_unused_line_views.xml',
        "views/hr_employee_public_views.xml",

        # Secciones de Estructura Salarial
        'views/hr_payroll_structure_section_views.xml',

        # Aumento Salarial Masivo
        'data/mail_template_salary_increase.xml',
        'views/hr_salary_increase_views.xml',

        # Componentes Genéricos - Vistas de ejemplo
        'views/actions_rules_ibd_viewer.xml',

        # Visor de Lineas de Nomina
        'views/hr_payslip_line_viewer_views.xml',

        # Vista de Liquidacion de Contrato
        'views/hr_payslip_liquidation_views.xml',

        # Menus con acciones (DEBE ir al final despues de todas las acciones)
        'views/menus.xml',
    ],

    'assets': {
        'web.assets_backend': [
            # === CONSTANTES Y SERVICIOS COMPARTIDOS ===
            'lavish_hr_payroll/static/src/constants/payroll_states.js',
            'lavish_hr_payroll/static/src/constants/payroll_categories.js',
            'lavish_hr_payroll/static/src/constants/payroll_icons.js',
            'lavish_hr_payroll/static/src/constants/generic_config.js',
            'lavish_hr_payroll/static/src/services/payroll_format_service.js',
            'lavish_hr_payroll/static/src/services/generic_data_service.js',

            # === ESTILOS COMPARTIDOS ===
           # 'lavish_hr_payroll/static/src/scss/components/_payslip_badges.scss',
           # 'lavish_hr_payroll/static/src/scss/components/_contract_kanban.scss',

            # === COMPONENTES COMPARTIDOS ===
            'lavish_hr_payroll/static/src/components/shared/payslip_line_row/payslip_line_row.js',
            'lavish_hr_payroll/static/src/components/shared/payslip_line_row/payslip_line_row.xml',
            'lavish_hr_payroll/static/src/components/shared/dashboard_card/dashboard_card.js',
            'lavish_hr_payroll/static/src/components/shared/dashboard_card/dashboard_card.xml',

            # === COMPONENTES GENÉRICOS ===
            # GenericKPI
            'lavish_hr_payroll/static/src/components/generic/kpi/generic_kpi.scss',
            'lavish_hr_payroll/static/src/components/generic/kpi/generic_kpi.js',
            'lavish_hr_payroll/static/src/components/generic/kpi/generic_kpi.xml',

            # GenericHierarchicalTable
            'lavish_hr_payroll/static/src/components/generic/hierarchical_table/hierarchical_table.scss',
            'lavish_hr_payroll/static/src/components/generic/hierarchical_table/hierarchical_table.js',
            'lavish_hr_payroll/static/src/components/generic/hierarchical_table/hierarchical_table.xml',

            # Ejemplos de uso de componentes genéricos
            'lavish_hr_payroll/static/src/components/examples/rules_ibd_viewer.js',
            'lavish_hr_payroll/static/src/components/examples/rules_ibd_viewer.xml',

            # Lottie - Iconos animados (LOCAL - sin CDN)
            'lavish_hr_payroll/static/src/lib/lottie/lottie.min.js',
            'lavish_hr_payroll/static/src/lib/lottie/lordicon_compat.js',
            'lavish_hr_payroll/static/src/lib/lottie/lottie_icon.js',

            # Dashboard Styles
            'lavish_hr_payroll/static/src/components/dashboard/dashboard.scss',

            # Section Kanban Styles
            'lavish_hr_payroll/static/src/scss/payroll_section_kanban.scss',

            # Dashboard JavaScript Components
            'lavish_hr_payroll/static/src/components/dashboard/dashboard.js',
            'lavish_hr_payroll/static/src/components/dashboard/kpi_card/kpi_card.js',
            'lavish_hr_payroll/static/src/components/dashboard/social_security_chart/social_security_chart.js',
            'lavish_hr_payroll/static/src/components/dashboard/batch_list/batch_list.js',
            'lavish_hr_payroll/static/src/components/dashboard/payslip_list/payslip_list.js',
            'lavish_hr_payroll/static/src/components/dashboard/generate_batch_modal/generate_batch_modal.js',
            'lavish_hr_payroll/static/src/components/dashboard/income_deductions_chart/income_deductions_chart.js',
            'lavish_hr_payroll/static/src/components/dashboard/disability_chart/disability_chart.js',
            'lavish_hr_payroll/static/src/components/dashboard/overtime_department_chart/overtime_department_chart.js',
            'lavish_hr_payroll/static/src/components/dashboard/absences_by_type_chart/absences_by_type_chart.js',
            'lavish_hr_payroll/static/src/components/dashboard/accidents_trend_chart/accidents_trend_chart.js',
            'lavish_hr_payroll/static/src/components/dashboard/city_map_card/city_map_card.js',
            'lavish_hr_payroll/static/src/components/dashboard/summary_hero/summary_hero.js',
            'lavish_hr_payroll/static/src/components/dashboard/alerts_breakdown_chart/alerts_breakdown_chart.js',
            'lavish_hr_payroll/static/src/components/dashboard/alerts_detail_card/alerts_detail_card.js',
            'lavish_hr_payroll/static/src/components/dashboard/expiring_contracts_card/expiring_contracts_card.js',
            'lavish_hr_payroll/static/src/components/dashboard/payment_schedule_card/payment_schedule_card.js',
            'lavish_hr_payroll/static/src/components/dashboard/new_employees_card/new_employees_card.js',
            'lavish_hr_payroll/static/src/components/dashboard/pending_leaves_card/pending_leaves_card.js',
            'lavish_hr_payroll/static/src/components/dashboard/payroll_summary_card/payroll_summary_card.js',

            # Dashboard XML Templates
            'lavish_hr_payroll/static/src/components/dashboard/dashboard.xml',
            'lavish_hr_payroll/static/src/components/dashboard/kpi_card/kpi_card.xml',
            'lavish_hr_payroll/static/src/components/dashboard/social_security_chart/social_security_chart.xml',
            'lavish_hr_payroll/static/src/components/dashboard/batch_list/batch_list.xml',
            'lavish_hr_payroll/static/src/components/dashboard/payslip_list/payslip_list.xml',
            'lavish_hr_payroll/static/src/components/dashboard/generate_batch_modal/generate_batch_modal.xml',
            'lavish_hr_payroll/static/src/components/dashboard/income_deductions_chart/income_deductions_chart.xml',
            'lavish_hr_payroll/static/src/components/dashboard/disability_chart/disability_chart.xml',
            'lavish_hr_payroll/static/src/components/dashboard/overtime_department_chart/overtime_department_chart.xml',
            'lavish_hr_payroll/static/src/components/dashboard/absences_by_type_chart/absences_by_type_chart.xml',
            'lavish_hr_payroll/static/src/components/dashboard/accidents_trend_chart/accidents_trend_chart.xml',
            'lavish_hr_payroll/static/src/components/dashboard/city_map_card/city_map_card.xml',
            'lavish_hr_payroll/static/src/components/dashboard/summary_hero/summary_hero.xml',
            'lavish_hr_payroll/static/src/components/dashboard/alerts_breakdown_chart/alerts_breakdown_chart.xml',
            'lavish_hr_payroll/static/src/components/dashboard/alerts_detail_card/alerts_detail_card.xml',
            'lavish_hr_payroll/static/src/components/dashboard/expiring_contracts_card/expiring_contracts_card.xml',
            'lavish_hr_payroll/static/src/components/dashboard/payment_schedule_card/payment_schedule_card.xml',
            'lavish_hr_payroll/static/src/components/dashboard/new_employees_card/new_employees_card.xml',
            'lavish_hr_payroll/static/src/components/dashboard/pending_leaves_card/pending_leaves_card.xml',
            'lavish_hr_payroll/static/src/components/dashboard/payroll_summary_card/payroll_summary_card.xml',

            # Payslip Line Detail Widget - Helpers (deben cargarse antes del componente principal)
            # Configuraciones y utilidades
            'lavish_hr_payroll/static/src/components/payslip_line_detail/helpers/config.js',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/helpers/formatters.js',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/helpers/legal_urls.js',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/helpers/index.js',
            # Data Processors
            'lavish_hr_payroll/static/src/components/payslip_line_detail/helpers/data_processors/contextual.js',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/helpers/data_processors/simple.js',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/helpers/data_processors/social_security.js',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/helpers/data_processors/index.js',
            # Computation Parsers
            'lavish_hr_payroll/static/src/components/payslip_line_detail/helpers/computation/provision_parser.js',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/helpers/computation/multi_paso_parser.js',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/helpers/computation/formula_parser.js',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/helpers/computation/index.js',
            # Steps Helpers
            'lavish_hr_payroll/static/src/components/payslip_line_detail/helpers/steps/step_manager.js',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/helpers/steps/navigation.js',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/helpers/steps/index.js',
            # Sub-componentes (deben cargarse antes del componente principal)
            'lavish_hr_payroll/static/src/components/payslip_line_detail/components/header/PayslipLineHeader.js',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/components/header/PayslipLineHeader.xml',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/components/contextual/PayslipLineContextual.js',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/components/contextual/PayslipLineContextual.xml',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/components/simple/PayslipLineSimple.js',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/components/simple/PayslipLineSimple.xml',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/components/provision/PayslipLineProvision.js',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/components/provision/PayslipLineProvision.xml',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/components/social_security/PayslipLineSocialSecurity.js',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/components/social_security/PayslipLineSocialSecurity.xml',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/components/prestacion/PayslipLinePrestacion.js',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/components/prestacion/PayslipLinePrestacion.xml',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/components/multi_paso/PayslipLineMultiPaso.js',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/components/multi_paso/PayslipLineMultiPaso.xml',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/components/formula/PayslipLineFormula.js',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/components/formula/PayslipLineFormula.xml',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/components/index.js',
            # Componente principal (debe cargarse al final)
            'lavish_hr_payroll/static/src/components/payslip_line_detail/payslip_line_detail.scss',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/payslip_line_detail.js',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/payslip_line_detail.xml',

            # Payslip Run Summary Widget
            'lavish_hr_payroll/static/src/components/payslip_run_summary/payslip_run_summary.js',
            'lavish_hr_payroll/static/src/components/payslip_run_summary/payslip_run_summary.xml',

            # Payslip Line Grid - Vista interactiva de lineas
            'lavish_hr_payroll/static/src/components/payslip_line_grid/payslip_line_grid.scss',
            'lavish_hr_payroll/static/src/components/payslip_line_grid/payslip_line_grid.js',
            'lavish_hr_payroll/static/src/components/payslip_line_grid/payslip_line_grid.xml',

            # Payslip Liquidation Summary Widget
            'lavish_hr_payroll/static/src/components/payslip_liquidation_summary/payslip_liquidation_summary.scss',
            'lavish_hr_payroll/static/src/components/payslip_liquidation_summary/payslip_liquidation_summary.js',
            'lavish_hr_payroll/static/src/components/payslip_liquidation_summary/payslip_liquidation_summary.xml',

            # Payslip Line Detail - Componentes adicionales
            'lavish_hr_payroll/static/src/components/payslip_line_detail/components/retencion/*.js',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/components/retencion/*.xml',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/components/auxilio/*.js',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/components/auxilio/*.xml',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/components/ibd/*.js',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/components/ibd/*.xml',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/components/ssocial/*.js',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/components/ssocial/*.xml',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/components/basic/*.js',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/components/basic/*.xml',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/components/horas_extras/*.js',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/components/horas_extras/*.xml',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/components/indemnizacion/*.js',
            'lavish_hr_payroll/static/src/components/payslip_line_detail/components/indemnizacion/*.xml',
            'lavish_hr_payroll/static/src/css/payslip_detail_compact.css',
            'lavish_hr_payroll/static/src/css/detalle_nomina.css',
            'lavish_hr_payroll/static/src/css/payslip_list_layout.css',
            'lavish_hr_payroll/static/src/components/payslip_run_summary/payslip_run_summary.css',
        ],
        'web.assets_tests': [
            'lavish_hr_payroll/static/tests/tours/payroll_novedades_ausencias_tour.js',
        ],
    },

    'pre_init_hook': 'pre_init_hook',

}

