from unittest import TestCase

from sqlalchemy import BigInteger, Column, String
from tornado.gen import coroutine
from tornado.testing import AsyncHTTPTestCase
from tornado.web import Application, RequestHandler

from tornado_sqlalchemy import (MissingFactoryError, SessionMixin, as_future,
                                declarative_base, make_session_factory)

try:
    from unittest.mock import Mock
except ImportError:
    from mock import Mock

postgres_url = 'postgres://t_sa:t_sa@localhost/t_sa'

mysql_url = 'mysql://t_sa:t_sa@localhost/t_sa'

sqlite_url = 'sqlite:///t_sa.sqlite3'

Base = declarative_base()


class User(Base):
    __tablename__ = 'users'

    id = Column(BigInteger, primary_key=True)
    username = Column(String(64), unique=True)

    def __init__(self, username):
        self.username = username


class BaseTestCase(TestCase):
    def setUp(self):
        self.factory = make_session_factory(postgres_url)

        Base.metadata.create_all(self.factory.engine)

    def tearDown(self):
        Base.metadata.drop_all(self.factory.engine)


class FactoryTestCase(TestCase):
    def _test_with_factory(self, factory):
        self.assertTrue(factory)

        Base.metadata.create_all(factory.engine)

        session = factory.make_session()

        self.assertTrue(session)
        self.assertEqual(session.query(User).count(), 0)

        session.close()

        Base.metadata.drop_all(factory.engine)

    def test_make_mysql_factoy(self):
        self._test_with_factory(make_session_factory(mysql_url))

    def test_make_postgres_factory(self):
        self._test_with_factory(make_session_factory(postgres_url))

    def test_make_sqlite_factory(self):
        self._test_with_factory(make_session_factory(sqlite_url))


class SessionFactoryTestCase(BaseTestCase):
    def test_make_session(self):
        session = self.factory.make_session()

        self.assertTrue(session)
        self.assertEqual(session.query(User).count(), 0)

        session.close()


class SessionMixinTestCase(BaseTestCase):
    def test_mixin_ok(self):
        class GoodHandler(SessionMixin):
            def __init__(h_self):
                h_self.application = Mock()
                h_self.application.settings = {'session_factory': self.factory}

            def run(h_self):
                with h_self.make_session() as session:
                    return session.query(User).count()

        self.assertEqual(GoodHandler().run(), 0)

    def test_mixin_no_session_factory(self):
        class BadHandler(SessionMixin):
            def __init__(h_self):
                h_self.application = Mock()
                h_self.application.settings = {}

            def run(h_self):
                with h_self.make_session() as session:
                    return session.query(User).count()

        self.assertRaises(MissingFactoryError, BadHandler().run)

    def test_distinct_sessions(self):
        sessions = set()

        class Handler(SessionMixin):
            def __init__(h_self):
                h_self.application = Mock()
                h_self.application.settings = {'session_factory': self.factory}

            def run(h_self):
                session = h_self.session

                sessions.add(id(session))
                value = session.query(User).count()

                session.commit()
                session.close()

                return value

        Handler().run()
        Handler().run()

        self.assertEqual(len(sessions), 2)


class RequestHandlersTestCase(AsyncHTTPTestCase):
    def __init__(self, *args, **kwargs):
        super(RequestHandlersTestCase, self).__init__(*args, **kwargs)

        class WithoutMixinRequestHandler(RequestHandler):
            def get(h_self):
                with h_self.make_session() as session:
                    count = session.query(User).count()

                h_self.write(str(count))

        class WithMixinRequestHandler(SessionMixin, RequestHandler):
            def get(h_self):
                with h_self.make_session() as session:
                    count = session.query(User).count()

                h_self.write(str(count))

        class GenCoroutinesRequestHandler(SessionMixin, RequestHandler):
            @coroutine
            def get(h_self):
                with h_self.make_session() as session:
                    count = yield as_future(session.query(User).count)

                h_self.write(str(count))

        class NativeCoroutinesRequestHandler(SessionMixin, RequestHandler):
            async def get(h_self):
                with h_self.make_session() as session:
                    count = await as_future(session.query(User).count)

                h_self.write(str(count))

        class UsesSelfSessionRequestHandler(SessionMixin, RequestHandler):
            def get(h_self):
                h_self.write(str(h_self.session.query(User).count()))

        handlers = (
            (r'/gen-coroutines', GenCoroutinesRequestHandler),
            (r'/native-coroutines', NativeCoroutinesRequestHandler),
            (r'/uses-self-session', UsesSelfSessionRequestHandler),
            (r'/with-mixin', WithMixinRequestHandler),
            (r'/without-mixin', WithoutMixinRequestHandler),
        )

        self._factory = make_session_factory(postgres_url)
        self._application = Application(
            handlers, session_factory=self._factory)

    def setUp(self, *args, **kwargs):
        super(RequestHandlersTestCase, self).setUp(*args, **kwargs)

        Base.metadata.create_all(self._factory.engine)

    def tearDown(self, *args, **kwargs):
        Base.metadata.drop_all(self._factory.engine)

        super(RequestHandlersTestCase, self).tearDown(*args, **kwargs)

    def get_app(self):
        return self._application

    def test_gen_coroutines(self):
        response = self.fetch('/gen-coroutines', method='GET')

        self.assertEqual(response.code, 200)
        self.assertEqual(response.body.decode('utf-8'), '0')

    def test_native_coroutines(self):
        response = self.fetch('/native-coroutines', method='GET')

        self.assertEqual(response.code, 200)
        self.assertEqual(response.body.decode('utf-8'), '0')

    def test_with_mixin(self):
        response = self.fetch('/with-mixin', method='GET')

        self.assertEqual(response.code, 200)
        self.assertEqual(response.body.decode('utf-8'), '0')

    def test_without_mixin(self):
        response = self.fetch('/without-mixin', method='GET')
        self.assertEqual(response.code, 500)

    def test_uses_self_session(self):
        response = self.fetch('/uses-self-session', method='GET')

        self.assertEqual(response.code, 200)
        self.assertEqual(response.body.decode('utf-8'), '0')


class DeclarativeBaseTestCase(TestCase):
    def test_multiple_calls_return_the_same_instance(self):
        first = declarative_base()
        second = declarative_base()

        self.assertTrue(first is second)
        self.assertEqual(id(first), id(second))
