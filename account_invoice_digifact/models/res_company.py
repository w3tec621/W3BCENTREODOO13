# -*- coding: utf-8 -*-

from odoo import fields, models
import requests
import json
import dateutil.parser
from odoo.exceptions import UserError

class ResCompany(models.Model):
    _inherit = 'res.company'

    regimen_iva = fields.Char(string='Regimen asociado de IVA', help='Regimen asociado de IVA en Guatemala. Iniciales necearias para comunicacion con FEL. En caso de duda, referirse a documentacion oficial de la Superintendencia de Administracion Tributaria.')
    codigo_est = fields.Char(string='Codigo Establecimiento', help='Número del establecimiento donde se emite el documento. Es el que aparece asignado por SAT en sus registros.')
    nombre_est = fields.Char(string='Nombre de Establecimiento', help='Nombre o abreviatura Número del establecimiento donde se emite el documento. Es el que aparece asignado por SAT en sus registros.')
    nombre_comercial = fields.Char(string='Nombre Comercial', help='Indica el nombre comercial del establecimiento (de acuerdo a los registros tributarios) donde se emite el documento.')
    #Credentials DigiFact
    username = fields.Char('Usuario')
    password = fields.Char('Contraseña')
    request_id = fields.Char('IDRequest')
    #Token Access Digifact
    token_access = fields.Text('Token')
    date_due = fields.Date('Expira')
    company_nit = fields.Char('Nit Autorizado')
    url_token = fields.Text('Url Token', default="https://felgttestaws.digifact.com.gt/felapi/api/login/get_token")
    url_request = fields.Text('Url Firmado', default="https://felgttestaws.digifact.com.gt/felapi/api/FELRequest")
    url_cancel = fields.Text('Url Anulacion', default="https://felgttestaws.digifact.com.gt/felapi/api/FELRequest")

    def action_get_token(self):
        for rec in self:
            post_url = rec.url_token
            headers = {
                "Content-type": "application/json"
            }
            if not rec.vat:
                raise UserError(('La empresa %s no tiene numero de NIT parametrizado') %(rec.name))
            nit = self.generate_nit(rec.vat)
            res = {
                "Username": "%s.%s.%s" %("GT", nit, rec.username),
                "Password": rec.password,
            } 
            try:
                response  = requests.post(post_url, data=json.dumps(res), headers=headers, stream=True, verify=False)
                if response.status_code == 200:
                    json_str = json.loads(response.content.decode("utf-8"))
                    rec.write({
                        'token_access': json_str.get('Token', False),
                        'date_due': dateutil.parser.parse(str(json_str.get('expira_en', False))).date(),
                        'company_nit': json_str.get('otorgado_a', False),
                    })
            except Exception as e:
                raise UserError(('%s') %(e))
        return True
    
    def generate_nit(self, nit):
        qty_zero = ""
        res_nit = ""
        if nit:
            leght_nit = len(nit)
            if leght_nit < 12:
                diff = 12 - leght_nit
                while diff > 0:
                    qty_zero += "0"
                    diff -= 1
            res_nit = str(qty_zero) + str(nit)
        return res_nit

ResCompany()