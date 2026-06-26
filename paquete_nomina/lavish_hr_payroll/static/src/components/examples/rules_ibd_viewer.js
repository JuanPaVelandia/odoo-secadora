/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { GenericHierarchicalTable } from "../generic/hierarchical_table/hierarchical_table";
import { GenericKPI } from "../generic/kpi/generic_kpi";
import { RULES_WITH_IBD_CONFIG } from "../../constants/generic_config";

/**
 * Rules IBD Viewer
 * ================
 *
 * Vista de ejemplo que muestra cómo usar los componentes genéricos
 * para visualizar reglas de nómina con información de IBD.
 *
 * Casos de uso:
 * - Ver todas las reglas agrupadas por categoría
 * - Mostrar % de IBD (40% aplica, 0% excluido)
 * - Enlaces a referencias legales
 * - Porcentaje usado y valor usado en cálculos
 */
export class RulesIBDViewer extends Component {
    static template = "lavish_hr_payroll.RulesIBDViewer";
    static components = { GenericHierarchicalTable, GenericKPI };

    setup() {
        this.orm = useService("orm");
        this.genericData = useService("generic_data");

        this.state = useState({
            loading: true,
            rulesData: [],
            tableConfig: RULES_WITH_IBD_CONFIG,
            kpis: {
                totalRules: 0,
                rulesWithIBD: 0,
                rulesExcluded: 0,
            },
        });

        onWillStart(async () => {
            await this.loadData();
        });
    }

    /**
     * Carga datos de categorías y reglas
     */
    async loadData() {
        try {
            // Cargar categorías
            const categories = await this.orm.searchRead(
                "hr.salary.rule.category",
                [],
                ["id", "code", "name", "sequence", "parent_id"],
                { order: "sequence" }
            );

            // Cargar reglas
            const rules = await this.orm.searchRead(
                "hr.salary.rule",
                [["active", "=", true]],
                [
                    "id", "code", "name", "category_id", "type_concepts", "dev_or_ded",
                    "base_seguridad_social", "excluir_40_porciento_ss", "excluir_seguridad_social",
                    "sequence"
                ],
                { order: "sequence" }
            );

            // Filtrar solo categorías principales (sin parent_id)
            const mainCategories = categories.filter(cat => !cat.parent_id);

            // Transformar a formato jerárquico
            this.state.rulesData = this.genericData.transformToHierarchical(
                mainCategories,
                rules,
                []  // Sin líneas en este caso
            );

            // Calcular KPIs
            this.state.kpis = {
                totalRules: rules.length,
                rulesWithIBD: rules.filter(r => r.base_seguridad_social).length,
                rulesExcluded: rules.filter(r => r.excluir_40_porciento_ss || r.excluir_seguridad_social).length,
            };

            this.state.loading = false;
        } catch (error) {
            console.error("Error loading rules data:", error);
            this.state.loading = false;
        }
    }

    /**
     * Maneja click en una fila
     */
    onRowClick(node) {
        console.log("Row clicked:", node);
        // TODO: Abrir formulario de regla o mostrar detalles
    }

    /**
     * Calcula porcentaje de reglas con IBD
     */
    get ibdPercentage() {
        if (this.state.kpis.totalRules === 0) return 0;
        return Math.round((this.state.kpis.rulesWithIBD / this.state.kpis.totalRules) * 100);
    }
}

registry.category("actions").add("rules_ibd_viewer", RulesIBDViewer);
