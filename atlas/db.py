"""SQL persistence; every customer lookup is scoped by authenticated customer ID."""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import (JSON, Boolean, Column, DateTime, ForeignKey, Integer, MetaData,
                        String, Table, Text, UniqueConstraint, create_engine, event)
from sqlalchemy.pool import StaticPool

metadata = MetaData()
customers = Table('customers', metadata, Column('id', String, primary_key=True),
    Column('name', String, nullable=False), Column('tier', String), Column('size', String),
    Column('style', String), Column('country', String))
products = Table('products', metadata, Column('id', String, primary_key=True),
    Column('name', String), Column('category', String), Column('style', String),
    Column('color', String), Column('price_cents', Integer), Column('description', Text))
variants = Table('variants', metadata, Column('id', String, primary_key=True),
    Column('product_id', ForeignKey('products.id'), nullable=False), Column('size', String),
    Column('stock', Integer, nullable=False))
orders = Table('orders', metadata, Column('id', String, primary_key=True),
    Column('customer_id', ForeignKey('customers.id'), nullable=False),
    Column('variant_id', ForeignKey('variants.id'), nullable=False), Column('quantity', Integer),
    Column('total_cents', Integer), Column('purchased_at', String), Column('delivered_at', String),
    Column('status', String), Column('condition', String), Column('channel', String))
shipments = Table('shipments', metadata, Column('id', String, primary_key=True),
    Column('order_id', ForeignKey('orders.id'), unique=True), Column('status', String),
    Column('estimated_delivery', String), Column('carrier', String))
returns = Table('returns', metadata, Column('id', String, primary_key=True),
    Column('order_id', ForeignKey('orders.id')), Column('reason', String), Column('status', String))
sessions = Table('sessions', metadata, Column('id', String, primary_key=True),
    Column('customer_id', ForeignKey('customers.id')), Column('token_hash', String, unique=True),
    Column('created_at', DateTime(timezone=True)), Column('expires_at', DateTime(timezone=True)))
messages = Table('messages', metadata, Column('id', String, primary_key=True),
    Column('session_id', ForeignKey('sessions.id')), Column('agent', String),
    Column('role', String), Column('content', JSON), Column('created_at', DateTime(timezone=True)))
runs = Table('runs', metadata, Column('id', String, primary_key=True),
    Column('session_id', ForeignKey('sessions.id')), Column('status', String),
    Column('result', JSON), Column('latency_ms', Integer), Column('created_at', DateTime(timezone=True)))
actions = Table('actions', metadata, Column('id', String, primary_key=True),
    Column('customer_id', ForeignKey('customers.id')), Column('order_id', ForeignKey('orders.id')),
    Column('kind', String), Column('amount_cents', Integer), Column('status', String),
    Column('requires_human', Boolean), Column('customer_confirmed', Boolean, default=False),
    Column('run_id', String), Column('created_at', DateTime(timezone=True)),
    UniqueConstraint('order_id', 'kind', name='one_resolution_per_order'))
audit = Table('audit', metadata, Column('id', String, primary_key=True),
    Column('action_id', ForeignKey('actions.id')), Column('actor', String), Column('event', String),
    Column('created_at', DateTime(timezone=True)))
outbox = Table('outbox', metadata, Column('id', String, primary_key=True),
    Column('action_id', ForeignKey('actions.id'), unique=True), Column('payload', JSON),
    Column('status', String), Column('created_at', DateTime(timezone=True)))
support_threads = Table('support_threads', metadata, Column('id', String, primary_key=True),
    Column('session_id', ForeignKey('sessions.id'), nullable=False, unique=True),
    Column('customer_id', ForeignKey('customers.id'), nullable=False),
    Column('status', String, nullable=False), Column('reason', String, nullable=False),
    Column('created_at', DateTime(timezone=True)), Column('updated_at', DateTime(timezone=True)))
support_messages = Table('support_messages', metadata, Column('id', Integer, primary_key=True),
    Column('thread_id', ForeignKey('support_threads.id'), nullable=False),
    Column('sender', String, nullable=False), Column('text', Text, nullable=False),
    Column('created_at', DateTime(timezone=True)))
support_events = Table('support_events', metadata, Column('id', Integer, primary_key=True),
    Column('thread_id', ForeignKey('support_threads.id'), nullable=False),
    Column('actor', String, nullable=False), Column('event', String, nullable=False),
    Column('reason', Text, nullable=False), Column('created_at', DateTime(timezone=True)))


def now():
    return datetime.now(timezone.utc)


def uid():
    return str(uuid4())


def make_engine(url):
    args = {'connect_args': {'check_same_thread': False, 'timeout': 30}} if url.startswith('sqlite') else {}
    if url == 'sqlite://':
        args['poolclass'] = StaticPool
    engine = create_engine(url, pool_pre_ping=True, **args)
    if url.startswith('sqlite'):
        @event.listens_for(engine, 'connect')
        def foreign_keys(connection, _):
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA journal_mode=WAL')
    metadata.create_all(engine)
    return engine
