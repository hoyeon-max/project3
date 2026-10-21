
# main.py
# 어제의 박스오피스 — KOBIS Open API
# Streamlit Cloud 배포용

import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import requests
import streamlit as st


# 1. 기본 화면 설정
st.set_page_config(
    page_title="어제의 박스오피스",
    page_icon="🎬",
    layout="wide",
)

API_URL = (
    "https://www.kobis.or.kr/kobisopenapi/webservice/rest/"
    "boxoffice/searchDailyBoxOfficeList.json"
)

# 한국 시간 기준으로 어제 날짜 계산
KST = ZoneInfo("Asia/Seoul")
yesterday = datetime.datetime.now(KST).date() - datetime.timedelta(days=1)
target_dt = yesterday.strftime("%Y%m%d")
display_date = yesterday.strftime("%Y년 %m월 %d일")


def format_number(value):
    """숫자를 천 단위 쉼표와 함께 표시한다."""
    return f"{int(value):,}"


# 2. 제목
st.title("🎬 어제의 박스오피스")
st.caption(f"📅 조회 날짜: {display_date} · 한국 시간 기준")
st.divider()


# 3. 비밀 금고에서 인증키 불러오기
try:
    api_key = st.secrets["KOBIS_KEY"]
except (KeyError, FileNotFoundError, RuntimeError):
    st.error("🔑 KOBIS 인증키를 찾을 수 없습니다.")
    st.markdown(
        """
        **확인 방법**
        1. Streamlit Cloud에서 앱의 Settings → Secrets로 이동합니다.
        2. 다음 형식으로 발급받은 인증키를 등록합니다.
        3. 저장한 뒤 앱을 다시 실행합니다.
        """
    )
    st.code('KOBIS_KEY = "발급받은_인증키"', language="toml")
    st.stop()

if not str(api_key).strip():
    st.error("🔑 KOBIS_KEY 값이 비어 있습니다.")
    st.info("Secrets에 유효한 인증키를 등록해 주세요.")
    st.stop()


# 4. API 요청
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_boxoffice(date_str):
    """KOBIS에서 해당 날짜의 일별 박스오피스를 가져온다."""
    key = st.secrets["KOBIS_KEY"]

    response = requests.get(
        API_URL,
        params={"key": key, "targetDt": date_str},
        timeout=20,
    )
    response.raise_for_status()

    try:
        data = response.json()
    except ValueError as exc:
        raise ValueError("JSON 응답을 읽을 수 없습니다.") from exc

    if not isinstance(data, dict):
        raise ValueError("API 응답 형식이 올바르지 않습니다.")

    return data


try:
    with st.spinner("어제의 영화 순위를 불러오는 중입니다..."):
        data = fetch_boxoffice(target_dt)

except requests.exceptions.Timeout:
    st.error("⏱️ KOBIS 서버의 응답 시간이 초과되었습니다.")
    st.info("잠시 기다렸다가 다시 시도해 주세요.")
    st.stop()

except requests.exceptions.HTTPError as exc:
    st.error("🌐 KOBIS 서버에서 HTTP 오류가 발생했습니다.")
    st.caption(f"응답 상태 코드: {exc.response.status_code}")
    st.info("API 주소와 서버 상태를 확인해 주세요.")
    st.stop()

except requests.exceptions.RequestException:
    st.error("🌐 KOBIS 서버에 연결하지 못했습니다.")
    st.info("인터넷 연결과 KOBIS 서버 상태를 확인해 주세요.")
    st.stop()

except (ValueError, KeyError, RuntimeError):
    st.error("⚠️ 데이터를 불러오거나 해석하지 못했습니다.")
    st.info("Secrets의 KOBIS_KEY와 API 응답을 확인해 주세요.")
    st.stop()


# 5. 인증키 오류 등 API 자체 오류 확인
# HTTP 상태 코드가 200이어도 faultInfo가 있을 수 있다.
if "faultInfo" in data:
    fault = data.get("faultInfo") or {}

    if isinstance(fault, dict):
        error_code = fault.get("errorCode", "정보 없음")
        error_message = fault.get("message", "상세 메시지 없음")
    else:
        error_code = "정보 없음"
        error_message = str(fault)

    st.error("🚨 KOBIS API가 오류를 반환했습니다.")
    st.write(f"**오류 코드:** {error_code}")
    st.write(f"**오류 메시지:** {error_message}")
    st.info("인증키가 정확한지, 발급 및 사용 상태가 정상인지 확인해 주세요.")
    st.stop()


# 6. 영화 목록 확인
boxoffice_result = data.get("boxOfficeResult")

if not isinstance(boxoffice_result, dict):
    st.error("⚠️ API 응답에 박스오피스 결과가 없습니다.")
    st.info("API 주소와 응답 구조를 확인한 뒤 다시 시도해 주세요.")
    st.stop()

movies = boxoffice_result.get("dailyBoxOfficeList", [])

if not isinstance(movies, list) or not movies:
    st.warning(f"📭 {display_date}의 영화 목록이 비어 있습니다.")
    st.markdown(
        """
        **다음 항목을 확인해 주세요.**
        - 해당 날짜의 박스오피스 집계가 완료되었는지 확인합니다.
        - KOBIS에서 해당 날짜의 자료를 제공하는지 확인합니다.
        - 잠시 후 앱을 새로고침해 다시 조회합니다.
        """
    )
    st.stop()


# 7. 데이터 정리
df = pd.DataFrame(movies)

required_columns = [
    "rank", "movieNm", "openDt", "audiCnt", "audiAcc", "scrnCnt"
]
missing_columns = [col for col in required_columns if col not in df.columns]

if missing_columns:
    st.error("⚠️ API 응답에 필요한 항목이 없습니다.")
    st.write("누락된 항목:", ", ".join(missing_columns))
    st.info("KOBIS API 응답 구조를 확인해 주세요.")
    st.stop()

# API 숫자 데이터는 문자열이므로 숫자로 변환
try:
    for col in ["rank", "audiCnt", "audiAcc", "scrnCnt"]:
        df[col] = pd.to_numeric(df[col], errors="raise")
except (ValueError, TypeError):
    st.error("⚠️ 순위 또는 관객수 데이터를 숫자로 변환하지 못했습니다.")
    st.info("KOBIS API 응답의 숫자 항목을 확인해 주세요.")
    st.stop()

df["movieNm"] = df["movieNm"].fillna("영화명 정보 없음").astype(str)
df["openDt"] = df["openDt"].fillna("").astype(str)
df = df.sort_values("rank").reset_index(drop=True)


# 8. 1위 영화 지표 카드 3개
first_movie = df.iloc[0]

# 수정: '오늘의 1위 영화'가 아니라 '어제의 1위 영화'로 표시
st.subheader(f"🥇 어제의 1위 영화: {first_movie['movieNm']}")

card1, card2, card3 = st.columns(3)

with card1:
    st.metric(
        "🎟️ 어제 관객수",
        f"{format_number(first_movie['audiCnt'])}명",
    )

with card2:
    st.metric(
        "👥 누적 관객수",
        f"{format_number(first_movie['audiAcc'])}명",
    )

with card3:
    st.metric(
        "🖥️ 스크린수",
        f"{format_number(first_movie['scrnCnt'])}개",
    )

st.caption(f"기준일: {display_date}")
st.divider()


# 9. 전체 영화 순위표
st.subheader("📋 어제의 영화 순위")

table = df[
    ["rank", "movieNm", "openDt", "audiCnt", "audiAcc", "scrnCnt"]
].copy()

table.columns = [
    "순위", "영화명", "개봉일", "관객수", "누적관객", "스크린수"
]

table["순위"] = table["순위"].map(lambda x: f"{int(x)}위")
table["개봉일"] = table["개봉일"].replace("", "정보 없음")

for col in ["관객수", "누적관객", "스크린수"]:
    table[col] = table[col].map(lambda x: f"{int(x):,}")

st.dataframe(
    table,
    hide_index=True,
    use_container_width=True,
)


# 10. 관객수 상위 5편 막대그래프
st.subheader("📊 관객수 상위 5편")

top5 = df.nlargest(5, "audiCnt").copy()
top5 = top5.sort_values("audiCnt", ascending=True)

fig = px.bar(
    top5,
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


# 11. 데이터 출처
st.divider()
st.caption("데이터 출처: 영화진흥위원회(KOBIS) 일별 박스오피스 Open API")
st.caption(f"조회 기준일: {target_dt}")
st.caption("데이터 집계 상황에 따라 결과가 달라질 수 있습니다.")
