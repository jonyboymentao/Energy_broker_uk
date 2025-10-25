# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ProductProduct(models.Model):
    _inherit = 'product.product'

    is_energy_meter = fields.Boolean(string='Is Energy Meter')
    meter_type = fields.Selection([
        ('hh', 'Half-Hourly Electricity'),
        ('nhh', 'Non-Half-Hourly Electricity'),
        ('gas', 'Gas'),
    ], string='Meter Type')
    # Identifiers
    mpan_mprn = fields.Char(string='MPAN/MPRN')
    mpan_core = fields.Char(string='MPAN Core (13)')
    mprn = fields.Char(string='MPRN')

    # Electricity attributes
    profile_class = fields.Char(string='Profile Class')
    mtc = fields.Char(string='Meter Time Switch (MTC)')
    llfc = fields.Char(string='Line Loss Factor (LLFC)')
    kva = fields.Float(string='KVA (HH only)')
    read_type = fields.Selection([
        ('amr', 'AMR'),
        ('smets', 'SMETS'),
        ('manual', 'Manual'),
        ('hh', 'Half-Hourly'),
    ], string='Read Type')
    gsp = fields.Char(string='GSP/Distribution ID')

    # Gas attributes
    aq_kwh = fields.Float(string='Annual Quantity (kWh)')
    meter_pressure = fields.Char(string='Meter Pressure')

    # Common/site
    default_annual_usage_kwh = fields.Float(string='Default Annual Usage (kWh)')
    supply_address = fields.Char(string='Supply Address')
    postcode = fields.Char(string='Postcode')
    site_name = fields.Char(string='Site Name')
    current_supplier_id = fields.Many2one('res.partner', string='Current Supplier', domain=[('supplier_rank', '>', 0)])
    contract_end_date = fields.Date(string='Current Contract End')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('is_energy_meter'):
                vals.setdefault('type', 'service')
                if 'default_code' in self._fields:
                    if vals.get('mpan_mprn') and not vals.get('default_code'):
                        vals['default_code'] = vals['mpan_mprn']
                    elif vals.get('default_code') and not vals.get('mpan_mprn'):
                        vals['mpan_mprn'] = vals['default_code']
        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        for rec in self:
            if rec.is_energy_meter:
                if 'type' in rec._fields and rec.type != 'service':
                    rec.type = 'service'
                if 'default_code' in rec._fields:
                    if rec.mpan_mprn and not rec.default_code:
                        rec.default_code = rec.mpan_mprn
                    elif rec.default_code and not rec.mpan_mprn:
                        rec.mpan_mprn = rec.default_code
        return res

    @api.onchange('default_code')
    def _onchange_default_code_sync_mpan_tmpl(self):
        for rec in self:
            if rec.default_code and not rec.mpan_mprn:
                rec.mpan_mprn = rec.default_code

    @api.onchange('mpan_mprn')
    def _onchange_mpan_sync_default_code_tmpl(self):
        for rec in self:
            if rec.mpan_mprn and not rec.default_code:
                rec.default_code = rec.mpan_mprn

    @api.onchange('default_code')
    def _onchange_default_code_sync_mpan(self):
        for rec in self:
            if rec.default_code and not rec.mpan_mprn:
                rec.mpan_mprn = rec.default_code

    @api.onchange('mpan_mprn')
    def _onchange_mpan_sync_default_code(self):
        for rec in self:
            if rec.mpan_mprn and not rec.default_code:
                rec.default_code = rec.mpan_mprn


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_energy_meter = fields.Boolean(string='Is Energy Meter')
    meter_type = fields.Selection([
        ('hh', 'Half-Hourly Electricity'),
        ('nhh', 'Non-Half-Hourly Electricity'),
        ('gas', 'Gas'),
    ], string='Meter Type')
    # Identifiers
    mpan_mprn = fields.Char(string='MPAN/MPRN')
    mpan_core = fields.Char(string='MPAN Core (13)')
    mprn = fields.Char(string='MPRN')

    # Electricity attributes
    profile_class = fields.Char(string='Profile Class')
    mtc = fields.Char(string='Meter Time Switch (MTC)')
    llfc = fields.Char(string='Line Loss Factor (LLFC)')
    kva = fields.Float(string='KVA (HH only)')
    read_type = fields.Selection([
        ('amr', 'AMR'),
        ('smets', 'SMETS'),
        ('manual', 'Manual'),
        ('hh', 'Half-Hourly'),
    ], string='Read Type')
    gsp = fields.Char(string='GSP/Distribution ID')

    # Gas attributes
    aq_kwh = fields.Float(string='Annual Quantity (kWh)')
    meter_pressure = fields.Char(string='Meter Pressure')

    # Common/site
    default_annual_usage_kwh = fields.Float(string='Default Annual Usage (kWh)')
    supply_address = fields.Char(string='Supply Address')
    postcode = fields.Char(string='Postcode')
    site_name = fields.Char(string='Site Name')
    current_supplier_id = fields.Many2one('res.partner', string='Current Supplier', domain=[('supplier_rank', '>', 0)])
    contract_end_date = fields.Date(string='Current Contract End')
