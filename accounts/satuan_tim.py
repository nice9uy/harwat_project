"""A Tim member's Satuan follows their Ketua Tim's.

The reports and the dashboard credit work to the Satuan on the worker's
biodata (Laporan.satuan): a vehicle a member added counts for the member's
unit. A team works for its Ketua Tim's unit, so a member's Satuan is kept the
same as their Ketua Tim's, on the account (AkunPublik.satuan) and on every
biodata of theirs, whenever it could drift apart: a member added or moved to
another team, a member's own biodata or account saved, a Ketua Tim's Satuan
changed (their whole team follows). `manage.py samakan_satuan_tim` brings data
from before this into line.
"""
from .models import AkunPublik, Anggota, Laporan


def satuan_ketua(ketua):
    """A Ketua Tim's Satuan: their account's, else their newest biodata's."""
    satuan = AkunPublik.objects.filter(user=ketua).values_list("satuan", flat=True).first()
    if satuan:
        return satuan
    return Laporan.objects.filter(akun=ketua).order_by("-dibuat_pada").values_list("satuan", flat=True).first()


def ketua_dari(user):
    """The Ketua Tim (a User) whose team ``user`` is in, or None."""
    node = Anggota.objects.filter(user=user, depth=2).first()
    return node.get_parent().user if node is not None else None


def satuan_tim(user):
    """The Satuan pk ``user`` must have as a Tim member, or None (not a member,
    or their Ketua Tim has no Satuan yet)."""
    ketua = ketua_dari(user)
    return satuan_ketua(ketua) if ketua is not None else None


def _terapkan(user_ids, satuan):
    if not satuan or not user_ids:
        return 0
    n = AkunPublik.objects.filter(user__in=user_ids).exclude(satuan=satuan).update(satuan=satuan)
    n += Laporan.objects.filter(akun__in=user_ids).exclude(satuan=satuan).update(satuan=satuan)
    return n


def samakan_anggota(user):
    """``user``, a Tim member, onto their Ketua Tim's Satuan."""
    return _terapkan([user.pk], satuan_tim(user))


def samakan_tim(ketua):
    """Every member of ``ketua``'s team onto ``ketua``'s Satuan."""
    node = Anggota.objects.filter(user=ketua, depth=1).first()
    if node is None:
        return 0
    anggota = list(node.get_children().values_list("user_id", flat=True))
    return _terapkan(anggota, satuan_ketua(ketua))


def samakan(user):
    """After ``user``'s Satuan or team may have changed: a Ketua Tim's team
    follows them; a member follows their Ketua Tim."""
    if Anggota.objects.filter(user=user, depth=1).exists():
        return samakan_tim(user)
    return samakan_anggota(user)
