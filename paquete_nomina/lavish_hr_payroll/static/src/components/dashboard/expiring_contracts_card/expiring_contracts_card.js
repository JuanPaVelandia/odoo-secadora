/** @odoo-module **/

import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class ExpiringContractsCard extends Component {
    static template = "lavish_hr_payroll.ExpiringContractsCard";

    setup() {
        this.action = useService("action");
    }

    get hasData() {
        return this.props.contractsData &&
               this.props.contractsData.contracts &&
               this.props.contractsData.contracts.length > 0;
    }

    get totalContracts() {
        return this.props.contractsData?.total || 0;
    }

    get criticalCount() {
        return this.props.contractsData?.critical || 0;
    }

    get highCount() {
        return this.props.contractsData?.high || 0;
    }

    get mediumCount() {
        return this.props.contractsData?.medium || 0;
    }

    get contracts() {
        if (!this.props.contractsData?.contracts) return [];
        // Return only first 5 contracts for display
        return this.props.contractsData.contracts.slice(0, 5);
    }

    getUrgencyClass(urgency) {
        const classes = {
            'critical': 'danger',
            'high': 'warning',
            'medium': 'info'
        };
        return classes[urgency] || 'secondary';
    }

    getUrgencyIcon(urgency) {
        const icons = {
            'critical': 'fa-exclamation-circle',
            'high': 'fa-exclamation-triangle',
            'medium': 'fa-info-circle'
        };
        return icons[urgency] || 'fa-circle';
    }

    getUrgencyText(urgency) {
        const texts = {
            'critical': 'Crítico',
            'high': 'Alto',
            'medium': 'Medio'
        };
        return texts[urgency] || urgency;
    }

    async onViewAllContracts() {
        if (this.props.onAction) {
            const params = {};
            if (this.props.period?.id) {
                params.period_id = this.props.period.id;
            }
            if (this.props.period?.date_from) {
                params.date_from = this.props.period.date_from;
            }
            if (this.props.period?.date_to) {
                params.date_to = this.props.period.date_to;
            }
            await this.props.onAction('view_expiring_contracts', params);
        }
    }

    async onViewContract(contractId) {
        if (this.props.onAction) {
            await this.props.onAction('view_contracts', {
                contract_id: contractId
            });
        }
    }
}
