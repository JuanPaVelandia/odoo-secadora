/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { SplitScreen } from "./split_screen";

/**
 * Container component that renders the split screen UI
 * Registered in main_components registry to be rendered in WebClient
 */
export class SplitScreenContainer extends Component {
    static template = "lavish_hr_payroll.SplitScreenContainer";
    static components = { SplitScreen };
    static props = {};
}

// Register in main_components to render globally in WebClient
registry.category("main_components").add("SplitScreenContainer", {
    Component: SplitScreenContainer,
});
