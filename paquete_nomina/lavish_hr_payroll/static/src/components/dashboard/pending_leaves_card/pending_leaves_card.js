/** @odoo-module **/

import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class PendingLeavesCard extends Component {
    static template = "lavish_hr_payroll.PendingLeavesCard";

    setup() {
        this.action = useService("action");
    }

    get hasData() {
        return this.props.leavesData &&
               this.props.leavesData.leaves &&
               this.props.leavesData.leaves.length > 0;
    }

    get totalLeaves() {
        return this.props.leavesData?.total || 0;
    }

    get criticalCount() {
        return this.props.leavesData?.critical || 0;
    }

    get highCount() {
        return this.props.leavesData?.high || 0;
    }

    get mediumCount() {
        return this.props.leavesData?.medium || 0;
    }

    get leaves() {
        if (!this.props.leavesData?.leaves) return [];
        // Return only first 5 leaves for display
        return this.props.leavesData.leaves.slice(0, 5);
    }

    getUrgencyClass(urgency) {
        const classes = {
            'critical': 'danger',
            'high': 'warning',
            'medium': 'info',
            'low': 'success'
        };
        return classes[urgency] || 'secondary';
    }

    getUrgencyIcon(urgency) {
        const icons = {
            'critical': 'fa-exclamation-circle',
            'high': 'fa-exclamation-triangle',
            'medium': 'fa-info-circle',
            'low': 'fa-check-circle'
        };
        return icons[urgency] || 'fa-circle';
    }

    getLeaveTypeIcon(leaveType) {
        // Map leave type codes to icons
        const icons = {
            'VAC': 'fa-plane',
            'IGE': 'fa-medkit',
            'IRL': 'fa-ambulance',
            'LMA': 'fa-female',
            'LPA': 'fa-child',
            'LIC': 'fa-file-alt'
        };

        // Check if leave_type contains any of the codes
        for (const [code, icon] of Object.entries(icons)) {
            if (leaveType && leaveType.includes(code)) {
                return icon;
            }
        }

        return 'fa-calendar-times';
    }

    async onViewAllLeaves() {
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
            await this.props.onAction('view_pending_leaves', params);
        }
    }

    async onViewLeave(leaveId) {
        // Open the leave record directly
        await this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'hr.leave',
            res_id: leaveId,
            views: [[false, 'form']],
            target: 'current',
        });
    }

    async onCreateLeave() {
        // Open form to create new leave
        await this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'hr.leave',
            views: [[false, 'form']],
            target: 'current',
            context: {
                default_state: 'confirm',
            }
        });
    }
}
