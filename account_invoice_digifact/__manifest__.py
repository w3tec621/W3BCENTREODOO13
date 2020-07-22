# -*- coding: utf-8 -*-

{
    'name': 'Account Invoice FEL -DigiFact',
    'version': '1.0.1',
    'author': 'Xetechs, S.A.',
    'website': 'https://www.xetechs.com', 
    'support': 'Luis Aquino --> laquino@xetechs.com', 
    'category': 'Accounting',
    'depends': ['account'],
    'summary': 'Transfer Invoice To MegaPrint And Receive Certificate',
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'views/account_invoice.xml',
        'views/res_company_view.xml',
        'views/satdte_frases.xml',
        'views/account_journal_views.xml',
        'views/satdte_frases_data.xml',
        'wizard/wizard_cancel_view.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'auto_install': False,
}
