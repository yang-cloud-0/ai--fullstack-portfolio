"""Textual 终端界面与对话生命周期。"""

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Footer, Header, Input, Static

from .providers import Conversation, ProviderError


class ChatApp(App):
    TITLE = "MewCode"
    SUB_TITLE = "多协议终端对话"
    BINDINGS = [("ctrl+l", "clear_history", "清空"), ("ctrl+q", "quit", "退出")]
    CSS = """
    #transcript { padding: 1 2; }
    #status { color: $text-muted; height: auto; padding: 0 2; }
    Input { margin: 0 1; }
    """

    def __init__(self, conversation: Conversation):
        super().__init__()
        self.conversation = conversation
        self.busy = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(Static(id="transcript"), id="scroll")
        yield Static("等待输入", id="status")
        yield Input(placeholder="输入问题后回车", max_length=6000)
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def action_clear_history(self) -> None:
        if not self.busy:
            self.conversation.clear()
            self.query_one("#transcript", Static).update(Text(""))
            self.query_one("#status", Static).update("已清空会话")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        question = event.value.strip()
        if self.busy or not question:
            return
        self.busy = True
        event.input.value = ""
        event.input.disabled = True
        self.answer(question)

    @work
    async def answer(self, question: str) -> None:
        transcript = self.query_one("#transcript", Static)
        scroll = self.query_one("#scroll", VerticalScroll)
        status = self.query_one("#status", Static)
        previous = "\n\n".join(
            ("你　" if message["role"] == "user" else "AI　") + message["content"]
            for message in self.conversation.history
        )
        prefix = (previous + "\n\n" if previous else "") + f"你　{question}\n\nAI　"
        parts = []
        status.update("正在接收回复…")
        transcript.update(Text(prefix))
        try:
            async for piece in self.conversation.ask(question):
                parts.append(piece)
                transcript.update(Text(prefix + "".join(parts)))
                scroll.scroll_end(animate=False)
            status.update("回复完成")
        except ProviderError as error:
            transcript.update(Text(prefix + "".join(parts) + "\n\n［回复未保存］"))
            status.update(Text(str(error)))
        finally:
            self.busy = False
            field = self.query_one(Input)
            field.disabled = False
            field.focus()
