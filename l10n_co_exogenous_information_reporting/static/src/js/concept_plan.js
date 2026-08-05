/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { user } from "@web/core/user";

/**
 * Vista OWL: Plan jerárquico de Conceptos.
 * Árbol expandible: Formato → Concepto → Columna.
 * Panel lateral para editar dominio, excluidos, naturaleza, etc.
 */

const NATURE_OPTIONS = [
    { value: "debit", label: "DB (Débito)" },
    { value: "credit", label: "CR (Crédito)" },
    { value: "db_cr", label: "DB-CR" },
    { value: "cr_db", label: "CR-DB" },
    { value: "base_calc_db", label: "Base DB" },
    { value: "base_calc_cr", label: "Base CR" },
    { value: "base_calc_db_cr", label: "Base DB-CR" },
    { value: "base_calc_cr_db", label: "Base CR-DB" },
    { value: "tax_base_amount", label: "Base almacenada" },
    { value: "balance", label: "Saldo" },
];

const DEFAULT_KPIS = { concepts: 0, columns: 0, configured: 0, accounts: 0 };
const STORAGE_KEY = "l10n_co_exogenous.concept_plan.viewState";

export class ExogenousConceptPlan extends Component {
    static template = "l10n_co_exogenous.ConceptPlan";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.natureOptions = NATURE_OPTIONS;

        this.state = useState({
            loading: false,
            formats: [],
            selectedFormatId: null,
            selectedSettingId: null,
            formatSettings: [],
            treeData: [],
            expandedConcepts: {},
            selectedNode: null,
            detailPattern: "",
            detailNature: "db_cr",
            detailDomain: "",
            detailMoveType: "all",
            detailTaxFilter: "all",
            kpis: { ...DEFAULT_KPIS },
        });

        onWillStart(async () => {
            this._restoreState();
            await Promise.all([this._loadFormats(), this._loadFormatSettings()]);
        });
    }

    // -- Persistencia local ---------------------------------------------------

    _persistState() {
        try {
            const snap = { ...this.state, loading: false };
            localStorage.setItem(STORAGE_KEY, JSON.stringify(snap));
        } catch (e) {
            /* quota / private mode — ignorar */
        }
    }

    _restoreState() {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            if (!raw) return;
            const saved = JSON.parse(raw);
            Object.assign(this.state, saved, { loading: false });
        } catch (e) {
            /* snapshot corrupto — ignorar */
        }
    }

    // -- Data loaders ---------------------------------------------------------

    async _loadFormats() {
        const result = await this.orm.searchRead(
            "l10n_co.exogenous_format",
            [["active", "=", true]],
            ["id", "code", "name", "apply_concepts"],
            { order: "code" },
        );
        this.state.formats = result;
    }

    async _loadFormatSettings() {
        const companyId = user.activeCompany?.id || user.context?.allowed_company_ids?.[0];
        const domain = [["active", "=", true]];
        if (companyId) {
            domain.push(["company_id", "=", companyId]);
        }
        const result = await this.orm.searchRead(
            "l10n_co.exogenous_format_setting",
            domain,
            ["id", "format_id"],
            { order: "format_id" },
        );
        this.state.formatSettings = result;
    }

    // -- Computed helpers -----------------------------------------------------

    get concepts() {
        return this.state.treeData.filter((n) => n.type === "concept");
    }

    getColumns(conceptId) {
        return this.state.treeData.filter(
            (n) => n.type === "column" && n.concept_id === conceptId,
        );
    }

    isExpandedConcept(conceptId) {
        return !!this.state.expandedConcepts[conceptId];
    }

    isNodeSelected(node) {
        const sel = this.state.selectedNode;
        if (!sel) return false;
        return sel.concept_id === node.concept_id && sel.field_id === node.field_id;
    }

    _findNode(conceptId, fieldId) {
        return this.state.treeData.find(
            (n) => n.type === "column" && n.concept_id === conceptId && n.field_id === fieldId,
        );
    }

    // -- Event handlers -------------------------------------------------------

    onFormatChange(ev) {
        const fid = parseInt(ev.target.value, 10) || null;
        this.state.selectedFormatId = fid;
        const match = this.state.formatSettings.find((fs) => fs.format_id && fs.format_id[0] === fid);
        this.state.selectedSettingId = match ? match.id : null;
        this._persistState();
    }

    onToggleConcept(conceptId) {
        if (!conceptId) return;
        if (this.state.expandedConcepts[conceptId]) {
            delete this.state.expandedConcepts[conceptId];
        } else {
            this.state.expandedConcepts[conceptId] = true;
        }
        this._persistState();
    }

    onExpandAll() {
        const all = {};
        this.concepts.forEach((c) => {
            all[c.concept_id] = true;
        });
        this.state.expandedConcepts = all;
        this._persistState();
    }

    onCollapseAll() {
        this.state.expandedConcepts = {};
        this._persistState();
    }

    onSelectNode(conceptId, fieldId) {
        const node = this._findNode(conceptId, fieldId);
        if (!node) return;
        this.state.selectedNode = node;
        this.state.detailPattern = node.pattern || "";
        this.state.detailNature = node.nature || "db_cr";
        this.state.detailDomain = node.domain || "";
        this.state.detailMoveType = node.move_type || "all";
        this.state.detailTaxFilter = node.tax_filter || "all";
        this._persistState();
    }

    onClosePanel() {
        this.state.selectedNode = null;
        this._persistState();
    }

    onPatternInput(ev) {
        this.state.detailPattern = ev.target.value;
    }

    onNatureChange(ev) {
        this.state.detailNature = ev.target.value;
    }

    onMoveTypeChange(ev) {
        this.state.detailMoveType = ev.target.value;
    }

    onTaxFilterChange(ev) {
        this.state.detailTaxFilter = ev.target.value;
    }

    onDomainInput(ev) {
        this.state.detailDomain = ev.target.value;
    }

    // -- Acciones principales -------------------------------------------------

    async onBuildTree() {
        if (!this.state.selectedFormatId) {
            this.notification.add(_t("Seleccione un formato"), {
                title: _t("Atención"),
                type: "warning",
            });
            return;
        }
        this.state.loading = true;
        try {
            const result = await this.orm.call(
                "l10n_co.exogenous_format_setting",
                "action_concept_plan_tree_owl",
                [this.state.selectedFormatId],
            );
            this.state.treeData = (result && result.tree) || [];
            this.state.kpis = (result && result.kpis) || { ...DEFAULT_KPIS };
            this.state.expandedConcepts = {};
            this.state.selectedNode = null;
            this._persistState();
        } catch (e) {
            this.notification.add(String(e), { title: _t("Error"), type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async _reloadTree() {
        const result = await this.orm.call(
            "l10n_co.exogenous_format_setting",
            "action_concept_plan_tree_owl",
            [this.state.selectedFormatId],
        );
        this.state.treeData = (result && result.tree) || [];
        this.state.kpis = (result && result.kpis) || { ...DEFAULT_KPIS };
        this._persistState();
    }

    async onApplyNodeConfig() {
        const node = this.state.selectedNode;
        if (!node || node.type !== "column") {
            this.notification.add(_t("Seleccione una columna del árbol"), {
                title: _t("Atención"),
                type: "warning",
            });
            return;
        }
        this.state.loading = true;
        try {
            await this.orm.call(
                "l10n_co.exogenous_format_setting",
                "action_apply_concept_node_owl",
                [
                    this.state.selectedFormatId,
                    node.concept_id,
                    node.field_id,
                    {
                        pattern: this.state.detailPattern,
                        nature: this.state.detailNature,
                        domain: this.state.detailDomain,
                        move_type: this.state.detailMoveType,
                        tax_filter: this.state.detailTaxFilter,
                    },
                ],
            );
            this.notification.add(_t("Configuración aplicada"), {
                title: _t("OK"),
                type: "success",
            });
            await this._reloadTree();
        } catch (e) {
            this.notification.add(String(e), { title: _t("Error"), type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async onSuggestAll() {
        if (!this.state.selectedFormatId) return;
        this.state.loading = true;
        try {
            const result = await this.orm.call(
                "l10n_co.exogenous_format_setting",
                "action_suggest_all_patterns_owl",
                [this.state.selectedFormatId],
            );
            this.notification.add(`${result.applied || 0} sugerencias aplicadas`, {
                title: _t("Sugerencias"),
                type: "success",
            });
            await this._reloadTree();
        } catch (e) {
            this.notification.add(String(e), { title: _t("Error"), type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async onLoadAllPatterns() {
        if (!this.state.selectedFormatId) return;
        this.state.loading = true;
        try {
            const result = await this.orm.call(
                "l10n_co.exogenous_format_setting",
                "action_load_all_patterns_owl",
                [this.state.selectedFormatId],
            );
            this.notification.add(`${result.loaded || 0} cuentas cargadas`, {
                title: _t("Cargado"),
                type: "success",
            });
            await this._reloadTree();
        } catch (e) {
            this.notification.add(String(e), { title: _t("Error"), type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async onSyncToSetting() {
        if (!this.state.selectedFormatId || !this.state.selectedSettingId) {
            this.notification.add(_t("Seleccione formato y configuración"), {
                title: _t("Atención"),
                type: "warning",
            });
            return;
        }
        this.state.loading = true;
        try {
            const result = await this.orm.call(
                "l10n_co.exogenous_format_setting",
                "action_sync_plan_to_setting_owl",
                [this.state.selectedFormatId, this.state.selectedSettingId],
            );
            this.notification.add(`${result.synced || 0} líneas sincronizadas`, {
                title: _t("Sincronizado"),
                type: "success",
            });
        } catch (e) {
            this.notification.add(String(e), { title: _t("Error"), type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async onTestDomain() {
        if (!this.state.detailDomain) {
            this.notification.add(_t("Escriba un dominio para probar"), {
                title: _t("Atención"),
                type: "warning",
            });
            return;
        }
        try {
            const result = await this.orm.call(
                "l10n_co.exogenous_format_setting",
                "action_test_domain_owl",
                [this.state.detailDomain],
            );
            this.notification.add(`${result.count || 0} líneas encontradas`, {
                title: _t("Dominio válido"),
                type: "success",
            });
        } catch (e) {
            this.notification.add(String(e), { title: _t("Error"), type: "danger" });
        }
    }
}

registry.category("actions").add("l10n_co_exogenous.concept_plan", ExogenousConceptPlan);
