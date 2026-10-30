**ZIRO DIGITAL    /    ENGINEERING ASSIGNMENT**

IMPLEMENTATION BRIEF   /   ONE DELIVERY   /   SINGLE-ENGINEER EDITION

Ziro YouTube
Automation Engine

Team execution handbook | Hemu: Team Lead | Dolender (nickname: Dolu): Sole Implementation Engineer

A supervised proof of concept: Hemu assigns and tracks delivery; Dolender builds the entire repeatable YouTube content-to-video pipeline single-handedly, with approval gates and a safe publishing pathway.

| DECISION / One supervised sandbox build. Hemu is the project lead and owns assignment, tracking, quality and sign-off. Dolender implements everything. Do NOT change Ziro production Supabase, the current Content Studio, or the official YouTube channel. Founder approves any later integration. |
| --- |

| PROJECT FACT | VALUE |
| --- | --- |
| Sponsor / final approval | Ziro Digital │ Founder |
| Team lead / accountable owner | Hemu - sprint planning, delegation, reviews, risk escalation and sign-off |
| Implementation owner | Dolender - all code, tests, artifacts, demos and documentation |
| Shared output | One GitHub sandbox repository + runnable demo + exported videos + evidence pack |
| Reference skill bundle | 11-skill YouTube Agent repository (MIT-licensed) |
| Working mode | Sandbox only; approval gated; no live production publishing |

## Outcome standard

Dolender must demonstrate one complete content-to-video workflow. Hemu owns the technical plan, allocation, quality checks, tracking and final team sign-off. A prompt, static mockup or manually assembled sample alone does not satisfy delivery.

Primary demo topic: "Agentic AI for beginners: build an agent that solves a real student problem." The implementation must support changing the topic, audience, duration, format and CTA.

# 01  Assignment overview

Ziro already operates a production AI Content Studio for blogs and Instagram. This assignment tests a YouTube automation extension before integration. Deliver one prototype, engineered by Dolender under Hemu's technical leadership, with clear ownership and review evidence.

## Objectives

Generate grounded research, a 5-hook shortlist, a spoken script, scene-by-scene storyboard, titles, thumbnail concepts and SEO metadata from a content brief.

Produce at least one real playable YouTube Short and one 3-5-minute educational video in branded templates.

Require a deliberate human approval before any external YouTube upload; for the assignment, publishing is mocked or limited to an explicitly authorized sandbox test channel.

Generate caption files, a thumbnail, a production manifest and an auditable run history.

Show the actual effort, software dependencies, failure modes and expected usage costs.

## Expected inputs and outputs

| **INPUTS** | **OUTPUTS** |
| --- | --- |
| Topic + audience + learning outcome | Research brief with source URLs and factual checkpoints |
| Language + duration + format | 5 hooks with explanations; final spoken script |
| CTA + brand profile | Scene plan; voiceover; 16:9 or 9:16 MP4 |
| Brand assets / approved media | Thumbnail PNG; SRT/VTT subtitles; SEO metadata JSON |
| Reviewer decision | Versioned approval record; mock upload result; run log |

## Scope boundaries

| **STRICT GUARDRAILS** Do not use student testimonials, placement figures, earnings claims or partner logos unless supplied as approved facts/assets. Do not impersonate real people, reuse copyrighted footage without rights, or scrape logged-in YouTube data. Avoid real channel credentials in code or screenshots. |
| --- |

## Pass / fail definition

PASS: a reviewer enters a different topic, runs the workflow, approves the script, receives working video files and metadata, and can see clear errors and logs. FAIL: only static sample outputs, a manual one-off edit, fake analytics, hard-coded scripts, or an ability to publish without approval.

# 02  What exists already at Ziro

Reference only. The following was verified in the linked Ziro production Supabase project and GitHub repository on 27 October 2026:

| **EXISTING CAPABILITY** | **EVIDENCE / REUSE DIRECTION** |
| --- | --- |
| Admin dashboard and content library | /blog/admin; /blog/admin/content-library; existing blog editing and status views |
| Planning and approvals | content_autopilot_ideas, content_autopilot_settings, content_approval_inbox |
| Blog pipeline | Research, write, audit, image and publish Edge Functions |
| Instagram pipeline | Creative drafts and publish jobs with approval gates |
| Operational history | 506 content ideas, 487 Instagram drafts, 21 published blog posts, 169 published Instagram jobs |
| Known reliability issues | Some blog image-generation failures; last new content idea dated 15 Oct; scheduled-job names differ from cron expressions |

Do not repair or refactor those systems as part of this challenge. Production integration and reliability remediation are separate decisions after the prototype review.

**Ziro Content Studio dashboard code  **[https://github.com/mahibabu224/skill-stride-success/blob/main/src/pages/blog-admin/BlogAdminDashboard.tsx](https://github.com/mahibabu224/skill-stride-success/blob/main/src/pages/blog-admin/BlogAdminDashboard.tsx)

**Ziro content-autopilot planner  **[https://github.com/mahibabu224/skill-stride-success/blob/main/supabase/functions/content-autopilot-planner/index.ts](https://github.com/mahibabu224/skill-stride-success/blob/main/supabase/functions/content-autopilot-planner/index.ts)

**Ziro approval-contract migration  **[https://github.com/mahibabu224/skill-stride-success/blob/main/supabase/migrations/20260811144000_content_autopilot_approval_contract.sql](https://github.com/mahibabu224/skill-stride-success/blob/main/supabase/migrations/20260811144000_content_autopilot_approval_contract.sql)

**Ziro admin route (requires login)  **[https://ziro.digital/blog/admin](https://ziro.digital/blog/admin)

# 03  Source skill pack and installation

The independent foundation is Jake Schincariol's MIT-licensed YouTube Agent pack. It is an instruction-and-Python-toolkit collection, not an auto-publisher or video renderer. Keep its copyright/license attribution and inspect third-party scripts before executing.

**GitHub repository (primary)  **[https://github.com/Jakeschincariol/youtube-agent-skill](https://github.com/Jakeschincariol/youtube-agent-skill)

**README / installation steps  **[https://github.com/Jakeschincariol/youtube-agent-skill/blob/main/README.md](https://github.com/Jakeschincariol/youtube-agent-skill/blob/main/README.md)

**YouTube skills folder  **[https://github.com/Jakeschincariol/youtube-agent-skill/tree/main/skills](https://github.com/Jakeschincariol/youtube-agent-skill/tree/main/skills)

**Voice profile template  **[https://github.com/Jakeschincariol/youtube-agent-skill/blob/main/templates/voice.md](https://github.com/Jakeschincariol/youtube-agent-skill/blob/main/templates/voice.md)

### Claude Code project-local installation (run in your isolated project):

git clone https://github.com/Jakeschincariol/youtube-agent-skill.git
mkdir -p .claude/skills
cp -r youtube-agent-skill/skills/yt-* .claude/skills/

Alternative Claude Code plugin method: /plugin marketplace add Jakeschincariol/youtube-agent-skill then /plugin install youtube-agent. Verify availability in your local Claude version before relying on the commands.

## Which skills are useful?

| **COMMAND** | **ROLE IN THE PIPELINE** |
| --- | --- |
| /yt-viral | Research winning angles in the niche; check source and recency |
| /yt-plan | Weekly editorial calendar |
| /yt-script | Five hooks, script, retention beats |
| /yt-package | Paired title + thumbnail concept |
| /yt-edit | Transcript-based edit decision list |
| /yt-shorts | Short candidates from long-form content |
| /yt-seo | Description, keywords and suggested queries |
| /yt-chapters | Validated chapter markers |
| /yt-comment | Reply drafting - optional and always review |
| /yt-retention | Retention-drop diagnosis from exports |
| /yt-audit | Channel-review recommendations |

Pilot scope: prioritise /yt-script, /yt-package, /yt-shorts, /yt-seo and /yt-chapters. Analytics, comments and channel audits are stretch features until data access is authorized.

# 04  Team structure, delegation & tracking

Hemu is accountable for the project outcome and delegates all engineering tasks to Dolender, the sole implementation engineer. Dolender works in one isolated repository using feature branches per work area, pull requests, Hemu-reviewed merges and a single demonstration. Hemu may re-sequence tasks based on priority and workload.

| ROLE / ACCOUNTABILITY | EXPECTED CONTRIBUTION |
| --- | --- |
| Hemu │ Team lead (A) | Own the project board, milestone plan and interfaces. Assign all tasks, review PRs, enforce acceptance criteria, unblock work, inspect costs/security and present final status. |
| Dolender │ Engineer (R) | Owns both halves. Content half: content brief -> research -> 11 Claude skill orchestration -> hooks/scripts/storyboard -> titles, SEO and content-package outputs; document and test APIs. Execution half: video assets / TTS -> Remotion / FFmpeg rendering -> captions, thumbnail, approval workflow, retry/logging and export; document and test the run path. |
| Sequencing rule | Hemu may re-sequence tasks, but every task must have a due-date agreed in the kickoff, review evidence and Hemu as the named reviewer. Dolender owns integration and end-to-end QA. The content half and execution half meet at one Hemu-reviewed contract (content_package), so each half stays independently testable. |

## Delivery rules for the team

Hemu creates the task board; Dolender is the directly responsible engineer for every engineering task and owns implementation, tests, documentation and evidence until Hemu accepts it.

Dolender uses one sandbox repository with a feature branch per work area. Interfaces and contracts between the content half and the execution half must be reviewed by Hemu before downstream work depends on them.

The team must complete the common primary topic and run a second-topic generalization test. Hemu validates that switching topics requires no hard-coded content or manual repairs.

All demos must use genuine renders and real research links. Label any mocked publishing or analytics, keep sandbox secrets private and require Hemu to review work before founder presentation.

## 04.1  Hemu: management and accountability

At kickoff, Hemu creates a GitHub Project or equivalent Kanban board; reviews the existing Ziro Content Studio only as reference; sets delivery dates and names a single owner for every task. He reviews pull requests, runs milestone demos, records blockers, and signs off before the founder review.

Minimum manager cadence: 15-minute kickoff; daily asynchronous progress update from Dolender; one short sync per working day; Hemu review at each phase gate. Escalate blocking issues within one working day rather than silently extending milestones.

## 04.2  Task allocation (all engineering tasks: Dolender)

| **ISSUE** | **INITIAL OWNER** | **EXPECTED EVIDENCE** |
| --- | --- | --- |
| YT-01 | Hemu | Set up board, milestones, role allocation, acceptance criteria and no-production rules. |
| YT-02 | Dolender | Install/audit 11 YouTube skills; brand/voice instructions; dependency inventory. |
| YT-03 | Dolender | Topic intake, attributed source research, claim ledger and factual review. |
| YT-04 | Dolender | Hooks, script, shot-by-shot storyboard, title/thumbnail pairing, SEO and chapters. |
| YT-05 | Dolender | Narration / audio generation, licensed assets and brand motion templates. |
| YT-06 | Dolender | Short and long MP4 rendering, subtitles, resolution and QA previews. |
| YT-07 | Dolender | Approval and run-state UI/API, failure/retry, logs and download bundles. |
| YT-08 | Dolender | Integrate one pipeline; the content interface and the execution interface meet at one Hemu-reviewed contract. |
| YT-09 | Dolender | Second-topic regression test, sources and content accuracy evidence. |
| YT-10 | Dolender | System/negative tests, sandbox publishing stub, cost/latency report. |
| YT-11 | Hemu | Review all PRs, reproduce demo from README, log gaps and sign off acceptance. |
| YT-12 | Hemu | Show the team demo and submit scoped integration recommendation to founder. |

All engineering issues are assigned to Dolender; GitHub Issue assignees must always reflect this, with Hemu as reviewer on every issue.

## 04.3  Issue board and daily tracking

Board columns: Backlog -> Ready -> In Progress -> Blocked -> In Review -> Done. Every issue contains owner, priority, agreed due date, acceptance criteria, dependency, branch/PR link and evidence link.

Mark Done only when (1) code is merged after Hemu review, (2) tests pass, (3) the feature can be demonstrated and (4) the relevant evidence is attached. A successful pipeline step with missing artifacts is not Done.

Daily update template for the engineer: Yesterday completed [issue IDs + links] | Today [issue IDs] | Blockers [what is needed / by whom] | Evidence [PR, video, screenshot or logs] | Risk to milestone [yes/no]. Hemu posts a consolidated status (green / amber / red) with upcoming gate and blockers to the founder.

## 04.4  Milestone checkpoints and escalations

| **GATE** | **REQUIRED DEMO TO HEMU** | **DECISION** |
| --- | --- | --- |
| Gate A | One fresh installation and a visible assigned workboard. | Go / fix setup |
| Gate B | Two script packages with factual sources and Ziro voice profile. | Approve content engine / rework |
| Gate C | Real branded Short and 3-5 minute video, audio and subtitles. | Approve render / rework |
| Gate D | Approval controls, retries, failure handling, export package and tests. | Approve technical readiness / rework |
| Gate E | Recorded end-to-end walkthrough, costs and security checklist. | Hemu signs off; founder decides next step |

Blocker escalation: engineer reports reproduction steps, impacted issue, log/error, proposed fix and decision needed. Hemu resolves ownership/dependency issues or raises budget/credential/priority decisions to the founder. No credentials should be shared in tickets or chat.

# 05  Recommended technical design

Proposed logical chain: Content brief -> topic research -> factual review -> script/hooks -> script approval -> scene plan -> voice/assets -> video renderer -> QA preview -> approval -> mock publishing -> metrics stub.

## Suggested architecture

| **LAYER** | **CONTRACT / IMPLEMENTATION** |
| --- | --- |
| UI / CLI | Create project, edit brief, preview script/video, approve/reject, download deliverables, inspect run logs. |
| Orchestrator | Idempotent stage runner; durable state; retries with backoff; timeout and error classes; safe resume. |
| Research + language | Claude skills and source collection; each material claim linked to a URL and reviewed before narration. |
| TTS + media | Approved text -> voice audio; visual assets from owned or licensed media; no unsourced real-person likenesses. |
| Renderer | Remotion or FFmpeg; produce 1080x1920 Short and 1920x1080 long-form output. Validate duration/audio sync. |
| Storage | Persist only sanitized brief, generated files, signed URLs, hashes, version and approval history. |
| Publish adapter | Initial mock. Optional YouTube OAuth integration with sandbox channel and private uploads only after approval. |
| Analytics adapter | Start with mocked schema; live YouTube Analytics OAuth integration is optional. |

## Suggested state machine

draft -> researching -> research_review -> scripting -> script_review -> storyboarding -> rendering -> qa_review -> approved -> export_ready -> uploaded_private (optional)

Any stage may transition to failed with a retryable/non-retryable flag; rejection returns to the previous editable artifact. A live upload operation must never be called from draft, failed, rejected or unapproved states.

## Minimal data model

| **ENTITY** | **MINIMUM FIELDS** |
| --- | --- |
| projects | id, owner, topic, audience, language, format, target_seconds, CTA, status, created_at |
| sources | project_id, url, title, accessed_at, claim, verification_status |
| artifacts | project_id, type, version, storage_path, checksum, model_or_tool, created_at |
| approvals | project_id, stage, approver, decision, notes, timestamp, artifact_version |
| jobs | project_id, stage, status, retry_count, started_at, finished_at, error_code, cost_estimate |
| publishing | project_id, platform, channel_id, privacy, scheduled_at, provider_video_id, status |

This is a conceptual schema, not a production migration. Do not deploy it to Ziro's live database during the challenge.

# 06  Build milestones and demonstrations

| PHASE | ENGINEERING DELIVERY | HEMU GATE / EXIT EVIDENCE |
| --- | --- | --- |
| A - Setup & assignment | Sandbox repo, Issue board, installed skills, voice profile, system diagram, agreed contracts | Tasks assigned to Dolender; baseline runs from a fresh README |
| B - Content engine | Sources, five hooks, final script, storyboards, title/thumb and SEO package | Hemu checks sources, facts, reuse of skills and regenerated second topic |
| C - Video engine | Narration, branded scenes, captions, thumbnail, Short and long MP4 | Hemu verifies playback, dimensions, mobile readability, synchronization |
| D - Workflow and QA | Approval, run history, error/retry, exports, secure publishing stub | Hemu observes rejection, failed-job recovery, no unapproved upload |
| E - Team review | Demo recording, PRs, run log, tests, costs and limitations | Hemu closes accepted issues; founder reviews signed-off prototype |

## Mandatory demo outputs

A 45-75 second vertical Short (1080x1920, MP4) explaining one concrete Agentic AI use case.

A 3-5 minute horizontal video (1920x1080, MP4) with a concrete technical walkthrough or grounded illustrative example.

Each video: approved script, sources ledger, storyboard, captions, thumbnail image, title alternatives, description and CTA.

Full stage run log; recorded reviewer approval; an unsuccessful-job demo with recovery.

Second topic demonstration showing that the pipeline is reusable; the second topic need not be fully rendered if time-constrained, but its script and package must complete.

## Recommended example briefs

| **DEMO** | **TOPIC AND CTA** |
| --- | --- |
| Short | "What makes an AI agent different from a chatbot?" Audience: Indian students; language: English; CTA: Explore AI learning at ziro.digital. |
| Long | "Build a simple agent workflow for résumé feedback." Audience: Python beginners; clarify it is an illustrative educational build, not a real-world recruitment decision system. |
| Generalization | "Three practical GenAI portfolio projects for freshers." No unsupported placement or salary claims. |

# 07  Content quality & branding standard

## Ziro voice and audience

Audience: Indian students, early-career developers and career switchers. Tone: clear, credible, practical, energetic without hype. Emphasize real demonstrations and learning outcomes over generic AI news. Brand spoken as "ZAIRO" and written as "Ziro". Use supplied official Ziro logo and approved colors; do not redraw it from memory.

## Script structure

| **SHORT (45-75s)** | **LONG (3-5m)** |
| --- | --- |
| 0-3s: one sharp, defensible hook | 0-15s: hook + outcome |
| 3-10s: relevance to viewer | 15-45s: context/prerequisites |
| 10-45s: one worked example | 45-210s: demo or step-by-step build |
| 45-60s: practical takeaway | Final section: recap, limitation and next action |
| Closing: one simple CTA | Closing: CTA, sources and next learning path |

## Quality rules

No invented salaries, placements, student identities, partnerships, certifications, reach or other metrics.

For topical/current claims, collect publication date and citation. If reliable evidence is missing, remove or qualify the claim.

Use genuine screen captures for tool demos; do not generate interfaces that pretend to be real product workflows.

Maintain readable text inside mobile safe areas; subtitles must not overlap CTA or UI overlays.

Music, SFX, fonts, footage and images must be owned, licensed or otherwise permitted; include an asset-license ledger.

Keep original project assets and all render outputs; templates should support repeatable generation.

# 08  YouTube API, permissions and compliance

This assignment does not require live publishing. An optional sandbox integration may upload PRIVATE videos only after an authorized human approves the artifact and explicitly connects their own test channel.

## Google OAuth checklist

Create a separate Google Cloud project; enable YouTube Data API v3; configure OAuth consent and use a test account/test channel.

Use Google OAuth 2.0 authorization code flow with CSRF state and secure refresh-token storage; do not request a password or channel cookie.

Request minimum needed scopes. youtube.upload is appropriate for upload; add youtube.readonly or yt-analytics.readonly only if used.

Use resumable video upload; record response video_id, error codes, privacy state and duplicate-protection key.

New, unverified API projects may have uploaded videos restricted to private until a YouTube compliance audit is completed. Do not promise public scheduling in the POC.

Service-account flow is generally not suitable for ordinary channels. Use user OAuth authorization as documented by Google.

## AI and creator-policy gates

Review YouTube's realistic altered/synthetic media disclosure rules; label eligible AI content where applicable.

Never clone an identifiable person's voice or likeness without permission, and never imply a synthetic speaker is the actual founder.

Require fact checking, rights checking, brand checking and human approval before publishing.

## Failure conditions to simulate

| **FAILURE** | **EXPECTED BEHAVIOR** |
| --- | --- |
| Missing OAuth token | No upload attempt; clear connection warning; project stays safe. |
| Rate limit / temporary API error | Bounded retry and exponential backoff; no duplicate video. |
| Renderer timeout | Job marked failed; input artifacts retained; manual retry. |
| Rejected script | Do not render or upload; return to editable script stage. |
| Duplicate Publish click | One idempotent upload task, not two videos. |
| Unsourced factual claim | Block approval or flag for correction; retain reviewer decision. |

# 09  Testing & acceptance checklist

| **TEST** | **ACCEPTANCE CRITERION** |
| --- | --- |
| T01 - New brief | Topic, audience, language, CTA and duration persist and appear in generated outputs. |
| T02 - Skills reproducible | Skills execute after fresh setup; dependencies documented; no manual copy-paste dependency. |
| T03 - Factual traceability | Every non-trivial external statistic/claim has a source; invented claims are blocked. |
| T04 - Quality of script | 5 distinct hooks; logical progression; practical takeaways; no unsupported hype. |
| T05 - Short render | Play a complete 9:16 MP4 with readable captions and synced audio. |
| T06 - Long render | Play a complete 16:9 MP4 with chapter/scene progression and no broken frames. |
| T07 - Brand consistency | Official assets used; Ziro naming/pronunciation consistent; CTA correct. |
| T08 - Approval gating | Reject -> no upload; approve -> enables export/publish mock only. |
| T09 - Retry behavior | Force a failure; retry succeeds or terminates clearly; artifacts stay intact. |
| T10 - Portability | A second engineer can install and run from README and sample .env template. |
| T11 - Cost visibility | List services, approximate per-video input usage and separately metered API charges. |
| T12 - Data security | No hard-coded keys or production writes; least privilege; no sensitive data in logs. |

## Engineering evidence pack

The single team submission must include a README, architecture diagram, configuration template (no secrets), deployment/local-run instructions, asset licenses, test results, two MP4 files, content packages, a screen recording, linked GitHub Issues and reviewed PRs, a status log, a cost report and production-readiness notes. Hemu signs off the evidence pack.

# 10  Evaluation rubric - 100 points

| **CRITERION** | **POINTS** | **WHAT WE LOOK FOR** |
| --- | --- | --- |
| Research and factuality | 15 | Source quality, no invented claims, domain accuracy |
| Script and learning value | 20 | Hooks, structure, explanation, learner outcomes |
| Video finish and branding | 20 | Audio, visuals, captions, thumbnail, polish |
| End-to-end automation | 15 | Reproducible generation without manual patching |
| Approval UX and safety | 10 | Human gate, clear versioning and privacy controls |
| Reliability and repeatability | 10 | Retries, logs, second topic, reproducibility |
| Cost and technical choices | 5 | Transparent external dependencies and trade-offs |
| Documentation and demo | 5 | Clean repo, onboarding, evidence pack |

Hemu grades the prototype against the 100-point rubric and records pass/fail evidence. Founder review decides next steps: 85+ = candidate for integration spike; 70-84 = improve and retest; below 70 = prototype only. The score does not authorize production deployment.

## Founder review questions

Can it produce useful technical teaching videos or does it only generate generic slides?

Could one team member operate the system without the original builder present?

How long does one video actually take end to end, including review?

Which parts of the original 11 skills are truly reused, and which are custom?

What can safely be integrated into Ziro's existing Content Studio, without breaking blogs/Instagram?

# 11  Accounts, costs, and operating constraints

Ziro has stated that the Claude for Startups benefit includes 25 Claude Pro seats. These seats can support human developers using Claude and eligible Claude Code workflows, but an unattended service using the Claude API has separate entitlement/billing. Verify any startup-specific API credits in the company's actual agreement before assuming cost coverage.

| **RESOURCE** | **DEFAULT FOR THIS CHALLENGE** |
| --- | --- |
| Claude Pro seat | Developer-assisted building, planning and testing; obey plan limits. |
| Claude API key | Optional; use separately authorized Console/API credits and a spend cap. |
| YouTube credential | Not required for MVP. Sandbox OAuth only for optional private upload. |
| Voice generation | Use licensed TTS; Sarvam is an option for Telugu/Hindi/English; cost separately tracked. |
| Rendering compute | Local machine or isolated cloud worker; measure CPU, memory and runtime. |
| Storage | Local folder or separate sandbox bucket; no Ziro student data or production credentials. |
| Paid asset tools | Use free/approved samples first. Request approval for any spending. |

## Cost-report format

Report: LLM tokens/API requests, voice minutes/characters, render minutes and machine type, image-generation requests, storage size, network egress, YouTube API usage, manual review minutes, and total cost per video. Distinguish actual observed expenses from estimates and list the price page checked.

# 12  Resource directory - use these links

Primary source: the original skill pack. All other links below are documentation, implementation references or official policy resources; the engineers should confirm platform changes during development.

## Claude + source skill pack

**YouTube Agent Skill: GitHub  **[https://github.com/Jakeschincariol/youtube-agent-skill](https://github.com/Jakeschincariol/youtube-agent-skill)

**Original README / install  **[https://github.com/Jakeschincariol/youtube-agent-skill/blob/main/README.md](https://github.com/Jakeschincariol/youtube-agent-skill/blob/main/README.md)

**Voice template  **[https://github.com/Jakeschincariol/youtube-agent-skill/blob/main/templates/voice.md](https://github.com/Jakeschincariol/youtube-agent-skill/blob/main/templates/voice.md)

**Claude Agent Skills overview  **[https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)

**Claude Pro and API billing distinction  **[https://support.claude.com/en/articles/9876003-i-have-a-paid-claude-subscription-pro-max-team-or-enterprise-plans-why-is-claude-api-usage-billed-separately-from-my-paid-claude-plan](https://support.claude.com/en/articles/9876003-i-have-a-paid-claude-subscription-pro-max-team-or-enterprise-plans-why-is-claude-api-usage-billed-separately-from-my-paid-claude-plan)

## Video and audio production

**Remotion: rendering videos  **[https://www.remotion.dev/docs/render](https://www.remotion.dev/docs/render)

**FFmpeg: official documentation  **[https://ffmpeg.org/documentation.html](https://ffmpeg.org/documentation.html)

**Sarvam: TTS overview  **[https://docs.sarvam.ai/api/api-guides-tutorials/text-to-speech/overview](https://docs.sarvam.ai/api/api-guides-tutorials/text-to-speech/overview)

**Sarvam: API quickstart  **[https://docs.sarvam.ai/api/getting-started/quickstart](https://docs.sarvam.ai/api/getting-started/quickstart)

## Publishing, privacy and analytics

**Google Cloud Console  **[https://console.cloud.google.com/](https://console.cloud.google.com/)

**YouTube OAuth 2.0 web-server guide  **[https://developers.google.com/youtube/data/guides/auth/server-side-web-apps](https://developers.google.com/youtube/data/guides/auth/server-side-web-apps)

**YouTube video upload guide  **[https://developers.google.com/youtube/data/guides/uploading_a_video](https://developers.google.com/youtube/data/guides/uploading_a_video)

**YouTube videos.insert API  **[https://developers.google.com/youtube/data/reference/rest/v3/videos/insert](https://developers.google.com/youtube/data/reference/rest/v3/videos/insert)

**YouTube Analytics reports.query  **[https://developers.google.com/youtube/analytics/reference/reports/query](https://developers.google.com/youtube/analytics/reference/reports/query)

**YouTube API revision history / private-upload audit  **[https://developers.google.com/youtube/data/revision_history](https://developers.google.com/youtube/data/revision_history)

**YouTube AI-content disclosure guidance  **[https://support.google.com/youtube/answer/14328491?hl=en](https://support.google.com/youtube/answer/14328491?hl=en)

## Infrastructure and Ziro internal patterns

**Supabase scheduling Edge Functions  **[https://supabase.com/docs/guides/functions/schedule-functions](https://supabase.com/docs/guides/functions/schedule-functions)

**Supabase Cron documentation  **[https://supabase.com/docs/guides/cron](https://supabase.com/docs/guides/cron)

**Ziro private code: blog dashboard  **[https://github.com/mahibabu224/skill-stride-success/blob/main/src/pages/blog-admin/BlogAdminDashboard.tsx](https://github.com/mahibabu224/skill-stride-success/blob/main/src/pages/blog-admin/BlogAdminDashboard.tsx)

**Ziro private code: autopilot planner  **[https://github.com/mahibabu224/skill-stride-success/blob/main/supabase/functions/content-autopilot-planner/index.ts](https://github.com/mahibabu224/skill-stride-success/blob/main/supabase/functions/content-autopilot-planner/index.ts)

**Ziro private code: blog publish worker  **[https://github.com/mahibabu224/skill-stride-success/blob/main/supabase/functions/content-autopilot-blog-publish-worker/index.ts](https://github.com/mahibabu224/skill-stride-success/blob/main/supabase/functions/content-autopilot-blog-publish-worker/index.ts)

Private GitHub links require authorized repository access. Refer to those files only; do not copy credentials, customer data or production service-role code into public prototype repos.

# 13  Team submission & management review

## Folder structure to submit

ziro-youtube-automation-poc/
  README.md                      # setup, run, limitations
  architecture/                 # system diagram + decisions
  src/                          # skill orchestration, app, workers
  templates/                    # Ziro brand and video layouts
  tests/                        # automated tests + manual QA evidence
  outputs/demo-short/            # MP4, SRT, thumbnail, metadata, sources
  outputs/demo-long/             # MP4, SRT, thumbnail, metadata, sources
  outputs/second-topic/          # script and package
  reports/                       # costs, metrics, workboard, sign-off
  .env.example                   # names only, no secrets

## Demo meeting format

20-minute review chaired by Hemu: 3 min architecture and task completion (Hemu); 13 min single engineering demo by Dolender covering research/scripts/metadata, then rendering, approvals and failure recovery; Hemu presents test results, spend, blockers and integration recommendation (4 min).

## Final deliverables checklist

[ ] GitHub repository and exact commit SHA shared with founder

[ ] Repeatable installation instructions and .env.example with no secrets

[ ] Two playable sample MP4 files, captions, thumbnails and SEO packages

[ ] Evidence of five hooks, research sources and approval record

[ ] At least one successful run plus one intentional failure/retry

[ ] Second-topic output demonstrating reusable generation

[ ] Cost breakdown, licenses, limitations, Hemu sign-off and recommendation to founder

Internal engineering brief   |   28 October 2026
