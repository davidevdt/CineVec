"""
Turns an agent run into the plain numbers we store: tokens, latency, cost and
which tools were called. No LLM involved.
"""

from dataclasses import dataclass, field

from cinevec.logging import logger
from cinevec.utils.file_utils import load_config_file

# gpt-5.4-mini list price, used when config.yaml has no monitoring block.
DEFAULT_INPUT_COST_PER_MILLION = 0.375
DEFAULT_OUTPUT_COST_PER_MILLION = 2.25


def _load_cost_rates() -> tuple[float, float]:
    """(input, output) USD per million tokens, from config/config.yaml.

    ConfigBox maps kebab-case keys to snake_case attributes, but only on
    attribute access -- .get("input_cost_per_million") would silently miss.
    """
    try:
        monitoring = load_config_file().monitoring
        return (float(monitoring.input_cost_per_million),
                float(monitoring.output_cost_per_million))
    except Exception:
        logger.warning("No monitoring cost rates in config; using defaults.")
        return DEFAULT_INPUT_COST_PER_MILLION, DEFAULT_OUTPUT_COST_PER_MILLION


# Read once at import, like movie_agent.py does, rather than per request.
INPUT_COST_PER_MILLION, OUTPUT_COST_PER_MILLION = _load_cost_rates()


@dataclass
class ConversationRecord:
    question: str
    answer: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    tool_calls: int
    response_time: float
    cost: float
    tools_used: list[str] = field(default_factory=list)


def compute_cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens / 1_000_000) * INPUT_COST_PER_MILLION + \
           (output_tokens / 1_000_000) * OUTPUT_COST_PER_MILLION


def extract_tools_used(result) -> list[str]:
    """Tool names from the run, in call order.

    search_movies is recorded as "search_movies:<mode>" because the mode is the
    interesting half: it says which retrieval strategy the agent picked.
    """
    labels = []
    for message in result.all_messages():
        for part in getattr(message, "parts", []):
            if getattr(part, "part_kind", None) != "tool-call":
                continue
            try:
                mode = part.args_as_dict().get("mode")
            except Exception:
                mode = None
            labels.append(f"{part.tool_name}:{mode}" if mode else part.tool_name)
    return labels


def build_record(question: str, result, model: str,
                 response_time: float) -> ConversationRecord:
    usage = result.usage   # a property, not a method
    tools = extract_tools_used(result)
    input_tokens = usage.input_tokens or 0
    output_tokens = usage.output_tokens or 0
    return ConversationRecord(
        question=question,
        answer=result.output,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=usage.total_tokens or 0,
        tool_calls=usage.tool_calls or len(tools),
        tools_used=tools,
        response_time=response_time,
        cost=compute_cost(input_tokens, output_tokens),
    )
