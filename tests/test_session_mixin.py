from unittest.mock import Mock

from tornado_sqlalchemy import MissingDatabaseSettingError, SessionMixin

from ._common import BaseTestCase, User, db


class SessionMixinTestCase(BaseTestCase):
    def test_mixin_ok(self):
        class GoodHandler(SessionMixin):
            def __init__(h_self):
                h_self.application = Mock()
                h_self.application.settings = {'db': db}

            def run(h_self):
                with h_self.make_session() as session:
                    return session.query(User).count()

        self.assertEqual(GoodHandler().run(), 0)

    def test_mixin_no_db(self):
        class BadHandler(SessionMixin):
            def __init__(h_self):
                h_self.application = Mock()
                h_self.application.settings = {}

            def run(h_self):
                with h_self.make_session() as session:
                    return session.query(User).count()

        self.assertRaises(MissingDatabaseSettingError, BadHandler().run)

    def test_distinct_sessions(self):
        sessions = set()

        class Handler(SessionMixin):
            def __init__(h_self):
                db.configure(url=self.db_url)

                h_self.application = Mock()
                h_self.application.settings = {'db': db}

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
