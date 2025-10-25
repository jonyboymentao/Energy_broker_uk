# -*- coding: utf-8 -*-
from odoo import models, fields


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_energy_supplier = fields.Boolean(string='Energy Supplier')
    tender_email = fields.Char(string='Tender Email')
    default_uplift_p_per_kwh = fields.Float(string='Default Uplift (p/kWh)')
    is_commission_customer = fields.Boolean(string='Commission Customer', help='Suppliers pay us commission; mark as customer for invoicing purposes.')

    def action_mark_energy_supplier(self):
        for rec in self:
            rec.is_energy_supplier = True
            # Ensure they are considered a supplier in Odoo
            if rec.supplier_rank < 1:
                rec.supplier_rank = 1

    def action_unmark_energy_supplier(self):
        for rec in self:
            rec.is_energy_supplier = False
