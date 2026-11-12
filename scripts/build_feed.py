"""중계용 데이터 파일(feed.json) 생성. 중앙일보 기사는 사용하지 않음.

출력: <out>/feed.json  (기본 out=data)
"""
import json
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(__file__))
import fetch_data as F  # noqa: E402


def weather_now():
    b = F.NOW - timedelta(minutes=40)
    d = json.loads(F.get("https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst", {
        "serviceKey": F.key("DATA_GO_KR_KEY"), "pageNo": 1, "numOfRows": 20, "dataType": "JSON",
        "base_date": b.strftime("%Y%m%d"), "base_time": b.strftime("%H00"), "nx": 61, "ny": 125}))
    it = {i["category"]: i["obsrValue"] for i in d["response"]["body"]["items"]["item"]}
    F.log(f"지금 기온: {it.get('T1H')}°, 습도 {it.get('REH')}%, 바람 {it.get('WSD')}m/s ({b:%H}:00 관측)")
    return {"t": round(float(it["T1H"])), "at": b.strftime("%H:00"), "pty": str(it.get("PTY", "0")).split(".")[0],
            "reh": round(float(it["REH"])) if "REH" in it else None, "wsd": round(float(it["WSD"]), 1) if "WSD" in it else None}


def weather_ultra():
    """초단기예보(30분마다 발표): 지금 시각의 하늘 상태(SKY)"""
    b = F.NOW - timedelta(minutes=45)
    d = json.loads(F.get("https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtFcst", {
        "serviceKey": F.key("DATA_GO_KR_KEY"), "pageNo": 1, "numOfRows": 60, "dataType": "JSON",
        "base_date": b.strftime("%Y%m%d"), "base_time": b.strftime("%H30"), "nx": 61, "ny": 125}))
    v = {}
    for i in d["response"]["body"]["items"]["item"]:
        v.setdefault(i["fcstDate"] + i["fcstTime"], {})[i["category"]] = i["fcstValue"]
    cur = F.NOW.strftime("%Y%m%d%H00")
    t = min((k for k in v if k >= cur and "SKY" in v[k]), default=None) or max((k for k in v if "SKY" in v[k]), default=None)
    if not t:
        return None
    return {"sky": v[t].get("SKY"), "pty": v[t].get("PTY", "0"), "at": f"{t[8:10]}:{t[10:]}", "base": b.strftime("%H:30")}


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "data"
    w = F.safe(F.weather, None)
    if w:
        w["pm"], w["pm25"] = F.safe(F.dust_both, (None, None))
        now = F.safe(weather_now, None)
        if now:
            w["now"] = now
        # 지금 하늘: 실제 관측된 비·눈(초단기실황) 우선, 아니면 초단기예보의 현재 시각 하늘
        ul = F.safe(weather_ultra, None)
        if now and now.get("pty", "0") not in ("0", ""):
            w["now_sky"], w["now_text"] = F.pty_icon(now["pty"]), F.PTY.get(now["pty"], "비")
            w["now_basis"] = f"{now['at']} 관측"
        elif ul:
            w["now_sky"], w["now_text"] = F.icon_of(ul["sky"], "0"), F.SKY.get(ul["sky"], "구름많음")
            w["now_basis"] = f"{ul['at']} 초단기예보({ul['base']} 발표)"
        F.log(f"지금 하늘: {w.get('now_sky')} / {w.get('now_text')} ({w.get('now_basis', '단기예보 기준')})")
    ipos = F.safe(F.ipo, [])
    feed = {
        "generated_at": F.NOW.strftime("%Y-%m-%d %H:%M"),
        "location": "테헤란로 204 · 역삼",
        "weather": w,
        "fx": F.safe(F.fx, {"basis": "", "items": []}),
        "ipo_list": [{"name": o["name"], "start": o["start"].isoformat(), "end": o["end"].isoformat(),
                      "price": o["price"], "broker": o["broker"]} for o in ipos],
        "sources": {
            "weather": "기상청 단기예보·초단기실황 (apis.data.go.kr)",
            "dust": "에어코리아 강남구 측정소 (apis.data.go.kr)",
            "fx": "한국수출입은행 매매기준율 (oapi.koreaexim.go.kr)",
            "ipo": "OpenDART 증권신고서 (opendart.fss.or.kr)",
        },
    }
    # 수집 실패한 항목은 직전 정상값 유지 (화면이 비지 않게)
    prev_path = os.path.join(out, "feed.json")
    try:
        prev = json.load(open(prev_path, encoding="utf-8"))
    except Exception:  # noqa: BLE001
        prev = {}
    kept = []
    if not feed["weather"] and prev.get("weather"):
        feed["weather"] = prev["weather"]; kept.append("weather")
    if not feed["fx"].get("items") and prev.get("fx", {}).get("items"):
        feed["fx"] = prev["fx"]; kept.append("fx")
    if not feed["ipo_list"] and prev.get("ipo_list"):
        feed["ipo_list"] = prev["ipo_list"]; kept.append("ipo")
    # 교통·증시·금리 (키가 있을 때만)
    import extra_data as X
    tr = F.safe(X.traffic, None)
    if tr:
        tr["ts"] = F.NOW.strftime("%Y-%m-%d %H:%M")
        feed["traffic"] = tr
    elif prev.get("traffic", {}).get("ts"):
        # 실시간 정보라 1시간 넘은 값은 쓰지 않음
        from datetime import datetime
        age = (F.NOW.replace(tzinfo=None) - datetime.strptime(prev["traffic"]["ts"], "%Y-%m-%d %H:%M")).total_seconds()
        if age <= 3600:
            feed["traffic"] = prev["traffic"]; kept.append("traffic")
    krd, kh = F.safe(X.kr, (None, prev.get("kr_hist")), prev.get("kr_hist"))
    if kh:
        feed["kr_hist"] = kh
    if krd:
        feed["kr"] = krd
    elif prev.get("kr"):
        feed["kr"] = prev["kr"]; kept.append("kr")
    rt = F.safe(X.rates, None)
    if rt:
        feed["rates"] = rt
    elif prev.get("rates"):
        feed["rates"] = prev["rates"]; kept.append("rates")
    feed["sources"].update({"traffic": "서울시 실시간 도시데이터 (openapi.seoul.go.kr)",
                            "kr": "한국거래소 KRX Open API (data-dbg.krx.co.kr)", "rates": "한국은행 ECOS (ecos.bok.or.kr)"})
    if kept:
        F.log("직전 값 유지: " + ", ".join(kept))
    feed["stale"] = kept
    # 달러 환율 추이(그래프용): 날짜별 값을 누적, 처음엔 최근 30일 채움
    hist = {h["d"]: h["v"] for h in prev.get("fx_hist", [])}
    usd = next((i for i in feed["fx"].get("items", []) if i["code"] == "USD"), None)
    if usd:
        hist[feed["fx"]["basis"][:5]] = usd["v"]
    if len(hist) < 5:
        for back in range(1, 45):
            day = F.NOW - timedelta(days=back)
            r = F.safe(F.fx_day, None, day)
            if r and "USD" in r:
                hist[day.strftime("%m.%d")] = r["USD"]
            if len(hist) >= 22:
                break
    def _key(md):
        m, d = md.split(".")
        y = F.NOW.year - (1 if int(m) > F.NOW.month else 0)
        return (y, int(m), int(d))
    feed["fx_hist"] = [{"d": k, "v": hist[k]} for k in sorted(hist, key=_key)][-22:]
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "feed.json"), "w", encoding="utf-8") as f:
        json.dump(feed, f, ensure_ascii=False, indent=1)
    with open(os.path.join(out, "feed_log.md"), "w", encoding="utf-8") as f:
        f.write(f"# feed 생성 {F.NOW:%Y-%m-%d %H:%M} KST\n\n" + "\n".join(f"- {l}" for l in F.LOG) + "\n")


if __name__ == "__main__":
    main()
