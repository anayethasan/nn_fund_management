from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError

class FundRequisition(models.Model):
    """
    Fund Requisition: request funds from a Project or Expense Head
    to pay for specific expenses. Linked to bills for actual spending.
 
    Workflow:draft → submitted → gm_approved → approved → closed
                                rejected / cancelled
 
    Double-spending prevention:
      - On submit: requested_amount is placed on requisition_hold in project or expense.
      - The held amount cannot be used for another requisition or transfer.
      - On approve: amount stays reserved; bills can be raised against it.
      - remaining_billable tracks how much is still available for bills.
      - On reject or cancel: held amount returns to project's available_balance.
    """
    _name = 'nn.fund.requisition'
    _description = 'Fund Requisition'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'request_date desc, id desc'
    
    name = fields.Char(
        string='Requisition Number',
        copy=False,
        readonly=True,
        default='New',
        tracking=True,
    )
    project_expense_id = fields.Many2one(
        comodel_name='nn.project.expense',
        string='Project or Expense Head',
        required=True,
        ondelete='restrict',
        tracking=True,
    )
    requested_amount = fields.Monetary(
        string='Requested Amount',
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
    required_date = fields.Date(string='Required By Date')
    requested_by = fields.Many2one(
        comodel_name='res.users',
        string='Requested By',
        default=lambda self: self.env.user,
        required=True,
        readonly=True,
    )
    attachment_ids = fields.Many2many(
        comodel_name='ir.attachment',
        string='Supporting Attachments',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        related='project_expense_id.company_id',
        store=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='project_expense_id.currency_id',
        store=True,
    )
    
    # Bills
    bill_ids = fields.One2many(
        comodel_name='nn.fund.bill',
        inverse_name='requisition_id',
        string='Bills',
    )
    bill_count = fields.Integer(
        string='Bill Count',
        compute='_compute_bill_stats',
    )
    total_billed = fields.Monetary(
        string='Total Billed',
        compute='_compute_bill_stats',
        store=True,
        currency_field='currency_id',
    )
    remaining_billable = fields.Monetary(
        string='Remaining Billable',
        compute='_compute_bill_stats',
        store=True,
        currency_field='currency_id',
        help='How much more can be billed against this requisition.',
    )
 
    @api.depends('bill_ids.amount', 'bill_ids.state', 'requested_amount', 'state')
    def _compute_bill_stats(self):
        for rec in self:
            posted_bills = rec.bill_ids.filtered(lambda b: b.state == 'posted')
            total_billed = sum(posted_bills.mapped('amount'))
            rec.bill_count = len(rec.bill_ids)
            rec.total_billed = total_billed
            # remaining_billable only meaningful when approved or closed
            if rec.state in ('approved', 'closed'):
                rec.remaining_billable = rec.requested_amount - total_billed
            else:
                rec.remaining_billable = 0.0
            
    # Approval tracking
    gm_approver_id = fields.Many2one('res.users', string='GM Approver', readonly=True, copy=False)
    gm_approval_date = fields.Datetime(string='GM Approval Date', readonly=True, copy=False)
    md_approver_id = fields.Many2one('res.users', string='MD Approver', readonly=True, copy=False)
    md_approval_date = fields.Datetime(string='MD Approval Date', readonly=True, copy=False)
    rejection_reason = fields.Text(string='Rejection or Cancellation Reason', readonly=True, copy=False)
    
    #State
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('submitted', 'Submitted'),
            ('gm_approved', 'GM Approved'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
            ('cancelled', 'Cancelled'),
            ('closed', 'Closed'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
        copy=False,
        index=True,
    )
    
    # Approval history (computed from nn.approval.history)
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
                vals['name'] = self.env['ir.sequence'].next_by_code('nn.fund.requisition') or 'New'
        return super().create(vals_list)
    
    # Constraint
    @api.constrains('requested_amount')
    def _check_amount_positive(self):
        for rec in self:
            if rec.requested_amount <= 0:
                raise ValidationError('Requisition amount must be greater than zero.')
    
    # Workflow
    def action_submit(self):
        """
        Submit the requisition.
        Checks available project or expense balance and places amount on hold.
        """
        for rec in self:
            if rec.state != 'draft':
                raise UserError(f'Only draft requisitions can be submitted.')
 
            available = rec.project_expense_id.available_balance
            if rec.requested_amount > available:
                raise UserError(
                    f'Insufficient balance in "{rec.project_expense_id.name}".\n'
                    f'Requested : {rec.requested_amount:,.2f}\n'
                    f'Available : {available:,.2f}\n\n'
                    f'The requested amount exceeds the available project/expense balance.'
                )
 
            old_state = rec.state
            rec.state = 'submitted'
            # Balance recompute: available_balance decreases, requisition_hold increases
            rec.project_expense_id._compute_balances()
 
            self.env['nn.approval.history'].log_action(
                document=rec,
                approval_level='submit',
                decision='submitted',
                state_before=old_state,
                state_after='submitted',
            )
 
    def action_gm_approve(self, comment=''):
        self._check_approver_group('gm')
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(f'GM can only approve submitted requisitions. Current state: {rec.state}.')
            self._check_not_own_request(rec)
 
            old_state = rec.state
            rec.write({
                'state': 'gm_approved',
                'gm_approver_id': self.env.uid,
                'gm_approval_date': fields.Datetime.now(),
            })
            self.env['nn.approval.history'].log_action(
                document=rec, approval_level='gm', decision='approved',
                comment=comment, state_before=old_state, state_after='gm_approved',
            )
 
    def action_md_approve(self, comment=''):
        """
        Final MD approval.
        Amount stays in requisition_hold until bills consume it or requisition is closed.
        """
        self._check_approver_group('md')
        for rec in self:
            if rec.state != 'gm_approved':
                raise UserError(
                    f'MD can only approve after GM approval. '
                    f'Current state: "{rec.state}". GM must approve first.'
                )
            self._check_not_own_request(rec)
 
            old_state = rec.state
            rec.write({
                'state': 'approved',
                'md_approver_id': self.env.uid,
                'md_approval_date': fields.Datetime.now(),
            })
            # Note: balance stays in requisition_hold until bills are posted or closed
            rec.project_expense_id._compute_balances()
 
            self.env['nn.approval.history'].log_action(
                document=rec, approval_level='md', decision='approved',
                comment=comment, state_before=old_state, state_after='approved',
            )
 
    def action_reject(self, comment=''):
        """Reject and release held amount back to available_balance."""
        self._check_approver_group('gm')
        for rec in self:
            if rec.state not in ('submitted', 'gm_approved'):
                raise UserError(f'Cannot reject requisition in state "{rec.state}".')
 
            old_state = rec.state
            rec.write({'state': 'rejected', 'rejection_reason': comment})
            rec.project_expense_id._compute_balances()
 
            self.env['nn.approval.history'].log_action(
                document=rec, approval_level='reject', decision='rejected',
                comment=comment, state_before=old_state, state_after='rejected',
            )
 
    def action_cancel(self, comment=''):
        """Cancel — releases hold if in submitted or gm_approved."""
        for rec in self:
            if rec.state in ('approved', 'closed'):
                raise UserError(
                    f'Cannot cancel an {rec.state} requisition. '
                    'Close it properly to release unused funds.'
                )
            if rec.state in ('rejected', 'cancelled'):
                raise UserError(f'"{rec.name}" is already {rec.state}.')
 
            old_state = rec.state
            rec.write({'state': 'cancelled', 'rejection_reason': comment})
 
            if old_state in ('submitted', 'gm_approved'):
                rec.project_expense_id._compute_balances()
 
            self.env['nn.approval.history'].log_action(
                document=rec, approval_level='cancel', decision='cancelled',
                comment=comment, state_before=old_state, state_after='cancelled',
            )
 
    def action_close(self, comment=''):
        """
        Close a requisition when:
          a) Fully billed (remaining_billable == 0), or
          b) Manually closed — unused amount returns to available_balance.
        """
        for rec in self:
            if rec.state != 'approved':
                raise UserError('Only approved requisitions can be closed.')
 
            old_state = rec.state
            rec.state = 'closed'
            # Release remaining unbilled amount back to project balance
            rec.project_expense_id._compute_balances()
 
            self.env['nn.approval.history'].log_action(
                document=rec, approval_level='cancel', decision='cancelled',
                comment=comment or 'Requisition closed.',
                state_before=old_state, state_after='closed',
            )
            
    # Security helpers
    def _check_approver_group(self, level):
        group_map = {
            'gm': 'nn_fund_management.group_gm_approver',
            'md': 'nn_fund_management.group_md_approver',
        }
        allowed = [group_map[level], 'nn_fund_management.group_fund_admin']
        if level == 'gm':
            allowed.append(group_map['md'])
        if not any(self.env.user.has_group(g) for g in allowed):
            raise UserError(f'You do not have permission. Required role: {level.upper()} Approver.')
 
    def _check_not_own_request(self, rec):
        if (
            rec.requested_by.id == self.env.uid
            and not self.env.user.has_group('nn_fund_management.group_fund_admin')
        ):
            raise UserError('You cannot approve your own requisition request.')
 
    def unlink(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(f'Requisition "{rec.name}" cannot be deleted. Cancel it first.')
        return super().unlink()
    
    def action_view_bills(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Bills',
            'res_model': 'nn.fund.bill',
            'view_mode': 'list,form',
            'domain': [('requisition_id', '=', self.id)],
            'context': {'default_requisition_id': self.id},
        }