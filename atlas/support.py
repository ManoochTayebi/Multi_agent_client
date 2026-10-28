"""Persistent human conversations; no model, financial permission or external helpdesk."""
from sqlalchemy import select, and_
from sqlalchemy.exc import IntegrityError
from atlas import db
from atlas.actions import Conflict


class Support:
    def __init__(self, engine):
        self.engine = engine

    def for_session(self, session_id):
        with self.engine.connect() as c:
            row = c.execute(select(db.support_threads).where(
                db.support_threads.c.session_id == session_id)).mappings().first()
        return dict(row) if row else None

    def get(self, thread_id):
        with self.engine.connect() as c:
            row = c.execute(select(db.support_threads).where(
                db.support_threads.c.id == thread_id)).mappings().first()
        if not row:
            raise KeyError('Support conversation not found')
        return dict(row)

    @staticmethod
    def event(c, thread_id, actor, event, reason):
        c.execute(db.support_events.insert().values(thread_id=thread_id, actor=actor,
            event=event, reason=reason, created_at=db.now()))

    @staticmethod
    def message(c, thread_id, sender, text):
        c.execute(db.support_messages.insert().values(thread_id=thread_id, sender=sender,
            text=text, created_at=db.now()))

    def request(self, session_id, customer_id, reason, initial_message=None):
        """One durable thread per session; duplicate requests do not duplicate queue entries."""
        try:
            with self.engine.begin() as c:
                row = c.execute(select(db.support_threads).where(
                    db.support_threads.c.session_id == session_id)).mappings().first()
                if row and row['status'] != 'closed':
                    return dict(row)
                if row:
                    thread_id = row['id']
                    c.execute(db.support_threads.update().where(db.support_threads.c.id == thread_id)
                        .values(status='waiting', reason=reason, updated_at=db.now()))
                    event = 'reopened'
                else:
                    thread_id = db.uid()
                    c.execute(db.support_threads.insert().values(id=thread_id, session_id=session_id,
                        customer_id=customer_id, status='waiting', reason=reason,
                        created_at=db.now(), updated_at=db.now()))
                    event = 'requested'
                self.event(c, thread_id, 'system' if reason != 'customer_request' else 'customer', event, reason)
                if initial_message:
                    self.message(c, thread_id, 'customer', initial_message)
            return self.get(thread_id)
        except IntegrityError:
            # The unique session constraint also protects requests outside this API process.
            existing = self.for_session(session_id)
            if not existing:
                raise
            return existing

    def post(self, thread_id, sender, text):
        with self.engine.begin() as c:
            allowed = ['active'] if sender == 'operator' else ['waiting', 'active']
            changed = c.execute(db.support_threads.update().where(and_(
                db.support_threads.c.id == thread_id, db.support_threads.c.status.in_(allowed)))
                .values(updated_at=db.now()))
            if not changed.rowcount:
                raise Conflict('Conversation must be open; an operator must take over before replying')
            self.message(c, thread_id, sender, text)

    def claim(self, thread_id):
        with self.engine.begin() as c:
            changed = c.execute(db.support_threads.update().where(and_(
                db.support_threads.c.id == thread_id, db.support_threads.c.status == 'waiting'))
                .values(status='active', updated_at=db.now()))
            if changed.rowcount:
                self.event(c, thread_id, 'human_operator', 'claimed', 'Operator took over the conversation')
            elif self.get(thread_id)['status'] != 'active':
                raise Conflict('Closed conversations cannot be taken over')
        return self.get(thread_id)

    def close(self, thread_id, actor, reason):
        with self.engine.begin() as c:
            changed = c.execute(db.support_threads.update().where(and_(
                db.support_threads.c.id == thread_id, db.support_threads.c.status != 'closed'))
                .values(status='closed', updated_at=db.now()))
            if changed.rowcount:
                self.event(c, thread_id, actor, 'closed', reason)
                self.message(c, thread_id, 'system', 'Human support closed: '+reason)
        return self.get(thread_id)

    def detail(self, thread_id):
        thread = self.get(thread_id)
        with self.engine.connect() as c:
            messages = [dict(x) for x in c.execute(select(db.support_messages).where(
                db.support_messages.c.thread_id == thread_id).order_by(db.support_messages.c.id)).mappings()]
            events = [dict(x) for x in c.execute(select(db.support_events).where(
                db.support_events.c.thread_id == thread_id).order_by(db.support_events.c.id)).mappings()]
        return {'thread':thread, 'messages':messages, 'events':events}
