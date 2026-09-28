"""marketing_data/meta.py — porta fiel de functions/api/_meta.js.

Busca dados de Meta Ads (Graph API v21.0) para alimentar o midia_paga do data.json.
Interface pública: fetch_meta_window(env, {since, until}) -> dict.

Endpoints replicados exatamente do JS:
  /insights  level=ad time_increment=1  fields=ad_name,spend,impressions,reach,actions,date_start
             limit=500  paginação paging.next ≤50 páginas  fatiado por mês calendário
  /insights  reach mensal  sem time_increment  fields=ad_name,reach  ≤20 páginas
  /ads       metadata com creative.thumbnail 400×400 + campaign + adset
             filtering effective_status IN [...11 status...]  limit=50  ≤50 páginas

fetch_meta_window engole falhas de reach/metadata; propaga apenas falha do insights diário.
"""

import time
import requests

META_API_VERSION = "v21.0"
_BASE = f"https://graph.facebook.com/{META_API_VERSION}"

# Action type que representa "novo contato por mensagem"
_MSG_ACTION = "onsite_conversion.messaging_first_reply"

# Status de anúncio incluídos na consulta de metadata (igual ao JS)
_AD_EFFECTIVE_STATUSES = [
    "ACTIVE", "PAUSED", "ARCHIVED", "CAMPAIGN_PAUSED", "ADSET_PAUSED",
    "PENDING_REVIEW", "DISAPPROVED", "PREAPPROVED", "PENDING_BILLING_INFO",
    "IN_PROCESS", "WITH_ISSUES",
]


# ---------------------------------------------------------------------------
# Helpers puros
# ---------------------------------------------------------------------------

def _js_num(x):
    """Replica JS `+(x.toFixed(2))`: 2 casas; inteiro serializa como int (JSON `0`, nao `0.0`)."""
    r = round(x, 2)
    return int(r) if r == int(r) else r


def month_windows(since: str, until: str) -> list[dict]:
    """Lista de janelas {ym, since, until} por mês calendário entre since e until.

    Porta direta de monthWindows() do _meta.js.
    Bordas são recortadas: primeiro mês começa em `since`, último termina em `until`.
    """
    from datetime import date, timedelta

    start_d = date.fromisoformat(since)
    end_d = date.fromisoformat(until)

    windows = []
    # Primeiro dia do mês inicial
    y, m = start_d.year, start_d.month

    while True:
        # Último dia do mês atual
        if m == 12:
            month_end = date(y + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(y, m + 1, 1) - timedelta(days=1)

        month_start = date(y, m, 1)

        # Recorta nas bordas (igual ao JS)
        call_since = since if month_start < start_d else f"{y}-{m:02d}-01"
        call_until = until if month_end > end_d else f"{y}-{m:02d}-{month_end.day:02d}"

        windows.append({
            "ym": f"{y}-{m:02d}",
            "since": call_since,
            "until": call_until,
        })

        # Avança para o próximo mês
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1

        if date(y, m, 1) > end_d:
            break

    return windows


def load_meta_creds(env) -> dict | None:
    """Lê credenciais Meta do env. Retorna None se ausentes; prefixa act_ se necessário."""
    token = env.get("META_ACCESS_TOKEN")
    acct = env.get("META_AD_ACCOUNT_ID")
    if not token or not acct:
        return None
    if not acct.startswith("act_"):
        acct = "act_" + acct
    return {"token": token, "acct": acct}


# ---------------------------------------------------------------------------
# Retry (replica withRetry do JS)
# ---------------------------------------------------------------------------

def with_retry(label: str, fn, attempts: int = 3, base_delay_s: float = 3.0):
    """Repete fn até attempts vezes em caso de exceção, com backoff."""
    last_err = None
    for i in range(1, attempts + 1):
        try:
            return fn()
        except Exception as e:
            last_err = e
            if i < attempts:
                delay = base_delay_s * i
                print(f"AVISO: {label} falhou (tentativa {i}/{attempts}): {e} — repetindo em {delay:.0f}s")
                time.sleep(delay)
    raise last_err


# ---------------------------------------------------------------------------
# Fetchers individuais
# ---------------------------------------------------------------------------

def fetch_meta_insights_daily(creds: dict, since: str, until: str) -> dict:
    """Insights por ad por dia (spend, impressions, reach, new_msg_contacts).

    Porta de fetchMetaInsightsDaily() do _meta.js.
    Fatiado por mês calendário via month_windows; paginação ≤50 páginas.
    """
    spend = {}
    impressions = {}
    reach = {}
    new_msg_contacts = {}

    for window in month_windows(since, until):
        s, u = window["since"], window["until"]
        params = {
            "level": "ad",
            "time_increment": "1",
            "time_range": f'{{"since":"{s}","until":"{u}"}}',
            "fields": "ad_name,spend,impressions,reach,actions,date_start",
            "limit": "500",
            "access_token": creds["token"],
        }
        url = f"{_BASE}/{creds['acct']}/insights"
        pages = 0
        while url:
            r = requests.get(url, params=params if pages == 0 else None)
            j = r.json()
            if j.get("error"):
                err = j["error"]
                raise Exception(f"Meta API: {err.get('message')} (code {err.get('code')})")
            for row in j.get("data") or []:
                ad = row.get("ad_name")
                day = row.get("date_start")
                if not ad or not day:
                    continue
                action = next(
                    (a for a in (row.get("actions") or []) if a.get("action_type") == _MSG_ACTION),
                    None,
                )
                new_contacts = int(action["value"]) if action else 0
                spend.setdefault(ad, {})[day] = _js_num(float(row.get("spend") or 0))
                impressions.setdefault(ad, {})[day] = int(row.get("impressions") or 0)
                reach.setdefault(ad, {})[day] = int(row.get("reach") or 0)
                new_msg_contacts.setdefault(ad, {})[day] = new_contacts
            pages += 1
            paging = j.get("paging") or {}
            url = paging.get("next")
            # Usar params=None nas páginas seguintes (url já tem todos os params)
            if pages > 50:
                break

    return {
        "spend": spend,
        "impressions": impressions,
        "reach": reach,
        "new_msg_contacts": new_msg_contacts,
    }


def fetch_meta_reach_monthly(creds: dict, since: str, until: str) -> dict:
    """Reach único por mês por ad. Porta de fetchMetaReachMonthly() do _meta.js.

    Paginação ≤20 páginas por janela.
    """
    reach_monthly = {}

    for window in month_windows(since, until):
        ym, s, u = window["ym"], window["since"], window["until"]
        params = {
            "level": "ad",
            "time_range": f'{{"since":"{s}","until":"{u}"}}',
            "fields": "ad_name,reach",
            "limit": "500",
            "access_token": creds["token"],
        }
        url = f"{_BASE}/{creds['acct']}/insights"
        pages = 0
        while url:
            r = requests.get(url, params=params if pages == 0 else None)
            j = r.json()
            if j.get("error"):
                err = j["error"]
                raise Exception(f"Meta API (reach {ym}): {err.get('message')}")
            for row in j.get("data") or []:
                ad = row.get("ad_name")
                if not ad:
                    continue
                reach_monthly.setdefault(ad, {})[ym] = int(row.get("reach") or 0)
            pages += 1
            paging = j.get("paging") or {}
            url = paging.get("next")
            if pages > 20:
                break

    return reach_monthly


def fetch_meta_ads_metadata(creds: dict) -> dict:
    """Metadata dos anúncios: thumbnail 400×400, campanha pai, adset pai.

    Porta de fetchMetaAdsMetadata() do _meta.js.
    fields e filtering idênticos ao JS; limit=50; paginação ≤50 páginas.
    """
    import json as _json

    params = {
        "fields": (
            "name,"
            "creative.thumbnail_width(400).thumbnail_height(400){thumbnail_url},"
            "campaign{id,name,status,effective_status},"
            "adset{id,name}"
        ),
        "filtering": _json.dumps([{
            "field": "ad.effective_status",
            "operator": "IN",
            "value": _AD_EFFECTIVE_STATUSES,
        }]),
        "limit": "50",
        "access_token": creds["token"],
    }
    url = f"{_BASE}/{creds['acct']}/ads"

    thumbs = {}
    ad_campaign = {}
    ad_adset = {}
    campaigns_by_id = {}
    pages = 0

    while url:
        r = requests.get(url, params=params if pages == 0 else None)
        j = r.json()
        if j.get("error"):
            err = j["error"]
            raise Exception(f"Meta API (ads): {err.get('message')}")
        for ad in j.get("data") or []:
            creative = ad.get("creative") or {}
            t = creative.get("thumbnail_url")
            if ad.get("name") and t:
                thumbs[ad["name"]] = t
            campaign = ad.get("campaign") or {}
            if ad.get("name") and campaign.get("name"):
                ad_campaign[ad["name"]] = campaign["name"]
                cid = campaign.get("id")
                if cid and cid not in campaigns_by_id:
                    campaigns_by_id[cid] = {
                        "name": campaign["name"],
                        "status": campaign.get("status") or None,
                        "effective_status": campaign.get("effective_status") or None,
                    }
            adset = ad.get("adset") or {}
            if ad.get("name") and adset.get("name"):
                ad_adset[ad["name"]] = adset["name"]
        pages += 1
        paging = j.get("paging") or {}
        url = paging.get("next")
        if pages > 50:
            break

    return {
        "thumbs": thumbs,
        "adCampaign": ad_campaign,
        "adAdset": ad_adset,
        "campaigns": list(campaigns_by_id.values()),
    }


# ---------------------------------------------------------------------------
# Interface de alto nível
# ---------------------------------------------------------------------------

def fetch_meta_window(env, window: dict) -> dict:
    """Monta os campos Meta do midia_paga para a janela {since, until}.

    Porta de fetchMetaWindow() do _meta.js.
    - Lança se creds ausentes ou se insights diário falhar.
    - Engole falhas de reach_monthly e metadata (o caller usa base do disco).
    """
    creds = load_meta_creds(env)
    if not creds:
        raise Exception("Credenciais Meta ausentes (META_ACCESS_TOKEN/META_AD_ACCOUNT_ID).")

    since = window["since"]
    until = window["until"]
    out = {}

    insights = with_retry(
        "insights diários",
        lambda: fetch_meta_insights_daily(creds, since, until),
    )
    out["spend_daily"] = insights["spend"]
    out["impressions_daily"] = insights["impressions"]
    out["reach_daily"] = insights["reach"]
    out["new_msg_contacts_daily"] = insights["new_msg_contacts"]
    out["spend_window"] = {"since": since, "until": until}

    try:
        out["reach_monthly"] = with_retry(
            "alcance mensal",
            lambda: fetch_meta_reach_monthly(creds, since, until),
        )
    except Exception:
        pass  # segue sem reach_monthly; base preenche

    try:
        meta = with_retry(
            "metadata",
            lambda: fetch_meta_ads_metadata(creds),
        )
        out["thumbnails"] = meta["thumbs"]
        out["ad_campaign"] = meta["adCampaign"]
        out["ad_adset"] = meta["adAdset"]
        out["campaigns"] = meta["campaigns"]
    except Exception:
        pass  # segue sem metadata; base preenche

    return out
