from app.ai_service import _responses_request


def test_responses_request_uses_responses_content_types():
    instructions, payload = _responses_request([
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": [
            {"type": "text", "text": "看这张图"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
        ]},
        {"role": "assistant", "content": "好的"},
    ])

    assert instructions == "你是助手"
    assert payload[0]["content"] == [
        {"type": "input_text", "text": "看这张图"},
        {"type": "input_image", "image_url": "data:image/png;base64,abc"},
    ]
    assert payload[1]["content"] == [{"type": "input_text", "text": "好的"}]
