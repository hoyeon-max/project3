
import html
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

st.set_page_config(
    page_title="어제의 박스오피스",
    page_icon="🎬",
    layout="wide",
)

BASE_URL = (
    "https://www.kobis.or.kr/kobisopenapi/"
    "webservice/rest"
)
KOREA_TZ = ZoneInfo("Asia/Seoul")


def korea_today():
    return datetime.now(KOREA_TZ).date()


def number(value):
    try:
        return int(float(value or 0))
    except (ValueError, TypeError):
        return 0


def fmt(value):
    return f"{number(value):,}"


def kobis_get(endpoint, params, api_key):
    response = requests.get(
        f"{BASE_URL}/{endpoint}.json",
        params={"key": api_key, **params},
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()

    if "faultInfo" in data:
        message = data["faultInfo"].get(
            "message", "KOBIS API 오류"
        )
        raise RuntimeError(message)

    return data


@st.cache_data(ttl=1800, show_spinner=False)
def get_daily(target_date, api_key):
    data = kobis_get(
        "boxoffice/searchDailyBoxOfficeList",
        {"targetDt": target_date},
        api_key,
    )
    return data.get(
        "boxOfficeResult", {}
    ).get("dailyBoxOfficeList", [])


@st.cache_data(ttl=86400, show_spinner=False)
def get_movie_detail(movie_code, api_key):
    data = kobis_get(
        "movie/searchMovieInfo",
        {"movieCd": movie_code},
        api_key,
    )
    return data.get("movieInfoResult", {}).get(
        "movieInfo", {}
    )


@st.cache_data(ttl=86400, show_spinner=False)
def get_weekly(target_date, api_key):
    data = kobis_get(
        "boxoffice/searchWeeklyBoxOfficeList",
        {
            "targetDt": target_date,
            "weekGb": "0",
        },
        api_key,
    )
    return data.get(
        "boxOfficeResult", {}
    ).get("weeklyBoxOfficeList", [])


def make_table(movies):
    rows = []

    for movie in movies:
        change = number(movie.get("rankInten"))

        if change > 0:
            movement = f"🔴 ▲ {change}"
        elif change < 0:
            movement = f"🔵 ▼ {abs(change)}"
        else:
            movement = "—"

        title = str(movie.get("movieNm", "제목 미상"))
        if number(movie.get("audiAcc")) > 1_000_000:
            title = "🏆 " + title

        rows.append({
            "순위": number(movie.get("rank")),
            "순위 변동": movement,
            "영화명": title,
            "개봉일": movie.get("openDt") or "-",
            "관객수": number(movie.get("audiCnt")),
            "누적관객": number(movie.get("audiAcc")),
            "스크린수": number(movie.get("scrnCnt")),
            "영화코드": str(movie.get("movieCd", "")),
        })

    return pd.DataFrame(rows)


def get_weekly_history(movie_code, release_date, end_date, api_key):
    """KOBIS 주간 상위 10편 데이터에서 해당 영화 기록을 수집."""
    if not release_date or release_date > end_date:
        return pd.DataFrame()

    rows = []
    seen = set()
    query_date = end_date

    while query_date >= release_date:
        try:
            weekly_movies = get_weekly(
                query_date.strftime("%Y%m%d"),
                api_key,
            )

            for item in weekly_movies:
                if str(item.get("movieCd", "")) != str(movie_code):
                    continue

                week = str(item.get("showRange", ""))

                if week in seen:
                    continue

                seen.add(week)
                rows.append({
                    "조회 기준일": query_date,
                    "주간 관객 수": number(item.get("audiCnt")),
                    "주간 누적 관객 수": number(item.get("audiAcc")),
                    "상영 기간": week or query_date.isoformat(),
                })

        except Exception:
            # 일부 주의 조회가 실패해도 다른 주를 계속 조회
            pass

        query_date -= timedelta(days=7)

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values("조회 기준일")


def show_movie_details(movie, api_key, selected_date):
    movie_code = str(movie.get("movieCd", ""))
    movie_name = str(movie.get("movieNm", "제목 미상"))
    open_date = str(movie.get("openDt", "")).strip()

    st.divider()
    st.subheader(f"🎞️ {movie_name} 상세 정보")

    poster_col, info_col = st.columns([1, 2], gap="large")

    with poster_col:
        st.markdown(
            """
            <div style="
                min-height:300px;
                border:1px solid #e5e5e5;
                border-radius:16px;
                display:flex;
                flex-direction:column;
                align-items:center;
                justify-content:center;
                text-align:center;
                padding:24px;
                background:linear-gradient(145deg,#fff8e7,#f2f4f8);
            ">
                <div style="font-size:76px;">🎬</div>
                <div style="font-size:18px;font-weight:700;">
                    포스터 정보 없음
                </div>
                <div style="font-size:13px;color:#666;margin-top:8px;">
                    KOBIS API는 포스터 이미지를 제공하지 않습니다.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with info_col:
        st.markdown("#### 영화 소개")
        st.info(
            "KOBIS API는 영화 줄거리(시놉시스)를 제공하지 않습니다. "
            "대신 KOBIS에서 조회한 영화 정보를 표시합니다."
        )

        try:
            detail = get_movie_detail(movie_code, api_key)
        except Exception as exc:
            detail = {}
            st.warning(f"상세 정보 조회 실패: {exc}")

        directors = detail.get("directors") or []
        actors = detail.get("actors") or []
        genres = detail.get("genres") or []
        nations = detail.get("nations") or []

        director_names = ", ".join(
            p.get("peopleNm", "") for p in directors
            if p.get("peopleNm")
        ) or "정보 없음"

        actor_names = ", ".join(
            p.get("peopleNm", "") for p in actors[:8]
            if p.get("peopleNm")
        ) or "정보 없음"

        genre_names = ", ".join(
            p.get("genreNm", "") for p in genres
            if p.get("genreNm")
        ) or "정보 없음"

        nation_names = ", ".join(
            p.get("nationNm", "") for p in nations
            if p.get("nationNm")
        ) or "정보 없음"

        st.markdown(
            f"**영화명:** {html.escape(str(detail.get('movieNm') or movie_name))}"
        )
        st.markdown(
            f"**영문명:** {html.escape(str(detail.get('movieNmEn') or '정보 없음'))}"
        )
        st.markdown(
            f"**개봉일:** {html.escape(str(detail.get('openDt') or open_date or '정보 없음'))}"
        )
        st.markdown(f"**감독:** {html.escape(director_names)}")
        st.markdown(f"**출연:** {html.escape(actor_names)}")
        st.markdown(f"**장르:** {html.escape(genre_names)}")
        st.markdown(f"**제작 국가:** {html.escape(nation_names)}")
        st.markdown(
            f"**상영 시간:** {html.escape(str(detail.get('showTm') or '정보 없음'))}분"
        )

    st.markdown("#### 📈 주간 관객 수 변화")
    st.caption(
        "KOBIS 주간 박스오피스는 주간 상위 10편만 제공합니다. "
        "그래프는 순위권에 포함되어 조회된 주만 표시하므로 "
        "누락된 주의 관객 수는 나타나지 않을 수 있습니다."
    )

    release = None
    try:
        if open_date:
            release = datetime.strptime(
                open_date, "%Y-%m-%d"
            ).date()
    except ValueError:
        pass

    if not release:
        st.warning("개봉일 정보가 없어 그래프를 표시할 수 없습니다.")
        return

    end_date = min(selected_date, korea_today())

    with st.spinner("주간 관객 수 데이터를 조회하고 있습니다..."):
        history = get_weekly_history(
            movie_code, release, end_date, api_key
        )

    if history.empty:
        st.warning(
            "주간 기록을 찾지 못했습니다. "
            "해당 영화가 주간 순위 상위 10편에 포함되지 않았거나 "
            "조회 가능한 데이터가 없을 수 있습니다."
        )
        return

    fig = px.bar(
        history,
        x="조회 기준일",
        y="주간 관객 수",
        hover_data=["주간 누적 관객 수", "상영 기간"],
        labels={
            "조회 기준일": "조회 기준일",
            "주간 관객 수": "주간 관객 수(명)",
        },
        title="KOBIS 주간 박스오피스 집계 관객 수",
    )
    fig.update_layout(
        xaxis_title="조회 기준일",
        yaxis_title="관객 수(명)",
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    history_display = history.rename(columns={
        "상영 기간": "KOBIS 상영 기간",
    }).copy()

    for col in ["주간 관객 수", "주간 누적 관객 수"]:
        history_display[col] = history_display[col].map(fmt)

    st.dataframe(
        history_display,
        use_container_width=True,
        hide_index=True,
    )


# =========================================================
# 메인 화면
# =========================================================
st.title("🎬 어제의 박스오피스")
st.caption("영화진흥위원회(KOBIS) 공식 오픈 API")

api_key = st.secrets.get("KOBIS_KEY", "")

if not api_key:
    st.error("KOBIS API 키를 찾을 수 없습니다.")
    st.markdown(
        """
        Streamlit Cloud의 **Settings → Secrets**에 아래를 등록하세요.

        ```toml
        KOBIS_KEY = "발급받은_KOBIS_API_키"
        ```
        """
    )
    st.stop()

today = korea_today()
yesterday = today - timedelta(days=1)

selected_date = st.date_input(
    "조회 날짜",
    value=yesterday,
    min_value=date(2004, 1, 1),
    max_value=yesterday,
    help="오늘은 집계가 완료되지 않았을 수 있어 선택할 수 없습니다.",
)

try:
    with st.spinner("일별 박스오피스를 불러오는 중입니다..."):
        movies = get_daily(
            selected_date.strftime("%Y%m%d"),
            str(api_key),
        )
except requests.exceptions.Timeout:
    st.error("KOBIS API 응답 시간이 초과되었습니다. 잠시 후 다시 시도하세요.")
    st.stop()
except requests.exceptions.RequestException as exc:
    st.error(f"KOBIS API 연결 오류: {exc}")
    st.info("인터넷 연결과 KOBIS API 서버 상태를 확인해 주세요.")
    st.stop()
except Exception as exc:
    st.error(f"데이터 조회 오류: {exc}")
    st.info("KOBIS API 키와 이용 상태를 확인해 주세요.")
    st.stop()

if not movies:
    st.info("그날은 아직 집계 전입니다")
    st.stop()

df = make_table(movies)

st.subheader(
    f"📅 {selected_date.strftime('%Y년 %m월 %d일')} 박스오피스"
)

first = movies[0]
c1, c2, c3 = st.columns(3)

with c1:
    st.metric("🥇 1위 영화", str(first.get("movieNm", "정보 없음")))
with c2:
    st.metric("1위 관객 수", f"{fmt(first.get('audiCnt'))}명")
with c3:
    st.metric("1위 누적 관객", f"{fmt(first.get('audiAcc'))}명")

st.markdown("### 📊 관객 수 상위 5편")

top5 = df.head(5).copy()
top5["그래프 영화명"] = top5["영화명"].str.replace(
    "🏆 ", "", regex=False
)

fig = px.bar(
    top5.sort_values("관객수", ascending=True),
    x="관객수",
    y="그래프 영화명",
    orientation="h",
    text="관객수",
    labels={
        "관객수": "관객 수(명)",
        "그래프 영화명": "영화",
    },
)
fig.update_traces(
    texttemplate="%{x:,.0f}",
    textposition="outside",
    cliponaxis=False,
)
fig.update_layout(
    xaxis_title="관객 수(명)",
    yaxis_title="",
    margin=dict(l=10, r=40, t=20, b=20),
)
st.plotly_chart(fig, use_container_width=True)

st.markdown("### 🎟️ 일별 박스오피스")
st.caption("아래에서 영화를 선택하면 상세 정보와 주간 관객 수 그래프를 볼 수 있습니다.")

movie_options = {
    f"{number(m.get('rank'))}위 · {m.get('movieNm', '제목 미상')}": str(m.get("movieCd", ""))
    for m in movies
}
labels = list(movie_options.keys())

if not labels:
    st.info("표시할 영화가 없습니다.")
    st.stop()

selected_label = st.selectbox(
    "상세 정보를 볼 영화",
    options=labels,
)

selected_code = movie_options[selected_label]

display_df = df[
    ["순위", "순위 변동", "영화명", "개봉일", "관객수", "누적관객", "스크린수"]
].copy()

for col in ["관객수", "누적관객", "스크린수"]:
    display_df[col] = display_df[col].map(fmt)

st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
)

selected_movie = next(
    (
        m for m in movies
        if str(m.get("movieCd", "")) == selected_code
    ),
    movies[0],
)

show_movie_details(
    selected_movie,
    str(api_key),
    selected_date,
)

st.divider()
st.caption(
    "데이터 출처: 영화진흥위원회(KOBIS) 오픈 API. "
    "주간 관객 수는 API에서 제공하는 순위권 데이터에 한정됩니다."
)
