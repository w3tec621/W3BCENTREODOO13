# -*- coding: utf-8 -*-

##############################################################################
#
#    OpenERP, Open Source Management Solution
#    This module copyright (C) 2020 Miguel Fuentes Gomez
#    (<http://www.addetec.com>).
#
##############################################################################

{
    'name': "Miembros W3BCentre",
    'version': '13.0.1.0.0',
    'author': 'Miguel Fuentes Addetec.com',
    'maintainer': 'Addetec',
    'website': 'http://www.addetec.com',
    'category': 'sale',
    'license': 'AGPL-3',
    'summary': """ """,
    'description': """ """,
    'depends': ['sale'],
    'data': [
        'views/res_partner_view.xml',
        'views/sale_order_view.xml',  
    ],    
    'installable': True,
    'application': True,
    'demo': [],
    'test': []
}
