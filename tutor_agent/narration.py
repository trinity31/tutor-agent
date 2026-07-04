"""낭독용 텍스트 정제 파이프라인 — PDF 텍스트 → 낭독 문장/청크.

tts-demo에서 검증된 규칙을 순수 함수로 구현합니다:
1. 한자 병기 제거 (사술(邪術) → 사술) + 잔여 독립 한자 어절 제거
2. 깨진 글리프·제어문자 제거, 특수 구두점 정리, 공백 정규화
3. 문장 분리 후 숫자 비율 15% 초과 문장(목차·쪽번호)과 표 내용 제외
4. 문장 리스트를 TTS 1회 호출 단위 청크로 그룹핑 (2~4문장, ~500자)
"""

import re

# 한자 병기: 한글(한자) → 한글
_HANJA_PAREN_RE = re.compile(r"([가-힣]+)\(([一-鿿]+)\)")
# 독립 한자 어절: 한자(와 구두점)로만 이루어진 어절
_HANJA_WORD_RE = re.compile(r"(?<![가-힣A-Za-z0-9])[一-鿿]+(?![가-힣A-Za-z0-9])")
# 제어문자(탭·개행 제외), 대체문자, 사용자 영역(깨진 글리프)
_BROKEN_GLYPH_RE = re.compile("[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f\\x7f\\ufffd\\ue000-\\uf8ff]")
# 가운뎃점 계열 특수 구두점 → 쉼표로 (낭독 시 자연스러운 끊어읽기)
_MIDDLE_DOT_RE = re.compile(r"\s*[‧∙・·•]\s*")
# 문장 종결(., !, ?, 다.) 뒤에서 분리
_SENTENCE_END_RE = re.compile(r"(?<=[.!?…])\s+")

# 청크 그룹핑 기본값: 청크당 2~4문장, ~500자 (TTS 1회 호출 단위)
MAX_CHUNK_SENTENCES = 4
MAX_CHUNK_CHARS = 500


def clean_text(text: str) -> str:
    """PDF 추출 텍스트에서 낭독에 방해되는 요소를 제거합니다."""
    text = _HANJA_PAREN_RE.sub(r"\1", text)
    text = _HANJA_WORD_RE.sub(" ", text)
    text = _BROKEN_GLYPH_RE.sub("", text)
    text = _MIDDLE_DOT_RE.sub(", ", text)
    # 빈 괄호(한자만 들어있던 괄호의 잔여물) 제거
    text = re.sub(r"\(\s*\)", "", text)
    # 줄 단위 구조는 유지하고 줄 안의 공백만 정규화
    lines = [re.sub(r"[ \t 　]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(lines)


def _digit_ratio(sentence: str) -> float:
    """공백 제외 문자 중 숫자의 비율."""
    chars = sentence.replace(" ", "")
    if not chars:
        return 0.0
    return sum(c.isdigit() for c in chars) / len(chars)


def _is_table_line(line: str) -> bool:
    """표로 추정되는 줄인지 판별합니다 (구분자·한글 비율 휴리스틱)."""
    if "|" in line or "\t" in line:
        return True
    chars = line.replace(" ", "")
    if not chars:
        return False
    hangul = sum("가" <= c <= "힣" for c in chars)
    # 한글이 거의 없는 줄(숫자·기호 나열)은 표/도식으로 간주
    return hangul / len(chars) < 0.3


def split_sentences(text: str) -> list[str]:
    """정제된 텍스트를 낭독 문장 리스트로 분리합니다.

    목차·쪽번호(숫자 비율 15% 초과)와 표 내용은 제외합니다.
    """
    # 표·목차 줄을 먼저 걸러낸 뒤, 남은 줄을 이어붙여 문장 단위로 분리.
    # 문장부호 없는 목차 줄은 다음 문장과 병합되므로 줄 단위에서 먼저 거른다.
    def _is_toc_line(line: str) -> bool:
        return _digit_ratio(line) > 0.15 and not re.search(r"[.!?…]", line)

    prose = " ".join(
        line
        for line in text.split("\n")
        if line.strip() and not _is_table_line(line) and not _is_toc_line(line)
    )
    prose = re.sub(r"\s+", " ", prose).strip()

    sentences = []
    for sent in _SENTENCE_END_RE.split(prose):
        sent = sent.strip()
        if len(sent) < 5:  # 쪽 머리글 등 짧은 파편 제외
            continue
        if _digit_ratio(sent) > 0.15:  # 목차·쪽번호
            continue
        sentences.append(sent)
    return sentences


def group_chunks(
    sentences: list[str],
    max_sentences: int = MAX_CHUNK_SENTENCES,
    max_chars: int = MAX_CHUNK_CHARS,
) -> list[list[str]]:
    """문장 리스트를 TTS 1회 호출 단위 청크로 그룹핑합니다."""
    chunks: list[list[str]] = []
    current: list[str] = []
    current_len = 0

    for sent in sentences:
        if current and (
            len(current) >= max_sentences or current_len + len(sent) > max_chars
        ):
            chunks.append(current)
            current = []
            current_len = 0
        current.append(sent)
        current_len += len(sent)

    if current:
        chunks.append(current)
    return chunks


def build_narration_chunks(raw_text: str) -> list[list[str]]:
    """PDF 원문 텍스트에서 낭독 청크(문장 리스트의 리스트)를 생성합니다."""
    return group_chunks(split_sentences(clean_text(raw_text)))
