
import re
from datetime import date, datetime, timedelta
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

# =========================================================
# 기본 설정
# =========================================================
st.set_page_config(
    page_title="어제의 박스오피스",
    page_icon="🎬",
    layout="wide",
)

BASE = "https://www.kobis.or.kr/kobisopenapi/webservice/rest"
SEOUL = ZoneInfo("Asia/Seoul")


# =========================================================
# 남색 시네마 테마
# =========================================================
st.markdown("""
<style>
.stApp {
    background:
        radial-gradient(ellipse at 12% 15%,
            rgba(52,76,135,.24), transparent 42%),
        radial-gradient(ellipse at 88% 82%,
            rgba(62,46,112,.22), transparent 40%),
        linear-gradient(135deg,#080f24 0%,#101a35 48%,#11182f 100%);
    color: #edf2ff;
    position: relative;
}
.stApp::before {
    content: "";
    position: fixed;
    z-index: 0;
    pointer-events: none;
    width: 115vw;
    height: 260px;
    left: -8vw;
    top: 24%;
    border-top: 2px solid rgba(174,195,255,.10);
    border-bottom: 2px solid rgba(174,195,255,.10);
    border-radius: 48% 52% 44% 56% / 40% 60% 40% 60%;
    transform: rotate(-12deg);
    opacity: .58;
    background: repeating-linear-gradient(
        90deg,
        transparent 0 32px,
        rgba(190,207,255,.055) 33px 45px,
        transparent 46px 65px
    );
    mask-image: linear-gradient(
        to bottom,transparent 0%,black 18%,black 82%,transparent 100%
    );
}
.stApp::after {
    content: "";
    position: fixed;
    z-index: 0;
    pointer-events: none;
    width: 125vw;
    height: 190px;
    left: -12vw;
    bottom: 7%;
    border-top: 1px solid rgba(160,181,255,.08);
    border-bottom: 1px solid rgba(160,181,255,.08);
    border-radius: 55% 45% 60% 40% / 55% 40% 60% 45%;
    transform: rotate(9deg);
    opacity: .48;
    background: repeating-linear-gradient(
        90deg,
        transparent 0 30px,
        rgba(175,195,255,.045) 31px 43px,
        transparent 44px 64px
    );
    filter: blur(1px);
}
[data-testid="stAppViewContainer"] > .main {
    position: relative;
    z-index: 1;
}
[data-testid="stHeader"] {
    background: rgba(8,15,36,.72);
}
h1,h2,h3 {
    color: #f3f5ff !important;
    letter-spacing: -.5px;
}
p,label,.stMarkdown,[data-testid="stCaptionContainer"] {
    color: #d4def7;
}
[data-testid="stMetric"] {
    background: rgba(28,42,77,.76);
    border: 1px solid rgba(158,181,255,.17);
    border-radius: 16px;
    padding: 18px 20px;
    box-shadow: 0 8px 24px rgba(0,0,0,.12);
    backdrop-filter: blur(8px);
}
[data-testid="stMetricLabel"] { color: #b9c9f4 !important; }
[data-testid="stMetricValue"] { color: #fff !important; }
.stButton > button,.stLinkButton > a {
    background: rgba(39,58,105,.88);
    color: #f4f6ff !important;
    border: 1px solid rgba(163,187,255,.25);
    border-radius: 10px;
    transition: all .2s ease;
}
.stButton > button:hover,.stLinkButton > a:hover {
    background: #354f8b;
    border-color: #91adff;
    color: #fff !important;
    transform: translateY(-1px);
}
[data-baseweb="select"] > div,
[data-testid="stDateInput"] input {
    background: rgba(22,34,64,.94);
    color: #fff;
    border-color: rgba(160,181,255,.30);
    border-radius: 10px;
}
[data-testid="stRadio"] label { color: #e4eaff !important; }
[data-testid="stDataFrame"],[data-testid="stTable"] {
    background: rgba(18,29,55,.84);
    border: 1px solid rgba(158,181,255,.16);
    border-radius: 12px;
    overflow: hidden;
}
hr { border-color: rgba(167,187,255,.18); }
[data-testid="stAlert"] {
    background: rgba(30,46,82,.90);
    border: 1px solid rgba(160,181,255,.22);
    border-radius: 12px;
    color: #edf2ff;
}
[data-testid="stPlotlyChart"] {
    background: rgba(19,30,57,.72);
    border: 1px solid rgba(158,181,255,.15);
    border-radius: 16px;
    padding: 5px;
}
a { color: #a9c5ff !important; }
@media (max-width:768px) {
    .stApp::before { height:180px; top:30%; opacity:.38; }
    .stApp::after { height:140px; opacity:.30; }
}
</style>
""", unsafe_allow_html=True)


# =========================================================
# 공통 함수
# =========================================================
def today_korea():
    return datetime.now(SEOUL).date()


def to_int(value):
    try:
        return int(float(value or 0))
    except (ValueError, TypeError):
        return 0


def fmt(value):
    return f"{to_int(value):,}"


def api_get(endpoint, params, key):
    response = requests.get(
        f"{BASE}/{endpoint}.json",
        params={"key": key, **params},
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()

    if "faultInfo" in data:
        raise RuntimeError(
            data["faultInfo"].get("message", "KOBIS API 오류")
        )

    return data


# =========================================================
# KOBIS API
# =========================================================
@st.cache_data(ttl=1800, show_spinner=False)
def daily_boxoffice(target_dt, key):
    data = api_get(
        "boxoffice/searchDailyBoxOfficeList",
        {"targetDt": target_dt},
        key,
    )
    return data.get("boxOfficeResult", {}).get(
        "dailyBoxOfficeList", []
    )


@st.cache_data(ttl=86400, show_spinner=False)
def movie_detail(movie_cd, key):
    data = api_get(
        "movie/searchMovieInfo",
        {"movieCd": movie_cd},
        key,
    )
    return data.get("movieInfoResult", {}).get("movieInfo", {})


@st.cache_data(ttl=86400, show_spinner=False)
def weekly_boxoffice(target_dt, key):
    data = api_get(
        "boxoffice/searchWeeklyBoxOfficeList",
        {"targetDt": target_dt, "weekGb": "0"},
        key,
    )
    return data.get("boxOfficeResult", {}).get(
        "weeklyBoxOfficeList", []
    )


# =========================================================
# 관객 수 이력
# =========================================================
@st.cache_data(ttl=86400, show_spinner=False)
def daily_history(movie_cd, open_date, end_date, key):
    try:
        release = date.fromisoformat(open_date)
        end = date.fromisoformat(end_date)
    except (ValueError, TypeError):
        return pd.DataFrame()

    start = max(release, end - timedelta(days=59))
    rows = []
    current = start

    while current <= end:
        try:
            movies = daily_boxoffice(current.strftime("%Y%m%d"), key)
            for item in movies:
                if str(item.get("movieCd")) == str(movie_cd):
                    rows.append({
                        "날짜": current,
                        "관객 수": to_int(item.get("audiCnt")),
                        "누적 관객 수": to_int(item.get("audiAcc")),
                    })
                    break
        except Exception:
            pass

        current += timedelta(days=1)

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values("날짜")


@st.cache_data(ttl=86400, show_spinner=False)
def weekly_history(movie_cd, open_date, end_date, key):
    try:
        release = date.fromisoformat(open_date)
        end = date.fromisoformat(end_date)
    except (ValueError, TypeError):
        return pd.DataFrame()

    if release > end:
        return pd.DataFrame()

    rows = []
    seen = set()
    current = end

    while current >= release:
        try:
            movies = weekly_boxoffice(current.strftime("%Y%m%d"), key)

            for item in movies:
                if str(item.get("movieCd")) != str(movie_cd):
                    continue

                period = str(item.get("showRange", ""))
                identity = period or current.isoformat()

                if identity in seen:
                    continue

                seen.add(identity)
                rows.append({
                    "날짜": current,
                    "관객 수": to_int(item.get("audiCnt")),
                    "누적 관객 수": to_int(item.get("audiAcc")),
                    "상영 기간": period or current.isoformat(),
                })
        except Exception:
            pass

        current -= timedelta(days=7)

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values("날짜")


def make_monthly_history(weekly_df):
    if weekly_df.empty:
        return pd.DataFrame()

    df = weekly_df.copy()
    df["월"] = pd.to_datetime(df["날짜"]).dt.to_period("M").astype(str)

    monthly = df.groupby("월", as_index=False).agg({
        "관객 수": "sum",
        "누적 관객 수": "last",
    })
    monthly["날짜"] = pd.to_datetime(monthly["월"] + "-01")
    return monthly.sort_values("날짜")


# =========================================================
# 그래프 스타일
# =========================================================
def style_line_chart(fig):
    fig.update_traces(
        line=dict(color="#91adff", width=3),
        marker=dict(color="#dce5ff", size=6),
    )
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(10,18,39,.20)",
        font=dict(color="#e8edff", size=10),
        title_font=dict(color="#fff", size=16),
        margin=dict(l=8, r=8, t=45, b=8),
        hovermode="x unified",
        xaxis=dict(
            title=None,
            tickfont=dict(color="#c4d2f5", size=9),
            gridcolor="rgba(180,198,255,.10)",
        ),
        yaxis=dict(
            title=None,
            tickfont=dict(color="#c4d2f5", size=9),
            gridcolor="rgba(180,198,255,.10)",
        ),
        showlegend=False,
    )
    return fig


def make_naver_links(movie_name):
    query = quote_plus(movie_name)
    poster_url = (
        "https://search.naver.com/search.naver"
        f"?where=image&query={query}+포스터"
    )
    synopsis_url = (
        "https://search.naver.com/search.naver"
        f"?query={query}+줄거리+시놉시스"
    )
    return poster_url, synopsis_url


# =========================================================
# 박스오피스 목록
# =========================================================
def render_movie_list(movies, selected_date):
    st.title("🎬 어제의 박스오피스")
    st.caption(
        f"{selected_date:%Y년 %m월 %d일} 기준 · "
        "순위 또는 영화 제목을 누르면 상세 화면으로 이동합니다."
    )

    first = movies[0]
    c1, c2, c3 = st.columns(3)
    c1.metric("🥇 1위 영화", first.get("movieNm", "-"))
    c2.metric("1위 관객 수", f"{fmt(first.get('audiCnt'))}명")
    c3.metric("1위 누적 관객", f"{fmt(first.get('audiAcc'))}명")

    st.subheader("📊 관객 수 상위 5편")
    chart_rows = []

    for movie in movies[:5]:
        name = str(movie.get("movieNm", "제목 미상"))
        if to_int(movie.get("audiAcc")) > 1_000_000:
            name = "🏆 " + name

        chart_rows.append({
            "영화명": name,
            "관객 수": to_int(movie.get("audiCnt")),
        })

    chart_df = pd.DataFrame(chart_rows).sort_values("관객 수")
    fig = px.bar(
        chart_df,
        x="관객 수",
        y="영화명",
        orientation="h",
        labels={"관객 수": "관객 수(명)", "영화명": "영화"},
    )
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(10,18,39,.20)",
        font=dict(color="#e8edff"),
        xaxis=dict(gridcolor="rgba(180,198,255,.10)"),
    )
    fig.update_traces(marker_color="#718fe0")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("🎟️ 일별 박스오피스")
    headers = st.columns([0.8, 1.0, 3.5, 1.5, 1.5, 1.5, 1.1])

    for col, label in zip(
        headers,
        ["순위", "변동", "영화 제목", "관객수", "누적관객", "개봉일", "스크린"],
    ):
        col.markdown(f"**{label}**")

    st.divider()

    for movie in movies:
        rank = to_int(movie.get("rank"))
        code = str(movie.get("movieCd", ""))
        title = str(movie.get("movieNm", "제목 미상"))

        if to_int(movie.get("audiAcc")) > 1_000_000:
            title = "🏆 " + title

        change = to_int(movie.get("rankInten"))
        if change > 0:
            movement = f"🔴 ▲ {change}"
        elif change < 0:
            movement = f"🔵 ▼ {abs(change)}"
        else:
            movement = "—"

        cols = st.columns([0.8, 1.0, 3.5, 1.5, 1.5, 1.5, 1.1])

        if cols[0].button(
            f"{rank}위", key=f"rank_{code}", use_container_width=True
        ):
            st.session_state["selected_movie"] = code
            st.session_state["selected_movie_data"] = movie
            st.session_state["selected_movie_date"] = selected_date
            st.rerun()

        cols[1].markdown(movement)

        if cols[2].button(
            title, key=f"title_{code}", use_container_width=True
        ):
            st.session_state["selected_movie"] = code
            st.session_state["selected_movie_data"] = movie
            st.session_state["selected_movie_date"] = selected_date
            st.rerun()

        cols[3].write(fmt(movie.get("audiCnt")))
        cols[4].write(fmt(movie.get("audiAcc")))
        cols[5].write(movie.get("openDt") or "-")
        cols[6].write(fmt(movie.get("scrnCnt")))


# =========================================================
# 영화 상세 화면
# 포스터 자리: 왼쪽에 그래프 설정 + 그래프
# 오른쪽에 영화 정보 + 네이버 하이퍼링크 버튼
# =========================================================
def render_movie_page(movie, key, selected_date):
    movie_cd = str(movie.get("movieCd", ""))
    movie_name = str(movie.get("movieNm", "제목 미상"))

    if st.button("← 박스오피스 목록으로 돌아가기"):
        st.session_state["selected_movie"] = None
        st.session_state.pop("selected_movie_data", None)
        st.rerun()

    st.title(f"🎬 {movie_name}")
    st.caption("영화 정보와 관객 수 추이를 확인하세요.")

    try:
        with st.spinner("영화 정보를 불러오는 중입니다..."):
            detail = movie_detail(movie_cd, key)
    except Exception:
        detail = {}

    poster_url, synopsis_url = make_naver_links(movie_name)

    # 포스터 자리에는 작은 그래프, 오른쪽에는 영화 정보를 배치
    graph_col, info_col = st.columns([1, 1.15], gap="large")

    with graph_col:
        st.subheader("📈 관객 수 추이")

        period = st.radio(
            "그래프 기간",
            ["일간", "주간", "월간"],
            horizontal=True,
            key=f"period_{movie_cd}",
        )

        open_date = str(movie.get("openDt", "")).strip()
        end_date = min(selected_date, today_korea()).isoformat()

        if period == "일간":
            st.caption("최근 60일 · 일별 상위 10편 기록")

            with st.spinner("일별 데이터를 조회하고 있습니다..."):
                history = daily_history(
                    movie_cd, open_date, end_date, key
                )

            if history.empty:
                st.info("조회 가능한 일별 기록이 없습니다.")
            else:
                fig = px.line(
                    history,
                    x="날짜",
                    y="관객 수",
                    markers=True,
                    hover_data=["누적 관객 수"],
                    title="일별 관객 수",
                )
                st.plotly_chart(
                    style_line_chart(fig),
                    use_container_width=True,
                )
                with st.expander("일별 데이터 표"):
                    st.dataframe(
                        history,
                        use_container_width=True,
                        hide_index=True,
                    )

        else:
            st.caption("주간 상위 10편에 포함된 기록 기준")

            with st.spinner("주간 데이터를 조회하고 있습니다..."):
                weekly = weekly_history(
                    movie_cd, open_date, end_date, key
                )

            if weekly.empty:
                st.info("조회 가능한 주간 기록이 없습니다.")

            elif period == "주간":
                fig = px.line(
                    weekly,
                    x="날짜",
                    y="관객 수",
                    markers=True,
                    hover_data=["누적 관객 수", "상영 기간"],
                    title="주간 관객 수",
                )
                st.plotly_chart(
                    style_line_chart(fig),
                    use_container_width=True,
                )
                with st.expander("주간 데이터 표"):
                    st.dataframe(
                        weekly,
                        use_container_width=True,
                        hide_index=True,
                    )

            else:
                monthly = make_monthly_history(weekly)

                if monthly.empty:
                    st.info("월별로 표시할 데이터가 없습니다.")
                else:
                    st.caption("주간 데이터의 월별 합계 · 참고용")
                    fig = px.line(
                        monthly,
                        x="날짜",
                        y="관객 수",
                        markers=True,
                        hover_data=["누적 관객 수"],
                        title="월별 관객 수 참고 추이",
                    )
                    st.plotly_chart(
                        style_line_chart(fig),
                        use_container_width=True,
                    )
                    with st.expander("월별 데이터 표"):
                        st.dataframe(
                            monthly[["월", "관객 수", "누적 관객 수"]],
                            use_container_width=True,
                            hide_index=True,
                        )

                    st.caption(
                        "월간 그래프는 공식 월간 집계가 아닙니다. "
                        "조회된 주간 상위 10편 데이터의 합계이며 "
                        "누락된 주가 있을 수 있습니다."
                    )

        st.caption(
            "참고: 일별은 최근 60일만 조회하며, "
            "순위권 밖 기간의 관객 수는 표시되지 않을 수 있습니다."
        )

    with info_col:
        st.subheader("🎞️ 영화 정보")

        directors = detail.get("directors") or []
        actors = detail.get("actors") or []
        genres = detail.get("genres") or []
        nations = detail.get("nations") or []

        director_names = ", ".join(
            p.get("peopleNm", "")
            for p in directors if p.get("peopleNm")
        ) or "정보 없음"

        actor_names = ", ".join(
            p.get("peopleNm", "")
            for p in actors[:10] if p.get("peopleNm")
        ) or "정보 없음"

        genre_names = ", ".join(
            p.get("genreNm", "")
            for p in genres if p.get("genreNm")
        ) or "정보 없음"

        nation_names = ", ".join(
            p.get("nationNm", "")
            for p in nations if p.get("nationNm")
        ) or "정보 없음"

        st.markdown(f"**영문 제목:** {detail.get('movieNmEn') or '정보 없음'}")
        st.markdown(
            f"**개봉일:** {detail.get('openDt') or movie.get('openDt') or '정보 없음'}"
        )
        st.markdown(f"**감독:** {director_names}")
        st.markdown(f"**출연:** {actor_names}")
        st.markdown(f"**장르:** {genre_names}")
        st.markdown(f"**제작 국가:** {nation_names}")
        st.markdown(f"**상영 시간:** {detail.get('showTm') or '정보 없음'}분")

        st.divider()
        st.subheader("🔎 포스터와 시놉시스")

        st.markdown(
            "포스터와 줄거리는 네이버 검색 페이지에서 확인할 수 있어."
        )

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

        st.caption(
            "버튼을 누르면 네이버 검색 결과가 새 페이지로 열려."
        )

        st.divider()
        st.subheader("🎟️ 선택한 날짜의 기록")

        m1, m2 = st.columns(2)
        m1.metric("일일 관객 수", f"{fmt(movie.get('audiCnt'))}명")
        m2.metric("누적 관객 수", f"{fmt(movie.get('audiAcc'))}명")

        m3, m4 = st.columns(2)
        m3.metric("상영 스크린 수", f"{fmt(movie.get('scrnCnt'))}개")
        m4.metric("상영 횟수", f"{fmt(movie.get('showCnt'))}회")


# =========================================================
# 앱 실행
# =========================================================
key = st.secrets.get("KOBIS_KEY", "")

if not key:
    st.title("🎬 어제의 박스오피스")
    st.error("KOBIS API 키가 설정되지 않았습니다.")
    st.code('KOBIS_KEY = "발급받은_KOBIS_API_키"', language="toml")
    st.stop()

today = today_korea()
yesterday = today - timedelta(days=1)

if "selected_movie" not in st.session_state:
    st.session_state["selected_movie"] = None

if "selected_movie_data" not in st.session_state:
    st.session_state["selected_movie_data"] = None

if "boxoffice_date" not in st.session_state:
    st.session_state["boxoffice_date"] = yesterday


if st.session_state["selected_movie"]:
    movie = st.session_state.get("selected_movie_data")
    selected_date = st.session_state.get(
        "selected_movie_date",
        st.session_state["boxoffice_date"],
    )

    if movie:
        render_movie_page(movie, str(key), selected_date)
    else:
        st.warning("선택한 영화 정보를 찾지 못했습니다.")
        if st.button("목록으로 돌아가기"):
            st.session_state["selected_movie"] = None
            st.rerun()

else:
    st.title("🎬 어제의 박스오피스")

    selected_date = st.date_input(
        "조회 날짜",
        value=yesterday,
        min_value=date(2004, 1, 1),
        max_value=yesterday,
        help="오늘 날짜는 선택할 수 없습니다.",
    )

    st.session_state["boxoffice_date"] = selected_date

    try:
        with st.spinner("박스오피스 데이터를 불러오는 중입니다..."):
            movies = daily_boxoffice(
                selected_date.strftime("%Y%m%d"),
                str(key),
            )

    except requests.exceptions.Timeout:
        st.error("KOBIS API 응답 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.")
        st.stop()

    except requests.exceptions.RequestException as exc:
        st.error(f"KOBIS API 연결 오류: {exc}")
        st.info("인터넷 연결과 API 키를 확인해 주세요.")
        st.stop()

    except Exception as exc:
        st.error(f"데이터 조회 오류: {exc}")
        st.stop()

    if not movies:
        st.info("그날은 아직 집계 전입니다")
    else:
        render_movie_list(movies, selected_date)
        st.caption(
            "데이터 출처: 영화진흥위원회(KOBIS) 오픈 API. "
            "관객 수 그래프는 조회 가능한 박스오피스 기록을 기준으로 합니다."
        )
