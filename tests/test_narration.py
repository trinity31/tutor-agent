"""narration.py 낭독용 텍스트 정제 파이프라인 테스트."""

from tutor_agent.narration import (
    build_narration_chunks,
    clean_text,
    group_chunks,
    split_sentences,
)

# --- 1. 한자 병기 제거 ---


def test_한자_병기_제거():
    assert clean_text("어떤 사술(邪術)의 유혹에도") == "어떤 사술의 유혹에도"


def test_한자_병기_여러_개_제거():
    text = "음양(陰陽)과 오행(五行)의 원리"
    assert clean_text(text) == "음양과 오행의 원리"


def test_독립_한자_어절_제거():
    assert clean_text("역이란 日月 두 글자를 모은 것") == "역이란 두 글자를 모은 것"


def test_괄호_안_한글은_보존():
    text = "부르디외(Bourdieu)의 문화자본(개념 정리)"
    assert clean_text(text) == text


# --- 2. 글리프·구두점·공백 정리 ---


def test_깨진_글리프_제어문자_제거():
    assert clean_text("명리\x01학�개론") == "명리학개론"


def test_가운뎃점을_쉼표로():
    assert clean_text("서울‧부산∙대구") == "서울, 부산, 대구"


def test_공백_정규화():
    assert clean_text("음양과   오행의 \t 원리") == "음양과 오행의 원리"


# --- 3. 문장 분리 + 목차·표 필터링 ---


def test_문장_분리():
    text = "역학을 공부한지 어느덧 20여 년! 결코 짧지 않은 세월이었습니다. 앞으로도 정진하겠습니다."
    assert split_sentences(text) == [
        "역학을 공부한지 어느덧 20여 년!",
        "결코 짧지 않은 세월이었습니다.",
        "앞으로도 정진하겠습니다.",
    ]


def test_목차_쪽번호_문장_제외():
    # 숫자 비율 15% 초과 → 제외
    text = "제1장 음양오행 12 15 27 33 45. 음양의 법칙은 우주 만물의 변화를 설명하는 근본 원리입니다."
    result = split_sentences(text)
    assert result == ["음양의 법칙은 우주 만물의 변화를 설명하는 근본 원리입니다."]


def test_표_내용_줄_제외():
    text = "갑 | 을 | 병 | 정\n음양의 법칙은 만물의 변화를 설명합니다."
    assert split_sentences(text) == ["음양의 법칙은 만물의 변화를 설명합니다."]


def test_한글_비율_낮은_줄_제외():
    text = "=== --- +++ 123 ***\n오행은 목화토금수의 다섯 기운을 말합니다."
    assert split_sentences(text) == ["오행은 목화토금수의 다섯 기운을 말합니다."]


def test_짧은_파편_제외():
    text = "3쪽. 음양의 법칙은 만물의 변화를 설명하는 원리입니다."
    assert split_sentences(text) == ["음양의 법칙은 만물의 변화를 설명하는 원리입니다."]


# --- 4. 청크 그룹핑 ---


def test_청크_최대_문장_수():
    sentences = [f"{i}번째 문장입니다." for i in range(10)]
    chunks = group_chunks(sentences, max_sentences=4, max_chars=500)
    assert [len(c) for c in chunks] == [4, 4, 2]


def test_청크_최대_글자_수():
    long_sentence = "가" * 300 + "."
    chunks = group_chunks([long_sentence, long_sentence], max_chars=500)
    # 두 문장을 합치면 500자 초과 → 각각 별도 청크
    assert len(chunks) == 2
    assert all(len(c) == 1 for c in chunks)


def test_청크_순서_보존():
    sentences = ["첫 번째 문장입니다.", "두 번째 문장입니다.", "세 번째 문장입니다."]
    chunks = group_chunks(sentences)
    flat = [s for c in chunks for s in c]
    assert flat == sentences


# --- 통합 ---


def test_전체_파이프라인():
    raw = (
        "제1장 역(易)의 의미 12 15 27\n"
        "역(易)은 음양(陰陽)의 변화를 담은 글자입니다. "
        "해와 달이 서로 의지하며 변화한다는 뜻입니다.\n"
        "갑 | 을 | 병\n"
        "도마뱀은 주위 상황에 따라 변화하며 적응합니다."
    )
    chunks = build_narration_chunks(raw)
    flat = [s for c in chunks for s in c]
    assert flat == [
        "역은 음양의 변화를 담은 글자입니다.",
        "해와 달이 서로 의지하며 변화한다는 뜻입니다.",
        "도마뱀은 주위 상황에 따라 변화하며 적응합니다.",
    ]
