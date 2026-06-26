/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class BatchList extends Component {
    static template = "lavish_hr_payroll.BatchList";
    static props = {
        batches: Array,
        period: Object,
    };

    setup() {
        this.action = useService("action");
        this.state = useState({
            selectedState: 'all',
        });
    }

    get states() {
        return [
            { key: 'all', label: 'Todos', icon: 'fa-list', color: 'secondary' },
            { key: 'draft', label: 'Borrador', icon: 'fa-pencil', color: 'secondary' },
            { key: 'verify', label: 'Verificar', icon: 'fa-search', color: 'info' },
            { key: 'close', label: 'Cerrado', icon: 'fa-lock', color: 'success' },
            { key: 'paid', label: 'Pagado', icon: 'fa-check-circle', color: 'primary' },
        ];
    }

    get filteredBatches() {
        if (this.state.selectedState === 'all') {
            return this.props.batches;
        }
        return this.props.batches.filter(b => b.state === this.state.selectedState);
    }

    get stateCount() {
        const counts = { all: this.props.batches.length };
        for (const batch of this.props.batches) {
            counts[batch.state] = (counts[batch.state] || 0) + 1;
        }
        return counts;
    }

    setStateFilter(state) {
        this.state.selectedState = state;
    }

    async openBatch(batchId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "hr.payslip.run",
            res_id: batchId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    getStateClass(state) {
        const stateClasses = {
            'draft': 'secondary',
            'verify': 'info',
            'close': 'success',
            'paid': 'primary',
        };
        return stateClasses[state] || 'secondary';
    }

    getStateIcon(state) {
        const stateIcons = {
            'draft': 'fa-pencil',
            'verify': 'fa-search',
            'close': 'fa-lock',
            'paid': 'fa-check-circle',
        };
        return stateIcons[state] || 'fa-circle';
    }
}
