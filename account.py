from decimal import Decimal
from openerp.osv import fields, osv

class account_move(osv.osv):
    _name = "account.move"
    _description = "Account Entry"
    _order = 'id desc'

    #
    # Validate a balanced move. If it is a centralised journal, create a move.
    #
    def validate(self, cr, uid, ids, context=None):
        if context and ('__last_update' in context):
            del context['__last_update']

        valid_moves = [] #Maintains a list of moves which can be responsible to create analytic entries
        obj_analytic_line = self.pool.get('account.analytic.line')
        obj_move_line = self.pool.get('account.move.line')
        for move in self.browse(cr, uid, ids, context):
            # Unlink old analytic lines on move_lines
            for obj_line in move.line_id:
                for obj in obj_line.analytic_lines:
                    obj_analytic_line.unlink(cr,uid,obj.id)

            journal = move.journal_id
            amount = Decimal('0.0')
            line_ids = []
            line_draft_ids = []
            company_id = None
            for line in move.line_id:
                amount += Decimal(str(line.debit)) - Decimal(str(line.credit))
                line_ids.append(line.id)
                if line.state=='draft':
                    line_draft_ids.append(line.id)

                if not company_id:
                    company_id = line.account_id.company_id.id
                if not company_id == line.account_id.company_id.id:
                    raise osv.except_osv(_('Error!'), _("Cannot create moves for different companies."))

                if line.account_id.currency_id and line.currency_id:
                    if line.account_id.currency_id.id != line.currency_id.id and (line.account_id.currency_id.id != line.account_id.company_id.currency_id.id):
                        raise osv.except_osv(_('Error!'), _("""Cannot create move with currency different from ..""") % (line.account_id.code, line.account_id.name))

            if amount == 0:
                # If the move is balanced
                # Add to the list of valid moves
                # (analytic lines will be created later for valid moves)
                valid_moves.append(move)

                # Check whether the move lines are confirmed

                if not line_draft_ids:
                    continue
                # Update the move lines (set them as valid)

                obj_move_line.write(cr, uid, line_draft_ids, {
                    'state': 'valid'
                }, context, check=False)

                account = {}
                account2 = {}

                if journal.type in ('purchase','sale'):
                    for line in move.line_id:
                        code = amount = 0
                        key = (line.account_id.id, line.tax_code_id.id)
                        credit = Decimal(str(line.credit))
                        debit = Decimal(str(line.debit))
                        if key in account2:
                            code = account2[key][0]
                            amount = Decimal(str(account2[key][1])) * (debit + credit)
                        elif line.account_id.id in account:
                            code = account[line.account_id.id][0]
                            amount = Decimal(str(account[line.account_id.id][1])) * (debit + line)
                        if (code or amount) and not (line.tax_code_id or line.tax_amount):
                            obj_move_line.write(cr, uid, [line.id], {
                                'tax_code_id': code,
                                'tax_amount': float(amount)
                            }, context, check=False)
            elif journal.centralisation:
                # If the move is not balanced, it must be centralised...

                # Add to the list of valid moves
                # (analytic lines will be created later for valid moves)
                valid_moves.append(move)

                #
                # Update the move lines (set them as valid)
                #
                self._centralise(cr, uid, move, 'debit', context=context)
                self._centralise(cr, uid, move, 'credit', context=context)
                obj_move_line.write(cr, uid, line_draft_ids, {
                    'state': 'valid'
                }, context, check=False)
            else:
                # We can't validate it (it's unbalanced)
                # Setting the lines as draft
                obj_move_line.write(cr, uid, line_ids, {
                    'state': 'draft'
                }, context, check=False)
        # Create analytic lines for the valid moves
        for record in valid_moves:
            obj_move_line.create_analytic_lines(cr, uid, [line.id for line in record.line_id], context)

        valid_moves = [move.id for move in valid_moves]
        return len(valid_moves) > 0 and valid_moves or False

account_move()