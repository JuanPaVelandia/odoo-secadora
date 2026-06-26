/** @odoo-module **/

import { Component, useState, onWillStart, onWillUpdateProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { FORMATTERS } from "../../../constants/generic_config";

/**
 * GenericHierarchicalTable Component
 * ==================================
 *
 * Componente genérico para mostrar datos jerárquicos en tabla expandible.
 * Soporta hasta 3 niveles de profundidad con configuración completa.
 *
 * @example
 * const config = {
 *     levels: [
 *         { name: 'category', labelField: 'name', colorField: 'color', expandable: true },
 *         { name: 'rule', labelField: 'name', showBadge: true, badgeField: 'type' },
 *     ],
 *     columns: [
 *         { key: 'name', label: 'Nombre', width: '40%' },
 *         { key: 'amount', label: 'Valor', width: '20%', formatter: 'currency' },
 *     ]
 * };
 *
 * <GenericHierarchicalTable
 *     data="state.hierarchicalData"
 *     config="tableConfig"
 *     expandedByDefault="false"
 * />
 */
export class GenericHierarchicalTable extends Component {
    static template = "lavish_hr_payroll.GenericHierarchicalTable";

    static props = {
        data: Array,
        config: Object,
        onRowClick: { type: Function, optional: true },
        expandedByDefault: { type: Boolean, optional: true },
        searchable: { type: Boolean, optional: true },
        title: { type: String, optional: true },
    };

    static defaultProps = {
        expandedByDefault: false,
        searchable: false,
    };

    setup() {
        this.genericData = useService("generic_data");

        this.state = useState({
            expanded: {},
            searchTerm: '',
        });

        onWillStart(() => {
            this.initializeExpandedState();
        });

        onWillUpdateProps((nextProps) => {
            if (nextProps.data !== this.props.data) {
                this.initializeExpandedState();
            }
        });
    }

    /**
     * Inicializa el estado de expansión para todos los nodos
     */
    initializeExpandedState() {
        if (this.props.expandedByDefault) {
            this._expandAll(this.props.data);
        }
    }

    /**
     * Expande todos los nodos recursivamente
     * @private
     */
    _expandAll(nodes) {
        nodes.forEach(node => {
            this.state.expanded[node.id] = true;
            if (node.children && node.children.length > 0) {
                this._expandAll(node.children);
            }
        });
    }

    /**
     * Toggle expansión de un nodo
     */
    toggleExpanded(nodeId) {
        this.state.expanded[nodeId] = !this.state.expanded[nodeId];
    }

    /**
     * Verifica si un nodo está expandido
     */
    isExpanded(nodeId) {
        return Boolean(this.state.expanded[nodeId]);
    }

    /**
     * Filtra datos por término de búsqueda
     */
    get filteredData() {
        if (!this.props.searchable || !this.state.searchTerm) {
            return this.props.data;
        }

        const term = this.state.searchTerm.toLowerCase();
        return this._filterNodes(this.props.data, term);
    }

    /**
     * Filtra nodos recursivamente
     * @private
     */
    _filterNodes(nodes, term) {
        return nodes.filter(node => {
            // Buscar en campos del nodo
            const nodeMatches = Object.values(node).some(value =>
                String(value).toLowerCase().includes(term)
            );

            // Buscar en hijos
            const childrenMatch = node.children && node.children.length > 0 &&
                this._filterNodes(node.children, term).length > 0;

            return nodeMatches || childrenMatch;
        }).map(node => {
            if (node.children && node.children.length > 0) {
                return {
                    ...node,
                    children: this._filterNodes(node.children, term)
                };
            }
            return node;
        });
    }

    /**
     * Obtiene la configuración del nivel para un nodo
     */
    getLevelConfig(node) {
        return this.props.config.levels.find(l => l.name === node.level) || {};
    }

    /**
     * Verifica si un nodo es expandible
     */
    isExpandable(node) {
        const levelConfig = this.getLevelConfig(node);
        return levelConfig.expandable && node.children && node.children.length > 0;
    }

    /**
     * Obtiene el icono de expansión
     */
    getExpandIcon(nodeId) {
        return this.isExpanded(nodeId) ? 'fa-chevron-down' : 'fa-chevron-right';
    }

    /**
     * Obtiene el valor de un campo del nodo
     */
    getFieldValue(node, fieldKey) {
        return node[fieldKey] || '';
    }

    /**
     * Formatea un valor según la columna
     */
    formatCellValue(node, column) {
        const value = this.getFieldValue(node, column.key);

        // Si la columna tiene formatter custom (función)
        if (typeof column.formatter === 'function') {
            return column.formatter(value, node);
        }

        // Si la columna tiene formatter por nombre
        if (typeof column.formatter === 'string' && FORMATTERS[column.formatter]) {
            return FORMATTERS[column.formatter](value);
        }

        // Por defecto, retornar valor como string
        return String(value || '');
    }

    /**
     * Obtiene el color de fondo de una celda
     */
    getCellBgColor(node, column) {
        // Si la columna tiene colorFormatter custom
        if (column.colorFormatter && typeof column.colorFormatter === 'function') {
            return column.colorFormatter(this.getFieldValue(node, column.key), node);
        }

        // Si el nodo tiene color definido
        if (column.key === 'ibd_percentage' && node.ibd_color) {
            return node.ibd_color;
        }

        return null;
    }

    /**
     * Obtiene el color de texto de una celda
     */
    getCellTextColor(node, column) {
        // Si la columna tiene textColorFormatter custom
        if (column.textColorFormatter && typeof column.textColorFormatter === 'function') {
            return column.textColorFormatter(this.getFieldValue(node, column.key), node);
        }

        return null;
    }

    /**
     * Obtiene el estilo completo de una celda
     */
    getCellStyle(node, column) {
        const styles = [];

        const bgColor = this.getCellBgColor(node, column);
        if (bgColor) {
            styles.push(`background-color: ${bgColor}`);
        }

        const textColor = this.getCellTextColor(node, column);
        if (textColor) {
            styles.push(`color: ${textColor}`);
        }

        if (column.width) {
            styles.push(`width: ${column.width}`);
        }

        return styles.join('; ');
    }

    /**
     * Obtiene el estilo de la fila según el nivel
     */
    getRowStyle(node) {
        const levelConfig = this.getLevelConfig(node);
        const styles = [];

        // Color de fondo del nivel
        if (node.bgColor) {
            styles.push(`background-color: ${node.bgColor}`);
        }

        // Color de texto del nivel
        if (node.textColor) {
            styles.push(`color: ${node.textColor}`);
        }

        return styles.join('; ');
    }

    /**
     * Obtiene la clase CSS de la fila según el nivel
     */
    getRowClass(node) {
        const classes = ['generic-table__row'];
        classes.push(`generic-table__row--${node.level}`);

        if (this.isExpandable(node)) {
            classes.push('generic-table__row--expandable');
        }

        return classes.join(' ');
    }

    /**
     * Maneja click en una fila
     */
    handleRowClick(node) {
        if (this.props.onRowClick) {
            this.props.onRowClick(node);
        }
    }

    /**
     * Maneja cambio en el campo de búsqueda
     */
    onSearchChange(ev) {
        this.state.searchTerm = ev.target.value;
    }

    /**
     * Obtiene el padding izquierdo según el nivel (indentación)
     */
    getIndentPadding(node) {
        const levelIndex = this.props.config.levels.findIndex(l => l.name === node.level);
        return `${levelIndex * 20}px`;
    }

    /**
     * Verifica si una columna es de tipo link
     */
    isLinkColumn(column) {
        return column.type === 'link';
    }

    /**
     * Verifica si una columna es de tipo badge
     */
    isBadgeColumn(column) {
        return column.type === 'badge';
    }

    /**
     * Obtiene la URL del link
     */
    getLinkUrl(node, column) {
        if (column.linkField) {
            return node[column.linkField] || '#';
        }
        return '#';
    }
}
