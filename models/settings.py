# -*- coding: utf-8 -*-
from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    uplift_default_p_per_kwh = fields.Float(string='Default Uplift (p/kWh)', config_parameter='energy_broker_uk.default_uplift_p_per_kwh')
    tender_default_suppliers_ids = fields.Many2many('res.partner', string='Default Tender Suppliers', domain=['|', ('is_energy_supplier', '=', True), ('supplier_rank', '>', 0)])
    comparison_disclaimer = fields.Char(string='Comparison Disclaimer', config_parameter='energy_broker_uk.comparison_disclaimer')

    energy_monitoring_api_url = fields.Char(string='Energy Monitoring API URL', config_parameter='energy_broker_uk.energy_monitoring_api_url')
    energy_monitoring_api_key = fields.Char(string='Energy Monitoring API Key', config_parameter='energy_broker_uk.energy_monitoring_api_key')

    jellyfish_api_base_url = fields.Char(string='Jellyfish API Base URL', config_parameter='energy_broker_uk.jellyfish_api_base_url')
    jellyfish_api_key = fields.Char(string='Jellyfish API Key', config_parameter='energy_broker_uk.jellyfish_api_key')

    loa_sign_template_id = fields.Many2one('sign.template', string='LOA Sign Template', config_parameter='energy_broker_uk.loa_sign_template_id')
    contract_sign_template_id = fields.Many2one('sign.template', string='Contract Sign Template', config_parameter='energy_broker_uk.contract_sign_template_id')

    max_uplift_p_per_kwh = fields.Float(string='Max Uplift (p/kWh)', config_parameter='energy_broker_uk.max_uplift_p_per_kwh')

    # Optional: Documents folder integration can be added after the Documents app is installed

    def get_values(self):
        res = super().get_values()
        ICP = self.env['ir.config_parameter'].sudo()
        ids_csv = ICP.get_param('energy_broker_uk.tender_default_suppliers_ids') or ''
        ids = [int(x) for x in ids_csv.split(',') if x.strip().isdigit()]
        res.update(tender_default_suppliers_ids=[(6, 0, ids)])
        return res

    def set_values(self):
        super().set_values()
        ICP = self.env['ir.config_parameter'].sudo()
        ids = self.tender_default_suppliers_ids.ids if self.tender_default_suppliers_ids else []
        ICP.set_param('energy_broker_uk.tender_default_suppliers_ids', ','.join(str(i) for i in ids))
