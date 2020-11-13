# -*- coding: utf-8 -*-

from odoo import models, fields, api

class Partner(models.Model):
	_inherit = 'account.payment'

	detalle_de_documento = fields.Selection([('tarjeta','Tarjeta'),
		('cheque','Cheque'),('deposito_transferencia','Depósito/Transferencia'),
		('efectivo','Efectivo'),('retencion','Retención'),('exencion','Exención'),
		('canje','Canje'),('deposito_en_garantia','Depósito en Garantía'),('otros','Otros'),])
	numero_detalle_documento = fields.Char('No.Documento')