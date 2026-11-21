# coverage.md — checklist audit toan repo

Sinh tu `git ls-files` — 773 file tracked.
`[ ]` chua audit · `[x]` da audit · `[skip]` co y bo qua kem ly do.

## VI TRI DANG DO
Xong 11 module o do sau day du 8 muc (Bước 0 == Bước 4 o ca 11):
   1. src.schemas       ( 5 file,  46 khoi /   368 muc)
   2. src.cache         ( 1 file,  12 khoi /    96 muc)
   3. src.guardrails    ( 3 file,  11 khoi /    88 muc)
   4. src.llm           ( 4 file,  34 khoi /   272 muc)
   5. src.config        ( 1 file,  83 khoi /   664 muc)
   6. src.chat.session  ( 5 file,  44 khoi /   352 muc)
   7. src.db            ( 4 file,  46 khoi /   368 muc)
   8. src.utils         ( 8 file,  47 khoi /   376 muc)
   9. src.rag           ( 8 file,  84 khoi /   672 muc)
  10. src.chat.routing  ( 7 file, 170 khoi / 1.360 muc)
  11. src.chat          (11 file, 141 khoi / 1.128 muc)
  Tong: 57 file, 718 khoi, 5.744 muc.

Con lai trong src/: src.api, src.crawler, src.di (di.py), src.main.
Sau do: research/evaluation/ (du 8 muc).
Phan con lai (datagen, LLMData, dashboards, scripts, docs): kiem ke, danh
dau [inventory] chu khong phai [x].

DINH CHINH da ap trong cac lan duyet sau:
  - src.rag Q-08 ha muc tu "loi" xuong "no thiet ke" (xem src.rag.md §7)
  - src.utils bo sung loi `_no_accent` bo sot chu d (xem src.utils.md §7)
  - src.chat.routing Q-02 va Q-04 sua lai sau khi doi chieu Modelfile that

## FILE

[skip] research/LLMData/acne_dataset.jsonl — ly do: du lieu jsonl
[ ] research/LLMData/chunk_qa/__init__.py — module: LLMData — 16 LOC
[ ] research/LLMData/chunk_qa/config.py — module: LLMData — 170 LOC
[ ] research/LLMData/chunk_qa/generator.py — module: LLMData — 545 LOC
[ ] research/LLMData/chunk_qa/loader.py — module: LLMData — 171 LOC
[ ] research/LLMData/chunk_qa/main.py — module: LLMData — 631 LOC
[ ] research/LLMData/chunk_qa/rule_filter.py — module: LLMData — 416 LOC
[ ] research/LLMData/chunk_qa/safety_cases.py — module: LLMData — 972 LOC
[ ] research/LLMData/chunk_qa/writer.py — module: LLMData — 216 LOC
[ ] research/LLMData/clinical_case/__init__.py — module: LLMData — 14 LOC
[ ] research/LLMData/clinical_case/generator.py — module: LLMData — 551 LOC
[ ] research/LLMData/clinical_case/main.py — module: LLMData — 67 LOC
[ ] research/LLMData/clinical_case/schema.py — module: LLMData — 46 LOC
[ ] research/LLMData/clinical_case/validator.py — module: LLMData — 179 LOC
[ ] research/LLMData/injection_qa/__init__.py — module: LLMData — 14 LOC
[ ] research/LLMData/injection_qa/injection_cases.py — module: LLMData — 1013 LOC
[ ] research/LLMData/injection_qa/main.py — module: LLMData — 349 LOC
[ ] research/LLMData/script.py — module: LLMData — 279 LOC
[skip] _to_delete/datasets_MANIFEST_cu.json — ly do: tracked nhung da xoa trong working tree
[skip] _to_delete/generated_v3_2_MANIFEST.json — ly do: tracked nhung da xoa trong working tree
[ ] config/drugs_acne.yaml — module: config — 277 LOC
[ ] config/guardrails.yaml — module: config — 100 LOC
[ ] config/prompts/clarify_user.j2 — module: config — 11 LOC
[ ] config/prompts/clarify_user.legacy.j2 — module: config — 14 LOC
[ ] config/prompts/knowledge_user.j2 — module: config — 12 LOC
[ ] config/prompts/knowledge_user.legacy.j2 — module: config — 10 LOC
[ ] config/prompts/refuse_user.j2 — module: config — 21 LOC
[ ] config/prompts/reject_user.j2 — module: config — 22 LOC
[ ] config/prompts/stream_user.j2 — module: config — 22 LOC
[skip] research/dashboards/KB/01_chunk_sources_pie.png — ly do: binary/asset (.png)
[skip] research/dashboards/KB/02_top_chunk_sources.png — ly do: binary/asset (.png)
[skip] research/dashboards/KB/03_source_type_distribution.png — ly do: binary/asset (.png)
[skip] research/dashboards/KB/04_trust_level_distribution.png — ly do: binary/asset (.png)
[skip] research/dashboards/KB/05_language_distribution.png — ly do: binary/asset (.png)
[skip] research/dashboards/KB/06_category_distribution.png — ly do: binary/asset (.png)
[skip] research/dashboards/KB/07_chunk_length_histogram.png — ly do: binary/asset (.png)
[skip] research/dashboards/KB/08_chunks_per_document_histogram.png — ly do: binary/asset (.png)
[skip] research/dashboards/KB/09_chunk_length_by_source.png — ly do: binary/asset (.png)
[skip] research/dashboards/KB/10_document_chunk_coverage.png — ly do: binary/asset (.png)
[skip] research/dashboards/KB/11_chunk_position_histogram.png — ly do: binary/asset (.png)
[ ] research/dashboards/README.md — module: dashboards — 33 LOC
[skip] research/dashboards/_overview/01_artifact_scale.png — ly do: binary/asset (.png)
[skip] research/dashboards/architecture/01_system_context.png — ly do: binary/asset (.png)
[skip] research/dashboards/architecture/02_chat_sse_workflow.png — ly do: binary/asset (.png)
[skip] research/dashboards/architecture/03_intake_safety_routing.png — ly do: binary/asset (.png)
[skip] research/dashboards/architecture/04_rag_kb_lifecycle.png — ly do: binary/asset (.png)
[skip] research/dashboards/architecture/05_finetune_data_factory.png — ly do: binary/asset (.png)
[skip] research/dashboards/architecture/06_evaluation_ablation.png — ly do: binary/asset (.png)
[skip] research/dashboards/architecture/07_docker_deployment.png — ly do: binary/asset (.png)
[ ] research/dashboards/architecture/AcneLLM_Architecture.drawio — module: dashboards — 869 LOC
[ ] research/dashboards/architecture/README.md — module: dashboards — 31 LOC
[ ] research/dashboards/architecture/build_drawio.py — module: dashboards — 593 LOC
[skip] research/dashboards/architecture/staruml_desktop.png — ly do: binary/asset (.png)
[ ] research/dashboards/build/README.md — module: dashboards — 13 LOC
[ ] research/dashboards/build/index.html — module: dashboards — 266 LOC
[ ] research/dashboards/build/source_snapshot.json — module: dashboards — 74 LOC
[skip] research/dashboards/evaluation/01_dataset_task_types.png — ly do: binary/asset (.png)
[skip] research/dashboards/evaluation/02_dataset_intents.png — ly do: binary/asset (.png)
[skip] research/dashboards/evaluation/03_expected_kb_sources.png — ly do: binary/asset (.png)
[skip] research/dashboards/evaluation/04_relevant_chunks_per_question.png — ly do: binary/asset (.png)
[skip] research/dashboards/evaluation/05_run_timeline.png — ly do: binary/asset (.png)
[skip] research/dashboards/evaluation/06_intake_headline_metrics.png — ly do: binary/asset (.png)
[skip] research/dashboards/evaluation/07_intake_confusion_matrix.png — ly do: binary/asset (.png)
[skip] research/dashboards/evaluation/08_intake_per_intent_prf.png — ly do: binary/asset (.png)
[skip] research/dashboards/evaluation/09_intake_extraction_field_f1.png — ly do: binary/asset (.png)
[skip] research/dashboards/evaluation/10_intake_scalar_list_quality.png — ly do: binary/asset (.png)
[skip] research/dashboards/evaluation/11_intake_latency.png — ly do: binary/asset (.png)
[skip] research/dashboards/evaluation/12_retrieval_headline_metrics.png — ly do: binary/asset (.png)
[skip] research/dashboards/evaluation/13_retrieval_source_types.png — ly do: binary/asset (.png)
[skip] research/dashboards/evaluation/14_retrieval_sources.png — ly do: binary/asset (.png)
[skip] research/dashboards/evaluation/15_retrieved_chunk_count.png — ly do: binary/asset (.png)
[skip] research/dashboards/evaluation/16_retrieval_score_distributions.png — ly do: binary/asset (.png)
[skip] research/dashboards/evaluation/17_ablation_arm_design.png — ly do: binary/asset (.png)
[skip] research/dashboards/evaluation/17_ablation_execution.png — ly do: binary/asset (.png)
[skip] research/dashboards/evaluation/18_ablation_answer_tone.png — ly do: binary/asset (.png)
[skip] research/dashboards/evaluation/19_ablation_content_errors.png — ly do: binary/asset (.png)
[skip] research/dashboards/evaluation/20_ablation_rag_faces.png — ly do: binary/asset (.png)
[skip] research/dashboards/evaluation/21_ablation_precision_ranking.png — ly do: binary/asset (.png)
[skip] research/dashboards/evaluation/22_ablation_paired_delta_forest.png — ly do: binary/asset (.png)
[skip] research/dashboards/evaluation/23_ablation_cost_quality.png — ly do: binary/asset (.png)
[skip] research/dashboards/evaluation/24_ablation_answer_quality_boxplot.png — ly do: binary/asset (.png)
[skip] research/dashboards/evaluation/25_ablation_latency_boxplot.png — ly do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/01_split_distribution.png — ly do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/02_generation_completion.png — ly do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/03_sample_kind_distribution.png — ly do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/04_sample_family_distribution.png — ly do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/05_input_style_distribution.png — ly do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/06_context_coverage.png — ly do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/07_context_source_count.png — ly do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/08_context_source_names.png — ly do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/09_user_length_histogram.png — ly do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/10_answer_length_histogram.png — ly do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/11_message_count_distribution.png — ly do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/12_audience_distribution.png — ly do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/13_generation_model_distribution.png — ly do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/14_gate_result_distribution.png — ly do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/15_sample_kind_by_split.png — ly do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/16_input_style_by_sample_kind.png — ly do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/17_rejection_reasons.png — ly do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/18_rejection_cases.png — ly do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/19_rejection_attempt_number.png — ly do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/20_retry_outcomes.png — ly do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/21_anchor_group_pair_sizes.png — ly do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/22_integrity_checks.png — ly do: binary/asset (.png)
[skip] research/dashboards/finetune_intaker/01_train_val_split.png — ly do: binary/asset (.png)
[skip] research/dashboards/finetune_intaker/02_intent_distribution.png — ly do: binary/asset (.png)
[skip] research/dashboards/finetune_intaker/03_case_type_distribution.png — ly do: binary/asset (.png)
[skip] research/dashboards/finetune_intaker/04_case_intent_matrix.png — ly do: binary/asset (.png)
[skip] research/dashboards/finetune_intaker/05_user_length_histogram.png — ly do: binary/asset (.png)
[skip] research/dashboards/finetune_intaker/06_confidence_histogram.png — ly do: binary/asset (.png)
[skip] research/dashboards/finetune_intaker/07_extracted_field_presence.png — ly do: binary/asset (.png)
[skip] research/dashboards/finetune_intaker/08_generation_sources.png — ly do: binary/asset (.png)
[skip] research/dashboards/finetune_intaker/09_rejected_attempt_reasons.png — ly do: binary/asset (.png)
[skip] research/dashboards/finetune_intaker/10_target_vs_actual.png — ly do: binary/asset (.png)
[ ] research/dashboards/generate_all.py — module: dashboards — 1341 LOC
[ ] research/dashboards/index.html — module: dashboards — 6 LOC
[ ] research/dashboards/manifest.json — module: dashboards — 1911 LOC
[skip] research/dashboards/repository/01_backend_files_by_package.png — ly do: binary/asset (.png)
[skip] research/dashboards/repository/02_backend_loc_by_package.png — ly do: binary/asset (.png)
[skip] research/dashboards/repository/03_file_types.png — ly do: binary/asset (.png)
[skip] research/dashboards/repository/04_files_by_top_directory.png — ly do: binary/asset (.png)
[skip] research/dashboards/repository/05_source_artifact_size.png — ly do: binary/asset (.png)
[skip] research/dashboards/repository/06_model_artifact_sizes.png — ly do: binary/asset (.png)
[skip] research/dashboards/repository/07_tests_by_domain.png — ly do: binary/asset (.png)
[ ] data/add_more_site.md — module: data — 202 LOC
[skip] data/bm25_index.pkl — ly do: binary/asset (.pkl)
[skip] data/bm25_index.pkl.sha256 — ly do: artifact sinh luc chay (.sha256)
[skip] data/chroma_db/chroma.sqlite3 — ly do: binary/asset (.sqlite3)
[ ] data/error_site.yaml — module: data — 544 LOC
[ ] data/extraction_errors_review.txt — module: data — 207 LOC
[skip] data/golden_extraction_gen.jsonl — ly do: du lieu jsonl
[skip] data/golden_extraction_gen_deepseek.jsonl — ly do: du lieu jsonl
[ ] data/intent_classify.build_metrics.json — module: data — 161 LOC
[skip] data/intent_classify.jsonl — ly do: du lieu jsonl
[skip] data/intent_classify.test.jsonl — ly do: du lieu jsonl
[skip] data/intent_classify.train.jsonl — ly do: du lieu jsonl
[skip] data/sample_queries.jsonl — ly do: du lieu jsonl
[ ] data/seed_sources.yaml — module: data — 873 LOC
[skip] data/subject_oos_eval.jsonl — ly do: du lieu jsonl
[ ] research/datagen/FINETUNE_DATAGEN_PLAN.md — module: datagen.core — 178 LOC
[ ] research/datagen/HANDOFF.md — module: datagen.core — 66 LOC
[ ] research/datagen/RUN.bat — module: datagen.core — 14 LOC
[ ] research/datagen/UNIFIED_INTAKE_DATAGEN_SPEC.md — module: datagen.core — 250 LOC
[ ] research/datagen/__init__.py — module: datagen.core — 2 LOC
[ ] research/datagen/config.py — module: datagen.core — 176 LOC
[ ] research/datagen/contamination.py — module: datagen.core — 125 LOC
[ ] research/datagen/gates.py — module: datagen.core — 1003 LOC
[ ] research/datagen/gen_role_dataset.py — module: datagen.core — 22 LOC
[ ] research/datagen/generator.py — module: datagen.core — 476 LOC
[ ] research/datagen/intake_json_system_prompt.md — module: datagen.core — 125 LOC
[ ] research/datagen/main.py — module: datagen.core — 1261 LOC
[ ] research/datagen/output/v4_role/.false_gate_recovery_v2.done — module: datagen.core — 2 LOC
[ ] research/datagen/output/v4_role/.generator.lock — module: datagen.core — 1 LOC
[skip] research/datagen/output/v4_role/SMOKE_REVIEW.md — ly do: artifact datagen sinh ra
[skip] research/datagen/output/v4_role/SMOKE_REVIEW_V2.md — ly do: artifact datagen sinh ra
[skip] research/datagen/output/v4_role/generation_summary.json — ly do: artifact datagen sinh ra
[skip] research/datagen/output/v4_role/limit_checkpoint.json — ly do: artifact datagen sinh ra
[skip] research/datagen/output/v4_role/rejected.audit.jsonl — ly do: du lieu jsonl
[skip] research/datagen/output/v4_role/v4_role.smoke.jsonl — ly do: du lieu jsonl
[skip] research/datagen/output/v4_role/v4_role.train.jsonl — ly do: du lieu jsonl
[skip] research/datagen/output/v4_role/verification_summary.json — ly do: artifact datagen sinh ra
[ ] research/datagen/render_context.py — module: datagen.core — 68 LOC
[ ] research/datagen/report_stats.py — module: datagen.core — 75 LOC
[ ] research/datagen/role_style_guide.md — module: datagen.core — 65 LOC
[ ] research/datagen/role_taxonomy.yaml — module: datagen.core — 99 LOC
[ ] research/datagen/test_gates.py — module: datagen.core — 146 LOC
[ ] research/datagen/test_pipeline_contracts.py — module: datagen.core — 302 LOC
[ ] research/datagen/writer.py — module: datagen.core — 69 LOC
[ ] research/datagen/intakedata/DATA_PROVENANCE_REPORT.md — module: datagen.intakedata — 56 LOC
[ ] research/datagen/intakedata/PLAN.md — module: datagen.intakedata — 223 LOC
[ ] research/datagen/intakedata/README.md — module: datagen.intakedata — 67 LOC
[ ] research/datagen/intakedata/__init__.py — module: datagen.intakedata — 17 LOC
[ ] research/datagen/intakedata/anchor.py — module: datagen.intakedata — 45 LOC
[ ] research/datagen/intakedata/config.py — module: datagen.intakedata — 239 LOC
[ ] research/datagen/intakedata/conftest.py — module: datagen.intakedata — 90 LOC
[ ] research/datagen/intakedata/gates.py — module: datagen.intakedata — 776 LOC
[ ] research/datagen/intakedata/generator.py — module: datagen.intakedata — 816 LOC
[ ] research/datagen/intakedata/output/.gitignore — module: datagen.intakedata — 2 LOC
[ ] research/datagen/intakedata/pipeline.py — module: datagen.intakedata — 718 LOC
[ ] research/datagen/intakedata/schema.py — module: datagen.intakedata — 301 LOC
[ ] research/datagen/intakedata/seed.py — module: datagen.intakedata — 295 LOC
[ ] research/datagen/intakedata/system_prompt.canonical.txt — module: datagen.intakedata — 25 LOC
[ ] research/datagen/intakedata/taxonomy.yaml — module: datagen.intakedata — 18 LOC
[ ] research/datagen/intakedata/tests/__init__.py — module: datagen.intakedata — 1 LOC
[ ] research/datagen/intakedata/tests/test_anchor.py — module: datagen.intakedata — 30 LOC
[ ] research/datagen/intakedata/tests/test_budget.py — module: datagen.intakedata — 25 LOC
[ ] research/datagen/intakedata/tests/test_gates.py — module: datagen.intakedata — 153 LOC
[ ] research/datagen/intakedata/tests/test_pipeline_contracts.py — module: datagen.intakedata — 306 LOC
[ ] research/datagen/intakedata/tests/test_schema.py — module: datagen.intakedata — 56 LOC
[ ] research/datagen/intakedata/tests/test_seed.py — module: datagen.intakedata — 61 LOC
[ ] research/datagen/intakedata/writer.py — module: datagen.intakedata — 103 LOC
[ ] research/datagen/roledata/PLAN.md — module: datagen.roledata — 297 LOC
[ ] research/datagen/roledata/__init__.py — module: datagen.roledata — 5 LOC
[ ] research/datagen/roledata/anchor.py — module: datagen.roledata — 32 LOC
[ ] research/datagen/roledata/config.py — module: datagen.roledata — 260 LOC
[ ] research/datagen/roledata/conftest.py — module: datagen.roledata — 20 LOC
[ ] research/datagen/roledata/finalize/__init__.py — module: datagen.roledata — 2 LOC
[ ] research/datagen/roledata/finalize/export.py — module: datagen.roledata — 165 LOC
[ ] research/datagen/roledata/finalize/split.py — module: datagen.roledata — 163 LOC
[ ] research/datagen/roledata/gates.py — module: datagen.roledata — 318 LOC
[ ] research/datagen/roledata/generator.py — module: datagen.roledata — 369 LOC
[skip] research/datagen/roledata/output/checksum.sha256 — ly do: artifact sinh luc chay (.sha256)
[skip] research/datagen/roledata/output/dataset_card.md — ly do: artifact datagen sinh ra
[skip] research/datagen/roledata/output/export/acnellm_role_lora.jsonl — ly do: du lieu jsonl
[skip] research/datagen/roledata/output/export/dataset_info.json — ly do: artifact datagen sinh ra
[skip] research/datagen/roledata/output/generation_summary.json — ly do: artifact datagen sinh ra
[skip] research/datagen/roledata/output/rejected.audit.jsonl — ly do: du lieu jsonl
[skip] research/datagen/roledata/output/roledata.smoke.jsonl — ly do: du lieu jsonl
[skip] research/datagen/roledata/output/roledata.train.jsonl — ly do: du lieu jsonl
[skip] research/datagen/roledata/output/splits/holdout.jsonl — ly do: du lieu jsonl
[skip] research/datagen/roledata/output/splits/train.jsonl — ly do: du lieu jsonl
[skip] research/datagen/roledata/output/splits/val.jsonl — ly do: du lieu jsonl
[ ] research/datagen/roledata/pipeline.py — module: datagen.roledata — 625 LOC
[ ] research/datagen/roledata/prompts/B1_grounded_role.j2 — module: datagen.roledata — 1 LOC
[ ] research/datagen/roledata/prompts/B2_missing_answer.j2 — module: datagen.roledata — 1 LOC
[ ] research/datagen/roledata/prompts/B3_irrelevant_chunk.j2 — module: datagen.roledata — 1 LOC
[ ] research/datagen/roledata/prompts/B4_conflicting_docs.j2 — module: datagen.roledata — 1 LOC
[ ] research/datagen/roledata/prompts/B5_depth_anchor.j2 — module: datagen.roledata — 1 LOC
[ ] research/datagen/roledata/prompts/K1_knowledge_anchor.j2 — module: datagen.roledata — 1 LOC
[ ] research/datagen/roledata/prompts/R10_special_population.j2 — module: datagen.roledata — 1 LOC
[ ] research/datagen/roledata/prompts/R1_identity.j2 — module: datagen.roledata — 1 LOC
[ ] research/datagen/roledata/prompts/R2_depth_adaptation.j2 — module: datagen.roledata — 1 LOC
[ ] research/datagen/roledata/prompts/R3_nonjudgment.j2 — module: datagen.roledata — 1 LOC
[ ] research/datagen/roledata/prompts/R4_measured_empathy.j2 — module: datagen.roledata — 1 LOC
[ ] research/datagen/roledata/prompts/R5_natural_clarification.j2 — module: datagen.roledata — 1 LOC
[ ] research/datagen/roledata/prompts/R6_role_boundary.j2 — module: datagen.roledata — 1 LOC
[ ] research/datagen/roledata/prompts/R7_conversation_glue.j2 — module: datagen.roledata — 1 LOC
[ ] research/datagen/roledata/prompts/R8_meta_jailbreak.j2 — module: datagen.roledata — 1 LOC
[ ] research/datagen/roledata/prompts/R9_multiturn.j2 — module: datagen.roledata — 1 LOC
[ ] research/datagen/roledata/style_guide.md — module: datagen.roledata — 18 LOC
[ ] research/datagen/roledata/taxonomy.yaml — module: datagen.roledata — 23 LOC
[ ] research/datagen/roledata/tests/__init__.py — module: datagen.roledata — 1 LOC
[ ] research/datagen/roledata/tests/conftest.py — module: datagen.roledata — 20 LOC
[ ] research/datagen/roledata/tests/test_anchor.py — module: datagen.roledata — 39 LOC
[ ] research/datagen/roledata/tests/test_budget.py — module: datagen.roledata — 24 LOC
[ ] research/datagen/roledata/tests/test_export.py — module: datagen.roledata — 73 LOC
[ ] research/datagen/roledata/tests/test_gates.py — module: datagen.roledata — 234 LOC
[ ] research/datagen/roledata/tests/test_generator.py — module: datagen.roledata — 25 LOC
[ ] research/datagen/roledata/tests/test_split.py — module: datagen.roledata — 49 LOC
[ ] research/datagen/roledata/tests/test_writer.py — module: datagen.roledata — 17 LOC
[ ] research/datagen/roledata/writer.py — module: datagen.roledata — 82 LOC
[ ] research/datagen/roledatav2/ROUND2.md — module: datagen.roledatav2 — 137 LOC
[ ] research/datagen/roledatav2/__init__.py — module: datagen.roledatav2 — 14 LOC
[skip] research/datagen/roledatav2/_output.round1.cu/checksum.sha256 — ly do: artifact sinh luc chay (.sha256)
[ ] research/datagen/roledatav2/_output.round1.cu/dataset_card.md — module: datagen.roledatav2 — 42 LOC
[skip] research/datagen/roledatav2/_output.round1.cu/export/acnellm_role_lora.jsonl — ly do: du lieu jsonl
[ ] research/datagen/roledatav2/_output.round1.cu/export/dataset_info.json — module: datagen.roledatav2 — 16 LOC
[ ] research/datagen/roledatav2/_output.round1.cu/generation_summary.json — module: datagen.roledatav2 — 56 LOC
[ ] research/datagen/roledatav2/_output.round1.cu/limit_checkpoint.json — module: datagen.roledatav2 — 26 LOC
[skip] research/datagen/roledatav2/_output.round1.cu/rejected.audit.jsonl — ly do: du lieu jsonl
[skip] research/datagen/roledatav2/_output.round1.cu/roledata.smoke.jsonl — ly do: du lieu jsonl
[skip] research/datagen/roledatav2/_output.round1.cu/roledata.train.jsonl — ly do: du lieu jsonl
[skip] research/datagen/roledatav2/_output.round1.cu/splits/holdout.jsonl — ly do: du lieu jsonl
[skip] research/datagen/roledatav2/_output.round1.cu/splits/train.jsonl — ly do: du lieu jsonl
[skip] research/datagen/roledatav2/_output.round1.cu/splits/val.jsonl — ly do: du lieu jsonl
[ ] research/datagen/roledatav2/anchor.py — module: datagen.roledatav2 — 6 LOC
[ ] research/datagen/roledatav2/config.py — module: datagen.roledatav2 — 328 LOC
[ ] research/datagen/roledatav2/conftest.py — module: datagen.roledatav2 — 20 LOC
[ ] research/datagen/roledatav2/finalize/__init__.py — module: datagen.roledatav2 — 11 LOC
[ ] research/datagen/roledatav2/finalize/__main__.py — module: datagen.roledatav2 — 68 LOC
[ ] research/datagen/roledatav2/finalize/split.py — module: datagen.roledatav2 — 146 LOC
[ ] research/datagen/roledatav2/gates.py — module: datagen.roledatav2 — 520 LOC
[ ] research/datagen/roledatav2/generator.py — module: datagen.roledatav2 — 750 LOC
[ ] research/datagen/roledatav2/knowledge.py — module: datagen.roledatav2 — 141 LOC
[skip] research/datagen/roledatav2/output/checksum.sha256 — ly do: artifact sinh luc chay (.sha256)
[skip] research/datagen/roledatav2/output/dataset_card.md — ly do: artifact datagen sinh ra
[skip] research/datagen/roledatav2/output/export/acnellm_role_lora.jsonl — ly do: du lieu jsonl
[skip] research/datagen/roledatav2/output/export/dataset_info.json — ly do: artifact datagen sinh ra
[skip] research/datagen/roledatav2/output/generation_summary.json — ly do: artifact datagen sinh ra
[skip] research/datagen/roledatav2/output/limit_checkpoint.json — ly do: artifact datagen sinh ra
[skip] research/datagen/roledatav2/output/rejected.audit.jsonl — ly do: du lieu jsonl
[skip] research/datagen/roledatav2/output/roledata.smoke.jsonl — ly do: du lieu jsonl
[skip] research/datagen/roledatav2/output/roledata.train.jsonl — ly do: du lieu jsonl
[skip] research/datagen/roledatav2/output/skeletons.jsonl — ly do: du lieu jsonl
[skip] research/datagen/roledatav2/output/skeletons.smoke.jsonl — ly do: du lieu jsonl
[skip] research/datagen/roledatav2/output/splits/holdout.jsonl — ly do: du lieu jsonl
[skip] research/datagen/roledatav2/output/splits/train.jsonl — ly do: du lieu jsonl
[skip] research/datagen/roledatav2/output/splits/val.jsonl — ly do: du lieu jsonl
[ ] research/datagen/roledatav2/phase1.py — module: datagen.roledatav2 — 377 LOC
[ ] research/datagen/roledatav2/pipeline.py — module: datagen.roledatav2 — 326 LOC
[ ] research/datagen/roledatav2/probe_provider.py — module: datagen.roledatav2 — 251 LOC
[ ] research/datagen/roledatav2/prompts/R5_natural_clarification.j2 — module: datagen.roledatav2 — 12 LOC
[ ] research/datagen/roledatav2/prompts/R9_multiturn.j2 — module: datagen.roledatav2 — 10 LOC
[ ] research/datagen/roledatav2/show_samples.py — module: datagen.roledatav2 — 134 LOC
[ ] research/datagen/roledatav2/taxonomy.yaml — module: datagen.roledatav2 — 115 LOC
[ ] research/datagen/roledatav2/tests/__init__.py — module: datagen.roledatav2 — 0 LOC
[ ] research/datagen/roledatav2/tests/helpers.py — module: datagen.roledatav2 — 168 LOC
[ ] research/datagen/roledatav2/tests/test_config.py — module: datagen.roledatav2 — 268 LOC
[ ] research/datagen/roledatav2/tests/test_context_survives.py — module: datagen.roledatav2 — 160 LOC
[ ] research/datagen/roledatav2/tests/test_distribution.py — module: datagen.roledatav2 — 78 LOC
[ ] research/datagen/roledatav2/tests/test_gates_v2.py — module: datagen.roledatav2 — 249 LOC
[ ] research/datagen/roledatav2/tests/test_grounding_language.py — module: datagen.roledatav2 — 270 LOC
[ ] research/datagen/roledatav2/tests/test_knowledge.py — module: datagen.roledatav2 — 197 LOC
[ ] research/datagen/roledatav2/tests/test_phase1.py — module: datagen.roledatav2 — 373 LOC
[ ] research/datagen/roledatav2/tests/test_pipeline.py — module: datagen.roledatav2 — 314 LOC
[ ] research/datagen/roledatav2/tests/test_r10_rx_warning.py — module: datagen.roledatav2 — 97 LOC
[ ] research/datagen/roledatav2/tests/test_round2.py — module: datagen.roledatav2 — 217 LOC
[ ] research/datagen/roledatav2/tests/test_smoke_all_cases.py — module: datagen.roledatav2 — 234 LOC
[ ] research/datagen/roledatav2/writer.py — module: datagen.roledatav2 — 6 LOC
[ ] research/dataset_viz/README.md — module: dataset_viz — 6 LOC
[ ] research/dataset_viz/generate_report.py — module: dataset_viz — 353 LOC
[ ] research/dataset_viz/plot_datasets.py — module: dataset_viz — 293 LOC
[ ] research/dataset_viz/run_all.py — module: dataset_viz — 72 LOC
[ ] .dockerignore — module: deploy — 26 LOC
[ ] Dockerfile — module: deploy — 35 LOC
[ ] docker-compose.gpu.yml — module: deploy — 9 LOC
[ ] docker-compose.yml — module: deploy — 128 LOC
[ ] docker/nginx/default.conf.template — module: deploy — 61 LOC
[ ] docker/ollama-init.sh — module: deploy — 41 LOC
[ ] docs/CLEANUP_PLAN.md — module: docs — 286 LOC
[ ] docs/CLEANUP_TASKS.md — module: docs — 363 LOC
[ ] docs/DATA_GEN_GIAI_THICH.md — module: docs — 212 LOC
[ ] docs/DEAD_CODE.md — module: docs — 252 LOC
[ ] docs/DOCKER_QUICKSTART.md — module: docs — 248 LOC
[ ] docs/EVAL_BLUEPRINT.md — module: docs — 497 LOC
[ ] docs/EVAL_DIAGRAM_SPEC.md — module: docs — 343 LOC
[ ] docs/README.md — module: docs — 40 LOC
[ ] docs/archive/CODEX_TASK_eval.md — module: docs — 186 LOC
[ ] docs/archive/CODEX_TASK_eval_multiturn.md — module: docs — 128 LOC
[ ] docs/archive/CODEX_TASK_eval_refactor.md — module: docs — 276 LOC
[ ] docs/archive/CONFIG_MAP.md — module: docs — 98 LOC
[ ] docs/archive/DASHBOARD_E2E_QA_PROMPT.md — module: docs — 80 LOC
[ ] docs/archive/DASHBOARD_FIGURES_PROMPT.md — module: docs — 132 LOC
[ ] docs/archive/DASHBOARD_SEMANTIC_PROBE_PROMPT.md — module: docs — 141 LOC
[ ] docs/archive/EVALUATION_REFACTOR_PLAN.md — module: docs — 161 LOC
[ ] docs/archive/EVAL_DASHBOARD_PROMPT.md — module: docs — 142 LOC
[ ] docs/archive/EVAL_VALIDATION_LOOP_PROMPT.md — module: docs — 161 LOC
[ ] docs/archive/README.md — module: docs — 9 LOC
[ ] docs/archive/UNIFIED_INTAKE_INTEGRATION_PLAN.md — module: docs — 150 LOC
[ ] docs/archive/baseline_audit_prompt.md — module: docs — 266 LOC
[ ] docs/archive/baseline_extraction_confidence_design.md — module: docs — 250 LOC
[ ] docs/archive/codex_intent_from_fields_round2.md — module: docs — 142 LOC
[ ] docs/archive/codex_llm_extractor_plan.md — module: docs — 353 LOC
[ ] docs/archive/codex_reorder_softreject_round4.md — module: docs — 112 LOC
[ ] docs/archive/codex_semantic_router_round3.md — module: docs — 129 LOC
[ ] docs/archive/eval_refactor_plan.md — module: docs — 148 LOC
[ ] docs/archive/extraction_fix_handoff.md — module: docs — 196 LOC
[ ] docs/archive/intent_label_de_xuat.md — module: docs — 108 LOC
[ ] docs/archive/prompt_refactor_todo.md — module: docs — 136 LOC
[ ] docs/config_layout.md — module: docs — 131 LOC
[ ] docs/config_reference.md — module: docs — 134 LOC
[ ] docs/dashboard_phan_tich_workflow.md — module: docs — 251 LOC
[ ] docs/eval_pipeline.html — module: docs — 366 LOC
[ ] docs/evaluation_refactor_evidence.md — module: docs — 314 LOC
[ ] docs/history/codex_bottleneck_fix_prompt.md — module: docs — 251 LOC
[ ] docs/history/codex_config_cleanup_prompt.md — module: docs — 342 LOC
[ ] docs/history/codex_datagen_onecmd_prompt.md — module: docs — 121 LOC
[ ] docs/history/codex_datagen_role_prompt.md — module: docs — 170 LOC
[ ] docs/history/codex_debug_eval_prompt.md — module: docs — 95 LOC
[ ] docs/history/codex_eval_module_refactor_prompt.md — module: docs — 500 LOC
[ ] docs/history/codex_eval_rename_prompt.md — module: docs — 124 LOC
[ ] docs/history/codex_eval_simplify_followup_prompt.md — module: docs — 98 LOC
[ ] docs/history/codex_eval_simplify_prompt.md — module: docs — 101 LOC
[ ] docs/history/codex_evaluation_refactor_prompt.md — module: docs — 116 LOC
[ ] docs/history/codex_extract_before_route_prompt.md — module: docs — 153 LOC
[ ] docs/history/codex_fix_citations_contract_prompt.md — module: docs — 103 LOC
[ ] docs/history/codex_grounding_eval_prompt.md — module: docs — 147 LOC
[ ] docs/history/codex_intakedata_build_prompt.md — module: docs — 100 LOC
[ ] docs/history/codex_llm_router_prompt.md — module: docs — 132 LOC
[ ] docs/history/codex_posthoc_citation_prompt.md — module: docs — 168 LOC
[ ] docs/history/codex_roledata_build_prompt.md — module: docs — 103 LOC
[ ] docs/history/codex_round3_prompt.md — module: docs — 122 LOC
[ ] docs/history/codex_runall_monitor_ui_prompt.md — module: docs — 102 LOC
[ ] docs/history/codex_runtime_cleanup_prompt.md — module: docs — 115 LOC
[ ] docs/history/codex_unified_intake_integration_prompt.md — module: docs — 114 LOC
[skip] docs/reports/AcneLLM_config_audit.xlsx — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] docs/reports/DANH_GIA_KHOA_LUAN.md — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] docs/reports/FINALIZE.md — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] docs/reports/TASKS.md — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] docs/reports/artifacts/acnellm_v2_proof.zip — ly do: binary/asset (.zip)
[skip] docs/reports/context.md — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] docs/reports/report.md — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] docs/reports/runtime_audit.md — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] docs/reports/schema_intent_execution_plan.md — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] docs/reports/schema_unification_plan.md — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] docs/reports/smoke_review.md — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[ ] docs/review_input_to_rag_to_prompt.md — module: docs — 247 LOC
[ ] docs/rulebase_audit.md — module: docs — 186 LOC
[ ] docs/schema_mapping.md — module: docs — 157 LOC
[ ] research/evaluation/METRIC_EVIDENCE.md — module: eval.core — 364 LOC
[ ] research/evaluation/README.md — module: eval.core — 170 LOC
[ ] research/evaluation/RERUN_DEEPSEEK.md — module: eval.core — 38 LOC
[ ] research/evaluation/WIKI.html — module: eval.core — 286 LOC
[ ] research/evaluation/__init__.py — module: eval.core — 0 LOC
[ ] research/evaluation/adapters/__init__.py — module: eval.adapters — 0 LOC
[ ] research/evaluation/adapters/_repo.py — module: eval.adapters — 80 LOC
[ ] research/evaluation/common.py — module: eval.core — 106 LOC
[ ] research/evaluation/configs/__init__.py — module: eval.core — 0 LOC
[ ] research/evaluation/datasets/README.md — module: eval.datasets — 105 LOC
[ ] research/evaluation/datasets/__init__.py — module: eval.datasets — 0 LOC
[ ] research/evaluation/datasets/_trash/README.md — module: eval.datasets — 15 LOC
[skip] research/evaluation/datasets/_trash/eval_set.jsonl — ly do: du lieu jsonl
[skip] research/evaluation/datasets/_trash/intake_eval.v2.partial.jsonl — ly do: du lieu jsonl
[skip] research/evaluation/datasets/_trash/intake_eval.v2.smoke.audit.jsonl — ly do: du lieu jsonl
[skip] research/evaluation/datasets/_trash/intake_eval.v2.smoke.partial.jsonl — ly do: du lieu jsonl
[skip] research/evaluation/datasets/_trash/sample.jsonl — ly do: du lieu jsonl
[skip] research/evaluation/datasets/active/MANIFEST.json — ly do: manifest sha256 sinh ra luc freeze
[skip] research/evaluation/datasets/active/generator_eval.v3_2_145.jsonl — ly do: du lieu jsonl
[skip] research/evaluation/datasets/active/generator_eval.v3_2_145.smoke.jsonl — ly do: du lieu jsonl
[skip] research/evaluation/datasets/active/intake_eval.v2_1500.audit.jsonl — ly do: du lieu jsonl
[skip] research/evaluation/datasets/active/intake_eval.v2_1500.jsonl — ly do: du lieu jsonl
[ ] research/evaluation/datasets/archive/README.md — module: eval.datasets — 47 LOC
[skip] research/evaluation/datasets/archive/generator_eval.v2_0_197.jsonl — ly do: du lieu jsonl
[skip] research/evaluation/datasets/archive/generator_eval.v3_1_195.jsonl — ly do: du lieu jsonl
[skip] research/evaluation/datasets/archive/generator_eval.v3_1_199.MANIFEST.json — ly do: manifest sha256 sinh ra luc freeze
[skip] research/evaluation/datasets/archive/generator_eval.v3_1_199.jsonl — ly do: du lieu jsonl
[skip] research/evaluation/datasets/extra/MANIFEST.json — ly do: manifest sha256 sinh ra luc freeze
[ ] research/evaluation/datasets/extra/README.md — module: eval.datasets — 32 LOC
[skip] research/evaluation/datasets/extra/intake_eval.v1_353.jsonl — ly do: du lieu jsonl
[skip] research/evaluation/datasets/extra/intake_eval.v2_smoke_10.jsonl — ly do: du lieu jsonl
[skip] research/evaluation/datasets/extra/intake_pregnancy_probe_41.jsonl — ly do: du lieu jsonl
[ ] research/evaluation/datasets/make_eval_set.py — module: eval.datasets — 1105 LOC
[ ] research/evaluation/datasets/make_intake_set.py — module: eval.datasets — 766 LOC
[ ] research/evaluation/datasets/make_intake_set_v2.py — module: eval.datasets — 926 LOC
[ ] research/evaluation/datasets/make_pregnancy_probe.py — module: eval.datasets — 167 LOC
[skip] research/evaluation/datasets/policy_cases.jsonl — ly do: du lieu jsonl
[ ] research/evaluation/datasets/registry.py — module: eval.datasets — 106 LOC
[ ] research/evaluation/e2e.ps1 — module: eval.core — 347 LOC
[ ] research/evaluation/eval_context.md — module: eval.core — 433 LOC
[ ] research/evaluation/full_evaluation.py — module: eval.core — 415 LOC
[ ] research/evaluation/judges/__init__.py — module: eval.judges — 0 LOC
[ ] research/evaluation/judges/calibrate.py — module: eval.judges — 433 LOC
[ ] research/evaluation/judges/clients.py — module: eval.judges — 269 LOC
[ ] research/evaluation/judges/context.py — module: eval.judges — 221 LOC
[ ] research/evaluation/judges/prompts/claim_extract.md — module: eval.judges — 7 LOC
[ ] research/evaluation/judges/prompts/entailment.md — module: eval.judges — 13 LOC
[ ] research/evaluation/judges/prompts/error_classify.md — module: eval.judges — 20 LOC
[ ] research/evaluation/judges/prompts/pairwise.md — module: eval.judges — 21 LOC
[ ] research/evaluation/judges/prompts/pointwise.md — module: eval.judges — 33 LOC
[ ] research/evaluation/judges/rubrics.py — module: eval.judges — 176 LOC
[ ] research/evaluation/metrics/__init__.py — module: eval.metrics — 0 LOC
[ ] research/evaluation/metrics/classification.py — module: eval.metrics — 75 LOC
[ ] research/evaluation/metrics/deterministic.py — module: eval.metrics — 90 LOC
[ ] research/evaluation/metrics/intake.py — module: eval.metrics — 126 LOC
[ ] research/evaluation/metrics/scorecard.py — module: eval.metrics — 200 LOC
[skip] research/evaluation/reports/ab_intake/acne-intaker-parity.json — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/ab_intake/acne-intaker.json — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/ab_intake/full.json — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/calibration/_goi_gui_di/HUONG_DAN.md — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/calibration/_goi_gui_di/cham.html — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/calibration/calibration_key.jsonl — ly do: du lieu jsonl
[skip] research/evaluation/reports/calibration/calibration_key.v1_nochecklist.jsonl — ly do: du lieu jsonl
[skip] research/evaluation/reports/calibration/calibration_sheet.jsonl — ly do: du lieu jsonl
[skip] research/evaluation/reports/calibration/calibration_sheet.v1_nochecklist.jsonl — ly do: du lieu jsonl
[skip] research/evaluation/reports/calibration/cham.html — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/calibration/cham_60cau.zip — ly do: binary/asset (.zip)
[skip] research/evaluation/reports/calibration/merged_v1v2.json — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/frontier_system_prompt_smoke_20260807/.fingerprint — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/frontier_system_prompt_smoke_20260807/run.log — ly do: artifact sinh luc chay (.log)
[skip] research/evaluation/reports/full_eval_1/ablation/.fingerprint — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/full_eval_1/ablation/results.json — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/full_eval_1/ablation/rows.jsonl — ly do: du lieu jsonl
[skip] research/evaluation/reports/full_eval_1/ablation/run.log — ly do: artifact sinh luc chay (.log)
[skip] research/evaluation/reports/full_eval_1/ablation/summary.json — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/full_eval_1/intake/report.json — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/full_eval_1/retrieval/results.json — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/full_eval_1/summary.json — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/full_eval_part2/ablation/.fingerprint — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/full_eval_part2/ablation/rows.jsonl — ly do: du lieu jsonl
[skip] research/evaluation/reports/full_eval_part2/ablation/run.log — ly do: artifact sinh luc chay (.log)
[skip] research/evaluation/reports/full_eval_part2/intake/report.json — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/full_eval_part2/retrieval/results.json — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/full_eval_part2/summary.json — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/intake_eval/report.json — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/judge_cache.sqlite — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/judge_calibration.json — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/rescore_gpt/v1/rows.jsonl — ly do: du lieu jsonl
[skip] research/evaluation/reports/rescore_gpt/v1/summary.json — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/rescore_gpt/v2/rows.jsonl — ly do: du lieu jsonl
[skip] research/evaluation/reports/rescore_gpt/v2/summary.json — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/rescore_luna/v1/rows.jsonl — ly do: du lieu jsonl
[skip] research/evaluation/reports/rescore_luna/v1/summary.json — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/rescore_luna/v2/rows.jsonl — ly do: du lieu jsonl
[skip] research/evaluation/reports/rescore_luna/v2/summary.json — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/run/intake/report.json — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/run/summary.json — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/run_full/intake/report.json — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/run_full/summary.json — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/run_full_v3_2.zip — ly do: binary/asset (.zip)
[skip] research/evaluation/reports/run_full_v3_2/ASSESSMENT.md — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/run_full_v3_2/ASSESSMENT_review.md — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/run_full_v3_2/GENERATOR_ROOT_CAUSE.md — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/run_full_v3_2/ablation/.fingerprint — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/run_full_v3_2/ablation/results.json — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/run_full_v3_2/ablation/rows.jsonl — ly do: du lieu jsonl
[skip] research/evaluation/reports/run_full_v3_2/ablation/run.log — ly do: artifact sinh luc chay (.log)
[skip] research/evaluation/reports/run_full_v3_2/ablation/summary.json — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/run_full_v3_2/e2e.console.log — ly do: artifact sinh luc chay (.log)
[skip] research/evaluation/reports/run_full_v3_2/intake/report.json — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/run_full_v3_2/retrieval/results.json — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/run_full_v3_2/summary.json — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/smoke_ds/intake/report.json — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/smoke_ds/summary.json — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/v1_round1/rows.jsonl — ly do: du lieu jsonl
[skip] research/evaluation/reports/v2_round2/.fingerprint — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/v2_round2/results.json — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/v2_round2/rows.jsonl — ly do: du lieu jsonl
[skip] research/evaluation/reports/v2_round2/run.log — ly do: artifact sinh luc chay (.log)
[skip] research/evaluation/reports/v2_smoke/.fingerprint — ly do: artifact ket qua cua lan chay truoc, khong phai kien truc
[skip] research/evaluation/reports/v2_smoke/rows.jsonl — ly do: du lieu jsonl
[skip] research/evaluation/reports/v2_smoke/run.log — ly do: artifact sinh luc chay (.log)
[ ] research/evaluation/runners/__init__.py — module: eval.runners — 0 LOC
[ ] research/evaluation/runners/rescore.py — module: eval.runners — 418 LOC
[ ] research/evaluation/runners/run_ablation.py — module: eval.runners — 1451 LOC
[ ] research/evaluation/runners/run_intake.py — module: eval.runners — 1134 LOC
[ ] research/evaluation/runners/run_retrieval.py — module: eval.runners — 196 LOC
[ ] research/evaluation/severity.py — module: eval.core — 124 LOC
[ ] research/evaluation/tests/__init__.py — module: eval.tests — 0 LOC
[ ] research/evaluation/tests/test_classification.py — module: eval.tests — 46 LOC
[ ] research/evaluation/tests/test_context_judge.py — module: eval.tests — 92 LOC
[ ] research/evaluation/tests/test_dataset_dedup.py — module: eval.tests — 288 LOC
[ ] research/evaluation/tests/test_field_accuracy.py — module: eval.tests — 82 LOC
[ ] research/evaluation/tests/test_intake_metrics.py — module: eval.tests — 29 LOC
[ ] research/evaluation/tests/test_make_intake_set.py — module: eval.tests — 453 LOC
[ ] research/evaluation/tests/test_make_intake_set_v2.py — module: eval.tests — 267 LOC
[ ] research/evaluation/tests/test_metrics.py — module: eval.tests — 43 LOC
[ ] research/evaluation/tests/test_per_value_metrics.py — module: eval.tests — 52 LOC
[ ] research/evaluation/tests/test_registry.py — module: eval.tests — 62 LOC
[ ] research/evaluation/tests/test_run_ablation.py — module: eval.tests — 202 LOC
[ ] research/evaluation/tests/test_run_intake.py — module: eval.tests — 130 LOC
[ ] research/evaluation/tests/test_severity_anchor.py — module: eval.tests — 102 LOC
[ ] research/evaluation/tests/test_severity_metrics.py — module: eval.tests — 62 LOC
[ ] research/evaluation/trace.py — module: eval.core — 275 LOC
[ ] frontend/.dockerignore — module: frontend — 6 LOC
[ ] frontend/.eslintrc.json — module: frontend — 4 LOC
[ ] frontend/Dockerfile — module: frontend — 35 LOC
[ ] frontend/next-env.d.ts — module: frontend — 6 LOC
[ ] frontend/next.config.js — module: frontend — 7 LOC
[skip] frontend/package-lock.json — ly do: lockfile/danh sach phu thuoc
[ ] frontend/package.json — module: frontend — 29 LOC
[ ] frontend/postcss.config.js — module: frontend — 6 LOC
[ ] frontend/src/app/globals.css — module: frontend — 38 LOC
[ ] frontend/src/app/layout.tsx — module: frontend — 20 LOC
[ ] frontend/src/app/page.tsx — module: frontend — 5 LOC
[ ] frontend/src/components/chat/ChatWindow.tsx — module: frontend — 283 LOC
[ ] frontend/src/components/chat/ChunkDetailModal.tsx — module: frontend — 134 LOC
[ ] frontend/src/components/chat/MessageBubble.tsx — module: frontend — 187 LOC
[ ] frontend/src/components/chat/MessageInput.tsx — module: frontend — 120 LOC
[ ] frontend/src/components/chat/SourceCard.tsx — module: frontend — 152 LOC
[ ] frontend/src/config/chatConfig.ts — module: frontend — 37 LOC
[ ] frontend/src/hooks/useSSE.ts — module: frontend — 87 LOC
[ ] frontend/src/lib/api.ts — module: frontend — 45 LOC
[ ] frontend/src/lib/types.ts — module: frontend — 51 LOC
[ ] frontend/src/stores/chatStore.ts — module: frontend — 128 LOC
[ ] frontend/tailwind.config.js — module: frontend — 21 LOC
[ ] frontend/tsconfig.json — module: frontend — 28 LOC
[skip] frontend/tsconfig.tsbuildinfo — ly do: artifact sinh luc chay (.tsbuildinfo)
[ ] research/guideline_docs/TAI-PDF.bat — module: guideline_docs — 13 LOC
[ ] research/guideline_docs/build_guideline_chunks.py — module: guideline_docs — 258 LOC
[ ] research/guideline_docs/download_acne_pdfs.py — module: guideline_docs — 184 LOC
[skip] research/guideline_docs/en_docs/text/AAFP-2004.pdf — ly do: binary/asset (.pdf)
[skip] research/guideline_docs/en_docs/text/AAFP-2012.pdf — ly do: binary/asset (.pdf)
[skip] research/guideline_docs/en_docs/text/AAFP-2019.pdf — ly do: binary/asset (.pdf)
[skip] research/guideline_docs/en_docs/text/BMJ-NICE-summary.pdf — ly do: binary/asset (.pdf)
[skip] research/guideline_docs/en_docs/text/CMAJ-2016-canada.pdf — ly do: binary/asset (.pdf)
[skip] research/guideline_docs/en_docs/text/EuroGuiDerm-2025-long.pdf — ly do: binary/asset (.pdf)
[skip] research/guideline_docs/en_docs/text/NICE-NG198-referral.pdf — ly do: binary/asset (.pdf)
[skip] research/guideline_docs/en_docs/text/NICE-NG198.pdf — ly do: binary/asset (.pdf)
[skip] research/guideline_docs/en_docs/text/Skin Health and Disease - 2023 - Corcoran - Systematic review of clinical practice guidelines for acne vulgaris published.pdf — ly do: binary/asset (.pdf)
[skip] research/guideline_docs/en_docs/text/The Journal of Dermatology - 2018 - Hayashi - Japanese Dermatological Association Guidelines  Guidelines for the treatment.pdf — ly do: binary/asset (.pdf)
[skip] research/guideline_docs/en_docs/txt/AAFP-2004.txt — ly do: text trich tu PDF = du lieu
[skip] research/guideline_docs/en_docs/txt/AAFP-2012.txt — ly do: text trich tu PDF = du lieu
[skip] research/guideline_docs/en_docs/txt/AAFP-2019.txt — ly do: text trich tu PDF = du lieu
[skip] research/guideline_docs/en_docs/txt/BMJ-NICE-summary.txt — ly do: text trich tu PDF = du lieu
[skip] research/guideline_docs/en_docs/txt/CMAJ-2016-canada.txt — ly do: text trich tu PDF = du lieu
[skip] research/guideline_docs/en_docs/txt/EuroGuiDerm-2025-long.txt — ly do: text trich tu PDF = du lieu
[skip] research/guideline_docs/en_docs/txt/NICE-NG198-referral.txt — ly do: text trich tu PDF = du lieu
[skip] research/guideline_docs/en_docs/txt/NICE-NG198.txt — ly do: text trich tu PDF = du lieu
[skip] research/guideline_docs/en_docs/txt/Skin Health and Disease - 2023 - Corcoran - Systematic review of clinical practice guidelines for acne vulgaris published.txt — ly do: text trich tu PDF = du lieu
[skip] research/guideline_docs/en_docs/txt/The Journal of Dermatology - 2018 - Hayashi - Japanese Dermatological Association Guidelines  Guidelines for the treatment.txt — ly do: text trich tu PDF = du lieu
[ ] research/guideline_docs/manifest.json — module: guideline_docs — 137 LOC
[ ] research/guideline_docs/merge_guideline_chunks.py — module: guideline_docs — 113 LOC
[ ] research/guideline_docs/pdf_to_text.py — module: guideline_docs — 347 LOC
[ ] research/guideline_docs/reembed_guideline.py — module: guideline_docs — 106 LOC
[skip] research/guideline_docs/vie_docs/scan/Quy\341\272\277t-\304\221\341\273\213nh-4416-Q\304\220-BYT.pdf — ly do: tracked nhung da xoa trong working tree
[skip] research/guideline_docs/vie_docs/text/108-isotretinoin-azithro.pdf — ly do: binary/asset (.pdf)
[skip] research/guideline_docs/vie_docs/text/108-isotretinoin-vitD.pdf — ly do: binary/asset (.pdf)
[skip] research/guideline_docs/vie_docs/text/AnGiang-phac-do-da-lieu.pdf — ly do: binary/asset (.pdf)
[skip] research/guideline_docs/vie_docs/text/BYT-Da-lieu-2015.pdf — ly do: binary/asset (.pdf)
[skip] research/guideline_docs/vie_docs/text/BacNinh-laser-seo-mun.pdf — ly do: binary/asset (.pdf)
[skip] research/guideline_docs/vie_docs/text/CanTho-isotretinoin.pdf — ly do: binary/asset (.pdf)
[skip] research/guideline_docs/vie_docs/text/Hue-azithromycin-adapalene.pdf — ly do: binary/asset (.pdf)
[skip] research/guideline_docs/vie_docs/text/VJDV-dong-thuan-duoc-my-pham.pdf — ly do: binary/asset (.pdf)
[skip] research/guideline_docs/vie_docs/text/VJDV-isotretinoin-so-sanh.pdf — ly do: binary/asset (.pdf)
[skip] research/guideline_docs/vie_docs/text/VJDV-minocyclin.pdf — ly do: binary/asset (.pdf)
[skip] research/guideline_docs/vie_docs/text/YHocTPHCM-2017.pdf — ly do: binary/asset (.pdf)
[skip] research/guideline_docs/vie_docs/txt/108-isotretinoin-azithro.txt — ly do: text trich tu PDF = du lieu
[skip] research/guideline_docs/vie_docs/txt/108-isotretinoin-vitD.txt — ly do: text trich tu PDF = du lieu
[skip] research/guideline_docs/vie_docs/txt/AnGiang-phac-do-da-lieu.txt — ly do: text trich tu PDF = du lieu
[skip] research/guideline_docs/vie_docs/txt/BYT-Da-lieu-2015.txt — ly do: text trich tu PDF = du lieu
[skip] research/guideline_docs/vie_docs/txt/BacNinh-laser-seo-mun.txt — ly do: text trich tu PDF = du lieu
[skip] research/guideline_docs/vie_docs/txt/CanTho-isotretinoin.txt — ly do: text trich tu PDF = du lieu
[skip] research/guideline_docs/vie_docs/txt/Hue-azithromycin-adapalene.txt — ly do: text trich tu PDF = du lieu
[skip] research/guideline_docs/vie_docs/txt/Quy\341\272\277t-\304\221\341\273\213nh-4416-Q\304\220-BYT.txt — ly do: tracked nhung da xoa trong working tree
[skip] research/guideline_docs/vie_docs/txt/VJDV-dong-thuan-duoc-my-pham.txt — ly do: text trich tu PDF = du lieu
[skip] research/guideline_docs/vie_docs/txt/VJDV-isotretinoin-so-sanh.txt — ly do: text trich tu PDF = du lieu
[skip] research/guideline_docs/vie_docs/txt/VJDV-minocyclin.txt — ly do: text trich tu PDF = du lieu
[skip] research/guideline_docs/vie_docs/txt/YHocTPHCM-2017.txt — ly do: text trich tu PDF = du lieu
[ ] research/notebooks/HYPERPARAMS_RATIONALE.md — module: notebooks — 94 LOC
[ ] research/notebooks/HYPERPARAMS_RATIONALE_intake.md — module: notebooks — 81 LOC
[ ] research/notebooks/TRAINING_REPORT.md — module: notebooks — 50 LOC
[ ] research/notebooks/_cu/colab/Finetune.ipynb — module: notebooks — 12469 LOC
[ ] research/notebooks/_cu/colab/Finetune3 (2).ipynb — module: notebooks — 12737 LOC
[ ] research/notebooks/_cu/colab/finetunev2.ipynb — module: notebooks — 12467 LOC
[ ] research/notebooks/_cu/colab/finetunev3 - Copy.ipynb — module: notebooks — 12468 LOC
[ ] research/notebooks/_cu/colab/finetunev3_l4.ipynb — module: notebooks — 12468 LOC
[ ] research/notebooks/generator/finetune_role_qwen25_q4.ipynb — module: notebooks — 9782 LOC
[ ] research/notebooks/generatorv2/GIAI_THICH_NOTEBOOK_V2.md — module: notebooks — 482 LOC
[ ] research/notebooks/generatorv2/finetune_role_v2_qwen25_T4.ipynb — module: notebooks — 678 LOC
[ ] research/notebooks/generatorv2/finetune_role_v2_qwen25_q4.DA_CHAY.ipynb — module: notebooks — 16112 LOC
[ ] research/notebooks/generatorv2/finetune_role_v2_qwen25_q4.ipynb — module: notebooks — 639 LOC
[ ] research/notebooks/intaker/finetune_intake_qwen25_3b_q4(colab).ipynb — module: notebooks — 6596 LOC
[ ] research/notebooks/intaker/finetune_intake_qwen25_3b_q4.ipynb — module: notebooks — 653 LOC
[ ] research/README.md — module: research.misc — 21 LOC
[skip] .codex/config.toml — ly do: tracked nhung da xoa trong working tree
[ ] .env.baseline — module: root — 32 LOC
[ ] .env.docker.example — module: root — 28 LOC
[ ] .gitattributes — module: root — 8 LOC
[ ] .gitignore — module: root — 110 LOC
[ ] README.md — module: root — 314 LOC
[ ] pyproject.toml — module: root — 30 LOC
[skip] requirements-dev.txt — ly do: lockfile/danh sach phu thuoc
[skip] requirements.txt — ly do: lockfile/danh sach phu thuoc
[ ] tasks.sh — module: root — 458 LOC
[skip] uv.lock — ly do: lockfile/danh sach phu thuoc
[ ] scripts/KB.ps1 — module: scripts — 160 LOC
[ ] scripts/RUN.ps1 — module: scripts — 170 LOC
[ ] scripts/ab_template_prompt.ps1 — module: scripts — 111 LOC
[ ] scripts/build_hybrid_finetune_dataset.py — module: scripts — 107 LOC
[ ] scripts/build_intent_dataset.py — module: scripts — 887 LOC
[ ] scripts/build_kb.py — module: scripts — 681 LOC
[ ] scripts/clean_acne_chat_response.py — module: scripts — 518 LOC
[ ] scripts/convert_acne_dataset.py — module: scripts — 184 LOC
[ ] scripts/crawl_all.py — module: scripts — 387 LOC
[ ] scripts/crawl_official_guidelines.py — module: scripts — 298 LOC
[ ] scripts/merge_finetune_datasets.py — module: scripts — 87 LOC
[ ] scripts/prepare_docker_bundle.ps1 — module: scripts — 127 LOC
[ ] scripts/run_all.sh — module: scripts — 55 LOC
[ ] scripts/runpod.ps1 — module: scripts — 162 LOC
[ ] scripts/visualize/output/chromadb_map.html — module: scripts — 3888 LOC
[skip] scripts/visualize/output/chromadb_map.png — ly do: binary/asset (.png)
[ ] scripts/visualize/visualize_chromadb.py — module: scripts — 208 LOC
[ ] src/acne_llm/__init__.py — module: src.__init__ — 2 LOC
[ ] src/acne_llm/api/__init__.py — module: src.api — 0 LOC
[ ] src/acne_llm/api/app.py — module: src.api — 69 LOC
[ ] src/acne_llm/api/deps.py — module: src.api — 34 LOC
[ ] src/acne_llm/api/observability.py — module: src.api — 143 LOC
[ ] src/acne_llm/api/routes/__init__.py — module: src.api — 0 LOC
[ ] src/acne_llm/api/routes/admin.py — module: src.api — 66 LOC
[ ] src/acne_llm/api/routes/chat.py — module: src.api — 236 LOC
[ ] src/acne_llm/api/routes/health.py — module: src.api — 28 LOC
[ ] src/acne_llm/api/routes/kb.py — module: src.api — 115 LOC
[ ] src/acne_llm/api/routes/metrics.py — module: src.api — 19 LOC
[ ] src/acne_llm/api/templates/partials/advise_card.html — module: src.api — 61 LOC
[ ] src/acne_llm/api/templates/partials/search_results.html — module: src.api — 22 LOC
[x] src/acne_llm/cache.py — module: src.cache — 141 LOC
[x] src/acne_llm/chat/__init__.py — module: src.chat — 6 LOC
[x] src/acne_llm/chat/_intake_parse.py — module: src.chat — 394 LOC
[x] src/acne_llm/chat/_intent_patch.py — module: src.chat — 88 LOC
[x] src/acne_llm/chat/_retrieval.py — module: src.chat — 392 LOC
[x] src/acne_llm/chat/_safety.py — module: src.chat — 371 LOC
[x] src/acne_llm/chat/confidence_hint.py — module: src.chat — 124 LOC
[x] src/acne_llm/chat/intake.py — module: src.chat — 854 LOC
[x] src/acne_llm/chat/orchestrator.py — module: src.chat — 187 LOC
[x] src/acne_llm/chat/preprocess.py — module: src.chat — 78 LOC
[x] src/acne_llm/chat/routing/__init__.py — module: src.chat — 10 LOC
[x] src/acne_llm/chat/routing/intent_router.py — module: src.chat — 669 LOC
[x] src/acne_llm/chat/routing/llm_extractor.py — module: src.chat — 103 LOC
[x] src/acne_llm/chat/routing/llm_router.py — module: src.chat — 162 LOC
[x] src/acne_llm/chat/routing/rule_extractor.py — module: src.chat — 406 LOC
[x] src/acne_llm/chat/routing/rule_normalizer.py — module: src.chat — 1975 LOC
[x] src/acne_llm/chat/routing/semantic_router.py — module: src.chat — 393 LOC
[x] src/acne_llm/chat/runtime.py — module: src.chat — 345 LOC
[x] src/acne_llm/chat/session/__init__.py — module: src.chat.session — 46 LOC
[x] src/acne_llm/chat/session/fold.py — module: src.chat.session — 338 LOC
[x] src/acne_llm/chat/session/memory.py — module: src.chat.session — 195 LOC
[x] src/acne_llm/chat/session/models.py — module: src.chat.session — 75 LOC
[x] src/acne_llm/chat/session/view.py — module: src.chat.session — 161 LOC
[x] src/acne_llm/chat/unified_intake.py — module: src.chat — 228 LOC
[ ] src/acne_llm/cli.py — module: src.cli — 51 LOC
[x] src/acne_llm/config.py — module: src.config — 288 LOC
[ ] src/acne_llm/crawler/__init__.py — module: src.crawler — 0 LOC
[ ] src/acne_llm/crawler/checkpoint.py — module: src.crawler — 225 LOC
[ ] src/acne_llm/crawler/dedup.py — module: src.crawler — 135 LOC
[ ] src/acne_llm/crawler/discovery.py — module: src.crawler — 586 LOC
[ ] src/acne_llm/crawler/extractor.py — module: src.crawler — 77 LOC
[ ] src/acne_llm/crawler/fetcher.py — module: src.crawler — 129 LOC
[ ] src/acne_llm/crawler/normalizer.py — module: src.crawler — 12 LOC
[ ] src/acne_llm/crawler/playwright_fetcher.py — module: src.crawler — 331 LOC
[ ] src/acne_llm/crawler/quality_filter.py — module: src.crawler — 325 LOC
[ ] src/acne_llm/crawler/sources/__init__.py — module: src.crawler — 0 LOC
[ ] src/acne_llm/crawler/sources/generic_html.py — module: src.crawler — 348 LOC
[ ] src/acne_llm/crawler/sources/pubmed.py — module: src.crawler — 94 LOC
[ ] src/acne_llm/crawler/stats.py — module: src.crawler — 176 LOC
[x] src/acne_llm/db/__init__.py — module: src.db — 5 LOC
[x] src/acne_llm/db/audit.py — module: src.db — 175 LOC
[x] src/acne_llm/db/base.py — module: src.db — 100 LOC
[x] src/acne_llm/db/session_store.py — module: src.db — 322 LOC
[ ] src/acne_llm/di.py — module: src.di — 344 LOC
[x] src/acne_llm/guardrails/__init__.py — module: src.guardrails — 0 LOC
[x] src/acne_llm/guardrails/pii.py — module: src.guardrails — 46 LOC
[x] src/acne_llm/guardrails/runner.py — module: src.guardrails — 209 LOC
[x] src/acne_llm/llm/__init__.py — module: src.llm — 0 LOC
[x] src/acne_llm/llm/language.py — module: src.llm — 30 LOC
[x] src/acne_llm/llm/ollama_backend.py — module: src.llm — 251 LOC
[x] src/acne_llm/llm/prompt_builder.py — module: src.llm — 253 LOC
[x] src/acne_llm/rag/__init__.py — module: src.rag — 0 LOC
[x] src/acne_llm/rag/chunker.py — module: src.rag — 234 LOC
[x] src/acne_llm/rag/cleaning.py — module: src.rag — 102 LOC
[x] src/acne_llm/rag/embedder.py — module: src.rag — 70 LOC
[x] src/acne_llm/rag/reranker.py — module: src.rag — 160 LOC
[x] src/acne_llm/rag/retriever.py — module: src.rag — 326 LOC
[x] src/acne_llm/rag/sparse.py — module: src.rag — 117 LOC
[x] src/acne_llm/rag/vectorstore.py — module: src.rag — 150 LOC
[x] src/acne_llm/schemas/__init__.py — module: src.schemas — 21 LOC
[x] src/acne_llm/schemas/clinical.py — module: src.schemas — 75 LOC
[x] src/acne_llm/schemas/core.py — module: src.schemas — 156 LOC
[x] src/acne_llm/schemas/extraction.py — module: src.schemas — 150 LOC
[x] src/acne_llm/schemas/kb.py — module: src.schemas — 195 LOC
[x] src/acne_llm/utils/__init__.py — module: src.utils — 3 LOC
[x] src/acne_llm/utils/chunk_filter.py — module: src.utils — 182 LOC
[x] src/acne_llm/utils/fuzzy_match.py — module: src.utils — 90 LOC
[x] src/acne_llm/utils/hashing.py — module: src.utils — 9 LOC
[x] src/acne_llm/utils/logging.py — module: src.utils — 229 LOC
[x] src/acne_llm/utils/retrieval_query.py — module: src.utils — 126 LOC
[x] src/acne_llm/utils/text_cleaning.py — module: src.utils — 89 LOC
[x] src/acne_llm/utils/timer.py — module: src.utils — 12 LOC
[ ] tests/chat/test_guideline_slot.py — module: tests — 106 LOC
[ ] tests/chat/test_unified_intake.py — module: tests — 552 LOC
[ ] tests/conftest.py — module: tests — 6 LOC
[ ] tests/test_admin_auth.py — module: tests — 52 LOC
[ ] tests/test_api.py — module: tests — 67 LOC
[ ] tests/test_audit.py — module: tests — 54 LOC
[ ] tests/test_chat_normalizer.py — module: tests — 212 LOC
[ ] tests/test_chat_stream.py — module: tests — 633 LOC
[ ] tests/test_chunk_filter_relevance.py — module: tests — 69 LOC
[ ] tests/test_chunk_qa_clinical_factory.py — module: tests — 168 LOC
[ ] tests/test_chunker.py — module: tests — 28 LOC
[ ] tests/test_cleaning.py — module: tests — 26 LOC
[ ] tests/test_clinical_dataset_validator.py — module: tests — 94 LOC
[ ] tests/test_clinical_planner.py — module: tests — 15 LOC
[ ] tests/test_confidence_behavior.py — module: tests — 60 LOC
[ ] tests/test_dedup.py — module: tests — 17 LOC
[ ] tests/test_env_keys.py — module: tests — 65 LOC
[ ] tests/test_extraction_confidence.py — module: tests — 90 LOC
[ ] tests/test_extraction_fieldresult.py — module: tests — 95 LOC
[ ] tests/test_extraction_negation.py — module: tests — 67 LOC
[ ] tests/test_guardrails.py — module: tests — 105 LOC
[ ] tests/test_intake.py — module: tests — 609 LOC
[ ] tests/test_intent_routing.py — module: tests — 231 LOC
[ ] tests/test_llm_extractor.py — module: tests — 382 LOC
[ ] tests/test_llm_router.py — module: tests — 158 LOC
[ ] tests/test_medication_gates.py — module: tests — 95 LOC
[ ] tests/test_normalizer_regression.py — module: tests — 469 LOC
[ ] tests/test_ollama_backend.py — module: tests — 103 LOC
[ ] tests/test_prompt_builder.py — module: tests — 323 LOC
[ ] tests/test_prose_only_contract.py — module: tests — 25 LOC
[ ] tests/test_quality_filter.py — module: tests — 122 LOC
[ ] tests/test_refusal_fallback.py — module: tests — 60 LOC
[ ] tests/test_reranker.py — module: tests — 32 LOC
[ ] tests/test_retrieval_merge.py — module: tests — 34 LOC
[ ] tests/test_retrieval_query.py — module: tests — 33 LOC
[ ] tests/test_retriever.py — module: tests — 120 LOC
[ ] tests/test_safety_dose_rule.py — module: tests — 48 LOC
[ ] tests/test_schemas.py — module: tests — 73 LOC
[ ] tests/test_semantic_router.py — module: tests — 161 LOC
[ ] tests/test_session.py — module: tests — 372 LOC
[ ] tests/test_session_fold_branches.py — module: tests — 219 LOC
[ ] tests/test_session_package_integrity.py — module: tests — 74 LOC
[ ] tests/test_settings.py — module: tests — 53 LOC
[ ] tests/test_sparse_bm25.py — module: tests — 34 LOC
[ ] tests/test_sqlite_session_store.py — module: tests — 116 LOC
[ ] tests/test_stream_safety.py — module: tests — 85 LOC
