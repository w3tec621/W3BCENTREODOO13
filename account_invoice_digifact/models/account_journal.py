# -*- coding: utf-8 -*-

from odoo import models, fields


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    factura_cambiaria = fields.Boolean('Factura Cambiaria')
    is_fel = fields.Boolean('¿Activar FEL?', required=False, default=False)
    codigo_est = fields.Char(string='Codigo Establecimiento', help='Número del establecimiento donde se emite el documento. Es el que aparece asignado por SAT en sus registros.')

AccountJournal()