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

        # A Tim member's biodata keeps their Ketua Tim's Satuan, and a Ketua
        # Tim's team follows a change of theirs (accounts/satuan_tim.py).
        from .models import Laporan
        post_save.connect(_satuan_tim, sender=Laporan, dispatch_uid="accounts_satuan_tim")

        # The live Aktivasi Ketua Tim badge (accounts/realtime.py).
        from django.db.models.signals import m2m_changed
        post_save.connect(_kabar_aktivasi_simpan, sender=User, dispatch_uid="accounts_kabar_aktivasi_simpan")
        post_delete.connect(_kabar_aktivasi, sender=User, dispatch_uid="accounts_kabar_aktivasi_hapus")
        m2m_changed.connect(_kabar_aktivasi, sender=User.groups.through, dispatch_uid="accounts_kabar_aktivasi_grup")


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


def _kabar_aktivasi(sender, **kwargs):
    """Who waits for activation may have changed: the open badges recount."""
    if kwargs.get("action", "post_").startswith("post_"):
        from .realtime import kabarkan
        kabarkan("aktivasi")


def _kabar_aktivasi_simpan(sender, update_fields=None, raw=False, **kwargs):
    # A sign-in only touches last_login: nothing to tell.
    if not raw and (update_fields is None or "is_active" in update_fields):
        _kabar_aktivasi(sender)


def _satuan_tim(sender, instance, raw=False, **kwargs):
    if raw or instance.akun_id is None:
        return
    from .satuan_tim import samakan
    samakan(instance.akun)
