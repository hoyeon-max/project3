
import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import quote_plus

# ==================================================
# 1. 기본 설정
# ==================================================
st.set_page_config(
    page_title="어제의 박스오피스",
    page_icon="🎬",
    layout="wide",
)

KST = ZoneInfo("Asia/Seoul")
TODAY = datetime.now(KST).date()
YESTERDAY = TODAY - timedelta(days=1)

BASE_URL = (
    "https://www.kobis.or.kr/"
    "kobisopenapi/webservice/rest"
)


# ==================================================
# 2. 화면 디자인
# 필름 장식에만 투명도 적용
# ==================================================
st.markdown("""
<style>
.stApp {
    background: linear-gradient(
        135deg,
        #081326 0%,
        #132747 55%,
        #081326 100%
    );
    color: #f5f8ff;
}

.stApp::before {
    content: "";
    position: fixed;
    z-index: 0;
    pointer-events: none;
    top: 15%;
    left: -8%;
    width: 120%;
    height: 130px;
    opacity: 0.075;
    border-top: 15px dashed #d8e7ff;
    border-bottom: 15px dashed #d8e7ff;
    border-radius: 50%;
    transform: rotate(-9deg);
}

.stApp [data-testid="stAppViewContainer"] {
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

[data-testid="stMetric"] {
    background-color: #172b49 !important;
    border: 1px solid #354b6c !important;
    border-radius: 14px !important;
    padding: 16px;
}

[data-testid="stMetricLabel"] {
    color: #c7d5eb !important;
}

[data-testid="stMetricValue"] {
    color: #ffffff !important;
}

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

div[data-baseweb="select"] > div,
div[data-baseweb="input"] > div {
    background-color: #172b49 !important;
    color: #ffffff !important;
    border-color: #526987 !important;
}

div[data-testid="stVerticalBlockBorderWrapper"] {
    background-color: #172b49 !important;
    border-color: #354b6c !important;
    border-radius: 14px !important;
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


# ==================================================
# 3. KOBIS API
# ==================================================
def get_api_key():
    try:
        return str(st.secrets.get("KOBIS_KEY", "")).strip()
    except Exception:
        return ""


def api_get(endpoint, params):
    key = get_api_key()

    if not key:
        raise RuntimeError(
            'API 키가 없습니다. Streamlit Cloud의 '
            'Settings → Secrets에 다음 항목을 설정하세요: '
            'KOBIS_KEY = "발급받은_API_키"'
        )

    request_params = dict(params)
    request_params["key"] = key

    url = f"{BASE_URL}/{endpoint}.json"

    try:
        response = requests.get(
            url,
            params=request_params,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()

    except requests.Timeout as exc:
        raise RuntimeError(
            "KOBIS 서버 응답 시간이 초과되었습니다."
        ) from exc

    except requests.RequestException as exc:
        raise RuntimeError(
            "KOBIS 서버에 연결하지 못했습니다."
        ) from exc

    except ValueError as exc:
        raise RuntimeError(
            "KOBIS 응답을 읽을 수 없습니다. API 키를 확인하세요."
        ) from exc

    if not isinstance(data, dict):
        raise RuntimeError("KOBIS 응답 형식이 올바르지 않습니다.")

    if data.get("faultInfo"):
        message = data["faultInfo"].get(
            "message",
            "KOBIS API 오류",
        )
        raise RuntimeError(message)

    return data


def int_value(value):
    try:
        return int(value or 0)
    except (ValueError, TypeError):
        return 0


def number(value):
    return f"{int_value(value):,}"


# ==================================================
# 4. 일별 박스오피스
# ==================================================
@st.cache_data(ttl=900, show_spinner=False)
def get_daily_boxoffice(date_text):
    target_date = datetime.strptime(
        date_text, "%Y-%m-%d"
    ).date()

    result = api_get(
        "boxoffice/searchDailyBoxOfficeList",
        {
            "targetDt": target_date.strftime("%Y%m%d"),
        },
    )

    movies = result.get(
        "boxOfficeResult", {}
    ).get("dailyBoxOfficeList", [])

    return movies if isinstance(movies, list) else []


# ==================================================
# 5. 주간 박스오피스
# ==================================================
@st.cache_data(ttl=3600, show_spinner=False)
def get_weekly_boxoffice(date_text):
    target_date = datetime.strptime(
        date_text, "%Y-%m-%d"
    ).date()

    result = api_get(
        "boxoffice/searchWeeklyBoxOfficeList",
        {
            "targetDt": target_date.strftime("%Y%m%d"),
            "weekGb": "0",
        },
    )

    movies = result.get(
        "boxOfficeResult", {}
    ).get("weeklyBoxOfficeList", [])

    return movies if isinstance(movies, list) else []


# ==================================================
# 6. 영화 상세 정보
# ==================================================
@st.cache_data(ttl=3600, show_spinner=False)
def get_movie_info(movie_code):
    result = api_get(
        "movie/searchMovieInfo",
        {"movieCd": str(movie_code)},
    )

    return result.get(
        "movieInfoResult", {}
    ).get("movieInfo", {})


# ==================================================
# 7. 일별 관객 추이
# 최근 30일
# ==================================================
@st.cache_data(ttl=1800, show_spinner=False)
def get_daily_history(movie_code, end_text, release_text):
    end_date = datetime.strptime(
        end_text, "%Y-%m-%d"
    ).date()

    try:
        release_date = datetime.strptime(
            release_text, "%Y%m%d"
        ).date()
    except (ValueError, TypeError):
        release_date = end_date - timedelta(days=29)

    start_date = max(
        end_date - timedelta(days=29),
        release_date,
    )

    rows = []
    current_date = start_date

    while current_date <= end_date:
        try:
            movies = get_daily_boxoffice(
                current_date.isoformat()
            )

            matched_movie = next(
                (
                    item for item in movies
                    if str(item.get("movieCd", ""))
                    == str(movie_code)
                ),
                None,
            )

            if matched_movie:
                rows.append({
                    "날짜": current_date,
                    "관객 수": int_value(
                        matched_movie.get("audiCnt")
                    ),
                })

        except Exception:
            # 한 날짜의 오류가 전체 화면을 막지 않도록 처리
            pass

        current_date += timedelta(days=1)

    return pd.DataFrame(
        rows,
        columns=["날짜", "관객 수"],
    )


# ==================================================
# 8. 주별 관객 추이
# ==================================================
@st.cache_data(ttl=3600, show_spinner=False)
def get_weekly_history(movie_code, end_text, release_text):
    end_date = datetime.strptime(
        end_text, "%Y-%m-%d"
    ).date()

    try:
        release_date = datetime.strptime(
            release_text, "%Y%m%d"
        ).date()
    except (ValueError, TypeError):
        release_date = end_date - timedelta(days=365)

    rows = []
    current_date = end_date

    # 최대 52주 조회
    for _ in range(52):
        if current_date < release_date:
            break

        try:
            movies = get_weekly_boxoffice(
                current_date.isoformat()
            )

            matched_movie = next(
                (
                    item for item in movies
                    if str(item.get("movieCd", ""))
                    == str(movie_code)
                ),
                None,
            )

            if matched_movie:
                rows.append({
                    "날짜": current_date,
                    "관객 수": int_value(
                        matched_movie.get("audiCnt")
                    ),
                    "기간": matched_movie.get(
                        "showRange",
                        current_date.strftime("%Y%m%d"),
                    ),
                })

        except Exception:
            pass

        current_date -= timedelta(days=7)

    if not rows:
        return pd.DataFrame(
            columns=["날짜", "관객 수", "기간"]
        )

    return (
        pd.DataFrame(rows)
        .drop_duplicates(subset=["날짜"])
        .sort_values("날짜")
        .reset_index(drop=True)
    )


# ==================================================
# 9. 선택한 영화에 맞는 링크 생성
# ==================================================
def movie_links(movie_name):
    # 반드시 선택된 영화의 제목으로 링크를 생성한다.
    encoded_name = quote_plus(str(movie_name).strip())

    poster_url = (
        "https://search.naver.com/search.naver"
        f"?where=image&query={encoded_name}+포스터"
    )

    synopsis_url = (
        "https://search.naver.com/search.naver"
        f"?query={encoded_name}+줄거리+시놉시스"
    )

    trailer_url = (
        "https://www.youtube.com/results?search_query="
        f"{encoded_name}+공식+예고편"
    )

    return poster_url, synopsis_url, trailer_url


# ==================================================
# 10. 영화 선택 콜백
# 중요: 반복문 변수에 의존하지 않고 선택한 영화 전달
# ==================================================
def open_movie_detail(movie_data, selected_date_text):
    st.session_state["selected_movie"] = dict(movie_data)
    st.session_state["selected_date"] = selected_date_text
    st.session_state["page"] = "detail"


def return_to_list():
    st.session_state["page"] = "list"


# ==================================================
# 11. 그래프 출력
# ==================================================
def draw_line_chart(df, x_column, title):
    fig = px.line(
        df,
        x=x_column,
        y="관객 수",
        markers=True,
        title=title,
    )

    fig.update_traces(
        line=dict(color="#80bfff", width=3),
        marker=dict(size=7),
    )

    fig.update_layout(
        paper_bgcolor="#172b49",
        plot_bgcolor="#172b49",
        font_color="#ffffff",
        title_font_color="#ffffff",
        margin=dict(l=10, r=15, t=55, b=10),
        xaxis_title="기간",
        yaxis_title="관객 수",
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
    )


# ==================================================
# 12. 영화 상세 화면
# ==================================================
def show_detail(movie, selected_date):
    # 상세 화면은 전달받은 영화 데이터만 사용
    movie = dict(movie)

    movie_name = str(movie.get("movieNm", "영화 정보"))
    movie_code = str(movie.get("movieCd", ""))
    release_text = str(movie.get("openDt", ""))

    st.button(
        "← 박스오피스 목록으로 돌아가기",
        key="back_to_list",
        on_click=return_to_list,
    )

    st.title(f"🎬 {movie_name}")
    st.caption(
        f"조회 기준일: {selected_date.strftime('%Y-%m-%d')}"
    )

    # 선택한 영화 제목으로만 외부 링크를 생성
    poster_url, synopsis_url, trailer_url = movie_links(
        movie_name
    )

    info_col, graph_col = st.columns(
        [0.9, 1.25],
        gap="large",
    )

    # ----------------------------------------------
    # 왼쪽: 선택한 영화의 정보와 외부 링크
    # ----------------------------------------------
    with info_col:
        with st.container(border=True):
            st.subheader("🎞️ 영화 정보")

            st.markdown(f"### {movie_name}")

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

            st.link_button(
                "🎬 유튜브에서 공식 예고편 찾기",
                trailer_url,
                use_container_width=True,
            )

            st.markdown("---")

            st.metric(
                "조회일 관객 수",
                f"{number(movie.get('audiCnt'))}명",
            )

            st.metric(
                "누적 관객 수",
                f"{number(movie.get('audiAcc'))}명",
            )

            st.metric(
                "스크린 수",
                f"{number(movie.get('scrnCnt'))}개",
            )

            # KOBIS 영화 상세 정보
            try:
                with st.spinner("영화 정보를 불러오는 중..."):
                    info = get_movie_info(movie_code)

                if info:
                    st.markdown("---")
                    st.markdown("#### 기본 정보")

                    if info.get("movieNmEn"):
                        st.write(
                            f"**영문명:** {info['movieNmEn']}"
                        )

                    if info.get("openDt"):
                        st.write(
                            f"**개봉일:** {info['openDt']}"
                        )

                    if info.get("showTm"):
                        st.write(
                            f"**상영 시간:** {info['showTm']}분"
                        )

                    genres = [
                        item.get("genreNm", "")
                        for item in info.get("genres", [])
                        if item.get("genreNm")
                    ]

                    if genres:
                        st.write(
                            f"**장르:** {', '.join(genres)}"
                        )

                    directors = [
                        item.get("peopleNm", "")
                        for item in info.get("directors", [])
                        if item.get("peopleNm")
                    ]

                    if directors:
                        st.write(
                            f"**감독:** {', '.join(directors)}"
                        )

                    actors = [
                        item.get("peopleNm", "")
                        for item in info.get("actors", [])[:5]
                        if item.get("peopleNm")
                    ]

                    if actors:
                        st.write(
                            f"**출연:** {', '.join(actors)}"
                        )

                else:
                    st.info("추가 영화 정보가 없습니다.")

            except Exception as exc:
                st.warning(
                    f"추가 영화 정보를 불러오지 못했습니다: {exc}"
                )

    # ----------------------------------------------
    # 오른쪽: 해당 영화의 관객 추이
    # ----------------------------------------------
    with graph_col:
        with st.container(border=True):
            st.subheader("📈 관객 추이")

            period = st.radio(
                "그래프 기간",
                ["일간", "주간", "월간"],
                horizontal=True,
                key=f"graph_period_{movie_code}",
            )

            end_text = selected_date.isoformat()

            try:
                if period == "일간":
                    with st.spinner(
                        "최근 30일 관객 데이터를 불러오는 중..."
                    ):
                        df = get_daily_history(
                            movie_code,
                            end_text,
                            release_text,
                        )

                    if df.empty:
                        st.info(
                            "최근 30일의 일별 TOP 10 자료에서 "
                            "이 영화의 관객 추이를 찾지 못했습니다."
                        )
                    else:
                        draw_line_chart(
                            df,
                            "날짜",
                            "최근 30일 일별 관객 수",
                        )

                else:
                    with st.spinner(
                        "주간 관객 데이터를 불러오는 중..."
                    ):
                        weekly = get_weekly_history(
                            movie_code,
                            end_text,
                            release_text,
                        )

                    if period == "주간":
                        if weekly.empty:
                            st.info(
                                "주간 TOP 10 자료에서 관객 추이를 "
                                "찾지 못했습니다."
                            )
                        else:
                            draw_line_chart(
                                weekly,
                                "날짜",
                                "주간 관객 수",
                            )

                    else:
                        if weekly.empty:
                            st.info(
                                "월별 그래프를 만들 자료가 없습니다."
                            )
                        else:
                            monthly = weekly.copy()

                            monthly["월"] = (
                                pd.to_datetime(monthly["날짜"])
                                .dt.to_period("M")
                                .astype(str)
                            )

                            monthly = (
                                monthly.groupby(
                                    "월",
                                    as_index=False,
                                )["관객 수"]
                                .sum()
                                .rename(columns={"월": "기간"})
                            )

                            draw_line_chart(
                                monthly,
                                "기간",
                                "월별 관객 수",
                            )

                            st.caption(
                                "월별 수치는 공식 월간 자료가 아니라 "
                                "조회 가능한 주간 TOP 10 관객 수를 "
                                "합산한 참고값입니다."
                            )

            except Exception as exc:
                st.warning(
                    f"그래프를 불러오지 못했습니다: {exc}"
                )

            st.caption(
                "KOBIS 일별·주별 박스오피스는 TOP 10까지만 "
                "제공하므로, 순위 밖 기간의 관객 수는 "
                "그래프에 포함되지 않을 수 있습니다."
            )


# ==================================================
# 13. 박스오피스 목록 화면
# ==================================================
def show_list():
    st.title("🎬 어제의 박스오피스")
    st.caption("영화진흥위원회(KOBIS) 공식 자료")

    selected_date = st.date_input(
        "조회 날짜",
        value=YESTERDAY,
        min_value=date(2004, 11, 11),
        max_value=YESTERDAY,
    )

    selected_date_text = selected_date.isoformat()

    try:
        with st.spinner("박스오피스를 불러오는 중..."):
            movies = get_daily_boxoffice(
                selected_date_text
            )

    except Exception as exc:
        st.error("박스오피스 데이터를 불러오지 못했습니다.")
        st.warning(str(exc))

        st.info(
            'Streamlit Cloud → Settings → Secrets에서 '
            'KOBIS_KEY = "발급받은_API_키"가 설정되어 있는지 '
            "확인해 주세요."
        )
        return

    if not movies:
        st.info("그날은 아직 집계 전입니다")
        return

    # ----------------------------------------------
    # 1위 영화 요약
    # ----------------------------------------------
    first_movie = movies[0]

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "🥇 1위 영화",
        first_movie.get("movieNm", "-"),
    )

    col2.metric(
        "오늘 관객 수",
        f"{number(first_movie.get('audiCnt'))}명",
    )

    col3.metric(
        "누적 관객 수",
        f"{number(first_movie.get('audiAcc'))}명",
    )

    st.markdown("---")
    st.subheader("📊 관객 수 TOP 5")

    top5 = pd.DataFrame([
        {
            "영화명": item.get("movieNm", ""),
            "관객 수": int_value(item.get("audiCnt")),
        }
        for item in movies[:5]
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
        margin=dict(l=10, r=45, t=25, b=10),
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
    )

    # ----------------------------------------------
    # 전체 영화 목록
    # ----------------------------------------------
    st.markdown("---")
    st.subheader("🏆 전체 순위")

    st.caption(
        "순위 또는 영화명을 누르면 해당 영화의 상세 화면으로 이동합니다."
    )

    for index, movie in enumerate(movies):
        # 각 반복마다 독립된 영화 사본 생성
        movie_data = dict(movie)
        movie_code = str(movie_data.get("movieCd", ""))
        movie_name = str(movie_data.get("movieNm", "이름 미상"))

        rank = int_value(movie_data.get("rank"))
        rank_change = int_value(movie_data.get("rankInten"))

        trophy = (
            " 🏆"
            if int_value(movie_data.get("audiAcc")) > 1_000_000
            else ""
        )

        if rank_change > 0:
            change_label = f"🔺 +{rank_change}"
        elif rank_change < 0:
            change_label = f"🔵 {rank_change}"
        else:
            change_label = "➖ 0"

        # 중요:
        # 클릭 시 현재 반복의 영화 사본과 날짜를 콜백에 직접 전달
        callback_args = (
            movie_data,
            selected_date_text,
        )

        with st.container(border=True):
            c1, c2, c3, c4, c5, c6, c7 = st.columns(
                [0.55, 0.7, 2.3, 0.85, 1.05, 1.05, 0.8]
            )

            with c1:
                st.button(
                    f"{rank}위",
                    key=(
                        f"rank_{selected_date_text}_"
                        f"{index}_{movie_code}"
                    ),
                    on_click=open_movie_detail,
                    args=callback_args,
                    use_container_width=True,
                )

            with c2:
                st.write(change_label)

            with c3:
                st.button(
                    f"{movie_name}{trophy}",
                    key=(
                        f"title_{selected_date_text}_"
                        f"{index}_{movie_code}"
                    ),
                    on_click=open_movie_detail,
                    args=callback_args,
                    use_container_width=True,
                )

            with c4:
                st.write(movie_data.get("openDt") or "-")

            with c5:
                st.write(number(movie_data.get("audiCnt")))

            with c6:
                st.write(number(movie_data.get("audiAcc")))

            with c7:
                st.write(number(movie_data.get("scrnCnt")))


# ==================================================
# 14. 앱 실행
# ==================================================
def main():
    if "page" not in st.session_state:
        st.session_state["page"] = "list"

    if st.session_state["page"] == "detail":
        movie = st.session_state.get("selected_movie")
        date_text = st.session_state.get(
            "selected_date",
            YESTERDAY.isoformat(),
        )

        if not movie:
            st.session_state["page"] = "list"
            st.rerun()
            return

        try:
            selected_date = datetime.strptime(
                date_text,
                "%Y-%m-%d",
            ).date()
        except (ValueError, TypeError):
            selected_date = YESTERDAY

        show_detail(movie, selected_date)

    else:
        show_list()


try:
    main()
except Exception as exc:
    st.error("앱 실행 중 오류가 발생했습니다.")
    st.exception(exc)
