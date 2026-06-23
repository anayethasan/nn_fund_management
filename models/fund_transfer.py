from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
 
 
class FundTransfer(models.Model):
    """
    Fund Transfer: move funds between Projects and or Expense Heads.
 
    Supported routes:
      project  → project
      project  → expense head
      expense  → project
      expense  → expense head
 
    Workflow: draft → submitted → gm_approved → approved
                               ↘ rejected or cancelled
 
    Double-spending prevention:
      - On submit: amount is locked in source's transfer_hold.
      - Held funds cannot be spent, requisitioned, or transferred again.
      - On approve: source transfer_hold decreases, destination balance increases.
      - On reject/cancel: transfer_hold is released back to source available_balance.
    """
    _name = 'nn.fund.transfer'
    _description = 'Fund Transfer'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'request_date desc, id desc'
    
    name = fields.Char(
        string='Transfer Number',
        copy=False,
        readonly=True,
        default='New',
        tracking=True,
    )
    source_id = fields.Many2one(
        comodel_name='nn.project.expense',
        string='Source (From)',
        required=True,
        ondelete='restrict',
        tracking=True,
    )
    destination_id = fields.Many2one(
        comodel_name='nn.project.expense',
        string='Destination (To)',
        required=True,
        ondelete='restrict',
        tracking=True,
    )
    amount = fields.Monetary(
        string='Transfer Amount',
        required=True,
        currency_field='currency_id',
        tracking=True,
    )
    reason = fields.Text(string='Reason or Purpose', required=True)
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
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        related='source_id.company_id',
        store=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='source_id.currency_id',
        store=True,
    )
    
    # Approval tracking
    gm_approver_id = fields.Many2one('res.users', string='GM Approver', readonly=True, copy=False)
    gm_approval_date = fields.Datetime(string='GM Approval Date', readonly=True, copy=False)
    md_approver_id = fields.Many2one('res.users', string='MD Approver', readonly=True, copy=False)
    md_approval_date = fields.Datetime(string='MD Approval Date', readonly=True, copy=False)
    rejection_reason = fields.Text(string='Rejection or Cancellation Reason', readonly=True, copy=False)
    
    # State
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
                vals['name'] = self.env['ir.sequence'].next_by_code('nn.fund.transfer') or 'New'
        return super().create(vals_list)
    
    #Constraints
    @api.constrains('amount')
    def _check_amount_positive(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError('Transfer amount must be greater than zero.')
 
    @api.constrains('source_id', 'destination_id')
    def _check_source_destination_different(self):
        """Source and destination cannot be the same project or expense head."""
        for rec in self:
            if rec.source_id and rec.destination_id and rec.source_id == rec.destination_id:
                raise ValidationError(
                    f'Source and destination cannot be the same: "{rec.source_id.name}". '
                    'Transfer requires two different projects or expense heads.'
                )
    
    # Workflow
    def action_submit(self):
        """
        Submit transfer.
        Locks the amount in source's transfer_hold — cannot be spent or
        requisitioned by anyone else while pending.
        """
        for rec in self:
            if rec.state != 'draft':
                raise UserError('Only draft transfers can be submitted.')
 
            # Server-side balance check
            available = rec.source_id.available_balance
            if rec.amount > available:
                raise UserError(
                    f'Insufficient balance in "{rec.source_id.name}".\n'
                    f'Transfer amount : {rec.amount:,.2f}\n'
                    f'Available       : {available:,.2f}\n\n'
                    f'Cannot transfer more than the available balance.'
                )
 
            old_state = rec.state
            rec.state = 'submitted'
 
            # Recompute source: available_balance decreases, transfer_hold increases
            rec.source_id._compute_balances()
 
            self.env['nn.approval.history'].log_action(
                document=rec, approval_level='submit', decision='submitted',
                state_before=old_state, state_after='submitted',
            )
 
    def action_gm_approve(self, comment=''):
        self._check_approver_group('gm')
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(f'GM can only approve submitted transfers. Current state: {rec.state}.')
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
        Final approval.
        source: transfer_hold decreases (total approved transfers increases)
        destination: total_allocated/available increases (incoming transfers approved)
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
 
            rec.source_id._compute_balances()
            rec.destination_id._compute_balances()
 
            self.env['nn.approval.history'].log_action(
                document=rec, approval_level='md', decision='approved',
                comment=comment, state_before=old_state, state_after='approved',
            )
 
    def action_reject(self, comment=''):
        """Reject — release transfer_hold back to source's available_balance."""
        self._check_approver_group('gm')
        for rec in self:
            if rec.state not in ('submitted', 'gm_approved'):
                raise UserError(f'Cannot reject transfer in state "{rec.state}".')
 
            old_state = rec.state
            rec.write({'state': 'rejected', 'rejection_reason': comment})
            rec.source_id._compute_balances()
 
            self.env['nn.approval.history'].log_action(
                document=rec, approval_level='reject', decision='rejected',
                comment=comment, state_before=old_state, state_after='rejected',
            )
 
    def action_cancel(self, comment=''):
        """Cancel — releases hold if in submitted or gm_approved."""
        for rec in self:
            if rec.state == 'approved':
                raise UserError(
                    f'Approved transfer "{rec.name}" cannot be cancelled directly. '
                    'Create a reverse transfer to move funds back.'
                )
            if rec.state in ('rejected', 'cancelled'):
                raise UserError(f'"{rec.name}" is already {rec.state}.')
 
            old_state = rec.state
            rec.write({'state': 'cancelled', 'rejection_reason': comment})
 
            if old_state in ('submitted', 'gm_approved'):
                rec.source_id._compute_balances()
 
            self.env['nn.approval.history'].log_action(
                document=rec, approval_level='cancel', decision='cancelled',
                comment=comment, state_before=old_state, state_after='cancelled',
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
            raise UserError('You cannot approve your own transfer request.')
 
    def unlink(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(f'Transfer "{rec.name}" cannot be deleted. Cancel it first.')
        return super().unlink()
    