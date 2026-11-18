from django.conf import settings


class BotRouter:
    """Models de cada bot vão pro banco com o nome do app; o resto fica no 'default'."""

    def _banco(self, app_label):
        return app_label if app_label in settings.BOTS_COM_BANCO else 'default'

    def db_for_read(self, model, **hints):
        return self._banco(model._meta.app_label)

    def db_for_write(self, model, **hints):
        return self._banco(model._meta.app_label)

    def allow_relation(self, obj1, obj2, **hints):
        # SQLite não tem chave estrangeira entre arquivos diferentes
        return self._banco(obj1._meta.app_label) == self._banco(obj2._meta.app_label)

    def allow_migrate(self, db, app_label, **hints):
        return db == self._banco(app_label)
