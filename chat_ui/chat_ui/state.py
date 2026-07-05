import reflex as rx

WELCOME_MESSAGE = {
    "role": "assistant",
    "content": "Hi! Type a message below and press send.",
}


class ChatState(rx.State):
    """Holds chat messages and the input box's text.

    send() only appends the user's message for now (presentation-only,
    per STORY-004); wiring to the shared query pipeline is STORY-006.
    """

    messages: list[dict[str, str]] = [WELCOME_MESSAGE]
    input_text: str = ""

    @rx.event
    def set_input_text(self, text: str):
        self.input_text = text

    @rx.event
    def send(self):
        text = self.input_text.strip()
        if not text:
            return
        self.messages.append({"role": "user", "content": text})
        self.input_text = ""
