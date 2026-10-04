# Requirements Document

## Introduction

NovelBridge is a local-first web application that helps readers of Chinese and Japanese
web/light novels continue a series when the official English translation has been dropped.
The user pastes previously translated chapters as reference, maintains a per-series glossary
of names and terms, then pastes a raw (untranslated) chapter. NovelBridge produces an English
translation that stays consistent with the established names, terminology, tone, and narrative
flow drawn from the reference material.

The prototype runs entirely on the user's local setup. Translation is performed by an Ollama
instance on the user's home server (local network). The architecture is engine-agnostic and
deployment-friendly so the app can later be hosted on AWS and, optionally, use Amazon Bedrock
as the translation engine without a rewrite.

### Primary goals

- Produce consistent, context-aware translations of raw CN/JP chapters into English.
- Keep the entire prototype runnable and demoable locally with no cloud dependency.
- Keep the architecture clean so a local-to-AWS transition is a configuration change, not a rewrite.

### Non-goals (prototype)

- No scraping of novel sites; references and raw chapters are pasted as text.
- No user accounts, authentication, or multi-user features.
- No automatic glossary extraction in the core (auto-suggest is a documented stretch goal).

### Glossary of terms

- **Project**: A per-series workspace holding reference chapters, a glossary, and translations.
- **Reference chapter**: A previously translated (English) chapter pasted in to establish style and naming.
- **Raw chapter**: An untranslated Chinese or Japanese chapter the user wants translated.
- **Glossary**: A set of term -> preferred-translation pairs (e.g. character/place/skill names) the translation must honor.
- **Translation engine**: A pluggable component that performs the actual translation (Ollama by default).

## Requirements

### Requirement 1: Manage series projects


**User Story:** As a reader following several dropped series, I want to organize my work into
per-series projects, so that each series keeps its own references, glossary, and translations separate.

#### Acceptance Criteria

1. WHEN the user opens the app THEN THE SYSTEM SHALL display a list of existing projects.
2. WHEN the user creates a project with a non-empty name THEN THE SYSTEM SHALL persist it and show it in the list.
3. WHEN the user selects a project THEN THE SYSTEM SHALL show that project's reference chapters, glossary, and translation workspace.
4. WHEN the user deletes a project THEN THE SYSTEM SHALL remove the project and all its associated data after a confirmation.
5. IF the user attempts to create a project with an empty name THEN THE SYSTEM SHALL reject the action and show a validation message.

### Requirement 2: Add reference chapters by pasting text

**User Story:** As a reader, I want to paste previously translated chapters into a project, so that
the translator can match established names, tone, and flow.

#### Acceptance Criteria

1. WHEN the user pastes text and provides a title into the reference input THEN THE SYSTEM SHALL save it as a reference chapter in the current project.
2. WHEN a project has reference chapters THEN THE SYSTEM SHALL list them with their titles and allow viewing their content.
3. WHEN the user deletes a reference chapter THEN THE SYSTEM SHALL remove it from the project.
4. IF the user submits an empty reference THEN THE SYSTEM SHALL reject it and show a validation message.
5. WHERE no reference chapters exist in a project THE SYSTEM SHALL still allow translation but SHALL indicate that no context is available.

### Requirement 3: Maintain a manual glossary

**User Story:** As a reader, I want to define how specific names and terms are translated, so that the
output is consistent across chapters (e.g. the same character name every time).

#### Acceptance Criteria

1. WHEN the user adds a glossary entry with a non-empty source term and a non-empty translation THEN THE SYSTEM SHALL persist the pair in the current project.
2. WHEN the user edits or deletes a glossary entry THEN THE SYSTEM SHALL update the persisted glossary accordingly.
3. WHEN a translation is requested THEN THE SYSTEM SHALL supply the project's glossary to the translation engine as binding guidance.
4. IF the user adds a glossary entry whose source term duplicates an existing one THEN THE SYSTEM SHALL reject or update it rather than create a conflicting duplicate.
5. WHERE the glossary is empty THE SYSTEM SHALL still allow translation.

### Requirement 4: Translate a raw chapter with context

**User Story:** As a reader, I want to paste a raw Chinese or Japanese chapter and get an English
translation that respects my glossary and prior chapters, so that the story reads consistently.

#### Acceptance Criteria

1. WHEN the user pastes a raw chapter and requests translation THEN THE SYSTEM SHALL send the raw text, the glossary, and relevant reference context to the translation engine and return English output.
2. WHEN reference chapters exist THEN THE SYSTEM SHALL include reference context in the translation request, bounded so the request stays within the engine's context limit.
3. WHEN the source language is specified or detected (Chinese or Japanese) THEN THE SYSTEM SHALL pass that information to the engine to guide translation.
4. WHILE a translation is in progress THE SYSTEM SHALL show a visible in-progress indicator and SHALL stream output if the engine supports streaming.
5. IF the translation engine is unreachable or returns an error THEN THE SYSTEM SHALL show a clear error message and SHALL NOT lose the user's pasted raw text.
6. WHEN a translation completes THEN THE SYSTEM SHALL display the result alongside the raw text and SHALL allow saving it to the project.

### Requirement 5: Pluggable, configurable translation engine

**User Story:** As the developer, I want the translation engine to be swappable and configurable, so that
I can use my home-server Ollama now and move to another engine (e.g. Bedrock) later without rewriting the app.

#### Acceptance Criteria

1. THE SYSTEM SHALL define a single translation-engine interface that all engine implementations conform to.
2. THE SYSTEM SHALL provide an Ollama engine implementation as the default.
3. THE SYSTEM SHALL provide a mock engine implementation that requires no network, for offline development and demos.
4. THE SYSTEM SHALL read the Ollama base URL and model name from configuration so a home-server address can be used.
5. WHEN configuration selects an engine THEN THE SYSTEM SHALL use that engine for all translation requests without code changes elsewhere.
6. IF a required engine configuration value is missing THEN THE SYSTEM SHALL fail fast at startup with a clear message.

### Requirement 6: Local-first operation with AWS-ready architecture

**User Story:** As the developer, I want the prototype to run fully locally yet be structured for AWS, so that
I can demo on my machine now and host it on AWS later with minimal change.

#### Acceptance Criteria

1. THE SYSTEM SHALL run end-to-end on the user's local machine with only the frontend, the backend, and a reachable Ollama instance.
2. THE SYSTEM SHALL store project data in a local persistence layer that is isolated behind a storage interface.
3. THE SYSTEM SHALL expose the backend as an HTTP API consumed by the frontend so the backend can later be hosted independently without changing the contract.
4. THE SYSTEM SHALL keep all environment-specific values in configuration or environment variables.
5. THE SYSTEM SHALL NOT require any AWS connection, credentials, or services to run the prototype.

### Requirement 7: Persist work across sessions

**User Story:** As a reader, I want my projects, references, glossary, and saved translations to survive restarts,
so that I can continue a long series over multiple sessions.

#### Acceptance Criteria

1. WHEN the user restarts the backend THEN THE SYSTEM SHALL retain all previously saved projects, references, glossary entries, and saved translations.
2. WHEN data is saved THEN THE SYSTEM SHALL write it to the local persistence layer defined by the storage interface.
3. IF the persistence layer is empty on first run THEN THE SYSTEM SHALL start with no projects and SHALL NOT error.

## Stretch goals

- Auto-suggest candidate glossary terms by analyzing pasted reference chapters for recurring names.
- Retrieval ranking that selects the most relevant reference passages when references exceed the context budget.
- Amazon Bedrock engine implementation and AWS hosting of the frontend/backend.
- Side-by-side diff/review and inline editing of saved translations.
