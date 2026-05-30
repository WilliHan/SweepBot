#!/usr/bin/env python3
"""
오늘 7% 이상 상승한 종목의 핵심 재료 분석 스크립트.

실행:
    python3 stock_analysis.py              # 오늘 날짜 분석
    python3 stock_analysis.py 20260530     # 특정 날짜 분석

등록된 OpenClaw cron 프롬프트:
    "오늘 7% 이상 상승한 종목의 핵심 재료를 실시간으로 크롤링해서 분석해 줘"
"""

import os
import sys
import json
import time
import logging
import textwrap
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# ── 경로 설정 ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
MSS_ROOT = ROOT.parent / "MSS"
sys.path.insert(0, str(MSS_ROOT))
sys.path.insert(0, str(MSS_ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env", override=False)
load_dotenv(MSS_ROOT / ".env", override=False)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── 설정 ────────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
RISE_THRESHOLD = 7.0          # 상승률 기준 (%)
MAX_STOCKS     = 20           # 최대 분석 종목 수
OUTPUT_DIR     = ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


# ── 1단계: pykrx로 상승률 상위 종목 수집 ──────────────────────────────────────
def get_rising_stocks(date_str: str) -> list[dict]:
    """KRX에서 date_str(YYYYMMDD) 기준 7% 이상 상승 종목 반환."""
    from pykrx import stock as krx

    log.info(f"KRX 데이터 조회: {date_str}")
    try:
        df = krx.get_market_ohlcv_by_ticker(date_str, market="KOSPI")
        df_aq = krx.get_market_ohlcv_by_ticker(date_str, market="KOSDAQ")
    except Exception as e:
        log.error(f"KRX 조회 실패: {e}")
        return []

    import pandas as pd
    df_all = pd.concat([df, df_aq])

    # 등락률 컬럼명 정규화 (pykrx 버전에 따라 다름)
    change_col = next((c for c in df_all.columns if "등락" in c or "change" in c.lower()), None)
    if change_col is None:
        log.warning(f"등락률 컬럼 없음. 컬럼 목록: {list(df_all.columns)}")
        return []

    rising = df_all[df_all[change_col] >= RISE_THRESHOLD].copy()
    rising = rising.sort_values(change_col, ascending=False).head(MAX_STOCKS)

    results = []
    for ticker, row in rising.iterrows():
        try:
            name = krx.get_market_ticker_name(ticker)
        except Exception:
            name = ticker
        results.append({
            "ticker": ticker,
            "name": name,
            "change_pct": round(float(row[change_col]), 2),
            "close": int(row.get("종가", row.get("Close", 0))),
            "volume": int(row.get("거래량", row.get("Volume", 0))),
        })

    log.info(f"7% 이상 상승 종목: {len(results)}개")
    return results


# ── 2단계: 네이버 금융 뉴스 크롤링 ────────────────────────────────────────────
def crawl_naver_news(ticker: str, name: str, max_articles: int = 5) -> list[dict]:
    """네이버 금융에서 종목 관련 최신 뉴스 제목/URL 수집."""
    import urllib.request
    from html.parser import HTMLParser

    _NAVER_BASE = "https://finance.naver.com"

    class NewsParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.results = []
            self._in_title = False
            self._current_href = ""

        def handle_starttag(self, tag, attrs):
            if tag == "a":
                attrs_d = dict(attrs)
                href = attrs_d.get("href", "")
                cls = attrs_d.get("class", "")
                # class="tit" + href=/item/news_read.naver?... 구조
                if "news_read" in href and "tit" in cls:
                    self._current_href = _NAVER_BASE + href
                    self._in_title = True

        def handle_data(self, data):
            if self._in_title and data.strip():
                self.results.append({"title": data.strip(), "url": self._current_href})
                self._in_title = False

    # Referer 없으면 빈 tbody 반환, sm=title_entity_id.basic 제거 필수
    url = f"{_NAVER_BASE}/item/news_news.naver?code={ticker}&page=1&clusterId="
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Referer": f"{_NAVER_BASE}/item/news.naver?code={ticker}",
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            html = resp.read().decode("euc-kr", errors="replace")

        parser = NewsParser()
        parser.feed(html)

        seen = set()
        news = []
        for item in parser.results:
            if item["title"] not in seen:
                seen.add(item["title"])
                news.append(item)
            if len(news) >= max_articles:
                break

        log.info(f"  [{name}] 뉴스 {len(news)}건 수집")
        return news

    except Exception as e:
        log.warning(f"  [{name}] 뉴스 크롤링 실패: {e}")
        return []


# ── 3단계: DART 공시 조회 ────────────────────────────────────────────────────
def get_dart_disclosures(ticker: str, name: str, date_str: str) -> list[dict]:
    """DART API로 오늘 공시 목록 조회."""
    dart_key = os.environ.get("DART_API_KEY", "")
    if not dart_key:
        return []

    import urllib.request
    url = (
        f"https://opendart.fss.or.kr/api/list.json?"
        f"crtfc_key={dart_key}&corp_code=&bgn_de={date_str}&end_de={date_str}"
        f"&last_reprt_at=N&pblntf_ty=A&pblntf_detail_ty=A001&page_no=1&page_count=10"
    )

    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read())

        items = data.get("list", [])
        matched = [
            {"title": i["report_nm"], "date": i["rcept_dt"]}
            for i in items
            if name in i.get("corp_name", "") or ticker in i.get("stock_code", "")
        ]
        if matched:
            log.info(f"  [{name}] DART 공시 {len(matched)}건")
        return matched[:3]

    except Exception as e:
        log.debug(f"  [{name}] DART 조회 실패: {e}")
        return []


# ── 4단계: Gemini로 핵심 재료 분석 ───────────────────────────────────────────
def analyze_with_gemini(stocks_data: list[dict]) -> str:
    """Gemini API로 상승 재료 종합 분석."""
    if not GEMINI_API_KEY:
        return "[GEMINI_API_KEY 없음 — 분석 생략]"

    import urllib.request

    # 프롬프트 구성
    stock_lines = []
    for s in stocks_data:
        news_titles = " / ".join(n["title"] for n in s.get("news", [])[:3]) or "뉴스 없음"
        dart_titles = " / ".join(d["title"] for d in s.get("dart", [])[:2]) or "공시 없음"
        stock_lines.append(
            f"- {s['name']}({s['ticker']}): +{s['change_pct']}%\n"
            f"  뉴스: {news_titles}\n"
            f"  공시: {dart_titles}"
        )

    today = datetime.now().strftime("%Y년 %m월 %d일")
    prompt = textwrap.dedent(f"""
        {today} 한국 주식시장에서 7% 이상 상승한 종목 {len(stocks_data)}개를 분석해줘.

        각 종목에 대해:
        1. 핵심 상승 재료 (뉴스/공시 기반)
        2. 시장 테마 분류 (예: AI, 반도체, 바이오, 정책 등)
        3. 단기 모멘텀 지속 가능성 (3줄 이내)

        종목 데이터:
        {chr(10).join(stock_lines)}

        형식: 종목별로 구분해서 간결하게 한국어로 작성. 추측은 가능하지만 근거를 명시해라.
    """).strip()

    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 2048}
    }).encode()

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    )

    try:
        req = urllib.request.Request(url, data=payload,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())

        text = result["candidates"][0]["content"]["parts"][0]["text"]
        log.info("Gemini 분석 완료")
        return text

    except Exception as e:
        log.error(f"Gemini 분석 실패: {e}")
        return f"[Gemini 오류: {e}]"


# ── 5단계: 결과 저장 ────────────────────────────────────────────────────────
def save_result(date_str: str, stocks: list[dict], analysis: str) -> Path:
    out_file = OUTPUT_DIR / f"stock_analysis_{date_str}.md"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        f"# 주식 급등 재료 분석 — {date_str[:4]}.{date_str[4:6]}.{date_str[6:]}",
        f"",
        f"> 생성: {now} | 기준: +{RISE_THRESHOLD}% 이상 | 종목 수: {len(stocks)}",
        f"",
        f"## 급등 종목 목록",
        f"",
    ]
    for s in stocks:
        news_str = " / ".join(n["title"] for n in s.get("news", [])[:2]) or "—"
        lines.append(f"| {s['name']}({s['ticker']}) | +{s['change_pct']}% | {news_str} |")

    lines += ["", "---", "", "## Gemini 핵심 재료 분석", "", analysis, ""]

    out_file.write_text("\n".join(lines), encoding="utf-8")
    log.info(f"결과 저장: {out_file}")
    return out_file


# ── 메인 ────────────────────────────────────────────────────────────────────
def main():
    date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y%m%d")
    log.info(f"=== 주식 분석 시작: {date_str} ===")

    # 1. 상승 종목 수집
    stocks = get_rising_stocks(date_str)
    if not stocks:
        log.warning("분석 대상 종목 없음 (장 마감 전이거나 데이터 없음)")
        sys.exit(0)

    # 2. 뉴스/공시 수집
    for s in stocks:
        time.sleep(0.5)  # 네이버 크롤링 딜레이
        s["news"] = crawl_naver_news(s["ticker"], s["name"])
        s["dart"] = get_dart_disclosures(s["ticker"], s["name"], date_str)

    # 3. Gemini 분석
    analysis = analyze_with_gemini(stocks)

    # 4. 결과 저장
    out_file = save_result(date_str, stocks, analysis)

    # 5. 콘솔 출력
    print("\n" + "=" * 60)
    print(f"분석 완료: {date_str}")
    print("=" * 60)
    for s in stocks[:5]:
        print(f"  {s['name']:12s} +{s['change_pct']:5.1f}%  {', '.join(n['title'][:20] for n in s['news'][:1])}")
    if len(stocks) > 5:
        print(f"  ... 외 {len(stocks)-5}개")
    print("-" * 60)
    print(analysis[:800] + ("..." if len(analysis) > 800 else ""))
    print(f"\n전체 결과: {out_file}")


if __name__ == "__main__":
    main()
