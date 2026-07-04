"""narration.py 낭독용 텍스트 정제 파이프라인 테스트."""

from tutor_agent.narration import (
    build_narration_chunks,
    build_narration_chunks_paged,
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


def test_호환_한자_영역_제거():
    # 宅(U+FA04), 李(U+F9E1) — CJK 호환 한자 영역
    assert clean_text("복택 宅 3) 점에 의한") == "복택 3) 점에 의한"
    assert clean_text("李 북대 대학원") == "북대 대학원"


def test_불릿_기호는_문장_경계로():
    # 슬라이드 글머리표는 제목·항목 구분자 → 마침표로 바꿔 병합 방지
    assert clean_text("풍수의 명칭￭ 풍수 라는") == "풍수의 명칭. 풍수 라는"
    assert clean_text("ㆍ 풍수지리설의 특징") == "풍수지리설의 특징"


# --- 2. 글리프·구두점·공백 정리 ---


def test_깨진_글리프_제어문자_제거():
    assert clean_text("명리\x01학�개론") == "명리학개론"


def test_가운뎃점을_쉼표로():
    assert clean_text("서울‧부산∙대구") == "서울, 부산, 대구"


def test_공백_정규화():
    assert clean_text("음양과   오행의 \t 원리") == "음양과 오행의 원리"


# --- 2-1. 고아 구두점 정리 (슬라이드형 PDF 추출 잔여물) ---


def test_고아_따옴표_어절_제거():
    # 따옴표가 본문과 분리되어 추출된 경우 (내용을 잃은 구두점)
    assert clean_text("풍수지리 와 풍수' ' ' '") == "풍수지리 와 풍수"


def test_고아_쉼표_연속_제거():
    assert clean_text("를 의미한다, , , , .") == "를 의미한다."


def test_고아_구두점_문장_경계_보존():
    # 종결부호가 섞인 고아 구두점은 마침표로 축약 → 문장 분리 유지
    text = "문헌에 등장한다, . 복택 점에 의한 길흉판단"
    assert clean_text(text) == "문헌에 등장한다. 복택 점에 의한 길흉판단"


def test_고아_구두점_문장_중간_제거():
    text = "풍수 에 지리 라는 단어가 붙은 것, ' ' ' ' 으로 판단된다."
    assert clean_text(text) == "풍수 에 지리 라는 단어가 붙은 것, 으로 판단된다."


def test_인용부호_제거_영어_아포스트로피_보존():
    # 인용부호는 낭독에 불필요하므로 제거 (내용은 보존)
    assert clean_text("'인용문'은 내용만 유지") == "인용문은 내용만 유지"
    assert clean_text("It doesn't matter") == "It doesn't matter"


def test_분리된_문장부호_붙이기():
    assert clean_text("길흉을 판단한다 .") == "길흉을 판단한다."


# --- 2-2. 단어 끝에 붙은 번호·각주 참조 제거 ---


def test_제목_뒤로_밀린_번호_제거():
    # "3) 명과 풍수의 관계"가 "명과 풍수의 관계3)"로 추출되는 경우
    assert clean_text("명 과 풍수 의 관계3) 천부적이며") == "명 과 풍수 의 관계 천부적이며"
    assert clean_text("풍수용어1. 풍수를 지칭하는") == "풍수용어. 풍수를 지칭하는"


def test_각주_참조_제거():
    assert clean_text("전문가1)를 말한다.") == "전문가를 말한다."
    assert clean_text("발견되지 않는다.2) 풍수 라는") == "발견되지 않는다. 풍수 라는"


def test_정상_순서_목록_번호는_보존():
    # 제목 줄은 마침표를 붙여 독립 문장으로 유지
    assert clean_text("3) 명과 풍수의 관계") == "3) 명과 풍수의 관계."
    assert clean_text("연도 표기 (1983) 보존") == "연도 표기 (1983) 보존"


# --- 2-3. 줄 끝으로 밀린 제목 번호 복원 ---


def test_밀린_제목_번호_복원():
    # "3) 명과 풍수의 관계"가 "명과 풍수의 관계3)"로 추출되는 경우 번호를 앞으로
    assert clean_text("명 과 풍수 의 관계3)") == "3) 명 과 풍수 의 관계."
    assert clean_text("풍수를 지칭하는 용어의 다양성1)") == "1) 풍수를 지칭하는 용어의 다양성."
    assert clean_text("풍수용어1.") == "1. 풍수용어."


def test_제목이_본문과_분리된_문장으로_유지():
    text = "명 과 풍수 의 관계3)\n인간의 운명은 타고난 것과 노력에 의해서 결정된다는 것이 일반적 견해이다."
    assert split_sentences(clean_text(text)) == [
        "3) 명 과 풍수 의 관계.",
        "인간의 운명은 타고난 것과 노력에 의해서 결정된다는 것이 일반적 견해이다.",
    ]


def test_종결부호가_있는_줄은_복원하지_않음():
    # 각주 참조("않는다.2)")가 줄 끝에 있어도 본문 문장이면 번호만 제거
    assert clean_text("사용된 근거가 발견되지 않는다.2)") == "사용된 근거가 발견되지 않는다."


def test_제목_직전_줄에_문장_경계_부여():
    # 종결부호 없는 소제목이 뒤따르는 번호 제목과 병합되지 않아야 함
    text = "설 론 학 의 구분\n명 과 풍수 의 관계3)"
    assert clean_text(text) == "설 론 학 의 구분.\n3) 명 과 풍수 의 관계."


def test_번호_제목은_새_청크_시작():
    sentences = [
        "풍수학 이 될 수 있는 것이다.",
        "3) 명 과 풍수 의 관계.",
        "인간의 운명은 결정된다는 것이 일반적 견해이다.",
    ]
    chunks = group_chunks(sentences)
    assert chunks == [
        ["풍수학 이 될 수 있는 것이다."],
        ["3) 명 과 풍수 의 관계.", "인간의 운명은 결정된다는 것이 일반적 견해이다."],
    ]


def test_URL_제거():
    assert clean_text("자세한 내용은 www.wdu.ac.kr 참고") == "자세한 내용은 참고"
    assert clean_text("출처: https://example.com/a?b=1 입니다") == "출처: 입니다"


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


# --- 페이지 매핑 (PDF 뷰 자동 넘김 근거) ---


def test_페이지_청크에_시작_페이지_기록():
    pages = [
        (3, "삼 페이지의 첫 문장입니다. 삼 페이지의 둘째 문장입니다."),
        (4, "사 페이지의 문장입니다."),
    ]
    chunks = build_narration_chunks_paged(pages)
    assert chunks[0]["page"] == 3
    assert chunks[0]["sentences"][0] == "삼 페이지의 첫 문장입니다."
    # 모든 문장이 순서대로 보존
    flat = [s for c in chunks for s in c["sentences"]]
    assert flat == [
        "삼 페이지의 첫 문장입니다.",
        "삼 페이지의 둘째 문장입니다.",
        "사 페이지의 문장입니다.",
    ]


def test_페이지_경계를_넘는_청크는_첫_문장_페이지():
    # 문장 5개 → 4+1로 청크 분할, 페이지 경계와 무관하게 첫 문장의 페이지 기록
    pages = [
        (1, "일 페이지 첫 문장입니다. 일 페이지 둘째 문장입니다. 일 페이지 셋째 문장입니다."),
        (2, "이 페이지 첫 문장입니다. 이 페이지 둘째 문장입니다."),
    ]
    chunks = build_narration_chunks_paged(pages)
    assert [c["page"] for c in chunks] == [1, 2]
    assert [len(c["sentences"]) for c in chunks] == [4, 1]


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
