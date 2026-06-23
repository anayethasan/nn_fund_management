from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError

class FundAllocation(models.Model):
    """
    Fund Allocation: moves money from a FundAccount's unassigned balance
    to a Project or Expense Head.
 
    Workflow:draft→submitted→gm_approved→approved
                                rejected/cancelled

    Double-spending prevention:
      - On submit: amount is deducted from unassigned_balance and added to held_amount.
      - The held amount CANNOT be used by any other allocation request.
      - On approve: held moves to assigned (project or expense balance increases).
      - On reject or cancel: held is released back to unassigned.
    """
    _name = 'nn.fund.allocation'
    _description = 'Fund Allocation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'request_date desc, id desc'
    
    name = fields.Char(
        string='Request Number',
        copy=False,
        readonly=True,
        default='New',
        tracking=True,
    )
    fund_account_id = fields.Many2one(
        comodel_name='nn.fund.account',
        string='Fund Account',
        required=True,
        ondelete='restrict',
        tracking=True,
    )
    project_expense_id = fields.Many2one(
        comodel_name='nn.project.expense',
        string='Project or Expense Head',
        required=True,
        ondelete='restrict',
        tracking=True,
    )
    amount = fields.Monetary(
        string='Amount',
        required=True,
        currency_field='currency_id',
        tracking=True,
    )
    purpose = fields.Text(string='Purpose', required=True)
    request_date = fields.Date(
        string='Request Date',
        required=True,
        default=fields.Date.context_today,
    )
    requested_by = fields.Many2one(
        comodel_name='res.users',
        string='Requested By',
        default=lambda self: self.env.user,
        required=True,
        readonly=True,
    )
    attachment_ids = fields.Many2many(
        comodel_name='ir.attachment',
        string='Attachments',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        related='fund_account_id.company_id',
        store=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='fund_account_id.currency_id',
        store=True,
    )
    
    # Approval tracking
    gm_approver_id = fields.Many2one(
        comodel_name='res.users',
        string='GM Approver',
        readonly=True,
        copy=False,
    )
    gm_approval_date = fields.Datetime(string='GM Approval Date', readonly=True, copy=False)
    md_approver_id = fields.Many2one(
        comodel_name='res.users',
        string='MD Approver',
        readonly=True,
        copy=False,
    )
    md_approval_date = fields.Datetime(string='MD Approval Date', readonly=True, copy=False)
    rejection_reason = fields.Text(string='Rejection or Cancellation Reason', readonly=True, copy=False)
    
    # Workflow state
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('submitted', 'Submitted'),
            ('gm_approved', 'GM Approved'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
        copy=False,
        index=True,
    )
    
    # Approval History
    approval_history_ids = fields.One2many(
        comodel_name='nn.approval.history',
        string='Approval History',
        compute='_compute_approval_history',
    )
    
    @api.depends('state')
    def _compute_approval_history(self):
        History = self.env['nn.approval.history']
        for rec in self:
            rec.approval_history_ids = History.search([
                ('res_model', '=', self._name),
                ('res_id', '=', rec.id),
            ])
    
    # Sequence
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('nn.fund.allocation') or 'New'
        return super().create(vals_list)
    
    # Constraint
    @api.constrains('amount')
    def _check_amount_positive(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError('Allocation amount must be greater than zero.')
    
    #Workflow Actions
    def action_submit(self):
        """
        KEY METHOD Double-spending prevention starts here.
        Before submitting:
          1.Check available unassigned balance is sufficient.
          2.Trigger recompute the FundAccount computed field will deduct this amount from unassigned and add it to held.
        """
        for rec in self:
            if rec.state != 'draft':
                raise UserError(f'Only draft allocations can be submitted. "{rec.name}" is {rec.state}.')
            
            #Server Side Balance Check
            available = rec.fund_account_id.unassigned_balance
            if rec.amount > available:
                raise UserError(
                    f'Insufficient unassigned balance.\n'
                    f'Requested: {rec.amount:,.2f}\n'
                    f'Available: {available:,.2f}\n\n'
                    f'The requested amount exceeds the available unassigned balance '
                    f'in "{rec.fund_account_id.name}".'
                )
 
            old_state = rec.state
            rec.state = 'submitted'
            # The FundAccount computed field automatically moves amount to held.
            # Force recompute immediately so the balance is updated in this transaction.
            rec.fund_account_id._compute_balances()
            
            # Audit log
            self.env['nn.approval.history'].log_action(
                document=rec,
                approval_level='submit',
                decision='submitted',
                state_before=old_state,
                state_after='submitted',
            )
            
    def action_gm_approve(self, comment=''):
        """GM approval — only users in group_gm_approver can call this."""
        self._check_approver_group('gm')
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(f'GM can only approve submitted allocations. "{rec.name}" is {rec.state}.')
            self._check_not_own_request(rec)
 
            old_state = rec.state
            rec.write({
                'state': 'gm_approved',
                'gm_approver_id': self.env.uid,
                'gm_approval_date': fields.Datetime.now(),
            })
            self.env['nn.approval.history'].log_action(
                document=rec,
                approval_level='gm',
                decision='approved',
                comment=comment,
                state_before=old_state,
                state_after='gm_approved',
            )
 
    def action_md_approve(self, comment=''):
        """
        MD approval only users in group_md_approver can call this.
        MD CANNOT approve before GM (state must be gm_approved).
        On final approval: held is released and project balance increases.
        """
        self._check_approver_group('md')
        for rec in self:
            if rec.state != 'gm_approved':
                raise UserError(
                    f'MD can only approve after GM approval. '
                    f'"{rec.name}" is currently "{rec.state}". '
                    'GM must approve first.'
                )
            self._check_not_own_request(rec)
 
            old_state = rec.state
            rec.write({
                'state': 'approved',
                'md_approver_id': self.env.uid,
                'md_approval_date': fields.Datetime.now(),
            })
 
            # Recompute balances:
            # FundAccount: held -= amount, assigned += amount
            # ProjectExpense: total_allocated += amount, available_balance += amount
            rec.fund_account_id._compute_balances()
            rec.project_expense_id._compute_balances()
 
            self.env['nn.approval.history'].log_action(
                document=rec,
                approval_level='md',
                decision='approved',
                comment=comment,
                state_before=old_state,
                state_after='approved',
            )
    
    
    def action_reject(self, comment=''):
        """
        Rejection (by GM or MD).
        Releases the held amount back to unassigned_balance.
        """
        self._check_approver_group('gm')
        for rec in self:
            if rec.state not in ('submitted', 'gm_approved'):
                raise UserError(f'Cannot reject "{rec.name}" in state "{rec.state}".')
 
            old_state = rec.state
            rec.write({
                'state': 'rejected',
                'rejection_reason': comment,
            })
 
            # Release held funds back to unassigned
            rec.fund_account_id._compute_balances()
 
            self.env['nn.approval.history'].log_action(
                document=rec,
                approval_level='reject',
                decision='rejected',
                comment=comment,
                state_before=old_state,
                state_after='rejected',
            )   
    
    def action_cancel(self, comment=''):
        """
        Cancellation allowed from draft, submitted, or gm_approved.
        Approved allocations cannot be simply cancelled (money is already in project).
        """
        for rec in self:
            if rec.state == 'approved':
                raise UserError(
                    f'Approved allocation "{rec.name}" cannot be cancelled directly. '
                    'A reversal transfer must be used to move funds back.'
                )
            if rec.state in ('rejected', 'cancelled'):
                raise UserError(f'"{rec.name}" is already {rec.state}.')
 
            old_state = rec.state
            rec.write({
                'state': 'cancelled',
                'rejection_reason': comment,
            })
 
            # If it was submitted or gm_approved, release the held amount
            if old_state in ('submitted', 'gm_approved'):
                rec.fund_account_id._compute_balances()
 
            self.env['nn.approval.history'].log_action(
                document=rec,
                approval_level='cancel',
                decision='cancelled',
                comment=comment,
                state_before=old_state,
                state_after='cancelled',
            )    
            
    #Security Helpers
    def _check_approver_group(self, level):
        """Server-side group check UI button visibility alone is insufficient."""
        group_map = {
            'gm': 'nn_fund_management.group_gm_approver',
            'md': 'nn_fund_management.group_md_approver',
        }
        # MD approvers can also act as GM approvers in the reject path
        allowed_groups = [group_map[level]]
        if level == 'gm':
            allowed_groups.append(group_map['md'])
        allowed_groups.append('nn_fund_management.group_fund_admin')
 
        if not any(self.env.user.has_group(g) for g in allowed_groups):
            raise UserError(
                f'You do not have permission to perform this approval action. '
                f'Required role: {level.upper()} Approver.'
            )
 
    def _check_not_own_request(self, rec):
        """Users cannot approve their own requests (unless fund_admin)."""
        if (
            rec.requested_by.id == self.env.uid
            and not self.env.user.has_group('nn_fund_management.group_fund_admin')
        ):
            raise UserError(
                'You cannot approve your own allocation request. '
                'A different approver must review this request.'
            )
    
    # Prevent deletion of non-draft records
    def unlink(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(
                    f'Allocation "{rec.name}" cannot be deleted because it is {rec.state}. '
                    'Cancel it first.'
                )
        return super().unlink()
