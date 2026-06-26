/** @odoo-module **/

import { registry } from "@web/core/registry";
import { stepUtils } from "@web_tour/tour_service/tour_utils";

function getState() {
    if (!window.__lavish_payroll_test) {
        window.__lavish_payroll_test = {};
    }
    return window.__lavish_payroll_test;
}

function normalize(text) {
    return (text || "")
        .toLowerCase()
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "");
}

function typeInInput(input, value) {
    if (!input) {
        return;
    }
    input.value = value;
    input.dispatchEvent(new Event("input", { bubbles: true }));
}

function setInputValue(input, value) {
    if (!input) {
        return false;
    }
    input.value = value;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
}

function pickAutocomplete(actions, preferred) {
    const items = Array.from(
        document.querySelectorAll(".ui-autocomplete > li > a:not(:has(i.fa))")
    );
    if (!items.length) {
        throw new Error("No autocomplete options found");
    }
    const preferredNorm = normalize(preferred);
    let target = items[0];
    if (preferredNorm) {
        const match = items.find((item) =>
            normalize(item.textContent).includes(preferredNorm)
        );
        if (match) {
            target = match;
        }
    }
    actions.click(target);
    return target.textContent.trim();
}

function formatDate(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
}

function getToday() {
    const state = getState();
    if (!state.today) {
        state.today = formatDate(new Date());
    }
    return state.today;
}

function openMany2oneInput(input, value) {
    const widget = input && input.closest(".o_field_widget");
    const dropdown = widget && widget.querySelector(".o_dropdown_button");
    typeInInput(input, value);
    if (dropdown) {
        dropdown.click();
    }
}

registry.category("web_tour.tours").add("lavish_hr_payroll_novedades_ausencias_tour", {
    url: "/odoo",
    steps: () => [
        stepUtils.showAppsMenuItem(),
        {
            trigger: '.o_app[data-menu-xmlid="hr_work_entry_enterprise.menu_hr_payroll_root"]',
            content: "Open Payroll",
            run: "click",
        },
        {
            trigger: '[data-menu-xmlid="lavish_hr_payroll.menu_novelties_different_concepts"]',
            content: "Open novelties",
            run: "click",
        },
        {
            trigger: ".o_list_button_add",
            content: "Create novelty",
            run: "click",
        },
        {
            trigger: ".o_field_widget[name='employee_id'] input",
            content: "Select employee",
            run: function () {
                const state = getState();
                const searchValue = state.employee || "a";
                openMany2oneInput(this.anchor, searchValue);
            },
        },
        {
            trigger: ".ui-autocomplete > li > a:not(:has(i.fa))",
            run: function (actions) {
                const state = getState();
                state.employee = pickAutocomplete(actions, state.employee);
            },
        },
        {
            trigger: ".o_field_widget[name='salary_rule_id'] input",
            content: "Select commission rule",
            run: function () {
                const state = getState();
                const searchValue = state.ruleQuery || "Comisiones";
                openMany2oneInput(this.anchor, searchValue);
            },
        },
        {
            trigger: ".ui-autocomplete > li > a:not(:has(i.fa))",
            run: function (actions) {
                const state = getState();
                const picked = pickAutocomplete(actions, state.ruleQuery || "comision");
                state.commissionRule = picked;
            },
        },
        {
            trigger: ".o_field_widget[name='date'] input",
            content: "Set novelty date",
            run: function () {
                setInputValue(this.anchor, getToday());
            },
        },
        {
            trigger: ".o_field_widget[name='amount'] input",
            content: "Set novelty amount",
            run: "edit 250000",
        },
        {
            trigger: ".o_field_widget[name='description'] input",
            content: "Set description",
            run: "edit Comisiones de venta",
        },
        {
            trigger: "button.o_form_button_save",
            content: "Save novelty",
            run: "click",
        },
        {
            trigger: ".o_form_view",
            run: function (actions) {
                const button = document.querySelector("button[name='action_submit_approval']");
                if (button) {
                    actions.click(button);
                }
            },
        },
        {
            trigger: ".o_form_view",
            run: function (actions) {
                const button = document.querySelector("button[name='action_approve']");
                if (button) {
                    actions.click(button);
                }
            },
        },
        {
            trigger: '[data-menu-xmlid="lavish_hr_payroll.menu_hr_holidays_leave_extender"]',
            content: "Open absences",
            run: "click",
        },
        {
            trigger: ".o_list_button_add",
            content: "Create absence",
            run: "click",
        },
        {
            trigger: ".o_field_widget[name='employee_id'] input",
            content: "Select same employee",
            run: function () {
                const state = getState();
                const searchValue = state.employee || "a";
                openMany2oneInput(this.anchor, searchValue);
            },
        },
        {
            trigger: ".ui-autocomplete > li > a:not(:has(i.fa))",
            run: function (actions) {
                const state = getState();
                pickAutocomplete(actions, state.employee);
            },
        },
        {
            trigger: ".o_field_widget[name='holiday_status_id'] input",
            content: "Select leave type",
            run: function () {
                const state = getState();
                const searchValue = state.leaveQuery || "Incapacidad";
                openMany2oneInput(this.anchor, searchValue);
            },
        },
        {
            trigger: ".ui-autocomplete > li > a:not(:has(i.fa))",
            run: function (actions) {
                const state = getState();
                const picked = pickAutocomplete(actions, state.leaveQuery || "incapacidad");
                state.leaveType = picked;
            },
        },
        {
            trigger: ".o_form_view",
            content: "Set leave dates",
            run: function () {
                const dateValue = getToday();
                const from =
                    document.querySelector(".o_field_widget[name='request_date_from'] input") ||
                    document.querySelector(".o_field_widget[name='date_from'] input");
                const to =
                    document.querySelector(".o_field_widget[name='request_date_to'] input") ||
                    document.querySelector(".o_field_widget[name='date_to'] input");
                const okFrom = setInputValue(from, dateValue);
                const okTo = setInputValue(to, dateValue);
                if (!okFrom || !okTo) {
                    throw new Error("Leave date inputs not found");
                }
            },
        },
        {
            trigger: "button.o_form_button_save",
            content: "Save absence",
            run: "click",
        },
        {
            trigger: ".o_form_view",
            run: function (actions) {
                const button = document.querySelector("button[name='action_confirm']");
                if (button) {
                    actions.click(button);
                }
            },
        },
        {
            trigger: ".o_form_view",
            run: function (actions) {
                const button =
                    document.querySelector("button[name='action_validate']") ||
                    document.querySelector("button[name='action_approve']");
                if (button) {
                    actions.click(button);
                }
            },
        },
        {
            trigger: '[data-menu-xmlid="hr_payroll.menu_hr_payroll_employee_payslips"]',
            content: "Open payslips",
            run: "click",
        },
        {
            trigger: ".o_list_button_add",
            content: "Create payslip",
            run: "click",
        },
        {
            trigger: ".o_field_widget[name='employee_id'] input",
            content: "Set employee on payslip",
            run: function () {
                const state = getState();
                const searchValue = state.employee || "a";
                openMany2oneInput(this.anchor, searchValue);
            },
        },
        {
            trigger: ".ui-autocomplete > li > a:not(:has(i.fa))",
            run: function (actions) {
                const state = getState();
                pickAutocomplete(actions, state.employee);
            },
        },
        {
            trigger: ".o_form_view",
            content: "Set payslip dates",
            run: function () {
                const dateValue = getToday();
                const from = document.querySelector(".o_field_widget[name='date_from'] input");
                const to = document.querySelector(".o_field_widget[name='date_to'] input");
                const okFrom = setInputValue(from, dateValue);
                const okTo = setInputValue(to, dateValue);
                if (!okFrom || !okTo) {
                    throw new Error("Payslip date inputs not found");
                }
            },
        },
        {
            trigger: "button.o_form_button_save",
            content: "Save payslip",
            run: "click",
        },
        {
            trigger: ".o_form_view",
            content: "Compute payslip",
            run: function (actions) {
                const selectors = [
                    "button[name='compute_sheet']",
                    "button[name='action_compute_sheet']",
                    "button[name='action_payslip_compute']",
                ];
                for (const selector of selectors) {
                    const button = document.querySelector(selector);
                    if (button) {
                        actions.click(button);
                        return;
                    }
                }
                throw new Error("Compute button not found on payslip");
            },
        },
        {
            trigger: ".o_form_view",
            content: "Check commission line",
            run: function () {
                const state = getState();
                if (!state.commissionRule) {
                    throw new Error("Commission rule not stored");
                }
                const widget = document.querySelector(".o_field_widget[name='line_ids']");
                if (!widget || !widget.textContent.includes(state.commissionRule)) {
                    throw new Error("Commission line not found in payslip lines");
                }
            },
        },
        {
            trigger: ".o_form_view",
            content: "Check absence detail",
            run: function () {
                const state = getState();
                if (!state.leaveType) {
                    throw new Error("Leave type not stored");
                }
                const widget = document.querySelector(".o_field_widget[name='leave_days_ids']");
                if (!widget || !widget.textContent.includes(state.leaveType)) {
                    throw new Error("Leave detail not found in payslip");
                }
            },
        },
    ],
});
