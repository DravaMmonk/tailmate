# Tailmate Feature General View

Version: `v0.16.0`
Audience: Non-technical stakeholders, operators, and collaborators
Status: Current product feature view based on the implemented repository slices

This document explains what Tailmate currently does in plain language.
It is intentionally written for readers who need a product-level understanding rather than an engineering walkthrough.

## 1. What Tailmate Is

Tailmate is a dog-care assistant that helps owners keep important dog context in one place and continue conversations on the web.
It is designed to support everyday dog-care questions, capture useful background about each dog over time, and make it easier for owners to ask for help without starting from zero on every conversation.

Today, Tailmate combines:

- a web workspace for account access, chat, history, and settings
- persistent dog memory that improves over time
- protected media handling for photos, videos, and voice notes
- a reviewed knowledge fallback for supported factual questions

## 2. Who It Is For

Tailmate currently serves three groups:

- Dog owners who want quick, personalized support about their dog
- Operators who need safe account, privacy, and quality controls
- Product teams who need a foundation that can grow into a broader pet-care experience

## 3. Core Product Promise

Tailmate's current product promise is:

- remember the dog so the owner does not need to repeat the same facts
- answer quickly in a familiar conversational format
- work through a durable owner-facing web workspace
- handle sensitive uploads more safely by removing unnecessary metadata
- keep owner data isolated, exportable, and erasable

## 4. Customer-Facing Features

### 4.1 Account and access

Users can create an account with email login on the web experience.
Once signed in, they receive access to protected chat, dashboard, history, and settings areas.

User benefit:

- gives each owner a private workspace
- keeps their dog records and conversations tied to the right person
- creates a durable base for owner-specific continuity

### 4.2 Dog profiles that build themselves over time

Tailmate can create a dog profile from very little information, starting with something as simple as the dog's name.
As the owner keeps chatting, Tailmate adds more details in the background, such as breed, age, weight, lifestyle details, and some medical context when mentioned.

The system also supports households with more than one dog.
It can remember the currently active dog, switch when another known dog is mentioned, and ask the owner to clarify when a message could apply to multiple dogs.

User benefit:

- reduces form filling
- makes later answers more tailored to the right dog
- supports real-life multi-dog households

### 4.3 Live chat with streaming replies

The web chat experience returns replies as they are generated instead of waiting for the whole response to finish.
This makes the interaction feel more immediate, especially for anxious or time-sensitive owner questions.

User benefit:

- faster perceived response time
- more conversational experience
- better fit for ongoing back-and-forth use

### 4.4 Conversation history and session continuity

Tailmate keeps previous chat sessions and surfaces them in the dashboard.
Owners can return to earlier conversations instead of losing context after each visit.

User benefit:

- easier follow-up on ongoing concerns
- less repeated explanation
- a more durable relationship with the product

### 4.5 Photo, video, and voice-note uploads

Tailmate supports media uploads inside the conversation flow.
Before storing any uploaded asset, it removes metadata that may contain sensitive details such as location, timestamps, or device information.

Supported upload categories currently include:

- images
- videos
- audio recordings

User benefit:

- safer handling of personal media
- easier sharing of relevant dog context
- media becomes part of the same conversation flow rather than a separate tool

### 4.6 Voice note transcription

When an owner sends a supported voice note, Tailmate can transcribe it and route the meaning back into the normal chat and dog-profile flow.
This means spoken updates can still improve the dog's profile or continue a conversation without a separate voice-only product path.

User benefit:

- easier use while walking, driving, or multitasking
- reduces friction for owners who prefer speaking over typing
- keeps voice messages useful beyond simple storage

### 4.7 Reviewed knowledge answers

Tailmate includes a reviewed knowledge fallback for supported factual questions.
If a suitable reviewed answer exists, it can respond from that trusted content.
If not, it falls back cleanly instead of pretending to know.

User benefit:

- more reliable answers for supported factual topics
- clearer boundaries when the system does not have a reviewed answer
- less risk of inconsistent responses for repeat factual questions

### 4.8 Channel scope

Tailmate's supported owner-facing channel is now the web application.
The earlier WhatsApp ingress experiment has been retired and is no longer part of the live product or onboarding journey.

User benefit:

- keeps the supported experience clear and predictable
- reduces operator risk from extra ingress infrastructure
- keeps the product surface aligned with the maintained frontend

### 4.9 Dashboard

The dashboard gives owners a single overview of:

- dog profiles
- recent conversation sessions
- quick actions for new chat and settings

User benefit:

- quick orientation after login
- one place to resume common tasks
- visible proof that Tailmate remembers prior activity

### 4.10 Settings, data export, and account deletion

Owners can download a full export of their account data and can permanently delete their account.
The current settings view also exposes account identity details and signals future language-preference support.

User benefit:

- builds trust through transparency
- supports portability of personal data
- gives owners direct control over account removal

## 5. Operator and Business Capabilities

Tailmate is not only a user-facing product.
It also includes the supporting product infrastructure needed for safe rollout and ongoing operation.

### 5.1 Identity and owner isolation

Each dog profile and media action is tied to a verified owner.
The current model is designed so one owner cannot access another owner's dog records through normal product flows.

Business value:

- reduces data-leak risk
- creates a safer baseline for future paid or multi-user features
- supports later expansion into controlled sharing models

### 5.2 Privacy workflow

Tailmate supports account export and hard deletion across persisted account, dog, media, and session data.
The product is built so privacy requests are part of the product path, not a manual cleanup exercise.

Business value:

- improves compliance readiness
- reduces operational burden for privacy handling
- strengthens user trust

### 5.3 Public abuse protection

The main public query route is rate-limited per user.
This helps protect the system from heavy or abusive traffic even when the caller is authenticated.

Business value:

- controls cost spikes
- protects service quality for normal users
- creates a more stable public product surface

### 5.4 Structured observability

Tailmate includes correlated logs and distributed tracing across the public gateway, runtime, storage paths, and retained internal service boundaries.
Operators can follow one request through multiple services more easily.

Business value:

- faster issue diagnosis
- clearer operational accountability
- better production support for cross-service flows

### 5.5 Business metrics

Tailmate exposes a metrics surface for key product signals such as:

- new sessions
- skill outcomes
- intent routing
- knowledge-base usage
- language-model latency

Business value:

- creates an early measurement layer for product usage
- helps operators spot quality or performance regressions
- supports future reporting and operational dashboards

### 5.6 Reviewed knowledge management

Reviewed knowledge content can be managed through controlled internal tools rather than manual database editing.
This makes the factual-answer layer more maintainable as the product grows.

Business value:

- makes content operations more repeatable
- reduces ad hoc data handling
- supports safer expansion of trusted knowledge coverage

## 6. Current User Journey

The typical web journey is:

1. Land on the website
2. Create an account or sign in
3. Start a chat
4. Mention a dog by name so Tailmate begins building the dog's profile
5. Continue chatting, optionally with photos, videos, or voice notes
6. Revisit the dashboard to see profiles and recent sessions
7. Export or delete account data from settings if needed

## 7. What Tailmate Is Already Good At

At its current stage, Tailmate is strongest in these areas:

- persistent dog memory instead of one-off anonymous chat
- a consistent owner-facing web experience
- privacy-aware media handling
- product-grade operational support for identity, privacy, observability, and metrics

## 8. Current Boundaries and Honest Scope

Tailmate is still a pre-1.0 product and should be described honestly.
Current boundaries include:

- dog profiles are created and enriched through conversation rather than through a full manual profile-management console
- reviewed knowledge answers are limited to curated content that has already been prepared
- language preference is signposted in the product, but a full persisted preference flow is not yet exposed as a dedicated public feature
- the product foundation is strong, but the business surface is still evolving through controlled slices

## 9. Summary

Tailmate already functions as more than a simple chat interface.
It is a dog-care product foundation with memory, protected media handling, factual fallback, account control, privacy tooling, and operator visibility.

For a non-technical stakeholder, the clearest way to understand Tailmate today is:

- it helps dog owners ask questions in a familiar conversational way
- it remembers each dog and improves personalization over time
- it works through a maintained web application
- it includes the trust and operations layers needed for a real product, not just a prototype
