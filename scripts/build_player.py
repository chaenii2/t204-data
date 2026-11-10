"""플레이어 HTML/zip 빌드.

python scripts/build_player.py relay  --feed-url https://chaenii2.github.io/t204-data/feed.json --embed data/feed.json --out dist/A
python scripts/build_player.py direct --embed data/feed.json --out dist/B   (키는 환경변수에서 읽어 HTML에 넣음: 테스트 전용)
"""
import argparse
import json
import os
import pathlib
import shutil
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
TPL = ROOT / "template"


def finalize_embedded(feed):
    """내장(오프라인 대비) 데이터: 화면 템플릿이 바로 쓸 수 있는 형태로."""
    d = dict(feed)
    d.setdefault("sample", False)
    d.setdefault("updated", {"morning": "", "evening": ""})
    d.setdefault("sponsor", {"morning": "", "evening": ""})
    d["date"] = feed["generated_at"][:10]
    import datetime as dt
    d["dow"] = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"][dt.date.fromisoformat(d["date"]).weekday()]
    d.setdefault("ipo", {"morning": [], "evening": []})
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["relay", "direct"])
    ap.add_argument("--feed-url", default="https://chaenii2.github.io/t204-data/feed.json")
    ap.add_argument("--embed", default=str(ROOT / "data" / "feed.json"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--zip", default="")
    ap.add_argument("--diag", action="store_true", help="열면 바로 연결 진단 화면")
    a = ap.parse_args()

    feed = json.loads(pathlib.Path(a.embed).read_text(encoding="utf-8"))
    cfg = {"mode": a.mode, "diag": a.diag}
    if a.mode == "relay":
        cfg["feedUrl"] = a.feed_url
    else:
        # 브라우저 직접 호출을 허용하는 공공데이터포털 키만 넣음 (수출입은행·DART는 CORS 미허용 → 중계)
        cfg["keys"] = {"DATA_GO_KR_KEY": os.environ.get("DATA_GO_KR_KEY", "").strip()}
        cfg["feedUrl"] = a.feed_url
    html = (TPL / "player_v4.src.html").read_text(encoding="utf-8")
    html = html.replace("/*DATA*/", json.dumps(finalize_embedded(feed), ensure_ascii=False))
    html = html.replace("/*CONFIG*/", json.dumps(cfg, ensure_ascii=False))
    html = html.replace("/*LOADER*/", (TPL / "loader.js").read_text(encoding="utf-8"))
    out = pathlib.Path(a.out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    (out / "index.html").write_text(html, encoding="utf-8")
    if a.zip:
        with zipfile.ZipFile(a.zip, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(out / "index.html", "index.html")
    print("built", out)


if __name__ == "__main__":
    main()
