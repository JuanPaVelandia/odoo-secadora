/** @odoo-module **/

import { hrGanttView } from "@hr_gantt/hr_gantt_view";
import { registry } from "@web/core/registry";
import { LavishWorkEntriesGanttController } from "./work_entries_gantt_controller";
import { LavishWorkEntriesGanttModel } from "./work_entries_gantt_model";

const viewRegistry = registry.category("views");

export const lavishWorkEntriesGanttView = {
    ...hrGanttView,
    Controller: LavishWorkEntriesGanttController,
    Model: LavishWorkEntriesGanttModel,
    buttonTemplate: "lavish_hr_work_entry_gantt.WorkEntriesGanttView.Buttons",
};

viewRegistry.add("lavish_work_entries_gantt", lavishWorkEntriesGanttView);
