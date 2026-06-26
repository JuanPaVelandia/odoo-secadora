from odoo.addons.hr_org_chart.controllers.hr_org_chart import HrOrgChartController
from odoo.http import request, route


class HrOrgChartControllerLavish(HrOrgChartController):
    """v19 core bug: get_org_chart compara ancestors (hr.employee.public) con
    current_parent (hr.employee) y v19 lanza TypeError al comparar recordsets
    de modelos distintos. Coercionamos ancestors al modelo del employee."""

    @route('/hr/get_org_chart', type='jsonrpc', auth='user')
    def get_org_chart(self, employee_id, new_parent_id=None, **kw):
        employee = self._get_employee(employee_id, **kw)
        new_parent = self._get_employee(new_parent_id, **kw).sudo()
        if not employee:
            return {'managers': [], 'children': []}

        EmployeeModel = employee._name
        ancestors, current = request.env[EmployeeModel].sudo(), employee.sudo()
        current_parent = new_parent if new_parent_id is not None else current.parent_id
        max_level = (kw.get('context')['max_level'] or self._managers_level) + 1
        # Comparamos por id para evitar TypeError en v19 cuando parent_id de
        # hr.employee.public ha sido redefinido para apuntar a hr.employee
        # (lavish_hr_employee/models/hr_employee.py:1730).
        while current_parent and current.id != current_parent.id and employee.id != current_parent.id and len(ancestors) < max_level:
            current = current_parent
            current_parent = current.parent_id if current.id != employee.id or not new_parent else new_parent
            if current_parent.id in ancestors.ids:
                break
            ancestors += request.env[EmployeeModel].sudo().browse(current.id) if current._name != EmployeeModel else current

        values = dict(
            self=self._prepare_employee_data(employee),
            managers=[
                self._prepare_employee_data(ancestor)
                for idx, ancestor in enumerate(ancestors)
                if idx < max_level - 1
            ],
            managers_more=len(ancestors) > self._managers_level,
            children=[self._prepare_employee_data(child) for child in employee.child_ids if child.id != employee.id],
        )
        values['managers'].reverse()
        return values
