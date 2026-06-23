from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
 
 
class FundBill(models.Model):
    """
    Fund Bill: records actual spending against an approved Fund Requisition.
 
    Key rules enforced server-side:
      1. Requisition must be in 'approved' state.
      2. Bill project or expense must MATCH the requisition's project or expense.
         (Project A cannot use Project B's requisition.)
      3. Bill amount cannot exceed requisition's remaining_billable.
      4. Multiple partial bills are allowed.
      5. On cancel: amount is returned to remaining_billable (no new funds created).
    """
    _name = 'nn.fund.bill'
    _description = 'Fund Bill'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'bill_date desc, id desc'
    
    name = fields.Char(
        string='Bill Number',
        copy=False,
        readonly=True,
        default='New',
        tracking=True,
    )
    requisition_id = fields.Many2one(
        comodel_name='nn.fund.requisition',
        string='Fund Requisition',
        required=True,
        ondelete='restrict',
        tracking=True,
        domain=[('state', '=', 'approved')],
    )
    project_expense_id = fields.Many2one(
        comodel_name='nn.project.expense',
        string='Project / Expense Head',
        related='requisition_id.project_expense_id',
        store=True,
        readonly=True,
        help='Automatically taken from the linked requisition. Cannot be changed.',
    )
    amount = fields.Monetary(
        string='Bill Amount',
        required=True,
        currency_field='currency_id',
        tracking=True,
    )
    vendor = fields.Char(string='Vendor', required=True)
    bill_date = fields.Date(
        string='Bill Date',
        required=True,
        default=fields.Date.context_today,
    )
    description = fields.Text(string='Description')
    attachment_ids = fields.Many2many(
        comodel_name='ir.attachment',
        string='Bill Attachments',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        related='requisition_id.company_id',
        store=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='requisition_id.currency_id',
        store=True,
    )
    
    # State
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('posted', 'Posted'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
        copy=False,
        index=True,
    )
    posted_by = fields.Many2one('res.users', string='Posted By', readonly=True, copy=False)
    posted_date = fields.Datetime(string='Posted On', readonly=True, copy=False)
    cancelled_by = fields.Many2one('res.users', string='Cancelled By', readonly=True, copy=False)
    cancelled_date = fields.Datetime(string='Cancelled On', readonly=True, copy=False)
    cancellation_reason = fields.Text(string='Cancellation Reason', readonly=True, copy=False)
    
    # Sequence
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('nn.fund.bill') or 'New'
        return super().create(vals_list)
    
    # Constraints
    @api.constrains('amount')
    def _check_amount_positive(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError('Bill amount must be greater than zero.')
 
    @api.constrains('requisition_id', 'state')
    def _check_requisition_approved(self):
        """Requisition must be approved."""
        for rec in self:
            if rec.requisition_id and rec.requisition_id.state not in ('approved', 'closed'):
                raise ValidationError(
                    f'Bills can only be created for approved requisitions. '
                    f'Requisition "{rec.requisition_id.name}" is currently "{rec.requisition_id.state}".'
                )
 
    @api.constrains('amount', 'requisition_id')
    def _check_amount_within_billable(self):
        """
        Bill amount cannot exceed remaining_billable.
        This accounts for partial bills already posted.
        """
        for rec in self:
            if not rec.requisition_id:
                continue
            req = rec.requisition_id
            # Sum all OTHER posted bills for the same requisition
            other_posted = sum(
                b.amount for b in req.bill_ids
                if b.state == 'posted' and b.id != rec.id
            )
            remaining = req.requested_amount - other_posted
            if rec.amount > remaining:
                raise ValidationError(
                    f'Bill amount ({rec.amount:,.2f}) exceeds the remaining billable amount '
                    f'({remaining:,.2f}) for requisition "{req.name}".\n\n'
                    f'Requisition total : {req.requested_amount:,.2f}\n'
                    f'Already billed    : {other_posted:,.2f}\n'
                    f'Remaining         : {remaining:,.2f}'
                )
    
    # Actions
    def action_post(self):
        """
        Post the bill — marks amount as spent.
        On post:
          - remaining_billable on requisition decreases
          - project/expense total_spent increases
          Both happen via the computed field recompute.
        """
        self._check_finance_user()
        for rec in self:
            if rec.state != 'draft':
                raise UserError(f'Only draft bills can be posted. "{rec.name}" is {rec.state}.')
 
            # Re-validate billable amount at post time (concurrent safety)
            req = rec.requisition_id
            if req.state not in ('approved',):
                raise UserError(
                    f'Cannot post bill: requisition "{req.name}" is no longer in approved state.'
                )
 
            other_posted = sum(
                b.amount for b in req.bill_ids
                if b.state == 'posted' and b.id != rec.id
            )
            remaining = req.requested_amount - other_posted
            if rec.amount > remaining:
                raise UserError(
                    f'Cannot post: bill amount ({rec.amount:,.2f}) exceeds remaining '
                    f'billable ({remaining:,.2f}) for "{req.name}".'
                )
 
            rec.write({
                'state': 'posted',
                'posted_by': self.env.uid,
                'posted_date': fields.Datetime.now(),
            })
 
            # Trigger recompute: remaining_billable decreases, total_spent increases
            req._compute_bill_stats()
            rec.project_expense_id._compute_balances()
 
            # Auto-close requisition if fully billed
            if req.remaining_billable <= 0:
                req.state = 'closed'
    
    def action_cancel(self, reason=''):
        """
        Cancel a posted bill.
        On cancel:
          - remaining_billable returns to requisition
          - project or expense total_spent decreases
          Reversal does NOT create new funds — it only restores the billable amount.
        """
        self._check_finance_user()
        for rec in self:
            if rec.state == 'cancelled':
                raise UserError(f'Bill "{rec.name}" is already cancelled.')
            if rec.state == 'draft':
                rec.state = 'cancelled'
                continue
 
            # Re-open requisition if it was auto-closed
            req = rec.requisition_id
            if req.state == 'closed':
                req.state = 'approved'
 
            rec.write({
                'state': 'cancelled',
                'cancelled_by': self.env.uid,
                'cancelled_date': fields.Datetime.now(),
                'cancellation_reason': reason,
            })
 
            # Recompute remaining_billable increases, total_spent decreases
            req._compute_bill_stats()
            rec.project_expense_id._compute_balances()  
            
    # Security helpers
    def _check_finance_user(self):
        if not (
            self.env.user.has_group('nn_fund_management.group_finance_user')
            or self.env.user.has_group('nn_fund_management.group_fund_admin')
        ):
            raise UserError('Only Finance Users or Fund Administrators can post or cancel bills.')
 
    def unlink(self):
        for rec in self:
            if rec.state == 'posted':
                raise UserError(
                    f'Posted bill "{rec.name}" cannot be deleted. Cancel it first.'
                )
        return super().unlink()          
            
        