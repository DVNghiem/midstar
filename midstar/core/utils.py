from starlette.responses import StreamingResponse

async def get_streaming_response_body(response: StreamingResponse) -> bytes:
    body = b""
    async for chunk in response.body_iterator:
        body += chunk
    return body