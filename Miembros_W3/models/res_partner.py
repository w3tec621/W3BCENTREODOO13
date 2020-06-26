# -*- coding: utf-8 -*-

from odoo import models, fields, api

class Partner(models.Model):
    _inherit = 'res.partner'

    como_contestar = fields.Text('Como Contestar')
    notas_w3 = fields.Text('Indicaciones')
    razon_social  = fields.Char('Razón Social', size=128, required=True)
    ext_w3 = fields.Char('Ext W3')
    codigo_w3 = fields.Char('Código W3')
    fecha_creacion = fields.Date('Fecha de Creación')
    fecha_aniversario = fields.Date('Fecha de Aniversario')
    fecha_constitucion = fields.Date('Fecha de Constitución')