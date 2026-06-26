/** @odoo-module **/

import { Component } from "@odoo/owl";
import { FORMATTERS } from "../../../constants/generic_config";

/**
 * GenericKPI Component
 * ====================
 *
 * Componente genérico para mostrar KPIs (Key Performance Indicators)
 * con iconos, valores formateados, tendencias y colores dinámicos.
 *
 * @example
 * <GenericKPI
 *     label="'IBD Total'"
 *     value="5000000"
 *     formatter="'currency'"
 *     icon="'fa-dollar-sign'"
 *     iconType="'fa'"
 *     color="'#43A047'"
 *     trend="{ value: 15, direction: 'up' }"
 *     onClick="() => this.handleClick()"
 * />
 */
export class GenericKPI extends Component {
    static template = "lavish_hr_payroll.GenericKPI";

    static props = {
        label: String,
        value: [Number, String],
        formatter: { type: String, optional: true },
        icon: { type: String, optional: true },
        iconType: { type: String, optional: true },  // 'fa' o 'lottie'
        color: { type: String, optional: true },
        bgColor: { type: String, optional: true },
        trend: { type: Object, optional: true },     // { value: number, direction: 'up'|'down'|'neutral' }
        onClick: { type: Function, optional: true },
        size: { type: String, optional: true },      // 'small', 'medium', 'large'
        helpText: { type: String, optional: true },
    };

    static defaultProps = {
        formatter: 'number',
        iconType: 'fa',
        color: '#43A047',
        bgColor: '#F5F5F5',
        size: 'medium',
    };

    /**
     * Formatea el valor según el tipo especificado
     */
    get formattedValue() {
        const formatter = FORMATTERS[this.props.formatter];
        if (formatter) {
            return formatter(this.props.value);
        }
        return String(this.props.value || '');
    }

    /**
     * Clase CSS para el tamaño del KPI
     */
    get sizeClass() {
        return `generic-kpi--${this.props.size || 'medium'}`;
    }

    /**
     * Clase CSS para el icono
     */
    get iconClass() {
        if (this.props.iconType === 'lottie') {
            return '';
        }
        return `fa ${this.props.icon || 'fa-chart-line'}`;
    }

    /**
     * Estilo dinámico para el icono
     */
    get iconStyle() {
        return `color: ${this.props.color || '#43A047'}`;
    }

    /**
     * Estilo dinámico para el fondo del KPI
     */
    get containerStyle() {
        return `background-color: ${this.props.bgColor || '#F5F5F5'}`;
    }

    /**
     * Clase CSS para la tendencia
     */
    get trendClass() {
        if (!this.props.trend) return '';

        const direction = this.props.trend.direction || 'neutral';
        return `generic-kpi__trend--${direction}`;
    }

    /**
     * Icono de tendencia
     */
    get trendIcon() {
        if (!this.props.trend) return '';

        const direction = this.props.trend.direction || 'neutral';
        const iconMap = {
            'up': 'fa-arrow-up',
            'down': 'fa-arrow-down',
            'neutral': 'fa-minus'
        };
        return `fa ${iconMap[direction]}`;
    }

    /**
     * Valor de tendencia formateado
     */
    get trendValue() {
        if (!this.props.trend || this.props.trend.value === undefined) return '';

        const value = Math.abs(this.props.trend.value);
        return `${value}%`;
    }

    /**
     * Maneja click en el KPI
     */
    handleClick() {
        if (this.props.onClick) {
            this.props.onClick();
        }
    }

    /**
     * Indica si el KPI es clickeable
     */
    get isClickable() {
        return Boolean(this.props.onClick);
    }
}
