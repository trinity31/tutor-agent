"""Streamlit UI — AI 과외 선생님 테스트 모드."""

import json
import os
import re
import tempfile
import uuid

import streamlit as st
import streamlit_authenticator as stauth
import yaml
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from tutor_agent.agents.graph import build_graph
from tutor_agent.file_search import (
    get_client as get_genai_client,
    get_or_create_store,
    load_manifest,
    save_manifest,
    upload_pdf,
    GEMINI_MODEL,
)

load_dotenv()

st.set_page_config(page_title="AI 과외 선생님", layout="wide")

# --- 인증 ---
with open("auth_config.yaml") as f:
    auth_config = yaml.safe_load(f)

authenticator = stauth.Authenticate(
    auth_config["credentials"],
    auth_config["cookie"]["name"],
    auth_config["cookie"]["key"],
    auth_config["cookie"]["expiry_days"],
)

authenticator.login()

if st.session_state["authentication_status"] is None:
    st.title("AI Tutor 24/7")
    st.info("로그인하거나 회원가입해 주세요.")

    with st.expander("회원가입"):
        reg_email = st.text_input("이메일", key="reg_email")
        reg_pw = st.text_input("비밀번호", type="password", key="reg_pw")
        reg_pw2 = st.text_input("비밀번호 확인", type="password", key="reg_pw2")

        if st.button("가입하기"):
            if not reg_email or not reg_pw:
                st.error("이메일과 비밀번호를 입력해 주세요.")
            elif reg_pw != reg_pw2:
                st.error("비밀번호가 일치하지 않습니다.")
            elif len(reg_pw) < 4:
                st.error("비밀번호는 4자 이상이어야 합니다.")
            else:
                username_key = reg_email.lower()
                if username_key in auth_config["credentials"]["usernames"]:
                    st.error("이미 등록된 이메일입니다.")
                else:
                    hashed = stauth.Hasher().hash(reg_pw)
                    auth_config["credentials"]["usernames"][username_key] = {
                        "name": reg_email,
                        "email": reg_email,
                        "password": hashed,
                    }
                    with open("auth_config.yaml", "w") as f:
                        yaml.dump(
                            auth_config, f, allow_unicode=True, default_flow_style=False
                        )
                    st.success("회원가입 완료! 이메일로 로그인해 주세요.")
    st.stop()

if st.session_state["authentication_status"] is False:
    st.error("아이디 또는 비밀번호가 올바르지 않습니다.")
    st.stop()

# --- 인증 완료 ---
username = st.session_state["username"]

# 그래프 초기화 (세션당 1회)
if "graph" not in st.session_state:
    checkpointer = MemorySaver()
    st.session_state["graph"] = build_graph(checkpointer=checkpointer)

if "thread_id" not in st.session_state:
    st.session_state["thread_id"] = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state["messages"] = []

# --- 사이드바 ---
with st.sidebar:
    st.markdown(f"**{st.session_state['name']}** 님 환영합니다!")
    authenticator.logout("로그아웃")

    st.divider()
    st.header("학습자료 업로드")

    uploaded_files = st.file_uploader(
        "PDF 파일을 업로드하세요",
        type=["pdf"],
        accept_multiple_files=True,
    )

    if uploaded_files and st.button("업로드 시작"):
        store_name = get_or_create_store(f"tutor-agent-{username}")
        existing = load_manifest(username)
        new_names = []

        for uploaded_file in uploaded_files:
            display_name = os.path.splitext(uploaded_file.name)[0]
            if display_name in existing:
                st.warning(f"이미 존재: {display_name}")
                continue

            with st.status(f"업로드 중: {display_name}...") as status:
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                    tmp.write(uploaded_file.getvalue())
                    tmp_path = tmp.name

                try:
                    upload_pdf(store_name, tmp_path, display_name)
                    new_names.append(display_name)
                    status.update(label=f"완료: {display_name}", state="complete")
                finally:
                    os.unlink(tmp_path)

        if new_names:
            save_manifest(existing + new_names, username)
            # manifest 캐시 무효화
            from tutor_agent.file_search import _manifest_cache

            _manifest_cache.pop(username, None)
            st.success(f"{len(new_names)}개 파일 업로드 완료!")
            st.rerun()

    # 업로드된 파일 목록
    st.divider()
    st.subheader("업로드된 자료")
    manifest = load_manifest(username)
    if manifest:
        for name in manifest:
            st.caption(f"- {name}")
    else:
        st.caption("아직 업로드된 자료가 없습니다.")

    # 새 대화 시작
    st.divider()
    if st.button("새 대화 시작"):
        st.session_state["messages"] = []
        st.session_state["thread_id"] = str(uuid.uuid4())
        for key in ["quiz_data", "quiz_index", "quiz_answers"]:
            st.session_state.pop(key, None)
        st.rerun()

# --- 퀴즈 헬퍼 ---


def _try_parse_quiz(text: str) -> dict | None:
    """AI 응답에서 퀴즈 JSON을 추출합니다."""
    # JSON 코드블록 안의 내용 추출
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    json_str = m.group(1) if m else text
    try:
        data = json.loads(json_str)
        if isinstance(data, dict) and "questions" in data:
            return data
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def _extract_ai_content(result: dict) -> str:
    """그래프 결과에서 AI 텍스트 응답을 추출합니다."""
    from langchain_core.messages import AIMessage

    for msg in reversed(result["messages"]):
        if not isinstance(msg, AIMessage):
            continue
        content = msg.content
        if not content:
            continue
        if isinstance(content, list):
            text_parts = [
                p["text"] if isinstance(p, dict) else str(p)
                for p in content
                if (isinstance(p, dict) and p.get("type") == "text")
                or isinstance(p, str)
            ]
            content = "\n".join(text_parts)
        if isinstance(content, str) and content.strip():
            return content.strip()
    return ""


def _render_quiz_question():
    """현재 퀴즈 문제를 렌더링합니다."""
    quiz = st.session_state["quiz_data"]
    questions = quiz["questions"]
    idx = st.session_state["quiz_index"]
    answers = st.session_state["quiz_answers"]

    if idx >= len(questions):
        # 퀴즈 완료 — 결과 표시
        correct = sum(1 for a in answers if a["correct"])
        total = len(answers)

        st.success(f"퀴즈 완료! {correct}/{total} 정답")
        st.progress(correct / total)

        for i, a in enumerate(answers):
            icon = "O" if a["correct"] else "X"
            with st.expander(f"{icon} Q{i + 1}. {a['question']}"):
                st.write(f"**내 답:** {a['selected']}")
                st.write(f"**정답:** {a['answer']}")
                if a.get("explanation"):
                    st.info(a["explanation"])
        return

    q = questions[idx]
    total = len(questions)
    q_num = idx + 1

    st.markdown(f"### Q{q_num} / {total}")
    st.markdown(f"**{q.get('question', '')}**")

    options = q.get("options", [])
    q_type = q.get("type", "")

    if not options and "o/x" in q_type.lower():
        options = ["O", "X"]

    for i, opt in enumerate(options):
        if st.button(opt, key=f"quiz_opt_{idx}_{i}", use_container_width=True):
            correct_answer = q.get("answer", q.get("correct", ""))
            is_correct = opt == correct_answer

            answers.append(
                {
                    "question": q.get("question", ""),
                    "selected": opt,
                    "answer": correct_answer,
                    "correct": is_correct,
                    "explanation": q.get("explanation", ""),
                }
            )

            if is_correct:
                st.toast("정답입니다!", icon="\u2705")
            else:
                st.toast(f"오답! 정답: {correct_answer}", icon="\u274c")

            st.session_state["quiz_index"] = idx + 1
            st.rerun()


# --- 예시 메시지 생성 ---


@st.cache_data(ttl=3600)
def _generate_example_messages(file_list: tuple[str, ...]) -> list[dict]:
    """업로드된 파일 목록을 참고하여 에이전트별 예시 메시지를 LLM으로 생성합니다."""
    if not file_list:
        return []

    sample = list(file_list[:10])
    file_names = "\n".join(f"- {f}" for f in sample)

    client = get_genai_client()
    from google.genai import types

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=(
            f"아래는 학생이 업로드한 강의 자료 파일명 목록입니다:\n{file_names}\n\n"
            "이 자료를 기반으로 학생이 AI 과외 선생님에게 보낼 만한 예시 메시지를 3개 생성해주세요.\n"
            "각 메시지는 서로 다른 에이전트를 활성화하도록 작성하세요:\n"
            '1. tutor: 주제에 대한 설명/학습 요청 (예: "~에 대해 쉽게 설명해 줘")\n'
            '2. qna: 특정 용어/개념의 짧은 질문 (예: "~가 뭐야?")\n'
            '3. quiz: 퀴즈 요청 (예: "~에 대한 퀴즈를 내줘")\n\n'
            "반드시 아래 JSON 형식으로만 응답하세요:\n"
            '[{"type":"tutor","message":"..."},{"type":"qna","message":"..."},{"type":"quiz","message":"..."}]'
        ),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )
    try:
        return json.loads(response.text)
    except (json.JSONDecodeError, ValueError):
        return []


# --- 메인: 채팅 ---
st.title("AI Tutor 24/7")

# 온보딩: 대화가 없을 때 사용법 + 예시 버튼 표시
if not st.session_state["messages"] and "quiz_data" not in st.session_state:
    st.markdown(
        """
        안녕하세요! AI 과외 선생님입니다. 아래와 같은 기능을 제공합니다:

        - **1:1 과외** — 주제에 대해 쉽게 설명하고, 질문하며 학습을 도와줍니다
        - **Q&A** — 특정 용어나 개념에 대한 질문에 간단히 답변합니다
        - **퀴즈** — 학습 자료 기반 퀴즈를 생성하고 풀 수 있습니다

        사이드바의 **PDF 학습자료**를 바탕으로, 아래 예시를 참고하여 대화를 시작해 보세요!
        """
    )

    manifest = load_manifest(username)
    if manifest:
        examples = _generate_example_messages(tuple(manifest))
        if examples:
            type_icons = {"tutor": "1:1 과외", "qna": "Q&A", "quiz": "퀴즈"}
            cols = st.columns(len(examples))
            for col, ex in zip(cols, examples):
                with col:
                    label = type_icons.get(ex.get("type", ""), "")
                    if st.button(
                        ex["message"],
                        key=f"example_{ex.get('type', '')}",
                        use_container_width=True,
                        help=label,
                    ):
                        st.session_state["_example_input"] = ex["message"]
                        st.rerun()
    else:
        st.info("왼쪽 사이드바에서 PDF 학습자료를 먼저 업로드해 주세요.")

# 히스토리 표시
for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        if msg.get("type") == "quiz":
            st.markdown("퀴즈가 생성되었습니다!")
        else:
            st.markdown(msg["content"])

# 진행 중인 퀴즈가 있으면 표시
if "quiz_data" in st.session_state:
    with st.chat_message("assistant"):
        _render_quiz_question()

# 사용자 입력 (예시 버튼 클릭 또는 직접 입력)
user_input = st.session_state.pop("_example_input", None) or st.chat_input(
    "메시지를 입력하세요"
)
if user_input:
    st.session_state["messages"].append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # 에이전트 호출
    with st.chat_message("assistant"):
        agent_labels = {
            "supervisor_agent": "Supervisor",
            "search_agent": "자료 검색",
            "quiz_agent": "퀴즈 생성",
            "qna_agent": "Q&A 답변",
            "tutor_agent": "1:1 과외",
        }

        with st.status("잠시만 기다려 주세요...", expanded=True) as status:
            config = {
                "configurable": {
                    "thread_id": f"{username}_{st.session_state['thread_id']}",
                }
            }
            user_store = get_or_create_store(f"tutor-agent-{username}")

            # 스트리밍으로 에이전트 실행
            for event in st.session_state["graph"].stream(
                {
                    "messages": [HumanMessage(content=user_input)],
                    "user_id": username,
                    "store_name": user_store,
                },
                config=config,
                stream_mode="updates",
            ):
                for node_name in event:
                    if node_name != "supervisor_agent":
                        label = agent_labels.get(node_name, node_name)
                        status.update(label=f"{label} 에이전트 답변 중...")

            # 최종 상태 가져오기
            snapshot = st.session_state["graph"].get_state(config)
            final_values = snapshot.values
            current_agent = final_values.get("current_agent", "")
            agent_label = agent_labels.get(current_agent, current_agent)
            status.update(
                label=f"{agent_label} 에이전트의 답변입니다.", state="complete"
            )

        ai_content = _extract_ai_content(final_values)
        if not ai_content:
            ai_content = "죄송합니다. 응답을 생성하지 못했습니다."

        # 퀴즈 JSON 감지 → 인터랙티브 모드 전환
        quiz_data = _try_parse_quiz(ai_content)
        if quiz_data and quiz_data.get("questions"):
            st.session_state["quiz_data"] = quiz_data
            st.session_state["quiz_index"] = 0
            st.session_state["quiz_answers"] = []
            st.session_state["messages"].append(
                {"role": "assistant", "content": ai_content, "type": "quiz"}
            )
            st.markdown("퀴즈가 생성되었습니다!")
            st.rerun()
        else:
            st.markdown(ai_content)
            st.session_state["messages"].append(
                {"role": "assistant", "content": ai_content}
            )
