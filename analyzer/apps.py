from django.apps import AppConfig
from django.db.models.signals import post_migrate


def activar_rls_supabase(using='default', **kwargs):
    """Activa Row Level Security en todas las tablas del esquema public.

    En Supabase, las tablas de 'public' se publican en su API REST y el rol
    'anon' (cuya llave va en el navegador) puede leerlas. Con RLS activo y sin
    políticas, esa API no ve nada. Django se conecta como 'postgres', que tiene
    BYPASSRLS, así que la app sigue funcionando igual. Corre después de cada
    migrate, así cubre también las tablas nuevas.
    """
    from django.db import connections
    conexion = connections[using]
    if conexion.vendor != 'postgresql':
        return
    with conexion.cursor() as c:
        c.execute("SELECT 1 FROM pg_roles WHERE rolname = 'anon'")
        if not c.fetchone():  # no es Supabase
            return
        c.execute("""
            SELECT c.relname FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind = 'r' AND NOT c.relrowsecurity
        """)
        for (tabla,) in c.fetchall():
            c.execute(f'ALTER TABLE public."{tabla}" ENABLE ROW LEVEL SECURITY')


def vigilar_env(sender, **kwargs):
    """runserver se reinicia solo al guardar el .env (llaves, BD), no solo los .py."""
    from django.conf import settings
    sender.watch_dir(settings.BASE_DIR, '.env')


class AnalyzerConfig(AppConfig):
    name = 'analyzer'

    def ready(self):
        from django.utils.autoreload import autoreload_started
        post_migrate.connect(activar_rls_supabase, sender=self)
        autoreload_started.connect(vigilar_env)
