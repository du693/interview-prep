import logging

logger = logging.getLogger("uvicorn.error")

# $ per 1M tokens (input, output)
PRICING = {
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-sonnet-4-6": (3.00, 15.00),
}


def log_cost(label: str, model: str, usage) -> float:
    input_rate, output_rate = PRICING[model]
    cost = (usage.input_tokens * input_rate + usage.output_tokens * output_rate) / 1_000_000
    logger.info(
        "[cost] %s (%s): %d in / %d out -> $%.5f",
        label,
        model,
        usage.input_tokens,
        usage.output_tokens,
        cost,
    )
    return cost
