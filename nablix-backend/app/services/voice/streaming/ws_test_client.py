"""Throwaway client to validate the Deepgram STT leg of streaming_server.py.

Streams a 16 kHz mono 16-bit PCM WAV to /voice/stream and prints every message.
Watch for {"type":"final_transcript",...} — that's Deepgram working. The later
tutor_response needs the main backend on :8000; STT does not.

    python ws_test_client.py path/to/16k_mono.wav
"""
import asyncio
import json
import sys
import wave

import websockets

WS = "ws://127.0.0.1:8004/voice/stream?session_id=test&student_id=ST001"
CHUNK = 3200  # 100 ms at 16 kHz * 2 bytes/sample


async def main(wav_path: str) -> None:
    with wave.open(wav_path, "rb") as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1 and w.getsampwidth() == 2, \
            "WAV must be 16 kHz mono 16-bit PCM"
        frames = w.readframes(w.getnframes())

    async with websockets.connect(WS) as ws:
        await ws.send(json.dumps({"type": "start", "language": "en"}))

        async def printer() -> None:
            async for msg in ws:
                print("<-", msg)

        reader = asyncio.create_task(printer())
        for i in range(0, len(frames), CHUNK):
            await ws.send(frames[i:i + CHUNK])
            await asyncio.sleep(0.1)  # pace ~real-time so Deepgram's VAD behaves
        await ws.send(json.dumps({"type": "stop"}))
        await asyncio.sleep(6)  # let final_transcript (+ tutor_response, if backend up) arrive
        reader.cancel()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python ws_test_client.py <16k_mono_16bit.wav>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
