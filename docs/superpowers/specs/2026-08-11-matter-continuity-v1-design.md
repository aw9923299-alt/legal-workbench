# Matter Continuity v1 Design

## Goal

Make the canonical Feishu message-analysis path surface deterministic related-Matter candidates instead of always persisting `related_matter_proposals=[]`, while preserving human confirmation as the only authority that creates a CandidateMatterLink or mutates a Matter.

## Current evidence

At `main@562e27e`:

- `FeishuMessage` already persists `thread_id`, `root_id`, `parent_id` and external `message_id`.
- `Communication` persists the outbound Feishu `external_message_id` and authoritative `matter_id` after a reviewed send.
- `CandidateMatterLink` persists human-confirmed message-candidate → Matter relationships.
- `ContextSnapshot.relevant_matter_ids`, `MessageCandidate.related_matter_proposals`, the candidate API response and web type already exist.
- Canonical `AnalyseFeishuMessageHandler._persist_success()` still creates/replaces candidates with no related Matter proposals.
- Message detail therefore requires the user to search all Matters manually before link/update.

## Scope

Implement a deterministic, read-only continuity resolver using only authoritative persisted facts:

1. **Reply-to-communication signal** — if the incoming Feishu message's `parent_id` or `root_id` matches a sent Communication's `external_message_id`, propose that Communication's Matter.
2. **Existing thread/root signal** — if another Feishu message in the same thread/root already has a human-confirmed CandidateMatterLink, propose that Matter.
3. Merge duplicate signals by Matter and retain the strongest score plus all evidence reasons.
4. Attach the resulting Matter IDs to `ContextSnapshot.relevant_matter_ids` and attach structured proposals to `MessageCandidate.related_matter_proposals`.
5. Persist an audit event when continuity candidates are materialized for an Agent result.
6. Show the proposals in Message Detail and preselect the top suggestion when the user chooses “关联已有 Matter” or “更新已有 Matter”. Final link/update remains an explicit human action.

## Proposal contract

Each proposal is JSON compatible with the existing field:

```json
{
  "matterId": "uuid",
  "matterNumber": "MAT-...",
  "title": "...",
  "confidence": 1.0,
  "signals": ["reply_to_communication", "same_thread_confirmed_link"],
  "evidenceRefs": ["communication:<uuid>", "message:<external-id>"]
}
```

Scores are deterministic, not model-generated:

- reply to a sent Communication: `1.0`
- same thread/root with confirmed CandidateMatterLink: `0.95`

No chat-only, participant-only or text-similarity matching is allowed in v1 because those signals are too weak to justify a privileged recommendation.

## Architecture

Add a focused application service `MatterContinuityResolver` that consumes the existing UnitOfWork repositories. Extend existing repository ports only with read methods required to retrieve:

- sent Communications by external Feishu message IDs;
- confirmed Matter links for a set of Feishu message database IDs.

Do not add a second runtime, queue, AI agent or parallel matter store.

`ContextSnapshotBuilder` resolves continuity inside the same deterministic snapshot transaction and includes the sorted Matter IDs in the snapshot hash. `AnalyseFeishuMessageHandler` derives the presentation proposals from the snapshot's continuity payload and persists them with the Candidate. This keeps the source of truth deterministic and replayable across retry/recovery.

## Governance and safety

- Resolver is advisory only.
- It cannot create CandidateMatterLink, MatterUpdateProposal, WorkItem or Communication.
- It only reads human-confirmed links and successfully sent Communications.
- Recalled/failed/unsent outbound data does not become an authority signal.
- Candidate resolution endpoints keep their current optimistic locking/idempotency/audit behavior.

## Observability

When an analysis persists one or more proposals, write `matter_continuity_candidates_materialized` against the Feishu message with Matter IDs, signals, AgentRun ID and ContextSnapshot ID. This is diagnostic evidence, not a business mutation.

## Testing

- Unit tests for merge/scoring and no-weak-signal behavior.
- ContextSnapshotBuilder tests proving relevant Matter IDs enter the immutable hash/payload.
- PostgreSQL integration test proving real repository joins across Communication / FeishuMessage / CandidateMatterLink.
- Message analysis test proving canonical Agent success persists proposals.
- Frontend test proving proposals are visible and top recommendation preselects the link/update modal.
- Existing lint, mypy, backend tests, frontend tests/typecheck/build, migrations and Compose gates must remain green.

## Out of scope

- automatic Matter linking;
- AI semantic Matter ranking;
- Matter Timeline / Activity feed;
- automatic WorkItem state changes after Communication;
- new Agent capabilities;
- vector retrieval or new infrastructure.
