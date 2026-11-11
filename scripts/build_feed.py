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
    t = next(i for i in d["response"]["body"]["items"]["item"] if i["category"] == "T1H")
    F.log(f"지금 기온: {t['obsrValue']}° ({b:%H}:00 관측)")
    return {"t": round(float(t["obsrValue"])), "at": b.strftime("%H:00")}


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "data"
    w = F.safe(F.weather, None)
    if w:
        w["pm"], w["pm25"] = F.safe(F.dust_both, ("보통", "보통"))
        now = F.safe(weather_now, None)
        if now:
            w["now"] = now
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
