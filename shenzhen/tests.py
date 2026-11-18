from types import SimpleNamespace

from django.contrib.auth.models import User
from django.test import SimpleTestCase

from main.models import Agendamento

from .routers import BotRouter


def model(app_label):
    return SimpleNamespace(_meta=SimpleNamespace(app_label=app_label))


class BotRouterTest(SimpleTestCase):
    def test_cada_bot_no_seu_banco(self):
        r = BotRouter()
        for app in ("braga", "news_", "fucador"):
            self.assertEqual(r.db_for_write(model(app)), app)
            self.assertTrue(r.allow_migrate(app, app))
            self.assertFalse(r.allow_migrate("default", app))
        self.assertEqual(r.db_for_read(User), "default")
        self.assertEqual(r.db_for_write(Agendamento), "default")
        self.assertFalse(r.allow_migrate("braga", "auth"))
        self.assertTrue(r.allow_migrate("default", "auth"))
        self.assertFalse(r.allow_relation(model("braga"), model("fucador")))
        self.assertTrue(r.allow_relation(model("braga"), model("braga")))
