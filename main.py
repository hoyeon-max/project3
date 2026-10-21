
# main.py
# 영화진흥위원회(KOBIS) 일별 박스오피스 조회 앱
# Streamlit Cloud 배포용

import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import requests
import streamlit as st


# --------------------------------------------------
# 1. 기본 설정
# --------------------------------------------------

st.set_page_config(
    page_title="박스오피스 탐험",
    page_icon="🎬",
    layout="wide",
)

API_URL = (
    "https://www.kobis.or.kr/kobisopenapi/webservice/rest/"
    "boxoffice/searchDailyBoxOfficeList.json"
)

# 서버 시간대와 상관없이 한국 시간으로 날짜 계산
KST = ZoneInfo("Asia/Seoul")
TODAY_KST = datetime.datetime.now(KST).date()
YESTERDAY = TODAY_KST - datetime.timedelta(days=1)

# KOBIS 일별 박스오피스 조회 시작일을 달력의 최소 날짜로 사용
EARLIEST_DATE = datetime.date(2004, 1, 1)


def format_number(value):
    """숫자에 천 단위 쉼표를 넣는다."""
    return f"{int(value):,}"


# --------------------------------------------------
# 2. 앱 제목과 날짜 선택
# --------------------------------------------------

st.title("🎬 박스오피스 탐험")
st.caption("영화진흥위원회(KOBIS) 공식 일별 박스오피스")
st.divider()

st.subheader("📅 조회 날짜 선택")

selected_date = st.date_input(
    "보고 싶은 날짜를 선택하세요.",
    value=YESTERDAY,
    min_value=EARLIEST_DATE,
    max_value=YESTERDAY,
    format="YYYY-MM-DD",
)

target_dt = selected_date.strftime("%Y%m%d")
display_date = selected_date.strftime("%Y년 %m월 %d일")

st.caption(
    f"선택한 날짜: {display_date} · "
    f"오늘({TODAY_KST.strftime('%Y-%m-%d')})은 아직 선택할 수 없습니다."
)


# --------------------------------------------------
# 3. Secrets에서 API 인증키 불러오기
# --------------------------------------------------

try:
    API_KEY = st.secrets["KOBIS_KEY"]
except (KeyError, FileNotFoundError, RuntimeError):
    st.error("🔑 KOBIS 인증키를 찾을 수 없습니다.")
    st.markdown(
        """
        **인증키 설정을 확인해 주세요.**

        1. Streamlit Cloud에서 앱의 Settings → Secrets로 이동합니다.
        2. 다음 형식으로 인증키를 등록합니다.
        3. 저장한 뒤 앱을 다시 실행합니다.
        """
    )
    st.code('KOBIS_KEY = "발급받은_인증키"', language="toml")
    st.stop()

if not str(API_KEY).strip():
    st.error("🔑 KOBIS_KEY 값이 비어 있습니다.")
    st.info("Secrets에 올바른 인증키를 등록해 주세요.")
    st.stop()


# --------------------------------------------------
# 4. KOBIS API 호출
# --------------------------------------------------

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_boxoffice(date_str, api_key):
    """선택한 날짜의 박스오피스 데이터를 가져온다."""

    response = requests.get(
        API_URL,
        params={
            "key": api_key,
            "targetDt": date_str,
        },
        timeout=20,
    )

    response.raise_for_status()

    try:
        data = response.json()
    except ValueError as exc:
        raise ValueError("API 응답이 올바른 JSON이 아닙니다.") from exc

    if not isinstance(data, dict):
        raise ValueError("API 응답 형식이 올바르지 않습니다.")

    return data


try:
    with st.spinner(f"{display_date} 박스오피스를 불러오는 중입니다..."):
        data = fetch_boxoffice(target_dt, str(API_KEY))

except requests.exceptions.Timeout:
    st.error("⏱️ KOBIS 서버의 응답 시간이 초과되었습니다.")
    st.info("잠시 기다렸다가 다시 조회해 주세요.")
    st.stop()

except requests.exceptions.HTTPError as exc:
    st.error("🌐 KOBIS 서버에서 HTTP 오류가 발생했습니다.")
    st.caption(f"응답 상태 코드: {exc.response.status_code}")
    st.info("API 주소와 KOBIS 서버 상태를 확인해 주세요.")
    st.stop()

except requests.exceptions.RequestException:
    st.error("🌐 KOBIS 서버에 연결하지 못했습니다.")
    st.info("네트워크 연결과 KOBIS 서버 상태를 확인해 주세요.")
    st.stop()

except (ValueError, KeyError, RuntimeError):
    st.error("⚠️ 데이터를 불러오거나 해석하지 못했습니다.")
    st.info("인증키와 API 응답 형식을 확인해 주세요.")
    st.stop()


# --------------------------------------------------
# 5. API가 반환한 오류 확인
# --------------------------------------------------

# 인증키가 틀려도 HTTP 상태코드는 200일 수 있으므로
# 응답 안에 faultInfo가 있는지 반드시 확인한다.
if "faultInfo" in data:
    fault = data.get("faultInfo") or {}

    if isinstance(fault, dict):
        error_code = fault.get("errorCode", "정보 없음")
        error_message = fault.get(
            "message",
            "상세 오류 메시지가 없습니다.",
        )
    else:
        error_code = "정보 없음"
        error_message = str(fault)

    st.error("🚨 KOBIS API에서 오류가 반환되었습니다.")
    st.write(f"**오류 코드:** {error_code}")
    st.write(f"**오류 메시지:** {error_message}")
    st.info(
        "Streamlit Secrets의 KOBIS_KEY가 정확한지, "
        "인증키가 정상적으로 발급되었는지 확인해 주세요."
    )
    st.stop()


# --------------------------------------------------
# 6. 영화 목록 확인
# --------------------------------------------------

boxoffice_result = data.get("boxOfficeResult")

if not isinstance(boxoffice_result, dict):
    st.error("⚠️ 박스오피스 결과를 찾을 수 없습니다.")
    st.info("KOBIS API 주소와 응답 구조를 확인해 주세요.")
    st.stop()

movies = boxoffice_result.get("dailyBoxOfficeList", [])

if not isinstance(movies, list) or len(movies) == 0:
    st.warning("📭 그날은 아직 집계 전입니다")
    st.info(
        f"{display_date}의 영화 목록이 비어 있습니다. "
        "집계가 완료된 뒤 다시 조회해 주세요. "
        "과거 날짜라면 KOBIS에서 해당 날짜의 자료를 제공하는지도 확인해 주세요."
    )
    st.stop()


# --------------------------------------------------
# 7. 데이터 정리
# --------------------------------------------------

df = pd.DataFrame(movies)

required_columns = [
    "rank",
    "rankInten",
    "movieNm",
    "openDt",
    "audiCnt",
    "audiAcc",
    "scrnCnt",
]

missing_columns = [
    column for column in required_columns
    if column not in df.columns
]

if missing_columns:
    st.error("⚠️ API 응답에 필요한 항목이 누락되었습니다.")
    st.write("누락된 항목:", ", ".join(missing_columns))
    st.info("KOBIS API 응답 구조를 확인해 주세요.")
    st.stop()

# API 숫자 값은 문자열이므로 숫자로 변환한다.
try:
    for column in [
        "rank",
        "rankInten",
        "audiCnt",
        "audiAcc",
        "scrnCnt",
    ]:
        df[column] = pd.to_numeric(df[column], errors="raise")

except (ValueError, TypeError):
    st.error("⚠️ 순위 또는 관객수 데이터를 해석할 수 없습니다.")
    st.info("KOBIS API의 숫자 항목을 확인해 주세요.")
    st.stop()

df["movieNm"] = (
    df["movieNm"].fillna("영화명 정보 없음").astype(str)
)
df["openDt"] = df["openDt"].fillna("").astype(str)

# 순위가 낮은 숫자부터 표시
df = df.sort_values("rank").reset_index(drop=True)

# 누적 관객수가 100만 명을 초과하면 트로피 추가
df["표시영화명"] = df.apply(
    lambda row: (
        f"{row['movieNm']} 🏆"
        if row["audiAcc"] > 1_000_000
        else row["movieNm"]
    ),
    axis=1,
)


# --------------------------------------------------
# 8. 1위 영화 지표 카드 3개
# --------------------------------------------------

first_movie = df.iloc[0]

st.subheader(f"🥇 {display_date} 1위: {first_movie['표시영화명']}")

card1, card2, card3 = st.columns(3)

with card1:
    st.metric(
        label="🎟️ 당일 관객수",
        value=f"{format_number(first_movie['audiCnt'])}명",
    )

with card2:
    st.metric(
        label="👥 누적 관객수",
        value=f"{format_number(first_movie['audiAcc'])}명",
    )

with card3:
    st.metric(
        label="🖥️ 스크린수",
        value=f"{format_number(first_movie['scrnCnt'])}개",
    )

st.caption("🏆 표시는 누적 관객수가 100만 명을 초과한 영화를 뜻합니다.")
st.divider()


# --------------------------------------------------
# 9. 전체 영화 순위표
# --------------------------------------------------

st.subheader("📋 전체 박스오피스 순위")

table = df[
    [
        "rank",
        "rankInten",
        "표시영화명",
        "openDt",
        "audiCnt",
        "audiAcc",
        "scrnCnt",
    ]
].copy()

table.columns = [
    "순위",
    "순위 변동",
    "영화명",
    "개봉일",
    "관객수",
    "누적관객",
    "스크린수",
]


def make_rank_change(value):
    """전날 대비 순위 변동을 화살표와 숫자로 표시한다."""
    value = int(value)

    if value > 0:
        # rankInten이 양수면 순위가 상승한 영화
        return f"↑ {value}"
    elif value < 0:
        # rankInten이 음수면 순위가 하락한 영화
        return f"↓ {abs(value)}"
    else:
        return "—"


table["순위 변동"] = table["순위 변동"].map(make_rank_change)
table["순위"] = table["순위"].map(lambda value: f"{int(value)}위")
table["개봉일"] = table["개봉일"].replace("", "정보 없음")

for column in ["관객수", "누적관객", "스크린수"]:
    table[column] = table[column].map(
        lambda value: f"{int(value):,}"
    )


# 순위 상승은 빨간색, 하락은 파란색으로 강조한다.
def color_rank_change(value):
    if value.startswith("↑"):
        return "color: red; font-weight: bold"
    elif value.startswith("↓"):
        return "color: blue; font-weight: bold"
    return "color: gray"


styled_table = table.style.map(
    color_rank_change,
    subset=["순위 변동"],
)

st.dataframe(
    styled_table,
    hide_index=True,
    use_container_width=True,
)


# --------------------------------------------------
# 10. 관객수 상위 5편 막대그래프
# --------------------------------------------------

st.subheader("📊 관객수 상위 5편")

top5 = df.nlargest(5, "audiCnt").copy()
top5 = top5.sort_values("audiCnt", ascending=True)

fig = px.bar(
    top5,
    x="audiCnt",
    y="표시영화명",
    orientation="h",
    text="audiCnt",
    labels={
        "audiCnt": "당일 관객수(명)",
        "표시영화명": "영화명",
    },
    title=f"{display_date} 관객수 TOP 5",
)

fig.update_traces(
    texttemplate="%{text:,.0f}명",
    textposition="outside",
    cliponaxis=False,
)

fig.update_layout(
    xaxis=dict(tickformat=","),
    yaxis_title="",
    xaxis_title="당일 관객수(명)",
    margin=dict(l=20, r=80, t=60, b=30),
)

st.plotly_chart(fig, use_container_width=True)


# --------------------------------------------------
# 11. 데이터 출처
# --------------------------------------------------

st.divider()
st.caption(
    "데이터 출처: 영화진흥위원회(KOBIS) 일별 박스오피스 Open API"
)
st.caption(f"조회 기준일: {target_dt}")
st.caption(
    "순위 변동은 KOBIS에서 제공하는 rankInten 값을 사용합니다."
)
