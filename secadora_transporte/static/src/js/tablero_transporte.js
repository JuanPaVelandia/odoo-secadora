/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

function filtrosVacios() {
    return {
        fecha_desde: "",
        fecha_hasta: "",
        transportadora_id: "",
        company_id: "",
        pago_flete: "todos",
    };
}

class TableroTransporte extends Component {
    static template = "secadora_transporte.TableroTransporte";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            data: null,
            loading: true,
            filtros: filtrosVacios(),
            expandidas: {},
        });

        onWillStart(async () => {
            await this.loadData();
        });
    }

    _filtrosRpc() {
        const f = this.state.filtros;
        const filtros = {};
        if (f.fecha_desde) filtros.fecha_desde = f.fecha_desde;
        if (f.fecha_hasta) filtros.fecha_hasta = f.fecha_hasta;
        if (f.transportadora_id) filtros.transportadora_id = parseInt(f.transportadora_id, 10);
        if (f.company_id) filtros.company_id = parseInt(f.company_id, 10);
        if (f.pago_flete && f.pago_flete !== "todos") filtros.pago_flete = f.pago_flete;
        return filtros;
    }

    async loadData() {
        this.state.loading = true;
        this.state.data = await this.orm.call(
            "secadora.flete",
            "get_tablero_transporte_data",
            [this._filtrosRpc()],
        );
        this.state.loading = false;
    }

    async onClickLimpiarFiltros() {
        this.state.filtros = filtrosVacios();
        await this.loadData();
    }

    toggleExpandida(transportadoraId) {
        this.state.expandidas[transportadoraId] = !this.state.expandidas[transportadoraId];
    }

    formatMoneda(value) {
        return new Intl.NumberFormat("es-CO", {
            style: "currency",
            currency: "COP",
            maximumFractionDigits: 0,
        }).format(value || 0);
    }

    async onClickVerFletes(transportadoraId) {
        // El dominio viene del backend (fuente única) para que el drill-down
        // coincida con las cifras del tablero; solo se agrega la hoja de la
        // transportadora de la tarjeta (id 0 = sin transportadora).
        const domain = (this.state.data.domain_fletes || []).concat([
            ["transportadora_id", "=", transportadoraId || false],
        ]);
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "Fletes",
            res_model: "secadora.flete",
            views: [[false, "list"], [false, "form"]],
            domain: domain,
            target: "current",
        });
    }

    async onClickVerFactura(facturaId) {
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "account.move",
            res_id: facturaId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async onClickImprimirPorPagar() {
        const f = this.state.filtros;
        const context = {};
        if (f.transportadora_id) {
            context.default_transportadora_id = parseInt(f.transportadora_id, 10);
        }
        if (f.company_id) {
            context.default_company_id = parseInt(f.company_id, 10);
        }
        if (f.fecha_desde) context.default_fecha_desde = f.fecha_desde;
        if (f.fecha_hasta) context.default_fecha_hasta = f.fecha_hasta;
        if (f.pago_flete && f.pago_flete !== "todos") {
            context.default_pago_flete = f.pago_flete;
        }
        await this.action.doAction(
            {
                type: "ir.actions.act_window",
                name: "Imprimir Viajes Facturados por Pagar",
                res_model: "secadora.imprimir.viajes.pagar.wizard",
                views: [[false, "form"]],
                target: "new",
                context: context,
            },
            {
                onClose: async () => {
                    await this.loadData();
                },
            }
        );
    }
}

registry.category("actions").add("secadora_tablero_transporte", TableroTransporte);
