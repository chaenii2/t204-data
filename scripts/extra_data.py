"""교통(서울시 실시간 도시데이터) · 증시(한국거래소) · 금리(한국은행 ECOS).
키가 없으면 None을 돌려주고, 화면은 해당 장면을 자동으로 뺀다.
주의: 키가 들어간 URL은 로그에 남기지 않는다."""
import json
import os
import urllib.parse
import urllib.request
from datetime import timedelta

import fetch_data as F


def _has(name):
    return bool(os.environ.get(name, "").strip())


def _json(url, headers=None, timeout=25):
    req = urllib.request.Request(url, headers={**F.UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _st(k):
    # 서울시 도시데이터 기준과 같게: 25 이상 원활, 15 이상 서행, 그 미만 정체
    return "원활" if k >= 25 else "서행" if k >= 15 else "정체"


# ---------- 교통 ----------
AREAS = [("강남역", "강남역 부근"), ("역삼역", "역삼역 부근"), ("선릉역", "선릉역 부근"), ("강남 MICE 관광특구", "삼성역 부근")]
CROSS = {"강남역": "강남대로", "선릉역": "선릉로", "역삼역": "논현로", "강남 MICE 관광특구": "영동대로"}


def _city(area):
    k = urllib.parse.quote(F.key("SEOUL_KEY"))
    d = _json(f"http://openapi.seoul.go.kr:8088/{k}/json/citydata/1/5/{urllib.parse.quote(area)}")
    if (d.get("RESULT") or {}).get("RESULT.CODE") != "INFO-000":
        raise RuntimeError(f"{area}: {(d.get('RESULT') or {}).get('RESULT.MESSAGE')}")
    return d["CITYDATA"]


def _wavg(links):
    w = sum(float(l.get("DIST") or 1) for l in links)
    return sum(float(l["SPD"]) * float(l.get("DIST") or 1) for l in links) / w if w else None


def traffic():
    if not _has("SEOUL_KEY"):
        return None
    segs, alll, roads, congest, msg, at = [], [], [], None, None, None
    for area, label in AREAS:
        try:
            c = _city(area)
        except Exception as e:  # noqa: BLE001
            F.log(f"⚠️ 도시데이터 {area} 실패: {type(e).__name__}: {str(e)[:120]}")
            continue
        r = c.get("ROAD_TRAFFIC_STTS") or {}
        links = [l for l in (r.get("ROAD_TRAFFIC_STTS") or []) if l.get("SPD") not in (None, "")]
        teh = [l for l in links if l.get("ROAD_NM") == "테헤란로"]
        if teh:
            k = round(_wavg(teh))
            segs.append({"name": label, "kmh": k})
            alll += teh
        cr = [l for l in links if l.get("ROAD_NM") == CROSS.get(area)]
        if cr:
            roads.append({"name": CROSS[area], "kmh": round(_wavg(cr))})
        at = at or (r.get("AVG_ROAD_DATA") or {}).get("ROAD_TRAFFIC_TIME")
        if area == "역삼역":
            p = (c.get("LIVE_PPLTN_STTS") or [{}])[0]
            congest = p.get("AREA_CONGEST_LVL")
            msg = (p.get("AREA_CONGEST_MSG") or "").split(".")[0].strip()
    if not alll:
        raise RuntimeError("테헤란로 구간 데이터 없음")
    kmh = round(_wavg(alll))
    t = {"basis": f"{(at or '')[11:16]} 기준 · 서울시 도시데이터".strip(" ·"),
         "status": _st(kmh), "kmh": kmh, "segments": segs,
         "roads": sorted(roads, key=lambda r: ["강남대로", "선릉로", "영동대로", "논현로"].index(r["name"]))[:2]}
    if congest:
        t["congest"], t["congest_msg"] = congest, (msg + "요" if msg and not msg.endswith("요") else msg)
    F.log(f"교통: 테헤란로 {t['status']} {kmh}km/h, 구간 {[(s['name'], s['kmh']) for s in segs]}, "
          f"역삼역 {congest}, 주변 {[(r['name'], r['kmh']) for r in roads]} ({at})")
    return t


# ---------- 증시 ----------
def _krx(path, day):
    d = _json(f"https://data-dbg.krx.co.kr/svc/apis/idx/{path}?basDd={day:%Y%m%d}",
              headers={"AUTH_KEY": F.key("KRX_KEY")})
    return d.get("OutBlock_1") or []


def _idx(path, name, day):
    row = next((x for x in _krx(path, day) if x.get("IDX_NM") == name), None)
    if not row or not row.get("CLSPRC_IDX"):
        return None
    return {"v": F.num(row["CLSPRC_IDX"]), "d": F.num(row.get("CMPPREVDD_IDX") or 0), "pct": F.num(row.get("FLUC_RT") or 0)}


def kr(prev_hist):
    """prev_hist: {"KOSPI": [{"d":"MM.DD","v":..}], ...} 직전 feed의 누적값"""
    if not _has("KRX_KEY"):
        return None, prev_hist
    hist = {k: {x["d"]: x["v"] for x in v} for k, v in (prev_hist or {}).items()}
    items, basis = [], None
    for code, path, name in [("KOSPI", "kospi_dd_trd", "코스피"), ("KOSDAQ", "kosdaq_dd_trd", "코스닥")]:
        h = hist.setdefault(code, {})
        need = 10 if len(h) < 5 else 1          # 처음엔 그래프용으로 최근 영업일을 몇 개 채움
        got, last = 0, None
        for back in range(1, 25):
            day = F.NOW - timedelta(days=back)
            if day.weekday() >= 5:
                continue
            md = day.strftime("%Y%m%d")
            if md in h and got >= 1:
                break
            x = _idx(path, name, day)
            if x:
                h[md] = x["v"]
                last = last or (day, x)
                got += 1
                if got >= need:
                    break
        if last:
            day, x = last
            basis = basis or f"{day:%m.%d} 종가 · 한국거래소"
            order = sorted(h)
            items.append({"code": code, **x, "hist": [h[m] for m in order][-10:]})
    if not items:
        raise RuntimeError("지수 데이터 없음 (API 이용신청 승인 여부 확인)")
    F.log(f"증시: {[(i['code'], i['v'], i['d']) for i in items]} ({basis})")
    out_hist = {k: [{"d": m, "v": v[m]} for m in sorted(v)][-22:] for k, v in hist.items()}
    return {"basis": basis, "items": items}, out_hist


# ---------- 금리 ----------
def rates():
    if not _has("ECOS_KEY"):
        return None
    k = urllib.parse.quote(F.key("ECOS_KEY"))
    rows = []
    # 일별 값 우선(금통위 결정 당일 반영), 없으면 월별
    for cyc, fr, to in [("D", (F.NOW - timedelta(days=40)).strftime("%Y%m%d"), F.NOW.strftime("%Y%m%d")),
                        ("M", (F.NOW - timedelta(days=200)).strftime("%Y%m"), F.NOW.strftime("%Y%m"))]:
        try:
            d = _json(f"https://ecos.bok.or.kr/api/StatisticSearch/{k}/json/kr/1/100/722Y001/{cyc}/{fr}/{to}/0101000")
            rows = (d.get("StatisticSearch") or {}).get("row") or []
        except Exception as e:  # noqa: BLE001
            F.log(f"⚠️ 금리({cyc}) 실패: {type(e).__name__}")
        if rows:
            break
    if not rows:
        raise RuntimeError("금리 데이터 없음")
    v = float(rows[-1]["DATA_VALUE"])
    F.log(f"금리: 한국은행 기준금리 {v}% ({cyc} {rows[-1].get('TIME')})")
    return {"basis": "한국은행 ECOS", "items": [{"name": "한국은행 기준금리", "v": v}]}


# ---------- 채용 (로켓펀치 Open API) ----------
# 채용공고 조회는 로켓펀치 관리자 승인 후 응답이 옴. 승인 전·실패 시 None → 화면에서 채용 클립 제외
RP_BASE = "https://openapi.rocketpunch.com/v1/jobs"
SIZE_KO = {"HUGE": "대기업", "LARGE": "중견기업", "MEDIUM": "중소기업", "SMALL": "스타트업", "TINY": "스타트업"}
SIZE_RANK = {"HUGE": 0, "LARGE": 1, "MEDIUM": 2, "SMALL": 3, "TINY": 3}
# 화면에 맞지 않는 공고(영업 설명회·설계사 모집 등) 제외
JOB_EXCLUDE = ("설명회", "설계사", "컨설턴트 모집", "FC 모집", "보험", "알바", "아르바이트")


def _rp_once(q):
    import urllib.error
    try:
        return _json(f"{RP_BASE}?{q}", headers={"X-RP-API-Key": F.key("ROCKETPUNCH_KEY"), "Accept-Language": "ko",
                                              "Accept": "application/json"})
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")[:200].replace("\n", " ")
        except Exception:  # noqa: BLE001
            pass
        F.log(f"⚠️ 로켓펀치 응답 {e.code}: {body}")  # 키는 기록하지 않음
        raise


def _rp(params):
    """배열 조건은 반복 키(a=1&a=2)로 먼저, 실패하면 쉼표(a=1,2)로 다시 시도."""
    try:
        return _rp_once(urllib.parse.urlencode(params, doseq=True))
    except Exception:  # noqa: BLE001
        if not any(isinstance(v, list) for v in params.values()):
            raise
        flat = {k: (",".join(v) if isinstance(v, list) else v) for k, v in params.items()}
        return _rp_once(urllib.parse.urlencode(flat))


def _kst_date(iso):
    if not iso:
        return None
    try:
        from datetime import datetime
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(F.KST).strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return iso[:10]


def _pick(items, out, seen, limit=4):
    today = F.NOW.strftime("%Y-%m-%d")
    for j in sorted(items, key=lambda x: SIZE_RANK.get((x.get("company") or {}).get("size"), 9)):
        if len(out) >= limit:
            break
        c = j.get("company") or {}
        name, title = (c.get("name") or "").strip(), (j.get("title") or "").strip()
        if not name or not title or name in seen:
            continue
        if j.get("hiring") is False or j.get("status") == "finish":
            continue
        if any(w in title for w in JOB_EXCLUDE):
            continue
        end = _kst_date(j.get("endAt"))
        if end and end < today:
            continue
        seen.add(name)
        out.append({"company": name, "title": title, "size": SIZE_KO.get(c.get("size"), ""),
                    "end": end, "cat": j.get("jobCategory") or ""})


def jobs():
    """중견기업 이상(HUGE·LARGE)만, 최신순 최대 12건 (화면: 6건씩 15초)."""
    if not _has("ROCKETPUNCH_KEY"):
        return None
    out, seen, total_big = [], set(), None
    for page in (1, 2):
        d = _rp({"sort": "DATE_DESC", "pageSize": 50, "page": page, "companySizes": ["HUGE", "LARGE"]})
        total_big = d.get("totalItems", total_big)
        items = [j for j in (d.get("items") or []) if (j.get("company") or {}).get("size") in ("HUGE", "LARGE")]
        # 최신순 유지 (규모 정렬 없이)
        for j in items:
            _pick([j], out, seen, limit=12)
        if len(out) >= 12 or len(d.get("items") or []) < 50:
            break
    if not out:
        raise RuntimeError("중견기업 이상 채용공고 없음 (채용공고 조회 API 승인 여부 확인)")
    F.log(f"채용: {len(out)}건 {[(o['company'], o['size']) for o in out]} (중견·대기업 전체 {total_big}건)")
    return {"basis": f"{F.NOW:%m.%d %H}시 기준", "ts": F.NOW.strftime("%Y-%m-%d %H:%M"),
            "total": total_big, "items": out}
