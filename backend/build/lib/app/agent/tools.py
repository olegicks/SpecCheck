"""Tools the agent can call, their JSON schemas, and their execution.

All tool results are plain strings. Anything that comes from the PDF is wrapped by
:func:`app.agent.prompts.wrap_document` so it is clearly marked as untrusted data.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from app.agent.prompts import looks_like_injection, wrap_document
from app.agent.schemas import AgentEvent, EventType
from app.core.requirements import Finding, Requirement
from app.core.verification import VerificationResult, verify_quote
from app.datasheets.pdf import ParsedPdf
from app.datasheets.search import DatasheetIndex

MAX_PAGE_CHARS = 6000
MAX_EXTRACT_PAGES = 3
SNIPPET_CHARS = 350


def _fn(name: str, description: str, properties: dict, required: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


TOOL_SCHEMAS: list[dict[str, Any]] = [
    _fn(
        "search_datasheet",
        "Keyword (BM25) search over the datasheet. Returns pages with short snippets.",
        {
            "query": {"type": "string", "description": "Technical keywords, e.g. 'VDDIO supply'"},
            "top_k": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
        },
        ["query"],
    ),
    _fn(
        "get_page",
        "Return the full extracted text of one page.",
        {"page_number": {"type": "integer", "minimum": 1}},
        ["page_number"],
    ),
    _fn(
        "extract_parameter",
        "Return a requirement's definition together with the text of up to 3 pages, "
        "ready for extracting the value. Follow up with submit_finding.",
        {
            "requirement_id": {"type": "string"},
            "page_numbers": {
                "type": "array",
                "items": {"type": "integer", "minimum": 1},
                "minItems": 1,
                "maxItems": MAX_EXTRACT_PAGES,
            },
        },
        ["requirement_id", "page_numbers"],
    ),
    _fn(
        "submit_finding",
        "Submit the extracted value for one requirement with page and verbatim quote. "
        "The quote is verified automatically against the page text.",
        {
            "requirement_id": {"type": "string"},
            "value": {
                "description": "As printed: number, 'min to max', integer count, true/false, "
                "or null if not found",
                "type": ["number", "string", "boolean", "null"],
            },
            "unit": {"type": ["string", "null"]},
            "page": {"type": ["integer", "null"], "minimum": 1},
            "quote": {"type": ["string", "null"], "maxLength": 600},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "notes": {"type": ["string", "null"]},
        },
        ["requirement_id", "value", "unit", "page", "quote", "confidence", "notes"],
    ),
]


class ToolArgumentError(ValueError):
    """Bad arguments from the model; the message is sent back so it can correct itself."""


class BudgetExceeded(RuntimeError):
    """A hard per-run limit was hit."""


@dataclass
class ToolOutcome:
    result: str
    events: list[AgentEvent] = field(default_factory=list)


@dataclass
class ToolExecutor:
    """Executes tool calls against one datasheet and collects findings."""

    parsed: ParsedPdf
    index: DatasheetIndex
    requirements: dict[str, Requirement]
    max_pages_read: int = 40
    max_submissions_per_requirement: int = 3
    findings: dict[str, Finding] = field(default_factory=dict)
    verifications: dict[str, VerificationResult] = field(default_factory=dict)
    pages_read: int = 0
    _submissions: dict[str, int] = field(default_factory=dict)
    _warned_pages: set[int] = field(default_factory=set)

    @property
    def missing_requirements(self) -> list[str]:
        return [rid for rid in self.requirements if rid not in self.findings]

    def execute(self, name: str, raw_arguments: str) -> ToolOutcome:
        """Run one tool. Raises ToolArgumentError for invalid JSON or arguments."""
        try:
            args = json.loads(raw_arguments or "{}")
        except json.JSONDecodeError as exc:
            raise ToolArgumentError(f"Arguments are not valid JSON ({exc.msg}).") from exc
        if not isinstance(args, dict):
            raise ToolArgumentError("Arguments must be a JSON object.")
        handler = {
            "search_datasheet": self._search,
            "get_page": self._get_page,
            "extract_parameter": self._extract,
            "submit_finding": self._submit,
        }.get(name)
        if handler is None:
            raise ToolArgumentError(f"Unknown tool '{name}'.")
        return handler(args)

    # -- helpers ------------------------------------------------------------------

    def _read_page(self, page: Any) -> tuple[int, str]:
        if not isinstance(page, int) or isinstance(page, bool):
            raise ToolArgumentError("page_number must be an integer.")
        text = self.parsed.page_text(page)
        if text is None:
            raise ToolArgumentError(
                f"Page {page} does not exist (document has {self.parsed.page_count} pages)."
            )
        if self.pages_read >= self.max_pages_read:
            raise BudgetExceeded(f"page read budget of {self.max_pages_read} pages exhausted")
        self.pages_read += 1
        return page, text[:MAX_PAGE_CHARS]

    def _injection_events(self, page: int, text: str) -> list[AgentEvent]:
        if page in self._warned_pages or not looks_like_injection(text):
            return []
        self._warned_pages.add(page)
        return [
            AgentEvent(
                type=EventType.WARNING,
                title=f"Instruction-like text on page {page}",
                detail="The page contains text that looks like instructions to an AI. "
                "It is treated as data only.",
                data={"page": page},
            )
        ]

    def _requirement(self, rid: Any) -> Requirement:
        if not isinstance(rid, str) or rid not in self.requirements:
            known = ", ".join(self.requirements)
            raise ToolArgumentError(f"Unknown requirement_id {rid!r}. Known ids: {known}.")
        return self.requirements[rid]

    # -- tools -----------------------------------------------------------------------

    def _search(self, args: dict[str, Any]) -> ToolOutcome:
        query = args.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ToolArgumentError("query must be a non-empty string.")
        top_k = args.get("top_k", 5)
        if not isinstance(top_k, int) or isinstance(top_k, bool):
            raise ToolArgumentError("top_k must be an integer.")
        hits = self.index.search(query[:200], top_k)
        snippets = [
            f"[page {h.page}, score {h.score}]\n{wrap_document(h.text[:SNIPPET_CHARS], h.page)}"
            for h in hits
        ]
        result = "\n\n".join(snippets) if snippets else "No matches. Try other keywords."
        event = AgentEvent(
            type=EventType.SEARCH,
            title=f'Searched "{query[:80]}"',
            detail=(
                f"{len(hits)} hit(s) on page(s) {', '.join(str(h.page) for h in hits)}"
                if hits
                else "No matches"
            ),
            data={"query": query, "pages": [h.page for h in hits]},
        )
        return ToolOutcome(result, [event])

    def _get_page(self, args: dict[str, Any]) -> ToolOutcome:
        page, text = self._read_page(args.get("page_number"))
        event = AgentEvent(type=EventType.READ_PAGE, title=f"Read page {page}", data={"page": page})
        return ToolOutcome(wrap_document(text, page), [event, *self._injection_events(page, text)])

    def _extract(self, args: dict[str, Any]) -> ToolOutcome:
        req = self._requirement(args.get("requirement_id"))
        pages = args.get("page_numbers")
        if not isinstance(pages, list) or not pages:
            raise ToolArgumentError("page_numbers must be a non-empty list of integers.")
        if len(pages) > MAX_EXTRACT_PAGES:
            raise ToolArgumentError(f"At most {MAX_EXTRACT_PAGES} pages per call.")
        blocks: list[str] = []
        events: list[AgentEvent] = []
        for page_arg in dict.fromkeys(pages):
            page, text = self._read_page(page_arg)
            blocks.append(wrap_document(text, page))
            events.extend(self._injection_events(page, text))
        header = (
            f"Requirement {req.id} — {req.title} ({req.type.value}: {req.describe()}).\n"
            "Extract the value from the pages below and call submit_finding."
        )
        event = AgentEvent(
            type=EventType.EXTRACT,
            title=f"Extracting {req.id} from page(s) {', '.join(map(str, dict.fromkeys(pages)))}",
            detail=req.title,
            data={"requirement_id": req.id, "pages": list(dict.fromkeys(pages))},
        )
        return ToolOutcome(header + "\n\n" + "\n\n".join(blocks), [event, *events])

    def _submit(self, args: dict[str, Any]) -> ToolOutcome:
        req = self._requirement(args.get("requirement_id"))
        count = self._submissions.get(req.id, 0)
        if count >= self.max_submissions_per_requirement:
            raise ToolArgumentError(
                f"{req.id} was already submitted {count} times; move on to the next requirement."
            )
        try:
            finding = Finding.model_validate(args)
        except ValidationError as exc:
            problems = "; ".join(
                f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()
            )
            raise ToolArgumentError(f"Invalid finding: {problems}") from exc
        self._submissions[req.id] = count + 1
        self.findings[req.id] = finding

        submit_event = AgentEvent(
            type=EventType.SUBMIT,
            title=f"Finding for {req.id}",
            detail=(
                f"{finding.value} {finding.unit or ''}".strip() + f" (page {finding.page})"
                if finding.value is not None
                else "Not found in datasheet"
            ),
            data={"requirement_id": req.id, "confidence": finding.confidence},
        )
        if finding.value is None:
            self.verifications.pop(req.id, None)
            return ToolOutcome(
                json.dumps({"accepted": True, "recorded_as": "not found"}), [submit_event]
            )

        page_text = self.parsed.page_text(finding.page) if finding.page else None
        verification = verify_quote(finding.quote, page_text)
        self.verifications[req.id] = verification
        verify_event = AgentEvent(
            type=EventType.VERIFY,
            title=f"Quote {'verified' if verification.verified else 'NOT verified'} for {req.id}",
            detail=(
                f"{verification.method.value} match on page {finding.page}"
                if verification.verified
                else verification.reason
            ),
            data={
                "requirement_id": req.id,
                "verified": verification.verified,
                "score": verification.score,
            },
        )
        reply: dict[str, Any] = {"accepted": True, "quote_verified": verification.verified}
        if not verification.verified:
            remaining = self.max_submissions_per_requirement - self._submissions[req.id]
            reply["problem"] = verification.reason
            reply["hint"] = (
                "Re-read the page and resubmit with a quote copied character for character."
                if remaining > 0
                else "No resubmissions left for this requirement."
            )
        return ToolOutcome(json.dumps(reply), [submit_event, verify_event])
