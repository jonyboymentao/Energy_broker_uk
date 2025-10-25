# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class CustomerSite(models.Model):
    _name = 'customer.site'
    _description = 'Customer Energy Site'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Site Name', required=True, tracking=True)
    partner_id = fields.Many2one('res.partner', string='Customer', required=True, tracking=True)
    lead_id = fields.Many2one('crm.lead', string='Lead/Opportunity', tracking=True)

    street = fields.Char()
    street2 = fields.Char()
    city = fields.Char()
    state_id = fields.Many2one('res.country.state', string='State')
    zip = fields.Char()
    country_id = fields.Many2one('res.country', string='Country')

    meter_type = fields.Selection([
        ('hh', 'Half-Hourly'),
        ('nhh', 'Non-Half-Hourly'),
        ('gas', 'Gas'),
    ], string='Meter Type', required=True)
    mpan_mprn = fields.Char(string='MPAN/MPRN')
    current_supplier_id = fields.Many2one('res.partner', string='Current Supplier', domain=[('supplier_rank', '>', 0)])
    contract_end_date = fields.Date(string='Current Contract End')
    annual_usage_kwh = fields.Float(string='Annual Usage (kWh)')
    kva = fields.Float(string='kVA (HH only)')

    @api.constrains('mpan_mprn', 'meter_type')
    def _check_mpan_mprn(self):
        for rec in self:
            if not rec.mpan_mprn:
                continue
            val = rec.mpan_mprn.replace(' ', '')
            if rec.meter_type in ('hh', 'nhh'):
                if not val.isdigit() or len(val) != 13:
                    raise ValidationError(_('Electricity MPAN core must be 13 digits.'))
                weights = [3, 7, 1] * 4
                total = sum(int(d) * w for d, w in zip(val[:12], weights))
                check = total % 10
                if check != int(val[12]):
                    raise ValidationError(_('Invalid MPAN check digit.'))
            else:
                if not val.isdigit() or not (6 <= len(val) <= 11):
                    raise ValidationError(_('Gas MPRN must be 6 to 11 digits.'))
