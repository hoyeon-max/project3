
import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import quote_plus

# --------------------------------------------------
# 기본 설정: 반드시 다른 Streamlit 명령보다 먼저 실행
# --------------------------------------------------
st.set_page_config(
    page_title="어제의 박스오피스",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

KST = ZoneInfo("Asia/Seoul")
TODAY_KST = datetime.now(KST).date()
YESTERDAY = TODAY_KST - timedelta(days=1)

BASE_URL = "https://www.kobis.or.kr/kobisopenapi/webservice/rest"


# --------------------------------------------------
# 화면 스타일
# --------------------------------------------------
st.markdown(
    """
    <style>
    .stApp {
        background:
            radial-gradient(ellipse at 15% 0%, #243d68 0%, transparent 42%),
            linear-gradient(135deg, #071326 0%, #101e38 55%, #080f20 100%);
        color: #f4f7ff;
    }

    .block-container {
        max-width: 1400px;
        padding-top: 2rem;
        padding-bottom: 3rem;
    }

    h1, h2, h3, p, label {
        color: #f4f7ff;
    }

    div[data-testid="stMetric"] {
        background: rgba(20, 39, 69, 0.78);
        border: 1px solid rgba(160, 190, 240, 0.18);
        border-radius: 16px;
        padding: 18px;
    }

    div[data-testid="stMetricLabel"] {
        color: #bac9e6;
    }

    div[data-testid="stMetricValue"] {
        color: #ffffff;
    }

    div.stButton > button,
    div.stLinkButton > a {
        background: rgba(39, 64, 103, 0.85);
        color: #ffffff;
        border: 1px solid rgba(160, 190, 240, 0.28);
        border-radius: 10px;
        min-height: 42px;
    }

    div.stButton > button:hover,
    div.stLinkButton > a:hover {
        border-color: #86baff;
        color: #ffffff;
    }

    div[data-testid="stDataFrame"] {
        border: 1px solid rgba(160, 190, 240, 0.2);
        border-radius: 12px;
        overflow: hidden;
    }

    .subtle {
        color: #aebfdd;
        font-size: 0.9rem;
    }

    [data-testid="stAlert"] {
        border-radius: 12px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------
# API 설정 및 공통 요청
# --------------------------------------------------
def get_api_key():
    try:
        key = st.secrets.get("KOBIS_KEY", "")
    except Exception:
        key = ""

    return str(key).strip() if key else ""


API_KEY = get_api_key()


def api_get(endpoint, params, timeout=20):
    """KOBIS JSON API를 안전하게 호출한다."""
    if not API_KEY:
        raise RuntimeError(
            "API 키를 찾을 수 없습니다. "
            "Streamlit Cloud의 Settings → Secrets에 "
            'KOBIS_KEY = "발급받은 API 키"를 설정해 주세요.'
        )

    request_params = dict(params)
    request_params["key"] = API_KEY

    url = f"{BASE_URL}/{endpoint}.json"

    try:
        response = requests.get(
            url,
            params=request_params,
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(
            "KOBIS 서버에 연결하지 못했습니다. "
            "인터넷 연결이나 KOBIS 서버 상태를 확인해 주세요."
        ) from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(
            "KOBIS 응답을 JSON으로 읽을 수 없습니다. "
            "API 키와 KOBIS 응답을 확인해 주세요."
        ) from exc

    if not isinstance(data, dict):
        raise RuntimeError("KOBIS에서 예상하지 못한 응답을 받았습니다.")

    if "faultInfo" in data:
        fault = data.get("faultInfo", {})
        message = fault.get("message", "KOBIS API 오류")
        raise RuntimeError(f"KOBIS API 오류: {message}")

    return data


def safe_int(value):
    try:
        return int(value or 0)
    except (ValueError, TypeError):
        return 0


def format_number(value):
    return f"{safe_int(value):,}"


# --------------------------------------------------
# 일별 박스오피스
# --------------------------------------------------
@st.cache_data(ttl=900, show_spinner=False)
def fetch_daily_boxoffice(target_date):
    data = api_get(
        "boxoffice/searchDailyBoxOfficeList",
        {"targetDt": target_date.strftime("%Y%m%d")},
    )

    boxoffice = data.get("boxOfficeResult", {})
    movies = boxoffice.get("dailyBoxOfficeList", [])

    if not isinstance(movies, list):
        return []

    return movies


# --------------------------------------------------
# 영화 상세 정보
# --------------------------------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_movie_info(movie_code):
    data = api_get(
        "movie/searchMovieInfo",
        {"movieCd": str(movie_code)},
    )
    return data.get("movieInfoResult", {}).get("movieInfo", {})


# --------------------------------------------------
# 주간 박스오피스
# --------------------------------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_weekly_boxoffice(target_date):
    data = api_get(
        "boxoffice/searchWeeklyBoxOfficeList",
        {
            "targetDt": target_date.strftime("%Y%m%d"),
            "weekGb": "0",
        },
    )

    boxoffice = data.get("boxOfficeResult", {})
    movies = boxoffice.get("weeklyBoxOfficeList", [])

    if not isinstance(movies, list):
        return []

    return movies


# --------------------------------------------------
# 관객 추이 데이터
# --------------------------------------------------
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_daily_history(movie_code, end_date, release_date_text):
    """최근 60일간 일별 TOP 10에서 해당 영화의 관객 수를 찾는다."""
    try:
        release_date = datetime.strptime(
            release_date_text, "%Y%m%d"
        ).date()
    except (ValueError, TypeError):
        release_date = end_date - timedelta(days=59)

    start_date = max(
        end_date - timedelta(days=59),
        release_date,
    )

    rows = []
    current = start_date

    while current <= end_date:
        try:
            movies = fetch_daily_boxoffice(current)
            found = next(
                (
                    item for item in movies
                    if str(item.get("movieCd", "")) == str(movie_code)
                ),
                None,
            )

            # TOP 10에 없는 날은 0으로 단정하지 않는다.
            if found:
                rows.append({
                    "날짜": current,
                    "관객 수": safe_int(found.get("audiCnt")),
                })
        except Exception:
            # 일부 날짜의 API 오류가 전체 화면을 중단시키지 않게 한다.
            pass

        current += timedelta(days=1)

    return pd.DataFrame(rows, columns=["날짜", "관객 수"])


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_weekly_history(movie_code, end_date, release_date_text):
    """주간 TOP 10에서 확인 가능한 영화 관객 수를 모은다."""
    try:
        release_date = datetime.strptime(
            release_date_text, "%Y%m%d"
        ).date()
    except (ValueError, TypeError):
        release_date = end_date - timedelta(days=365)

    rows = []
    current = end_date
    seen_dates = set()

    # 최대 약 2년 범위에서 주간 데이터를 확인한다.
    for _ in range(105):
        if current < release_date:
            break

        try:
            movies = fetch_weekly_boxoffice(current)
            found = next(
                (
                    item for item in movies
                    if str(item.get("movieCd", "")) == str(movie_code)
                ),
                None,
            )

            if found:
                week_key = (
                    found.get("showRange")
                    or found.get("targetDt")
                    or current.strftime("%Y%m%d")
                )

                if week_key not in seen_dates:
                    seen_dates.add(week_key)
                    rows.append({
                        "기간": str(week_key),
                        "관객 수": safe_int(found.get("audiCnt")),
                        "정렬 날짜": current,
                    })
        except Exception:
            pass

        current -= timedelta(days=7)

    if not rows:
        return pd.DataFrame(columns=["기간", "관객 수", "정렬 날짜"])

    return (
        pd.DataFrame(rows)
        .sort_values("정렬 날짜")
        .reset_index(drop=True)
    )


def make_monthly_history(weekly_df):
    """확인 가능한 주간 TOP 10 데이터만 월별로 합산한다."""
    if weekly_df.empty:
        return pd.DataFrame(columns=["기간", "관객 수"])

    df = weekly_df.copy()
    df["월"] = pd.to_datetime(df["정렬 날짜"]).dt.to_period("M").astype(str)

    result = (
        df.groupby("월", as_index=False)["관객 수"]
        .sum()
        .rename(columns={"월": "기간"})
    )

    return result


def make_naver_links(movie_name):
    encoded = quote_plus(movie_name)
    poster_url = (
        "https://search.naver.com/search.naver"
        f"?where=image&query={encoded}+포스터"
    )
    synopsis_url = (
        "https://search.naver.com/search.naver"
        f"?query={encoded}+줄거리+시놉시스"
    )
    return poster_url, synopsis_url


# --------------------------------------------------
# 상세 화면
# --------------------------------------------------
def show_movie_detail(movie, selected_date):
    movie_name = str(movie.get("movieNm", "영화 정보"))
    movie_code = str(movie.get("movieCd", ""))
    release_date_text = str(movie.get("openDt", ""))

    if st.button("← 박스오피스 목록으로 돌아가기", key="back_to_list"):
        st.session_state["page"] = "list"
        st.rerun()

    st.title(f"🎬 {movie_name}")
    st.caption(f"조회 기준일: {selected_date.strftime('%Y-%m-%d')}")

    poster_url, synopsis_url = make_naver_links(movie_name)

    left, right = st.columns([1.15, 1])

    with left:
        st.subheader("📈 관객 추이")

        period = st.radio(
            "그래프 기간",
            ["일간", "주간", "월간"],
            horizontal=True,
            key="detail_graph_period",
        )

        try:
            if period == "일간":
                with st.spinner("일별 관객 데이터를 불러오는 중..."):
                    history = fetch_daily_history(
                        movie_code, selected_date, release_date_text
                    )

                if history.empty:
                    st.info(
                        "최근 60일의 일별 TOP 10 자료에서 "
                        "이 영화의 관객 추이를 찾지 못했습니다."
                    )
                else:
                    fig = px.line(
                        history,
                        x="날짜",
                        y="관객 수",
                        markers=True,
                        title="일별 관객 수 (최근 60일)",
                    )
                    fig.update_traces(line=dict(width=3, color="#80bfff"))
                    fig.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        font_color="#f4f7ff",
                        margin=dict(l=10, r=10, t=55, b=10),
                        xaxis_title="날짜",
                        yaxis_title="관객 수",
                    )
                    st.plotly_chart(fig, use_container_width=True)

            else:
                with st.spinner("주간 관객 데이터를 불러오는 중..."):
                    weekly = fetch_weekly_history(
                        movie_code, selected_date, release_date_text
                    )

                if period == "주간":
                    if weekly.empty:
                        st.info(
                            "주간 TOP 10 자료에서 이 영화의 관객 추이를 "
                            "찾지 못했습니다."
                        )
                    else:
                        fig = px.line(
                            weekly,
                            x="정렬 날짜",
                            y="관객 수",
                            markers=True,
                            title="주간 관객 수",
                        )
                        fig.update_traces(
                            line=dict(width=3, color="#80bfff")
                        )
                        fig.update_layout(
                            paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="rgba(0,0,0,0)",
                            font_color="#f4f7ff",
                            margin=dict(l=10, r=10, t=55, b=10),
                            xaxis_title="주간 기준일",
                            yaxis_title="관객 수",
                        )
                        st.plotly_chart(fig, use_container_width=True)

                else:
                    monthly = make_monthly_history(weekly)

                    if monthly.empty:
                        st.info("월별로 표시할 관객 데이터가 없습니다.")
                    else:
                        fig = px.line(
                            monthly,
                            x="기간",
                            y="관객 수",
                            markers=True,
                            title="월별 관객 수 (확인 가능한 주간 자료 합산)",
                        )
                        fig.update_traces(
                            line=dict(width=3, color="#80bfff")
                        )
                        fig.update_layout(
                            paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="rgba(0,0,0,0)",
                            font_color="#f4f7ff",
                            margin=dict(l=10, r=10, t=55, b=10),
                            xaxis_title="월",
                            yaxis_title="관객 수",
                        )
                        st.plotly_chart(fig, use_container_width=True)
                        st.caption(
                            "월별 수치는 공식 월간 박스오피스가 아니라 "
                            "조회 가능한 주간 TOP 10 자료를 합산한 참고값입니다."
                        )

        except Exception as exc:
            st.warning(f"그래프를 불러오지 못했습니다: {exc}")

    with right:
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

        # 목록에서 선택했을 당시의 정보가 있으면 우선 사용
        st.metric(
            "선택 날짜 관객 수",
            f"{format_number(movie.get('audiCnt'))}명",
        )
        st.metric(
            "누적 관객 수",
            f"{format_number(movie.get('audiAcc'))}명",
        )
        st.metric(
            "스크린 수",
            f"{format_number(movie.get('scrnCnt'))}개",
        )

        try:
            with st.spinner("영화 상세 정보를 확인하는 중..."):
                info = fetch_movie_info(movie_code)

            if info:
                st.markdown("#### 기본 정보")

                if info.get("movieNm"):
                    st.write(f"**영화명:** {info['movieNm']}")

                if info.get("movieNmEn"):
                    st.write(f"**영문명:** {info['movieNmEn']}")

                if info.get("showTm"):
                    st.write(f"**상영 시간:** {info['showTm']}분")

                if info.get("openDt"):
                    st.write(f"**개봉일:** {info['openDt']}")

                genres = info.get("genres", [])
                genre_names = [
                    item.get("genreNm", "")
                    for item in genres
                    if item.get("genreNm")
                ]
                if genre_names:
                    st.write(f"**장르:** {', '.join(genre_names)}")

                directors = info.get("directors", [])
                director_names = [
                    item.get("peopleNm", "")
                    for item in directors
                    if item.get("peopleNm")
                ]
                if director_names:
                    st.write(f"**감독:** {', '.join(director_names)}")

                actors = info.get("actors", [])
                actor_names = [
                    item.get("peopleNm", "")
                    for item in actors[:5]
                    if item.get("peopleNm")
                ]
                if actor_names:
                    st.write(f"**출연:** {', '.join(actor_names)}")
            else:
                st.caption("KOBIS에서 추가 영화 정보를 제공하지 않았습니다.")

        except Exception as exc:
            st.caption(f"추가 영화 정보를 불러오지 못했습니다: {exc}")


# --------------------------------------------------
# 목록 화면
# --------------------------------------------------
def show_boxoffice_list():
    st.title("🎬 어제의 박스오피스")
    st.caption("영화진흥위원회(KOBIS) 공식 박스오피스 자료")

    selected_date = st.date_input(
        "조회 날짜",
        value=YESTERDAY,
        min_value=date(2004, 11, 11),
        max_value=YESTERDAY,
        help="오늘 자료는 아직 집계되지 않을 수 있어 어제까지만 선택할 수 있습니다.",
    )

    if selected_date > YESTERDAY:
        st.warning("조회 날짜는 어제까지만 선택할 수 있습니다.")
        return

    try:
        with st.spinner("박스오피스 데이터를 불러오는 중..."):
            movies = fetch_daily_boxoffice(selected_date)

    except Exception as exc:
        st.error("박스오피스 데이터를 불러오지 못했습니다.")
        st.warning(str(exc))
        st.markdown(
            """
            **확인할 사항**
            - Streamlit Cloud의 `Settings → Secrets`에 `KOBIS_KEY`가 있는지 확인
            - API 키가 정확한지 확인
            - `requirements.txt`의 패키지가 정상 설치됐는지 확인
            """
        )
        return

    if not movies:
        st.info("그날은 아직 집계 전입니다")
        return

    # 1위 영화 요약
    first = movies[0]
    metric1, metric2, metric3 = st.columns(3)

    with metric1:
        st.metric("🥇 1위 영화", first.get("movieNm", "-"))
    with metric2:
        st.metric("오늘 관객 수", f"{format_number(first.get('audiCnt'))}명")
    with metric3:
        st.metric("누적 관객 수", f"{format_number(first.get('audiAcc'))}명")

    st.markdown("---")
    st.subheader("🏆 순위별 박스오피스")

    # 상위 5개 영화 관객 수 그래프
    top5 = movies[:5]
    chart_df = pd.DataFrame({
        "영화명": [m.get("movieNm", "") for m in top5],
        "관객 수": [safe_int(m.get("audiCnt")) for m in top5],
    })

    fig = px.bar(
        chart_df,
        x="관객 수",
        y="영화명",
        orientation="h",
        title="관객 수 TOP 5",
        text="관객 수",
    )
    fig.update_traces(
        marker_color="#80bfff",
        texttemplate="%{text:,}",
        textposition="outside",
        cliponaxis=False,
    )
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#f4f7ff",
        yaxis=dict(autorange="reversed"),
        margin=dict(l=10, r=50, t=55, b=10),
        xaxis_title="관객 수",
        yaxis_title="",
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.subheader("📋 전체 순위")

    st.caption("순위 또는 영화명을 누르면 해당 영화의 상세 화면으로 이동합니다.")

    for index, movie in enumerate(movies):
        rank = safe_int(movie.get("rank"))
        rank_inten = safe_int(movie.get("rankInten"))
        movie_name = str(movie.get("movieNm", "이름 미상"))
        cumulative = safe_int(movie.get("audiAcc"))

        trophy = " 🏆" if cumulative > 1_000_000 else ""

        if rank_inten > 0:
            change_text = f"🔺 +{rank_inten}"
        elif rank_inten < 0:
            change_text = f"🔵 {rank_inten}"
        else:
            change_text = "➖ 0"

        with st.container(border=True):
            col_rank, col_change, col_title, col_release, col_audience, col_total, col_screen = (
                st.columns([0.55, 0.75, 2.4, 0.9, 1.05, 1.1, 0.85])
            )

            with col_rank:
                if st.button(
                    f"{rank}위",
                    key=f"rank_{selected_date}_{index}_{movie.get('movieCd')}",
                    use_container_width=True,
                ):
                    st.session_state["selected_movie_data"] = movie
                    st.session_state["selected_movie_date"] = selected_date
                    st.session_state["page"] = "detail"
                    st.rerun()

            with col_change:
                st.markdown(f"**{change_text}**")

            with col_title:
                if st.button(
                    f"{movie_name}{trophy}",
                    key=f"title_{selected_date}_{index}_{movie.get('movieCd')}",
                    use_container_width=True,
                ):
                    st.session_state["selected_movie_data"] = movie
                    st.session_state["selected_movie_date"] = selected_date
                    st.session_state["page"] = "detail"
                    st.rerun()

            with col_release:
                st.write(movie.get("openDt") or "-")

            with col_audience:
                st.write(format_number(movie.get("audiCnt")))

            with col_total:
                st.write(format_number(movie.get("audiAcc")))

            with col_screen:
                st.write(format_number(movie.get("scrnCnt")))


# --------------------------------------------------
# 앱 진입점: 상세 화면 오류가 목록 화면까지 막지 않게 처리
# --------------------------------------------------
def main():
    if "page" not in st.session_state:
        st.session_state["page"] = "list"

    if st.session_state["page"] == "detail":
        movie = st.session_state.get("selected_movie_data")
        selected_date = st.session_state.get(
            "selected_movie_date", YESTERDAY
        )

        if not movie:
            st.session_state["page"] = "list"
            st.warning("선택한 영화 정보를 찾을 수 없어 목록으로 돌아갑니다.")
            st.rerun()
            return

        try:
            show_movie_detail(movie, selected_date)
        except Exception as exc:
            st.error("영화 상세 화면을 표시하는 중 문제가 발생했습니다.")
            st.exception(exc)

            if st.button("목록으로 돌아가기", key="detail_error_back"):
                st.session_state["page"] = "list"
                st.rerun()
    else:
        show_boxoffice_list()


try:
    main()
except Exception as exc:
    st.error("앱을 표시하는 중 예상하지 못한 오류가 발생했습니다.")
    st.exception(exc)
    st.info(
        "오류 메시지를 확인해 주세요. "
        "화면 전체가 비어 있는 대신 문제의 원인을 표시하도록 처리했습니다."
    )
