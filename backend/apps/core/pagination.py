"""
Pagination classes.

Two strategies, chosen deliberately:

* StandardPagination (page numbers) — for browsable, relatively static lists
  such as photographers or products. Users expect "page 3 of 10".

* TimelineCursorPagination (cursors) — for chat and notifications, where new
  rows are inserted constantly at the top. Page numbers there would cause
  items to shift between pages and be shown twice or skipped.
"""

from collections import OrderedDict

from rest_framework.pagination import CursorPagination, PageNumberPagination
from rest_framework.response import Response


class StandardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response(
            OrderedDict(
                [
                    ("data", data),
                    (
                        "meta",
                        {
                            "pagination": {
                                "page": self.page.number,
                                "page_size": self.get_page_size(self.request),
                                "total_pages": self.page.paginator.num_pages,
                                "total_items": self.page.paginator.count,
                                "has_next": self.page.has_next(),
                                "has_previous": self.page.has_previous(),
                                "next": self.get_next_link(),
                                "previous": self.get_previous_link(),
                            }
                        },
                    ),
                ]
            )
        )


class LargePagination(StandardPagination):
    """For admin tables and exports."""

    page_size = 50
    max_page_size = 500


class TimelineCursorPagination(CursorPagination):
    page_size = 30
    max_page_size = 100
    page_size_query_param = "page_size"
    ordering = "-created_at"

    def get_paginated_response(self, data):
        return Response(
            OrderedDict(
                [
                    ("data", data),
                    (
                        "meta",
                        {
                            "pagination": {
                                "page_size": self.get_page_size(self.request),
                                "next": self.get_next_link(),
                                "previous": self.get_previous_link(),
                                "has_next": self.get_next_link() is not None,
                            }
                        },
                    ),
                ]
            )
        )
