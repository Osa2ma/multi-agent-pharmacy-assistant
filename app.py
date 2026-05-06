import os
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import requests
import streamlit as st


WEBHOOK_ENV_VAR = "WEBHOOK_URL"
DEFAULT_WEBHOOK_URL = "https://partly-overcast-lilly.ngrok-free.dev/webhook/pharmacy-query"


@dataclass
class UserContext:
    age: Optional[int]
    role: str
    known_conditions: List[str]
    current_medications: List[str]


def get_webhook_url() -> str:
    """Resolve the webhook URL from environment or default."""
    return os.environ.get(WEBHOOK_ENV_VAR, DEFAULT_WEBHOOK_URL)


def parse_multiline_list(text: str) -> List[str]:
    """Parse newline-delimited text into a clean list."""
    items = [line.strip() for line in text.splitlines() if line.strip()]
    return items


def ensure_session_id() -> str:
    """Create or reuse a session_id stored in Streamlit session state."""
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
    return st.session_state.session_id


def build_user_context(role: str, age: Optional[int], meds_text: str, conds_text: str) -> UserContext:
    """Build a UserContext from form inputs."""
    return UserContext(
        age=age,
        role=role,
        known_conditions=parse_multiline_list(conds_text),
        current_medications=parse_multiline_list(meds_text),
    )


def build_payload(session_id: str, user_query: str, ctx: UserContext) -> Dict[str, Any]:
    """Build the JSON payload for the webhook request."""
    return {
        "session_id": session_id,
        "user_query": user_query,
        "user_context": {
            "age": ctx.age,
            "role": ctx.role,
            "known_conditions": ctx.known_conditions,
            "current_medications": ctx.current_medications,
        },
    }


def safe_get_color(confidence: Optional[str]) -> Tuple[str, str]:
    """Map confidence to label and color for display."""
    if confidence == "high":
        return "High", "green"
    if confidence == "medium":
        return "Medium", "orange"
    if confidence == "low":
        return "Low", "red"
    return "Unknown", "gray"


def safety_icon(verdict: Optional[str]) -> str:
    """Map safety verdict to an icon."""
    if verdict == "approve":
        return "✅"
    if verdict == "modify":
        return "⚠️"
    if verdict == "block":
        return "❌"
    return ""


def call_webhook(url: str, payload: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Call the webhook and return response JSON or an error message."""
    try:
        response = requests.post(url, json=payload, timeout=60)
    except requests.RequestException as exc:
        return None, f"Webhook unreachable at {url}. Error: {exc}"

    if response.status_code != 200:
        return None, f"Webhook error {response.status_code} from {url}: {response.text}"

    try:
        return response.json(), None
    except ValueError:
        return None, f"Webhook returned non-JSON response from {url}."


def init_state() -> None:
    """Initialize chat history in session state."""
    if "messages" not in st.session_state:
        st.session_state.messages = []


def add_example_query(query: str) -> None:
    """Set the selected example query into session state."""
    st.session_state.example_query = query


def render_response_details(data: Dict[str, Any]) -> None:
    """Render response details section."""
    with st.expander("Response details", expanded=False):
        key_takeaway = data.get("key_takeaway")
        confidence = data.get("confidence")
        safety_verdict = data.get("safety_verdict")
        safety_issues = data.get("safety_issues", [])
        rag_sources = data.get("rag_sources", [])
        disclaimer = data.get("disclaimer")

        if key_takeaway:
            st.markdown(f"**Key takeaway:** {key_takeaway}")

        confidence_label, confidence_color = safe_get_color(confidence)
        st.markdown(
            f"**Confidence:** :{confidence_color}[{confidence_label}]"
        )

        if safety_verdict:
            icon = safety_icon(safety_verdict)
            st.markdown(f"**Safety verdict:** {icon} {safety_verdict}")

        if safety_issues:
            st.markdown("**Safety issues:**")
            for issue in safety_issues:
                severity = issue.get("severity", "unknown")
                description = issue.get("description", "")
                st.write(f"- {severity}: {description}")

        if rag_sources:
            st.markdown("**Sources cited:**")
            for source in rag_sources:
                drug = source.get("drug_name", "")
                section = source.get("section", "")
                if drug or section:
                    st.write(f"- {drug} ({section})")

        if disclaimer:
            st.markdown(f"**Disclaimer:** {disclaimer}")


def render_special_containers(data: Dict[str, Any], response_text: str) -> None:
    """Render response with special containers for refused or crisis responses."""
    status = data.get("status")
    if data.get("is_crisis_response") or status == "crisis_resources":
        st.error(response_text)
        return
    if status in {"refused", "out_of_scope"}:
        st.warning(response_text)
        return
    st.write(response_text)


def main() -> None:
    """Run the Streamlit chat application."""
    st.set_page_config(page_title="💊 Pharmacy Assistant", page_icon="💊", layout="centered")
    st.title("💊 Pharmacy Assistant")
    st.caption("Ask a medication-related question and get a safety-aware response.")

    init_state()
    session_id = ensure_session_id()

    with st.sidebar:
        st.header("User context")
        role = st.selectbox("Role", ["patient", "pharmacist", "physician"], index=0)
        age = st.number_input("Age", min_value=0, max_value=120, value=0, step=1)
        meds_text = st.text_area("Current medications (one per line)", height=100)
        conds_text = st.text_area("Known conditions (one per line)", height=100)

        st.subheader("Example queries")
        example_queries = [
            "What is metformin used for?",
            "Can I take ibuprofen with my lisinopril?",
            "How much paracetamol can I give my 5-year-old child?",
            "I accidentally took two doses of my warfarin this morning, what should I do?",
            "Is it safe to take cetirizine with alcohol?",
        ]
        for query in example_queries:
            if st.button(query, use_container_width=True):
                add_example_query(query)

        if st.button("Reset chat", type="secondary", use_container_width=True):
            st.session_state.messages = []
            st.session_state.pop("example_query", None)

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if message["role"] == "assistant" and message.get("details"):
                details = message["details"]
                response_text = message["content"]
                if details.get("recommend_professional_consultation"):
                    st.info("This answer recommends consulting a healthcare professional.")
                render_special_containers(details, response_text)
                render_response_details(details)
            else:
                st.write(message["content"])

    default_input = st.session_state.pop("example_query", "")
    if default_input:
        st.session_state["chat_input"] = default_input
    prompt = st.chat_input("Type your question", key="chat_input")

    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)

        user_ctx = build_user_context(role, int(age), meds_text, conds_text)
        payload = build_payload(session_id, prompt, user_ctx)
        webhook_url = get_webhook_url()

        with st.chat_message("assistant"):
            with st.spinner("Contacting pharmacy workflow..."):
                data, error = call_webhook(webhook_url, payload)

            if error:
                st.error(error)
                st.session_state.messages.append({"role": "assistant", "content": error})
                return

            response_text = data.get("response", "") if data else ""

            if data.get("recommend_professional_consultation"):
                st.info("This answer recommends consulting a healthcare professional.")

            render_special_containers(data, response_text)

            render_response_details(data)

            st.session_state.messages.append(
                {"role": "assistant", "content": response_text, "details": data}
            )


if __name__ == "__main__":
    main()
