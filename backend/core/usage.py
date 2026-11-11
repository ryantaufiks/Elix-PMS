"""Metered usage per site and month: video intercom time and AI conversations (with tokens).

Use past a plan's monthly allowance keeps working; it is counted as overage for the invoice, and the
site admins, billing contact and platform admins get an email at 80% and at 100% of the allowance.
"""
import logging
import math

from django.db.models import F
from django.utils import timezone

from . import entitlements
from .models import UsageCounter

logger = logging.getLogger(__name__)

# Stored counters. Allowances are in the plan's units: intercom minutes (from seconds), AI conversations.
INTERCOM_SECONDS = "intercom_seconds"
AI_CONVERSATIONS = "ai_conversations"
AI_OWN_KEY_CONVERSATIONS = "ai_conversations_own_key"  # The site's own OpenAI key: not billed as overage.
AI_TOKENS_IN = "ai_tokens_in"
AI_TOKENS_OUT = "ai_tokens_out"
THRESHOLDS = (80, 100)


def month_of(day=None):
    return (day or timezone.localdate()).replace(day=1)


def add(condo, metric, amount, day=None):
    """Count ``amount`` of ``metric`` for this month and warn when an allowance is crossed."""
    if not amount or amount <= 0:
        return
    month = month_of(day)
    counter, created = UsageCounter.objects.get_or_create(condominium=condo, month=month, metric=metric,
                                                          defaults={"value": amount})
    if not created:
        UsageCounter.objects.filter(pk=counter.pk).update(value=F("value") + amount)
    try:
        _warn(condo, month)
    except Exception:  # A reminder must never break a call or a conversation.
        logger.exception("Usage warning failed for %s", condo)


def counters(condo, month) -> dict:
    return dict(UsageCounter.objects.filter(condominium=condo, month=month).values_list("metric", "value"))


def metered(raw: dict) -> dict:
    """Plan units from stored counters: {'intercom_minutes': n, 'ai_conversations': n}."""
    return {"intercom_minutes": math.ceil(raw.get(INTERCOM_SECONDS, 0) / 60),
            "ai_conversations": raw.get(AI_CONVERSATIONS, 0)}


def this_month(condo) -> dict:
    return metered(counters(condo, month_of()))


def _warn(condo, month):
    from . import subscriptions

    sub = getattr(condo, "subscription", None)
    if sub is None:
        return
    allowed = entitlements.limits(condo)
    for key, used in metered(counters(condo, month)).items():
        limit = allowed.get(key)
        if not limit:
            continue
        pct = used * 100 // limit
        for threshold in THRESHOLDS:
            if pct >= threshold:
                subscriptions.notify(sub, f"usage-{key}-{threshold}", month, template="usage",
                                     metric=entitlements.LIMITS[key].name, unit=entitlements.LIMITS[key].unit,
                                     used=used, allowed=limit, threshold=threshold)


# --- Hooks ---------------------------------------------------------------------------------------------

def call_ended(call):
    """Answered time of an intercom call, once it has ended."""
    if call.answered_at and call.ended_at and call.ended_at > call.answered_at:
        add(call.condominium, INTERCOM_SECONDS, int((call.ended_at - call.answered_at).total_seconds()))


def conversation_started(condo, own_key: bool):
    add(condo, AI_OWN_KEY_CONVERSATIONS if own_key else AI_CONVERSATIONS, 1)


def tokens(condo, response_json):
    """Token counts from an OpenAI response (chat or transcription), when it reports them."""
    usage = (response_json or {}).get("usage") or {}
    add(condo, AI_TOKENS_IN, int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0))
    add(condo, AI_TOKENS_OUT, int(usage.get("completion_tokens") or usage.get("output_tokens") or 0))


# --- Monthly report --------------------------------------------------------------------------------------

def report(month, sites) -> list[dict]:
    """One row per site: usage against its allowances, overage and its price, and the AI cost estimate."""
    from .models import SystemSettings

    s = SystemSettings.load()
    rows = []
    for condo in sites:
        sub = getattr(condo, "subscription", None)
        raw = counters(condo, month)
        used = metered(raw)
        allowed = entitlements.limits(condo)
        rates = sub.plan.overage_rates if sub else {}
        row = {"site": condo.name, "site_id": condo.pk, "code": condo.code, "plan": sub.plan.name if sub else "",
               "status": sub.status if sub else "", "currency": sub.plan.currency if sub else "SGD",
               "ai_conversations_own_key": raw.get(AI_OWN_KEY_CONVERSATIONS, 0),
               "ai_tokens_in": raw.get(AI_TOKENS_IN, 0), "ai_tokens_out": raw.get(AI_TOKENS_OUT, 0),
               "overage_amount": 0.0}
        for key, value in used.items():
            limit = allowed.get(key)
            over = max(0, value - limit) if limit is not None else 0
            amount = round(over * float(rates.get(key, 0)), 2)
            row.update({key: value, f"{key}_allowed": limit, f"{key}_overage": over, f"{key}_amount": amount})
            row["overage_amount"] = round(row["overage_amount"] + amount, 2)
        if s.ai_usd_per_million_input is not None and s.ai_usd_per_million_output is not None:
            row["ai_cost_usd"] = round(row["ai_tokens_in"] / 1e6 * float(s.ai_usd_per_million_input)
                                       + row["ai_tokens_out"] / 1e6 * float(s.ai_usd_per_million_output), 4)
        else:
            row["ai_cost_usd"] = None
        rows.append(row)
    return rows
