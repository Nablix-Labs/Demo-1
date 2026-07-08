# Streaming TTS - WebSocket Protocol Changes

## What changed and why

Previously, the voice server waited for the FULL audio to be generated (2-3 seconds) before sending anything to the frontend. Text and audio were bundled in a single `tutor_response` message.

Now, text is sent immediately and audio is streamed in chunks. The frontend can show text right away and start playing audio as soon as the first chunk arrives (~300-500ms instead of 2-3s).

## New message flow

### 1. tutor_response (text only - sent immediately)

This is the same message type as before, but `audio_base64` is no longer included.

```json
{
  "type": "tutor_response",
  "transcript": "what is 2 plus 3",
  "normalized_expression": null,
  "confidence": 0.9812,
  "text": "Great question! 2 + 3 = 5. ...",
  "voice_text": "Great question! 2 plus 3 equals 5.",
  "needs_clarification": false,
  "text_latency_ms": 1200,
  "canvas_draw": []
}
```

**Frontend action:** Display the text response. DO NOT close the WebSocket. Audio chunks are coming next.

### 2. tutor_audio_chunk (one per chunk)

Each chunk is a piece of the MP3 audio, base64-encoded. Multiple of these arrive in sequence.

```json
{
  "type": "tutor_audio_chunk",
  "chunk": "<base64-encoded mp3 bytes>",
  "chunk_index": 0
}
```

- `chunk_index` starts at 0 and increments by 1 for each chunk.
- Typical chunk size: ~4KB of audio data before base64 encoding.
- First chunk usually arrives 300-500ms after `tutor_response`.
- Total chunks depend on response length. Short answers: 5-10 chunks. Long answers: 20-40 chunks.

**Frontend action:** Decode the base64 chunk and either:
- (Option A - simpler) Collect all chunks in an array, concatenate them after `tutor_audio_end`, then play.
- (Option B - lower latency) Use MediaSource API or Web Audio API to play chunks as they arrive.

Option A is fine for Demo-1. Option B gives the best user experience but is more complex.

### 3. tutor_audio_end (sent once, after all chunks)

Signals that all audio chunks have been sent.

```json
{
  "type": "tutor_audio_end",
  "total_chunks": 12,
  "tts_latency_ms": 1850
}
```

If TTS failed, it will include an error field:

```json
{
  "type": "tutor_audio_end",
  "total_chunks": 0,
  "tts_latency_ms": 0,
  "error": "OpenAI TTS failed: ..."
}
```

**Frontend action:** If using Option A, concatenate all collected chunks into one audio blob and play it. If `total_chunks` is 0, skip audio playback (text-only fallback).

## CRITICAL: Do not close the WebSocket after tutor_response

The old frontend code closes the WebSocket after receiving `tutor_response`. That needs to change. The WebSocket must stay open to receive `tutor_audio_chunk` and `tutor_audio_end` messages.

Close the WebSocket (or reset for next turn) only after receiving `tutor_audio_end`.

## Option A implementation sketch (collect and play)

```javascript
let audioChunks = [];

socket.onmessage = (event) => {
  const data = JSON.parse(event.data);

  if (data.type === "tutor_response") {
    // Show text immediately
    displayTutorText(data.text);
    audioChunks = [];  // reset for new audio
  }

  else if (data.type === "tutor_audio_chunk") {
    // Collect chunks
    audioChunks.push(data.chunk);
  }

  else if (data.type === "tutor_audio_end") {
    if (data.total_chunks > 0) {
      // Combine all base64 chunks into one audio blob
      const combined = audioChunks.join("");
      const audioBytes = atob(combined);
      const arrayBuffer = new Uint8Array(audioBytes.length);
      for (let i = 0; i < audioBytes.length; i++) {
        arrayBuffer[i] = audioBytes.charCodeAt(i);
      }
      const blob = new Blob([arrayBuffer], { type: "audio/mp3" });
      const audioUrl = URL.createObjectURL(blob);
      const audio = new Audio(audioUrl);
      audio.play();
    }
    // Ready for next turn
  }
};
```

## Backward compatibility note

The `tutor_response` message no longer contains `audio_base64`. If the frontend still looks for `audio_base64`, it will be `undefined`, which is fine as long as the frontend doesn't crash on missing fields. The frontend needs to be updated to handle the new chunk-based flow.

## Timeline

- Backend: streaming is live on the voice server now.
- Frontend: Manav needs to update the WebSocket message handler.
- For testing: you can use Option A (simpler) first, then optimize to Option B later if needed.
