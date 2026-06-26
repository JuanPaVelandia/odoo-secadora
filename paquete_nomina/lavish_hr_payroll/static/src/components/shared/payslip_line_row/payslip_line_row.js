/** @odoo-module **/
/**
 * Componente reutilizable para lineas de nomina.
 * Reemplaza el sub-template PayslipLineRow duplicado en multiples componentes.
 */

import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { getCategory } from "../../../constants/payroll_categories";
import { getFaIcon } from "../../../constants/payroll_icons";

export class PayslipLineRow extends Component {
    static template = "lavish_hr_payroll.SharedPayslipLineRow";
    static props = {
        line: Object,
        showCode: { type: Boolean, optional: true },
        showQty: { type: Boolean, optional: true },
        showActions: { type: Boolean, optional: true },
        colorType: { type: String, optional: true },  // 'earning', 'deduction', 'auto'
        onViewDetail: { type: Function, optional: true },
        onViewRule: { type: Function, optional: true },
    };
    static defaultProps = {
        showCode: true,
        showQty: true,
        showActions: true,
        colorType: 'auto',
    };

    setup() {
        this.format = useService("payroll_format");
    }

    get line() {
        return this.props.line || {};
    }

    get categoryConfig() {
        return getCategory(this.line.category_code || 'OTROS');
    }

    get icon() {
        // Usar icono de categoria o icono de props
        return this.line.icon || this.categoryConfig.icon || getFaIcon('default');
    }

    get iconColor() {
        return this.categoryConfig.color || '#9E9E9E';
    }

    get name() {
        return this.line.name || this.line.rule_name || '';
    }

    get code() {
        return this.line.code || '';
    }

    get quantity() {
        if (this.line.quantity === undefined || this.line.quantity === null) {
            return null;
        }
        return this.format.number(this.line.quantity, 2);
    }

    get amount() {
        return this.format.currency(this.line.amount || 0);
    }

    get total() {
        return this.format.currency(this.line.total || 0);
    }

    get amountClass() {
        const total = this.line.total || 0;
        if (this.props.colorType === 'earning') {
            return 'payslip-line__amount--positive';
        } else if (this.props.colorType === 'deduction') {
            return 'payslip-line__amount--negative';
        }
        // Auto: basado en signo
        return total >= 0 ? 'payslip-line__amount--positive' : 'payslip-line__amount--negative';
    }

    get hasActions() {
        return this.props.showActions && (this.props.onViewDetail || this.props.onViewRule);
    }

    onClickDetail(ev) {
        ev.stopPropagation();
        if (this.props.onViewDetail) {
            this.props.onViewDetail(this.line);
        }
    }

    onClickRule(ev) {
        ev.stopPropagation();
        if (this.props.onViewRule) {
            this.props.onViewRule(this.line);
        }
    }
}
