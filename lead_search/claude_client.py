"""Claude API helpers: web-research calls and structured extraction."""

import anthropic

WEB_TOOLS = [
    {"type": "web_search_20260209", "name": "web_search"},
    {"type": "web_fetch_20260209", "name": "web_fetch"},
]
MAX_CONTINUATIONS = 5


class RefusalError(RuntimeError):
    """Raised when the model declines a request (stop_reason == 'refusal')."""


class ClaudeRunner:
    def __init__(self, model: str = "claude-opus-5"):
        self.client = anthropic.Anthropic()
        self.model = model

    def research(self, prompt: str) -> str:
        """Run a web-search-enabled research call and return the final text.

        Streams (research turns can run long) and resumes pause_turn, which the
        server emits when a server-tool loop hits its iteration limit.
        """
        messages = [{"role": "user", "content": prompt}]
        response = None
        for _ in range(MAX_CONTINUATIONS):
            with self.client.messages.stream(
                model=self.model,
                max_tokens=64000,
                tools=WEB_TOOLS,
                messages=messages,
            ) as stream:
                response = stream.get_final_message()
            if response.stop_reason != "pause_turn":
                break
            messages = [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": response.content},
            ]
        if response.stop_reason == "refusal":
            raise RefusalError("Model declined the research request.")
        return "".join(b.text for b in response.content if b.type == "text")

    def extract(self, prompt: str, schema_model):
        """Run a no-tools call whose response is validated against a Pydantic model."""
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=16000,
            messages=[{"role": "user", "content": prompt}],
            output_format=schema_model,
        )
        if response.stop_reason == "refusal":
            raise RefusalError("Model declined the extraction request.")
        return response.parsed_output

    def research_and_extract(self, prompt: str, schema_model):
        """Research with web tools, then parse the findings into a schema."""
        findings = self.research(prompt)
        return self.extract(
            "Convert the following research findings into the requested structured "
            "format. Do not invent information that is not present in the findings; "
            "leave optional fields empty when the findings do not support them.\n\n"
            f"<findings>\n{findings}\n</findings>",
            schema_model,
        )
