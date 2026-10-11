from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    def ready(self):
        from django.contrib.auth.models import User
        from django.db.models.signals import post_save

        post_save.connect(_buat_akun_publik, sender=User, dispatch_uid="accounts_akun_publik")

        from django.db.models.signals import post_delete
        from .models import VpnPeer
        post_save.connect(_tulis_vpn, sender=VpnPeer, dispatch_uid="accounts_vpn_simpan")
        post_delete.connect(_tulis_vpn, sender=VpnPeer, dispatch_uid="accounts_vpn_hapus")


def _tulis_vpn(sender, **kwargs):
    """Every change to a peer rewrites the WireGuard server's config."""
    from django.db import transaction
    from .vpn_utils import tulis_server_conf
    transaction.on_commit(tulis_server_conf)


def _buat_akun_publik(sender, instance, created, raw=False, **kwargs):
    """Every user gets a public UUID (AkunPublik) for use in URLs."""
    if created and not raw:
        from .models import AkunPublik
        AkunPublik.objects.get_or_create(user=instance)
