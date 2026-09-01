"""
conversation.py
------------------------------------------------------------
Defines the chatbot's conversation flow / question script.

Flow (matches Section 4 & 7 of the requirements doc):
  greeting -> intro -> scenario -> followup1 -> followup2 -> closing -> done

Duration target: ~5-10 minutes (Section 8), left configurable.
"""

STAGE_ORDER = [
    "greeting",
    "scenario",
    "followup1",
    "followup2",
    "closing",
    "done",
]

# Each stage's bot message. `{name}` is substituted with the candidate's
# name when known.
STAGE_SCRIPT = {
    "greeting": (
        "Hello{name_suffix}! Welcome to your communication assessment. "
        "This will take about 5-10 minutes and has two short parts: a "
        "quick introduction, and a realistic professional scenario. "
        "You can answer by voice (recommended) or by typing. "
        "Let's begin - please introduce yourself briefly: who you are and "
        "a little about your background."
    ),
    "scenario": (
        "Thanks, that was a great introduction. Now let's try a realistic "
        "scenario. Imagine you need to connect with a vendor regarding a "
        "product your company needs. Please start the conversation as you "
        "would in real life - introduce yourself to the vendor and explain "
        "why you're reaching out."
    ),
    "followup1": (
        "Good. Now the vendor asks: \"Could you tell me more about your "
        "specific requirements, timeline, and budget expectations?\" "
        "Please respond as you would to the vendor."
    ),
    "followup2": (
        "The vendor says they can meet most of your requirements but the "
        "timeline is a bit tight. How would you respond and move the "
        "conversation toward next steps?"
    ),
    "closing": (
        "Great. Please wrap up the conversation with the vendor "
        "professionally - a short summary and a courteous close."
    ),
    "done": (
        "Thank you - that completes your assessment! Your responses are "
        "being evaluated on pitch/self-presentation, vocabulary, and "
        "tonality. You can view your result now."
    ),
}

# Which stages count as "intro test" vs "scenario test" for scoring context
STAGE_CONTEXT = {
    "greeting": "intro",
    "scenario": "scenario",
    "followup1": "scenario",
    "followup2": "scenario",
    "closing": "scenario",
}


def first_stage():
    return STAGE_ORDER[0]


def next_stage(current_stage):
    try:
        idx = STAGE_ORDER.index(current_stage)
    except ValueError:
        return "done"
    if idx + 1 < len(STAGE_ORDER):
        return STAGE_ORDER[idx + 1]
    return "done"


def get_bot_message(stage, candidate_name=None):
    name_suffix = f", {candidate_name}" if candidate_name else ""
    template = STAGE_SCRIPT.get(stage) or STAGE_SCRIPT["done"]
    return template.format(name_suffix=name_suffix)


def is_terminal(stage):
    return stage == "done"


def scoring_context_for(stage):
    return STAGE_CONTEXT.get(stage, "scenario")
