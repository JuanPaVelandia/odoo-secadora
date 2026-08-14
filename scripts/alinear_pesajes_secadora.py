"""Devuelve a la Secadora los pesajes que quedaron en otra empresa.

La báscula es de la Secadora La Gran Colombia, así que todo pesaje debería
pertenecerle. Unos pocos se registraron mientras el usuario tenía otra empresa
activa en pantalla y heredaron esa, lo que después provoca errores de acceso al
abrirlos con una sola empresa seleccionada.

Por defecto solo simula. Con --aplicar escribe los cambios.

    python3 alinear_pesajes_secadora.py            # simulacro
    python3 alinear_pesajes_secadora.py --aplicar  # de verdad
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
        pesajes = env['secadora.pesaje'].search([
            ('company_id', '!=', CIA_SECADORA),
        ])
        if not pesajes:
            print('No hay pesajes fuera de la Secadora.')
            return

        print(f'{"pesaje":<12}{"empresa actual":<32}{"OS":<10}{"estado":<14}')
        print('-' * 70)
        for p in pesajes:
            print(f'{p.name:<12}{(p.company_id.name or "-")[:31]:<32}'
                  f'{(p.orden_servicio_id.name or "-"):<10}{p.state:<14}')

        print(f'\nTotal a mover a la Secadora: {len(pesajes)}')

        if not aplicar:
            print('\nSIMULACRO: no se escribio nada. Use --aplicar.')
            cr.rollback()
            return

        pesajes.write({'company_id': CIA_SECADORA})
        cr.commit()
        print(f'\nLISTO: {len(pesajes)} pesajes movidos a la Secadora.')


if __name__ == '__main__':
    main()
