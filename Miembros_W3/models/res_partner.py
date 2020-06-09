# -*- coding: utf-8 -*-

from odoo import models, fields, api

class Partner(models.Model):
    _inherit = 'res.partner'

    como_contestar = fields.Text('Como Contestar')
    notas_w3 = fields.Text('Indicaciones')
    razon_social  = fields.Char('Razón Social', size=128, required=True)
    ext_w3 = fields.Char('Ext W3')
    codigo_w3 = fields.Char('Código W3')
    fecha_creacion = fields.Date('Ingreso a W3')
    fecha_aniversario = fields.Date('Aniversario/Cumpleaños')
    fecha_constitucion = fields.Date('Constitución de la Empresa')
    vat = fields.Char('NIT')
