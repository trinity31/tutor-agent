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
    get_or_create_store,
    load_manifest,
    save_manifest,
    upload_pdf,
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
        store_name = get_or_create_store(f"tutor-{username}")
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


# --- 메인: 채팅 ---
st.title("AI Tutor 24/7")

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

# 사용자 입력
if user_input := st.chat_input("메시지를 입력하세요"):
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
            user_store = get_or_create_store(f"tutor-{username}")

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
            status.update(label=f"{agent_label} 에이전트의 답변입니다.", state="complete")

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
