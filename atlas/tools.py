"""Allowlisted domain tools; models never supply SQL or identity."""
from datetime import date
import httpx
from sqlalchemy import select, and_, func
from atlas import db


class Tools:
    def __init__(self, engine, config):
        self.engine, self.config = engine, config

    def profile(self, customer_id):
        with self.engine.connect() as c:
            row = c.execute(select(db.customers).where(db.customers.c.id == customer_id)).mappings().first()
            if not row:
                raise ValueError('Unknown customer')
            profile = dict(row)
            profile['previous_returns'] = c.scalar(select(func.count()).select_from(
                db.returns.join(db.orders)).where(db.orders.c.customer_id == customer_id))
            return profile

    def order(self, customer_id, order_id):
        if not order_id:
            return None
        with self.engine.connect() as c:
            row = c.execute(select(db.orders).where(and_(db.orders.c.id == order_id,
                db.orders.c.customer_id == customer_id))).mappings().first()
            return dict(row) if row else None

    def recent_orders(self, customer_id):
        with self.engine.connect() as c:
            return [dict(x) for x in c.execute(select(db.orders).where(
                db.orders.c.customer_id == customer_id).order_by(db.orders.c.id.desc()).limit(10)).mappings()]

    def investigate(self, customer_id, order_id):
        order = self.order(customer_id, order_id)
        if not order:
            return {'found':False, 'eligible':False,
                'reason':'Provide an order ID belonging to your account.', 'needs_review':False}
        profile = self.profile(customer_id)
        age = ((self.config.as_of_date - date.fromisoformat(order['delivered_at'])).days
               if order['delivered_at'] else None)
        eligible = (order['status'] == 'delivered' and age is not None and 0 <= age <= 30
                    and order['condition'] == 'unworn')
        reasons = []
        if order['status'] != 'delivered':
            reasons.append('Order is not recorded as delivered')
        if age is None:
            reasons.append('No verified delivery date')
        elif age < 0 or age > 30:
            reasons.append('Outside the 30-day return window')
        if order['condition'] != 'unworn':
            reasons.append('Item condition requires review')
        review = not eligible or order['total_cents'] > 15000 or profile['previous_returns'] >= 3
        return dict(found=True, order=order, age_days=age, eligible=eligible, needs_review=review,
            reason='; '.join(reasons) or 'Within window with verified unworn condition',
            previous_returns=profile['previous_returns'],
            review_reasons=reasons + (['Refund exceeds EUR 150'] if order['total_cents'] > 15000 else [])
            + (['Repeat-return review signal (not a fraud finding)'] if profile['previous_returns'] >= 3 else []))

    def catalog(self, size, category=None, budget_cents=None, style=None):
        query = select(db.products, db.variants.c.id.label('variant_id'), db.variants.c.size,
            db.variants.c.stock).join(db.variants).where(
                and_(db.variants.c.size == size, db.variants.c.stock > 0))
        if category:
            query = query.where(db.products.c.category == category)
        if budget_cents is not None:
            query = query.where(db.products.c.price_cents <= budget_cents)
        with self.engine.connect() as c:
            rows = [dict(x) for x in c.execute(query).mappings()]
        rows.sort(key=lambda p: (p['style'] != style, p['price_cents'], p['id']))
        return rows[:30]

    def shipment(self, customer_id, order_id):
        order = self.order(customer_id, order_id)
        if not order:
            return {'found':False, 'reason':'Provide an order ID belonging to your account.'}
        with self.engine.connect() as c:
            record = c.execute(select(db.shipments).where(db.shipments.c.order_id == order_id)).mappings().first()
        if not record:
            return {'found':True, 'status':'unknown', 'source':'No synchronized shipment record'}
        cached = dict(record)
        if self.config.carrier_base_url:
            try:
                # Operator-configured origin only; order ID has already passed ownership validation.
                r = httpx.get(self.config.carrier_base_url.rstrip('/')+'/shipments/'+record['id'],
                    headers={'Authorization':'Bearer '+self.config.carrier_api_key}, timeout=5)
                r.raise_for_status()
                live = r.json()
                if live.get('status') not in {'in_transit','delivered','delayed','lost'}:
                    raise ValueError('Invalid carrier payload')
                cached.update(status=live['status'], source='live carrier API')
                return {'found':True, **cached}
            except (httpx.HTTPError, ValueError):
                cached['warning'] = 'Carrier unavailable; showing last synchronized status'
        return {'found':True, **cached, 'source':'cached mock carrier record'}

    def memory(self, session_id, agent, limit=6):
        with self.engine.connect() as c:
            rows = c.execute(select(db.messages.c.content).where(and_(
                db.messages.c.session_id == session_id, db.messages.c.agent == agent))
                .order_by(db.messages.c.created_at.desc()).limit(limit)).scalars().all()
        return list(reversed(rows))

    def remember(self, session_id, agent, role, content):
        with self.engine.begin() as c:
            c.execute(db.messages.insert().values(id=db.uid(), session_id=session_id, agent=agent,
                role=role, content=content, created_at=db.now()))
