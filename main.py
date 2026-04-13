import asyncio
import os
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, Input, Button, ListView, ListItem, Label, Digits, Select, Log, TabbedContent, TabPane, Markdown
from textual.containers import Vertical, Horizontal, Container, ScrollableContainer
from textual.reactive import reactive
from openai import OpenAI
import anthropic
import google.generativeai as genai

# --- Dokumentations-Inhalt ---
HELP_DOCS = """
# 1-2-Apps Dokumentation

Willkommen bei **1-2-Apps**, deiner All-in-One TUI-Lösung.

## 1. Sticky Notes (Notizen)
Verwalte deine Aufgaben mit farblicher Priorisierung:
- **Rot (Hoch)**: Dringende Aufgaben, die sofortige Aufmerksamkeit erfordern.
- **Gelb (Mittel)**: Wichtige Aufgaben für den heutigen Tag.
- **Grün (Niedrig)**: Optionale Aufgaben oder Ideen.
- *Bedienung*: Text eingeben, Prioritäts-Button klicken. Die Notiz erscheint in der Liste.

## 2. Pomodoro Timer
Fokussiertes Arbeiten nach der Pomodoro-Technik:
- Standardmäßig auf **25 Minuten** eingestellt.
- **Start**: Beginnt den Countdown.
- **Stop**: Pausiert den Timer.
- **Reset**: Setzt den Timer auf 25:00 zurück.

## 3. Terminal Agent
KI-Unterstützung direkt in deinem Terminal:
- Unterstützt **Claude** (Anthropic), **ChatGPT** (OpenAI) und **Gemini** (Google).
- **API-Key**: Gib deinen persönlichen Key sicher im Passwort-Feld ein.
- **Modellauswahl**: Wähle deinen bevorzugten Anbieter aus dem Dropdown-Menü.
- **Interaktion**: Deine Anfragen und die Antworten der KI werden im Log-Bereich protokolliert.

## Tastenkürzel & Navigation
- Nutze die **Tab-Leiste** oben, um zwischen den Apps zu wechseln.
- Mit der **Tab-Taste** kannst du zwischen Eingabefeldern und Buttons springen.
- **Strg+C**: Beendet die Anwendung sicher.

---
No (c) 2026 ThatDev
"""

# --- Sticky Notes Sub-App ---
class NoteItem(ListItem):
    def __init__(self, content: str, priority: str):
        super().__init__()
        self.content = content
        self.priority = priority

    def compose(self) -> ComposeResult:
        color_map = {"Hoch": "red", "Mittel": "yellow", "Niedrig": "green"}
        color = color_map.get(self.priority, "white")
        yield Label(f"[{color}]●[/] {self.content} ({self.priority})")

class StickyNotesApp(Static):
    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Sticky Notes", classes="sub-title"),
            Horizontal(
                Input(placeholder="Neue Notiz...", id="note_input"),
                Button("Hoch", variant="error", id="btn_high"),
                Button("Mittel", variant="warning", id="btn_med"),
                Button("Niedrig", variant="success", id="btn_low"),
                classes="input-area"
            ),
            ListView(id="notes_list"),
            classes="sub-container"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        input_widget = self.query_one("#note_input", Input)
        content = input_widget.value.strip()
        if not content: return
        priority = {"btn_high": "Hoch", "btn_med": "Mittel", "btn_low": "Niedrig"}.get(event.button.id)
        if priority:
            self.query_one("#notes_list", ListView).append(NoteItem(content, priority))
            input_widget.value = ""
            input_widget.focus()

# --- Pomodoro Timer Sub-App ---
class PomodoroTimer(Static):
    time_left = reactive(25 * 60)
    is_running = reactive(False)
    
    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Pomodoro Timer", classes="sub-title"),
            Digits("25:00", id="timer_display"),
            Horizontal(
                Button("Start", variant="success", id="start_btn"),
                Button("Stop", variant="error", id="stop_btn"),
                Button("Reset", variant="primary", id="reset_btn"),
                classes="input-area"
            ),
            classes="sub-container"
        )

    def watch_time_left(self, time_left: int) -> None:
        minutes, seconds = divmod(time_left, 60)
        self.query_one("#timer_display", Digits).update(f"{minutes:02}:{seconds:02}")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "start_btn":
            if not self.is_running:
                self.is_running = True
                asyncio.create_task(self.run_timer())
        elif event.button.id == "stop_btn":
            self.is_running = False
        elif event.button.id == "reset_btn":
            self.is_running = False
            self.time_left = 25 * 60

    async def run_timer(self) -> None:
        while self.is_running and self.time_left > 0:
            await asyncio.sleep(1)
            if self.is_running: self.time_left -= 1

# --- Terminal Agent Sub-App ---
class TerminalAgent(Static):
    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Terminal Agent", classes="sub-title"),
            Horizontal(
                Select([("Claude", "claude"), ("ChatGPT", "chatgpt"), ("Gemini", "gemini")], prompt="Modell", id="model_select"),
                Input(placeholder="API Key...", id="api_key_input", password=True),
                classes="input-area"
            ),
            Log(id="agent_log"),
            Horizontal(
                Input(placeholder="Frage den Agenten...", id="agent_input"),
                Button("Senden", variant="primary", id="send_btn"),
                classes="input-area"
            ),
            classes="sub-container"
        )

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "send_btn": await self.process_query()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "agent_input": await self.process_query()

    async def process_query(self) -> None:
        input_w = self.query_one("#agent_input", Input)
        query, model, api_key = input_w.value.strip(), self.query_one("#model_select", Select).value, self.query_one("#api_key_input", Input).value
        log = self.query_one("#agent_log", Log)
        if not (query and model and api_key):
            log.write_line("[System] Fehler: Bitte Modell, Key und Anfrage prüfen.")
            return
        log.write_line(f"[User] {query}")
        input_w.value = ""
        try:
            resp = await self.call_api(model, api_key, query)
            log.write_line(f"[Agent] {resp}")
        except Exception as e: log.write_line(f"[System] API Fehler: {str(e)}")

    async def call_api(self, model: str, api_key: str, query: str) -> str:
        if model == "chatgpt":
            return OpenAI(api_key=api_key).chat.completions.create(model="gpt-4", messages=[{"role": "user", "content": query}]).choices[0].message.content
        elif model == "claude":
            return anthropic.Anthropic(api_key=api_key).messages.create(model="claude-3-opus-20240229", max_tokens=1024, messages=[{"role": "user", "content": query}]).content[0].text
        elif model == "gemini":
            genai.configure(api_key=api_key)
            return genai.GenerativeModel('gemini-pro').generate_content(query).text
        return "Unbekannt"

# --- Main App ---
class OneTwoApps(App):
    TITLE = "1-2-Apps"
    CSS = """
    .sub-title { text-align: center; width: 100%; background: $accent; color: white; padding: 1; margin-bottom: 1; }
    .sub-container { padding: 1; height: 100%; }
    .input-area { height: auto; margin-bottom: 1; }
    #notes_list, #agent_log { border: solid $accent; height: 1fr; margin-bottom: 1; }
    #timer_display { text-align: center; font-size: 5; margin: 2; }
    #footer_text { text-align: center; width: 100%; background: $surface; color: $text-muted; padding: 1; }
    #help_container { padding: 2; height: 100%; }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            with TabPane("Sticky Notes"): yield StickyNotesApp()
            with TabPane("Pomodoro"): yield PomodoroTimer()
            with TabPane("Agent"): yield TerminalAgent()
            with TabPane("Hilfe"):
                with ScrollableContainer(id="help_container"):
                    yield Markdown(HELP_DOCS)
        yield Static("No (c) 2026 ThatDev", id="footer_text")
        yield Footer()

if __name__ == "__main__":
    OneTwoApps().run()
