"""Paging shared by every table: at most PER_HALAMAN rows per page."""
from django.core.paginator import Paginator

PER_HALAMAN = 15


def halaman(request, data, param="page", **ganti):
    """The requested page of ``data`` (a queryset or list).

    ``param`` names the page's query parameter, so two tables on one page can
    page independently. The page gets ``query_dasar``: the current query string
    without ``param`` (with ``ganti`` values set), ready for ``?{{ query_dasar }}page=N``,
    and ``param`` for the pagination template.
    """
    page = Paginator(data, PER_HALAMAN).get_page(request.GET.get(param))
    query = request.GET.copy()
    query.pop(param, None)
    for kunci, nilai in ganti.items():
        query[kunci] = nilai
    dasar = query.urlencode()
    page.query_dasar = f"{dasar}&" if dasar else ""
    page.param = param
    page.rentang = list(page.paginator.get_elided_page_range(page.number, on_each_side=1, on_ends=1))
    return page
