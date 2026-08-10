import os
from datetime import datetime
from zoneinfo import ZoneInfo

import yfinance as yf
from google import genai
import requests


# =========================================================
# 환경변수
# =========================================================

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]


# =========================================================
# 기본 설정
# =========================================================

KST = ZoneInfo("Asia/Seoul")

now = datetime.now(KST)

current_date = now.strftime("%Y년 %m월 %d일")

current_time = now.strftime("%H:%M")

weekday_names = [
    "월요일",
    "화요일",
    "수요일",
    "목요일",
    "금요일",
    "토요일",
    "일요일"
]

weekday = weekday_names[now.weekday()]


# =========================================================
# 오전 / 오후 분석 구분
# =========================================================

if now.hour < 12:

    report_type = "🌅 오전 시장 브리핑"

    market_focus = """
이번 보고서는 한국시간 오전 시장 브리핑이다.

중점적으로 분석할 것:

- 직전 미국 증시 마감
- S&P 500
- NASDAQ
- Dow Jones
- 미국 주요 기술주
- 거래량 변화
- 미국 국채금리 및 달러 관련 흐름
- 밤사이 주요 뉴스
- 연준 및 미국 경제 관련 뉴스
- 오늘 미국 시장에서 주목할 종목
- 오늘 시장에서 주목할 위험요인
"""

else:

    report_type = "🌇 오후 시장 브리핑"

    market_focus = """
이번 보고서는 한국시간 오후 시장 브리핑이다.

중점적으로 분석할 것:

- 최근 미국 증시 흐름
- S&P 500
- NASDAQ
- Dow Jones
- 미국 주요 기술주
- 거래량 변화
- 최근 주요 뉴스
- 미국 경제 및 연준 관련 뉴스
- 미국 시장에서 주목할 종목
- 미국 시장의 주요 상승 및 하락 요인
- 다음 미국 증시 거래에서 주목할 사항
"""


# =========================================================
# Yahoo Finance 시장 데이터
# =========================================================

MARKET_SYMBOLS = [
    ("^GSPC", "S&P 500"),
    ("^IXIC", "NASDAQ"),
    ("^DJI", "Dow Jones"),
    ("^VIX", "VIX"),
    ("^TNX", "미국 10년물 금리"),
    ("KRW=X", "USD/KRW"),
    ("GC=F", "Gold"),
    ("CL=F", "WTI Crude Oil"),
]


# 주요 미국 기술주
STOCK_SYMBOLS = [
    ("NVDA", "NVIDIA"),
    ("AAPL", "Apple"),
    ("MSFT", "Microsoft"),
    ("AMZN", "Amazon"),
    ("GOOGL", "Alphabet"),
    ("META", "Meta"),
    ("TSLA", "Tesla"),
    ("AVGO", "Broadcom"),
    ("AMD", "AMD"),
    ("NFLX", "Netflix"),
]


def get_quote(symbol, name):

    try:

        ticker = yf.Ticker(symbol)

        history = ticker.history(
            period="5d",
            interval="1d"
        )

        if history.empty:
            return None

        history = history.dropna(subset=["Close"])

        if history.empty:
            return None

        latest = history.iloc[-1]

        close = float(latest["Close"])

        previous_close = None

        if len(history) >= 2:
            previous_close = float(
                history.iloc[-2]["Close"]
            )

        change_percent = None

        if previous_close:
            change_percent = (
                (close - previous_close)
                / previous_close
            ) * 100

        volume = latest.get("Volume")

        if volume is not None:
            volume = int(volume)

        return {
            "name": name,
            "symbol": symbol,
            "close": close,
            "previous_close": previous_close,
            "change_percent": change_percent,
            "volume": volume
        }

    except Exception as error:

        print(
            f"시장 데이터 수집 실패 "
            f"({name}): {error}"
        )

        return None


def collect_market_data():

    results = []

    for symbol, name in MARKET_SYMBOLS:

        result = get_quote(
            symbol,
            name
        )

        if result:
            results.append(result)

    return results


def collect_stock_data():

    results = []

    for symbol, name in STOCK_SYMBOLS:

        result = get_quote(
            symbol,
            name
        )

        if result:
            results.append(result)

    return results


# =========================================================
# Yahoo Finance 뉴스
# =========================================================

def collect_news():

    queries = [
        "US stock market",
        "S&P 500 Nasdaq",
        "Federal Reserve",
        "US economy",
        "technology stocks",
        "NVIDIA",
        "Apple",
        "Microsoft"
    ]

    all_news = []

    for query in queries:

        try:

            search = yf.Search(
                query,
                max_results=10,
                news_count=10
            )

            news_items = search.news

            if not news_items:
                continue

            for item in news_items:

                content = item.get(
                    "content",
                    {}
                )

                title = content.get(
                    "title",
                    ""
                )

                if not title:
                    continue

                provider = content.get(
                    "provider",
                    {}
                )

                source = provider.get(
                    "displayName",
                    ""
                )

                canonical_url = content.get(
                    "canonicalUrl",
                    {}
                )

                link = canonical_url.get(
                    "url",
                    ""
                )

                pub_date = content.get(
                    "pubDate",
                    ""
                )

                all_news.append({
                    "title": title,
                    "source": source,
                    "date": pub_date,
                    "link": link
                })

        except Exception as error:

            print(
                f"뉴스 수집 실패 "
                f"({query}): {error}"
            )

    # 제목 중복 제거
    unique_news = []

    seen_titles = set()

    for article in all_news:

        title_key = article["title"].strip().lower()

        if title_key in seen_titles:
            continue

        seen_titles.add(title_key)

        unique_news.append(article)

    return unique_news[:30]


# =========================================================
# 데이터 → Gemini용 텍스트
# =========================================================

def build_market_information(
    market_data,
    stock_data,
    news
):

    text = ""

    text += """
===========================
📊 주요 시장 데이터
===========================
"""

    for item in market_data:

        change = item["change_percent"]

        if change is not None:

            text += (
                f"- {item['name']} "
                f"({item['symbol']}): "
                f"{item['close']:.2f} "
                f"({change:+.2f}%)"
            )

        else:

            text += (
                f"- {item['name']} "
                f"({item['symbol']}): "
                f"{item['close']:.2f}"
            )

        if item["volume"] is not None:

            text += (
                f" | 거래량: "
                f"{item['volume']:,}"
            )

        text += "\n"


    text += """
===========================
🏢 주요 미국 기술주
===========================
"""

    for item in stock_data:

        change = item["change_percent"]

        if change is not None:

            text += (
                f"- {item['name']} "
                f"({item['symbol']}): "
                f"{item['close']:.2f} "
                f"({change:+.2f}%)"
            )

        else:

            text += (
                f"- {item['name']} "
                f"({item['symbol']}): "
                f"{item['close']:.2f}"
            )

        if item["volume"] is not None:

            text += (
                f" | 거래량: "
                f"{item['volume']:,}"
            )

        text += "\n"


    text += """
===========================
📰 Yahoo Finance 최신 뉴스
===========================
"""

    if news:

        for index, article in enumerate(
            news,
            start=1
        ):

            text += (
                f"{index}. "
                f"{article['title']}\n"
                f"   출처: "
                f"{article['source']}\n"
                f"   시각: "
                f"{article['date']}\n"
                f"   링크: "
                f"{article['link']}\n"
            )

    else:

        text += "뉴스를 가져오지 못했습니다.\n"

    return text


# =========================================================
# Gemini 분석
# =========================================================

def analyze_with_gemini(
    market_information
):

    client = genai.Client(
        api_key=GEMINI_API_KEY
    )

    prompt = f"""
현재 한국시간:

{current_date} {current_time}
({weekday})

보고서:

{report_type}

너는 전문 미국 주식시장 분석가다.

Yahoo Finance에서 수집한 최신 시장 데이터와
최신 뉴스를 기반으로 미국 주식시장을 분석해라.

{market_focus}

===========================
Yahoo Finance 데이터
===========================

{market_information}

===========================
분석 원칙
===========================

1. 제공된 최신 데이터를 최우선으로 사용한다.
2. 데이터에 없는 내용을 사실처럼 만들지 않는다.
3. 사실과 전망을 구분한다.
4. 숫자가 있으면 가능한 경우 포함한다.
5. 주가와 거래량을 함께 분석한다.
6. 단순한 가격 상승/하락보다 거래량과 뉴스가 가격 움직임을 뒷받침하는지 분석한다.
7. 서로 다른 뉴스가 같은 시장 방향을 가리키는지 확인한다.
8. 과도한 낙관 또는 비관을 피한다.
9. 투자 추천이 아니라 시장 분석으로 작성한다.
10. 불확실한 내용은 불확실하다고 표시한다.

===========================
최종 보고서
===========================

반드시 아래 구조를 사용한다.

📊 미국 증시 AI 시장 브리핑
📅 {current_date} ({weekday})
⏰ 분석 기준: {current_time} KST
📌 {report_type}

━━━━━━━━━━━━━━━━

🇺🇸 미국 증시 한눈에 보기

- S&P 500
- NASDAQ
- Dow Jones
- 전체 시장 방향

📈 시장 흐름

- 핵심 시장 흐름 2~3개
- 상승 또는 하락의 주요 원인

🔥 거래량 분석

- 거래량이 눈에 띄는 주요 종목
- 거래량과 주가 움직임의 관계
- 시장 강도에 대한 판단

📰 주요 뉴스

- 시장에 영향을 줄 가능성이 높은 뉴스 3~5개
- 각 뉴스가 시장에 미치는 영향

🏢 주요 종목

- NVIDIA
- Apple
- Microsoft
- Amazon
- Alphabet
- Meta
- Tesla

필요한 경우 위 종목 중 중요한 종목만 선택한다.

📊 시장에 영향을 주는 요인

- 금리
- 달러
- 국채금리
- 유가 / 원자재
- 연준
- 경제지표

데이터가 제공되지 않은 항목은 억지로 추측하지 않는다.

🟢 상승 요인

- 중요한 상승 요인 2~3개

🔴 하락 요인

- 중요한 하락 요인 2~3개

⚠️ 주요 리스크

- 중요한 위험 2~3개

👀 오늘 체크할 것

- 투자자가 확인해야 할 지표나 뉴스 2~3개

🤖 Gemini 종합 분석

- 현재 시장에서 가장 중요한 흐름
- 단기적으로 주목할 부분
- 시장이 예상과 다르게 움직일 경우 확인할 부분

🎯 최종 판단

현재 미국 증시에 대한 핵심 판단을
2~3문장으로 작성한다.

📌 투자 참고용이며 투자 권유가 아닙니다.

===========================

작성 규칙:

- 한국어로 작성
- 1,800자 이내
- 긴 문단 금지
- 짧은 bullet 중심
- 같은 내용 반복 금지
- 읽기 쉬운 Discord 형식
"""

    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=prompt
    )

    return response.text


# =========================================================
# Discord 메시지 분할
# =========================================================

def split_message(
    text,
    max_length=1900
):

    paragraphs = text.split("\n\n")

    chunks = []

    current = ""

    for paragraph in paragraphs:

        paragraph = paragraph.strip()

        if not paragraph:
            continue

        candidate = (
            current + "\n\n" + paragraph
            if current
            else paragraph
        )

        if len(candidate) <= max_length:

            current = candidate

        else:

            if current:
                chunks.append(current)

            if len(paragraph) > max_length:

                lines = paragraph.split("\n")

                current = ""

                for line in lines:

                    line = line.strip()

                    if not line:
                        continue

                    candidate = (
                        current + "\n" + line
                        if current
                        else line
                    )

                    if len(candidate) <= max_length:

                        current = candidate

                    else:

                        if current:
                            chunks.append(current)

                        while len(line) > max_length:

                            chunks.append(
                                line[:max_length]
                            )

                            line = line[
                                max_length:
                            ]

                        current = line

            else:

                current = paragraph

    if current:
        chunks.append(current)

    return chunks


# =========================================================
# Discord 전송
# =========================================================

def send_to_discord(report):

    chunks = split_message(
        report,
        max_length=1900
    )

    total = len(chunks)

    print(
        f"Discord 전송 메시지 수: {total}"
    )

    for index, chunk in enumerate(
        chunks,
        start=1
    ):

        if total > 1:

            content = (
                f"📊 **Gemini 미국 증시 브리핑 "
                f"({index}/{total})**\n\n"
                f"{chunk}"
            )

        else:

            content = chunk

        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json={
                "content": content
            },
            timeout=30
        )

        if not response.ok:

            print(
                "Discord 응답 상태:",
                response.status_code
            )

            print(
                "Discord 응답 내용:",
                response.text
            )

        response.raise_for_status()


# =========================================================
# 실행
# =========================================================

print("====================================")
print("미국 증시 AI 분석 시작")
print("====================================")

print("시장 데이터 수집 중...")

market_data = collect_market_data()

print(
    f"시장 데이터 수집 완료: "
    f"{len(market_data)}건"
)

print("주요 종목 데이터 수집 중...")

stock_data = collect_stock_data()

print(
    f"주요 종목 데이터 수집 완료: "
    f"{len(stock_data)}건"
)

print("Yahoo Finance 뉴스 수집 중...")

latest_news = collect_news()

print(
    f"뉴스 수집 완료: "
    f"{len(latest_news)}건"
)

market_information = build_market_information(
    market_data,
    stock_data,
    latest_news
)

print("Gemini 분석 시작...")

final_report = analyze_with_gemini(
    market_information
)

print("Gemini 분석 완료")

with open(
    "daily_report.txt",
    "w",
    encoding="utf-8"
) as file:

    file.write(final_report)

print("Discord 전송 시작...")

send_to_discord(
    final_report
)

print("====================================")
print("모든 작업 완료")
print("====================================")
