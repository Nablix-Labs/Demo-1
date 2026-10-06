# Profile and People: handoff to Saravanan

Saravanan, the Demo-1 profile proxy and both screens are implemented locally.
The remaining work is in Student Model: authenticated profile reads and updates,
plus database storage for any missing learning preferences. We need that work
before we can verify the screens against real accounts and call the integration
complete.

## Student Model routes

Please add `GET /students/me/profile` and `PATCH /students/me/profile`.
Demo-1 forwards the student's bearer token unchanged, without a student ID,
query parameters or an internal-service token. Authenticate that token and
resolve the student from the account. Reject expired tokens and non-student
roles, and enforce ownership even when someone calls Student Model directly.
Existing account restrictions still apply.

The response and PATCH schemas are defined in
`nablix-backend/app/models/student_profile.py` and exposed in Demo-1 OpenAPI.
Return all required response keys, using null for missing optional values.
Return every linked guardian in `guardians`, each with a stable `guardian_id`.
Use an empty array when there are none. Guardian verification must come from
verification records; use null when it is unknown. Consent acceptance does not
establish identity verification.

`avatar_url` and `consents` are optional, read-only values from existing records.
Avatar URLs must use HTTP(S). Missing consent records display "Not set".
Do not copy browser onboarding values into the response or invent acceptance
timestamps.

## Saving changes

PATCH accepts display name, age/year bands, preferred mode, and nested
preferences for input mode and panel side. For example:

```json
{"display_name":"Chiru","preferences":{"panel_side":"right"}}
```

Leave omitted fields unchanged, including fields inside `preferences`.
Only `grade_band` accepts explicit null to clear its value. Reject empty patches,
unknown fields, blank names and invalid enum values with 422 before writing.
Also reject changes to identity, email, student code, tier, account status,
guardian links or verification, photos and consents. Use the schema's exact
age/year/mode values, including the en dash in age bands. Student Model must
validate these rules even though Demo-1 checks requests too.

Reuse the existing identity, guardian links and consent records. Add only the
missing preference storage, with migrations in the Student Model repository.
Demo-1 must not have a second profile or identity database. Commit the update
atomically, then return the full saved profile. Repeating the same PATCH must
be safe because Demo-1 retries transient transport failures. GET must not
change account or consent state.

Use these HTTP statuses:

- 401 for missing, invalid or expired credentials.
- 403 for a forbidden role or account.
- 404 for a missing student profile.
- 422 for invalid changes.
- 5xx for service failures.

Return a safe error response on failure. Do not return a partially saved profile.

## Checks before completing the integration

- Run GET → PATCH → GET against the actual Student Model database. Restart the
  service and read the profile after a fresh browser login to confirm persistence.
- Test two students. Changing browser student-code storage or supplying another
  student ID must never change whose profile the token can access.
- Confirm omitted fields and untouched nested preferences survive a save, that
  grade can be cleared, and that failed writes leave no partial changes.
- Check zero, one and multiple guardians, plus unknown verification and consent
  values.
- Apply the migrations and verify both routes in the target environment before
  declaring the screens integrated.

The Demo-1 loopback tests cover its transport and screens using contract fixtures.
They do not prove real Student Model authentication or database persistence.
Run the focused checks from each project's directory:

```sh
# nablix-backend
.venv/bin/python -m pytest tests/test_student_profile_proxy.py tests/test_http_utils.py -q

# Numera-ui
NODE_OPTIONS=--no-experimental-webstorage npm test -- lib/__tests__/profileScreens.test.ts
npx tsc --noEmit
```

The Node option prevents Node 26's experimental storage from interfering with
jsdom's browser storage. These checks pass locally: 27 backend tests, 9 screen
tests, and TypeScript validation.

Production cutover, avatar changes, consent changes, classes and invitations
remain outside this handoff.

## Learning walkthrough: editing the name

1. Profile holds the proposed name in form state. It is still unsaved.
2. PATCH sends only changed editable fields with the student's bearer token.
3. Student Model authenticates the token: who is making the request?
4. It resolves the student and checks authorization: whose profile can they edit?
5. It validates the change and commits it to the database: is it persisted?
6. Demo-1 validates the returned profile, then updates the screen and greeting
   stores from that confirmed response. A failed save preserves the confirmed
   values and shows an error. A response from an old login cannot update a new one.
7. People reads the same profile resource and displays its guardians. It needs
   no separate endpoint or database.

Changing a browser's stored student code must never grant access to another
account: the browser is user-controlled, while the token and the server's account
to student mapping establish ownership. Seeing a new name on screen alone does
not prove a database save. Form or browser state can change without a commit;
a fresh authenticated read checks what was persisted.
