
# main.py
# 어제의 박스오피스 — 영화진흥위원회(KOBIS) Open API
# Streamlit Cloud 배포용

import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import requests
import streamlit as st


# --------------------------------------------------
# 1. 기본 화면 설정
# --------------------------------------------------

st.set_page_config(
    page_title="어제의 박스오피스",
    page_icon="🎬",
    layout="wide",
)

API_URL = (
    "https://www.kobis.or.kr/kobisopenapi/webservice/rest/"
    "boxoffice/searchDailyBoxOfficeList.json"
)

# 한국 시간 기준으로 어제 날짜를 계산한다.
# 배포 서버의 시간대가 달라도 항상 한국 날짜를 사용한다.
KST = ZoneInfo("Asia/Seoul")
today_kst = datetime.datetime.now(KST).date()
yesterday = today_kst - datetime.timedelta(days=1)

target_dt = yesterday.strftime("%Y%m%d")
display_date = yesterday.strftime("%Y년 %m월 %d일")

# 숫자에 천 단위 쉼표를 넣어 읽기 쉽게 표시한다.
def format_number(value):
    """숫자를 1,234 형태의 문자열로 변환한다."""
    return f"{int(value):,}"


# --------------------------------------------------
# 2. 화면 제목
# --------------------------------------------------

st.title("🎬 어제의 박스오피스")
st.caption(
    f"📅 조회 날짜: {display_date} · 한국 시간 기준"
)
st.divider()


# --------------------------------------------------
# 3. 인증키 확인
# --------------------------------------------------

# 인증키를 코드에 직접 적지 않고 Streamlit 비밀 금고에서 읽는다.
# Streamlit Cloud의 앱 설정 → Secrets에 KOBIS_KEY를 등록해야 한다.
try:
    api_key = st.secrets["KOBIS_KEY"]
except (KeyError, FileNotFoundError, RuntimeError):
    st.error("🔑 KOBIS 인증키를 찾을 수 없습니다.")
    st.markdown(
        """
        **다음 항목을 확인해 주세요.**

        1. Streamlit Cloud에서 앱의 **Settings → Secrets**를 엽니다.
        2. `KOBIS_KEY`라는 이름으로 발급받은 인증키를 등록합니다.
        3. 저장한 뒤 앱을 다시 실행합니다.
        """
    )
    st.code('KOBIS_KEY = "발급받은 인증키"', language="toml")
    st.stop()

if not str(api_key).strip():
    st.error("🔑 KOBIS_KEY 값이 비어 있습니다.")
    st.info("Streamlit Cloud의 Secrets에 유효한 인증키를 등록해 주세요.")
    st.stop()


# --------------------------------------------------
# 4. KOBIS API에서 박스오피스 데이터 가져오기
# --------------------------------------------------

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_boxoffice(date_str):
    """KOBIS API에 요청하고 JSON 응답을 반환한다."""
    # 캐시된 결과를 인증키 값 자체에 연결하지 않도록
    # 함수 안에서 비밀 금고의 키를 읽는다.
    key = st.secrets["KOBIS_KEY"]

    response = requests.get(
        API_URL,
        params={
            "key": key,
            "targetDt": date_str,
        },
        timeout=20,
    )

    # HTTP 4xx, 5xx 등의 오류를 확인한다.
    response.raise_for_status()

    # 응답 본문이 올바른 JSON인지 검사한다.
    try:
        data = response.json()
    except ValueError as exc:
        raise ValueError(
            "API 응답을 JSON으로 읽을 수 없습니다."
        ) from exc

    if not isinstance(data, dict):
        raise ValueError("API 응답 형식이 올바르지 않습니다.")

    return data


# API 요청 실행 및 연결 오류 처리
try:
    with st.spinner("어제의 영화 순위를 불러오는 중입니다..."):
        data = fetch_boxoffice(target_dt)

except requests.exceptions.Timeout:
    st.error("⏱️ KOBIS 서버의 응답 시간이 초과되었습니다.")
    st.info("잠시 기다렸다가 새로고침해 주세요.")

    st.stop()

except requests.exceptions.HTTPError as exc:
    st.error("🌐 KOBIS 서버가 요청을 처리하지 못했습니다.")
    st.caption(f"응답 상태: {exc.response.status_code}")
    st.info(
        "인터넷 연결, API 주소 또는 KOBIS 서버 상태를 확인해 주세요."
    )

    st.stop()

except requests.exceptions.RequestException:
    st.error("🌐 KOBIS 서버에 연결하지 못했습니다.")
    st.info(
        "Streamlit Cloud의 인터넷 연결과 KOBIS 서버 상태를 확인한 뒤 "
        "잠시 후 다시 시도해 주세요."
    )

    st.stop()

except (ValueError, KeyError, RuntimeError):
    st.error("⚠️ 박스오피스 데이터를 불러오거나 해석하지 못했습니다.")
    st.info(
        "Secrets의 KOBIS_KEY, API 응답 형식, KOBIS 서버 상태를 확인해 주세요."
    )

    st.stop()


# --------------------------------------------------
# 5. API 오류 응답 확인
# --------------------------------------------------

# 중요: 인증키가 틀려도 HTTP 상태코드는 200일 수 있다.
# 따라서 상태코드만 믿지 않고 faultInfo를 별도로 확인한다.
if "faultInfo" in data:
    fault = data.get("faultInfo") or {}

    if isinstance(fault, dict):
        error_code = fault.get("errorCode", "정보 없음")
        error_message = fault.get("message", "상세 오류 메시지 없음")
    else:
        error_code = "정보 없음"
        error_message = str(fault)

    st.error("🚨 KOBIS API에서 오류 응답을 반환했습니다.")
    st.write(f"**오류 코드:** {error_code}")
    st.write(f"**오류 메시지:** {error_message}")
    st.info(
        "KOBIS_KEY에 입력한 인증키가 정확한지, 발급 및 사용 상태가 "
        "정상인지 확인해 주세요."
    )

    st.stop()


# --------------------------------------------------
# 6. 영화 목록 확인
# --------------------------------------------------

boxoffice_result = data.get("boxOfficeResult")

if not isinstance(boxoffice_result, dict):
    st.error("⚠️ API 응답에 박스오피스 결과가 없습니다.")
    st.info(
        "KOBIS API 주소와 응답 구조를 확인해 주세요. "
        "잠시 후 다시 시도해 보는 것도 좋습니다."
    )
    st.stop()

movies = boxoffice_result.get("dailyBoxOfficeList", [])

if not isinstance(movies, list) or len(movies) == 0:
    st.warning(f"📭 {display_date}의 영화 목록이 비어 있습니다.")
    st.markdown(
        """
        **다음 항목을 확인해 주세요.**

        - 해당 날짜의 박스오피스 집계가 완료되었는지 확인합니다.
        - KOBIS에서 해당 날짜의 일별 박스오피스 자료가 제공되는지 확인합니다.
        - 잠시 후 앱을 새로고침해 다시 조회합니다.
        """
    )
    st.stop()


# --------------------------------------------------
# 7. 데이터 정리
# --------------------------------------------------

df = pd.DataFrame(movies)

# 화면과 그래프에 필요한 열이 응답에 존재하는지 확인한다.
required_columns = [
    "rank",
    "movieNm",
    "openDt",
    "audiCnt",
    "audiAcc",
    "scrnCnt",
]

missing_columns = [
    col for col in required_columns if col not in df.columns
]

if missing_columns:
    st.error("⚠️ API 응답에 필요한 항목이 누락되었습니다.")
    st.write("누락된 항목:", ", ".join(missing_columns))
    st.info("KOBIS API의 응답 구조를 확인해 주세요.")
    st.stop()

# API 숫자 값은 문자열로 오므로 정수형 숫자로 변환한다.
numeric_columns = ["rank", "audiCnt", "audiAcc", "scrnCnt"]

try:
    for col in numeric_columns:
        df[col] = pd.to_numeric(df[col], errors="raise")

except (ValueError, TypeError):
    st.error("⚠️ 관객수나 순위 등 숫자 데이터를 읽을 수 없습니다.")
    st.info("KOBIS API 응답의 숫자 항목을 확인해 주세요.")
    st.stop()

# 영화명과 개봉일이 비어 있는 경우를 고려한다.
df["movieNm"] = df["movieNm"].fillna("영화명 정보 없음").astype(str)
df["openDt"] = df["openDt"].fillna("").astype(str)

# 순위 오름차순으로 정리한다.
df = df.sort_values("rank").reset_index(drop=True)


# --------------------------------------------------
# 8. 1위 영화 지표 카드 3개
# --------------------------------------------------

first_movie = df.iloc[0]

st.subheader(f"🥇 오늘의 1위 영화: {first_movie['movieNm']}")

card1, card2, card3 = st.columns(3)

with card1:
    st.metric(
        label="🎟️ 어제 관객수",
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

st.caption(
    f"위 지표는 {display_date} 일별 박스오피스의 1위 영화 기준입니다."
)

st.divider()


# --------------------------------------------------
# 9. 전체 박스오피스 순위표
# --------------------------------------------------

st.subheader(f"🥇 어제의 1위 영화: {first_movie['movieNm']}")

# 요청한 여섯 항목을 보기 쉬운 한국어 열 이름으로 바꾼다.
table = df[
    ["rank", "movieNm", "openDt", "audiCnt", "audiAcc", "scrnCnt"]
].copy()

table.columns = [
    "순위",
    "영화명",
    "개봉일",
    "관객수",
    "누적관객",
    "스크린수",
]

# 날짜와 숫자를 읽기 편하게 표시한다.
table["개봉일"] = table["개봉일"].replace("", "정보 없음")
for col in ["관객수", "누적관객", "스크린수"]:
    table[col] = table[col].map(lambda x: f"{int(x):,}")

table["순위"] = table["순위"].map(lambda x: f"{int(x)}위")

st.dataframe(
    table,
    hide_index=True,
    use_container_width=True,
)


# --------------------------------------------------
# 10. 관객수 상위 5편 막대그래프
# --------------------------------------------------

st.subheader("📊 관객수 상위 5편")

top5 = (
    df.sort_values("audiCnt", ascending=False)
    .head(5)
    .copy()
)

# 영화명이 긴 경우에도 그래프에서 알아보기 쉽도록 가로 막대그래프를 사용한다.
fig = px.bar(
    top5.sort_values("audiCnt", ascending=True),
    x="audiCnt",
    y="movieNm",
    orientation="h",
    text="audiCnt",
    labels={
        "audiCnt": "어제 관객수(명)",
        "movieNm": "영화명",
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
    xaxis_title="어제 관객수(명)",
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
st.caption(
    f"조회 기준일: {target_dt} · "
    "데이터 집계 상황에 따라 결과가 달라질 수 있습니다."
)
