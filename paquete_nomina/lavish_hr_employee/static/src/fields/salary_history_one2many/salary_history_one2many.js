/** @odoo-module */

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";
import { deserializeDate, formatDate } from "@web/core/l10n/dates";
import { Component, useState, onWillStart, onWillUpdateProps } from "@odoo/owl";

export class SalaryHistoryField extends Component {
    static template = "lavish_hr_employee.SalaryHistoryField";
    static props = {
        ...standardFieldProps,
    };

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        this.state = useState({
            records: [],
            loading: true,
        });

        onWillStart(async () => {
            await this.loadRecords();
        });

        onWillUpdateProps(async (nextProps) => {
            if (nextProps.record !== this.props.record) {
                await this.loadRecords(nextProps);
            }
        });
    }

    async loadRecords(props = this.props) {
        this.state.loading = true;
        try {
            const recordIds = props.record.data[props.name]?.records?.map(r => r.resId) || [];

            if (recordIds.length > 0) {
                const records = await this.orm.searchRead(
                    "hr.contract.change.wage",
                    [["id", "in", recordIds]],
                    ["id", "name", "date_start", "wage", "wage_old", "difference", "difference_percentage", "reason", "origin_type", "job_id", "state"],
                    { order: "date_start desc" }
                );
                this.state.records = records;
            } else {
                this.state.records = [];
            }
        } catch (error) {
            console.error("Error loading salary history:", error);
            this.state.records = [];
        }
        this.state.loading = false;
    }

    formatDateValue(date) {
        if (!date) return "";
        const dateObj = deserializeDate(date);
        return formatDate(dateObj);
    }

    formatCurrency(value) {
        if (value === undefined || value === null) return "$0";
        return "$" + Math.round(value).toLocaleString("es-CO");
    }

    getDifferenceClass(difference) {
        if (difference >= 0) {
            return "bg-success";
        }
        return "bg-danger";
    }

    getDifferenceSign(difference) {
        return difference >= 0 ? "+" : "";
    }

    getReasonLabel(reason) {
        const reasons = {
            'start': 'Inicio de Contrato',
            'hire': 'Contratacion',
            'promotion': 'Promocion',
            'annual_update': 'Ajuste Anual',
            'performance': 'Desempeno',
            'merit': 'Merito',
            'adjustment': 'Ajuste General',
            'legal': 'Normativa Legal',
            'collective': 'Negociacion Colectiva',
            'business_decision': 'Decision Empresarial',
            'market_adjustment': 'Ajuste al Mercado',
            'restructuring': 'Reestructuracion',
            'other': 'Otro'
        };
        return reasons[reason] || reason || '';
    }

    getOriginBadge(originType) {
        const origins = {
            'salary_increase': { class: 'bg-primary', label: 'Aumento Masivo' },
            'manual': { class: 'bg-secondary', label: 'Manual' },
            'import': { class: 'bg-warning text-dark', label: 'Importacion' },
            'system': { class: 'bg-dark', label: 'Sistema' },
        };
        return origins[originType] || null;
    }

    getStateBadge(state) {
        const states = {
            'draft': { class: 'bg-info', label: 'Borrador' },
            'approved': { class: 'bg-success', label: 'Aprobado' },
        };
        return states[state] || null;
    }

    async onClickRecord(record) {
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "hr.contract.change.wage",
            res_id: record.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async onAddRecord() {
        const contractId = this.props.record.resId;
        if (!contractId) {
            return;
        }
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "hr.contract.change.wage",
            views: [[false, "form"]],
            target: "new",
            context: {
                default_contract_id: contractId,
            },
        });
    }

    async onDeleteRecord(record, ev) {
        ev.stopPropagation();
        try {
            await this.orm.unlink("hr.contract.change.wage", [record.id]);
            await this.loadRecords();
        } catch (error) {
            console.error("Error deleting record:", error);
        }
    }
}

export const salaryHistoryField = {
    component: SalaryHistoryField,
    supportedTypes: ["one2many"],
};

registry.category("fields").add("salary_history_one2many", salaryHistoryField);
