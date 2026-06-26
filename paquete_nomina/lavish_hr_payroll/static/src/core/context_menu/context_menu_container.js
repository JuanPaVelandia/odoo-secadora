/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { ContextMenu } from "./context_menu";

/**
 * Container component that renders the global context menu
 * Registered in main_components registry to be rendered in WebClient
 */
export class ContextMenuContainer extends Component {
    static template = "lavish_hr_payroll.ContextMenuContainer";
    static components = { ContextMenu };
    static props = {};
}

// Register in main_components to render globally in WebClient
registry.category("main_components").add("ContextMenuContainer", {
    Component: ContextMenuContainer,
});
