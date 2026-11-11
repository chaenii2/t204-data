"""T204 데일리 브리핑 데이터 수집.

출력: data/data.json (템플릿 입력), data/fetch_log.md (수집 결과 요약)
출처: 기상청 단기예보, 에어코리아, 한국수출입은행, OpenDART, 중앙일보 경제 섹션 기사
"""
import html
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
NOW = datetime.now(KST)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"}
DOW = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
LOG = []


def log(msg):
    LOG.append(msg)
    print(msg)


def get(url, params=None, timeout=25):
    if params:
        url += "?" + urllib.parse.urlencode(params, safe="")
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def key(name):
    return os.environ[name].strip()


def num(s):
    return float(str(s).replace(",", ""))


# ---------------------------------------------------------------- 날씨
SKY = {"1": "맑음", "3": "구름많음", "4": "흐림"}
PTY = {"1": "비", "2": "비/눈", "3": "눈", "4": "소나기", "5": "빗방울", "6": "빗방울눈날림", "7": "눈날림"}


def icon_of(sky, pty):
    if pty and pty != "0":
        return "rain"
    return {"1": "clear", "3": "partly", "4": "cloudy"}.get(sky, "partly")


def weather():
    # 당일 최저/최고(TMN/TMX)를 모두 받으려면 02시 발표(없으면 전날 23시)를 사용
    base = NOW.replace(hour=2, minute=0)
    if NOW < NOW.replace(hour=2, minute=15):
        base = (NOW - timedelta(days=1)).replace(hour=23, minute=0)
    d = json.loads(get("https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst", {
        "serviceKey": key("DATA_GO_KR_KEY"), "pageNo": 1, "numOfRows": 1000, "dataType": "JSON",
        "base_date": base.strftime("%Y%m%d"), "base_time": base.strftime("%H00"), "nx": 61, "ny": 125}))
    items = d["response"]["body"]["items"]["item"]
    today = NOW.strftime("%Y%m%d")
    v = {}
    for i in items:
        if i["fcstDate"] == today:
            v.setdefault(i["fcstTime"], {})[i["category"]] = i["fcstValue"]
    tmps = {t: float(x["TMP"]) for t, x in v.items() if "TMP" in x}
    tmn = next((float(x["TMN"]) for x in v.values() if "TMN" in x), min(tmps.values()))
    tmx = next((float(x["TMX"]) for x in v.values() if "TMX" in x), max(tmps.values()))
    day = [t for t in sorted(v) if "0600" <= t <= "2100"]
    pop = max(int(v[t].get("POP", 0)) for t in day)
    ptys = [v[t].get("PTY", "0") for t in day if v[t].get("PTY", "0") != "0"]
    skies = [v[t].get("SKY", "1") for t in day]
    if ptys:
        text, sky = PTY.get(max(set(ptys), key=ptys.count), "비"), "rain"
    else:
        main = max(set(skies), key=skies.count)
        text, sky = SKY.get(main, "구름많음"), icon_of(main, "0")
    hourly = []
    for hh in ["0600", "0900", "1200", "1500", "1800", "2100"]:
        x = v.get(hh, {})
        if "TMP" in x:
            hourly.append({"h": f"{int(hh[:2])}시", "t": round(float(x["TMP"])), "sky": icon_of(x.get("SKY"), x.get("PTY"))})
    gap = round(tmx - tmn)
    if pop >= 60:
        tip = f"강수확률 {pop}%, 우산을 꼭 챙기세요"
    elif gap >= 10:
        tip = f"일교차 {gap}도, 겉옷을 챙기세요"
    elif tmx >= 30:
        tip = "무더운 날씨, 물 자주 드세요"
    elif tmn <= -5:
        tip = "한파 주의, 따뜻하게 입으세요"
    else:
        tip = "활동하기 좋은 날씨예요"
    # 지금 시각에 가장 가까운 예보 시각의 하늘 상태
    cur = NOW.strftime("%H00")
    near = min((t for t in v if "SKY" in v[t]), key=lambda t: abs(int(t[:2]) - int(cur[:2])), default=None)
    now_sky = icon_of(v[near].get("SKY"), v[near].get("PTY")) if near else sky
    log(f"날씨: 최저 {tmn} / 최고 {tmx}, {text}, 강수 {pop}%, 지금 하늘 {now_sky} (발표 {base:%m-%d %H}시)")
    # 내일 예보
    tmr = (NOW + timedelta(days=1)).strftime("%Y%m%d")
    tv = {}
    for i in items:
        if i["fcstDate"] == tmr:
            tv.setdefault(i["fcstTime"], {})[i["category"]] = i["fcstValue"]
    tomorrow = None
    if tv:
        ttmp = [float(x["TMP"]) for x in tv.values() if "TMP" in x]
        tn = next((float(x["TMN"]) for x in tv.values() if "TMN" in x), min(ttmp))
        tx = next((float(x["TMX"]) for x in tv.values() if "TMX" in x), max(ttmp))
        tday = [t for t in sorted(tv) if "0600" <= t <= "2100"]
        tpop = max(int(tv[t].get("POP", 0)) for t in tday) if tday else 0
        tp = [tv[t].get("PTY", "0") for t in tday if tv[t].get("PTY", "0") != "0"]
        ts = [tv[t].get("SKY", "1") for t in tday]
        tsky = "rain" if tp else icon_of(max(set(ts), key=ts.count), "0") if ts else "partly"
        tomorrow = {"min": round(tn), "max": round(tx), "pop": tpop, "sky": tsky}
    return {"sky": sky, "now_sky": now_sky, "text": text, "min": round(tmn), "max": round(tmx), "pop": pop, "tip": tip, "hourly": hourly, "tomorrow": tomorrow}


GRADE = {"1": "좋음", "2": "보통", "3": "나쁨", "4": "매우나쁨"}


def _grade(v, cuts):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    for lim, g in zip(cuts, ["좋음", "보통", "나쁨"]):
        if x <= lim:
            return g
    return "매우나쁨"


def dust_both():
    """(미세먼지 등급, 초미세먼지 등급) — 강남 일대 측정소 최근 측정값. 모르면 None."""
    pm10 = pm25 = None
    for st in ["강남구", "도산대로", "강남대로"]:
        try:
            d = json.loads(get("https://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getMsrstnAcctoRltmMesureDnsty", {
                "serviceKey": key("DATA_GO_KR_KEY"), "returnType": "json", "numOfRows": 6, "pageNo": 1,
                "stationName": st, "dataTerm": "DAILY", "ver": "1.0"}))
        except Exception:  # noqa: BLE001
            continue
        for it in d["response"]["body"]["items"]:
            if pm10 is None:
                pm10 = GRADE.get(str(it.get("pm10Grade1h") or it.get("pm10Grade") or "")) or _grade(it.get("pm10Value"), [30, 80, 150])
            if pm25 is None:
                pm25 = GRADE.get(str(it.get("pm25Grade1h") or it.get("pm25Grade") or "")) or _grade(it.get("pm25Value"), [15, 35, 75])
            if pm10 and pm25:
                log(f"미세먼지: {pm10} / 초미세먼지: {pm25} ({st} 측정소 {it.get('dataTime')})")
                return pm10, pm25
    log(f"미세먼지: {pm10} / 초미세먼지: {pm25} (측정값 일부 없음)")
    return pm10, pm25


def dust():
    d = json.loads(get("https://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getMsrstnAcctoRltmMesureDnsty", {
        "serviceKey": key("DATA_GO_KR_KEY"), "returnType": "json", "numOfRows": 12, "pageNo": 1,
        "stationName": "강남구", "dataTerm": "DAILY", "ver": "1.0"}))
    for it in d["response"]["body"]["items"]:
        g = it.get("pm10Grade")
        if it.get("pm10Value") not in (None, "-", "") and g not in (None, "", "-"):
            grade = {"1": "좋음", "2": "보통", "3": "나쁨", "4": "매우나쁨"}.get(str(g), "보통")
            log(f"미세먼지: 강남구 {it['dataTime']} PM10 {it['pm10Value']} ({grade})")
            return grade
    log("미세먼지: 최근 측정값 없음 → '보통' 대체")
    return "보통"


# ---------------------------------------------------------------- 환율
FX = [("USD", "미국 달러", "USD", ""), ("JPY(100)", "일본 엔", "JPY", "100엔"), ("EUR", "유로", "EUR", ""), ("CNH", "중국 위안", "CNY", "")]


def fx_day(day):
    d = json.loads(get("https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON",
                       {"authkey": key("KOREAEXIM_KEY"), "searchdate": day.strftime("%Y%m%d"), "data": "AP01"}))
    if isinstance(d, list) and d and d[0].get("result") in (1, "1"):
        return {r["cur_unit"]: num(r["deal_bas_r"]) for r in d}
    return None


def fx():
    found = []
    for back in range(0, 12):
        day = NOW - timedelta(days=back)
        r = fx_day(day)
        if r:
            found.append((day, r))
        if len(found) == 2:
            break
    (d0, cur), (_, prev) = found
    items = [{"name": n, "code": c, "unit": u, "v": cur[k], "d": round(cur[k] - prev[k], 2)} for k, n, c, u in FX if k in cur]
    log(f"환율: {d0:%m-%d} 매매기준율 " + ", ".join(f"{i['code']} {i['v']}" for i in items))
    return {"basis": f"{d0:%m.%d} 매매기준율 · 한국수출입은행", "items": items}


# ---------------------------------------------------------------- 공모주
def parse_sbd(s):
    m = re.findall(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", s or "")
    if not m:
        return None, None
    ds = [datetime(int(y), int(mo), int(d), tzinfo=KST).date() for y, mo, d in m]
    return ds[0], ds[-1]


def ipo():
    dk = key("DART_KEY")
    rows = json.loads(get("https://opendart.fss.or.kr/api/list.json", {
        "crtfc_key": dk, "bgn_de": (NOW - timedelta(days=75)).strftime("%Y%m%d"), "end_de": NOW.strftime("%Y%m%d"),
        "pblntf_detail_ty": "C001", "page_count": 100})).get("list", [])
    out, seen = [], set()
    for r in rows:
        if r["corp_cls"] != "E" or r["corp_code"] in seen:  # 비상장(신규 상장 공모)만
            continue
        seen.add(r["corp_code"])
        try:
            d = json.loads(get("https://opendart.fss.or.kr/api/estkRs.json", {
                "crtfc_key": dk, "corp_code": r["corp_code"],
                "bgn_de": (NOW - timedelta(days=75)).strftime("%Y%m%d"), "end_de": NOW.strftime("%Y%m%d")}))
        except Exception:  # noqa: BLE001
            continue
        if d.get("status") != "000":
            continue
        g = {x["title"]: x["list"] for x in d["group"]}
        gen = (g.get("일반사항") or [{}])[-1]
        start, end = parse_sbd(gen.get("sbd"))
        if not start:
            continue
        kind = (g.get("증권의종류") or [{}])[-1]
        price = kind.get("slprc") or gen.get("exprc") or "-"
        lead = next((x["actnmn"] for x in g.get("인수인정보", []) if x.get("actsen") == "대표"), "")
        out.append({"name": gen.get("corp_name") or r["corp_name"], "start": start, "end": end,
                    "price": f"{price}원" if price not in ("-", "") else "공모가 확정 전",
                    "broker": f"대표주관 {lead}" if lead else ""})
    log("공모주 후보: " + ", ".join(f"{o['name']}({o['start']:%m.%d}~{o['end']:%m.%d})" for o in out[:10]))
    return out


def ipo_cards(lst, today, evening=False):
    """진행 중·다가오는 청약 2건. 퇴근판은 '내일' 기준 문구를 씀."""
    ref = today + timedelta(days=1) if evening else today
    cards = []
    for o in sorted(lst, key=lambda x: x["start"]):
        if o["end"] < ref or (o["start"] - today).days > 10:
            continue
        if o["start"] <= today <= o["end"]:
            if o["end"] == today:
                badge = "오늘 마감"
            elif evening and o["end"] == ref:
                badge = "내일 마감"
            else:
                badge = "청약 중"
        else:
            n = (o["start"] - today).days
            badge = "내일 시작" if n == 1 else f"D-{n}"
        cards.append({"badge": badge, "name": o["name"], "period": f"{o['start']:%m.%d} ~ {o['end']:%m.%d}",
                      "price": o["price"], "broker": o["broker"]})
    return cards[:2]


# ---------------------------------------------------------------- 중앙일보 기사
SECTIONS = ["https://www.joongang.co.kr/money", "https://www.joongang.co.kr/money/finance",
            "https://www.joongang.co.kr/money/globaleconomy", "https://www.joongang.co.kr/money/general"]


def ja_headlines():
    seen, out = set(), []
    for sec in SECTIONS:
        for page in ("", "?page=2"):
            try:
                h = get(sec + page)
            except Exception:  # noqa: BLE001
                continue
            for u, t in re.findall(r'<h2 class="headline[^"]*">\s*<a href="(https://www\.joongang\.co\.kr/article/\d+)"[^>]*>(.*?)</a>', h, re.S):
                if u not in seen:
                    seen.add(u)
                    out.append((u, html.unescape(re.sub("<[^>]+>", "", t)).strip()))
    return out


DEBUG = []


def ja_article(url):
    h = get(url)
    pub = re.search(r'property="article:published_time"\s+content="([^"]+)"', h)
    body = re.search(r'<div[^>]+id="article_body"[^>]*>(.*?)</div>\s*<!--', h, re.S) or re.search(r'id="article_body"[^>]*>(.*?)</section>', h, re.S)
    text = html.unescape(re.sub(r"<[^>]+>", " ", body.group(1) if body else h))
    text = re.sub(r"\s+", " ", text)
    sents = [x.strip() for x in re.split(r"(?<=다)\.\s", text) if re.search(r"포인트|나스닥|다우|S&P|코스피|코스닥|순매수|순매도", x)]
    DEBUG.append(f"## {url} ({pub.group(1) if pub else ''})\n" + "\n".join(f"- {x[:220]}" for x in sents[:12]))
    return (pub.group(1) if pub else ""), text


NUM = r"(\d+만\s?[\d,]*\.?\d*|[\d,]+\.\d+)"


def knum(x):
    x = x.replace(",", "").replace(" ", "")
    if "만" in x:
        a, b = x.split("만")
        return float(a) * 10000 + (float(b) if b else 0)
    return float(x)


def idx_pat(names):
    # "나스닥 종합지수는 673.71포인트(2.74%) 오른 2만5253.14에 각각 마감했다"
    return re.compile(r"(?:%s)[^.%%]{0,40}?([\d,]+\.\d+)\s*포인트\s*\(\s*([+-]?[\d.]+)\s*%%\s*\)\s*(오른|내린|상승한|하락한|오르며|내리며)\s*%s\s*(?:에|로|으로|,)(?:(?!다\.).){0,130}?(?:마쳤|마감|끝냈)" % ("|".join(names), NUM))


def extract(text, names):
    m = idx_pat(names).search(text)
    if not m:
        return None
    d, pct, way, v = num(m.group(1)), float(m.group(2)), m.group(3), knum(m.group(4))
    sign = -1 if way.startswith(("내", "하")) else 1
    return {"v": v, "d": round(sign * abs(d), 2), "pct": round(sign * abs(pct), 2)}


def short(t, n=18):
    t = re.sub(r"^\[[^\]]+\]\s*", "", t).strip()
    return t if len(t) <= n else t[: n - 1] + "…"


def us_market(heads):
    for u, t in heads:
        if not re.search(r"뉴욕|월가|미\s?증시|미국\s?증시|나스닥|다우|S&P|엔비디아|빅테크|테슬라|애플|마이크로소프트|美", t):
            continue
        pub, text = ja_article(u)
        items = []
        for name, code, short_name, pats in [
            ("나스닥", "NASDAQ", "나스닥", [r"나스닥\s*종합\s*지수", r"나스닥\s*지수", "나스닥"]),
            ("S&P 500", "S&P500", "S&P500", [r"S&P\)?\s*500\s*지수", r"S&P\)?\s*500", "S&P500"]),
            ("다우존스", "DOW", "다우", [r"다우존스\s*30\s*산업평균지수", r"다우\s*지수", "다우존스", "다우"]),
            ("필라델피아 반도체", "SOX", "반도체", [r"필라델피아\s*반도체\s*지수", "필라델피아반도체지수"]),
        ]:
            r = extract(text, pats)
            if r:
                items.append({"name": name, "code": code, "short": short_name, **r})
        if len(items) >= 1 and any(i["code"] in ("NASDAQ", "S&P500", "DOW") for i in items):
            log(f"미국 증시: {t} ({u}) → " + ", ".join(f"{i['code']} {i['v']}" for i in items))
            return {"basis": f"{pub[5:10].replace('-', '.')} 새벽 미국 장 마감 · 중앙일보", "items": items, "src": u}
    log("미국 증시: 해당 기사 없음")
    return {"basis": "", "items": []}


def kr_market(heads):
    for u, t in heads:
        if "코스피" not in t and "코스닥" not in t and "증시" not in t:
            continue
        pub, text = ja_article(u)
        items = []
        for name, code, pats in [("코스피", "KOSPI", [r"코스피\s*지수", "코스피"]), ("코스닥", "KOSDAQ", [r"코스닥\s*지수", "코스닥"])]:
            r = extract(text, pats)
            if r:
                items.append({"name": name, "code": code, **r})
        if not items:
            continue
        pt = datetime.fromisoformat(pub) if pub else NOW
        if pt.tzinfo is None:
            pt = pt.replace(tzinfo=KST)
        pt = pt.astimezone(KST)
        close_day = pt.date()
        if pt.hour * 60 + pt.minute < 15 * 60 + 30:  # 장 마감 전 기사 → 앞 거래일 마감 값
            close_day = close_day - timedelta(days=1)
            while close_day.weekday() >= 5:
                close_day -= timedelta(days=1)
        flow = []
        for who in ["개인", "외국인", "기관"]:
            m = re.search(who + r"[^.]{0,25}?([\d,]+)\s*억\s*원(?:어치)?[^.]{0,8}?순(매수|매도)", text)
            if m:
                v = num(m.group(1)) * (1 if m.group(2) == "매수" else -1)
                flow.append({"who": who, "v": int(v)})
        log(f"국내 증시: {t} ({u}, {pt:%m-%d %H:%M}) → {close_day:%m.%d} 마감 " + ", ".join(f"{i['code']} {i['v']}" for i in items) + f" / 수급 {flow}")
        return {"basis": f"{close_day:%m.%d} 장 마감 · 중앙일보", "items": items, "flow": flow, "src": u}
    log("국내 증시: 마감 기사 없음")
    return {"basis": "", "items": [], "flow": []}


# ---------------------------------------------------------------- 실행
def safe(fn, default, *a):
    try:
        return fn(*a)
    except Exception as e:  # noqa: BLE001
        log(f"⚠️ {fn.__name__} 실패: {type(e).__name__}: {str(e)[:200]}")
        return default


def main():
    w = safe(weather, {"sky": "partly", "text": "-", "min": 0, "max": 0, "pop": 0, "tip": "", "hourly": []})
    w["pm"] = safe(dust, "보통")
    ipos = safe(ipo, [])
    heads = safe(ja_headlines, [])
    log(f"중앙일보 경제 기사 목록 {len(heads)}건")
    data = {
        "sample": False,
        "date": NOW.strftime("%Y-%m-%d"), "dow": DOW[NOW.weekday()],
        "location": "테헤란로 204 · 역삼",
        "updated": {"morning": "06:30 업데이트", "evening": "18:00 업데이트"},
        "sponsor": {"morning": "", "evening": ""},
        "weather": w,
        "us": safe(us_market, {"basis": "", "items": []}, heads),
        "kr": safe(kr_market, {"basis": "", "items": [], "flow": []}, heads),
        "fx": safe(fx, {"basis": "", "items": []}),
        "ipo": {"morning": ipo_cards(ipos, NOW.date()), "evening": ipo_cards(ipos, NOW.date(), evening=True)},
        "fetched_at": NOW.strftime("%Y-%m-%d %H:%M"),
    }
    os.makedirs("data", exist_ok=True)
    with open("data/data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    with open("data/debug_articles.md", "w", encoding="utf-8") as f:
        f.write("\n\n".join(DEBUG[:40]))
    with open("data/fetch_log.md", "w", encoding="utf-8") as f:
        f.write(f"# 수집 로그 {NOW:%Y-%m-%d %H:%M} KST\n\n" + "\n".join(f"- {l}" for l in LOG) + "\n")


if __name__ == "__main__":
    main()
