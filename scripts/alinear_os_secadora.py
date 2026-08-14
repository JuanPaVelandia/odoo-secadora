"""Pasa OS-0008 y todo lo que cuelga de ella a la Secadora.

Los pesajes ya se alinearon a la Secadora, pero OS-0008 seguía en la empresa de
Jose Eduardo y 12 pesajes apuntaban a ella. Se mueve la orden junto con sus
registros de bultos y sus movimientos: dejarlos atrás rompería el inventario de
la bodega, que dejaría de verse desde la Secadora.

El cliente de la orden no cambia; solo cambia qué empresa presta el servicio.

    python3 alinear_os_secadora.py            # simulacro
    python3 alinear_os_secadora.py --aplicar  # de verdad
"""
import sys

sys.path.insert(0, '/opt/odoo19/odoo')
import odoo
from odoo.api import Environment

BASE = 'secadora_2'
CIA_SECADORA = 1


def main():
    aplicar = '--aplicar' in sys.argv
    odoo.tools.config.parse_config(['-c', '/etc/odoo19.conf'])
    reg = odoo.modules.registry.Registry(BASE)

    with reg.cursor() as cr:
        env = Environment(cr, odoo.SUPERUSER_ID, {
            'allowed_company_ids': [1, 2, 3, 4],
        })
        ordenes = env['secadora.orden.servicio'].search([
            ('company_id', '!=', CIA_SECADORA),
        ])
        if not ordenes:
            print('No hay ordenes fuera de la Secadora.')
            return

        for o in ordenes:
            bultos = env['secadora.registro.bultos'].search([
                ('orden_id', '=', o.id),
            ])
            movs = env['secadora.movimiento.bultos'].search([
                ('registro_bultos_id', 'in', bultos.ids),
            ])
            print(f'{o.name}: {o.company_id.name} -> Secadora  '
                  f'(estado={o.state}, factura={o.factura_id.name or "ninguna"})')
            print(f'   registros de bultos: {len(bultos)}')
            print(f'   movimientos        : {len(movs)}')

            if aplicar:
                o.company_id = CIA_SECADORA
                if bultos:
                    bultos.write({'company_id': CIA_SECADORA})
                if movs:
                    movs.write({'company_id': CIA_SECADORA})

        if not aplicar:
            print('\nSIMULACRO: no se escribio nada. Use --aplicar.')
            cr.rollback()
            return

        cr.commit()
        print('\nLISTO: ordenes, bultos y movimientos movidos a la Secadora.')


if __name__ == '__main__':
    main()
