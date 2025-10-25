from odoo import models, fields, api, _
from dateutil.relativedelta import relativedelta

class CustomerContractExt(models.Model):
    _inherit = "customer.contract"

    state = fields.Selection([
        ("draft", "Draft"),
        ("doc_pending", "Documents Pending"),
        ("sale_agreed", "Sale Agreed"),
        ("confirmed", "Confirmed"),
        ("accepted", "Accepted"),
        ("live", "Live"),
        ("complete", "Complete"),
        ("payment_confirmed", "Payment Confirmed"),
        ("query", "Query"),
        ("cot_cancelled", "COT Cancelled"),
        ("cancelled", "Cancelled"),
    ], default="draft", tracking=True)

    # Commission config
    commission_rule_id = fields.Many2one("energy.commission.rule", string="Commission Rule")

    # Commission fields
    supplier_commission = fields.Float(compute="_compute_supplier_commission", store=True)
    commission_first_payment = fields.Float()
    full_commission = fields.Float(compute="_compute_full_commission", store=True)
    commission_amount_total = fields.Float(compute="_compute_commission_amount_total", store=True)
    commission_to_pay = fields.Float(compute="_compute_commission_to_pay", store=True)

    # Alerts
    alert = fields.Boolean(default=False)
    alert_no = fields.Char()
    alert_color = fields.Char(default="black")

    # Odoo Sign
    sign_template_id = fields.Many2one("sign.template", string="Sign Template")
    sign_request_id = fields.Many2one("sign.request", string="Sign Request")
    sign_status = fields.Selection([
        ("draft", "Draft"), ("pending", "Pending"), ("signed", "Signed"),
        ("refused", "Refused"), ("cancelled", "Cancelled")
    ], default="draft")
    signer_partner_id = fields.Many2one("res.partner", string="Signer")
    sign_completed_on = fields.Datetime()

    @api.depends("price_response_id", "price_response_id.line_ids.annual_usage_kwh", "uplift_p_per_kwh", "commission_rule_id")
    def _compute_supplier_commission(self):
        for rec in self:
            usage = 0.0
            if rec.price_response_id:
                usage = sum(rec.price_response_id.line_ids.mapped("annual_usage_kwh"))
            base = (usage * (rec.uplift_p_per_kwh or 0.0)) / 100.0
            rule = rec.commission_rule_id
            if rule and rule.supplier_percent:
                rec.supplier_commission = base * (rule.supplier_percent / 100.0)
            else:
                rec.supplier_commission = base

    @api.depends("supplier_commission", "commission_rule_id")
    def _compute_full_commission(self):
        for rec in self:
            rule = rec.commission_rule_id
            broker_split = (rule.broker_split_percent / 100.0) if (rule and rule.broker_split_percent) else 1.0
            rec.full_commission = (rec.supplier_commission or 0.0) * broker_split
            # Derive first payment from upfront % if not already set
            if rule and rule.upfront_percent is not None:
                rec.commission_first_payment = (rec.full_commission or 0.0) * (rule.upfront_percent / 100.0)

    def _compute_commission_amount_total(self):
        for rec in self:
            # If reconciliation models are present, try summing; otherwise just mirror full_commission
            total = rec.full_commission or 0.0
            try:
                if hasattr(rec, supplier_reconcile_ids):
                    total = sum(l.com_amount for l in rec.supplier_reconcile_ids)
            except Exception:
                pass
            rec.commission_amount_total = total

    def _compute_commission_to_pay(self):
        for rec in self:
            paid = 0.0
            try:
                if hasattr(rec, broker_reconcile_ids):
                    paid = sum(l.comm_amount for l in rec.broker_reconcile_ids)
            except Exception:
                paid = 0.0
            rec.commission_to_pay = (rec.supplier_commission or 0.0) - (rec.commission_first_payment or 0.0) - paid

    def cron_contract_alerts(self):
        today = fields.Date.today()
        contracts = self.search([("end_date", "!=", False)])
        for c in contracts:
            days = (c.end_date - today).days if c.end_date else 0
            c.alert = days in (90, 60, 30)

    def action_send_for_signature(self):
        self.ensure_one()
        template = self.sign_template_id
        signer = self.signer_partner_id or self.partner_id
        if not template or not signer:
            return False
        SignRequest = self.env["sign.request"]
        vals = {
            "template_id": template.id,
            "reference": self.name or "Contract",
        }
        req = SignRequest.create(vals)
        # Assign signer on first role if available
        try:
            roles = req.template_id.role_ids
            if roles:
                req.write({
                    "request_item_ids": [(0, 0, {
                        "partner_id": signer.id,
                        "role_id": roles[0].id,
                    })]
                })
        except Exception:
            pass
        self.sign_request_id = req.id
        self.sign_status = "pending"
        return {
            "type": "ir.actions.act_window",
            "res_model": "sign.request",
            "res_id": req.id,
            "view_mode": "form",
            "target": "current",
        }

    def cron_sync_sign_status(self):
        for rec in self.search([("sign_request_id", "!=", False)]):
            req = rec.sign_request_id
            status = getattr(req, "state", False) or getattr(req, "status", False)
            if status in ("completed", "signed"):
                rec.sign_status = "signed"
                rec.sign_completed_on = fields.Datetime.now()
                att = self.env["ir.attachment"].search([
                    ("res_model", "=", "sign.request"),
                    ("res_id", "=", req.id),
                    ("mimetype", "ilike", "pdf")
                ], order="id desc", limit=1)
                if att:
                    rec.pdf_attachment_id = att
                if rec.state in ("draft", "doc_pending", "sale_agreed"):
                    rec.state = "confirmed"
            elif status in ("refused", "rejected"):
                rec.sign_status = "refused"
                if rec.state not in ("cancelled", "cot_cancelled"):
                    rec.state = "query"
            elif status in ("cancel", "cancelled"):
                rec.sign_status = "cancelled"
            else:
                rec.sign_status = "pending"
