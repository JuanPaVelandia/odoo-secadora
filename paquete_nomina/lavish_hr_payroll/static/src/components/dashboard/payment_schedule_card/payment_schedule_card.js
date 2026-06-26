/** @odoo-module **/

import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class PaymentScheduleCard extends Component {
    static template = "lavish_hr_payroll.PaymentScheduleCard";

    setup() {
        this.action = useService("action");
    }

    get hasData() {
        return this.props.scheduleData &&
               this.props.scheduleData.schedule &&
               this.props.scheduleData.schedule.length > 0;
    }

    get totalScheduled() {
        return this.props.scheduleData?.formatted_total || '$0';
    }

    get paymentDatesCount() {
        return this.props.scheduleData?.payment_dates_count || 0;
    }

    get scheduleItems() {
        if (!this.props.scheduleData?.schedule) return [];
        // Return only first 5 items for display
        return this.props.scheduleData.schedule.slice(0, 5);
    }

    get totalItems() {
        return this.props.scheduleData?.schedule?.length || 0;
    }

    getDaysUntilPayment(dateStr) {
        if (!dateStr) return null;
        const paymentDate = new Date(dateStr);
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        paymentDate.setHours(0, 0, 0, 0);
        const diffTime = paymentDate - today;
        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
        return diffDays;
    }

    getUrgencyClass(dateStr) {
        const days = this.getDaysUntilPayment(dateStr);
        if (days === null) return 'secondary';
        if (days < 0) return 'danger';
        if (days <= 3) return 'warning';
        if (days <= 7) return 'info';
        return 'secondary';
    }

    getUrgencyText(dateStr) {
        const days = this.getDaysUntilPayment(dateStr);
        if (days === null) return '';
        if (days < 0) return 'Vencido';
        if (days === 0) return 'Hoy';
        if (days === 1) return 'Mañana';
        return `En ${days} días`;
    }

    async onViewAllSchedule() {
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
            await this.props.onAction('view_payment_schedule', params);
        }
    }

    async onViewBatch(batchId) {
        if (this.props.onAction) {
            await this.props.onAction('view_batches', {
                batch_id: batchId
            });
        }
    }
}
