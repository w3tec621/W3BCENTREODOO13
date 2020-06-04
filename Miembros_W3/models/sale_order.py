# -*- coding: utf-8 -*-

from odoo import models, fields, api

class Partner(models.Model):
    _inherit = 'sale.order'

    terminos_condiciones_w3 = fields.Selection([('oficina_virtual', 'Oficina Virtual'),('oficina_ejecutiva', 'Oficina Ejecutiva'),
    	('sala_reuniones', 'Sala de Reuniones'),('sala_capacitaciones', 'Sala de Capacitaciones'),('focus_group', 'Focus Group'),('estandar', 'Estandar')])