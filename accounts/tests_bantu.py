"""Helpers shared by the tests."""


def kode_hapus(client, nama):
    """The delete code (accounts/captcha_hapus.py) for ``nama`` as POST data:
    the one the confirmation dialog put in the session, else a fresh one."""
    sesi = client.session
    kunci = f"captcha_hapus:{nama}"
    if kunci not in sesi:
        sesi[kunci] = "246810"
        sesi.save()
    return {"captcha": sesi[kunci]}
