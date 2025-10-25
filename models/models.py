# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from dateutil.relativedelta import relativedelta
import requests
import json
import base64
import io
import csv


class CustomerLoa(models.Model):
    _name = 'customer.loa'
    _description = 'Letter of Authority'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Reference', default=lambda self: _('New'), copy=False, readonly=True)
    partner_id = fields.Many2one('res.partner', string='Customer', required=True, tracking=True)
    lead_id = fields.Many2one('crm.lead', string='Lead/Opportunity', tracking=True)
    issue_date = fields.Date(string='Issue Date', default=fields.Date.context_today, tracking=True)
    expiry_date = fields.Date(string='Expiry Date', compute='_compute_expiry_date', store=True)
    status = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('signed', 'Signed'),
        ('valid', 'Valid'),
        ('expired', 'Expired'),
    ], default='draft', tracking=True)
    pdf_attachment_id = fields.Many2one('ir.attachment', string='LOA PDF')
    sign_request_id = fields.Many2one('sign.request', string='Signature Request')

    price_request_ids = fields.One2many('supplier.price.request', 'loa_id', string='Price Requests')
    price_request_count = fields.Integer(compute='_compute_price_request_count', string='Tenders Count')

    @api.depends('issue_date')
    def _compute_expiry_date(self):
        for rec in self:
            rec.expiry_date = rec.issue_date and (rec.issue_date + relativedelta(months=12)) or False

    @api.depends('price_request_ids')
    def _compute_price_request_count(self):
        for rec in self:
            rec.price_request_count = len(rec.price_request_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                seq = self.env['ir.sequence'].next_by_code('customer.loa') or _('New')
                partner_name = ''
                if vals.get('partner_id'):
                    partner = self.env['res.partner'].browse(vals['partner_id'])
                    partner_name = partner.display_name
                vals['name'] = ('%s - %s' % (seq, partner_name)) if partner_name else seq
        return super().create(vals_list)

    def action_send_for_signature(self):
        for rec in self:
            rec.status = 'sent'
            if rec.partner_id and rec.partner_id.email:
                subject = _('Letter of Authority for %s') % (rec.partner_id.display_name,)
                body = _('<p>Please review and sign the attached Letter of Authority.</p>')
                vals = {
                    'subject': subject,
                    'body_html': body,
                    'email_to': rec.partner_id.email,
                }
                if rec.pdf_attachment_id:
                    vals['attachment_ids'] = [(4, rec.pdf_attachment_id.id)]
                mail = self.env['mail.mail'].create(vals)
                try:
                    mail.send()
                except Exception:
                    pass

    def action_fetch_jellyfish_prices(self):
        for rec in self:
            ICP = self.env['ir.config_parameter'].sudo()
            base_url = ICP.get_param('energy_broker_uk.jellyfish_api_base_url')
            api_key = ICP.get_param('energy_broker_uk.jellyfish_api_key')
            if not base_url or not api_key:
                raise ValidationError(_('Please configure Jellyfish API Base URL and Key in Energy Settings.'))
            payload = {
                'customer': rec.partner_id and rec.partner_id.display_name,
                'meters': []
            }
            for line in rec.line_ids:
                payload['meters'].append({
                    'identifier': line.mpan_mprn,
                    'type': line.meter_type or '',
                    'annual_usage_kwh': line.annual_usage_kwh or 0.0,
                    'supply_address': line.supply_address or '',
                })
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            }
            try:
                resp = requests.post(base_url.rstrip('/') + '/pricing/quotes', data=json.dumps(payload), headers=headers, timeout=30)
            except Exception as e:
                raise ValidationError(_('Failed to reach Jellyfish API: %s') % e)
            # Attach request payload for traceability
            attachment = self.env['ir.attachment'].create({
                'name': f'jellyfish_request_{rec.name}.json',
                'type': 'binary',
                'datas': base64.b64encode(json.dumps(payload, indent=2).encode('utf-8')),
                'res_model': rec._name,
                'res_id': rec.id,
                'mimetype': 'application/json',
            })
            rec.attachment_ids = [(4, attachment.id)]
            # Attach response payload
            att2 = self.env['ir.attachment'].create({
                'name': f'jellyfish_response_{rec.name}.json',
                'type': 'binary',
                'datas': base64.b64encode(resp.text.encode('utf-8')),
                'res_model': rec._name,
                'res_id': rec.id,
                'mimetype': 'application/json',
            })
            rec.attachment_ids = [(4, att2.id)]
            # Ensure supplier record exists for traceability
            partner = self.env['res.partner'].search([('name', '=', 'Jellyfish Energy')], limit=1)
            if not partner:
                partner = self.env['res.partner'].create({'name': 'Jellyfish Energy', 'is_energy_supplier': True, 'supplier_rank': 1})
            self.env['supplier.price.response'].create({
                'request_id': rec.id,
                'partner_id': partner.id,
                'notes': _('Jellyfish API response attached as JSON. Please review and map rates.'),
            })

    def _get_latest_jellyfish_response_json(self):
        self.ensure_one()
        atts = self.attachment_ids.filtered(lambda a: a.name and a.name.startswith('jellyfish_response_') and a.mimetype == 'application/json')
        if not atts:
            # search globally if not linked in many2many
            atts = self.env['ir.attachment'].search([
                ('res_model', '=', self._name),
                ('res_id', '=', self.id),
                ('name', 'ilike', 'jellyfish_response_'),
                ('mimetype', '=', 'application/json')
            ], order='id desc', limit=1)
        else:
            atts = atts.sorted(key=lambda a: a.id, reverse=True)[0]
        if not atts:
            return None
        data = base64.b64decode(atts.datas or b'{}').decode('utf-8')
        try:
            return json.loads(data)
        except Exception:
            return None

    def action_map_jellyfish_offers(self):
        for req in self:
            data = req._get_latest_jellyfish_response_json()
            if not data:
                raise ValidationError(_('No Jellyfish JSON response attachment found to map.'))
            partner = self.env['res.partner'].search([('name', '=', 'Jellyfish Energy')], limit=1)
            if not partner:
                partner = self.env['res.partner'].create({'name': 'Jellyfish Energy', 'is_energy_supplier': True, 'supplier_rank': 1})
            response = self.env['supplier.price.response'].create({
                'request_id': req.id,
                'partner_id': partner.id,
                'lead_id': req.lead_id.id,
                'notes': _('Auto-mapped from Jellyfish API response.'),
            })
            # try common shapes: {'offers': [...]}, {'quotes': [...]}, or list
            offers = []
            if isinstance(data, dict):
                for key in ('offers', 'quotes', 'results'):
                    if key in data and isinstance(data[key], list):
                        offers = data[key]
                        break
            elif isinstance(data, list):
                offers = data
            # build index by identifier
            lines_by_identifier = {l.mpan_mprn.replace(' ', ''): l for l in req.line_ids if l.mpan_mprn}
            for item in offers:
                try:
                    ident = (item.get('identifier') or item.get('mpan') or item.get('mprn') or '').replace(' ', '')
                    req_line = lines_by_identifier.get(ident)
                    if not req_line:
                        continue
                    term_years = item.get('term_years') or (item.get('term_months') and int(item.get('term_months')/12)) or 1
                    unit_rate = item.get('unit_rate_p_per_kwh') or item.get('unit_rate_ppkwh') or item.get('unit_rate')
                    standing = item.get('standing_charge_gbp_per_day') or item.get('standing_charge_per_day') or item.get('standing')
                    self.env['supplier.price.response.line'].create({
                        'response_id': response.id,
                        'request_line_id': req_line.id,
                        'unit_rate_p_per_kwh': float(unit_rate or 0.0),
                        'standing_charge_gbp_per_day': float(standing or 0.0),
                        'contract_term_years': int(term_years or 1),
                    })
                except Exception:
                    continue

    def action_send_customer_quote(self):
        for rec in self:
            if not rec.partner_id or not rec.partner_id.email:
                raise ValidationError(_('Customer email is required to send quotation.'))
            report = self.env.ref('energy_broker_uk.action_supplier_price_request_report')
            pdf = report._render_qweb_pdf([rec.id])[0]
            attachment = self.env['ir.attachment'].create({
                'name': f"{rec.name}_comparison.pdf",
                'type': 'binary',
                'datas': base64.b64encode(pdf),
                'res_model': rec._name,
                'res_id': rec.id,
                'mimetype': 'application/pdf',
            })
            mail = self.env['mail.mail'].create({
                'subject': _('Energy Pricing Comparison: %s') % (rec.name,),
                'body_html': _('<p>Please find attached your energy pricing comparison.</p>'),
                'email_to': rec.partner_id.email,
                'attachment_ids': [(4, attachment.id)],
            })
            try:
                mail.send()
            except Exception:
                pass

    def action_fetch_jellyfish_prices(self):
        for rec in self:
            ICP = self.env['ir.config_parameter'].sudo()
            base_url = ICP.get_param('energy_broker_uk.jellyfish_api_base_url')
            api_key = ICP.get_param('energy_broker_uk.jellyfish_api_key')
            if not base_url or not api_key:
                raise ValidationError(_('Please configure Jellyfish API Base URL and Key in Energy Settings.'))
            payload = {
                'customer': rec.partner_id and rec.partner_id.display_name,
                'meters': []
            }
            for line in rec.line_ids:
                payload['meters'].append({
                    'identifier': line.mpan_mprn,
                    'type': line.meter_type or '',
                    'annual_usage_kwh': line.annual_usage_kwh or 0.0,
                    'supply_address': line.supply_address or '',
                })
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            }
            try:
                resp = requests.post(base_url.rstrip('/') + '/pricing/quotes', data=json.dumps(payload), headers=headers, timeout=30)
            except Exception as e:
                raise ValidationError(_('Failed to reach Jellyfish API: %s') % e)
            attachment = self.env['ir.attachment'].create({
                'name': f'jellyfish_request_{rec.name}.json',
                'type': 'binary',
                'datas': base64.b64encode(json.dumps(payload, indent=2).encode('utf-8')),
                'res_model': rec._name,
                'res_id': rec.id,
                'mimetype': 'application/json',
            })
            rec.attachment_ids = [(4, attachment.id)]
            att2 = self.env['ir.attachment'].create({
                'name': f'jellyfish_response_{rec.name}.json',
                'type': 'binary',
                'datas': base64.b64encode(resp.text.encode('utf-8')),
                'res_model': rec._name,
                'res_id': rec.id,
                'mimetype': 'application/json',
            })
            rec.attachment_ids = [(4, att2.id)]
            partner = self.env['res.partner'].search([('name', '=', 'Jellyfish Energy')], limit=1)
            if not partner:
                partner = self.env['res.partner'].create({'name': 'Jellyfish Energy', 'is_energy_supplier': True, 'supplier_rank': 1})
            self.env['supplier.price.response'].create({
                'request_id': rec.id,
                'partner_id': partner.id,
                'notes': _('Jellyfish API response attached as JSON. Please review and map rates.'),
            })

    

    def name_get(self):
        result = []
        for rec in self:
            parts = [rec.name or '']
            if rec.partner_id:
                parts.append(rec.partner_id.display_name)
            result.append((rec.id, ' - '.join(p for p in parts if p)))
        return result

    def action_mark_signed(self):
        for rec in self:
            rec.status = 'signed'

    def action_validate(self):
        for rec in self:
            if rec.expiry_date and rec.expiry_date < fields.Date.today():
                raise ValidationError(_('Cannot validate an expired LOA'))
            rec.status = 'valid'

    def name_get(self):
        result = []
        for rec in self:
            parts = [rec.name or '']
            if rec.partner_id:
                parts.append(rec.partner_id.display_name)
            result.append((rec.id, ' - '.join(p for p in parts if p)))
        return result

    def cron_update_loa_status(self):
        today = fields.Date.today()
        expired = self.search([('expiry_date', '<', today), ('status', '!=', 'expired')])
        for rec in expired:
            rec.status = 'expired'


class SupplierPriceRequest(models.Model):
    _name = 'supplier.price.request'
    _description = 'Supplier Price Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(default=lambda self: _('New'), copy=False, readonly=True)
    loa_id = fields.Many2one('customer.loa', string='LOA', required=True, tracking=True)
    lead_id = fields.Many2one('crm.lead', string='Lead/Opportunity', tracking=True)
    partner_id = fields.Many2one('res.partner', string='Customer', related='loa_id.partner_id', store=True, readonly=True)
    supplier_ids = fields.Many2many(
        'res.partner',
        string='Target Suppliers',
        domain=['|', ('is_energy_supplier', '=', True), ('supplier_rank', '>', 0)]
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'Sent'),
    ], default='draft', tracking=True)

    line_ids = fields.One2many('supplier.price.request.line', 'request_id', string='Meters')
    attachment_ids = fields.Many2many('ir.attachment', string='Attachments')

    contract_id = fields.Many2one('customer.contract', string='Contract')
    can_create_contract = fields.Boolean(compute='_compute_can_create_contract')

    @api.depends('line_ids', 'line_ids.annual_usage_kwh')
    def _compute_can_create_contract(self):
        for rec in self:
            rec.can_create_contract = bool(rec.line_ids)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if rec.name == _('New') or rec.name.startswith(_('New')):
                seq = self.env['ir.sequence'].next_by_code('supplier.price.request') or _('New')
                partner_name = rec.partner_id.display_name if rec.partner_id else (rec.loa_id.partner_id.display_name if rec.loa_id else '')
                rec.name = ('%s - %s' % (seq, partner_name)) if partner_name else seq
        return records

    def action_send(self):
        for rec in self:
            if not rec.loa_id or rec.loa_id.status != 'valid' or (rec.loa_id.expiry_date and rec.loa_id.expiry_date < fields.Date.today()):
                raise ValidationError(_('LOA must be Valid and not expired before sending a price request.'))
            if rec.name == _('New'):
                rec.name = self.env['ir.sequence'].next_by_code('supplier.price.request') or _('New')
            rec.state = 'sent'

    @api.onchange('loa_id')
    def _onchange_loa(self):
        for rec in self:
            if rec.loa_id:
                rec.lead_id = rec.loa_id.lead_id
                if not rec.supplier_ids:
                    ICP = self.env['ir.config_parameter'].sudo()
                    ids_csv = ICP.get_param('energy_broker_uk.tender_default_suppliers_ids') or ''
                    ids = [int(x) for x in ids_csv.split(',') if x.strip().isdigit()]
                    if ids:
                        rec.supplier_ids = [(6, 0, ids)]

    def action_send_tender_emails(self):
        for rec in self:
            if not rec.supplier_ids:
                raise ValidationError(_('Please select at least one supplier.'))
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(['MPAN/MPRN', 'Annual Usage (kWh)', 'Current Supplier', 'Contract End', 'Meter Type', 'Supply Address'])
            for line in rec.line_ids:
                writer.writerow([
                    line.mpan_mprn or '',
                    line.annual_usage_kwh or 0.0,
                    line.current_supplier_id.display_name if line.current_supplier_id else '',
                    line.contract_end_date or '',
                    line.meter_type or '',
                    line.supply_address or '',
                ])
            data = base64.b64encode(buf.getvalue().encode('utf-8'))
            attachment = self.env['ir.attachment'].create({
                'name': f"tender_{rec.name}.csv",
                'type': 'binary',
                'datas': data,
                'res_model': rec._name,
                'res_id': rec.id,
                'mimetype': 'text/csv',
            })
            subject = _('Tender Request: %s') % (rec.name,)
            body = _('<p>Please find attached the meter list for tendering.</p>')
            for supplier in rec.supplier_ids:
                email = supplier.tender_email or supplier.email
                if not email:
                    continue
                mail = self.env['mail.mail'].create({
                    'subject': subject,
                    'body_html': body,
                    'email_to': email,
                    'attachment_ids': [(4, attachment.id)],
                })
                try:
                    mail.send()
                except Exception:
                    pass


class SupplierPriceRequestLine(models.Model):
    _name = 'supplier.price.request.line'
    _description = 'Supplier Price Request Line'

    request_id = fields.Many2one('supplier.price.request', string='Request', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Meter Product')
    mpan_mprn = fields.Char(string='MPAN/MPRN')
    annual_usage_kwh = fields.Float(string='Annual Usage (kWh)')
    current_supplier_id = fields.Many2one('res.partner', string='Current Supplier', domain=[('supplier_rank', '>', 0)])
    contract_end_date = fields.Date(string='Current Contract End')
    meter_type = fields.Selection([
        ('hh', 'Half-Hourly'),
        ('nhh', 'Non-Half-Hourly'),
    ], string='Meter Type')
    supply_address = fields.Char(string='Supply Address')

    @api.onchange('product_id')
    def _onchange_product_fill_meter(self):
        for rec in self:
            if rec.product_id and getattr(rec.product_id, 'is_energy_meter', False):
                rec.mpan_mprn = rec.product_id.mpan_mprn or rec.mpan_mprn
                rec.annual_usage_kwh = rec.product_id.default_annual_usage_kwh or rec.annual_usage_kwh
                if rec.product_id.meter_type in ('hh', 'nhh'):
                    rec.meter_type = rec.product_id.meter_type
                elif rec.product_id.meter_type == 'gas':
                    rec.meter_type = 'gas'
                rec.supply_address = rec.product_id.supply_address or rec.supply_address

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


class SupplierPriceResponse(models.Model):
    _name = 'supplier.price.response'
    _description = 'Supplier Price Response'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(default=lambda self: _('New'), copy=False, readonly=True)
    request_id = fields.Many2one('supplier.price.request', string='Price Request', required=True, ondelete='cascade')
    lead_id = fields.Many2one('crm.lead', string='Lead/Opportunity', tracking=True)
    partner_id = fields.Many2one('res.partner', string='Supplier', domain=[('supplier_rank', '>', 0)], required=True)
    line_ids = fields.One2many('supplier.price.response.line', 'response_id', string='Response Lines')
    attachment_ids = fields.Many2many('ir.attachment', string='Quote Attachments')
    notes = fields.Text(string='Notes')

    total_annual_cost = fields.Monetary(string='Total Annual Cost', compute='_compute_total', currency_field='currency_id', store=True)
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id.id)
    is_best_offer = fields.Boolean(string='Best Offer')

    @api.depends('line_ids', 'line_ids.annual_cost')
    def _compute_total(self):
        for rec in self:
            rec.total_annual_cost = sum(rec.line_ids.mapped('annual_cost'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('supplier.price.response') or _('New')
        return super().create(vals_list)

    @api.onchange('request_id')
    def _onchange_request(self):
        for rec in self:
            if rec.request_id:
                rec.lead_id = rec.request_id.lead_id or rec.request_id.loa_id.lead_id


class SupplierPriceResponseLine(models.Model):
    _name = 'supplier.price.response.line'
    _description = 'Supplier Price Response Line'

    response_id = fields.Many2one('supplier.price.response', string='Response', required=True, ondelete='cascade')
    request_line_id = fields.Many2one('supplier.price.request.line', string='Request Line')

    unit_rate_p_per_kwh = fields.Float(string='Unit Rate (p/kWh)')
    standing_charge_gbp_per_day = fields.Float(string='Standing (£/day)')
    contract_term_years = fields.Integer(string='Term (years)', default=1)
    kva_price = fields.Float(string='KVA Price (HH only)')

    annual_usage_kwh = fields.Float(related='request_line_id.annual_usage_kwh', store=True)
    annual_cost = fields.Monetary(string='Annual Cost', compute='_compute_annual_cost', currency_field='currency_id', store=True)
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id.id)

    uplift_p_per_kwh = fields.Float(string='Uplift (p/kWh)', groups='energy_broker_uk.group_energy_broker_manager')
    unit_rate_with_uplift_p_per_kwh = fields.Float(string='Unit Rate w/ Uplift (p/kWh)', compute='_compute_uplift', store=True, groups='energy_broker_uk.group_energy_broker_manager')
    annual_cost_with_uplift = fields.Monetary(string='Annual Cost w/ Uplift', compute='_compute_uplift', currency_field='currency_id', store=True, groups='energy_broker_uk.group_energy_broker_manager')

    @api.depends('unit_rate_p_per_kwh', 'standing_charge_gbp_per_day', 'annual_usage_kwh')
    def _compute_annual_cost(self):
        for rec in self:
            energy_cost = (rec.unit_rate_p_per_kwh / 100.0) * (rec.annual_usage_kwh or 0.0)
            standing = (rec.standing_charge_gbp_per_day or 0.0) * 365
            rec.annual_cost = energy_cost + standing

    @api.depends('unit_rate_p_per_kwh', 'uplift_p_per_kwh', 'standing_charge_gbp_per_day', 'annual_usage_kwh')
    def _compute_uplift(self):
        for rec in self:
            rec.unit_rate_with_uplift_p_per_kwh = (rec.unit_rate_p_per_kwh or 0.0) + (rec.uplift_p_per_kwh or 0.0)
            energy_cost_uplifted = (rec.unit_rate_with_uplift_p_per_kwh / 100.0) * (rec.annual_usage_kwh or 0.0)
            standing = (rec.standing_charge_gbp_per_day or 0.0) * 365
            rec.annual_cost_with_uplift = energy_cost_uplifted + standing

    @api.constrains('uplift_p_per_kwh')
    def _check_max_uplift(self):
        ICP = self.env['ir.config_parameter'].sudo()
        max_uplift = float(ICP.get_param('energy_broker_uk.max_uplift_p_per_kwh') or 0.0)
        for rec in self:
            if max_uplift and rec.uplift_p_per_kwh and rec.uplift_p_per_kwh > max_uplift:
                raise ValidationError(_('Uplift exceeds maximum allowed (%.4g p/kWh)') % max_uplift)


class CustomerContract(models.Model):
    _name = 'customer.contract'
    _description = 'Customer Contract'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(default=lambda self: _('New'), copy=False, readonly=True)
    partner_id = fields.Many2one('res.partner', string='Customer', required=True, tracking=True)
    lead_id = fields.Many2one('crm.lead', string='Lead/Opportunity', tracking=True)
    loa_id = fields.Many2one('customer.loa', string='LOA', tracking=True)

    price_request_id = fields.Many2one('supplier.price.request', string='Price Request', tracking=True)
    price_response_id = fields.Many2one('supplier.price.response', string='Winning Response', tracking=True)

    supplier_id = fields.Many2one('res.partner', string='Supplier', domain=[('supplier_rank', '>', 0)], required=True)
    contract_type = fields.Selection([
        ('electricity', 'Electricity'),
        ('gas', 'Gas'),
        ('dual', 'Dual'),
    ], string='Contract Type', required=True)

    unit_rate_p_per_kwh = fields.Float(string='Unit Rate (p/kWh)')
    standing_charge_gbp_per_day = fields.Float(string='Standing (£/day)')

    start_date = fields.Date(string='Start Date', required=True)
    end_date = fields.Date(string='End Date', required=True)

    pdf_attachment_id = fields.Many2one('ir.attachment', string='Signed Contract PDF')

    uplift_p_per_kwh = fields.Float(string='Uplift (p/kWh)', groups='energy_broker_uk.group_energy_broker_manager')
    commission_amount = fields.Monetary(string='Estimated Commission', compute='_compute_commission', currency_field='currency_id', store=True, groups='energy_broker_uk.group_energy_broker_manager')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id.id)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('customer.contract') or _('New')
        return super().create(vals_list)

    @api.onchange('price_response_id')
    def _onchange_price_response(self):
        for rec in self:
            if rec.price_response_id:
                rec.supplier_id = rec.price_response_id.partner_id.id
                # Use first line as defaults if available
                line = rec.price_response_id.line_ids[:1]
                if line:
                    rec.unit_rate_p_per_kwh = line.unit_rate_p_per_kwh
                    rec.standing_charge_gbp_per_day = line.standing_charge_gbp_per_day
                    rec.uplift_p_per_kwh = line.uplift_p_per_kwh
                rec.lead_id = rec.price_response_id.lead_id or rec.price_response_id.request_id.lead_id

    @api.onchange('price_request_id')
    def _onchange_price_request(self):
        for rec in self:
            if rec.price_request_id and not rec.lead_id:
                rec.lead_id = rec.price_request_id.lead_id

    @api.depends('uplift_p_per_kwh', 'price_response_id', 'price_response_id.line_ids', 'price_response_id.line_ids.annual_usage_kwh')
    def _compute_commission(self):
        for rec in self:
            usage = 0.0
            if rec.price_response_id:
                # sum usage across lines
                usage = sum(rec.price_response_id.line_ids.mapped('annual_usage_kwh'))
            rec.commission_amount = (usage * (rec.uplift_p_per_kwh or 0.0)) / 100.0

    def cron_send_expiry_reminders(self):
        today = fields.Date.today()
        for days in (90, 60, 30):
            target = today + relativedelta(days=days)
            contracts = self.search([('end_date', '=', target)])
            for cont in contracts:
                cont.activity_schedule('mail.mail_activity_data_todo', summary=_('Contract expiring in %s days') % days)

    def action_send_for_signature(self):
        for rec in self:
            if rec.partner_id and rec.partner_id.email:
                subject = _('Contract for %s') % (rec.partner_id.display_name,)
                body = _('<p>Please review and sign the attached contract.</p>')
                vals = {
                    'subject': subject,
                    'body_html': body,
                    'email_to': rec.partner_id.email,
                }
                if rec.pdf_attachment_id:
                    vals['attachment_ids'] = [(4, rec.pdf_attachment_id.id)]
                mail = self.env['mail.mail'].create(vals)
                try:
                    mail.send()
                except Exception:
                    pass

    def action_mark_signed(self):
        for rec in self:
            pass

    def action_refresh_signature_status(self):
        for rec in self:
            if not rec.sign_request_id:
                continue
            att = self.env['ir.attachment'].search([
                ('res_model', '=', 'sign.request'),
                ('res_id', '=', rec.sign_request_id.id),
                ('mimetype', 'ilike', 'pdf')
            ], order='id desc', limit=1)
            if att:
                rec.pdf_attachment_id = att
                if hasattr(rec, 'status'):
                    rec.status = 'signed'


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    loa_count = fields.Integer(compute='_compute_energy_counts')
    request_count = fields.Integer(compute='_compute_energy_counts')
    response_count = fields.Integer(compute='_compute_energy_counts')
    contract_count = fields.Integer(compute='_compute_energy_counts')

    def _compute_energy_counts(self):
        for rec in self:
            rec.loa_count = self.env['customer.loa'].search_count([('lead_id', '=', rec.id)])
            rec.request_count = self.env['supplier.price.request'].search_count([('lead_id', '=', rec.id)])
            rec.response_count = self.env['supplier.price.response'].search_count([('lead_id', '=', rec.id)])
            rec.contract_count = self.env['customer.contract'].search_count([('lead_id', '=', rec.id)])

    def action_open_lead_loas(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('LOAs'),
            'res_model': 'customer.loa',
            'view_mode': 'list,form',
            'domain': [('lead_id', '=', self.id)],
            'context': {'default_lead_id': self.id, 'default_partner_id': self.partner_id.id if self.partner_id else False},
        }

    def action_open_lead_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Price Requests'),
            'res_model': 'supplier.price.request',
            'view_mode': 'list,form',
            'domain': [('lead_id', '=', self.id)],
            'context': {'default_lead_id': self.id},
        }

    def action_open_lead_responses(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Supplier Responses'),
            'res_model': 'supplier.price.response',
            'view_mode': 'list,form',
            'domain': [('lead_id', '=', self.id)],
            'context': {'default_lead_id': self.id},
        }

    def action_open_lead_contracts(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Contracts'),
            'res_model': 'customer.contract',
            'view_mode': 'list,form',
            'domain': [('lead_id', '=', self.id)],
            'context': {'default_lead_id': self.id, 'default_partner_id': self.partner_id.id if self.partner_id else False},
        }
