# Key Notes and saved notes: what the backend needs (10 Oct 2026)

The frontend for both is built and live. It switches to real data as soon as these endpoints exist.
No other frontend change is needed: the field names below are exactly what the screens read.

## 1. Key Notes: Sanya (Tutor Backend)

Revision notes made from the student's own lessons. Already listed in the 4 Oct master plan (§4, Medium).

**`GET /students/me/key-notes?session_id=<optional>`** (student bearer token)

```json
{ "notes": [
  {
    "id": "ALG-ORI-02",                       // stable; used to save a card
    "topic_code": "ALG-ORI-02",
    "topic": "Reading algebraic notation",
    "meaning": "A number next to a letter means multiply: 3x is 3 × x.",
    "how_to_start": "Spot the number touching the letter.",
    "steps": ["Read 3x as 3 times x", "Read ab as a times b"],
    "be_careful": ["3x is not 3 + x"],
    "tips": ["Say the × out loud"],
    "formula": "ab = a × b",
    "example": ["3y when y = 2", "= 3 × 2 = 6"],
    "exam_tip": "Write the × if unsure.",
    "flagged": true                           // from a mistake made in this session
  }
] }
```

- With `session_id`: notes for that session's topic. Without it: the student's latest notes.
- Every field except `topic` may be missing or empty; the screen leaves that section out.
- No notes yet → `{ "notes": [] }` with 200 (the screen shows "No key notes yet").
- Source suggestion: the Phase 4 review already has `first_error` and the pattern summary, which can seed `be_careful` and `flagged`.

## 2. Saved notes: Saravanan (Student Model, Postgres)

Students save key-note cards and write their own notes per topic. Today these are kept in the
student's browser only, so they are lost on another device or after clearing the browser.

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/students/me/notes` | — | `{ "notes": Note[] }`, newest first |
| POST | `/students/me/notes` | `{ topic, text, key_note_id }` | `Note` (201) |
| PATCH | `/students/me/notes/{id}` | `{ topic?, text? }` | `Note` |
| DELETE | `/students/me/notes/{id}` | — | 204 |

```json
Note = {
  "id": "NOTE-…",
  "topic": "Reading algebraic notation",
  "text": "3x means three lots of x. Not 3 plus x!",   // "" for a saved card with no comment
  "key_note_id": "ALG-ORI-02",                         // null for the student's own note
  "created_at": "2026-10-10T09:12:00Z",
  "updated_at": "2026-10-10T09:12:00Z"
}
```

- Only the owner can read or change a note (404 for anyone else's).
- Limits: `topic` up to 80 characters, `text` up to 2000.
- One saved card per `key_note_id` per student (POST again returns the existing one).
- Nice to have: on first load, the frontend can upload the notes already in the browser, so nothing is lost at the switch-over.

## 3. Frontend switch-over: Manav

- Key Notes: nothing to do. The screen already calls the endpoint and shows "on their way" until it exists.
- Saved notes: set `NEXT_PUBLIC_NOTES_API=true`, rebuild, deploy, and test with a real student.
