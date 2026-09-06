---
name: no-partial-sprint-completion-claims
description: "Never declare a sprint complete or merge it before auditing every ticket and required gate"
condition: ["Sprint 5 batch đầu hoàn tất", "PR #24 đã merge thành công", "Sprint 5 started"]
scope: "text"
---

Before claiming a sprint is complete or merging its branch, audit every ticket in the sprint and verify each required acceptance criterion, Jira status, branch state, oracle verdict, CI result, and merge state. Distinguish clearly between a completed batch and a completed sprint; never mark unfinished tickets Done or imply the sprint is finished when only a subset was delivered.