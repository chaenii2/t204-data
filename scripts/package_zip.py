#!/usr/bin/env python3
"""운영사 전달용 ZIP 패키징 (코엑스 LED ZIP 구성 참고)
- ZIP 루트에 index.html
- 글꼴을 ZIP 안 font/ 폴더에 포함 (외부 글꼴 서버 호출 없음)
- 캐시 금지 메타, 고정 viewport
사용: package_zip.py <빌드된 index.html> <out.zip>
"""
import sys, re, zipfile, pathlib
src, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
root = pathlib.Path(__file__).resolve().parent.parent
font = root / "assets/font/NotoSansKR-T204.woff2"
h = src.read_text(encoding="utf-8")
h = re.sub(r'\s*<link[^>]+fonts\.(googleapis|gstatic)\.com[^>]*>', '', h)
face = ("<style>@font-face{font-family:'Noto Sans KR';src:url('font/NotoSansKR-T204.woff2') format('woff2');"
        "font-weight:100 900;font-style:normal;font-display:block}</style>")
h = h.replace('<meta name="viewport" content="width=device-width, initial-scale=1">',
    '<meta name="viewport" content="width=1200,initial-scale=1,maximum-scale=1,user-scalable=no">\n'
    '<meta http-equiv="Pragma" content="no-cache">\n'
    '<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">\n' + face, 1)
assert 'fonts.googleapis' not in h and 'NotoSansKR-T204' in h
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("index.html", h)
    z.write(font, "font/NotoSansKR-T204.woff2")
print("packaged", out)
