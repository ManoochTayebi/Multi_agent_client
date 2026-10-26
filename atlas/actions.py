"""Idempotent proposal/confirmation/review state machine with transactional simulated outbox."""
from sqlalchemy import select, and_
from sqlalchemy.exc import IntegrityError
from atlas import db


class Conflict(ValueError):
    pass


class Actions:
    def __init__(self, engine, tools):
        self.engine, self.tools = engine, tools

    def propose(self, customer_id, order_id, run_id):
        evidence = self.tools.investigate(customer_id, order_id)
        if not evidence['found']:
            return None
        with self.engine.connect() as c:
            previous = c.execute(select(db.actions).where(and_(db.actions.c.order_id == order_id,
                db.actions.c.kind == 'refund'))).mappings().first()
            if previous:
                return dict(previous)
        row = dict(id=db.uid(), customer_id=customer_id, order_id=order_id, kind='refund',
            amount_cents=evidence['order']['total_cents'], status='proposed',
            requires_human=evidence['needs_review'], customer_confirmed=False,
            run_id=run_id, created_at=db.now())
        try:
            with self.engine.begin() as c:
                c.execute(db.actions.insert().values(**row))
                self.log(c, row['id'], 'system', 'proposed')
        except IntegrityError:
            # A concurrent request may have inserted the same order/kind.
            with self.engine.connect() as c:
                row = dict(c.execute(select(db.actions).where(and_(
                    db.actions.c.order_id == order_id, db.actions.c.kind == 'refund'))).mappings().one())
        return row

    @staticmethod
    def log(c, action_id, actor, event):
        c.execute(db.audit.insert().values(id=db.uid(), action_id=action_id, actor=actor,
            event=event, created_at=db.now()))

    def confirm(self, action_id, customer_id):
        with self.engine.begin() as c:
            row = c.execute(select(db.actions).where(and_(db.actions.c.id == action_id,
                db.actions.c.customer_id == customer_id))).mappings().first()
            if not row:
                raise KeyError('Action not found')
            if row['status'] != 'proposed':
                return dict(row)
            # Revalidate against current source of truth; never trust saved model evidence.
            evidence = self.tools.investigate(customer_id, row['order_id'])
            review = (row['requires_human'] or evidence['needs_review']
                      or evidence['order']['total_cents'] != row['amount_cents'])
            status = 'pending_review' if review else 'queued_simulation'
            changed = c.execute(db.actions.update().where(and_(db.actions.c.id == action_id,
                db.actions.c.status == 'proposed')).values(status=status,
                requires_human=review, customer_confirmed=True))
            if changed.rowcount:
                self.log(c, action_id, 'customer', 'confirmed')
                if not review:
                    self.enqueue(c, row)
            return dict(c.execute(select(db.actions).where(db.actions.c.id == action_id)).mappings().one())

    def decide(self, action_id, approve, reason):
        with self.engine.begin() as c:
            row = c.execute(select(db.actions).where(db.actions.c.id == action_id)).mappings().first()
            if not row:
                raise KeyError('Action not found')
            if row['status'] != 'pending_review' or not row['customer_confirmed']:
                raise Conflict('Only confirmed pending-review proposals can be decided')
            status = 'queued_simulation' if approve else 'rejected'
            changed = c.execute(db.actions.update().where(and_(db.actions.c.id == action_id,
                db.actions.c.status == 'pending_review')).values(status=status))
            if not changed.rowcount:
                raise Conflict('Action was already decided')
            self.log(c, action_id, 'human_operator', ('approved: ' if approve else 'rejected: ')+reason)
            if approve:
                self.enqueue(c, row)
            return {'id':action_id, 'status':status}

    @staticmethod
    def enqueue(c, row):
        c.execute(db.outbox.insert().values(id=db.uid(), action_id=row['id'],
            payload={'order_id':row['order_id'], 'amount_cents':row['amount_cents'],
                     'provider':'simulation', 'message':'No real payment is executed'},
            status='queued', created_at=db.now()))

    def drain(self):
        with self.engine.begin() as c:
            rows = c.execute(select(db.outbox).where(db.outbox.c.status == 'queued')).mappings().all()
            for row in rows:
                changed = c.execute(db.outbox.update().where(and_(db.outbox.c.id == row['id'],
                    db.outbox.c.status == 'queued')).values(status='completed_simulation'))
                if changed.rowcount:
                    c.execute(db.actions.update().where(db.actions.c.id == row['action_id'])
                              .values(status='completed_simulation'))
                    self.log(c, row['action_id'], 'simulation_worker', 'completed_simulation')
        return len(rows)
