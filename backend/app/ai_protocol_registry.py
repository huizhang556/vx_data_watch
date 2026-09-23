"""Runtime protocol registry shared by catalog validation and request code."""

CHAT_PROTOCOL_HANDLERS = {
    "chat_completions": "openai_chat",
    "responses": "openai_responses",
    "anthropic": "anthropic_messages",
    "gemini": "gemini_contents",
    "grok": "openai_chat",
}

SUPPORTED_CHAT_PROTOCOLS = frozenset(CHAT_PROTOCOL_HANDLERS)
SUPPORTED_IMAGE_PROTOCOLS = frozenset({"openai_images"})
SUPPORTED_VIDEO_PROTOCOLS = frozenset({"openai_videos"})

RUNTIME_PROTOCOLS = {
    "chat": SUPPORTED_CHAT_PROTOCOLS,
    "image": SUPPORTED_IMAGE_PROTOCOLS,
    "video": SUPPORTED_VIDEO_PROTOCOLS,
}
