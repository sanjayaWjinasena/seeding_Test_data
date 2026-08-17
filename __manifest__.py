# -*- coding: utf-8 -*-
{
    'name': 'Seeding - Test Data',
    'version': '17.0.0.0.1',
    'summary': (
        'Seeds minimum accounting scaffold from Clear-DB reference '
        'onto the dev env so Repair automations can be tested E2E'
    ),
    'author': 'Jinasena Agricultural Machinery (Pvt) Ltd.',
    'category': 'Accounting',
    'license': 'LGPL-3',
    'depends': ['account', 'sale', 'stock'],
    'data': [
        'security/ir.model.access.csv',
    ],
    'post_init_hook': 'seed_accounting_scaffold',
    'installable': True,
    'auto_install': False,
    'application': False,
}
