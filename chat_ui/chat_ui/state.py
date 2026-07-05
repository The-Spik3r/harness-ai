import reflex as rx

WELCOME_MESSAGE = {
    "role": "assistant",
    "content": "Hi! Type a message below and press send.",
}


class ChatState(rx.State):
    """Holds chat messages, the input box's text, and the session's user_id.

    user_id is collected once per session via submit_user_id() (STORY-005)
    and reused by send() below; from STORY-006 onward it is also passed
    into run_query(...). send() only appends the user's message for now
    (presentation-only, per STORY-004); wiring to the shared query
    pipeline is STORY-006.
    """

    messages: list[dict[str, str]] = [WELCOME_MESSAGE]
    input_text: str = ""
    user_id: str = ""
    user_id_input: str = ""

    @rx.event
    def set_input_text(self, text: str):
        self.input_text = text

    @rx.event
    def set_user_id_input(self, text: str):
        self.user_id_input = text

    @rx.event
    def submit_user_id(self):
        text = self.user_id_input.strip()
        if not text:
            return
        self.user_id = text

    @rx.event
    def send(self):
        if not self.user_id.strip():
            return
        text = self.input_text.strip()
        if not text:
            return
        self.messages.append({"role": "user", "content": text})
        self.input_text = ""
