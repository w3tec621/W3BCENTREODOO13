# -*- coding: utf-8 -*-

import random

import datetime
import uuid

from odoo import fields, models, api
from odoo.exceptions import UserError, Warning
from odoo.addons.account_invoice_digifact import numero_a_texto

import requests
import json
from xml.dom import minidom
import xml.etree.ElementTree as ET
from xml.etree import ElementTree
from xml.etree.ElementTree import Element, SubElement
import base64
from odoo.tools.translate import _

import os  

import logging

_logger = logging.getLogger( __name__ )

class AccountInvoice(models.Model):
    _inherit = 'account.move'

    uuid_fel = fields.Char(string='No. Factura', readonly=True, default=0, copy=False,
                           states={'draft': [('readonly', False)]}, help='UUID returned by certifier')  # No. Invoice
    fel_serie = fields.Char(string='Serie', readonly=True, states={'draft': [('readonly', False)]}, copy=False,
                            help='Raw Serial number return by GFACE or FEL provider')  # Fel Series
    fel_no = fields.Char(string='Numero.', readonly=True, states={'draft': [('readonly', False)]}, copy=False,
                         help='Raw Serial number return by GFACE or FEL provider')
    fel_date = fields.Char(string='Fecha DTE.', readonly=True, states={'draft': [('readonly', False)]}, copy=False,
                         help='Raw date return by GFACE or FEL provider')
    fel_received_sat = fields.Char(string='Acuse Recibo SAT', readonly=True, states={'draft': [('readonly', False)]}, copy=False)
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
    uuid_refund = fields.Char('UUID a rectificar', related="invoice_refund_id.uuid")
    txt_filename = fields.Char('Archivo', required=False, readonly=True, copy=False)
    file = fields.Binary('Archivo', required=False, readonly=True, copy=False)
    txt_filename_xml = fields.Char('Archivo XML', required=False, readonly=True, copy=False)
    file_xml = fields.Binary('Archivo XML', required=False, readonly=True, copy=False)
    invoice_refund_id = fields.Many2one('account.move', 'Invoice Refund', required=False, readonly=False)
    #FEL Cancel
    be_cancel = fields.Boolean('DTE Anulado', default=False)
    fel_codes_cancel = fields.Char(string='Codigos SAT', readonly=True, copy=False)
    fel_cancel_sat = fields.Char(string='Acuse Anulacion SAT', readonly=True, copy=False)
    txt_filename_cancel = fields.Char('Archivo XML Anulacion', required=False, readonly=True, copy=False)
    file_cancel = fields.Binary('Archivo XML Anulacion', required=False, readonly=True, copy=False)
    is_fel = fields.Boolean('FEL', related="journal_id.is_fel")


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
        item_no = 0
        dte = {}
        adenda = []
        complement_data = []
        complement = {}
        details = []
        details_taxes = []
        details_total_taxes = []
        frases_lines = []
        total_taxes = 0.00
        for inv in self:
            access_number = str(random.randint(100000000, 999999999))
            while True:
                access_count = self.env['account.move'].search_count([('no_acceso', '=', access_number)])
                if access_count > 0:
                    access_number = str(random.randint(100000000, 999999999))
                else:
                    break
            dte['access_number'] = access_number
            date_dte = fields.Datetime.context_timestamp(self.with_context(tz=self.env.user.tz), datetime.datetime.now())
            dte['date_dte'] = date_dte.strftime(megaprint_dateformat)
            #Adenda DTE
            if inv.name:
                adenda.append({'REFERENCIA_INTERNA': self.name})
            adenda.append({'FECHA_REFERENCIA': date_dte.strftime(megaprint_dateformat)})
            adenda.append({'VALIDAR_REFERENCIA_INTERNA': 'NO_VALIDAR'})
            dte['adenda'] = adenda
            #Tipo Documento DTE
            if inv.type in ['out_invoice', 'in_invoice']:
                if inv.journal_id.factura_cambiaria == True:
                    dte['tipo'] = 'FCAM'
                else:
                    dte['tipo'] = 'FACT'
            #Frases del DTE
            #if not frases_lines:
            #    frases_lines = [[1, 1]]
            if self.frase_ids:
                for frase in self.frase_ids:
                    frases_lines.append([frase.codigo_escenario, frase.tipo_frase])
            else:
                frases_lines = [[1, 1]]
            #Datos emisor
            dte['frases'] = frases_lines
            dte['moneda'] = inv.currency_id.name or 'GTQ'
            dte['establecimiento'] = inv.journal_id.codigo_est
            dte['regimeniva']  = inv.company_id.regimen_iva
            dte['correoemisor'] = inv.company_id.email
            dte['nitemisor'] = inv.company_id.vat
            dte['nombrecomercial'] = inv.company_id.nombre_comercial
            dte['nombreemisor'] = inv.company_id.name
            dte['calleemisor'] = inv.company_id.street + ' ' + inv.company_id.street2 if inv.company_id.street and inv.company_id.street2 else ''
            dte['municipioemisor'] = inv.company_id.city or ''
            dte['departamentoemisor'] = inv.company_id.state_id.name or ''
            dte['postalemisor'] = inv.company_id.zip or ''
            dte['paisemisor'] = inv.company_id.country_id.code or ''
            #Datos Receptor
            dte['correoreceptor'] = inv.partner_id.email or ''
            dte['nitreceptor'] = inv.partner_id.vat or 'CF'
            dte['nombrereceptor'] = inv.partner_id.name
            dte['callereceptor'] = inv.partner_id.street + ' ' + inv.partner_id.street2 if inv.partner_id.street and inv.partner_id.street2 else ''
            dte['municipiorecptor'] = inv.partner_id.city or ''
            dte['departamentoreceptor'] = inv.partner_id.state_id.name
            dte['postalreceptor'] = inv.partner_id.zip or ''
            dte['paisreceptor'] = inv.partner_id.country_id.code
            #Nota de Credito complementos
            if inv.type in ['out_refund', 'in_refund']:  # Credit Note
                complement['auth_number_doc_origin'] = inv.uuid_refund
                complement['origin_date'] = str(inv.invoice_refund_id.invoice_date)
                complement['reference'] = inv.ref or ""
                complement['doc_numero_origin'] = inv.invoice_refund_id.fel_no
                complement['doc_serie_origin'] = inv.invoice_refund_id.fel_serie
                #complement_data.append(complement)
                dte['complementos'] = complement
                dte['tipo'] = 'NCRE'
            #Items de la factura
            for line in inv.invoice_line_ids:
                #Variables x item
                item = {}
                tax_line = {}
                details_taxes = []
                subtotal_taxes = 0.00
                item_no += 1
                price_unit = line.price_unit
                discount_unit = (line.price_unit * (line.discount / 100))
                taxes_unit = line.tax_ids.compute_all((price_unit - discount_unit), inv.currency_id, 1.00, line.product_id, inv.partner_id)
                taxes = line.tax_ids.compute_all((price_unit - discount_unit), inv.currency_id, line.quantity, line.product_id, inv.partner_id)
                print(taxes)
                #Taxes calculted
                item['grabable'] = str(round(taxes.get('total_included', 0.00), 2))
                item['subtotal'] = str(round(taxes.get('total_included', 0.00), 2))
                item['descuento'] = str(round((discount_unit * line.quantity), 2))
                item['cantidad'] = str(line.quantity)
                item['descripcion'] = str(line.name)
                item['preciounitario'] = str(round(taxes_unit.get('total_included', 0.00),2))
                item['uom'] = 'UNI'
                item['line'] = str(item_no)
                item['tipoitem'] = 'S' if line.product_id.type == 'service' else 'B'
                for tax in taxes.get('taxes', False):
                    tax_name = ""
                    subtotal_taxes += round(tax.get('amount', 0.00), 2)
                    total_taxes += subtotal_taxes
                    if tax.get('name', '')[0:3] == "IVA":
                        tax_name = 'IVA'
                    else:
                        tax_name = tax.get('name', '')
                    tax_line = {
                        'base': str(round(tax.get('base', 0.00), 2)),
                        'tax': str(round(tax.get('amount', 0.00), 2)),
                        'tax_name': tax_name,
                        'quantity': str(line.quantity),
                    }
                    details_taxes.append(tax_line)
                    details_total_taxes.append(tax_line)
                item['itemsimpuestos'] = details_taxes
                item['subtotalimpuestos'] = str(round(subtotal_taxes, 2))
                details.append(item)
            dte['items'] = details
            dte['itemimpuestos'] = str(details_total_taxes)
            dte['totalimpuestos'] = str(round(total_taxes, 2))
            dte['total'] = str(round(inv.amount_total, 2))
        return dte

    def generate_xml_old(self):
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
            uom = "UNI"
            for tax in inv_line.tax_ids:
                if tax.name[0:3] == "IVA":
                    iva_grabable = str(grabable)
                    iva_qty = str(inv_line.quantity)
                    iva = str(total_price - grabable)
            detail.append(bien_servicio)  # Product Type
            detail.append(no_lin)  # Line number
            no_lin += 1
            detail.append(inv_line.quantity)  # Product Quantity
            detail.append(uom)  # Unit Of Measure
            detail.append(descripcion_not)  # Product description
            detail.append(inv_line.price_unit)  # Price of the product
            detail.append(total_price)  # Total Price
            detail.append(discount)  # Product Discount
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
        #Datos Receptor
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
                self.post_dte(res_xml)
            else:  # Normal Invoice
                res_xml = self.GenerateXML_FACT(currency, fecha_str, no_acceso, "FACT", afIVA, codeEstab, correoEmisor, nitEmisor, nombreComercial,
                                      nombreEmisor, calleEmisor, postalEmisor, municipioEmisor, departamentoEmisor, paisEmisor, correoRec,
                                      vatRec, nombreRec, calleRec, postalRec, municipioRec, departamentoRec, paisRec, fases_lines,
                                      _items, total_impuesto, gran_total, uuid_txt, AdendaSummary)
                self.xml_request = res_xml
                self.post_dte(res_xml)
        if self.type in ['out_refund', 'in_refund']:  # Credit Note
            Complemento_Data['auth_number_doc_origin'] = str(self.uuid_refund)
            Complemento_Data['origin_date'] = str(self.invoice_refund_id.invoice_date)
            Complemento_Data['reference'] = str(self.ref)
            Complemento_Data['doc_numero_origin'] = str(self.invoice_refund_id.fel_no)
            Complemento_Data['doc_serie_origin'] = str(self.invoice_refund_id.fel_serie)
            res_xml = self.GenerateXML_NCRE(currency, fecha_str, no_acceso, "NCRE", afIVA, codeEstab, correoEmisor, nitEmisor, nombreComercial,
                                  nombreEmisor, calleEmisor, postalEmisor, municipioEmisor, departamentoEmisor, paisEmisor, correoRec,
                                  vatRec, nombreRec, calleRec, postalRec, municipioRec, departamentoRec, paisRec, fases_lines,
                                  _items, total_impuesto, gran_total, uuid_txt, Complemento_Data, AdendaSummary)
            self.xml_request = res_xml
            self.post_dte(res_xml)

    def action_post(self):
        xml = False
        res = super(AccountInvoice, self).action_post()
        if self.journal_id.is_fel == True:
            result = self.generate_xml()
            if self.type in ['out_invoice', 'in_invoice'] and self.journal_id.factura_cambiaria == False:
                xml = self.GenerateXML_FACT(result)
                _logger.info(xml.decode('utf-8'))
                #raise UserError(('%s') %(xml.decode('utf-8')))
                #print(str(xml.decode('iso-8859-15').encode('utf8')))
            elif self.type in ['out_refund', 'in_refund']:
                xml = self.GenerateXML_NCRE(result)
            self.post_dte(str(xml.decode('iso-8859-15')))
        return res
    
    def post_dte(self, xml_dte):
        if xml_dte:
            if not self.company_id.url_request:
                raise UserError(('Para la compañia %s no hay url de firmado configurado.!') %(self.company_id.name))
            post_url = self.company_id.url_request
            nit = self.company_id.company_nit
            if not self.company_id.token_access:
                raise UserError(('Para la compañia %s no hay token de acceso generado.!') %(self.company_id.name))
            headers = {
                'Content-Type': 'application/xml; charset=utf-8',
                'Authorization': self.company_id.token_access
            }
            params = {
                'NIT': nit,
                'TIPO': 'CERTIFICATE_DTE_XML_TOSIGN',
                'FORMAT': 'XML,PDF'
            }
            response = {}
            try:
                #raise UserError(('%s') %(type(xml_dte)))
                response  = requests.post(post_url, data=str(xml_dte), params=params, headers=headers, stream=True, verify=False)
            except Exception as e:
                raise Warning(('%s') %(e))
            if response and response.status_code == 200:
                _logger.info(response)
                json_res = json.loads(response.content.decode("utf-8"))
                self.write({
                    'xml_request': xml_dte.encode('iso-8859-15').decode('utf-8'),
                    'xml_response': json_res,
                    'fel_serie': json_res.get('Serie', ''),
                    'fel_no': json_res.get('NUMERO', ''),
                    'uuid': json_res.get('Autorizacion', ''),
                    'fel_date': json_res.get('Fecha_DTE', ''),
                    'fel_received_sat': json_res.get('AcuseReciboSAT', ''),
                    'txt_filename': "%s.pdf" %(json_res.get('Autorizacion', '')),
                    'file': base64.decodebytes(base64.b64encode(str(json_res.get('ResponseDATA3', '')).encode('utf-8'))),
                    'txt_filename_xml': "%s.xml" %(json_res.get('Autorizacion', '')),
                    'file_xml': base64.decodebytes(base64.b64encode(str(json_res.get('ResponseDATA1', '')).encode('utf-8'))),
                })
            elif response.status_code != 200:
                _logger.info(response.status_code)
                _logger.info(response.content.decode("utf-8"))
                json_res = json.loads(response.content.decode("utf-8"))
                msg = ""
                errors = json_res.get('ResponseDATA1', '')
                for item in errors.split('\n'):
                    msg += item + '\n'
                raise Warning(('%s') %(msg))

    def generate_xml_cancel(self):
        megaprint_dateformat = "%Y-%m-%dT%H:%M:%S"
        xml_str = ""
        for rec in self:
            try:
                GTAnulacionDocumento = Element('dte:GTAnulacionDocumento')
                GTAnulacionDocumento.set('xmlns:dte', 'http://www.sat.gob.gt/dte/fel/0.1.0')
                GTAnulacionDocumento.set('xmlns:xsi', 'http://www.w3.org/2001/XMLSchema-instance')
                GTAnulacionDocumento.set('Version', '0.1')
                sat = SubElement(GTAnulacionDocumento, 'dte:SAT')
                AnulacionDTE = SubElement(sat, 'dte:AnulacionDTE')
                AnulacionDTE.set('ID', 'DatosCertificados')
                DatosGenerales = SubElement(AnulacionDTE, 'dte:DatosGenerales')
                DatosGenerales.set('ID', 'DatosAnulacion')
                DatosGenerales.set('NumeroDocumentoAAnular', str(rec.uuid))
                DatosGenerales.set('NITEmisor', str(rec.company_id.vat))
                DatosGenerales.set('IDReceptor', str(rec.partner_id.vat))
                DatosGenerales.set('FechaEmisionDocumentoAnular', str(rec.fel_date))
                #DatosGenerales.set('FechaHoraAnulacion', str(rec.fel_date))
                date_fel = fields.Datetime.context_timestamp(self.with_context(tz=self.env.user.tz), datetime.datetime.now())
                DatosGenerales.set('FechaHoraAnulacion', str(date_fel.strftime(megaprint_dateformat)))
                DatosGenerales.set('MotivoAnulacion', str(rec.narration))
                #To XML to String
                rough_string = ET.tostring(GTAnulacionDocumento)
                reparsed = minidom.parseString(rough_string)
                xml_str = reparsed.toprettyxml(indent="  ", encoding="utf-8")
            except Exception as e:
                raise UserError(('%s') %(e))
            finally:
                return xml_str
    
    def action_cancel_fel(self):
        view = self.env.ref('account_invoice_digifact.wizard_cancel_fel')
        new_id = self.env['wizard.fel.cancel']
        for rec in self:
            vals = {
                'invoice_id': rec.id or False,
            }
            view_id = new_id.create(vals)
            return {
                'name': _("Anulacion FEL"),
                'view_mode': 'form',
                'view_id': view.id,
                'res_id': view_id.id,
                'view_type': 'form',
                'res_model': 'wizard.fel.cancel',
                'type': 'ir.actions.act_window',
                'target': 'new',
            }

    def post_cancel_dte(self, xml_dte):
        if xml_dte:
            if not self.company_id.url_cancel:
                raise UserError(('Para la compañia %s no hay url de anulacion configurado.!') %(self.company_id.name))
            post_url = self.company_id.url_cancel
            nit = self.company_id.company_nit
            if not self.company_id.token_access:
                raise UserError(('Para la compañia %s no hay token de acceso generado.!') %(self.company_id.name))
            headers = {
                'Content-Type': 'application/xml',
                'Authorization': self.company_id.token_access
            }
            params = {
                'NIT': nit,
                'TIPO': 'ANULAR_FEL_TOSIGN',
                'FORMAT': 'XML'
            }
            response = {}
            try:
                response  = requests.post(post_url, data=xml_dte, params=params, headers=headers, stream=True, verify=False)
            except Exception as e:
                raise Warning(('%s') %(e))
            if response and response.status_code == 200:
                json_res = json.loads(response.content.decode("utf-8"))
                self.write({
                    'be_cancel': True,
                    'fel_codes_cancel': json_res.get('CodigosSAT', ''),
                    'fel_cancel_sat': json_res.get('AcuseReciboSAT', ''),
                    'txt_filename_cancel': "Anulacion-%s.xml" %(json_res.get('Autorizacion', '')),
                    'file_cancel': base64.decodebytes(base64.b64encode(str(json_res.get('ResponseDATA1', '')).encode('utf-8'))),
                })
            elif response.status_code != 200:
                json_res = json.loads(response.content.decode("utf-8"))
                msg = ""
                errors = json_res.get('ResponseDATA1', '')
                for item in errors.split('\n'):
                    msg += item + '\n'
                raise Warning(('%s') %(msg))


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

class AccountMoveReversal(models.TransientModel):
    _inherit = 'account.move.reversal'

    def reverse_moves(self):
        moves = self.move_id or self.env['account.move'].browse(self._context['active_ids'])

        # Create default values.
        default_values_list = []
        for move in moves:
            default_values_list.append({
                'ref': _('Reversal of: %s, %s') % (move.name, self.reason) if self.reason else _('Reversal of: %s') % (move.name),
                'date': self.date or move.date,
                'invoice_date': move.is_invoice(include_receipts=True) and (self.date or move.date) or False,
                'journal_id': self.journal_id and self.journal_id.id or move.journal_id.id,
                'invoice_refund_id': move.id or False,
            })

        # Handle reverse method.
        if self.refund_method == 'cancel' or (moves and moves[0].type == 'entry'):
            new_moves = moves._reverse_moves(default_values_list, cancel=True)
        elif self.refund_method == 'modify':
            new_moves = moves._reverse_moves(default_values_list, cancel=True)
            moves_vals_list = []
            for move in moves.with_context(include_business_fields=True):
                moves_vals_list.append(move.copy_data({
                    'invoice_payment_ref': move.name,
                    'date': self.date or move.date,
                })[0])
            new_moves = moves.create(moves_vals_list)
        elif self.refund_method == 'refund':
            new_moves = moves._reverse_moves(default_values_list)
        else:
            return

        # Create action.
        action = {
            'name': _('Reverse Moves'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
        }
        if len(new_moves) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': new_moves.id,
            })
        else:
            action.update({
                'view_mode': 'tree,form',
                'domain': [('id', 'in', new_moves.ids)],
            })
        return action

AccountMoveReversal()