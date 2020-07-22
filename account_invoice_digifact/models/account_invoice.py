# -*- coding: utf-8 -*-

import random

import datetime
import uuid

from odoo import fields, models, api
from odoo.exceptions import UserError
from odoo.addons.account_invoice_digifact import numero_a_texto

import requests
from xml.dom import minidom
from lxml import etree as ET
from xml.etree import ElementTree
from xml.etree.ElementTree import Element, SubElement
import base64

class AccountInvoice(models.Model):
    _inherit = 'account.move'

    uuid_fel = fields.Char(string='No. Factura', readonly=True, default=0, copy=False,
                           states={'draft': [('readonly', False)]}, help='UUID returned by certifier')  # No. Invoice
    fel_serie = fields.Char(string='Serie Fel', readonly=True, states={'draft': [('readonly', False)]}, copy=False,
                            help='Raw Serial number return by GFACE or FEL provider')  # Fel Series
    fel_no = fields.Char(string='Fel No.', readonly=True, states={'draft': [('readonly', False)]}, copy=False,
                         help='Raw Serial number return by GFACE or FEL provider')
    uuid = fields.Char(string='UUID', readonly=True, states={'draft': [('readonly', False)]}, copy=False,
                       help='UUID given to the certifier to register the document')
    no_acceso = fields.Char(string='Numero de Acceso', readonly=True, states={'draft': [('readonly', False)]},
                            copy=False, help='Electronic singnature given sent to FEL')  # Access Number
    frase_ids = fields.Many2many('satdte.frases', 'inv_frases_rel', 'inv_id', 'frases_id', 'Frases')

    factura_cambiaria = fields.Boolean('Factura Cambiaria', related='journal_id.factura_cambiaria', readonly=True)
    number_of_payments = fields.Integer('Cantidad De Abonos', default=1, copy=False, help='Number Of Payments')
    frecuencia_de_vencimiento = fields.Integer('Frecuencia De Vencimiento', copy=False, help='Due date frequency (calendar days)')
    megaprint_payment_lines = fields.One2many('megaprint.payment.line', 'invoice_id', 'Payment Info', copy=False)
    xml_request = fields.Text(string='XML Request', readonly=True, states={'draft': [('readonly', False)]}, copy=False)
    xml_response = fields.Text(string='XML Response', readonly=True, states={'draft': [('readonly', False)]}, copy=False)
    xml_notes = fields.Text('XML Children')
    uuid_refund = fields.Char('UUID a rectificar')
    txt_filename = fields.Char('Archivo', required=False, readonly=True)
    file = fields.Binary('Archivo', required=False, readonly=True)

    def calculate_payment_info(self):
        for inv in self:
            if inv.journal_id.factura_cambiaria and inv.number_of_payments and inv.frecuencia_de_vencimiento and inv.invoice_date:
                inv.megaprint_payment_lines.unlink()  # Delete Old Payment Lines
                amount = inv.amount_total / inv.number_of_payments
                new_date = None
                for i in range(inv.number_of_payments):
                    if not new_date:
                        new_date = datetime.datetime.strptime(str(inv.invoice_date), '%Y-%m-%d').date() + datetime.timedelta(days=inv.frecuencia_de_vencimiento)
                    else:
                        new_date = new_date + datetime.timedelta(days=inv.frecuencia_de_vencimiento)
                    self.env['megaprint.payment.line'].create({
                        'invoice_id': inv.id,
                        'serial_no': i + 1,
                        'amount': amount,
                        'due_date': new_date.strftime('%Y-%m-%d')
                    })
    
    def generate_xml(self):
        megaprint_dateformat = "%Y-%m-%dT%H:%M:%S"
        fecha_str = ""
        no_lin = 1
        AdendaSummary = []
        Complemento_Data = {}
        _items = []
        total_impuesto = 0

        gran_total = 0

        # Generate 9 digit random number as a Access Number
        no_acceso = str(random.randint(100000000, 999999999))
        while True:
            acceso = self.env['account.move'].search_count([('no_acceso', '=', no_acceso)])
            if acceso > 0:
                no_acceso = str(random.randint(100000000, 999999999))
            else:
                break

        # Current time For the tag FechaHoraEmision
        fecha = fields.Datetime.context_timestamp(self.with_context(tz=self.env.user.tz), datetime.datetime.now())
        if fecha:
            fecha_str = str(fecha.strftime(megaprint_dateformat))
        
        if self.name:
            AdendaSummary.append({'REFERENCIA_INTERNA': self.name})
            #AdendaSummary.append(self.name)
        AdendaSummary.append({'FECHA_REFERENCIA': fecha_str})
        AdendaSummary.append({'VALIDAR_REFERENCIA_INTERNA': 'NO_VALIDAR'})
        for inv_line in self.invoice_line_ids:
            detail = []
            if inv_line.product_id.type == 'service':
                bien_servicio = 'S'
            else:
                bien_servicio = 'B'

            total_price = inv_line.price_unit * inv_line.quantity
            discount = total_price * ((inv_line.discount or 0.0) / 100.0)
            # grabable = total_price - discount
            grabable = round(((total_price - discount) / 1.12),2)
            MontoImp = round((total_price - discount - grabable),2)
            total_impuesto += MontoImp
            total = grabable + MontoImp
            gran_total += total
            descripcion_not = inv_line.name
            #AdendaSummary.append(inv_line.name)

            #if str(inv_line.uom_id.name):
            uom = "UNI"
            #else:
            #    uom = inv_line.uom_id.name
            #    uom = uom.encode('utf-8')

            for tax in inv_line.tax_ids:
                if tax.name[0:3] == "IVA":
                    iva_grabable = str(grabable)
                    iva_qty = str(inv_line.quantity)
                    iva = str(total_price - grabable)
                    #if inv_line.price_tax:
                    #    iva = str(inv_line.price_tax)
                    # iva = '''<dte:Impuestos><dte:Impuesto><dte:NombreCorto>IVA</dte:NombreCorto><dte:CodigoUnidadGravable>1</dte:CodigoUnidadGravable><dte:MontoGravable>'''+grabable+'''</dte:MontoGravable><dte:CantidadUnidadesGravables>'''+str(inv_line.quantity)+'''</dte:CantidadUnidadesGravables><dte:MontoImpuesto>'''+str(inv_line.price_tax)+'''</dte:MontoImpuesto></dte:Impuesto></dte:Impuestos>'''

            detail.append(bien_servicio)  # Product Type
            detail.append(no_lin)  # Line number
            no_lin += 1
            detail.append(inv_line.quantity)  # Product Quantity
            detail.append(uom)  # Unit Of Measure
            detail.append(descripcion_not)  # Product description
            detail.append(inv_line.price_unit)  # Price of the product
            detail.append(total_price)  # Total Price
            detail.append(discount)  # Product Discount
            # IVA info
            detail.append(round(grabable, 2))
            detail.append(inv_line.quantity)  # Product Quantity
            detail.append(round(MontoImp, 2))
            detail.append(round(total, 2))
            _items.append(detail)

        total_impuesto = round(total_impuesto, 2)
        gran_total = round(gran_total, 2)

        codeEstab = self.journal_id.codigo_est or ''  # Company Establishment Code
        afIVA = self.company_id.regimen_iva or 'GEN'  # Company Associated VAT regime OR 'GEN'(Default)
        correoEmisor = self.company_id.email or ''  # Company Email
        nitEmisor = self.company_id.vat  # Compant vat No
        nombreComercial = self.company_id.nombre_comercial or ''  # Company Tradename
        nombreRec = ""
        calleRec = ""
        DatosCliente = False
        nombreEmisor = self.company_id.name or ''  # Company Name
        # Company Address Details
        if self.company_id.street:
            calleEmisor = self.company_id.street or ''
        else:
            calleEmisor = ""
        if self.company_id.street2:
            calleEmisor = calleEmisor + ' ' + self.company_id.street2 or ''
        if self.company_id.city:
            municipioEmisor = self.company_id.city or ''
        else:
            municipioEmisor = ''
        if self.company_id.state_id:
            departamentoEmisor = self.company_id.state_id.name or ''
        else:
            departamentoEmisor = ""
        if self.company_id.zip:
            postalEmisor = self.company_id.zip
        else:
            postalEmisor = ""
        if self.company_id.country_id.code:
            paisEmisor = self.company_id.country_id.code or ''
        else:
            paisEmisor = ""
        # Partner Details
        #if not self.partner_id.vat or self.partner_id.var != "CF":
        #DatosCliente = self.get_datos_cliente(nitEmisor, self.partner_id.vat)
        if self.partner_id.email:
            correoRec = self.partner_id.email
        else:
            correoRec = ""
        if self.partner_id.vat:
            vatRec = self.partner_id.vat
            #if self.partner_id.var == 'CF':
        elif self.partner_id.vat == 'EXPORT':
            vatRec = "EXPORT"
        elif self.partner_id.vat == "CF":
            vatRec = "CF"
        else:
            vatRec = "CF"
        if self.partner_id.name:   
            nombreRec = self.partner_id.name        
        if self.partner_id.street:
            calleRec = self.partner_id.street
        else:
            calleRec = ""
        if self.partner_id.street2:
            calleRec = calleRec + ' ' + self.partner_id.street2
        if self.partner_id.city:
            municipioRec = self.partner_id.city
        else:
            municipioRec = ""
        if self.partner_id.state_id:
            departamentoRec = self.partner_id.state_id.name
        else:
            departamentoRec = ""
        if self.partner_id.zip:
            postalRec = self.partner_id.zip
        else:
            postalRec = ""
        if self.partner_id.country_id:
            paisRec = self.partner_id.country_id.code
        else:
            paisRec = ""

        fases_lines = []  # Frase Information
        for frase in self.frase_ids:
            fases_lines.append([frase.codigo_escenario, frase.tipo_frase])
        if not fases_lines:
            fases_lines = [[1, 1]]

        # currency = self.currency_id.name
        currency = self.currency_id.name or 'GTQ'

        uuid_txt = uuid.uuid4()
        self.uuid = uuid_txt

        Complemento_Data['origin_date'] = str(self.invoice_date)
        Complemento_Data['auth_number_doc_origin'] = str(self.uuid)

        if self.type in ['out_invoice', 'in_invoice']:
            if self.journal_id.factura_cambiaria:  # Cambiaria Invoice
                res_xml = self.GenerateXML_FCAM(currency, fecha_str, no_acceso, "FCAM", afIVA, codeEstab, correoEmisor, nitEmisor, nombreComercial,
                                      nombreEmisor, calleEmisor, postalEmisor, municipioEmisor, departamentoEmisor, paisEmisor, correoRec,
                                      vatRec, nombreRec, calleRec, postalRec, municipioRec, departamentoRec, paisRec, fases_lines,
                                      _items, total_impuesto, gran_total, uuid_txt, Complemento_Data, AdendaSummary)
                self.xml_request = res_xml
            else:  # Normal Invoice
                res_xml = self.GenerateXML_FACT(currency, fecha_str, no_acceso, "FACT", afIVA, codeEstab, correoEmisor, nitEmisor, nombreComercial,
                                      nombreEmisor, calleEmisor, postalEmisor, municipioEmisor, departamentoEmisor, paisEmisor, correoRec,
                                      vatRec, nombreRec, calleRec, postalRec, municipioRec, departamentoRec, paisRec, fases_lines,
                                      _items, total_impuesto, gran_total, uuid_txt, AdendaSummary)
                self.xml_request = res_xml

        if self.type in ['out_refund', 'in_refund']:  # Credit Note
            Complemento_Data['auth_number_doc_origin'] = str(self.uuid_refund)
            res_xml = self.GenerateXML_NCRE(currency, fecha_str, no_acceso, "NCRE", afIVA, codeEstab, correoEmisor, nitEmisor, nombreComercial,
                                  nombreEmisor, calleEmisor, postalEmisor, municipioEmisor, departamentoEmisor, paisEmisor, correoRec,
                                  vatRec, nombreRec, calleRec, postalRec, municipioRec, departamentoRec, paisRec, fases_lines,
                                  _items, total_impuesto, gran_total, uuid_txt, Complemento_Data, AdendaSummary)
            #self.send_appfirma(res_xml)
            self.xml_request = res_xml
        # return super(AccountInvoice, self).action_invoice_open()

    def action_post(self):
        res = super(AccountInvoice, self).action_post()
        if self.type in ('out_invoice', 'out_refund') and self.journal_id.is_fel == True:
            self.generate_xml()
        return res
AccountInvoice()
        
class MegaprintPaymentLine(models.Model):
    _name = 'megaprint.payment.line'
    _description = 'Megaprint Payment Line'
    _order = 'serial_no'

    invoice_id = fields.Many2one('account.move', 'Inovice')
    serial_no = fields.Integer('#No', readonly=True)
    amount = fields.Float('Monto', readonly=True, help='Amount')
    due_date = fields.Date('Vencimiento', readonly=True, help='Due Date')

MegaprintPaymentLine()