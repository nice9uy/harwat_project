"""Live badges: who waits for activation is announced on every change that
matters, reaches the open streams, and the stream is for those allowed only."""
import asyncio
from unittest import mock

from django.contrib.auth.models import Group, User
from django.test import TestCase, TransactionTestCase

from accounts import realtime


class KabarAktivasiTests(TestCase):
    def _kabar(self, aksi):
        with mock.patch.object(realtime, "_terbitkan") as terbit, self.captureOnCommitCallbacks(execute=True):
            aksi()
        return [c.args[0] for c in terbit.call_args_list]

    def test_changes_that_matter_are_announced(self):
        ketua = User.objects.create_user(username="calon", password="x", is_active=False)
        self.assertIn("aktivasi", self._kabar(lambda: ketua.groups.add(Group.objects.get(name="Ketua Tim"))))

        def aktifkan():
            ketua.is_active = True
            ketua.save(update_fields=["is_active"])
        self.assertIn("aktivasi", self._kabar(aktifkan))
        self.assertIn("aktivasi", self._kabar(lambda: User.objects.create_user(username="baru", password="x")))
        self.assertIn("aktivasi", self._kabar(ketua.delete))

    def test_a_sign_in_is_not(self):
        user = User.objects.create_user(username="u", password="x")
        self.assertEqual(self._kabar(lambda: user.save(update_fields=["last_login"])), [])


class SebaranTests(TransactionTestCase):
    def test_a_notice_reaches_every_open_stream_of_the_process(self):
        async def jalan():
            a, b = realtime.langganan(), realtime.langganan()
            tunggu = [asyncio.ensure_future(a.__anext__()), asyncio.ensure_future(b.__anext__())]
            await asyncio.sleep(0)
            self.assertEqual(realtime.jumlah_aliran(), 2)
            realtime._bangunkan("aktivasi")
            hasil = await asyncio.wait_for(asyncio.gather(*tunggu), 1)
            await a.aclose()
            await b.aclose()
            return hasil

        with mock.patch.dict("os.environ", {"REDIS_URL": ""}):
            self.assertEqual(asyncio.run(jalan()), ["aktivasi", "aktivasi"])
        # A closed stream holds nothing any more.
        self.assertEqual(realtime.jumlah_aliran(), 0)


class AliranAksesTests(TestCase):
    def test_the_stream_needs_a_user_with_the_aktivasi_menu(self):
        from django_bolt.testing import TestClient

        from accounts.api import api

        with TestClient(api) as klien:
            self.assertEqual(klien.get("/sse/aktivasi").status_code, 403)


class LencanaBersamaTests(TestCase):
    def test_one_count_per_notice_shared_by_the_streams(self):
        from accounts import api

        api._lencana_terakhir.clear()
        with mock.patch.object(api, "_render_lencana", side_effect=lambda m: f"n{realtime.versi('aktivasi')}") as hitung:
            async def jalan():
                pertama = await asyncio.gather(*(api._lencana_bersama("darat") for _ in range(50)))
                realtime._bangunkan("aktivasi")
                kedua = await asyncio.gather(*(api._lencana_bersama("darat") for _ in range(50)))
                return pertama, kedua
            pertama, kedua = asyncio.run(jalan())
        # 50 streams, 2 states of the data: counted twice, never stale after a notice.
        self.assertEqual(hitung.call_count, 2)
        self.assertEqual(set(pertama), {pertama[0]})
        self.assertNotEqual(pertama[0], kedua[0])
