"""Report Center API: ``/v1/reports/`` (catalogue) and ``/v1/reports/<key>/`` (one report, JSON or download)."""
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from . import entitlements
from . import models as m
from . import reports
from .scoping import ALL_STAFF, staff_condo_ids

CONTENT_TYPES = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def allowed_sites(user):
    """Sites the user may report on: every active site for superusers, else the ones they are staff of."""
    if user.is_superuser:
        return m.Condominium.objects.filter(is_active=True).order_by("name")
    return m.Condominium.objects.filter(pk__in=staff_condo_ids(user, ALL_STAFF)).order_by("name")


def chosen_sites(request):
    """``?condominium=<id>``; superusers may also pass several ids (``1,2``) or ``all``."""
    raw = request.query_params.get("condominium", "").strip()
    allowed = allowed_sites(request.user)
    if raw == "all" and request.user.is_superuser:
        sites = list(allowed)
    else:
        try:
            ids = {int(part) for part in raw.split(",") if part.strip()}
        except ValueError:
            raise ValidationError({"condominium": "Site ids must be numbers."})
        if not ids:
            raise ValidationError({"condominium": "Choose a site."})
        if len(ids) > 1 and not request.user.is_superuser:
            raise PermissionDenied("Only platform admins can combine several sites in one report.")
        sites = list(allowed.filter(pk__in=ids))
        if len(sites) != len(ids):
            raise PermissionDenied("You can only report on your own site.")
    if not sites:
        raise PermissionDenied("No site to report on.")
    return sites


def _int(value, default):
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


class ReportCatalogView(APIView):
    @extend_schema(operation_id="reports_catalog", responses=OpenApiTypes.OBJECT)
    def get(self, request):
        """The reports, their filters and search tokens, and the sites this user can report on."""
        sites = allowed_sites(request.user)
        if not sites.exists():
            raise PermissionDenied("Reports are for condominium staff.")
        return Response({
            "reports": [r.catalog() for r in reports.REPORTS.values()],
            "sites": [{"id": c.pk, "name": c.name} for c in sites],
            "can_combine": request.user.is_superuser,
            "max_days": reports.MAX_DAYS,
            "print_max_rows": reports.PRINT_MAX_ROWS,
        })


class ReportView(APIView):
    @extend_schema(
        parameters=[
            OpenApiParameter("condominium", str, required=True, description="Site id; superusers: ids comma-separated or `all`."),
            OpenApiParameter("date_from", str, description="YYYY-MM-DD (default: 6 days before date_to)"),
            OpenApiParameter("date_to", str, description="YYYY-MM-DD (default: today)"),
            OpenApiParameter("q", str, description='Smart search: words and key:value tokens, e.g. unit:05-12 plate:SGX "Ace Aircon"'),
            OpenApiParameter("page", int), OpenApiParameter("page_size", str, description="Up to 100, or `print`"),
            OpenApiParameter("export", str, enum=["csv", "xlsx"]),
        ],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request, key):
        """One report: summary (KPIs, breakdowns, daily trend) and detail rows; ``export`` downloads every row."""
        report = reports.REPORTS.get(key)
        if report is None:
            raise NotFound("Unknown report.")
        sites = chosen_sites(request)
        params = request.query_params
        try:
            rows, summary, (first, last) = reports.run(report, sites, params)
        except reports.ReportError as exc:
            raise ValidationError({"detail": str(exc)})
        multi = len(sites) > 1
        meta = {
            "sites": [c.name for c in sites],
            "period_label": f"{first:%d %b %Y} – {last:%d %b %Y}",
            "generated_at": timezone.localtime(),
            "generated_by": request.user.get_full_name() or request.user.get_username(),
            "filters": reports.described_filters(report, params),
        }
        count = len(rows) if isinstance(rows, list) else rows.count()
        if "insights" in summary and not all(entitlements.has(site, "advanced_reports") for site in sites):
            summary.pop("insights")  # Insights are Advanced reports; the page offers them instead.
            summary["insights_locked"] = True

        export = params.get("export")
        if export in CONTENT_TYPES or params.get("page_size") == "print":
            for site in sites:  # Export and print / PDF are Advanced reports.
                entitlements.require(site, "advanced_reports")
        if export in CONTENT_TYPES:
            if count > reports.EXPORT_MAX_ROWS:
                raise ValidationError({"detail": f"{count:,} rows is too many to export; narrow the period or filters "
                                                 f"(at most {reports.EXPORT_MAX_ROWS:,})."})
            body = (reports.to_csv(report, rows, multi) if export == "csv"
                    else reports.to_xlsx(report, rows, summary, meta, multi))
            scope = "all-sites" if multi else sites[0].code
            response = HttpResponse(body, content_type=CONTENT_TYPES[export])
            response["Content-Disposition"] = f'attachment; filename="elix-{report.key}-{scope}-{first:%Y%m%d}-{last:%Y%m%d}.{export}"'
            return response

        printing = params.get("page_size") == "print"
        size = reports.PRINT_MAX_ROWS if printing else min(100, _int(params.get("page_size"), 50))
        page = 1 if printing else _int(params.get("page"), 1)
        chunk = rows[(page - 1) * size: page * size]
        columns, data = reports.json_rows(report, chunk, multi)
        return Response({
            "report": report.key, "title": report.title, "description": report.description,
            "landscape": report.landscape,
            "sites": meta["sites"],
            "period": {"from": first.isoformat(), "to": last.isoformat(), "label": meta["period_label"]},
            "generated_at": meta["generated_at"].isoformat(), "generated_by": meta["generated_by"],
            "filters": meta["filters"],
            "summary": summary,
            "columns": columns, "rows": data,
            "count": count, "page": page, "page_size": size, "truncated": printing and count > size,
        })
