/** @odoo-module */

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart } from "@odoo/owl";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

/**
 * Widget de Selección de Facturas estilo SAP
 * Muestra lista de facturas pendientes con checkboxes para seleccionar
 */
export class InvoiceSelectorWidget extends Component {
    static template = "custom_account_treasury.InvoiceSelectorWidget";
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            invoices: [],
            selectedIds: new Set(),
            loading: false,
            totalSelected: 0,
            searchTerm: "",
            showOverdue: true,
            showCurrent: true,
        });

        onWillStart(async () => {
            await this.loadInvoices();
        });
    }

    get partnerId() {
        return this.props.record.data.partner_id?.[0] || false;
    }

    get partnerType() {
        return this.props.record.data.partner_type || 'supplier';
    }

    get currencyId() {
        return this.props.record.data.currency_id?.[0] || false;
    }

    get companyId() {
        return this.props.record.data.company_id?.[0] || false;
    }

    async loadInvoices() {
        if (!this.partnerId) {
            this.state.invoices = [];
            return;
        }

        this.state.loading = true;
        try {
            const moveTypes = this.partnerType === 'customer'
                ? ['out_invoice', 'out_refund']
                : ['in_invoice', 'in_refund'];

            const domain = [
                ['partner_id', '=', this.partnerId],
                ['state', '=', 'posted'],
                ['payment_state', 'in', ['not_paid', 'partial']],
                ['move_type', 'in', moveTypes],
                ['amount_residual', '!=', 0],
            ];

            if (this.companyId) {
                domain.push(['company_id', '=', this.companyId]);
            }

            const invoices = await this.orm.searchRead(
                "account.move",
                domain,
                [
                    'name', 'ref', 'invoice_date', 'invoice_date_due',
                    'amount_total', 'amount_residual', 'currency_id',
                    'payment_state', 'move_type'
                ],
                { order: 'invoice_date_due asc, name asc' }
            );

            // Calcular días de vencimiento y formatear
            const today = new Date();
            this.state.invoices = invoices.map(inv => {
                const dueDate = inv.invoice_date_due ? new Date(inv.invoice_date_due) : null;
                const daysDue = dueDate ? Math.floor((today - dueDate) / (1000 * 60 * 60 * 24)) : 0;

                return {
                    ...inv,
                    daysDue,
                    isOverdue: daysDue > 0,
                    dueDateFormatted: dueDate ? dueDate.toLocaleDateString('es-CO') : '-',
                    amountFormatted: this.formatCurrency(inv.amount_residual, inv.currency_id?.[1]),
                    totalFormatted: this.formatCurrency(inv.amount_total, inv.currency_id?.[1]),
                    isRefund: inv.move_type.includes('refund'),
                };
            });
        } catch (error) {
            console.error("Error loading invoices:", error);
            this.state.invoices = [];
        }
        this.state.loading = false;
    }

    formatCurrency(amount, currencyName = 'COP') {
        return new Intl.NumberFormat('es-CO', {
            style: 'decimal',
            minimumFractionDigits: 0,
            maximumFractionDigits: 0
        }).format(amount);
    }

    toggleInvoice(invoiceId) {
        if (this.state.selectedIds.has(invoiceId)) {
            this.state.selectedIds.delete(invoiceId);
        } else {
            this.state.selectedIds.add(invoiceId);
        }
        this.updateTotal();
    }

    selectAll() {
        this.filteredInvoices.forEach(inv => {
            this.state.selectedIds.add(inv.id);
        });
        this.updateTotal();
    }

    deselectAll() {
        this.state.selectedIds.clear();
        this.updateTotal();
    }

    selectOverdue() {
        this.state.invoices
            .filter(inv => inv.isOverdue)
            .forEach(inv => this.state.selectedIds.add(inv.id));
        this.updateTotal();
    }

    updateTotal() {
        let total = 0;
        this.state.invoices.forEach(inv => {
            if (this.state.selectedIds.has(inv.id)) {
                // Las notas crédito restan
                const sign = inv.isRefund ? -1 : 1;
                total += inv.amount_residual * sign;
            }
        });
        this.state.totalSelected = total;
    }

    get filteredInvoices() {
        let invoices = this.state.invoices;

        // Filtrar por término de búsqueda
        if (this.state.searchTerm) {
            const term = this.state.searchTerm.toLowerCase();
            invoices = invoices.filter(inv =>
                inv.name.toLowerCase().includes(term) ||
                (inv.ref && inv.ref.toLowerCase().includes(term))
            );
        }

        // Filtrar por estado
        if (!this.state.showOverdue) {
            invoices = invoices.filter(inv => !inv.isOverdue);
        }
        if (!this.state.showCurrent) {
            invoices = invoices.filter(inv => inv.isOverdue);
        }

        return invoices;
    }

    get selectedCount() {
        return this.state.selectedIds.size;
    }

    get hasSelection() {
        return this.state.selectedIds.size > 0;
    }

    async addSelectedToPayment() {
        if (!this.hasSelection) return;

        const selectedInvoices = Array.from(this.state.selectedIds);

        // Llamar al método del modelo para agregar las facturas
        try {
            await this.orm.call(
                "account.payment",
                "action_add_invoices_to_payment",
                [[this.props.record.resId], selectedInvoices]
            );

            // Limpiar selección
            this.state.selectedIds.clear();
            this.state.totalSelected = 0;

            // Recargar el registro
            await this.props.record.load();

            // Recargar lista de facturas
            await this.loadInvoices();
        } catch (error) {
            console.error("Error adding invoices:", error);
        }
    }

    openInvoice(invoiceId) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'account.move',
            res_id: invoiceId,
            views: [[false, 'form']],
            target: 'current',
        });
    }

    onSearchChange(ev) {
        this.state.searchTerm = ev.target.value;
    }

    toggleOverdue() {
        this.state.showOverdue = !this.state.showOverdue;
    }

    toggleCurrent() {
        this.state.showCurrent = !this.state.showCurrent;
    }

    async refresh() {
        await this.loadInvoices();
    }
}

export const invoiceSelectorWidget = {
    component: InvoiceSelectorWidget,
    supportedTypes: ["char", "boolean"],
};

registry.category("fields").add("invoice_selector", invoiceSelectorWidget);
