/** @odoo-module **/

import { registry } from "@web/core/registry";
import { getCategory } from "../constants/payroll_categories";

/**
 * Servicio Genérico de Transformación de Datos
 * ============================================
 *
 * Transforma datos de Odoo a estructuras genéricas reutilizables
 * para los componentes visuales.
 *
 * Casos de uso:
 * - Tablas jerárquicas (categorías → reglas → líneas)
 * - Secciones de pasos (fórmulas, cálculos)
 * - Visualización de registros (nóminas, ausencias, préstamos)
 * - Comparaciones históricas
 */
export const genericDataService = {
    start() {
        return {
            /**
             * Transforma reglas de nómina a formato jerárquico genérico
             *
             * @param {Array} categories - Categorías de hr.salary.rule.category
             * @param {Array} rules - Reglas de hr.salary.rule
             * @param {Array} lines - Líneas de hr.payslip.line (opcional)
             * @returns {Array} Estructura jerárquica lista para GenericHierarchicalTable
             *
             * @example
             * const data = transformToHierarchical(categories, rules, lines);
             * // [{id: 'cat_1', name: 'Devengo Salarial', children: [...]}]
             */
            transformToHierarchical(categories, rules, lines = []) {
                return categories.map(cat => {
                    const categoryConfig = getCategory(cat.code);
                    const categoryRules = rules.filter(r => r.category_id && r.category_id[0] === cat.id);

                    return {
                        id: `cat_${cat.id}`,
                        level: 'category',
                        name: cat.name,
                        code: cat.code,
                        color: categoryConfig?.color || '#9E9E9E',
                        bgColor: categoryConfig?.bgColor || '#F5F5F5',
                        textColor: categoryConfig?.textColor || '#424242',
                        icon: categoryConfig?.icon || 'fa-folder',
                        total: this._calculateCategoryTotal(categoryRules, lines),
                        children: this._transformRules(categoryRules, lines)
                    };
                });
            },

            /**
             * Transforma reglas a formato genérico
             * @private
             */
            _transformRules(rules, lines) {
                return rules.map(rule => {
                    const ruleLines = lines.filter(l => l.salary_rule_id && l.salary_rule_id[0] === rule.id);

                    return {
                        id: `rule_${rule.id}`,
                        level: 'rule',
                        name: rule.name,
                        code: rule.code,
                        type_concepts: rule.type_concepts || 'contrato',
                        dev_or_ded: rule.dev_or_ded || '',

                        // Campos IBD
                        base_seguridad_social: rule.base_seguridad_social || false,
                        excluir_40_porciento_ss: rule.excluir_40_porciento_ss || false,
                        excluir_seguridad_social: rule.excluir_seguridad_social || false,
                        ibd_percentage: this._calculateIBDPercentage(rule),
                        ibd_color: this._getIBDColor(rule),

                        // Referencias legales (si existen)
                        law_reference: rule.law_reference || '',
                        law_url: rule.law_url || '',

                        // Totales
                        total: this._calculateRuleTotal(ruleLines),
                        quantity: this._calculateRuleQuantity(ruleLines),

                        // Líneas hijas
                        children: this._transformLines(ruleLines)
                    };
                });
            },

            /**
             * Transforma líneas a formato genérico
             * @private
             */
            _transformLines(lines) {
                return lines.map(line => ({
                    id: `line_${line.id}`,
                    level: 'line',
                    description: this._buildLineDescription(line),
                    payslip_id: line.slip_id ? line.slip_id[0] : null,
                    payslip_number: line.slip_id ? line.slip_id[1] : '',
                    date_from: line.date_from || '',
                    date_to: line.date_to || '',
                    quantity: line.quantity || 0,
                    amount: line.amount || 0,
                    rate: line.rate || 0,
                    total: line.total || 0,
                }));
            },

            /**
             * Calcula total de categoría
             * @private
             */
            _calculateCategoryTotal(rules, lines) {
                if (lines.length === 0) return 0;

                const ruleIds = rules.map(r => r.id);
                return lines
                    .filter(l => l.salary_rule_id && ruleIds.includes(l.salary_rule_id[0]))
                    .reduce((sum, line) => sum + (line.total || 0), 0);
            },

            /**
             * Calcula total de regla
             * @private
             */
            _calculateRuleTotal(lines) {
                return lines.reduce((sum, line) => sum + (line.total || 0), 0);
            },

            /**
             * Calcula cantidad de regla
             * @private
             */
            _calculateRuleQuantity(lines) {
                if (lines.length === 0) return 0;
                // Retornar promedio de cantidad si hay múltiples líneas
                const total = lines.reduce((sum, line) => sum + (line.quantity || 0), 0);
                return total / lines.length;
            },

            /**
             * Calcula porcentaje de IBD
             * @private
             */
            _calculateIBDPercentage(rule) {
                if (rule.excluir_seguridad_social || rule.excluir_40_porciento_ss) {
                    return 0;
                }
                return rule.base_seguridad_social ? 40 : 0;
            },

            /**
             * Obtiene color para indicador de IBD
             * @private
             */
            _getIBDColor(rule) {
                if (rule.excluir_seguridad_social || rule.excluir_40_porciento_ss) {
                    return '#C0C0C0'; // Gris - Excluido
                }
                return rule.base_seguridad_social ? '#92D050' : '#FFFFFF'; // Verde - Aplica 40% | Blanco - No aplica
            },

            /**
             * Construye descripción de línea
             * @private
             */
            _buildLineDescription(line) {
                const parts = [];

                if (line.slip_id && line.slip_id[1]) {
                    parts.push(line.slip_id[1]);
                }

                if (line.date_from && line.date_to) {
                    const dateFrom = new Date(line.date_from);
                    const dateTo = new Date(line.date_to);
                    const monthYear = `${dateTo.toLocaleString('es-ES', { month: 'short' })}/${dateTo.getFullYear()}`;
                    const fortnight = dateTo.getDate() <= 15 ? 'Q1' : 'Q2';
                    parts.push(`${fortnight} ${monthYear}`);
                }

                return parts.join(' - ') || line.name || 'Línea';
            },

            /**
             * Transforma datos de IBD a formato de pasos
             *
             * @param {Object} ibdData - Datos de IBD con estructura de explicaciones legales
             * @returns {Array} Pasos formateados para GenericStepByStep
             *
             * @example
             * const steps = transformToSteps(ibdData);
             * // [{number: 1, label: 'Ingresos Salariales', formula: '...', value: 3500000, ...}]
             */
            transformToSteps(ibdData) {
                if (!ibdData || !ibdData.explicaciones_legales) {
                    return [];
                }

                return ibdData.explicaciones_legales.map((exp, idx) => ({
                    number: idx + 1,
                    label: exp.titulo || `Paso ${idx + 1}`,
                    formula: exp.formula || '',
                    value: exp.valor || 0,
                    legalReference: {
                        text: exp.base_legal || '',
                        url: exp.url || '#'
                    },
                    details: exp.explicacion || '',
                    termino_legal: exp.termino_legal || ''
                }));
            },

            /**
             * Transforma nómina a formato de visualización de registro
             *
             * @param {Object} payslip - Registro de hr.payslip
             * @returns {Object} Datos formateados para GenericRecordViewer
             */
            transformPayslip(payslip) {
                return {
                    recordType: 'payslip',
                    recordId: payslip.id,
                    fields: this._getPayslipFields(payslip),
                    sections: this._groupPayslipLinesByCategory(payslip.line_ids)
                };
            },

            /**
             * Obtiene campos de nómina
             * @private
             */
            _getPayslipFields(payslip) {
                return [
                    { key: 'id', label: 'ID', value: payslip.id, type: 'text', highlight: true },
                    { key: 'number', label: 'Número', value: payslip.number, type: 'text' },
                    { key: 'employee_id', label: 'Empleado', value: payslip.employee_id ? payslip.employee_id[1] : '', type: 'text' },
                    { key: 'date_from', label: 'Desde', value: payslip.date_from, type: 'date' },
                    { key: 'date_to', label: 'Hasta', value: payslip.date_to, type: 'date' },
                    { key: 'state', label: 'Estado', value: payslip.state, type: 'badge', colorMap: this._getPayslipStateColors() },
                ];
            },

            /**
             * Agrupa líneas de nómina por categoría
             * @private
             */
            _groupPayslipLinesByCategory(lines) {
                const sections = new Map();

                lines.forEach(line => {
                    if (!line.category_id) return;

                    const catCode = line.category_id[1]; // Assuming [id, name]
                    const categoryConfig = getCategory(catCode);

                    if (!sections.has(catCode)) {
                        sections.set(catCode, {
                            title: line.category_id[1],
                            color: categoryConfig?.bgColor || '#F5F5F5',
                            textColor: categoryConfig?.textColor || '#424242',
                            lines: []
                        });
                    }

                    sections.get(catCode).lines.push({
                        code: line.code,
                        name: line.name,
                        quantity: line.quantity,
                        amount: line.total
                    });
                });

                return Array.from(sections.values());
            },

            /**
             * Colores de estados de nómina
             * @private
             */
            _getPayslipStateColors() {
                return {
                    'draft': '#EEEEEE',
                    'verify': '#E8EAF6',
                    'done': '#E8F5E9',
                    'paid': '#E1F5FE',
                    'cancel': '#FFEBEE'
                };
            },

            /**
             * Transforma ausencia a formato de visualización
             *
             * @param {Object} absence - Registro de hr.leave
             * @returns {Object} Datos formateados para GenericRecordViewer
             */
            transformAbsence(absence) {
                return {
                    recordType: 'absence',
                    recordId: absence.id,
                    fields: this._getAbsenceFields(absence),
                    sections: this._getAbsenceSections(absence)
                };
            },

            /**
             * Obtiene campos de ausencia
             * @private
             */
            _getAbsenceFields(absence) {
                return [
                    { key: 'id', label: 'ID Ausencia', value: absence.id, type: 'text', highlight: true },
                    { key: 'holiday_status_id', label: 'Tipo', value: absence.holiday_status_id ? absence.holiday_status_id[1] : '', type: 'badge' },
                    { key: 'employee_id', label: 'Empleado', value: absence.employee_id ? absence.employee_id[1] : '', type: 'text' },
                    { key: 'date_from', label: 'Desde', value: absence.request_date_from, type: 'date' },
                    { key: 'date_to', label: 'Hasta', value: absence.request_date_to, type: 'date' },
                    { key: 'number_of_days', label: 'Días', value: absence.number_of_days, type: 'number' },
                    { key: 'state', label: 'Estado', value: absence.state, type: 'badge' },
                ];
            },

            /**
             * Obtiene secciones de ausencia
             * @private
             */
            _getAbsenceSections(absence) {
                const sections = [];

                if (absence.payslip_line_ids && absence.payslip_line_ids.length > 0) {
                    sections.push({
                        title: 'Líneas de Nómina Afectadas',
                        color: '#FFF3E0',
                        lines: absence.payslip_line_ids.map(line => ({
                            code: line.code,
                            name: line.name,
                            amount: line.total
                        }))
                    });
                }

                return sections;
            },

            /**
             * Transforma préstamo a formato de visualización
             *
             * @param {Object} loan - Registro de hr.loan
             * @returns {Object} Datos formateados para GenericRecordViewer
             */
            transformLoan(loan) {
                return {
                    recordType: 'loan',
                    recordId: loan.id,
                    fields: this._getLoanFields(loan),
                    sections: this._getLoanSections(loan)
                };
            },

            /**
             * Obtiene campos de préstamo
             * @private
             */
            _getLoanFields(loan) {
                return [
                    { key: 'id', label: 'ID Préstamo', value: loan.id, type: 'text', highlight: true },
                    { key: 'name', label: 'Nombre', value: loan.name, type: 'text' },
                    { key: 'employee_id', label: 'Empleado', value: loan.employee_id ? loan.employee_id[1] : '', type: 'text' },
                    { key: 'loan_amount', label: 'Monto', value: loan.loan_amount, type: 'currency' },
                    { key: 'balance_amount', label: 'Saldo', value: loan.balance_amount, type: 'currency' },
                    { key: 'installment', label: 'Cuota', value: loan.installment, type: 'currency' },
                    { key: 'state', label: 'Estado', value: loan.state, type: 'badge' },
                ];
            },

            /**
             * Obtiene secciones de préstamo
             * @private
             */
            _getLoanSections(loan) {
                const sections = [];

                if (loan.loan_lines && loan.loan_lines.length > 0) {
                    const pending = loan.loan_lines.filter(l => !l.paid);
                    const paid = loan.loan_lines.filter(l => l.paid);

                    if (pending.length > 0) {
                        sections.push({
                            title: 'Cuotas Pendientes',
                            color: '#FFF3E0',
                            lines: pending.map(l => ({
                                code: l.id,
                                name: `Cuota ${l.seq}`,
                                amount: l.amount
                            }))
                        });
                    }

                    if (paid.length > 0) {
                        sections.push({
                            title: 'Cuotas Pagadas',
                            color: '#E8F5E9',
                            lines: paid.map(l => ({
                                code: l.id,
                                name: `Cuota ${l.seq}`,
                                amount: l.amount
                            }))
                        });
                    }
                }

                return sections;
            },

            /**
             * Transforma datos para comparación histórica
             *
             * @param {Object} currentValue - Valor actual
             * @param {Array} previousRecords - Registros históricos
             * @param {String} comparisonField - Campo a comparar
             * @returns {Object} Datos formateados para GenericHistorySection
             */
            transformToHistory(currentValue, previousRecords, comparisonField) {
                const currentVal = currentValue[comparisonField] || 0;

                return {
                    currentValue: {
                        ...currentValue,
                        value: currentVal
                    },
                    previousValues: previousRecords.map(record => {
                        const recordVal = record[comparisonField] || 0;
                        const difference = currentVal - recordVal;
                        const percentChange = recordVal !== 0 ? ((difference / recordVal) * 100) : 0;

                        return {
                            period: record.period || record.date || '',
                            label: record.label || this._formatPeriodLabel(record),
                            value: recordVal,
                            difference: difference,
                            percentChange: percentChange,
                            reason: record.reason || ''
                        };
                    })
                };
            },

            /**
             * Formatea etiqueta de período
             * @private
             */
            _formatPeriodLabel(record) {
                if (record.date) {
                    const date = new Date(record.date);
                    return date.toLocaleString('es-ES', { month: 'long', year: 'numeric' });
                }
                return 'Período anterior';
            },

            /**
             * Formatea valor según tipo
             *
             * @param {*} value - Valor a formatear
             * @param {String} formatter - Tipo de formato ('currency', 'number', 'percentage', 'date')
             * @returns {String} Valor formateado
             */
            formatValue(value, formatter) {
                if (value === null || value === undefined) return '';

                switch (formatter) {
                    case 'currency':
                        return new Intl.NumberFormat('es-CO', {
                            style: 'currency',
                            currency: 'COP',
                            minimumFractionDigits: 0,
                            maximumFractionDigits: 0
                        }).format(value);

                    case 'number':
                        return new Intl.NumberFormat('es-CO').format(value);

                    case 'percentage':
                        return `${value}%`;

                    case 'date':
                        return new Date(value).toLocaleDateString('es-CO');

                    default:
                        return String(value);
                }
            }
        };
    }
};

registry.category("services").add("generic_data", genericDataService);
