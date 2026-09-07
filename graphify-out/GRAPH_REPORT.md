# Graph Report - harness-ai  (2026-09-06)

## Corpus Check
- Large corpus: 527 files · ~833,574 words. Semantic extraction will be expensive (many Claude tokens). Consider running on a subfolder.

## Summary
- 3936 nodes · 8966 edges · 257 communities (151 shown, 97 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 508 edges (avg confidence: 0.9)
- Token cost: 3,793,025 input · 199,642 output

## Community Hubs (Navigation)
- Schema Migration & DB Tests
- Chat Session Acceptance Criteria
- Chat UI Story Plans
- Admin State Load & Auth Tests
- Admin Row Formatting
- Audit Aggregate Read Functions
- Admin Shell Import Smoke Tests
- Chat Session CRUD
- Register Table Components
- ChatState Session Actions
- Audit Log Storage & PII Columns
- Admin Row & Figure Models
- Users Table CRUD
- Session Title & Activity Formatting
- ChatState Error Handling Tests
- Chat Sessions Service Tests
- Database Layer Plans
- Session Ownership Tests
- Shared libSQL Client
- PII Redaction Epic
- RBAC Design Rationale
- Admin Copy & State Tests
- Register Filter & Sort Assertions
- Query Router Tests
- Authorization Service
- Turso Migration CLI Tests
- Session ID Over POST /query
- Startup Failure Classification
- Turso Migration Reports
- Chat Sessions Service Module
- Session Create & Count Tests
- RBAC Story Board
- Reflex Chat UI Epic
- Chat Correctness Foundations
- Request & Response Schemas
- Chat Message Store
- AdminState Class
- Admin Console Risk Mitigations
- Harness IA Plans & Conventions
- Admin Console Story Chain
- Token Hashing & Identity
- PII End-to-End Integration Tests
- Query Pipeline & Policy Refusal
- Pipeline Session Passthrough Tests
- Session Reports & Formatting
- Summary Tally Sheet Components
- Chat Message Model & Persistence
- Frontend Package Manifest
- Admin Console Design Plans
- Register Scope & Count Copy
- Session Rail Component
- Duplicate Detection Service
- New Chat & Transcript Restore
- Admin Palette Tests
- RBAC Ingress Parity Tests
- Turso Migration Story Board
- Presidio Redactor Engine
- Admin Route & Copy Assertions
- PII Dedup Isolation Tests
- Console Render Invariant Tests
- Register State & Empty Panels
- Register Column & Verdict Ink
- User Lookup Functions
- Chat Pipeline Integration Stories
- OpenRouter Client
- Migration Fingerprint & Outcome
- Database URL Test Fixtures
- Delegating Connection Wrapper
- Admin Pages & Shell
- Chat UI Redesign Mechanisms
- Audit Logger Tests
- Chat Copy Tests
- Admin Console Reports
- PII & Chat UI Story Boards
- Connection Wrapper
- Turso Migration Script
- Pipeline Integration Tests
- Chat Sessions Story Board
- Turso Config & Startup Guard
- FastAPI App Startup Tests
- Audit Session ID Tests
- Session Ordering & Deletion Tests
- Frontend Runtime Dependencies
- Env Example Config Tests
- Database URL Validation Tests
- Harness IA Story Board
- Chat UI Startup Guard Tests
- Contrast & Accessibility Tests
- Untouched App Guard Tests
- Row Detail Disclosure
- Session Management Plans
- Stale Client Recovery
- Session Ownership Signature
- Reflex Chat UI Story Board
- Session ID Threading Stories
- Admin Copy Constant Tests
- Settings & Env Example
- Cursor Wrapper
- Row Wrapper
- Summary Figure Render Tests
- Admin Endpoints & Auth Reports
- Database Reachability Probe
- Summary Sheet Tests
- Reflex Instance Harness
- Users Table & Bootstrap CLI
- Connection Layer Swap
- Batched Summary Snapshot
- Chat Table DDL & Session ID
- Harness IA MVP Concepts
- Session Rail Spine & Shell
- Test Provenance & Client Recovery
- Chat Session Listing
- Frontend Dev Dependencies
- Authz Permission Matrix
- Chat Component Import Tests
- Session Rail Tests
- Session Summary Model Plans
- Forbidden Response & Login
- DDL Column Verification
- Config Boundary Tests
- Transcript Persist & Restore Plans
- RBAC Config & Model Allowlist
- Rail Source AST Probe
- Session Ownership 403 Plans
- Additive Audit Column Migration
- Auth Dependencies & Endpoint Gates
- ChatState History Flag
- Settings Field Validators
- Reflex Agent Skills
- History Flag Absent Rail Tests
- Project Scaffolding Reports
- Driver Spike & SQL Aggregation
- Rail Tokens & Copy Rules
- Audit & Figure Projection Tests
- Control Focus Ring Tests
- Register Match Arm Tests
- Identity Resolution Report
- Query Router Auth & Docs
- Safe Endpoint Redaction
- Test Removal Guard Plan
- Workflow Slash Commands
- Exception Characterization
- Module-Owned Storage Errors
- Feature Flag Switches
- Relative Time Humanizer Tests
- Pinned Suite Guard Tests
- Sort Direction Mark Tests
- Route Reservation Tests
- Frontend Build Scripts
- Raw Audit Retention Test
- Component Import Probe
- Component Import Probe
- Request Schema Report
- Agent Template & Rules Command
- Frontend Overrides
- Token In Body Refusal Test
- Bootstrap Guard Default Test
- Bootstrap Guard Override Test
- Chat History Toggle Test
- PII Badge Risk Test
- Upstream Error Risk Test
- Duplicate Timestamp Copy Test
- Admin Copy Template Test
- Filter Joiner Test
- Refresh Stamp Test
- Refusal Message Test
- Untitled Fallback Test
- Load Notice Copy Test
- Delete Confirmation Copy Test
- Delete Action Restraint Test
- Rail Vocabulary Test
- Rail Failure Copy Test
- Keyboard Reachability Test
- Nothing Recorded State Test
- No Matches Clear Test
- No Matches Sentence Test
- Default Table State Test
- Empty State Type Test
- Table Arm Default Test
- Grid Constant Test
- Named Control Test
- Module Import Smoke Test
- Register Factory Test
- Register Load Guard Test
- Register Colour Boundary Test
- Register Tint Test
- Scope Line Bound Test
- Register Source Discovery Test
- Literal Hex Colour Test
- Body Face Reservation Test
- Data Face Dominance Test
- Register Focus Ring Test
- Table Scroll Test
- Preview Leak Boundary Test
- Error Ordering Test
- PII Indicator Test
- Disclosure Render Test
- Disclosure Button Test
- Disclosure Open State Test
- Row Toggle Isolation Test
- Disclosure Wrap Test
- Disclosure Continuity Test
- Row Model Field Test
- Filter Strip Test
- Verdict Filter Toggle Test
- Free Text Field Test
- Debounce Performance Test
- Filtered Count Test
- Clear Action Test
- Sort Control Coverage Test
- Timestamp Default Sort Test
- Direction Mark Test
- Rail Header Structure Test
- Spine Mark Construction Test
- Delete Sentence Test
- Rail Render Scope Test
- Rail Token File Test
- User Facing String Test
- Type Role Test
- Three Rail States Test
- Fault State Precedence Test
- Row Affordance Test
- Row Weight Uniformity Test
- No Dialog Rail Test
- Flag Naming Exemption Test
- Summary Import Smoke Test
- Summary Factory Test
- Summary Load Guard Test
- Summary Block Structure Test
- Completion Note Test
- Success Rate Wording Test
- Summary Refresh Stamp Test
- Summary Scope Note Test
- Ranked List Cut Test
- Empty Sheet Total Test
- Summary Colour Boundary Test
- Summary Tint Test
- Summary Source Discovery Test
- Summary Body Face Test
- Summary Data Face Test
- Ranked Items Test
- Summary Focus Ring Test
- Sheet Scroll Test
- Sheet Navigation Test
- Figure Indent Test
- Install Command
- Prime Command
- Review Command

## God Nodes (most connected - your core abstractions)
1. `ChatState` - 101 edges
2. `Identity` - 99 edges
3. `AuditLog` - 96 edges
4. `get_connection()` - 88 edges
5. `get_audit_log()` - 87 edges
6. `_make_state()` - 87 edges
7. `User` - 81 edges
8. `AdminState` - 81 edges
9. `insert_audit_log()` - 78 edges
10. `insert_user()` - 77 edges

## Surprising Connections (you probably didn't know these)
- `_Row/_Cursor/_Connection wrappers restore named access and iteration the raw driver lacks` --rationale_for--> `_Connection`  [EXTRACTED]
  .agents/plans/PRD-007-turso-migration/completed/STORY-006-libsql-connection-layer.plan.md → app/db/database.py
- `check_database_reachable(): one SELECT 1 at init_db() top, classifies unreachable vs auth failure` --rationale_for--> `check_database_reachable()`  [EXTRACTED]
  .agents/plans/PRD-007-turso-migration/completed/STORY-008-startup-guard.plan.md → app/db/database.py
- `_row_to_audit_log serves two row shapes (_Row off the wire and the summary_snapshot json dict) -- a new column must be added to both inputs` --rationale_for--> `_row_to_audit_log()`  [EXTRACTED]
  .agents/plans/PRD-008-chat-sessions/completed/STORY-008-audit-log-session-id.plan.md → app/db/database.py
- `Recursive CTE splits comma-separated pii_entities server-side instead of transferring every row` --rationale_for--> `top_pii_entities()`  [EXTRACTED]
  .agents/plans/PRD-007-turso-migration/completed/STORY-009-top-pii-entities-sql-aggregation.plan.md → app/db/database.py
- `summary_snapshot(): ten scalar/json_group_array subqueries in one SELECT, no client batch API exists` --rationale_for--> `summary_snapshot()`  [EXTRACTED]
  .agents/plans/PRD-007-turso-migration/completed/STORY-010-batched-summary-read.plan.md → app/db/database.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Harness IA PRD Sequential Epic Chain** — agents_prds_prd_001_harness_ia_prd, agents_prds_prd_002_reflex_chat_ui_prd, agents_prds_prd_003_pii_redaction_prd, agents_prds_prd_004_chat_ui_redesign_prd, agents_prds_prd_005_rbac_prd, agents_prds_prd_006_admin_console_prd, agents_prds_prd_007_turso_migration_prd, agents_prds_prd_008_chat_sessions_prd [EXTRACTED 1.00]
- **Required-Parameter Structural Enforcement Pattern** — agents_prds_prd_002_reflex_chat_ui_prd_run_query, agents_prds_prd_005_rbac_prd_enforcement_by_signature, agents_prds_prd_008_chat_sessions_prd_session_ownership [INFERRED 0.85]
- **Shared Chat/Console Verdict Vocabulary** — agents_prds_prd_004_chat_ui_redesign_prd_six_outcome, agents_prds_prd_006_admin_console_prd_verdict_derivation, agents_prds_prd_008_chat_sessions_prd_session_rail [EXTRACTED 1.00]
- **Function-Based Service Module Convention Family** — agents_plans_prd_001_harness_ia_completed_story_004_duplicate_detection_service_plan, agents_plans_prd_001_harness_ia_completed_story_005_pattern_detection_service_plan, agents_plans_prd_001_harness_ia_completed_story_006_audit_logging_service_plan, agents_plans_prd_001_harness_ia_completed_story_007_openrouter_client_plan [INFERRED 0.85]
- **Admin-Gated Endpoints Sharing require_admin_token** — agents_plans_prd_001_harness_ia_completed_story_009_admin_auth_middleware_plan, agents_plans_prd_001_harness_ia_completed_story_010_get_audit_endpoint_plan, agents_plans_prd_001_harness_ia_completed_story_011_get_stats_endpoint_plan [EXTRACTED 1.00]
- **Chat-to-API Pipeline Parity Guarantee** — agents_plans_prd_002_reflex_chat_ui_completed_story_001_shared_query_pipeline_extraction_plan, agents_plans_prd_002_reflex_chat_ui_completed_story_006_wire_chatstate_to_pipeline_plan, agents_plans_prd_002_reflex_chat_ui_completed_story_007_chat_pipeline_test_suite_plan [EXTRACTED 1.00]
- **PRD-003 in-pipeline redaction chain (redactor service -> input redaction -> output redaction -> response signal)** — _agents_plans_prd_003_pii_redaction_completed_story_001_pii_redactor_service_plan_story, _agents_plans_prd_003_pii_redaction_completed_story_005_pipeline_input_redaction_plan_story, _agents_plans_prd_003_pii_redaction_completed_story_006_pipeline_output_redaction_plan_story, _agents_plans_prd_003_pii_redaction_completed_story_007_query_response_pii_signal_plan_story [EXTRACTED 0.95]
- **PRD-004 message-kind discriminated rendering system (ChatMessage model, metadata population, copy module, rx.match dispatch)** — _agents_plans_prd_004_chat_ui_redesign_completed_story_004_chat_message_model_plan_story, _agents_plans_prd_004_chat_ui_redesign_completed_story_005_send_populates_outcome_metadata_plan_story, _agents_plans_prd_004_chat_ui_redesign_completed_story_007_copy_module_plan_story, _agents_plans_prd_004_chat_ui_redesign_completed_story_008_bubble_renderers_match_dispatch_plan_story [EXTRACTED 0.95]
- **PRD-003 audit telemetry read/write loop (schema, writer, admin-endpoint reader)** — _agents_plans_prd_003_pii_redaction_completed_story_003_audit_log_pii_schema_plan_story, _agents_plans_prd_003_pii_redaction_completed_story_004_audit_logger_pii_telemetry_plan_story, _agents_plans_prd_003_pii_redaction_completed_story_009_audit_stats_pii_endpoints_plan_story [EXTRACTED 0.90]
- **RBAC Control Plane (Identity -> Authz -> Pipeline -> Dependencies -> Router)** — agents_plans_prd_005_rbac_completed_story_003_identity_resolution_plan_doc, agents_plans_prd_005_rbac_completed_story_006_authz_permission_matrix_plan_doc, agents_plans_prd_005_rbac_completed_story_010_pipeline_identity_authorization_plan_doc, agents_plans_prd_005_rbac_completed_story_012_auth_dependencies_plan_doc, agents_plans_prd_005_rbac_completed_story_013_query_router_authentication_plan_doc [INFERRED 0.85]
- **Audit Log Schema Evolution (PII columns to RBAC columns)** — agents_plans_prd_005_rbac_completed_story_001_additive_audit_log_migration_plan_doc, agents_plans_prd_005_rbac_completed_story_002_users_table_schema_plan_doc, agents_plans_prd_005_rbac_completed_story_009_audit_rbac_columns_plan_doc [INFERRED 0.85]
- **Dual Ingress Authorization Parity (HTTP and Chat UI)** — agents_plans_prd_005_rbac_completed_story_010_pipeline_identity_authorization_plan_doc, agents_plans_prd_005_rbac_completed_story_013_query_router_authentication_plan_doc, agents_plans_prd_005_rbac_completed_story_014_chat_ui_login_plan_doc, agents_plans_prd_005_rbac_completed_story_017_rbac_test_suite_plan_doc [INFERRED 0.85]
- **Computed vars reading self.X in-body (Reflex auto-dependency contract)** — chat_ui_chat_ui_admin_state_visible_rows, chat_ui_chat_ui_admin_state_register_scope, chat_ui_chat_ui_admin_state_register_filtered, chat_ui_chat_ui_admin_state_register_state, chat_ui_chat_ui_admin_state_summary_state [INFERRED 0.85]
- **Verdict-keyed rx.match dispatch across the console** — chat_ui_chat_ui_admin_formatting_derive_verdict, chat_ui_chat_ui_components_register_verdict_tag, chat_ui_chat_ui_components_register_stamp_margin, chat_ui_chat_ui_admin_state_register_state [INFERRED 0.80]
- **STORY-019 quality-floor pass over the shell, register and summary** — _agents_plans_prd_006_admin_console_completed_story_019_quality_floor_and_critique_plan_doc, chat_ui_chat_ui_components_admin_shell_admin_masthead, chat_ui_chat_ui_components_register_register, chat_ui_chat_ui_components_summary_summary, _agents_plans_prd_006_admin_console_completed_story_019_quality_floor_and_critique_plan_quality_floor [INFERRED 0.75]
- **Batched admin-summary read pipeline (STORY-009 through STORY-012)** — agents_plans_prd_007_turso_migration_completed_story_009_top_pii_entities_sql_aggregation_plan, agents_plans_prd_007_turso_migration_completed_story_010_batched_summary_read_plan, agents_plans_prd_007_turso_migration_completed_story_011_stats_endpoint_batched_plan, agents_plans_prd_007_turso_migration_completed_story_012_admin_console_batched_reads_plan [INFERRED 0.85]
- **Chat-session ownership-as-signature discipline (STORY-004 through STORY-007)** — agents_plans_prd_008_chat_sessions_completed_story_004_session_crud_functions_plan, agents_plans_prd_008_chat_sessions_completed_story_005_message_store_functions_plan, agents_plans_prd_008_chat_sessions_completed_story_006_chat_sessions_service_plan, agents_plans_prd_008_chat_sessions_completed_story_007_ownership_signature_guard_plan [INFERRED 0.85]
- **Core libSQL driver abstraction chain: spike decision, error surface, connection swap** — agents_plans_prd_007_turso_migration_completed_story_001_libsql_driver_spike_plan, agents_plans_prd_007_turso_migration_completed_story_004_module_owned_error_surface_plan, agents_plans_prd_007_turso_migration_completed_story_006_libsql_connection_layer_plan [INFERRED 0.85]
- **PRD-008 chat send/persist/restore/manage flow** — _agents_plans_prd_008_chat_sessions_completed_story_013_chat_state_session_list_and_lazy_create_plan_doc, _agents_plans_prd_008_chat_sessions_completed_story_014_transcript_persistence_write_plan_doc, _agents_plans_prd_008_chat_sessions_completed_story_015_transcript_restore_plan_doc, _agents_plans_prd_008_chat_sessions_completed_story_016_session_rename_delete_logout_plan_doc [INFERRED 0.85]
- **PRD-008 session rail surface (data model, tokens/copy, component)** — _agents_plans_prd_008_chat_sessions_completed_story_012_session_summary_and_formatting_plan_doc, _agents_plans_prd_008_chat_sessions_completed_story_017_rail_tokens_and_copy_plan_doc, _agents_plans_prd_008_chat_sessions_completed_story_018_session_rail_component_plan_doc [INFERRED 0.85]
- **PRD-001 POST /query interception pipeline services** — _agents_reports_prd_001_harness_ia_story_004_duplicate_detection_service_report_doc, _agents_reports_prd_001_harness_ia_story_005_pattern_detection_service_report_doc, _agents_reports_prd_001_harness_ia_story_006_audit_logging_service_report_doc, _agents_reports_prd_001_harness_ia_story_007_openrouter_client_report_doc, _agents_reports_prd_001_harness_ia_story_008_post_query_pipeline_report_doc [EXTRACTED 1.00]
- **Full PII Redaction Pipeline (Adapter, Input, Output, Signal, Audit)** — _agents_reports_prd_003_pii_redaction_story_001_pii_redactor_service_report_presidio_pii_redactor_adapter, _agents_reports_prd_003_pii_redaction_story_005_pipeline_input_redaction_report_input_redaction_fail_closed, _agents_reports_prd_003_pii_redaction_story_006_pipeline_output_redaction_report_output_redaction_fail_closed, _agents_reports_prd_003_pii_redaction_story_007_query_response_pii_signal_report_pii_redacted_signal_field, _agents_reports_prd_003_pii_redaction_story_003_audit_log_pii_schema_report_audit_logs_pii_telemetry_columns [INFERRED 0.85]
- **Chat UI Message Flow (Identity Gate, Background Event, Shared Pipeline)** — _agents_reports_prd_002_reflex_chat_ui_story_005_session_user_id_entry_report_user_id_entry_gate, _agents_reports_prd_002_reflex_chat_ui_story_006_wire_chatstate_to_pipeline_report_chatstate_send_background_event, _agents_reports_prd_002_reflex_chat_ui_story_001_shared_query_pipeline_extraction_report_run_query_pipeline [INFERRED 0.85]
- **Docker/Lifespan Integration Pattern Across PRDs** — _agents_reports_prd_002_reflex_chat_ui_story_003_mount_fastapi_single_port_report_api_transformer_single_port_mount, _agents_reports_prd_002_reflex_chat_ui_story_008_docker_single_port_packaging_report_docker_multistage_single_port_packaging, _agents_reports_prd_003_pii_redaction_story_011_docker_image_spacy_model_report_docker_image_spacy_model_bake, _agents_reports_prd_003_pii_redaction_story_002_startup_nlp_model_loading_report_pii_redaction_lifespan_warmload [INFERRED 0.85]
- **PRD-004 Chat UI Redesign epic story set** — _agents_reports_prd_004_chat_ui_redesign_story_001_async_run_query_offload_report_async_to_thread_offload, _agents_reports_prd_004_chat_ui_redesign_story_002_exhaustive_exception_handling_report_exhaustive_exception_handling, _agents_reports_prd_004_chat_ui_redesign_story_003_pending_state_flag_report_pending_state_flag, _agents_reports_prd_004_chat_ui_redesign_story_004_chat_message_model_report_chatmessage_model, _agents_reports_prd_004_chat_ui_redesign_story_005_send_populates_outcome_metadata_report_outcome_metadata_population, _agents_reports_prd_004_chat_ui_redesign_story_007_copy_module_report_copy_module, _agents_reports_prd_004_chat_ui_redesign_story_008_bubble_renderers_match_dispatch_report_bubble_dispatch_rx_match, _agents_reports_prd_004_chat_ui_redesign_story_009_pii_badge_report_pii_badge, _agents_reports_prd_004_chat_ui_redesign_story_010_success_metadata_footer_report_success_metadata_footer, _agents_reports_prd_004_chat_ui_redesign_story_011_duplicate_relative_time_report_duplicate_relative_time, _agents_reports_prd_004_chat_ui_redesign_story_012_pending_indicator_composer_lock_report_pending_indicator_composer_lock, _agents_reports_prd_004_chat_ui_redesign_story_013_auto_scroll_newest_report_auto_scroll_newest, _agents_reports_prd_004_chat_ui_redesign_story_014_shell_header_empty_state_report_shell_header_empty_state, _agents_reports_prd_004_chat_ui_redesign_story_015_user_id_validation_report_user_id_validation, _agents_reports_prd_004_chat_ui_redesign_story_016_model_selector_allowlist_report_model_selector_allowlist, _agents_reports_prd_004_chat_ui_redesign_story_017_device_user_agent_capture_report_device_user_agent_capture, _agents_reports_prd_004_chat_ui_redesign_story_018_retry_and_edit_resend_report_retry_and_edit_resend, _agents_reports_prd_004_chat_ui_redesign_story_019_six_outcome_regression_verification_report_six_outcome_regression_verification [EXTRACTED 1.00]
- **Bubble rendering system (ChatMessage model, copy, dispatch, badges, footer, timing)** — _agents_reports_prd_004_chat_ui_redesign_story_004_chat_message_model_report_chatmessage_model, _agents_reports_prd_004_chat_ui_redesign_story_007_copy_module_report_copy_module, _agents_reports_prd_004_chat_ui_redesign_story_008_bubble_renderers_match_dispatch_report_bubble_dispatch_rx_match, _agents_reports_prd_004_chat_ui_redesign_story_009_pii_badge_report_pii_badge, _agents_reports_prd_004_chat_ui_redesign_story_010_success_metadata_footer_report_success_metadata_footer, _agents_reports_prd_004_chat_ui_redesign_story_011_duplicate_relative_time_report_duplicate_relative_time [INFERRED 0.85]
- **Async request lifecycle: offload, exhaustive handling, pending guard, indicator, recovery** — _agents_reports_prd_004_chat_ui_redesign_story_001_async_run_query_offload_report_async_to_thread_offload, _agents_reports_prd_004_chat_ui_redesign_story_002_exhaustive_exception_handling_report_exhaustive_exception_handling, _agents_reports_prd_004_chat_ui_redesign_story_003_pending_state_flag_report_pending_state_flag, _agents_reports_prd_004_chat_ui_redesign_story_012_pending_indicator_composer_lock_report_pending_indicator_composer_lock, _agents_reports_prd_004_chat_ui_redesign_story_018_retry_and_edit_resend_report_retry_and_edit_resend [INFERRED 0.85]
- **app/services/authz.py evolution across STORY-006/007/011/016** — _agents_reports_prd_005_rbac_story_006_authz_permission_matrix_report_authz_module, _agents_reports_prd_005_rbac_story_007_roles_file_override_report_load_function, _agents_reports_prd_005_rbac_story_011_model_allowlist_and_byok_report_authorize_model_function, _agents_reports_prd_005_rbac_story_016_startup_bootstrap_guard_report_check_bootstrap [INFERRED 0.85]
- **RBAC enforcement spanning matrix, pipeline, dependency, and router layers** — _agents_reports_prd_005_rbac_story_006_authz_permission_matrix_report_authorize_function, _agents_reports_prd_005_rbac_story_010_pipeline_identity_authorization_report_run_query_step0, _agents_reports_prd_005_rbac_story_012_auth_dependencies_report_require_permission, _agents_reports_prd_005_rbac_story_013_query_router_authentication_report_query_router_auth [INFERRED 0.85]
- **Chat UI explicit handling of a policy-refused query** — _agents_reports_prd_005_rbac_story_008_forbidden_response_schema_report_query_blocked_forbidden_response, _agents_reports_prd_005_rbac_story_014_chat_ui_login_report_render_forbidden, _agents_reports_prd_005_rbac_story_014_chat_ui_login_report_login_function [INFERRED 0.85]
- **The app/ baseline drift investigation thread (commit 3f553f2), traced across stories to its resolution** — concept_prd006_app_baseline_drift, _agents_reports_prd_006_admin_console_story_007_register_theme_tokens_report, _agents_reports_prd_006_admin_console_story_009_admin_shell_and_gate_report, _agents_reports_prd_006_admin_console_story_015_summary_tally_sheet_report, _agents_reports_prd_006_admin_console_story_018_render_invariant_tests_report, _agents_reports_prd_006_admin_console_story_020_untouched_app_regression_report [INFERRED 0.85]
- **The admin console's audit-row data pipeline: AuditLog to_audit_row -> AuditRow -> AdminState.load -> visible_rows -> register()** — chat_ui_chat_ui_admin_formatting_to_audit_row, chat_ui_chat_ui_admin_models_auditrow, chat_ui_chat_ui_admin_state_load, chat_ui_chat_ui_admin_state_visible_rows, chat_ui_chat_ui_components_register_register [INFERRED 0.85]
- **Console surfaces bound by the no-tint/no-accent rule (Risk 6): only hairlines, type and the four verdict inks** — concept_prd006_risk6_no_tint_no_accent, chat_ui_chat_ui_components_register_register, chat_ui_chat_ui_components_summary_summary, chat_ui_chat_ui_components_admin_shell_admin_masthead [INFERRED 0.80]
- **STREAM_EXPIRED Shared-Client Idle-Stream Investigation** — _agents_reports_prd_007_turso_migration_story_009_top_pii_entities_sql_aggregation_report_stream_expired_issue, _agents_reports_prd_007_turso_migration_story_009_top_pii_entities_sql_aggregation_report_document, _agents_reports_prd_007_turso_migration_story_012_admin_console_batched_reads_report_document, _agents_reports_prd_007_turso_migration_story_013_data_migration_script_report_document, _agents_reports_prd_007_turso_migration_story_015_readme_and_deployment_docs_report_document, _agents_reports_prd_007_turso_migration_story_016_two_instance_smoke_test_report_document [INFERRED 0.85]
- **Chat Session Ownership Guarantee Chain** — _agents_reports_prd_008_chat_sessions_story_004_session_crud_functions_report_document, _agents_reports_prd_008_chat_sessions_story_005_message_store_functions_report_document, _agents_reports_prd_008_chat_sessions_story_006_chat_sessions_service_report_document, _agents_reports_prd_008_chat_sessions_story_007_ownership_signature_guard_report_document [EXTRACTED 1.00]
- **libSQL Driver Limitation Workarounds** — _agents_reports_prd_007_turso_migration_story_001_driver_decision_libsql_client_choice, _agents_reports_prd_007_turso_migration_story_006_libsql_connection_layer_report_document, _agents_reports_prd_007_turso_migration_story_009_top_pii_entities_sql_aggregation_report_document, _agents_reports_prd_007_turso_migration_story_010_batched_summary_read_report_document, _agents_reports_prd_007_turso_migration_story_013_data_migration_script_report_document [INFERRED 0.85]
- **Chat Session Persistence and Restore Pipeline** — agents_reports_prd_008_chat_sessions_story_013_chat_state_session_list_and_lazy_create_report, agents_reports_prd_008_chat_sessions_story_014_transcript_persistence_write_report, agents_reports_prd_008_chat_sessions_story_015_transcript_restore_report [INFERRED 0.85]
- **Session Rail UI Feature Build** — agents_reports_prd_008_chat_sessions_story_012_session_summary_and_formatting_report, agents_reports_prd_008_chat_sessions_story_017_rail_tokens_and_copy_report, agents_reports_prd_008_chat_sessions_story_018_session_rail_component_report [INFERRED 0.85]
- **8-Step Query Interception Pipeline Components** — agents_stories_prd_001_harness_ia_story_004_duplicate_detection_service, agents_stories_prd_001_harness_ia_story_005_pattern_detection_service, agents_stories_prd_001_harness_ia_story_006_audit_logging_service, agents_stories_prd_001_harness_ia_story_007_openrouter_client, agents_stories_prd_001_harness_ia_story_008_post_query_pipeline [EXTRACTED 1.00]
- **Chat Pipeline Wiring Flow (run_query extraction -> session identity -> ChatState.send wiring)** — agents_stories_prd_002_reflex_chat_ui_story_001_shared_query_pipeline_extraction, agents_stories_prd_002_reflex_chat_ui_story_005_session_user_id_entry, agents_stories_prd_002_reflex_chat_ui_story_006_wire_chatstate_to_pipeline [EXTRACTED 1.00]
- **PII Redaction Pipeline Flow (input redaction -> output redaction -> audit telemetry -> response signal)** — agents_stories_prd_003_pii_redaction_story_005_pipeline_input_redaction, agents_stories_prd_003_pii_redaction_story_006_pipeline_output_redaction, agents_stories_prd_003_pii_redaction_story_004_audit_logger_pii_telemetry, agents_stories_prd_003_pii_redaction_story_007_query_response_pii_signal [EXTRACTED 1.00]
- **Cross-Epic Docker/docker-compose Packaging Pattern** — agents_stories_prd_001_harness_ia_story_013_docker_packaging, agents_stories_prd_002_reflex_chat_ui_story_008_docker_single_port_packaging, agents_stories_prd_003_pii_redaction_story_011_docker_image_spacy_model [INFERRED 0.80]
- **Phase 1 - Correctness Foundation (async offload, exception handling, pending flag)** — _agents_stories_prd_004_chat_ui_redesign_story_001_async_run_query_offload_story, _agents_stories_prd_004_chat_ui_redesign_story_002_exhaustive_exception_handling_story, _agents_stories_prd_004_chat_ui_redesign_story_003_pending_state_flag_story [EXTRACTED 1.00]
- **Six-Outcome kind Discriminator: model, dispatch, and verification** — _agents_stories_prd_004_chat_ui_redesign_story_004_chat_message_model_chatmessage_model, _agents_stories_prd_004_chat_ui_redesign_story_008_bubble_renderers_match_dispatch_rx_match_dispatch, _agents_stories_prd_004_chat_ui_redesign_story_019_six_outcome_regression_verification_six_outcome_verification [INFERRED 0.85]
- **Risk 4 Duplicate-Loop Mitigation: copy, relative-time card, and recovery action** — _agents_stories_prd_004_chat_ui_redesign_story_007_copy_module_centralized_copy_module, _agents_stories_prd_004_chat_ui_redesign_story_011_duplicate_relative_time_relative_time_and_window_release, _agents_stories_prd_004_chat_ui_redesign_story_018_retry_and_edit_resend_retry_edit_resend_recovery [EXTRACTED 1.00]
- **Authorization enforced identically through the router and chat-UI ingresses** — app_services_query_pipeline_run_query, chat_ui_chat_ui_state_send, app_routers_query_post_query, app_middleware_auth_require_identity [EXTRACTED 1.00]
- **Startup hooks duplicated across app.main lifespan and the Reflex chat_ui entrypoint** — app_main_lifespan, chat_ui_chat_ui_chat_ui, app_services_authz_load, app_db_database_init_db [EXTRACTED 1.00]
- **In-band policy-refusal response family (BLOCKED status)** — app_models_schemas_queryblockedforbiddenresponse, app_models_schemas_queryresponse, chat_ui_chat_ui_state_send, app_routers_query_post_query [EXTRACTED 1.00]
- **Admin authentication gate flow** — _agents_stories_prd_006_admin_console_story_003_admin_token_gate_story, _agents_stories_prd_006_admin_console_story_004_threaded_database_read_story, _agents_stories_prd_006_admin_console_story_009_admin_shell_and_gate_story, _agents_stories_prd_006_admin_console_story_003_admin_token_gate_risk1_gate_guard, _agents_stories_prd_006_admin_console_story_009_admin_shell_and_gate_gate_as_state, _agents_stories_prd_006_admin_console_story_003_admin_token_gate_no_oracle_gate_error [INFERRED 0.85]
- **Derived-once row formatting pipeline** — _agents_stories_prd_006_admin_console_story_001_audit_row_model_story, _agents_stories_prd_006_admin_console_story_002_verdict_derivation_formatting_story, _agents_stories_prd_006_admin_console_story_004_threaded_database_read_story, _agents_stories_prd_006_admin_console_story_011_register_table_stamp_margin_story, _agents_stories_prd_006_admin_console_story_002_verdict_derivation_formatting_derived_once_row_model [INFERRED 0.80]
- **No-cards, no-accent enforcement chain** — _agents_stories_prd_006_admin_console_story_009_admin_shell_and_gate_story, _agents_stories_prd_006_admin_console_story_011_register_table_stamp_margin_story, _agents_stories_prd_006_admin_console_story_012_row_detail_disclosure_story, _agents_stories_prd_006_admin_console_story_013_filter_and_sort_controls_story, _agents_stories_prd_006_admin_console_story_018_render_invariant_tests_story, _agents_stories_prd_006_admin_console_story_009_admin_shell_and_gate_risk6_no_cards_no_accent [INFERRED 0.85]
- **PRD-007 Phase 2: storage layer swap** — _agents_stories_prd_007_turso_migration_story_004_module_owned_error_surface, _agents_stories_prd_007_turso_migration_story_005_turso_configuration, _agents_stories_prd_007_turso_migration_story_006_libsql_connection_layer, _agents_stories_prd_007_turso_migration_story_007_concurrent_safe_init_db, _agents_stories_prd_007_turso_migration_story_008_startup_guard [EXTRACTED 1.00]
- **PRD-007 Phase 3: network-cost remediation** — _agents_stories_prd_007_turso_migration_story_009_top_pii_entities_sql_aggregation, _agents_stories_prd_007_turso_migration_story_010_batched_summary_read, _agents_stories_prd_007_turso_migration_story_011_stats_endpoint_batched, _agents_stories_prd_007_turso_migration_story_012_admin_console_batched_reads [EXTRACTED 1.00]
- **PRD-008: session ownership enforced as a signature rule** — _agents_stories_prd_008_chat_sessions_story_004_session_crud_functions, _agents_stories_prd_008_chat_sessions_story_005_message_store_functions, _agents_stories_prd_008_chat_sessions_story_006_chat_sessions_service, _agents_stories_prd_008_chat_sessions_story_007_ownership_signature_guard, concept_ownership_as_signature_rule [EXTRACTED 1.00]
- **ChatState session lifecycle: create, persist, restore, manage** — agents_stories_prd_008_chat_sessions_story_013_chat_state_session_list_and_lazy_create, agents_stories_prd_008_chat_sessions_story_014_transcript_persistence_write, agents_stories_prd_008_chat_sessions_story_015_transcript_restore, agents_stories_prd_008_chat_sessions_story_016_session_rename_delete_logout [INFERRED 0.85]
- **Session rail design system: tokens, component, layout, guards** — agents_stories_prd_008_chat_sessions_story_017_rail_tokens_and_copy, agents_stories_prd_008_chat_sessions_story_018_session_rail_component, agents_stories_prd_008_chat_sessions_story_019_shell_layout_and_responsive, agents_stories_prd_008_chat_sessions_story_020_rail_design_guards [INFERRED 0.90]
- **Restoring test-suite signal integrity: real proof, honest guards, hidden defects** — agents_stories_prd_008_chat_sessions_story_021_two_instance_and_flag_off_smoke, agents_stories_prd_008_chat_sessions_story_023_untouched_app_guard_rescope, agents_stories_prd_008_chat_sessions_story_024_stale_client_recovery [INFERRED 0.80]
- **Reflex agent skill installation and usage workflow** — chat_ui_agents_reflex_docs_skill, chat_ui_agents_setup_python_env_skill, chat_ui_agents_reflex_process_management_skill, chat_ui_agents_agent_skills_marketplace [EXTRACTED 0.90]

## Communities (257 total, 97 thin omitted)

### Community 0 - "Schema Migration & DB Tests"
Cohesion: 0.03
Nodes (122): Additive-only schema migration (no drops, renames, or type changes), get_connection(), init_db(), A transaction handle over the process-wide client. Public because thirteen test…, Create or migrate the schema -- and, first, prove the database answers. **The…, _column_names(), _create_pre_chat_sessions_database(), _create_pre_pii_database() (+114 more)

### Community 1 - "Chat Session Acceptance Criteria"
Cohesion: 0.05
Nodes (94): _capturing_run_query(), _fields(), _make_state(), asyncio, parametrize, AC 4. One session, titled by formatting.derive_title through the service's…, AC 4's ordering half, and the only assertion that distinguishes a create placed…, AC 5. Lazy means once per chat, not once per send. (+86 more)

### Community 2 - "Chat UI Story Plans"
Cohesion: 0.07
Nodes (70): Plan: Inline validation error on empty user_id submit, Plan: Model selector driven by a curated allowlist, Plan: Populate device from browser User-Agent on chat sends, Plan: Retry on error cards and edit-and-resend on duplicate cards, Plan: Six-outcome walkthrough and full-suite regression verification, Plan: Retry on error cards and edit-and-resend on duplicate cards (PRD-004 dir copy), Plan: Chat UI login replaces the free-text user_id prompt, STORY-002: Reflex project scaffolding & dependency setup (+62 more)

### Community 3 - "Admin State Load & Auth Tests"
Cohesion: 0.06
Nodes (69): _authenticate(), _fixed_snapshot(), _label_for(), _load(), _loaded_record(), _logs(), asyncio, STORY-004 AC 6, strengthened past STORY-003's version: not merely "rows stay… (+61 more)

### Community 4 - "Admin Row Formatting"
Cohesion: 0.05
Nodes (67): derive_verdict(), format_share(), _format_timestamps(), _parse_pii_entities(), datetime, Pure-Python formatting for the admin register's rows and figures. Like…, A NULL column reads as the absent mark, so the row field stays a plain str., Splits the stored TEXT form written by `app/services/audit_logger.py:43`.… (+59 more)

### Community 5 - "Audit Aggregate Read Functions"
Cohesion: 0.06
Nodes (54): STORY-004: AdminState.load() — all ten read functions via asyncio.to_thread, with a catch-all fault arm, STORY-009: GET /audit and GET /stats - PII telemetry fields, count_blocked_duplicates(), count_blocked_suspicious(), count_pii_detected_queries(), count_successful_queries(), count_unique_users(), Exception (+46 more)

### Community 6 - "Admin Shell Import Smoke Tests"
Cohesion: 0.03
Nodes (64): child_db_env(), The `DATABASE_URL` entry a probe subprocess needs. A plain function rather than…, app_source(), pages_probe(), probe(), fixture, Smoke and invariant tests for the admin console's shell. Two halves, because…, Catches circular imports and names missing at module scope. (+56 more)

### Community 7 - "Chat Session CRUD"
Cohesion: 0.06
Nodes (63): create_chat_session(), delete_chat_session(), get_chat_session(), Writes one owned session and returns its new id. **The id is minted here, and…, The owner's session, or None. **A session that exists but belongs to someone…, Retitles an owned session. False when there was no such owned row.…, Moves an owned session's `updated_at` to now. False when not owned. The send…, Removes an owned session and its messages in one transaction. **The message… (+55 more)

### Community 8 - "Register Table Components"
Cohesion: 0.06
Nodes (60): _cell(), _chip_button(), _clear_control(), _column_head(), _control_button(), _control_label(), _disclosure_toggle(), _empty_panel() (+52 more)

### Community 9 - "ChatState Session Actions"
Cohesion: 0.05
Nodes (37): format_duplicate_info(), Returns (relative-time line, 24h-window-release line) for a duplicate block.…, ChatState, event, var, Session state for the chat surface: the transcript, the composer, and who is…, 50 most recent of 212" -- the window, stated against the whole list. Empty when…, Signs in, then loads this identity's session list. Async but *not*… (+29 more)

### Community 10 - "Audit Log Storage & PII Columns"
Cohesion: 0.07
Nodes (58): Row scoping happens in SQL, not by filtering in Python, STORY-003: audit_logs schema - PII telemetry columns, STORY-004: Audit logger records PII telemetry (raw preview unchanged), Audit log stays raw (compliance trail unaffected by redaction), insert_audit_log(), list_audit_logs(), AuditLog, _fail_if_called() (+50 more)

### Community 11 - "Admin Row & Figure Models"
Cohesion: 0.06
Nodes (49): STORY-005: filter and sort vars, AuditRow, Typed row and figure models for the admin console. `AuditRow` is a deliberate…, One register row: every field the audit table and its disclosure render., One figure on the summary tally sheet: what it counts, and over what window., SummaryFigure, _count_figure(), filter_rows() (+41 more)

### Community 12 - "Users Table CRUD"
Cohesion: 0.06
Nodes (50): deactivate_user(), insert_user(), list_users(), Raises app.db.errors.IntegrityError on a duplicate user_id or token_hash --…, Revocation is not deletion: audit_logs rows carry a bare user_id with no…, _row_to_user(), User, PRD-007 STORY-002 characterization test -- the endpoint-level half of the arm… (+42 more)

### Community 13 - "Session Title & Activity Formatting"
Cohesion: 0.06
Nodes (54): STORY-012: ChatSessionSummary plus auto-title derivation and relative activity time, _bucket(), derive_title(), format_activity(), humanize_compact(), datetime, Pure-Python formatting helpers for chat_ui bubbles and session rows. These run…, The rail's activity time: "2m ago", "yesterday", "3 days ago". A **third**… (+46 more)

### Community 14 - "ChatState Error Handling Tests"
Cohesion: 0.06
Nodes (55): ChatSessionError, Exception, A session or transcript operation failed at the storage layer. The same move…, _count_audit_rows(), _fail_if_called(), _handler(), _last_audit_id(), _raise_chat_session_error() (+47 more)

### Community 15 - "Chat Sessions Service Tests"
Cohesion: 0.04
Nodes (54): history_off(), fixture, The chat store from PRD-008, and the service over it: STORY-004's six session…, A stand-in for `app.db.database` on which every access is a failure. AC 4 asks…, Every public function *defined* in the service module. Discovered, not…, One service function's body with its docstring removed. `_statements_of` above…, AC 1. A statement about the module; no database needed., AC 1, the other direction. A story that exposes a further function has to say… (+46 more)

### Community 16 - "Database Layer Plans"
Cohesion: 0.06
Nodes (48): Plan: Additive schema-migration mechanism for audit_logs, Plan: users table schema and CRUD helpers, Plan: audit_logs gains role and denied_permission columns, Any, _add_missing_columns(), _constraint_of(), _decode_count(), _decode_ranked() (+40 more)

### Community 17 - "Session Ownership Tests"
Cohesion: 0.06
Nodes (53): _assert_returns_nothing(), _call_service(), _call_store(), _count(), _drive_and_assert_nothing_changed(), parametrize, PRD-008's ownership rule, asserted against the signatures rather than…, Every public session/message function *defined* in `app/db/database.py`.… (+45 more)

### Community 18 - "Shared libSQL Client"
Cohesion: 0.05
Nodes (47): count_audit_logs(), The process-wide libSQL client, constructed once and reused. PRD-007 Section 6…, _shared_client(), db_connect(), Opens a connection to the database named by URL, for raw DDL. For the handful…, _an_audit_row(), The database fixtures' own contract, asserted rather than assumed.…, The STORY-002 characterization tests need a database whose `users` table is… (+39 more)

### Community 19 - "PII Redaction Epic"
Cohesion: 0.08
Nodes (49): Presidio adapter isolation pattern, STORY-001: Presidio PII redactor service, Lazy singleton + eager startup load, STORY-002: Load Presidio NLP model once at FastAPI startup, STORY-003: audit_logs schema PII telemetry columns, Raw audit trail principle (RF-7), STORY-004: Audit logger records PII telemetry, Fail-closed, audited redaction failure handling (+41 more)

### Community 20 - "RBAC Design Rationale"
Cohesion: 0.09
Nodes (36): 401 means unknown identity, 403 means known identity lacking permission, HTTP-layer dependencies are defense in depth, not the authoritative control, Failing fast makes RBAC_ENABLED=true safe as a default, ADMIN_TOKEN documented as break-glass credential, not primary auth, Plan: Identity resolution -- token hashing, Identity value object, ADMIN_TOKEN break-glass, Plan: Bootstrap CLI -- scripts/manage_users.py, Plan: RBAC configuration settings and env vars, Plan: authz service -- permission constants, default role matrix, deny-by-default authorize() (+28 more)

### Community 21 - "Admin Copy & State Tests"
Cohesion: 0.06
Nodes (47): Centralized user-facing copy and templates for the admin console. The…, configured_token(), _figures(), _populate(), fixture, The console's gate, asserted rather than reviewed. Three of STORY-003's…, Fills every declared field with a non-default value, and returns the defaults…, AC 7. A filter surviving a sign-out is the standing disclosure PRD-006 Section… (+39 more)

### Community 22 - "Register Filter & Sort Assertions"
Cohesion: 0.06
Nodes (49): _call(), _loaded(), AC 1. Plain base vars, not computed ones — the controls write them., AC 2, second half — PRD-006 Section 6: "filtering never re-reads the database".…, AC 6. `row.verdict not in []` is True for every row, so a predicate missing the…, AC 3. `127` isolating audit #127 is PRD Section 5 story 5 — the loop that…, AC 4. An OR would widen the register at the exact moment the admin is narrowing…, AC 5's default. `sort_key` defaults to "" — not to "timestamp" — because… (+41 more)

### Community 23 - "Query Router Tests"
Cohesion: 0.09
Nodes (45): _boom(), _boom_on_second_call(), _capturing_openrouter(), _count_audit_rows(), _fail_if_called(), _latest_audit_entry(), _openrouter_returning(), PRD-007 STORY-002 characterization test, pinning the consequence of the `except… (+37 more)

### Community 24 - "Authorization Service"
Cohesion: 0.09
Nodes (40): Identity is constructed only in identity.py (trustworthy argument type), Deny-by-default authorization (no fallback grant), Full replacement (not merge) of role matrix on override, get_audit(), authorize(), authorize_model(), AuthzConfigError, load() (+32 more)

### Community 25 - "Turso Migration CLI Tests"
Cohesion: 0.11
Nodes (43): main(), _dest_counts(), _make_source(), PRD-007 STORY-013 -- `scripts/migrate_to_turso.py`. The source is the one…, AC 1 and AC 3 -- every row, every column, and the counts are reported. The…, AC 2 -- `GET /audit/{id}` addresses rows by id, so the ids must survive., AC 5 -- refuses outright, and says so on stderr with stdout untouched., AC 4 -- a short copy is caught, and the message names table and check. (+35 more)

### Community 26 - "Session ID Over POST /query"
Cohesion: 0.08
Nodes (42): _count_audit_rows(), _fail_if_called(), _fake_call_openrouter(), _last_audit_row(), parametrize, `session_id` over `POST /query` -- PRD-008 STORY-010. The API boundary is the…, AC 2. The compatibility promise PRD Section 3 makes to the integrating…, AC 2's "the audit row [is] identical to the current release", asserted rather… (+34 more)

### Community 27 - "Startup Failure Classification"
Cohesion: 0.08
Nodes (36): CLI is the only administration surface in the MVP, _classify_startup_failure(), Credential rotation (STORY-004 `issue-token`). The old hash stops resolving the…, Driver text with the credential removed, in both forms it can take. Belt and…, Which of the two boot-time failures this is, and what to tell an operator.…, _redacted(), set_user_token_hash(), DatabaseAuthError (+28 more)

### Community 28 - "Turso Migration Reports"
Cohesion: 0.07
Nodes (41): STORY-001 Driver Decision Record, libsql==0.1.11 Driver Decision, STORY-001 Implementation Report: libSQL Driver Spike, STORY-002 Implementation Report: Exception Characterization Tests, Centralized DATABASE_URL Test Fixture, STORY-003 Implementation Report: Centralize DATABASE_URL Fixture, STORY-004 Implementation Report: Module-Owned Error Surface, app/db/errors.py Module-Owned Exception Surface (+33 more)

### Community 29 - "Chat Sessions Service Module"
Cohesion: 0.09
Nodes (39): health(), append_message(), delete(), get(), list_for(), messages_for(), owns(), Whose row this is, and whether history is on at all -- in one place. PRD-008… (+31 more)

### Community 30 - "Session Create & Count Tests"
Cohesion: 0.08
Nodes (39): count(), create(), How many sessions this identity has in total -- cap or no cap. The companion…, Opens a new session for this identity, titled from its first prompt. Returns…, _call(), _identity(), parametrize, An `Identity` the way `resolve()` would have produced one. Constructed directly… (+31 more)

### Community 31 - "RBAC Story Board"
Cohesion: 0.10
Nodes (38): PRD-005: Role-Based Access Control, STORY-001: Additive schema-migration mechanism for audit_logs, STORY-002: users table schema and CRUD helpers, STORY-003: Identity resolution — token hashing, Identity value object, ADMIN_TOKEN break-glass, STORY-004: Bootstrap CLI — scripts/manage_users.py, STORY-005: RBAC configuration settings and env vars, STORY-006: authz service — permission matrix, deny-by-default authorize(), STORY-007: Role matrix loaded from RBAC_ROLES_FILE at startup (+30 more)

### Community 32 - "Reflex Chat UI Epic"
Cohesion: 0.09
Nodes (38): run_query() Shared Pipeline Function, STORY-001: Extract run_query() Shared Pipeline Function (Report), STORY-002: Reflex Project Scaffolding & Dependency Setup (Report), api_transformer Single-Port FastAPI Mount, STORY-003: Mount FastAPI into Reflex — Single-Port Process (Report), STORY-004: Claude-like Chat UI Components — Static (Report), STORY-005: Session user_id Entry Field (Report), Session user_id Entry Gate (+30 more)

### Community 33 - "Chat Correctness Foundations"
Cohesion: 0.08
Nodes (38): asyncio.to_thread Worker Offload, STORY-001: Offload run_query to worker thread via asyncio.to_thread, No-Silent-Drops Exception Handling Invariant, STORY-002: Exhaustive except arms in send(), Finally-Reset Pending Flag & Single In-Flight Guard, STORY-003: pending state var with finally-reset and in-flight guard, ChatMessage Typed Model with kind Discriminator, STORY-004: ChatMessage typed model replaces list[dict[str, str]] (+30 more)

### Community 34 - "Request & Response Schemas"
Cohesion: 0.10
Nodes (34): Plan: QueryBlockedForbiddenResponse joins the QueryResponse union, AuditQueryEntry, AuditResponse, field_validator, QueryBlockedDuplicateResponse, QueryBlockedSuspiciousResponse, QueryRequest, QuerySuccessResponse (+26 more)

### Community 35 - "Chat Message Store"
Cohesion: 0.10
Nodes (38): append_chat_message(), list_chat_messages(), One `chat_messages` row as the dataclass STORY-002 declared. **`pii_redacted`…, Writes one message into an owned session and returns its new `id`. **One…, One owned session's whole transcript, in the order it was written. **`ORDER BY…, _row_to_stored_message(), One row of chat_messages -- the table's shape, not the bubble's. pii_entities…, StoredMessage (+30 more)

### Community 36 - "AdminState Class"
Cohesion: 0.07
Nodes (23): AdminState, event, The console's session: who is through the gate, and what has been read. Every…, Whether anything is narrowing the register right now. Sort is excluded:…, Which of the four states the register is showing — decided once, here. **The…, Refreshed 2026-08-31 14:22:07 UTC" — the line the control produces. One verb…, Which of the three states the sheet is showing — decided once, here. **The…, Adds or removes one verdict from the selection. Reassigns the list rather than… (+15 more)

### Community 37 - "Admin Console Risk Mitigations"
Cohesion: 0.13
Nodes (36): Risk 2: no preview fields on AuditRow, STORY-001: AuditRow and SummaryFigure models — a projection with no preview fields, Derived-once row model, Risk 3: verdict never branches on model_used, STORY-002: admin_formatting.py — verdict derivation, relative time, device and shares, Verdict derivation precedence, No-oracle gate refusal, Risk 1: load() guarded by authentication (+28 more)

### Community 38 - "Harness IA Plans & Conventions"
Cohesion: 0.12
Nodes (36): Security Review Command, Validate Command, Project Scaffolding & Configuration Loading Plan (STORY-001), SQLite Connection & audit_logs Schema Plan (STORY-002), Repository Pattern (SQL Isolated in db Layer), Pydantic Request/Response Schemas Plan (STORY-003), Duplicate Detection Service Plan (STORY-004), Fail Loud, Not Silent Principle (+28 more)

### Community 39 - "Admin Console Story Chain"
Cohesion: 0.16
Nodes (34): STORY-001: AuditRow and SummaryFigure models, STORY-002: verdict derivation and formatting, STORY-003: AdminState token gate, STORY-004: threaded database read, STORY-006: admin state tests, STORY-007: register theme tokens, STORY-008: admin copy module, STORY-009: admin shell and gate (+26 more)

### Community 40 - "Token Hashing & Identity"
Cohesion: 0.10
Nodes (31): hash_token(), issue_token(), SHA-256 digest of a credential. Deliberately independent of the prompt-hashing…, Generates a new credential. Returns the plaintext -- the caller is responsible…, Verifies a credential and returns the Identity it belongs to, or None. None…, resolve(), test_identity_lacking_both_audit_permissions_returns_403(), test_hash_token_differs_for_different_input() (+23 more)

### Community 41 - "PII End-to-End Integration Tests"
Cohesion: 0.10
Nodes (31): STORY-010: End-to-end PII redaction integration test suite, _capturing_openrouter(), _epic_base(), _git(), _post_pii_query(), parametrize, AC1, per entity: name, email and phone are each individually absent., AC2: masked response + pii_redacted/pii_entities_masked, exact field set. (+23 more)

### Community 42 - "Query Pipeline & Policy Refusal"
Cohesion: 0.13
Nodes (27): Policy refusal stays in-band as status BLOCKED, STORY-006: Redact model response before returning to caller, STORY-007: POST /query response - pii_redacted signal field, log_query(), QueryBlockedForbiddenResponse, QueryResponse union, OpenRouterResult, run_query() (+19 more)

### Community 43 - "Pipeline Session Passthrough Tests"
Cohesion: 0.13
Nodes (30): PiiRedactorError, Exception, _boom(), _boom_call_openrouter(), _boom_on_second_call(), _fail_if_called(), _fake_call_openrouter(), _last_audit_entry() (+22 more)

### Community 44 - "Session Reports & Formatting"
Cohesion: 0.08
Nodes (29): STORY-009 Report: Pipeline Session Passthrough, The _deny() Required session_id Parameter, STORY-010 Report: QueryRequest Session ID, chat_sessions.owns() Ownership Check, STORY-011 Report: Audit Entry Session ID, AuditQueryEntry.session_id Projection, STORY-012 Report: Session Summary and Formatting, derive_title Word-Boundary Truncation (+21 more)

### Community 45 - "Summary Tally Sheet Components"
Cohesion: 0.13
Nodes (28): _block(), _empty_summary(), _figure(), _figure_label(), _figure_note(), _figure_value(), _indented_figure(), Component (+20 more)

### Community 46 - "Chat Message Model & Persistence"
Cohesion: 0.09
Nodes (24): ChatMessage, Typed chat message model carrying kind discriminator and metadata., One bubble as one `chat_messages` row. `ChatMessage` defaults its optional…, Puts one bubble on screen, then tries to record it. In that order. **The order…, _to_stored_message(), AC 3: "the model selector and the signed-in user are untouched"., AC 8: swapping the transcript out from under an in-flight send would append the…, The bare-`Exception` half of AC 9. A ChatSessionError-only catch would let a… (+16 more)

### Community 47 - "Frontend Package Manifest"
Cohesion: 0.07
Nodes (27): name, type, autoprefixer, @emotion/react, isbot, lucide-react, postcss, postcss-import (+19 more)

### Community 48 - "Admin Console Design Plans"
Cohesion: 0.16
Nodes (27): STORY-007: register theme tokens plan, Risk 6: no cards/fills/accent — avoid KPI-dashboard drift, STORY-008: admin_copy.py plan, STORY-009: admin_shell.py gate plan, STORY-010: admin route registration plan, STORY-011: register table + stamp margin plan, Risk 4: scope line stated honestly against the true total, Stamp margin as the console's one signature element (+19 more)

### Community 49 - "Register Scope & Count Copy"
Cohesion: 0.09
Nodes (23): format_count(), A whole-number figure, thousands-separated: 3180 reads as "3,180". Here rather…, `verdict denied and text "ana" matched none of the 100 rows loaded.` PRD-006…, The register's window, stated against the whole record. PRD-006 Risk 4: all-…, 12 of 100 shown" — how much of the loaded window survived the filter. **A…, AC 2's first half, and PRD-006 Section 6.1: "the no-matches state names the…, ... matched none of the 100 rows loaded." The denominator is the loaded window,…, An authenticated state holding a full set of counts. (+15 more)

### Community 50 - "Session Rail Component"
Cohesion: 0.14
Nodes (25): _action_button(), _body(), _delete_confirm(), _empty_state(), _fault_state(), _is_active(), Component, Var (+17 more)

### Community 51 - "Duplicate Detection Service"
Cohesion: 0.17
Nodes (24): STORY-008: Tests - redaction cannot affect dedup/pattern-check behavior, check_duplicate(), DuplicateCheckError, DuplicateCheckResult, hash_prompt(), Exception, _seed(), test_boundary_just_inside_24h() (+16 more)

### Community 52 - "New Chat & Transcript Restore"
Cohesion: 0.09
Nodes (25): count_chat_sessions(), How many sessions this user has, in total. Exists so the rail can state its cap…, _new_chat(), AC 3, the PRD's headline behavioural claim: "a session row is written on the…, The session's rows, read straight from the store rather than through…, AC 6: "a failed reorder is cosmetic and must not surface as a lost turn." The…, AC 1: `active_session_id` and `messages` are cleared and no row is written., AC 2: the lazy rule, stated as the absence it is. Two clicks and an empty table… (+17 more)

### Community 53 - "Admin Palette Tests"
Cohesion: 0.10
Nodes (23): _admin_modules(), _literal_hexes(), parametrize, Path, The console's palette is an inheritance, and two inks are not part of it.…, The scale block stays ascending; TEXT_MICRO is a new smallest., A glob that matches nothing would pass every test below vacuously., Every colour on the console resolves from theme.py. Parametrized per module… (+15 more)

### Community 54 - "RBAC Ingress Parity Tests"
Cohesion: 0.13
Nodes (22): Ingress-parity tests are the regression guard for PRD Risk 1, _create_pre_rbac_database(), Builds the 17-column audit_logs table exactly as it ships on `main` today --…, _count_audit_rows(), _fail_if_called(), _fake_success(), _latest_audit_entry(), _make_chat_state() (+14 more)

### Community 55 - "Turso Migration Story Board"
Cohesion: 0.17
Nodes (24): STORY-001: libSQL driver spike, STORY-003: Centralize DATABASE_URL test fixture, STORY-005: Turso configuration, STORY-006: libSQL connection layer swap, STORY-007: Concurrent-safe init_db(), STORY-008: Startup guard, STORY-009: top_pii_entities SQL aggregation, STORY-010: Batched summary read (+16 more)

### Community 56 - "Presidio Redactor Engine"
Cohesion: 0.13
Nodes (23): STORY-001: Presidio PII redactor service, Presidio adapter-pattern isolation (no other module imports presidio_*), STORY-002: Load Presidio NLP model once at FastAPI startup, STORY-005: Redact prompt before forwarding to OpenRouter, AnalyzerEngine, AnonymizerEngine, _build_analyzer(), _get_analyzer() (+15 more)

### Community 57 - "Admin Route & Copy Assertions"
Cohesion: 0.09
Nodes (24): _admin_modules(), parametrize, Path, The route string is typed once in the codebase, and this is where. STORY-010…, AC 7's "no literal text", made checkable. Case-sensitive and quoted,…, PRD-006 Section 4, from the source side. Complements the `sys.modules` probe:…, AC 6 across the console, not just the shell., AC 8, and PRD-006 Section 4's out-of-scope list: "Auto-refresh, polling, or… (+16 more)

### Community 58 - "PII Dedup Isolation Tests"
Cohesion: 0.13
Nodes (21): _capturing_openrouter(), _changed_since_epic_base(), _count_audit_rows(), _epic_base(), _fail_if_called(), fixture, parametrize, Control for the test above: dedup is not simply broken in the presence of PII. (+13 more)

### Community 59 - "Console Render Invariant Tests"
Cohesion: 0.11
Nodes (22): _page_without_the_stylesheet(), parametrize, The console's two render invariants, asserted against a seeded database.…, The page with `theme.GLOBAL_CSS` removed, having proved the removal. The…, Catches an import failure, a raised read, or a page that would not build., **The load-bearing test in this file.** Every preview assertion below is a…, PRD-006 Risk 2's render half, over both halves of what the browser gets.…, PRD-006 Risk 2's mitigation, verbatim: "A test asserts `AuditRow` has no… (+14 more)

### Community 60 - "Register State & Empty Panels"
Cohesion: 0.10
Nodes (21): STORY-012: row detail disclosure, STORY-013: filter and sort controls, STORY-014: three empty states, Three register states with fixed precedence: read_failed > no_rows > no_matches > rows, Smoke and invariant tests for the register. Three halves, because three…, AC 1 and AC 2: two panels, and two *different* sentences. The inequality is the…, AC 6: the register's existing type and rules, and nothing else. An empty state…, The controls sit outside the switch, so the way out of the no-matches state is… (+13 more)

### Community 61 - "Register Column & Verdict Ink"
Cohesion: 0.09
Nodes (22): parametrize, AC 1: the eight columns PRD-006 Section 4 names are all on the surface., AC 3, from the render side. All four `rx.match` arms are in the compiled…, AC 3: four verdicts, four inks, no two sharing a treatment., The stamp margin is a fixed-width column (AC 4), the rows carry the register's…, Case-sensitive and quoted, deliberately: the verdict *keys* ("cleared", "held",…, PRD-006 Section 4, from the source side. Complements the `sys.modules` probe:…, AC 1: every field PRD-006 Section 10 moves onto disclosure is labelled. (+14 more)

### Community 62 - "User Lookup Functions"
Cohesion: 0.20
Nodes (20): STORY-002: Exception characterization tests, STORY-004: Module-owned error surface, find_user_by_token_hash(), get_user(), Returns the user regardless of active state -- administrative reads (CLI…, Active users only. A revoked credential is indistinguishable from an unknown…, main(), Also a PRD-007 STORY-002 characterization test, pinning the `except… (+12 more)

### Community 63 - "Chat Pipeline Integration Stories"
Cohesion: 0.14
Nodes (19): STORY-012: End-to-end integration test suite, STORY-013: Docker & docker-compose packaging, STORY-014: README & usage documentation, STORY-001: Extract run_query(...) shared pipeline function, STORY-005: Session user_id entry field, STORY-006: Wire ChatState.send() to the shared query pipeline, STORY-007: Chat pipeline unit test suite, STORY-008: Multi-stage Docker packaging for single-port image (+11 more)

### Community 64 - "OpenRouter Client"
Cohesion: 0.24
Nodes (18): query(), call_openrouter(), OpenRouterError, Exception, Client, post, QueryResponse, _FakeClient (+10 more)

### Community 65 - "Migration Fingerprint & Outcome"
Cohesion: 0.13
Nodes (20): _fingerprint(), _migrate(), MigrationError, _Outcome, _print_summary(), Exception, Namespace, Path (+12 more)

### Community 66 - "Database URL Test Fixtures"
Cohesion: 0.12
Nodes (20): database_url(), database_url_factory(), _libsql_endpoint(), _never_the_configured_database(), fixture, The one place a test database is provisioned, and the one place a URL is…, Proves the endpoint is reachable once, and says how to start it if not. A hard…, Every test starts on an empty database, whether it asked for one or not. Until… (+12 more)

### Community 67 - "Delegating Connection Wrapper"
Cohesion: 0.10
Nodes (12): _DelegatingConnection, _driver_error(), _FailingAlterConnection, _GatedConnection, _is_add_column(), _is_table_info(), Base for the connection proxies below: passes everything through. Same idiom as…, Reports `audit_logs` as having no columns; everything else is real. (+4 more)

### Community 68 - "Admin Pages & Shell"
Cohesion: 0.17
Nodes (19): admin_register_page(), admin_summary_page(), Component, admin_gate(), admin_masthead(), admin_page(), fault_panel(), Component (+11 more)

### Community 69 - "Chat UI Redesign Mechanisms"
Cohesion: 0.20
Nodes (19): asyncio.to_thread offload of run_query, Exhaustive exception handling (no silent drop), Pending state flag and single in-flight guard, ChatMessage typed model, send() populates full outcome metadata, Centralized copy.py module, Six bubble renderers dispatched via rx.match, Informational PII badge on assistant bubbles (+11 more)

### Community 70 - "Audit Logger Tests"
Cohesion: 0.27
Nodes (18): get_audit_log(), log_query(), PRD-008 STORY-008 AC 4: every caller that predates the parameter -- the seven…, test_duplicate_blocked_case_logs_null_response_fields(), test_empty_entity_list_stored_as_none(), test_entity_list_joined_in_caller_order_without_reordering(), test_long_prompt_and_response_truncated_but_hash_over_full_text(), test_no_ip_or_location_field_in_logged_row() (+10 more)

### Community 71 - "Chat Copy Tests"
Cohesion: 0.11
Nodes (18): Verify all critical copy strings are non-empty and accessible., AC4 / Risk 4: Duplicate card copy states that text must change for resend to go…, Verify footer separator and formatting tokens exist., AC3: Empty or unparseable first_query_at renders fallback without crash ('No…, AC6: every admin-facing string is non-empty and accessible, matching…, STORY-012: both fallbacks are user-facing sentences, so both live here. Neither…, STORY-014 AC 5 and AC 6, as copy rather than as behaviour. Both notices are…, The one claim in the string that could be false in the wrong direction.… (+10 more)

### Community 72 - "Admin Console Reports"
Cohesion: 0.19
Nodes (17): Derived-once row model, STORY-001: AuditRow / SummaryFigure models plan, Reflex plugin skills unavailable — verify-against-package substitution, Risk 2: preview fields dropped at the boundary, STORY-002: admin_formatting.py plan, Verdict precedence: held > denied > fault > cleared, STORY-003: AdminState token gate plan, No-oracle gate: one refusal message for every failure mode (+9 more)

### Community 73 - "PII & Chat UI Story Boards"
Cohesion: 0.14
Nodes (18): 8-Step Query Interception Pipeline, PRD-003 Story Board, PRD-003: PII Redaction (Presidio), Presidio pii_redactor.py Adapter, Raw Audit Retention Rationale, PRD-004 Story Board, PRD-004: Chat UI Redesign, ChatMessage Typed Model (+10 more)

### Community 74 - "Connection Wrapper"
Cohesion: 0.12
Nodes (11): _Connection, A transaction over the shared client, with the old block's semantics. `with…, Deliberately a no-op. The client is shared by every caller in the process, so…, _open_source(), Opens the source strictly read-only. `mode=ro` is enforcement, not intention:…, The source table's columns, or `None` when the table does not exist. Same…, Decides the column list for one table, or refuses (AC 9). **Copying is by…, _reconcile() (+3 more)

### Community 75 - "Turso Migration Script"
Cohesion: 0.15
Nodes (16): _build_parser(), _chunks(), _copy_table(), _dest_count(), ArgumentParser, One-time copy of `audit_logs` and `users` from a legacy SQLite file into Turso.…, What will be copied for one table, and what the destination will default., Copies one table as chunked multi-row INSERTs. Returns statements issued. **One… (+8 more)

### Community 76 - "Pipeline Integration Tests"
Cohesion: 0.18
Nodes (17): _count_audit_rows(), _fail_if_called(), _fake_call_openrouter(), fixture, parametrize, PRD Section 5.3: every one of the 7 listed patterns is blocked before…, A successful, a duplicate-blocked, and a suspicious-blocked query all surface…, conftest's initialized database, plus this suite's two authenticated users. (+9 more)

### Community 77 - "Chat Sessions Story Board"
Cohesion: 0.24
Nodes (17): STORY-001: Chat history configuration, STORY-002: Chat session schema, STORY-003: init_db tables and audit column, STORY-004: Session CRUD functions, STORY-005: Message store functions, STORY-006: Chat sessions service, STORY-007: Ownership signature guard, STORY-008: audit_log session_id (+9 more)

### Community 78 - "Turso Config & Startup Guard"
Cohesion: 0.14
Nodes (16): CHILD_SETTINGS_PREAMBLE: subprocess URL travels beside a validator-satisfying placeholder, DATABASE_URL required, no sqlite:// default, no local-file fallback, STORY-005: Turso configuration (DATABASE_URL/TURSO_AUTH_TOKEN validators), TURSO_AUTH_TOKEN required for remote schemes, optional for local http://, _safe_endpoint()/_redacted() strip token and query string before any raised message, check_database_reachable(): one SELECT 1 at init_db() top, classifies unreachable vs auth failure, STORY-008: startup guard for unreachable database / bad token, Chunked multi-row INSERT VALUES(...),(...) replaces an unproven executemany/batch API (+8 more)

### Community 79 - "FastAPI App Startup Tests"
Cohesion: 0.15
Nodes (11): count_active_users(), _empty_users_db(), fixture, conftest's initialized database, with no user seeded into it. Requested for its…, STORY-008 AC1 and AC4 on the FastAPI path. The distinction this test exists to…, _small_model_and_reset(), test_lifespan_boots_when_rbac_enabled_and_one_active_user(), test_lifespan_fails_fast_even_with_only_admin_token_configured() (+3 more)

### Community 80 - "Audit Session ID Tests"
Cohesion: 0.18
Nodes (16): _audit_entries(), _fail_if_called(), _fake_call_openrouter(), fixture, `session_id` back out through `GET /audit` -- PRD-008 STORY-011. Four stories…, AC 3 and AC 4 in the mixed state a real deployment is actually in. A client…, PRD Section 12 Phase 2: "the four blocked outcomes each carry the session on…, conftest's initialized database, plus this suite's authenticated sender. A… (+8 more)

### Community 81 - "Session Ordering & Deletion Tests"
Cohesion: 0.12
Nodes (17): _backdate_session(), _delete(), AC 4's insert half. STORY-013's create leaves the new session out of…, AC 1: "the most recently active session becomes active and its transcript is…, AC 6: the UI lands on the next most recent session., AC 6's other arm: "or on the empty state if none remains"., AC 6's absolute: "never on a transcript belonging to a deleted id". The one…, The scope line counts the account, not the page, so a delete has to move it --… (+9 more)

### Community 82 - "Frontend Runtime Dependencies"
Cohesion: 0.12
Nodes (16): dependencies, isbot, lucide-react, @radix-ui/react-form, @radix-ui/themes, react, react-debounce-input, react-dom (+8 more)

### Community 83 - "Env Example Config Tests"
Cohesion: 0.12
Nodes (6): The committed example must not hand anyone the value that now fails., AC 6's committed-file half: the example must never carry a real token., AC 4's content half: the comment states the consequence, not the type. Asserted…, test_env_example_carries_no_sqlite_url(), test_env_example_says_what_the_off_state_does(), test_env_example_ships_no_token_value()

### Community 84 - "Database URL Validation Tests"
Cohesion: 0.12
Nodes (16): AC 3: the local libSQL server takes no token (PRD Section 9)., AC 7's fifth case: the configuration this PRD is migrating toward., `"https://".startswith("http://")` is False, and the token rule depends on it.…, A trailing newline in a `.env` value must not read as an unknown scheme., AC 1: both settings exist with the defaults PRD-008 Section 9 tabulates., The boundary on the accepted side, so `<= 1` fails here and not in STORY-006., The defaults are the module's, not a developer's exported environment., _settings() (+8 more)

### Community 85 - "Harness IA Story Board"
Cohesion: 0.20
Nodes (15): STORY-001: Project Scaffolding & Configuration Loading, STORY-002: SQLite Connection & audit_logs Schema, STORY-003: Pydantic Request/Response Schemas, STORY-004: Duplicate Detection Service (24h Exact-Match), SHA256 Exact-Match 24h Duplicate Window, STORY-005: Suspicious Pattern Detection Service, Seven-Pattern Injection Detector (Strategy List), STORY-006: Audit Logging Service (+7 more)

### Community 86 - "Chat UI Startup Guard Tests"
Cohesion: 0.18
Nodes (14): _empty_rbac_env(), fixture, Startup-guard coverage for the chat UI entry point. Two guards live here now,…, Runs the import probe and returns stderr, insisting it did fail. Same…, The chat UI's environment, pointed at a database that cannot answer., AC1 and AC4 on the Reflex path: the failure is at import, not per-request.…, AC3 where it actually matters: an operator reads the whole traceback, not just…, _run_failing_probe() (+6 more)

### Community 87 - "Contrast & Accessibility Tests"
Cohesion: 0.24
Nodes (14): contrast(), _luminance(), parametrize, WCAG AA contrast floor for the chat palette. The verdict inks are the whole…, Every pairing the admin console introduced, at AA. A cross product over-asserts…, Guards the maths itself, so a wrong helper cannot silently pass everything., The tag is small text on the transcript ground., A hovered row is still a row being read. (+6 more)

### Community 88 - "Untouched App Guard Tests"
Cohesion: 0.22
Nodes (14): _base(), _git(), parametrize, PRD-006's containment, asserted against git rather than remembered. STORY-020's…, Run a git command at the repo root; None when git/history is unavailable., The pinned baseline, or None when this tree cannot resolve it., AC 1: the six suites PRD-006 promised never to open, asserted by census. Byte-…, AC 1, the half byte-equality cannot cover. `test_copy.py` and… (+6 more)

### Community 89 - "Row Detail Disclosure"
Cohesion: 0.18
Nodes (14): STORY-012: row detail disclosure plan, AdminState.toggle_detail(), _detail(), _detail_field(), _detail_label(), _detail_value(), _is_open(), Whether this row's disclosure is open. `Var.contains()` and not `in`: the `in`… (+6 more)

### Community 90 - "Session Management Plans"
Cohesion: 0.24
Nodes (14): delete_session(session_id) lands on next most recent chat, STORY-016 Plan: new chat, rename, delete, logout, logout() clears state; delete_session() deletes rows, new_chat() writes nothing, rename_session(session_id, title) does not bump updated_at, STORY-017 Plan: rail tokens and copy, No-new-ink proof (AC2/AC9), Ten copy.py rail strings (+6 more)

### Community 91 - "Stale Client Recovery"
Cohesion: 0.22
Nodes (14): Two-seam recovery: validate-on-acquire + invalidate-without-retry, STORY-024 Plan: stale libSQL client recovery, _IDLE_PROBE_AFTER_SECONDS=5.0 floor, _is_dead_stream() classifier (STREAM_EXPIRED / invalid baton), STORY-004 Report: duplicate detection service, duplicate_checker.py: SHA256 hash + 24h lookup, DuplicateCheckError, STORY-005 Report: suspicious pattern detection service, detect_suspicious_pattern(prompt); SUSPICIOUS_PATTERNS strategy list (+6 more)

### Community 92 - "Session Ownership Signature"
Cohesion: 0.18
Nodes (14): delete_chat_session deletes messages via an ownership subselect then the session, in one transaction, STORY-004: six user-scoped chat_sessions CRUD functions, session_id minted server-side with uuid4; caller can never supply one (active_session_id is client-visible), Ownership as a signature property: user_id required and undefaulted on every function, turning a missed WHERE into a TypeError, Empty pii_entities normalized to NULL on write so a later '' .split(',') never manufactures a phantom entity, STORY-005: append_chat_message and list_chat_messages, The session_id parameter is authoritative for both write and predicate; StoredMessage.session_id is never read, A foreign or unknown session_id raises StorageError with one identical message -- unknown and foreign are deliberately indistinguishable (+6 more)

### Community 93 - "Reflex Chat UI Story Board"
Cohesion: 0.18
Nodes (14): POST /query Endpoint, PRD-002 Story Board, PRD-002: Embedded Chat UI (Reflex), api_transformer Single-Port Mount, ChatState (Reflex), run_query() Shared Pipeline Function, asyncio.to_thread Event-Loop Offload, PRD-005 Story Board (+6 more)

### Community 94 - "Session ID Threading Stories"
Cohesion: 0.16
Nodes (14): STORY-010: QueryRequest.session_id with UUID validation and a 403 on a foreign session, Ownership rule lives in exactly one module (chat_sessions), STORY-011: AuditQueryEntry.session_id so GET /audit reports the conversation, STORY-015: Restore a transcript on sign-in and on switch, rehydrating all seven bubble kinds, STORY-016: New chat, rename, delete, and a logout that clears state without deleting rows, logout() clears state; delete_session() deletes rows -- distinct operations, STORY-021: Two instances serve one session, and CHAT_HISTORY_ENABLED=false writes nothing, Two application instances sharing one libSQL database (+6 more)

### Community 95 - "Admin Copy Constant Tests"
Cohesion: 0.18
Nodes (13): _public_constants(), STORY-016 — the console's copy assertions that carry a correctness claim. **Why…, AC2 / Risk 4 mitigation, verbatim: "The completion label is covered by a copy…, AC4 / Risk 4's first clause: all-time figures beside a 100-row window "invite a…, AC5 / PRD-006 Section 9, verbatim: "an empty, malformed or wrong token produces…, Every public uppercase name in admin_copy, as (name, value) pairs., AC3: each constant in `admin_copy.py` asserted non-empty. The division of…, AC1 / Risk 4: the completion figure says what it actually counts. PRD-006… (+5 more)

### Community 96 - "Settings & Env Example"
Cohesion: 0.15
Nodes (10): A remote endpoint without its credential is a startup error, not a retry. Both…, Settings, BaseSettings, .env.example, model_validator, AC 5: the default is removed, not replaced with another default.…, test_database_url_is_required_with_no_default(), test_settings_construct_without_new_env_vars() (+2 more)

### Community 98 - "Row Wrapper"
Cohesion: 0.15
Nodes (6): A result row that answers both `row["timestamp"]` and `(count,) = row`. libSQL…, _Row, _audit_log_from_source(), The `AuditLog` the source row should produce once migrated., Layer C -- the rows come back through `get_audit_log()` (AC 8). Layer B proves…, _verify_read_back()

### Community 99 - "Summary Figure Render Tests"
Cohesion: 0.15
Nodes (13): parametrize, AC 1, in the half a component test can carry. The nine labels are on…, A figure's label, value, scope, share and ranked items all reach the output — a…, AC 7's "no accent colour". The four inks are the register's legend, one per…, PRD-006 Section 4, from the source side. Complements the `sys.modules` probe:…, The two chat-only inks and the five tints, from the source side —…, test_every_figure_field_is_rendered(), test_every_figure_var_reaches_the_sheet() (+5 more)

### Community 100 - "Admin Endpoints & Auth Reports"
Cohesion: 0.32
Nodes (12): require_admin_token dependency (HTTPBearer + compare_digest), STORY-009 Report: admin auth middleware, STORY-010 Report: GET /audit endpoint, GET /audit: count_audit_logs/list_audit_logs, _row_to_audit_log, STORY-011 Report: GET /stats endpoint, GET /stats: six aggregate repository functions, success_rate formatting, STORY-012 Report: integration test suite, tests/test_integration.py cross-cutting e2e suite (+4 more)

### Community 101 - "Database Reachability Probe"
Cohesion: 0.17
Nodes (7): check_database_reachable(), One round trip, at boot, so an unreachable database is not a runtime surprise.…, _count_statements(), Counts the statements that reach the database, and delegates the rest. The same…, AC5: one round trip, not a handshake-plus-retry loop. Same recording-proxy…, _RecordingConnection, test_guard_issues_exactly_one_extra_statement()

### Community 102 - "Summary Sheet Tests"
Cohesion: 0.17
Nodes (11): Smoke and invariant tests for the summary's tally sheet. The same two halves…, AC 2's first half. The indent is a `padding_left` of `theme.STAMP_X`, and it…, The precedence is `AdminState.summary_state`'s, and the fault arm renders the…, AC 7, as the list of what is absent. PRD-006 Risk 6 names the drift this…, Every colour resolves from theme.py (AC 7). A hex in this file is a colour a…, AC 6's "as a subset of the total by their indentation alone". The honest…, test_a_blocked_figure_differs_from_the_total_by_its_indent_alone(), test_no_literal_hex_colour() (+3 more)

### Community 103 - "Reflex Instance Harness"
Cohesion: 0.27
Nodes (4): Instance, One running application process, addressed over its own pipes., Writes one command without waiting for its reply. Separate from `recv` on…, Fails the test with both streams. A dead child must never hang the suite on a…

### Community 104 - "Users Table & Bootstrap CLI"
Cohesion: 0.20
Nodes (11): STORY-002 Report: Users Table Schema, Storage-only layer separation design, idx_users_token_hash unique index, User dataclass + CRUD helpers, users table (SQLite), STORY-004 Report: manage_users.py CLI, scripts/manage_users.py CLI, RBAC_DEFAULT_ROLE setting (+3 more)

### Community 105 - "Connection Layer Swap"
Cohesion: 0.18
Nodes (11): conftest fixture contract: yields a str URL, never a Path, database_url_factory: session-scoped seam for module-scoped subprocess probes, STORY-003: centralize DATABASE_URL test fixture, _Row/_Cursor/_Connection wrappers restore named access and iteration the raw driver lacks, Explicit commit()/rollback() in _Connection.__exit__ rather than inherited context-manager semantics, STORY-006: swap database.py onto shared libSQL client, Per-thread client cache keyed on (DATABASE_URL, TURSO_AUTH_TOKEN), Duplicate-column ADD COLUMN failure treated as convergence, not error (+3 more)

### Community 106 - "Batched Summary Snapshot"
Cohesion: 0.24
Nodes (11): SummarySnapshot.figures/.errors partition ten figures so one bad column names itself (PRD Risk 6), STORY-010: one batched summary_snapshot() read for all ten figures, Statement-level failure falls back to ten standalone reads, paying round trips only when already broken, summary_snapshot(): ten scalar/json_group_array subqueries in one SELECT, no client batch API exists, STORY-011: GET /stats consumes the batched read, row_limit=0 empties the unused 'rows' figure so /stats does not pull 100 audit rows it never reads, Resolution: commit stays transactional, only attribution is rescued -- nothing partial is ever committed, STORY-012: AdminState._READS consumes the batched read (+3 more)

### Community 107 - "Chat Table DDL & Session ID"
Cohesion: 0.18
Nodes (11): duplicate_relative_info/duplicate_release_info deliberately have no column -- recomputed on load, STORY-002: chat_sessions/chat_messages DDL and dataclasses, session_id declared in both AUDIT_LOGS_ADDED_COLUMNS and CREATE_AUDIT_LOGS_TABLE so fresh DBs need no ALTER, Four chat DDL executes land in init_db()'s existing single _session() block, not a second transaction, STORY-003: init_db() creates transcript tables and converges session_id column, Sanctioned deviation: test_two_instance_smoke.py's exact table-list pin must grow from two tables to four, STORY-008: session_id on AuditLog, log_query and insert_audit_log, _row_to_audit_log serves two row shapes (_Row off the wire and the summary_snapshot json dict) -- a new column must be added to both inputs (+3 more)

### Community 108 - "Harness IA MVP Concepts"
Cohesion: 0.18
Nodes (11): PRD-001 Story Board, PRD-001: Harness IA - MVP, ADMIN_TOKEN Bearer Authentication, Audit Logging Pipeline (audit_logs), 24h Exact-Match Duplicate Detection, OpenRouter Client Wrapper, Suspicious Pattern Blocklist Detection, Recall-Biased Confidence Threshold (+3 more)

### Community 109 - "Session Rail Spine & Shell"
Cohesion: 0.22
Nodes (11): STORY-018: session_rail.py: the spine as the active mark, three states, no fill and no pill, The spine as sole active-session mark (no fill, no pill, no bold), STORY-019: The rail in the shell: full-width masthead, collapse at narrow viewport, STORY-020: Palette-drift and contrast assertions so the sidebar default fails a test, _new_chat_control(), **New chat**, and what it produces is a chat. PRD Section 6.1 refuses "a bright…, 50 most recent of 212" — the window, stated against the whole shelf. PRD-006…, The rail — or nothing at all, when this deployment keeps no history. **The one… (+3 more)

### Community 110 - "Test Provenance & Client Recovery"
Cohesion: 0.18
Nodes (11): STORY-023: test_untouched_app.py: retire closed-question provenance guards, convert to a coverage census, Provenance-guard defect: fixed-baseline diff against a moving tree stopped answering its own question after a main merge, STORY-024: Recover the shared libSQL client when its stream dies, Discard-and-rebuild recovery for a dead cached libSQL client, _shared_client, _translated, harness-ai Compose Service, CI Workflow (GitHub Actions) (+3 more)

### Community 111 - "Chat Session Listing"
Cohesion: 0.20
Nodes (11): list_chat_sessions(), One `chat_sessions` row as the dataclass STORY-002 declared. No coercion,…, One user's sessions, newest activity first. `WHERE user_id = ? ORDER BY…, _row_to_chat_session(), ChatSession, AC 4, the half that matters. Note bob genuinely has a session -- a test where…, The rail asks before it knows whether the user has ever sent anything., test_list_never_returns_another_users_rows() (+3 more)

### Community 112 - "Frontend Dev Dependencies"
Cohesion: 0.18
Nodes (11): devDependencies, autoprefixer, @emotion/react, postcss, postcss-import, @react-router/dev, @react-router/fs-routes, tailwindcss (+3 more)

### Community 113 - "Authz Permission Matrix"
Cohesion: 0.20
Nodes (10): STORY-006 Report: authz Permission Matrix, app/services/authz.py module, PermissionDenied exception, ROLE_PERMISSIONS matrix (admin/auditor/user), STORY-007 Report: Roles File Override, AuthzConfigError exception, Dual lifespan registration pattern (app.main + chat_ui), authz.load() startup loader (+2 more)

### Community 114 - "Chat Component Import Tests"
Cohesion: 0.20
Nodes (7): probe(), fixture, Smoke test for the Reflex component layer. Every other chat test exercises…, Catches circular imports and names missing at module scope., PRD-004 'no silent drops', enforced at the render layer., test_component_modules_import(), test_every_kind_renders_a_component()

### Community 115 - "Session Rail Tests"
Cohesion: 0.20
Nodes (9): Smoke and invariant tests for the session rail. Two halves, following…, The story's last technical note, checked rather than trusted., AC 2. One mark, in `SPINE`, on the active arm of the row's `rx.cond` -- and…, `theme.py` is the only place a colour is spelled., `copy.py`'s rule for this surface: the rail "renders these two constants and…, test_no_colour_is_written_as_a_literal_hex(), test_the_active_mark_is_spine_and_appears_once_per_row(), test_the_fault_state_does_not_render_the_storage_layers_words() (+1 more)

### Community 116 - "Session Summary Model Plans"
Cohesion: 0.28
Nodes (9): ChatSessionSummary model (session_id, title, activity_info), derive_title(prompt) auto-title truncation, STORY-012 Plan: ChatSessionSummary and formatting.py, format_activity(updated_at, now) relative time, rx.Base unavailable in pinned reflex==0.9.6.post1, STORY-013 Plan: ChatState session list and lazy create, Lazy chat_sessions.create() in _do_send, login() converted to a plain async handler (+1 more)

### Community 117 - "Forbidden Response & Login"
Cohesion: 0.25
Nodes (9): STORY-008 Report: Forbidden Response Schema, QueryBlockedForbiddenResponse model, STORY-010 Report: Pipeline Identity Authorization, Required (non-default) identity parameter design, run_query() step-0 authorization, STORY-014 Report: Chat UI Login, ChatState.login()/logout() token-based session, render_forbidden() chat bubble (+1 more)

### Community 118 - "DDL Column Verification"
Cohesion: 0.28
Nodes (9): _ddl_body(), _ddl_columns(), _ddl_defaults(), The column names a CREATE TABLE statement declares, in declaration order.…, Column name -> the value the destination applies when the INSERT omits it.…, Layer B -- every column of every row, compared cell by cell (AC 3). Exhaustive…, _verify_content(), The DDL parser is the single source of truth for the column list. Pinned… (+1 more)

### Community 119 - "Config Boundary Tests"
Cohesion: 0.22
Nodes (9): parametrize, AC 2: both remote schemes require the credential, not just libsql://., AC 4: never a file, never silently ignored, and the error is actionable.…, AC 6: the credential is "never echoed in error messages" (PRD Section 9)., AC 2: a limit of 0 renders an empty rail on a user who has sessions. `"0"` is…, test_a_chat_session_limit_below_one_is_a_startup_error(), test_any_sqlite_url_is_rejected_and_the_message_names_the_replacement(), test_no_failure_message_ever_echoes_the_token() (+1 more)

### Community 120 - "Transcript Persist & Restore Plans"
Cohesion: 0.39
Nodes (8): _append_and_persist(bubble, identity, session_id) helper, STORY-014 Plan: transcript persistence write, _to_stored_message(bubble, session_id) serializer, Two guarded arms: transcript_error vs sessions_error, STORY-015 Plan: transcript restore, rx.page on_load confirmed but not wired, select_session(session_id) handler, _to_chat_message(row) deserializer (inverse of _to_stored_message)

### Community 121 - "RBAC Config & Model Allowlist"
Cohesion: 0.25
Nodes (8): STORY-005 Report: RBAC Configuration Settings, model_allowlist_list parsing property, RBAC_ENABLED / RBAC_ROLES_FILE / MODEL_ALLOWLIST settings, authorize(identity, permission) function, Deny-by-default authorization policy, STORY-011 Report: Model Allowlist and BYOK, authorize_model(identity, model) function, _deny() shared denial helper

### Community 122 - "Rail Source AST Probe"
Cohesion: 0.25
Nodes (8): AST, code_strings(), _docstring_nodes(), probe(), fixture, Every string literal the rail's *code* contains, docstrings excluded., Every `ast.Constant` that is a docstring, by identity. This module argues its…, source()

### Community 123 - "Session Ownership 403 Plans"
Cohesion: 0.43
Nodes (7): session_id ownership 403 in POST /query router, STORY-010 Plan: QueryRequest.session_id, chat_sessions.owns() service function, QueryRequest.session_id field + UUID4 validator, AuditQueryEntry.session_id passthrough projection, Byte-equality vs coverage-census resolution for AC5, STORY-011 Plan: AuditQueryEntry.session_id

### Community 124 - "Additive Audit Column Migration"
Cohesion: 0.29
Nodes (7): STORY-001 Report: Additive Audit-Log Migration, _add_missing_columns() migration helper, AUDIT_LOGS_ADDED_COLUMNS mapping, Additive-migration idempotence design, STORY-009 Report: Audit RBAC Columns, audit_logs.role / audit_logs.denied_permission columns, log_query() role/denied_permission kwargs

### Community 125 - "Auth Dependencies & Endpoint Gates"
Cohesion: 0.33
Nodes (7): STORY-012 Report: Auth Dependencies, require_admin_token reimplementation on Identity, require_identity FastAPI dependency, require_permission(permission) dependency factory, STORY-015 Report: Admin Endpoint Permissions, /audit endpoint audit:read:all vs audit:read:own scoping, /stats endpoint stats:read gating

### Community 126 - "ChatState History Flag"
Cohesion: 0.33
Nodes (7): Derived display fields precomputed in the backend, never at render, STORY-013: ChatState holds the session list, creates lazily on first send, CHAT_HISTORY_ENABLED feature flag, Lazy session creation on first send, STORY-014: Persist each bubble after append, touch the session, degrade without losing the turn, Audit write and transcript write are independent, one may fail without the other, _do_send

### Community 127 - "Settings Field Validators"
Cohesion: 0.29
Nodes (5): field_validator, At least one session listed, or a startup error (PRD-008). A limit of 0 renders…, The scheme part of a URL, and the only part of one any message quotes. A libSQL…, A libSQL endpoint, or a startup error -- never a file (PRD-007)., _scheme_of()

### Community 128 - "Reflex Agent Skills"
Cohesion: 0.48
Nodes (5): reflex-dev/agent-skills plugin marketplace, reflex-docs skill, Reflex (full-stack Python web framework), reflex-process-management skill, setup-python-env skill

### Community 129 - "History Flag Absent Rail Tests"
Cohesion: 0.29
Nodes (7): AC 10, verbatim: "the rail is **absent** -- not empty, not disabled."…, The specific falsehood this branch exists to remove. With the flag off the…, The control. Every assertion above is satisfied by a function that returns…, _render_with_flag(), test_the_absent_rail_does_not_render_the_invitation(), test_the_rail_is_absent_when_history_is_off(), test_the_rail_is_present_when_history_is_on()

### Community 130 - "Project Scaffolding Reports"
Cohesion: 0.33
Nodes (6): app/config.py typed pydantic-settings Settings, app/main.py FastAPI app + /health route, STORY-001 Report: project scaffolding, audit_logs DDL + AuditLog dataclass (no IP/location), get_connection/init_db/insert_audit_log/get_audit_log, STORY-002 Report: SQLite audit schema

### Community 131 - "Driver Spike & SQL Aggregation"
Cohesion: 0.33
Nodes (6): Driver selection via empirical spike, Fresh-client read-back as durability evidence, STORY-001: libSQL driver spike, NULL seed (not '') preserves genuine empty segments, reproducing str.split(',') exactly, STORY-009: aggregate top_pii_entities() in SQL, Recursive CTE splits comma-separated pii_entities server-side instead of transferring every row

### Community 132 - "Rail Tokens & Copy Rules"
Cohesion: 0.33
Nodes (6): STORY-017: Rail tokens in theme.py and every rail string in copy.py, No literal user-facing text in a component; every string resolves from copy.py, No new ink rule: rail reuses existing ground/verdict tokens only, Single-file token rule: all sizes/colors declared once in theme.py, copy.py rail strings, theme.py rail tokens

### Community 133 - "Audit & Figure Projection Tests"
Cohesion: 0.33
Nodes (6): parametrize, AC 4, at the projection the console actually uses., AC 6. The cut is the figure's *value* because the ranked reads return names…, test_each_constructed_log_reaches_the_row_with_its_verdict(), test_each_ranked_figure_states_its_cut_and_carries_its_items(), test_every_wrong_token_is_refused()

### Community 134 - "Control Focus Ring Tests"
Cohesion: 0.33
Nodes (6): _controls_source(), The ring `theme.GLOBAL_CSS` grants must not be taken back locally.…, Just the control factories, from `_control_label` down to `_scope_line`. Sliced…, AC 2's "visibly marked", against PRD-006 Risk 6's "no fills". The mark is the…, test_the_controls_set_no_focus_reset(), test_the_selected_verdicts_are_marked_without_a_fill()

### Community 135 - "Register Match Arm Tests"
Cohesion: 0.33
Nodes (6): _match_arms(), AC 4, at the render layer: an error is never presented as emptiness. The…, The `rx.match` arms in `_register_body`, one per line., All four keys `admin_state.REGISTER_STATES` declares are matched. A state with…, test_every_register_state_has_an_arm(), test_the_fault_arm_renders_the_table_not_an_empty_state()

### Community 136 - "Identity Resolution Report"
Cohesion: 0.40
Nodes (5): STORY-003 Report: Identity Resolution, ADMIN_TOKEN break-glass credential, hash_token/hash_prompt isolation design, Identity(user_id, role) frozen dataclass, resolve(token) identity resolution function

### Community 137 - "Query Router Auth & Docs"
Cohesion: 0.40
Nodes (5): STORY-013 Report: Query Router Authentication, POST /query bearer authentication wiring, QueryRequest.user_id becomes optional/deprecated, STORY-018 Report: RBAC Documentation, README.md RBAC documentation updates

### Community 138 - "Safe Endpoint Redaction"
Cohesion: 0.40
Nodes (5): `scheme://host[:port]` -- no userinfo, no path, no query, no fragment.…, _safe_endpoint(), AC1 wants the endpoint named. A scheme alone would not tell two apart., test_safe_endpoint_degrades_rather_than_echoing_an_unparseable_url(), test_safe_endpoint_keeps_the_port_so_the_message_identifies_the_database()

### Community 139 - "Test Removal Guard Plan"
Cohesion: 0.83
Nodes (4): STORY-023 Plan: test_untouched_app.py rescope, Working-tree diff vs pinned baseline answers the wrong question, test_no_test_was_removed_from_the_six_pinned_suites (name census), _DELIBERATELY_SUPERSEDED_TESTS allowlist

### Community 140 - "Workflow Slash Commands"
Cohesion: 0.50
Nodes (4): /create-prd command, /create-stories command, /implement command, /plan command

### Community 141 - "Exception Characterization"
Cohesion: 0.50
Nodes (4): Characterization test pins current behavior, not desired behavior, Discrepancy A: duplicate-check failure is 500, not graceful degradation, Discrepancy B: duplicate token_hash indistinguishable from duplicate user_id at CLI, STORY-002: exception characterization tests

### Community 142 - "Module-Owned Storage Errors"
Cohesion: 0.50
Nodes (4): Narrowed 401 catch: only missing-table folds to None, other failures now surface as 500, STORY-004: module-owned error surface (app/db/errors.py), StorageError/MissingRelationError/IntegrityError hierarchy mirrors sqlite3.Error, _translated()/_session() context managers as the single driver-exception seam

### Community 143 - "Feature Flag Switches"
Cohesion: 0.50
Nodes (4): DB_BOOTSTRAP_ENABLED escape hatch for the Docker builder stage, CHAT_HISTORY_ENABLED master switch, off state fully supported from the same image, CHAT_SESSION_LIMIT validator rejects <1 to avoid a silently empty rail, STORY-001: CHAT_HISTORY_ENABLED and CHAT_SESSION_LIMIT settings

### Community 144 - "Relative Time Humanizer Tests"
Cohesion: 0.50
Nodes (4): _humanize(), parametrize, A duplicate card is the first thing many users see; "1 seconds ago" undermines…, test_relative_time_reads_naturally_at_every_boundary()

### Community 145 - "Pinned Suite Guard Tests"
Cohesion: 0.50
Nodes (4): _git(), Run a git command at the repo root; None when git/history is unavailable.…, AC 8, turned from a promise into an assertion. The story requires…, test_the_three_pinned_suites_are_unmodified_in_the_working_tree()

### Community 146 - "Sort Direction Mark Tests"
Cohesion: 0.50
Nodes (4): _as_compiled(), How a non-ASCII mark actually appears in the compiled JSX. Reflex emits the…, Three marks on screen would say three orderings are in force at once, where…, test_the_direction_mark_rides_only_on_the_active_control()

### Community 147 - "Route Reservation Tests"
Cohesion: 0.83
Nodes (3): _harness_route_paths(), test_expected_harness_routes_present(), test_no_route_collides_with_reflex_reserved_routes()

### Community 148 - "Frontend Build Scripts"
Cohesion: 0.67
Nodes (3): scripts, dev, export

### Community 149 - "Raw Audit Retention Test"
Cohesion: 0.67
Nodes (3): _count_audit_rows(), AC3 (the actual promise, PRD RF-7): the persisted row is never masked., test_audit_row_keeps_both_raw_previews_and_raw_hashes()

### Community 150 - "Component Import Probe"
Cohesion: 0.67
Nodes (3): probe(), fixture, source()

### Community 151 - "Component Import Probe"
Cohesion: 0.67
Nodes (3): probe(), fixture, source()

## Ambiguous Edges - Review These
- `hash_prompt()` → `STORY-008: Tests - redaction cannot affect dedup/pattern-check behavior`  [AMBIGUOUS]
  .agents/stories/PRD-003-pii-redaction/STORY-008-dedup-pattern-isolation-tests.md · relation: references
- `Pending state flag and single in-flight guard` → `Redesigned shell: header with session identity and empty state`  [AMBIGUOUS]
  .agents/reports/PRD-004-chat-ui-redesign/STORY-014-shell-header-empty-state.report.md · relation: references

## Knowledge Gaps
- **161 isolated node(s):** `name`, `type`, `dev`, `export`, `@radix-ui/react-form` (+156 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 1525 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **97 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `hash_prompt()` and `STORY-008: Tests - redaction cannot affect dedup/pattern-check behavior`?**
  _Edge tagged AMBIGUOUS (relation: references) - confidence is low._
- **What is the exact relationship between `Pending state flag and single in-flight guard` and `Redesigned shell: header with session identity and empty state`?**
  _Edge tagged AMBIGUOUS (relation: references) - confidence is low._
- **Why does `ChatState` connect `ChatState Session Actions` to `Chat Session Acceptance Criteria`, `Chat UI Story Plans`, `Audit Aggregate Read Functions`, `Session Title & Activity Formatting`, `ChatState Error Handling Tests`, `Authorization Service`, `Request & Response Schemas`, `Admin Console Risk Mitigations`, `Query Pipeline & Policy Refusal`, `Pipeline Session Passthrough Tests`, `Chat Message Model & Persistence`, `Session Rail Component`, `Duplicate Detection Service`, `New Chat & Transcript Restore`, `RBAC Ingress Parity Tests`, `Chat Pipeline Integration Stories`, `OpenRouter Client`, `Session Ordering & Deletion Tests`, `Session Rail Spine & Shell`, `Chat Session Listing`, `ChatState History Flag`?**
  _High betweenness centrality (0.072) - this node is a cross-community bridge._
- **Why does `AuditLog` connect `Audit Log Storage & PII Columns` to `Schema Migration & DB Tests`, `Admin State Load & Auth Tests`, `Admin Row Formatting`, `Audit Aggregate Read Functions`, `Chat Session CRUD`, `Admin Row & Figure Models`, `ChatState Error Handling Tests`, `Chat Sessions Service Tests`, `Database Layer Plans`, `Session Ownership Tests`, `Shared libSQL Client`, `Admin Copy & State Tests`, `Query Router Tests`, `Turso Migration CLI Tests`, `RBAC Story Board`, `Admin Console Risk Mitigations`, `Token Hashing & Identity`, `Duplicate Detection Service`, `New Chat & Transcript Restore`, `RBAC Ingress Parity Tests`, `Audit Logger Tests`, `Turso Migration Script`, `Chat Sessions Story Board`, `Row Wrapper`?**
  _High betweenness centrality (0.067) - this node is a cross-community bridge._
- **Why does `get_connection()` connect `Schema Migration & DB Tests` to `Chat Session Acceptance Criteria`, `Audit Aggregate Read Functions`, `Chat Session CRUD`, `Audit Log Storage & PII Columns`, `Users Table CRUD`, `ChatState Error Handling Tests`, `Chat Sessions Service Tests`, `Database Layer Plans`, `Session Ownership Tests`, `Shared libSQL Client`, `Raw Audit Retention Test`, `Query Router Tests`, `Turso Migration CLI Tests`, `Session ID Over POST /query`, `Chat Sessions Service Module`, `PII End-to-End Integration Tests`, `Query Pipeline & Policy Refusal`, `Pipeline Session Passthrough Tests`, `New Chat & Transcript Restore`, `RBAC Ingress Parity Tests`, `Turso Migration Story Board`, `PII Dedup Isolation Tests`, `Migration Fingerprint & Outcome`, `Database URL Test Fixtures`, `Connection Wrapper`, `Turso Migration Script`, `Pipeline Integration Tests`, `Session Ordering & Deletion Tests`, `Database Reachability Probe`?**
  _High betweenness centrality (0.038) - this node is a cross-community bridge._
- **Are the 39 inferred relationships involving `ChatState` (e.g. with `index()` and `_failure()`) actually correct?**
  _`ChatState` has 39 INFERRED edges - model-reasoned connections that need verification._
- **Are the 27 inferred relationships involving `Identity` (e.g. with `require_admin_token()` and `require_identity()`) actually correct?**
  _`Identity` has 27 INFERRED edges - model-reasoned connections that need verification._