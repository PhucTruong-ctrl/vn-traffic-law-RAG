# Engineering Rules

These rules are derived from the engineering principles in Robert C. Martin's *Clean Code* and *Clean Architecture*.

Use them as persistent coding constraints. Apply judgment: optimize for clarity, cohesion, testability, controlled dependencies, and ease of change. Do not chase arbitrary metrics or create abstractions only to satisfy a rule mechanically.

## 1. Core Priorities

- Optimize code for humans to read, understand, modify, test, and maintain.
- Preserve both behavior and structure. Working code with poor structure is unfinished work.
- Prefer simple, explicit designs over clever or speculative ones.
- Keep responsibilities cohesive and dependencies intentional.
- Make change local. A small requirement change should not force unrelated parts of the system to change.
- Keep technical details replaceable when the business policy does not require commitment to them.
- Leave touched code cleaner than you found it when the improvement is local and safe.
- Preserve behavior while refactoring. Use tests to make structural changes safely.

## 2. Naming

- Use intention-revealing names.
- Name variables, functions, classes, modules, and tests after what they mean in the domain or solution.
- Avoid vague names when a more precise name exists, including generic terms such as `data`, `info`, `item`, `obj`, `temp`, `manager`, `helper`, or `utils`.
- Avoid misleading names and names that imply behavior the code does not provide.
- Use one consistent word for one concept.
- Do not use the same word for unrelated concepts.
- Prefer pronounceable and searchable names.
- Avoid unnecessary encodings, type prefixes, member prefixes, and Hungarian-style notation.
- Choose class names as nouns or noun phrases that describe a responsibility.
- Choose function and method names as verbs or verb phrases that describe behavior.
- Make names describe important side effects.
- Use longer names when scope is larger or additional context is required.
- Prefer clarity over brevity.
- Avoid jokes, puns, abbreviations, and clever naming that makes readers decode intent.

## 3. Functions

- Keep functions small enough to understand quickly.
- A function should do one coherent thing.
- Keep one level of abstraction within a function.
- Do not mix orchestration with low-level implementation details.
- Organize functions so code reads from high-level intent toward lower-level detail.
- Extract meaningful operations instead of adding large internal sections to one function.
- Prefer descriptive function names over explanatory comments.
- Keep argument lists small.
- Avoid flag arguments that make one function perform multiple modes of behavior.
- When multiple arguments form one concept, consider a meaningful parameter object.
- Avoid output arguments when a return value or explicit state-changing operation is clearer.
- Do not hide side effects.
- Separate commands that change state from queries that return information when practical.
- Keep error handling from obscuring the primary operation.
- Avoid deep nesting. Use clear control flow, extracted predicates, and small functions.
- Prefer positive, intention-revealing conditions when they are clearer.
- Encapsulate complicated conditions behind well-named predicates.
- Avoid `goto`.
- Multiple early returns are acceptable when they make a small function clearer.

## 4. Duplication and Expressiveness

- Do not duplicate knowledge.
- When the same logic appears repeatedly, identify the underlying concept and give it one authoritative representation.
- Do not extract abstractions merely because two blocks look syntactically similar. Extract when they represent the same concept or reason to change.
- Prefer expressive code over compressed or clever code.
- Use explanatory variables when they improve understanding.
- Replace meaningful magic numbers, strings, statuses, and configuration values with named concepts.
- Make behavior obvious from structure and naming.
- Remove unnecessary indirection and accidental complexity.

## 5. Comments

- Do not use comments to compensate for unclear code.
- First improve names, structure, function boundaries, and abstractions.
- Keep comments only when they add information the code cannot reasonably express by itself.
- Good comments may explain intent, important consequences, non-obvious constraints, warnings, legal requirements, or public API usage.
- Remove redundant comments that restate the code.
- Remove misleading, obsolete, noisy, journal-style, or decorative comments.
- Delete commented-out implementation code. Version control owns history.
- Do not add comments merely to satisfy a documentation convention when they add no useful information.
- Prefer a well-named function or variable over a comment explaining an expression.

## 6. Formatting and File Organization

- Format code to communicate structure.
- Keep closely related code close together.
- Separate distinct concepts visually.
- Order code so readers encounter high-level concepts before low-level implementation details.
- Keep declarations and functions near the code they conceptually belong to.
- Follow the codebase's consistent formatting conventions.
- Do not create a long disorganized source file containing unrelated responsibilities.
- Split a source file when it contains distinct responsibilities, concepts, actors, or reasons to change.
- Split by cohesion and responsibility, not by arbitrary line count.
- Do not mechanically fragment cohesive code into many tiny files that make navigation harder.
- A large file is a design smell that must trigger a responsibility and cohesion review.

## 7. Classes and Modules

- Keep classes and modules cohesive.
- A class or module should have one primary reason to change.
- Do not turn one class into a container for unrelated behavior.
- If fields and methods form separate clusters of responsibility, extract cohesive classes or modules.
- Put behavior where the required information and responsibility naturally belong.
- Avoid feature envy, where one object spends most of its effort manipulating another object's internals.
- Preserve encapsulation.
- Do not expose internal structure only to make callers perform work that belongs inside the abstraction.
- Prefer many cohesive classes over one God class when responsibilities are genuinely distinct.
- Do not create empty abstractions or excessive classes only to make classes smaller.
- Organize classes so changes to one responsibility do not unnecessarily risk another.

## 8. Objects and Data Structures

- Distinguish objects from data structures.
- Objects should hide internal data and expose behavior.
- Data structures may expose data but should not pretend to be rich behavioral objects.
- Avoid hybrids that expose internal representation while also claiming behavioral encapsulation.
- Avoid long navigation chains that couple callers to object internals.
- Encapsulate traversal and structural knowledge behind meaningful operations.
- Keep boundary DTOs simple and purpose-specific.

## 9. Error Handling

- Keep error handling explicit and consistent.
- Prefer the language's normal error mechanism over ad hoc return codes when that improves clarity.
- Provide useful context with errors.
- Keep the normal flow readable.
- Keep error handling as its own responsibility when it becomes substantial.
- Avoid returning `null` when a clearer absence or result abstraction is available and appropriate.
- Avoid accepting `null` when it represents an invalid contract.
- Do not silently ignore failures.
- Do not mix unrelated error policies across the codebase.

## 10. Third-Party and External Boundaries

- Treat third-party libraries and external APIs as boundaries.
- Do not spread external API types and assumptions throughout application code.
- Wrap volatile external dependencies behind application-specific abstractions when doing so protects the core design.
- Keep external changes localized.
- Use learning or boundary tests when integrating third-party behavior that the application depends on.
- Prefer an interface the application wishes it had over leaking an awkward external interface into the core.

## 11. Tests

- Treat test code as production-quality code.
- Keep tests readable, simple, expressive, and maintainable.
- Tests should protect the ability to refactor.
- Test one behavioral concept per test.
- Minimize assertions per concept when that improves clarity, but do not enforce a mechanical one-assert rule.
- Keep tests fast when they are intended to be unit tests.
- Keep tests independent where practical.
- Keep tests repeatable.
- Make tests self-validating.
- Write tests in a timely manner.
- Test important boundary conditions.
- When fixing a bug, add regression coverage for the failing behavior and nearby risky conditions.
- Do not skip trivial tests when they provide useful behavioral documentation.
- Use coverage information to find untested behavior, not as a substitute for thoughtful test design.
- Keep test APIs and seams stable enough that harmless refactoring does not break the suite unnecessarily.

## 12. Refactoring Discipline

- Prefer small, behavior-preserving refactoring steps over large uncontrolled rewrites.
- Keep tests passing throughout structural changes whenever practical.
- Improve names, remove duplication, extract functions, and separate responsibilities incrementally.
- Do not rewrite working code from scratch merely because the current design is messy.
- Refactor when change exposes a design problem.
- Do not refactor unrelated areas without a concrete reason.
- Make the code easier to read and easier to change after each meaningful modification.

## 13. Concurrency

- Keep concurrency concerns separate from unrelated business logic.
- Minimize shared mutable state.
- Prefer independent state, copies, or immutability when practical.
- Keep synchronized or locked sections as small as correctness allows.
- Understand the concurrency primitives and execution model being used.
- Do not assume concurrent code is correct because failures are rare.
- Test concurrent behavior under conditions likely to expose race conditions and ordering problems.
- Keep non-concurrent business behavior independently testable.

# Clean Architecture Rules

## 14. Architecture Serves Change

- Architecture exists to make the system easier to develop, deploy, operate, maintain, and change.
- Do not optimize only for the current behavior while destroying future changeability.
- Keep significant decisions reversible when the use case does not require commitment yet.
- Delay unnecessary commitment to frameworks, databases, delivery mechanisms, and infrastructure choices.
- The structure of the system should minimize the cost and risk of expected change.

## 15. Single Responsibility Principle

- A module should be responsible to one actor or one cohesive group of stakeholders that changes it for the same reason.
- Separate responsibilities that change for different actors.
- Do not confuse SRP with the mechanical rule that every class or function must contain only one tiny action.
- At function level, still keep each function focused on one coherent operation.
- At module and component level, organize around reasons to change.

## 16. Open-Closed Principle

- Design stable policy so new behavior can often be added by extension instead of repeatedly modifying unrelated existing code.
- Protect high-level policy from unnecessary changes in lower-level details.
- Use abstraction strategically where a real variation point exists.
- Do not introduce speculative extension points without evidence of variation.

## 17. Liskov Substitution Principle

- Implementations of an abstraction must honor the abstraction's behavioral contract.
- A caller should not need type checks, special cases, or implementation-specific workarounds to use a subtype correctly.
- Do not create inheritance or interface hierarchies whose implementations require incompatible expectations.
- If implementations are not substitutable, redesign the abstraction or separate the contracts.

## 18. Interface Segregation Principle

- Do not force clients to depend on operations they do not use.
- Prefer focused, client-relevant interfaces over broad kitchen-sink interfaces.
- Split contracts when different consumers need materially different capabilities.
- Keep dependencies as narrow as the use case allows.

## 19. Dependency Inversion Principle

- High-level policy must not depend directly on volatile low-level implementation details.
- Source-code dependencies across important boundaries should point toward higher-level policy.
- Let details implement abstractions appropriate to the policy.
- Stable policy should define or own the abstractions it needs when practical.
- Do not apply DIP mechanically to stable platform primitives that do not create meaningful volatility.

## 20. Component Cohesion

- Components must have a coherent purpose.
- Group classes that belong together for release, change, and reuse.
- Common Closure Principle: keep together classes that change for the same reasons and at the same times.
- Separate classes that change for different reasons or at different times.
- Common Reuse Principle: do not force consumers of a component to depend on classes they do not use.
- Do not create miscellaneous shared components containing unrelated utilities.

## 21. Component Coupling

- Keep the component dependency graph acyclic.
- Break dependency cycles by correcting ownership, moving responsibilities, or introducing an appropriate abstraction.
- Depend in the direction of stability.
- Do not make a stable, widely depended-on component depend on a volatile component without an explicit boundary.
- Stable components that need flexibility should contain suitable abstractions.
- Do not design the entire component graph speculatively before the logical design reveals real boundaries.

## 22. Boundaries

- Draw boundaries between things that change for different reasons and at different rates.
- Separate high-level policy from low-level details.
- Keep UI, delivery, persistence, frameworks, and devices outside the core business policy.
- Make boundary crossings explicit.
- Control the direction of dependencies at every significant boundary.
- Translate data at boundaries when external representations would pollute the inner model.
- Pass simple, purpose-specific data across boundaries rather than framework-specific objects.
- Do not let an outer detail dictate the shape of inner policy.

## 23. Business Rules and Use Cases

- Business rules are the core reason the system exists.
- Keep enterprise and domain policy independent from UI, database, transport, frameworks, and infrastructure.
- Model application-specific behavior as explicit use cases.
- Keep unrelated use cases independently changeable.
- Do not allow one use case to become a central conditional dispatcher for many unrelated behaviors.
- Use application-owned request and response models at use-case boundaries.
- Keep business policy testable without requiring the web, UI, database, or network.

## 24. Dependency Rule

- Dependencies that cross architectural boundaries must point inward toward higher-level policy.
- Inner layers must not know implementation details of outer layers.
- Domain and use-case code must not import web frameworks, ORM entities, database drivers, transport clients, or presentation classes merely for convenience.
- Use interfaces, adapters, and data mapping when required to maintain the dependency direction.
- Flow of control may move outward, but source-code dependencies must still respect the boundary direction.

## 25. Presenters, Views, and Humble Objects

- Keep presentation formatting outside use cases and domain policy.
- Use presenters or equivalent boundary objects to transform application output into view-specific forms.
- Keep UI and framework-facing objects thin when they are difficult to test.
- Move decision-making policy into testable objects.
- Do not put business rules in controllers, views, serializers, or framework lifecycle callbacks.

## 26. Database Is a Detail

- Do not design the core domain around a database product, ORM, schema, or query language.
- Persistence must serve the application, not define the application.
- Keep database access behind explicit boundaries.
- Do not reuse persistence entities automatically as domain entities, use-case models, and transport DTOs.
- Map representations when their responsibilities differ.
- Core business behavior must remain testable without the real database.

## 27. Web and Transport Are Details

- HTTP, RPC, messaging, CLI, GUI, and other delivery mechanisms are IO details.
- Do not let the delivery mechanism define the core architecture.
- Keep request parsing, transport validation, serialization, and protocol concerns at the outer boundary.
- Translate transport models into application-owned input models.
- Core use cases should not know whether they were invoked by HTTP, CLI, queue, GUI, or another delivery mechanism.

## 28. Frameworks Are Details

- Treat frameworks as tools, not as the architecture itself.
- Do not make core business policy inherit from framework base classes or depend on framework lifecycle contracts unless unavoidable.
- Keep framework-specific annotations, objects, and configuration near the outer boundary.
- Prefer adapters that isolate framework integration.
- Avoid deep commitment to a framework when the use case can remain independent.

## 29. Screaming Architecture

- The top-level structure should communicate the business domain and major use cases.
- A reader should be able to infer what the application does without first understanding its framework.
- Avoid top-level organization that exposes only technical buckets such as `controllers`, `services`, and `repositories` while hiding the domain.
- Prefer cohesive domain- or capability-oriented organization when it better communicates the system's purpose.
- Technical layers may exist, but they must not erase business boundaries.

## 30. Package and Module Organization

- Package by responsibility, capability, or component when that better preserves cohesion and boundaries.
- Do not scatter one business capability across unrelated technical packages without a strong reason.
- Keep implementation details inaccessible when callers should use a boundary interface.
- Make module visibility enforce the intended architecture.
- Do not create a package structure that looks clean while public APIs allow every layer to bypass it.
- Keep code that changes together close enough to change together.
- Separate code that changes independently.

## 31. Composition and Main

- Keep dependency construction and wiring outside business policy.
- Centralize concrete assembly in an outer composition root, main component, bootstrap layer, or equivalent.
- Inject details into policy instead of making policy construct details directly.
- Keep configuration and framework startup logic out of core domain and use-case modules.

## 32. Services and Distribution

- A service boundary is not automatically an architectural boundary.
- Do not introduce a network hop merely to make code look decoupled.
- Separate components according to policy, change, and deployment needs.
- Keep behavior together when it changes together.
- Distribute components only when independent deployment, scaling, ownership, or change provides concrete value.
- Do not replace in-process coupling with distributed coupling while preserving the same architectural dependency problem.

# Agent Execution Rules

When writing or modifying code:

1. Identify the responsibility and architectural layer of the code being changed.
2. Preserve existing behavior unless the task explicitly changes behavior.
3. Prefer the smallest coherent change that satisfies the requirement.
4. Before expanding a large class, function, or source file, check whether the new behavior belongs to a separate responsibility.
5. Before adding a dependency, determine its direction and whether it crosses an architectural boundary.
6. Keep business policy independent from framework, persistence, delivery, and presentation details.
7. Use names and structure that make the code explain itself.
8. Add or update tests for behavior that can break.
9. Refactor locally when the requested change exposes duplication, low cohesion, misplaced responsibility, or a broken boundary.
10. Do not create abstractions, interfaces, layers, files, or services without a concrete responsibility or variation point.
11. Do not optimize for fewer lines. Optimize for clarity, cohesion, and ease of change.
12. Do not optimize for more files. Split only when boundaries and responsibilities justify it.
13. After the change, verify that dependencies still point in the intended architectural direction.
14. Keep the touched code at least as understandable and maintainable as before.

# Review Triggers

Before considering a change complete, review for these smells:

- Vague, misleading, or inconsistent names.
- Large functions with multiple responsibilities.
- Mixed abstraction levels.
- Long or flag-heavy argument lists.
- Hidden side effects.
- Deep nesting or obscured conditionals.
- Duplicated knowledge.
- Magic values with hidden meaning.
- Comments compensating for unclear code.
- Commented-out or dead code.
- Low-cohesion classes or modules.
- God classes, God services, or monolithic source files.
- Misplaced responsibilities or feature envy.
- Leaking object internals through long navigation chains.
- Null-heavy contracts.
- Error handling obscuring normal flow.
- Third-party APIs leaking into core policy.
- Tests that are unreadable, slow, fragile, or test multiple unrelated concepts.
- UI, framework, database, transport, or serialization concerns inside business rules.
- Persistence or transport models reused indiscriminately across boundaries.
- Broad interfaces that clients only partially use.
- Stable policy depending on volatile details.
- Dependency cycles.
- Framework-first or technology-first architecture.
- Top-level structure that hides the business domain.
- Network/service boundaries with no real policy or deployment independence.

If one of these smells appears in newly written code, fix it before extending the design further unless the task explicitly requires preserving the existing structure.
