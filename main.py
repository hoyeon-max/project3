
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urljoin

import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from bs4 import BeautifulSoup

st.set_page_config(
    page_title="어제의 박스오피스",
    page_icon="🎬",
    layout="wide",
)

BASE = "https://www.kobis.or.kr/kobisopenapi/webservice/rest"
KOBIS_WEB = "https://www.kobis.or.kr"
TZ = ZoneInfo("Asia/Seoul")


def today_korea():
    return datetime.now(TZ).date()


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


@st.cache_data(ttl=86400, show_spinner=False)
def get_kobis_web_info(movie_cd):
    """
    KOBIS 영화 상세 웹페이지에서 포스터와 줄거리 정보를 찾는다.
    페이지 구조나 접근 정책에 따라 정보가 반환되지 않을 수 있다.
    """
    url = (
        f"{KOBIS_WEB}/kobis/business/mast/mvie/"
        f"searchMovieDtl.do?movieCd={movie_cd}"
    )

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "ko-KR,ko;q=0.9",
    }

    try:
        response = requests.get(
            url, headers=headers, timeout=15
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        poster = ""
        for selector in [
            'meta[property="og:image"]',
            'meta[name="twitter:image"]',
        ]:
            tag = soup.select_one(selector)
            if tag and tag.get("content"):
                poster = urljoin(url, tag["content"])
                break

        if not poster:
            for img in soup.select("img[src]"):
                src = img.get("src", "")
                alt = img.get("alt", "")
                if any(word in (src + alt).lower()
                       for word in ["poster", "포스터", "movie"]):
                    poster = urljoin(url, src)
                    break

        synopsis = ""
        # 줄거리 영역의 후보 선택자
        for selector in [
            "#synop",
            ".synop",
            ".movieSynopsis",
            ".movie_synopsis",
            ".plot",
            "[class*='synop']",
            "[id*='synop']",
        ]:
            tag = soup.select_one(selector)
            if tag:
                text = tag.get_text(" ", strip=True)
                if len(text) > 20:
                    synopsis = text
                    break

        # 선택자에서 찾지 못하면 페이지 텍스트의 줄거리 항목을 확인
        if not synopsis:
            page_text = soup.get_text("\n", strip=True)
            match = re.search(
                r"(?:줄거리|시놉시스)\s*[:：]?\s*(.{30,1200})",
                page_text,
                re.DOTALL,
            )
            if match:
                synopsis = re.split(
                    r"\n(?:영화|감독|출연|배우|제작|배급|상영)",
                    match.group(1),
                )[0].strip()

        # 사이트 메타 설명은 줄거리 영역이 없는 경우에만 보조로 사용
        if not synopsis:
            meta = soup.select_one('meta[name="description"]')
            if meta:
                description = meta.get("content", "").strip()
                if len(description) > 30:
                    synopsis = description

        return {
            "poster": poster,
            "synopsis": synopsis,
            "url": url,
        }

    except Exception:
        return {
            "poster": "",
            "synopsis": "",
            "url": url,
        }


@st.cache_data(ttl=86400, show_spinner=False)
def weekly_history(movie_cd, open_date, end_date, key):
    """주간 박스오피스 상위 10편에서 조회되는 기록만 모은다."""
    try:
        release = datetime.strptime(
            open_date, "%Y-%m-%d"
        ).date()
    except (ValueError, TypeError):
        return pd.DataFrame()

    end = date.fromisoformat(end_date)
    if release > end:
        return pd.DataFrame()

    rows = []
    seen = set()
    query_date = end

    while query_date >= release:
        try:
            movies = weekly_boxoffice(
                query_date.strftime("%Y%m%d"), key
            )
            for item in movies:
                if str(item.get("movieCd", "")) != str(movie_cd):
                    continue

                period = str(item.get("showRange", ""))
                identity = period or query_date.isoformat()
                if identity in seen:
                    continue

                seen.add(identity)
                rows.append({
                    "조회 기준일": query_date,
                    "주간 관객 수": to_int(item.get("audiCnt")),
                    "주간 누적 관객 수": to_int(item.get("audiAcc")),
                    "상영 기간": period or query_date.isoformat(),
                })
        except Exception:
            pass

        query_date -= timedelta(days=7)

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values("조회 기준일")


def render_movie_list(movies, selected_date):
    st.title("🎬 어제의 박스오피스")
    st.caption(
        f"{selected_date:%Y년 %m월 %d일} · "
        "순위 또는 영화 제목을 눌러 상세 화면으로 이동하세요."
    )

    first = movies[0]
    c1, c2, c3 = st.columns(3)
    c1.metric("🥇 1위 영화", first.get("movieNm", "-"))
    c2.metric("1위 관객 수", f"{fmt(first.get('audiCnt'))}명")
    c3.metric("1위 누적 관객", f"{fmt(first.get('audiAcc'))}명")

    rows = []
    for movie in movies:
        change = to_int(movie.get("rankInten"))
        if change > 0:
            movement = f"🔴 ▲ {change}"
        elif change < 0:
            movement = f"🔵 ▼ {abs(change)}"
        else:
            movement = "—"

        title = str(movie.get("movieNm", "제목 미상"))
        if to_int(movie.get("audiAcc")) > 1_000_000:
            title = "🏆 " + title

        rows.append({
            "순위": to_int(movie.get("rank")),
            "순위 변동": movement,
            "영화명": title,
            "개봉일": movie.get("openDt") or "-",
            "관객수": to_int(movie.get("audiCnt")),
            "누적관객": to_int(movie.get("audiAcc")),
            "스크린수": to_int(movie.get("scrnCnt")),
        })

    df = pd.DataFrame(rows)

    st.subheader("📊 관객 수 상위 5편")
    top5 = df.head(5).copy()
    top5["그래프 영화명"] = top5["영화명"].str.replace(
        "🏆 ", "", regex=False
    )

    fig = px.bar(
        top5.sort_values("관객수"),
        x="관객수",
        y="그래프 영화명",
        orientation="h",
        labels={
            "관객수": "관객 수(명)",
            "그래프 영화명": "영화",
        },
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("🎟️ 일별 박스오피스")
    st.caption("아래에서 순위 또는 영화 제목을 클릭하세요.")

    # 각 행의 순위와 제목 버튼은 동일한 영화 상세 화면을 연다.
    header = st.columns([0.8, 1.0, 3.5, 1.5, 1.5, 1.5, 1.1])
    for col, label in zip(
        header,
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
            st.rerun()

        cols[1].markdown(movement)

        if cols[2].button(
            title, key=f"title_{code}", use_container_width=True
        ):
            st.session_state["selected_movie"] = code
            st.rerun()

        cols[3].write(fmt(movie.get("audiCnt")))
        cols[4].write(fmt(movie.get("audiAcc")))
        cols[5].write(movie.get("openDt") or "-")
        cols[6].write(fmt(movie.get("scrnCnt")))


def render_movie_page(movie, key, selected_date):
    movie_cd = str(movie.get("movieCd", ""))
    movie_name = str(movie.get("movieNm", "제목 미상"))

    if st.button("← 박스오피스 목록으로 돌아가기"):
        st.session_state["selected_movie"] = None
        st.rerun()

    st.title(f"🎬 {movie_name}")
    st.caption("KOBIS 영화 정보 및 관객 수 기록")

    # 상세정보 조회
    with st.spinner("영화 정보를 불러오는 중입니다..."):
        try:
            detail = movie_detail(movie_cd, key)
        except Exception:
            detail = {}

        web_info = get_kobis_web_info(movie_cd)

    poster_col, info_col = st.columns([1, 2], gap="large")

    with poster_col:
        if web_info.get("poster"):
            st.image(web_info["poster"], use_container_width=True)
        else:
            st.markdown(
                """
                <div style="
                    height:350px;border:1px solid #ddd;
                    border-radius:16px;display:flex;
                    flex-direction:column;align-items:center;
                    justify-content:center;text-align:center;
                    padding:20px;background:#fff8e7;">
                    <div style="font-size:72px;">🎞️</div>
                    <b>포스터를 찾지 못했습니다</b>
                    <p>KOBIS 웹페이지에서 이미지가 제공되지 않았습니다.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with info_col:
        st.subheader("영화 정보")

        directors = detail.get("directors") or []
        actors = detail.get("actors") or []
        genres = detail.get("genres") or []
        nations = detail.get("nations") or []

        director_names = ", ".join(
            p.get("peopleNm", "") for p in directors
            if p.get("peopleNm")
        ) or "정보 없음"

        actor_names = ", ".join(
            p.get("peopleNm", "") for p in actors[:10]
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

        st.markdown(f"**영문 제목:** {detail.get('movieNmEn') or '정보 없음'}")
        st.markdown(f"**개봉일:** {detail.get('openDt') or movie.get('openDt') or '정보 없음'}")
        st.markdown(f"**감독:** {director_names}")
        st.markdown(f"**출연:** {actor_names}")
        st.markdown(f"**장르:** {genre_names}")
        st.markdown(f"**제작 국가:** {nation_names}")
        st.markdown(f"**상영 시간:** {detail.get('showTm') or '정보 없음'}분")

        st.subheader("📖 시놉시스")

        if web_info.get("synopsis"):
            st.write(web_info["synopsis"])
        else:
            st.info(
                "KOBIS 웹페이지에서 줄거리를 자동으로 찾지 못했습니다. "
                "웹페이지 구조 또는 접근 제한 때문에 정보가 없을 수 있습니다."
            )
            st.link_button(
                "KOBIS 영화 상세 페이지 열기",
                web_info["url"],
            )

    st.divider()
    st.subheader("📈 주간 관객 수 변화")
    st.caption(
        "꺾은선 그래프입니다. KOBIS 주간 박스오피스는 상위 10편만 제공하므로 "
        "순위권에 포함된 주만 표시될 수 있습니다."
    )

    open_date = str(movie.get("openDt", "")).strip()
    end_date = min(selected_date, today_korea())

    with st.spinner("주간 관객 수 기록을 조회하고 있습니다..."):
        history = weekly_history(
            movie_cd,
            open_date,
            end_date.isoformat(),
            key,
        )

    if history.empty:
        st.warning(
            "조회 가능한 주간 관객 수 기록이 없습니다. "
            "영화가 주간 상위 10편에 포함되지 않았을 수 있습니다."
        )
    else:
        fig = px.line(
            history,
            x="조회 기준일",
            y="주간 관객 수",
            markers=True,
            hover_data=["주간 누적 관객 수", "상영 기간"],
            labels={
                "조회 기준일": "조회 기준일",
                "주간 관객 수": "주간 관객 수(명)",
            },
            title=f"{movie_name} 주간 관객 수",
        )
        fig.update_layout(
            hovermode="x unified",
            xaxis_title="조회 기준일",
            yaxis_title="주간 관객 수(명)",
        )
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(
            history,
            use_container_width=True,
            hide_index=True,
        )


# =========================================================
# 앱 시작
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

# 날짜 선택과 박스오피스 조회는 목록 화면에서만 표시
selected_code = st.session_state.get("selected_movie")

if selected_code:
    try:
        with st.spinner("영화 정보를 확인하는 중입니다..."):
            # 선택한 영화의 이름/개봉일을 현재 목록에서 먼저 찾는다.
            selected_date = st.session_state.get(
                "boxoffice_date", yesterday
            )
            movies = daily_boxoffice(
                selected_date.strftime("%Y%m%d"), str(key)
            )
            movie = next(
                (
                    item for item in movies
                    if str(item.get("movieCd", "")) == str(selected_code)
                ),
                None,
            )

            if movie is None:
                # 날짜 변경으로 목록에 없더라도 기본 조회일의 기록을 확인
                movies = daily_boxoffice(
                    yesterday.strftime("%Y%m%d"), str(key)
                )
                movie = next(
                    (
                        item for item in movies
                        if str(item.get("movieCd", "")) == str(selected_code)
                    ),
                    None,
                )

        if movie is None:
            st.warning(
                "선택한 영화의 일별 목록 정보를 찾지 못했습니다. "
                "목록으로 돌아가 다시 선택해 주세요."
            )
            if st.button("목록으로 돌아가기"):
                st.session_state["selected_movie"] = None
                st.rerun()
        else:
            render_movie_page(movie, str(key), selected_date)

    except Exception as exc:
        st.error(f"영화 정보를 불러오지 못했습니다: {exc}")
        if st.button("목록으로 돌아가기"):
            st.session_state["selected_movie"] = None
            st.rerun()

else:
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
                selected_date.strftime("%Y%m%d"), str(key)
            )
    except requests.exceptions.Timeout:
        st.error("KOBIS API 응답 시간이 초과되었습니다. 잠시 후 다시 시도하세요.")
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
            "데이터 출처: 영화진흥위원회(KOBIS) 오픈 API 및 KOBIS 웹페이지. "
            "포스터·줄거리 자동 수집은 웹페이지 구조와 접근 상태에 따라 실패할 수 있습니다."
        )
