
import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import quote_plus

st.set_page_config(
    page_title="어제의 박스오피스",
    page_icon="🎬",
    layout="wide",
)

KST = ZoneInfo("Asia/Seoul")
TODAY = datetime.now(KST).date()
YESTERDAY = TODAY - timedelta(days=1)
BASE_URL = "https://www.kobis.or.kr/kobisopenapi/webservice/rest"

# --------------------------------------------------
# 스타일: 투명도는 배경 필름 장식에만 적용
# --------------------------------------------------
st.markdown("""
<style>
.stApp {
    background: linear-gradient(135deg, #081326, #132747 55%, #081326);
    color: #f5f8ff;
}

/* 투명한 필름 장식만 배경에 표시 */
.stApp::before {
    content: "";
    position: fixed;
    z-index: 0;
    pointer-events: none;
    top: 13%;
    left: -7%;
    width: 115%;
    height: 135px;
    opacity: 0.075;
    border-top: 15px dashed #d8e7ff;
    border-bottom: 15px dashed #d8e7ff;
    border-radius: 50%;
    transform: rotate(-9deg);
}

/* 실제 콘텐츠는 장식 위에 배치 */
.stApp > header,
.stApp [data-testid="stAppViewContainer"],
.stApp [data-testid="stHeader"],
.stApp .block-container {
    position: relative;
    z-index: 1;
}

.block-container {
    max-width: 1450px;
    padding-top: 2rem;
    padding-bottom: 3rem;
}

h1, h2, h3, p, label,
[data-testid="stMarkdownContainer"] {
    color: #f5f8ff;
}

/* 불투명한 카드 */
[data-testid="stMetric"],
[data-testid="stVerticalBlockBorderWrapper"] {
    background-color: #172b49 !important;
    border: 1px solid #354b6c !important;
    border-radius: 14px !important;
}

[data-testid="stMetric"] {
    padding: 16px;
}

[data-testid="stMetricLabel"] {
    color: #c7d5eb !important;
}

[data-testid="stMetricValue"] {
    color: #ffffff !important;
}

/* 버튼은 선명한 단색 */
.stButton > button,
.stLinkButton > a {
    background-color: #24466f !important;
    color: #ffffff !important;
    border: 1px solid #5478a6 !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    min-height: 42px;
    opacity: 1 !important;
}

.stButton > button:hover,
.stLinkButton > a:hover {
    background-color: #326092 !important;
    border-color: #9bcaff !important;
    color: #ffffff !important;
}

/* 입력 컨트롤도 불투명하게 */
div[data-baseweb="select"] > div,
div[data-baseweb="input"] > div {
    background-color: #172b49 !important;
    color: #ffffff !important;
    border-color: #526987 !important;
}

div[data-testid="stDataFrame"] {
    background-color: #172b49 !important;
    border-radius: 12px;
}

hr {
    border-color: #354b6c;
}
</style>
""", unsafe_allow_html=True)


# --------------------------------------------------
# KOBIS API
# --------------------------------------------------
def get_api_key():
    try:
        return str(st.secrets.get("KOBIS_KEY", "")).strip()
    except Exception:
        return ""


def api_get(endpoint, params):
    key = get_api_key()
    if not key:
        raise RuntimeError(
            'API 키가 없습니다. Streamlit Cloud Secrets에 '
            'KOBIS_KEY = "발급받은_API_키"를 등록해 주세요.'
        )

    url = f"{BASE_URL}/{endpoint}.json"
    request_params = dict(params)
    request_params["key"] = key

    try:
        response = requests.get(url, params=request_params, timeout=15)
        response.raise_for_status()
        data = response.json()
    except requests.Timeout as exc:
        raise RuntimeError("KOBIS 응답 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.") from exc
    except requests.RequestException as exc:
        raise RuntimeError("KOBIS 서버에 연결하지 못했습니다.") from exc
    except ValueError as exc:
        raise RuntimeError("KOBIS 응답을 해석할 수 없습니다. API 키를 확인해 주세요.") from exc

    if not isinstance(data, dict):
        raise RuntimeError("KOBIS에서 예상하지 못한 응답을 받았습니다.")

    if data.get("faultInfo"):
        message = data["faultInfo"].get("message", "KOBIS API 오류")
        raise RuntimeError(message)

    return data


def number(value):
    try:
        return f"{int(value or 0):,}"
    except (ValueError, TypeError):
        return "0"


def int_value(value):
    try:
        return int(value or 0)
    except (ValueError, TypeError):
        return 0


# --------------------------------------------------
# 데이터 조회: 반복 호출 결과는 캐시
# --------------------------------------------------
@st.cache_data(ttl=900, show_spinner=False)
def get_daily_boxoffice(date_text):
    target = datetime.strptime(date_text, "%Y-%m-%d").date()
    result = api_get(
        "boxoffice/searchDailyBoxOfficeList",
        {"targetDt": target.strftime("%Y%m%d")},
    )
    return result.get("boxOfficeResult", {}).get("dailyBoxOfficeList", [])


@st.cache_data(ttl=3600, show_spinner=False)
def get_weekly_boxoffice(date_text):
    target = datetime.strptime(date_text, "%Y-%m-%d").date()
    result = api_get(
        "boxoffice/searchWeeklyBoxOfficeList",
        {"targetDt": target.strftime("%Y%m%d"), "weekGb": "0"},
    )
    return result.get("boxOfficeResult", {}).get("weeklyBoxOfficeList", [])


@st.cache_data(ttl=3600, show_spinner=False)
def get_movie_info(movie_code):
    result = api_get("movie/searchMovieInfo", {"movieCd": str(movie_code)})
    return result.get("movieInfoResult", {}).get("movieInfo", {})


@st.cache_data(ttl=1800, show_spinner=False)
def get_daily_history(movie_code, end_text, release_text):
    end_date = datetime.strptime(end_text, "%Y-%m-%d").date()

    try:
        release_date = datetime.strptime(release_text, "%Y%m%d").date()
    except (ValueError, TypeError):
        release_date = end_date - timedelta(days=29)

    start_date = max(end_date - timedelta(days=29), release_date)
    rows = []
    current = start_date

    # 최근 30일로 제한해 로딩 속도 개선
    while current <= end_date:
        try:
            movies = get_daily_boxoffice(current.isoformat())
            movie = next(
                (m for m in movies if str(m.get("movieCd")) == str(movie_code)),
                None,
            )
            if movie:
                rows.append({
                    "날짜": current,
                    "관객 수": int_value(movie.get("audiCnt")),
                })
        except Exception:
            pass
        current += timedelta(days=1)

    return pd.DataFrame(rows, columns=["날짜", "관객 수"])


@st.cache_data(ttl=3600, show_spinner=False)
def get_weekly_history(movie_code, end_text, release_text):
    end_date = datetime.strptime(end_text, "%Y-%m-%d").date()

    try:
        release_date = datetime.strptime(release_text, "%Y%m%d").date()
    except (ValueError, TypeError):
        release_date = end_date - timedelta(days=365)

    rows = []
    current = end_date

    # 최대 52주까지만 조회
    for _ in range(52):
        if current < release_date:
            break

        try:
            movies = get_weekly_boxoffice(current.isoformat())
            movie = next(
                (m for m in movies if str(m.get("movieCd")) == str(movie_code)),
                None,
            )
            if movie:
                rows.append({
                    "날짜": current,
                    "관객 수": int_value(movie.get("audiCnt")),
                    "기간": movie.get("showRange", current.strftime("%Y%m%d")),
                })
        except Exception:
            pass

        current -= timedelta(days=7)

    if not rows:
        return pd.DataFrame(columns=["날짜", "관객 수", "기간"])

    return pd.DataFrame(rows).sort_values("날짜").reset_index(drop=True)


def naver_links(movie_name):
    name = quote_plus(movie_name)
    poster = (
        "https://search.naver.com/search.naver"
        f"?where=image&query={name}+포스터"
    )
    synopsis = (
        "https://search.naver.com/search.naver"
        f"?query={name}+줄거리+시놉시스"
    )
    return poster, synopsis


# --------------------------------------------------
# 공통 그래프 스타일
# --------------------------------------------------
def draw_line_chart(df, x, title):
    fig = px.line(
        df,
        x=x,
        y="관객 수",
        markers=True,
        title=title,
    )
    fig.update_traces(line=dict(color="#80bfff", width=3))
    fig.update_layout(
        paper_bgcolor="#172b49",
        plot_bgcolor="#172b49",
        font_color="#ffffff",
        title_font_color="#ffffff",
        margin=dict(l=10, r=15, t=55, b=10),
        xaxis_title="기간",
        yaxis_title="관객 수",
    )
    st.plotly_chart(fig, use_container_width=True)


# --------------------------------------------------
# 영화 상세 화면
# --------------------------------------------------
def show_detail(movie, selected_date):
    movie_name = str(movie.get("movieNm", "영화 정보"))
    movie_code = str(movie.get("movieCd", ""))
    release_text = str(movie.get("openDt", ""))

    if st.button("← 박스오피스 목록으로 돌아가기", key="back_list"):
        st.session_state["page"] = "list"
        st.rerun()

    st.title(f"🎬 {movie_name}")
    st.caption(f"조회 기준일: {selected_date.strftime('%Y-%m-%d')}")

    poster_url, synopsis_url = naver_links(movie_name)

    # 상세 페이지 안에서 영화 정보와 해당 영화 링크를 함께 표시
    info_col, graph_col = st.columns([0.9, 1.25], gap="large")

    with info_col:
        with st.container(border=True):
            st.subheader("🎞️ 영화 정보")

            st.link_button(
                "🖼️ 네이버에서 포스터 찾기",
                poster_url,
                use_container_width=True,
            )
            st.link_button(
                "📖 네이버에서 시놉시스 찾기",
                synopsis_url,
                use_container_width=True,
            )

            st.markdown("---")
            st.metric("조회일 관객 수", f"{number(movie.get('audiCnt'))}명")
            st.metric("누적 관객 수", f"{number(movie.get('audiAcc'))}명")
            st.metric("스크린 수", f"{number(movie.get('scrnCnt'))}개")

            try:
                info = get_movie_info(movie_code)
                if info:
                    st.markdown("#### 기본 정보")

                    if info.get("movieNmEn"):
                        st.write(f"**영문명:** {info['movieNmEn']}")
                    if info.get("openDt"):
                        st.write(f"**개봉일:** {info['openDt']}")
                    if info.get("showTm"):
                        st.write(f"**상영 시간:** {info['showTm']}분")

                    genres = [
                        g.get("genreNm", "")
                        for g in info.get("genres", [])
                        if g.get("genreNm")
                    ]
                    if genres:
                        st.write(f"**장르:** {', '.join(genres)}")

                    directors = [
                        d.get("peopleNm", "")
                        for d in info.get("directors", [])
                        if d.get("peopleNm")
                    ]
                    if directors:
                        st.write(f"**감독:** {', '.join(directors)}")

                    actors = [
                        a.get("peopleNm", "")
                        for a in info.get("actors", [])[:5]
                        if a.get("peopleNm")
                    ]
                    if actors:
                        st.write(f"**출연:** {', '.join(actors)}")
            except Exception as exc:
                st.warning(f"추가 영화 정보를 불러오지 못했습니다: {exc}")

    with graph_col:
        with st.container(border=True):
            st.subheader("📈 관객 추이")

            period = st.radio(
                "그래프 기간 선택",
                ["일간", "주간", "월간"],
                horizontal=True,
                key="detail_period",
            )

            end_text = selected_date.isoformat()

            try:
                if period == "일간":
                    with st.spinner("최근 30일 자료를 불러오는 중..."):
                        df = get_daily_history(
                            movie_code, end_text, release_text
                        )

                    if df.empty:
                        st.info("최근 30일의 일별 TOP 10 자료에서 관객 추이를 찾지 못했습니다.")
                    else:
                        draw_line_chart(df, "날짜", "최근 30일 일별 관객 수")

                else:
                    with st.spinner("주간 자료를 불러오는 중..."):
                        weekly = get_weekly_history(
                            movie_code, end_text, release_text
                        )

                    if period == "주간":
                        if weekly.empty:
                            st.info("주간 TOP 10 자료에서 관객 추이를 찾지 못했습니다.")
                        else:
                            draw_line_chart(weekly, "날짜", "주간 관객 수")
                    else:
                        if weekly.empty:
                            st.info("월별 그래프를 만들 자료가 없습니다.")
                        else:
                            monthly = weekly.copy()
                            monthly["월"] = pd.to_datetime(
                                monthly["날짜"]
                            ).dt.to_period("M").astype(str)
                            monthly = (
                                monthly.groupby("월", as_index=False)["관객 수"]
                                .sum()
                                .rename(columns={"월": "기간"})
                            )
                            draw_line_chart(monthly, "기간", "월별 관객 수")
                            st.caption(
                                "월별 수치는 공식 월간 자료가 아니라 "
                                "조회 가능한 주간 TOP 10 관객 수를 합산한 참고값입니다."
                            )

            except Exception as exc:
                st.warning(f"그래프를 불러오지 못했습니다: {exc}")

            st.caption(
                "KOBIS 일별·주별 자료는 TOP 10까지만 제공되므로 "
                "순위 밖 기간의 관객 수는 그래프에 포함되지 않을 수 있습니다."
            )


# --------------------------------------------------
# 박스오피스 목록 화면
# --------------------------------------------------
def show_list():
    st.title("🎬 어제의 박스오피스")
    st.caption("영화진흥위원회(KOBIS) 공식 자료")

    selected_date = st.date_input(
        "조회 날짜",
        value=YESTERDAY,
        min_value=date(2004, 11, 11),
        max_value=YESTERDAY,
    )

    try:
        with st.spinner("박스오피스 데이터를 불러오는 중..."):
            movies = get_daily_boxoffice(selected_date.isoformat())
    except Exception as exc:
        st.error("박스오피스 데이터를 불러오지 못했습니다.")
        st.warning(str(exc))
        st.info(
            'Streamlit Cloud의 Settings → Secrets에서 '
            'KOBIS_KEY = "발급받은_API_키"가 설정되어 있는지 확인해 주세요.'
        )
        return

    if not movies:
        st.info("그날은 아직 집계 전입니다")
        return

    first = movies[0]
    m1, m2, m3 = st.columns(3)
    m1.metric("🥇 1위 영화", first.get("movieNm", "-"))
    m2.metric("오늘 관객 수", f"{number(first.get('audiCnt'))}명")
    m3.metric("누적 관객 수", f"{number(first.get('audiAcc'))}명")

    st.markdown("---")
    st.subheader("📊 관객 수 TOP 5")

    top5 = pd.DataFrame([
        {
            "영화명": m.get("movieNm", ""),
            "관객 수": int_value(m.get("audiCnt")),
        }
        for m in movies[:5]
    ])

    fig = px.bar(
        top5,
        x="관객 수",
        y="영화명",
        orientation="h",
        text="관객 수",
    )
    fig.update_traces(
        marker_color="#80bfff",
        texttemplate="%{text:,}",
        textposition="outside",
        cliponaxis=False,
    )
    fig.update_layout(
        paper_bgcolor="#172b49",
        plot_bgcolor="#172b49",
        font_color="#ffffff",
        yaxis=dict(autorange="reversed"),
        margin=dict(l=10, r=45, t=20, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.subheader("🏆 전체 순위")
    st.caption("순위 또는 영화명을 누르면 해당 영화의 상세 화면으로 이동합니다.")

    for i, movie in enumerate(movies):
        rank = int_value(movie.get("rank"))
        change = int_value(movie.get("rankInten"))
        title = str(movie.get("movieNm", "이름 미상"))
        trophy = " 🏆" if int_value(movie.get("audiAcc")) > 1_000_000 else ""

        if change > 0:
            change_label = f"🔺 +{change}"
        elif change < 0:
            change_label = f"🔵 {change}"
        else:
            change_label = "➖ 0"

        with st.container(border=True):
            c1, c2, c3, c4, c5, c6, c7 = st.columns(
                [0.55, 0.7, 2.3, 0.85, 1.05, 1.05, 0.8]
            )

            def select_movie():
                st.session_state["selected_movie"] = movie
                st.session_state["selected_date"] = selected_date.isoformat()
                st.session_state["page"] = "detail"

            with c1:
                st.button(
                    f"{rank}위",
                    key=f"rank_{selected_date}_{i}_{movie.get('movieCd')}",
                    on_click=select_movie,
                    use_container_width=True,
                )
            with c2:
                st.write(change_label)
            with c3:
                st.button(
                    f"{title}{trophy}",
                    key=f"title_{selected_date}_{i}_{movie.get('movieCd')}",
                    on_click=select_movie,
                    use_container_width=True,
                )
            with c4:
                st.write(movie.get("openDt") or "-")
            with c5:
                st.write(number(movie.get("audiCnt")))
            with c6:
                st.write(number(movie.get("audiAcc")))
            with c7:
                st.write(number(movie.get("scrnCnt")))


# --------------------------------------------------
# 앱 진입점
# --------------------------------------------------
def main():
    if "page" not in st.session_state:
        st.session_state["page"] = "list"

    if st.session_state["page"] == "detail":
        movie = st.session_state.get("selected_movie")
        date_text = st.session_state.get("selected_date", YESTERDAY.isoformat())

        if not movie:
            st.session_state["page"] = "list"
            st.rerun()
            return

        try:
            selected_date = datetime.strptime(date_text, "%Y-%m-%d").date()
        except ValueError:
            selected_date = YESTERDAY

        show_detail(movie, selected_date)
    else:
        show_list()


try:
    main()
except Exception as exc:
    st.error("앱 실행 중 오류가 발생했습니다.")
    st.exception(exc)
