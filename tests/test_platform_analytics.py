"""Super-admin revenue & growth analytics."""
from datetime import date, timedelta

from models.platform import Payment, Subscription, Plan
from tests.factories import make_school, make_platform_user, make_student
from services import platform as plat


def test_revenue_analytics_aggregates(app, db):
    s = make_school(db, slug='s')
    p = Plan(name='Pro', price_ghs=400)
    db.session.add(p); db.session.flush()
    db.session.add(Payment(school_id=s.id, plan_id=p.id, reference='R1',
                           amount_pesewas=40000, status='success',
                           paid_at=date.today()))
    db.session.add(Payment(school_id=s.id, plan_id=p.id, reference='R2',
                           amount_pesewas=10000, status='failed'))  # ignored
    make_student(db, s, admission_no='A1')
    db.session.commit()
    data = plat.revenue_analytics(months=6)
    # success revenue this month = 400
    this_month = f'{date.today().year:04d}-{date.today().month:02d}'
    rev = dict(data['revenue_by_month'])
    assert rev[this_month] == 400
    assert len(data['recent_payments']) == 1     # only the successful one
    assert data['students_per_school'][0][1] == 1


def test_expiring_soon(app, db):
    s = make_school(db, slug='s')
    p = Plan(name='Pro', price_ghs=400)
    db.session.add(p); db.session.flush()
    db.session.add(Subscription(school_id=s.id, plan_id=p.id, status='active',
                                ends_on=date.today() + timedelta(days=5)))
    db.session.add(Subscription(school_id=s.id, plan_id=p.id, status='active',
                                ends_on=date.today() + timedelta(days=90)))  # not soon
    db.session.commit()
    data = plat.revenue_analytics()
    assert len(data['expiring_soon']) == 1


def test_analytics_page_renders(app, db, client):
    make_platform_user(db, email='super@x.test')
    make_school(db, slug='s')
    db.session.commit()
    client.post('/auth/login', data={'school_slug': '', 'email': 'super@x.test',
                                     'password': 'pw'})
    assert client.get('/platform/analytics').status_code == 200
