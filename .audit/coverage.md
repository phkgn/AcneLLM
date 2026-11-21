# Coverage ledger — `20260822T152307Z`

Snapshot HEAD: `585333cc68d6e29b666337bdf366c99e00abc9b7` on `codex/simplify-chat-pipeline`.
Mẫu số: toàn bộ Git-tracked + untracked không bị ignore, trừ `.audit/**` (audit tự sinh).
`[ ]` chưa audit semantic · `[x]` đủ FINDINGS 8 mục · `[skip]` bỏ qua có lý do.
Các dấu `[x]` của coverage cũ không tự carry-forward vì run cũ thiếu fingerprint.

## VỊ TRÍ ĐANG DỞ

Semantic audit và completion gate đã hoàn tất: 581 done, 202 skip, 0 open.

## FILE

[skip] .codex/config.toml — lý do: tracked path absent from working tree
[x] .dockerignore — module: root — 26 LOC — sha256:f9f31643bf8892660bdb0285e429ee18cb97ef1a7ad5468df9eda36b3328e522 — symbols:0
[x] .env.baseline — module: root — 32 LOC — sha256:99c2011bc47c2f991bd27ce959bbfcc261de9006ed552d0ff6d11c53560cd353 — symbols:0
[x] .env.docker.example — module: root — 28 LOC — sha256:8d0ef608ebd179e3484afa9cd67d4d96a18fae0f4ad8fcb9724fc98b6d88a5a7 — symbols:0
[x] .gitattributes — module: root — 8 LOC — sha256:b05698fea950a912e6a155124398c955ae7dacc92309242f3d2158b2dfd11461 — symbols:0
[x] .gitignore — module: root — 110 LOC — sha256:94fcadabecdf3f60d639ab47a9cacf78a7092c0eccab997c95f7c2b0f01d65bc — symbols:0
[skip] _to_delete/datasets_MANIFEST_cu.json — lý do: tracked path absent from working tree
[skip] _to_delete/generated_v3_2_MANIFEST.json — lý do: tracked path absent from working tree
[x] config/drugs_acne.yaml — module: config — 277 LOC — sha256:0f4edb05c42b4525ad0f1d1a13b54bb8568421db1a616a0d8bb9da76fc0671aa — symbols:0
[x] config/guardrails.yaml — module: config — 100 LOC — sha256:a26173a835932d1226b047c545220af849a5a1e381f21cfb02705243502c3a94 — symbols:0
[x] config/prompts/clarify_user.j2 — module: config — 11 LOC — sha256:af1c1488506ce1712bab6c358acc4390a49fa4716e5dd08bf01f5bb680cb0e6a — symbols:0
[x] config/prompts/clarify_user.legacy.j2 — module: config — 14 LOC — sha256:5ca5dff4845f44f583a6896ef47e95c13a8e2cc869727884005625bc955baefd — symbols:0
[x] config/prompts/knowledge_user.j2 — module: config — 12 LOC — sha256:fa2bd97cac9b2f68ff03e335441c50468ae568bdb320f90c5afe1c3e275dedca — symbols:0
[x] config/prompts/knowledge_user.legacy.j2 — module: config — 10 LOC — sha256:ff0d3303c0421be4c5793a06fbf10db5851fd4c8ebf4e6726488ca6b629be326 — symbols:0
[x] config/prompts/refuse_user.j2 — module: config — 21 LOC — sha256:6f93caaabd6794cfb02ed5edc0ba600b6530ebd3cea6fc800041577203b82839 — symbols:0
[x] config/prompts/reject_user.j2 — module: config — 22 LOC — sha256:851e973002eb37db9be36b1d59107417165fb6968f6107074453dae8f10ab615 — symbols:0
[x] config/prompts/stream_user.j2 — module: config — 22 LOC — sha256:0ee61e06461209cf3614e189aa1bed08fa7073a32566c1729180fb5319611d4c — symbols:0
[x] data/add_more_site.md — module: data — 202 LOC — sha256:a043be01d6a74e3b46d408163242801da45482509c79dde5ec5fc9620a1f4b5b — symbols:0
[skip] data/bm25_index.pkl — lý do: binary/asset (.pkl)
[skip] data/bm25_index.pkl.sha256 — lý do: data/runtime artifact (.sha256)
[skip] data/chroma_db/chroma.sqlite3 — lý do: binary/asset (.sqlite3)
[x] data/error_site.yaml — module: data — 544 LOC — sha256:bac1c7dd016d78112a1fcb66b8157d30d7f4f9944522e2ad648387e4d90302f0 — symbols:0
[x] data/extraction_errors_review.txt — module: data — 207 LOC — sha256:3215d4f6f82c332ff2512d3288e46e7e999565cec5d508e37347dd77e484fca6 — symbols:0
[skip] data/golden_extraction_gen.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] data/golden_extraction_gen_deepseek.jsonl — lý do: data/runtime artifact (.jsonl)
[x] data/intent_classify.build_metrics.json — module: data — 161 LOC — sha256:25c3d34240c42f257ae88490d821ab1da27771344c90418db33c86d2b0a33dc8 — symbols:0
[skip] data/intent_classify.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] data/intent_classify.test.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] data/intent_classify.train.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] data/sample_queries.jsonl — lý do: data/runtime artifact (.jsonl)
[x] data/seed_sources.yaml — module: data — 873 LOC — sha256:d1935bb728ae4265741baecb324b14b47fa2aa84b504e7352e56d5b8f994b4f2 — symbols:0
[skip] data/subject_oos_eval.jsonl — lý do: data/runtime artifact (.jsonl)
[x] docker-compose.gpu.yml — module: docker-compose — 9 LOC — sha256:226bc04b1d0ced216776c1ffa807936c59c5c88ed72a479e81ca266b49d30085 — symbols:0
[x] docker-compose.yml — module: docker-compose — 128 LOC — sha256:7472829b2da4e78081924222611f7298407f802379d89d16ecd74a801d606123 — symbols:0
[skip] docker/nginx/default.conf.template — lý do: non-source artifact (.template)
[x] docker/ollama-init.sh — module: docker — 41 LOC — sha256:ca24c89ea9cf3cc921e0e4a412128ced9dae1ebb66d3b221a5dbf014d6cb8441 — symbols:1
[x] Dockerfile — module: Dockerfile — 35 LOC — sha256:472ba350d15adc212e4e112b76cccc5ddf768be43d08a8ce463c961be0e322e8 — symbols:0
[x] docs/archive/baseline_audit_prompt.md — module: docs — 266 LOC — sha256:1715f8ce92b62028451662c3a2377c3059168d73b52a812cdd9f97c249349174 — symbols:0
[x] docs/archive/baseline_extraction_confidence_design.md — module: docs — 250 LOC — sha256:162114e90364f770f1d01d5de478af281029989efd1628592e2add8c8e323d91 — symbols:0
[x] docs/archive/codex_intent_from_fields_round2.md — module: docs — 142 LOC — sha256:acd475bd8b74a9db1e09bf464a7db307e6c3685ba14cf8fc3f34c2b29a413223 — symbols:0
[x] docs/archive/codex_llm_extractor_plan.md — module: docs — 353 LOC — sha256:bb6b0c2e46e9ba218cbe798407ba5a6227392fc456c60bd32b7b1bcf81afd562 — symbols:0
[x] docs/archive/codex_reorder_softreject_round4.md — module: docs — 112 LOC — sha256:17db793f18d2d8712e1c310ea4064098f29ad0d03819863e21fcaf0e320c92df — symbols:0
[x] docs/archive/codex_semantic_router_round3.md — module: docs — 129 LOC — sha256:15eae0289b6e0478803fe8bc23232e67bb3962e863a360a58b97d69b61422427 — symbols:0
[x] docs/archive/CODEX_TASK_eval.md — module: docs — 186 LOC — sha256:37b10d69db6981979460a97ffaffd44164e1adebaaa2b7ea33e4730f0fbcb047 — symbols:0
[x] docs/archive/CODEX_TASK_eval_multiturn.md — module: docs — 128 LOC — sha256:e1d7b920a58f401771602458abe7a1872ca07f07f916d36b3ae862f707bed544 — symbols:0
[x] docs/archive/CODEX_TASK_eval_refactor.md — module: docs — 276 LOC — sha256:f26b3b0b82609b78e848e78d7e647fd714cf230fb18ef2b03c39aeb7ecb90693 — symbols:0
[x] docs/archive/CONFIG_MAP.md — module: docs — 98 LOC — sha256:02b571a8da722a0f535eb63788b0e57e060a42bdb61f93c27cda944871e83a04 — symbols:0
[x] docs/archive/DASHBOARD_E2E_QA_PROMPT.md — module: docs — 80 LOC — sha256:382708b76eeae3661c1857c18da5339a77ccd914107f99018e8737b0f3697cef — symbols:0
[x] docs/archive/DASHBOARD_FIGURES_PROMPT.md — module: docs — 132 LOC — sha256:a32c01b9f093681a38b9601a846e9e93b56e7d08da7b80a25f0b2358b58e4ee7 — symbols:0
[x] docs/archive/DASHBOARD_SEMANTIC_PROBE_PROMPT.md — module: docs — 141 LOC — sha256:d951762924f1dc43417f5dc5781835357a783a29fb4e2bfe27776c07c946654a — symbols:0
[x] docs/archive/EVAL_DASHBOARD_PROMPT.md — module: docs — 142 LOC — sha256:1c8a504a880b78bc0c905872413a3fe0bba37927fa9a515c5b74cf0877a6b2db — symbols:0
[x] docs/archive/eval_refactor_plan.md — module: docs — 148 LOC — sha256:261c0ac9e98fa644262b9ca7ab3f82239823dba06a84e1f4e80dea129afb839b — symbols:0
[x] docs/archive/EVAL_VALIDATION_LOOP_PROMPT.md — module: docs — 161 LOC — sha256:31eb94a18578f2021ce4bc9f1814a2005b0f791811581fea5bc04f77c85aaa7e — symbols:0
[x] docs/archive/EVALUATION_REFACTOR_PLAN.md — module: docs — 161 LOC — sha256:21ba50e81d2d7177044e23eb0603ea423ac368ee1f9549da83a45e1e0df8705b — symbols:0
[x] docs/archive/extraction_fix_handoff.md — module: docs — 196 LOC — sha256:e1292d5ae6aa000dd2455d5175c97a1d83b0fc04f9054b829911f374c9a973f6 — symbols:0
[x] docs/archive/intent_label_de_xuat.md — module: docs — 108 LOC — sha256:19dadb2f9073eb3007160d8602f80f65cb87434364eef65b3ad6c793413a9181 — symbols:0
[x] docs/archive/prompt_refactor_todo.md — module: docs — 136 LOC — sha256:1a0b0d489b0700ecdc8022bd6d9f79191af51272926e0dfcbbd208c0b327c060 — symbols:0
[x] docs/archive/README.md — module: docs — 9 LOC — sha256:e4208aaa2070335830e7c72d2e9b143c9618d5993361c460235cc4cbcf91eb26 — symbols:0
[x] docs/archive/UNIFIED_INTAKE_INTEGRATION_PLAN.md — module: docs — 150 LOC — sha256:b06bb85bccd3b81bbeaae9ab0f79b4d4d85106fc213a2613464cbbb3d66720b5 — symbols:0
[x] docs/CLEANUP_PLAN.md — module: docs — 286 LOC — sha256:78c2f3e8ecbb4458578b27b5c43a6190f368e34528398678caeca1f2f6e7413f — symbols:0
[x] docs/CLEANUP_TASKS.md — module: docs — 363 LOC — sha256:6323a1212b2e9cd34807d219709fd6c0651a4f5d296aaf02442d119df87dc763 — symbols:0
[x] docs/config_layout.md — module: docs — 131 LOC — sha256:22d88cfeb74bb0eefb56c7bb3546ecbd7913c62fa2c2f8f78888b1c75ad117de — symbols:0
[x] docs/config_reference.md — module: docs — 134 LOC — sha256:d00684ba143da2dd40651047dc71080bbf646e7066c8a17689341f8db42e552a — symbols:0
[x] docs/dashboard_phan_tich_workflow.md — module: docs — 251 LOC — sha256:b57c4c189ce0e7a661c1b7d20084d7aa849829f6e4438badbdb5347fee30e334 — symbols:0
[x] docs/DATA_GEN_GIAI_THICH.md — module: docs — 212 LOC — sha256:f7a81305f9547457d3c34b1d014f8c69002c3dbb8e7ab9769aaa9df58b2d8272 — symbols:0
[x] docs/DEAD_CODE.md — module: docs — 252 LOC — sha256:f434cfe2fdc84d0492a5ebf1d1773d0bbe42c5e79b23ac2af63bb14cb97ac955 — symbols:0
[x] docs/DOCKER_QUICKSTART.md — module: docs — 248 LOC — sha256:1a12486139ae37f0d3fb6ae00a680285b91b371fa80e932cf60f54c7d5f6ba6e — symbols:0
[x] docs/EVAL_BLUEPRINT.md — module: docs — 497 LOC — sha256:b2ddb7bf9d005b386ec04b7bbc2d57dbcb4620d821664b481a0c6a5282cd4097 — symbols:0
[x] docs/EVAL_DIAGRAM_SPEC.md — module: docs — 343 LOC — sha256:c669484ed42ee91daddb56aa664e160126735717d97f6d70bf55c29f052e9ca4 — symbols:0
[x] docs/eval_pipeline.html — module: docs — 366 LOC — sha256:9a504ab33d6186c0218497f6d013a00f99178f85377d0821529a9f8bffbceabd — symbols:0
[x] docs/evaluation_refactor_evidence.md — module: docs — 314 LOC — sha256:e23b4c13b108f60f6017ed0bddec90cc11007aa7818e30e0e5601dca92e0788f — symbols:0
[x] docs/history/codex_bottleneck_fix_prompt.md — module: docs — 251 LOC — sha256:78af84eca5a04303532e108561179cb19498565c35a7723239399b75ed3f7ce1 — symbols:0
[x] docs/history/codex_config_cleanup_prompt.md — module: docs — 342 LOC — sha256:e509fafffd40f2c763ed094e82dbc8133fd59a72b5fbfec8585c01a6b4faaec6 — symbols:0
[x] docs/history/codex_datagen_onecmd_prompt.md — module: docs — 121 LOC — sha256:b1858a0b6b5983514014a00c275848d0b2723164a041f10f9f29c4437023a914 — symbols:0
[x] docs/history/codex_datagen_role_prompt.md — module: docs — 170 LOC — sha256:2e4d04a79953d46a74e5f68d2b5e178e22ae788bcb608015b3e8d2764cd087d2 — symbols:0
[x] docs/history/codex_debug_eval_prompt.md — module: docs — 95 LOC — sha256:5584a6c3a8badf9a21d492fffbd55acf4c1e463178d5a6b7a962765046c8b61e — symbols:0
[x] docs/history/codex_eval_module_refactor_prompt.md — module: docs — 500 LOC — sha256:8b53f15c689b93fbf46527ffbe81c50a673bc5d3051d09e6b19123d40f774fdf — symbols:0
[x] docs/history/codex_eval_rename_prompt.md — module: docs — 124 LOC — sha256:1d1df5285766e85f8a20e6bcba1c61313340db421b0e79c7ae8c7a537322c389 — symbols:0
[x] docs/history/codex_eval_simplify_followup_prompt.md — module: docs — 98 LOC — sha256:c98d30a664658ad1f1066a2cc6750f862c43c07a426357cc410fe80a383f236b — symbols:0
[x] docs/history/codex_eval_simplify_prompt.md — module: docs — 101 LOC — sha256:dfa47f9f1eec657e3f5275dd8e03a203e2e652fa218cc434cd347bc6ba4f209d — symbols:0
[x] docs/history/codex_evaluation_refactor_prompt.md — module: docs — 116 LOC — sha256:0526f4c1c6918a090ae4506c0fca2ffd08f131ff2ad56882c0e6fbfb52b93f46 — symbols:0
[x] docs/history/codex_extract_before_route_prompt.md — module: docs — 153 LOC — sha256:e2f53451cb701ace4852b6c8ee0ca076c5605ab30809cba923bc7e05f450a704 — symbols:0
[x] docs/history/codex_fix_citations_contract_prompt.md — module: docs — 103 LOC — sha256:9327218ff1a75f19b4e95c991b4b8b8c5e0a0b174242e9afb687add8e97a72b4 — symbols:0
[x] docs/history/codex_grounding_eval_prompt.md — module: docs — 147 LOC — sha256:a65f8862e01f0bf4b8a89ad8ead964f5ddd69bdc0b211d2893e93011dd5d2c61 — symbols:0
[x] docs/history/codex_intakedata_build_prompt.md — module: docs — 100 LOC — sha256:c90ed709c4d7a43f8f37106becc76e1f89e18c8256733721187aa593d4f0e60c — symbols:0
[x] docs/history/codex_llm_router_prompt.md — module: docs — 132 LOC — sha256:fad2f43d144eb69d4324aa008bd66d60e2daf553a2d1030e1be9af5f0d4dac62 — symbols:0
[x] docs/history/codex_posthoc_citation_prompt.md — module: docs — 168 LOC — sha256:231884a6947045ab59f4ce85ecb03f7fa2944f4cd905f60fefcafd1c79509dee — symbols:0
[x] docs/history/codex_roledata_build_prompt.md — module: docs — 103 LOC — sha256:27e2c394bed8ca094a0ebb5677d2dd84a83340ed60f6995f6aa13fa1c96eec72 — symbols:0
[x] docs/history/codex_round3_prompt.md — module: docs — 122 LOC — sha256:53f72a9c58786c103f13585625ca6f9078939db245c0eea57cf8f1cce60b2e8d — symbols:0
[x] docs/history/codex_runall_monitor_ui_prompt.md — module: docs — 102 LOC — sha256:8b89cebb59ea99e8b0adfeae8879a5f7da37821a51026f786531938944240d22 — symbols:0
[x] docs/history/codex_runtime_cleanup_prompt.md — module: docs — 115 LOC — sha256:d788d9f583dd42518cc432762d8646ceb311303b04d0175bd639644670a21eac — symbols:0
[x] docs/history/codex_unified_intake_integration_prompt.md — module: docs — 114 LOC — sha256:f60ff90b0ba1b103a891ac01645f13575ae77a37e54991a1cd77f1186a974c00 — symbols:0
[x] docs/README.md — module: docs — 40 LOC — sha256:2180b9b2ca285a7ecd92ec3616b32a515fe999651c7354514e28cdb833dbc4c4 — symbols:0
[skip] docs/reports/AcneLLM_config_audit.xlsx — lý do: binary/asset (.xlsx)
[skip] docs/reports/artifacts/acnellm_v2_proof.zip — lý do: binary/asset (.zip)
[x] docs/reports/context.md — module: docs — 657 LOC — sha256:c5aa4d4cbd8ac07b5eecce55a6e7fa87c498280253c8400fbbec3eb2a3c26f1a — symbols:0
[x] docs/reports/DANH_GIA_KHOA_LUAN.md — module: docs — 175 LOC — sha256:8304c4e0b9a5f805ef6340459c5991dd36dd13b57bf6e48fd6ee5396aedf584d — symbols:0
[x] docs/reports/FINALIZE.md — module: docs — 246 LOC — sha256:f8d4cbe320d255a0e812b2b503068b997792deded53fc618700eb9423c1d0de7 — symbols:0
[x] docs/reports/report.md — module: docs — 1038 LOC — sha256:67b9539362d146c7bf59a7fbdaf8ec55464f9270b573d575aaea906541e76342 — symbols:0
[x] docs/reports/runtime_audit.md — module: docs — 358 LOC — sha256:74913f78a11fc0f065195a148aa5af0e75fcb2d3ee4aab73e50d0ada282a1157 — symbols:0
[x] docs/reports/schema_intent_execution_plan.md — module: docs — 191 LOC — sha256:f08b6d6a60cf7b53032b92dbf4dd179c84a138eefa030eaaca1045fa7f2905a6 — symbols:0
[x] docs/reports/schema_unification_plan.md — module: docs — 191 LOC — sha256:95f2ed446d4e4b95786c7fe8ec2cc604739ad429ed7abd4e5f6e005148083b82 — symbols:0
[x] docs/reports/smoke_review.md — module: docs — 296 LOC — sha256:6bef1eef0b757cdc1f865dc1b5b29a27bafb9a45bb446b6d7290bb03d6355ed1 — symbols:0
[x] docs/reports/TASKS.md — module: docs — 143 LOC — sha256:420d97d31fe5ce6cb0d13f681e2823ef9dc98ba90566323e3fb0645ed80df830 — symbols:0
[x] docs/review_input_to_rag_to_prompt.md — module: docs — 247 LOC — sha256:4a1e15b74f29fd45d2fdada5ab269cd0c3d62bf057ec33520ec6aecd8a8896c4 — symbols:0
[x] docs/rulebase_audit.md — module: docs — 186 LOC — sha256:9758bb0b68b048fa3d64d82a0f6a45292b3a9fd8e09f493a2c957d62e1b4ef4c — symbols:0
[x] docs/schema_mapping.md — module: docs — 157 LOC — sha256:65776dbdc46323c2c7764fed596bde44dc62fbe9af3149fddd019f6c547bdd12 — symbols:0
[x] evaluation/judges/prompts/pointwise.md — module: evaluation — 37 LOC — sha256:780e9b28ef9b1c2ac8e37411b4c91717f8f69d834c0033599e35f6e0f176cb50 — symbols:0
[x] frontend/.dockerignore — module: frontend — 6 LOC — sha256:01547ed233aa085e4cabf29f40b665cc88653c319637aa80c39a205856b9d2ff — symbols:0
[x] frontend/.eslintrc.json — module: frontend — 4 LOC — sha256:d1847183d449a873db4388d28ec2bb0867bdefab98b86945ae15c0dba397a04e — symbols:0
[x] frontend/Dockerfile — module: frontend — 35 LOC — sha256:5d5813fe662ff78c78fc2a7d255c94fec2d85283ef0424b2b728a8a68567a29f — symbols:0
[x] frontend/next-env.d.ts — module: frontend — 6 LOC — sha256:85ae5aee75f011967cf2d25cbc342f62d69314e9d925f7f4aa3456fc2cffcca6 — symbols:0
[x] frontend/next.config.js — module: frontend — 7 LOC — sha256:8e287aa19f681e08954bbac2ba74f4275308b412024ec3fdca77fcc13c3754a9 — symbols:1
[skip] frontend/package-lock.json — lý do: generated dependency/build lock artifact
[x] frontend/package.json — module: frontend — 29 LOC — sha256:79af81078db9991a7e5db63511fc2ee782d2a987122641a20b7b2d6f9d8dc27f — symbols:0
[x] frontend/postcss.config.js — module: frontend — 6 LOC — sha256:fa650b380adfabb151a0b352f7135e107e6352345f899060f1c5c231228f94bf — symbols:0
[x] frontend/src/app/globals.css — module: frontend — 38 LOC — sha256:28b14acf7049d234ba4690d8234605225f4972bc6539b83e0e7fdfef163de4f4 — symbols:0
[x] frontend/src/app/layout.tsx — module: frontend — 20 LOC — sha256:11c3037a1b9cd49d6fc4e56cc9c34252e59b5a77bc19afd8e3a79814a8dfdb5e — symbols:1
[x] frontend/src/app/page.tsx — module: frontend — 5 LOC — sha256:a830be229b4a8c872ae316b97df83208b7bf0e33359fc7f77492447a08887aec — symbols:1
[x] frontend/src/components/chat/ChatWindow.tsx — module: frontend — 283 LOC — sha256:064065a033d53ab4094234256dbeb9058e32a9bf8a35b0e74fe409f9d9bf3451 — symbols:16
[x] frontend/src/components/chat/ChunkDetailModal.tsx — module: frontend — 134 LOC — sha256:7a482ef9a6627ac76d764c5acf6d4744443603d6eb04b6320497d57b1399039b — symbols:6
[x] frontend/src/components/chat/MessageBubble.tsx — module: frontend — 187 LOC — sha256:0969cd28bbaafbed98959b4ba0d27908f473b6409f4c25ebbf5e32837aafe31f — symbols:12
[x] frontend/src/components/chat/MessageInput.tsx — module: frontend — 120 LOC — sha256:1b484989f67dddeb252b27aea0f4cfcac2b8d17be22fa0dc7875e21659b78141 — symbols:16
[x] frontend/src/components/chat/SourceCard.tsx — module: frontend — 152 LOC — sha256:273aede2e56170be03736b4f2dd90d351ba32ff04fc4266710db10fed28e39b9 — symbols:12
[x] frontend/src/config/chatConfig.ts — module: frontend — 37 LOC — sha256:456c450e3dc1de64074ffe5aa965f42e31888d34ddefd3edb1df82f8a66b178c — symbols:4
[x] frontend/src/hooks/useSSE.ts — module: frontend — 87 LOC — sha256:34ee7bfb81d12b3f3f744aaddd57ac58b98715fac3458ffad609330fdb3667e9 — symbols:22
[x] frontend/src/lib/api.ts — module: frontend — 45 LOC — sha256:9b29b4709cd408361fbb2764a15ba855de978fc63b1d59c9b450a24101432bc4 — symbols:7
[x] frontend/src/lib/types.ts — module: frontend — 51 LOC — sha256:be151384918bf112fb48d880c59674535ea972fee7c72cd05dd1c30a3ca21595 — symbols:0
[x] frontend/src/stores/chatStore.ts — module: frontend — 128 LOC — sha256:7ca9470f9e8a33290432253b11fdc057a5cdc764cac7128d0ce5865154349b22 — symbols:12
[x] frontend/tailwind.config.js — module: frontend — 21 LOC — sha256:3cc46849046a14e78a08fc2f383f5833bdb57b9667a5e04777924f2c380513c3 — symbols:0
[x] frontend/tsconfig.json — module: frontend — 28 LOC — sha256:5ca16fde6749151382bd00942de170be15443c8099903b2a8265c879a59e8972 — symbols:0
[skip] frontend/tsconfig.tsbuildinfo — lý do: generated dependency/build lock artifact
[x] guideline_docs/download_acne_pdfs.py — module: guideline_docs — 113 LOC — sha256:169d977eb79b872b04a473b551076184d3d7da080d3a878d781c94dfade6d74d — symbols:11
[x] pyproject.toml — module: pyproject — 30 LOC — sha256:344ace1496e0d3b892407c4bb5e257f213a706d49a16080f9c1a59a21a4b04b5 — symbols:0
[x] README.md — module: README — 314 LOC — sha256:a7944d3b827c4310794f147308b99f5cc60f7496732582990acf329d8bd2d95a — symbols:0
[x] requirements-dev.txt — module: requirements-dev — 35 LOC — sha256:35614de12a39c4e5d5fc399ec12c61d9bee096d158af56dc9f64932c361f2302 — symbols:0
[x] requirements.txt — module: requirements — 55 LOC — sha256:13a9cff478dd17b9bb711a747a68e0ee9775bf85ce534f77eba0df466f721240 — symbols:0
[skip] research/dashboards/_overview/01_artifact_scale.png — lý do: binary/asset (.png)
[skip] research/dashboards/architecture/01_system_context.png — lý do: binary/asset (.png)
[skip] research/dashboards/architecture/02_chat_sse_workflow.png — lý do: binary/asset (.png)
[skip] research/dashboards/architecture/03_intake_safety_routing.png — lý do: binary/asset (.png)
[skip] research/dashboards/architecture/04_rag_kb_lifecycle.png — lý do: binary/asset (.png)
[skip] research/dashboards/architecture/05_finetune_data_factory.png — lý do: binary/asset (.png)
[skip] research/dashboards/architecture/06_evaluation_ablation.png — lý do: binary/asset (.png)
[skip] research/dashboards/architecture/07_docker_deployment.png — lý do: binary/asset (.png)
[skip] research/dashboards/architecture/AcneLLM_Architecture.drawio — lý do: binary/asset (.drawio)
[x] research/dashboards/architecture/build_drawio.py — module: research — 593 LOC — sha256:53db3f1306eca7408fed693d645997f7b6ffce1a522e12da99ef57ef1b782ae6 — symbols:19
[x] research/dashboards/architecture/README.md — module: research — 31 LOC — sha256:bc802c46c5c29947f4230a2dad08710b63548798b9fbe74609fe1dbb09e075c2 — symbols:0
[skip] research/dashboards/architecture/staruml_desktop.png — lý do: binary/asset (.png)
[x] research/dashboards/build/index.html — module: research — 266 LOC — sha256:9bf0fe0cbcd9f4b1430127fc532eb9cba7bcd31b301e94d82e2918f34b7282ad — symbols:0
[x] research/dashboards/build/README.md — module: research — 13 LOC — sha256:5bf0e2e1be81d0aad8c8d501220b8a3053d0c48ffed835b2e501e10fd34a27aa — symbols:0
[x] research/dashboards/build/source_snapshot.json — module: research — 74 LOC — sha256:000635ff77dd92aeb2b428af086863fdfac1ab74f6bed7075a004132ba484396 — symbols:0
[skip] research/dashboards/evaluation/01_dataset_task_types.png — lý do: binary/asset (.png)
[skip] research/dashboards/evaluation/02_dataset_intents.png — lý do: binary/asset (.png)
[skip] research/dashboards/evaluation/03_expected_kb_sources.png — lý do: binary/asset (.png)
[skip] research/dashboards/evaluation/04_relevant_chunks_per_question.png — lý do: binary/asset (.png)
[skip] research/dashboards/evaluation/05_run_timeline.png — lý do: binary/asset (.png)
[skip] research/dashboards/evaluation/06_intake_headline_metrics.png — lý do: binary/asset (.png)
[skip] research/dashboards/evaluation/07_intake_confusion_matrix.png — lý do: binary/asset (.png)
[skip] research/dashboards/evaluation/08_intake_per_intent_prf.png — lý do: binary/asset (.png)
[skip] research/dashboards/evaluation/09_intake_extraction_field_f1.png — lý do: binary/asset (.png)
[skip] research/dashboards/evaluation/10_intake_scalar_list_quality.png — lý do: binary/asset (.png)
[skip] research/dashboards/evaluation/11_intake_latency.png — lý do: binary/asset (.png)
[skip] research/dashboards/evaluation/12_retrieval_headline_metrics.png — lý do: binary/asset (.png)
[skip] research/dashboards/evaluation/13_retrieval_source_types.png — lý do: binary/asset (.png)
[skip] research/dashboards/evaluation/14_retrieval_sources.png — lý do: binary/asset (.png)
[skip] research/dashboards/evaluation/15_retrieved_chunk_count.png — lý do: binary/asset (.png)
[skip] research/dashboards/evaluation/16_retrieval_score_distributions.png — lý do: binary/asset (.png)
[skip] research/dashboards/evaluation/17_ablation_arm_design.png — lý do: binary/asset (.png)
[skip] research/dashboards/evaluation/17_ablation_execution.png — lý do: binary/asset (.png)
[skip] research/dashboards/evaluation/18_ablation_answer_tone.png — lý do: binary/asset (.png)
[skip] research/dashboards/evaluation/19_ablation_content_errors.png — lý do: binary/asset (.png)
[skip] research/dashboards/evaluation/20_ablation_rag_faces.png — lý do: binary/asset (.png)
[skip] research/dashboards/evaluation/21_ablation_precision_ranking.png — lý do: binary/asset (.png)
[skip] research/dashboards/evaluation/22_ablation_paired_delta_forest.png — lý do: binary/asset (.png)
[skip] research/dashboards/evaluation/23_ablation_cost_quality.png — lý do: binary/asset (.png)
[skip] research/dashboards/evaluation/24_ablation_answer_quality_boxplot.png — lý do: binary/asset (.png)
[skip] research/dashboards/evaluation/25_ablation_latency_boxplot.png — lý do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/01_split_distribution.png — lý do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/02_generation_completion.png — lý do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/03_sample_kind_distribution.png — lý do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/04_sample_family_distribution.png — lý do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/05_input_style_distribution.png — lý do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/06_context_coverage.png — lý do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/07_context_source_count.png — lý do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/08_context_source_names.png — lý do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/09_user_length_histogram.png — lý do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/10_answer_length_histogram.png — lý do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/11_message_count_distribution.png — lý do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/12_audience_distribution.png — lý do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/13_generation_model_distribution.png — lý do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/14_gate_result_distribution.png — lý do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/15_sample_kind_by_split.png — lý do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/16_input_style_by_sample_kind.png — lý do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/17_rejection_reasons.png — lý do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/18_rejection_cases.png — lý do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/19_rejection_attempt_number.png — lý do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/20_retry_outcomes.png — lý do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/21_anchor_group_pair_sizes.png — lý do: binary/asset (.png)
[skip] research/dashboards/finetune_generator/22_integrity_checks.png — lý do: binary/asset (.png)
[skip] research/dashboards/finetune_intaker/01_train_val_split.png — lý do: binary/asset (.png)
[skip] research/dashboards/finetune_intaker/02_intent_distribution.png — lý do: binary/asset (.png)
[skip] research/dashboards/finetune_intaker/03_case_type_distribution.png — lý do: binary/asset (.png)
[skip] research/dashboards/finetune_intaker/04_case_intent_matrix.png — lý do: binary/asset (.png)
[skip] research/dashboards/finetune_intaker/05_user_length_histogram.png — lý do: binary/asset (.png)
[skip] research/dashboards/finetune_intaker/06_confidence_histogram.png — lý do: binary/asset (.png)
[skip] research/dashboards/finetune_intaker/07_extracted_field_presence.png — lý do: binary/asset (.png)
[skip] research/dashboards/finetune_intaker/08_generation_sources.png — lý do: binary/asset (.png)
[skip] research/dashboards/finetune_intaker/09_rejected_attempt_reasons.png — lý do: binary/asset (.png)
[skip] research/dashboards/finetune_intaker/10_target_vs_actual.png — lý do: binary/asset (.png)
[x] research/dashboards/generate_all.py — module: research — 1341 LOC — sha256:a45a4d5d327947d08961ca2be0e89d658fbd5a44e168b2ec6b33efcd9bcd9eb7 — symbols:42
[x] research/dashboards/index.html — module: research — 6 LOC — sha256:8821a43ca9ddac022f6d0a2e4bdb0b3e55cf89453d76a4adf7e105051f696449 — symbols:0
[skip] research/dashboards/KB/01_chunk_sources_pie.png — lý do: binary/asset (.png)
[skip] research/dashboards/KB/02_top_chunk_sources.png — lý do: binary/asset (.png)
[skip] research/dashboards/KB/03_source_type_distribution.png — lý do: binary/asset (.png)
[skip] research/dashboards/KB/04_trust_level_distribution.png — lý do: binary/asset (.png)
[skip] research/dashboards/KB/05_language_distribution.png — lý do: binary/asset (.png)
[skip] research/dashboards/KB/06_category_distribution.png — lý do: binary/asset (.png)
[skip] research/dashboards/KB/07_chunk_length_histogram.png — lý do: binary/asset (.png)
[skip] research/dashboards/KB/08_chunks_per_document_histogram.png — lý do: binary/asset (.png)
[skip] research/dashboards/KB/09_chunk_length_by_source.png — lý do: binary/asset (.png)
[skip] research/dashboards/KB/10_document_chunk_coverage.png — lý do: binary/asset (.png)
[skip] research/dashboards/KB/11_chunk_position_histogram.png — lý do: binary/asset (.png)
[x] research/dashboards/manifest.json — module: research — 1911 LOC — sha256:62099ab470503f986a5ef6f0a86d3359e5252c89ac3b7bdda931de4389c53b47 — symbols:0
[x] research/dashboards/README.md — module: research — 33 LOC — sha256:3d6fd15a6e612c19e855897dd28597d28bfb6a7396774ad9ae9626d9e744d4ed — symbols:0
[skip] research/dashboards/repository/01_backend_files_by_package.png — lý do: binary/asset (.png)
[skip] research/dashboards/repository/02_backend_loc_by_package.png — lý do: binary/asset (.png)
[skip] research/dashboards/repository/03_file_types.png — lý do: binary/asset (.png)
[skip] research/dashboards/repository/04_files_by_top_directory.png — lý do: binary/asset (.png)
[skip] research/dashboards/repository/05_source_artifact_size.png — lý do: binary/asset (.png)
[skip] research/dashboards/repository/06_model_artifact_sizes.png — lý do: binary/asset (.png)
[skip] research/dashboards/repository/07_tests_by_domain.png — lý do: binary/asset (.png)
[x] research/datagen/__init__.py — module: datagen.__init__ — 2 LOC — sha256:7fe50d9b386596344b3eb7ecadc437eb4823da5c9d255b19332d425d74f8d347 — symbols:0
[x] research/datagen/config.py — module: datagen.config — 176 LOC — sha256:d1520a01e5dc1c36ab93bd8df0c883fb6f275ac92a7f7af54be61dcc45b8ea63 — symbols:11
[x] research/datagen/contamination.py — module: datagen.contamination — 125 LOC — sha256:9edb004b9396904ea032ffebd70b19e5a7c15cb27d5448c055cd610b6fdeb897 — symbols:11
[x] research/datagen/FINETUNE_DATAGEN_PLAN.md — module: datagen.FINETUNE_DATAGEN_PLAN — 178 LOC — sha256:d6ddaa1c28ef63cff8165cc311db6378b456b5746b194fd18fe0c869ef7c3464 — symbols:0
[x] research/datagen/gates.py — module: datagen.gates — 1003 LOC — sha256:d2aedf9bdeb37a0fd988730730c0cb8b20437023ffc4c470a7c4d4532f859a4f — symbols:54
[x] research/datagen/gen_role_dataset.py — module: datagen.gen_role_dataset — 22 LOC — sha256:8ff757d852af2fcae78275a587d99100768ff7cb4f0da2750c24382680e411ef — symbols:0
[x] research/datagen/generator.py — module: datagen.generator — 476 LOC — sha256:23b8fab4571bda627d8ca354f311abf59d6b42b66f6913bfe28a979747d3475a — symbols:31
[x] research/datagen/HANDOFF.md — module: datagen.HANDOFF — 66 LOC — sha256:a4f9c690aee3d0198d9dcee26a20a25bcac42f0d55642c7172753fd755a5d970 — symbols:0
[x] research/datagen/intake_json_system_prompt.md — module: datagen.intake_json_system_prompt — 125 LOC — sha256:ffcaf1e4ef334bcee3acf2eb4f021195b4989f8f5244b385b7b816c47ba74265 — symbols:0
[x] research/datagen/intakedata/__init__.py — module: datagen.intakedata — 17 LOC — sha256:197cb86caa0c923f3e7a0b2f45ac3621ff1b5d1e170c895803a19f2dfc536a3a — symbols:1
[x] research/datagen/intakedata/anchor.py — module: datagen.intakedata — 45 LOC — sha256:eecad61a17bde0f172f6583147e93ff4707795ab59e41bb4ee1b6f9bbf37b56f — symbols:3
[x] research/datagen/intakedata/config.py — module: datagen.intakedata — 239 LOC — sha256:4f3a4c93883b86bd824a72de00e89807bdd63dd227462f4c37dd46654c8b42a1 — symbols:19
[x] research/datagen/intakedata/conftest.py — module: datagen.intakedata — 90 LOC — sha256:011c43cc3acca6f2fd3dea181c586f2397a585e6846a1c93a2dbaf7dc4d77013 — symbols:5
[x] research/datagen/intakedata/DATA_PROVENANCE_REPORT.md — module: datagen.intakedata — 56 LOC — sha256:c35669f088a792be3e51da1aebd144dfebb2727701b832f021c70a29ed2bffb0 — symbols:0
[x] research/datagen/intakedata/gates.py — module: datagen.intakedata — 776 LOC — sha256:bbaa43c93d437b7fd3df8fe827679112eb9c7aca3f79cec3d87941e935e38b06 — symbols:30
[x] research/datagen/intakedata/generator.py — module: datagen.intakedata — 816 LOC — sha256:d1310c70283ae7cb5f5c1eaad5ef98f5327e4fd56fbdc4793f31bcb018bb3458 — symbols:39
[x] research/datagen/intakedata/output/.gitignore — module: datagen.intakedata — 2 LOC — sha256:240a3e0d37d2e86b614063f5347eb02d4f99ca6c254de6b82871ff8d95532a7d — symbols:0
[x] research/datagen/intakedata/pipeline.py — module: datagen.intakedata — 718 LOC — sha256:56c6f6286cccea89d9726875134310015b8c081bbed7c6a26016f6a18b470c57 — symbols:21
[x] research/datagen/intakedata/PLAN.md — module: datagen.intakedata — 223 LOC — sha256:eb9bc99f485bfd7292dd6e20b2a1ff20469cddbbf7984a98c9d95a9355ccd7fe — symbols:0
[x] research/datagen/intakedata/README.md — module: datagen.intakedata — 67 LOC — sha256:fdc5e3f6a403fd5c24baa20beb1d4db834438a79476d184c66868662a5b02eed — symbols:0
[x] research/datagen/intakedata/schema.py — module: datagen.intakedata — 301 LOC — sha256:f3dd7b1518ef85380488f541719338d779a87d6465903833ffdf99e82cf8a211 — symbols:20
[x] research/datagen/intakedata/seed.py — module: datagen.intakedata — 295 LOC — sha256:ed2aa891654ced6557d71d2fe3f61b039637abd71014b64e1f6e369f38f6aeb9 — symbols:13
[x] research/datagen/intakedata/system_prompt.canonical.txt — module: datagen.intakedata — 25 LOC — sha256:0af17a45ef3cd245af08b8f6e5a73368affc2f6b9e09c315e4c78b32b8215535 — symbols:0
[x] research/datagen/intakedata/taxonomy.yaml — module: datagen.intakedata — 18 LOC — sha256:1c84ffb133c9d55648a3708575699cc4f7db2bc5e5fc506d7b0857998456ae16 — symbols:0
[x] research/datagen/intakedata/tests/__init__.py — module: datagen.intakedata — 1 LOC — sha256:82a8a39ec06b1fa273a2ebdf69037d6381b0ec8010acc72f5bc813138d659125 — symbols:0
[x] research/datagen/intakedata/tests/test_anchor.py — module: datagen.intakedata — 30 LOC — sha256:614d269e83c4a835601279c8b7027c4ff9d2e2dd0abe18cc5524fddd28f589f8 — symbols:3
[x] research/datagen/intakedata/tests/test_budget.py — module: datagen.intakedata — 25 LOC — sha256:cc6dde2a7402ed7cbcff6eb771c173a2d1d1ef976d8b404a2557c449c950b46b — symbols:3
[x] research/datagen/intakedata/tests/test_gates.py — module: datagen.intakedata — 153 LOC — sha256:b89792ee5e2c70d2a74479c7dd9005e69814cfc026f2d1b614d4ee3155963927 — symbols:7
[x] research/datagen/intakedata/tests/test_pipeline_contracts.py — module: datagen.intakedata — 306 LOC — sha256:7ef0f24f40f8ed2ba31453917908a0ebeefa758606e621a59ecba3c92b60abc7 — symbols:10
[x] research/datagen/intakedata/tests/test_schema.py — module: datagen.intakedata — 56 LOC — sha256:21705e2782475789d2c11260e887c96700c38f9872eb02d68ee220df37f92047 — symbols:4
[x] research/datagen/intakedata/tests/test_seed.py — module: datagen.intakedata — 61 LOC — sha256:d1f4c64d1eba520f497d036cf0b82ca3fc175cb2047958806623b45eb22a6c2a — symbols:4
[x] research/datagen/intakedata/writer.py — module: datagen.intakedata — 103 LOC — sha256:8751cabd771615fae1066820dc899535037242f7d36665c9c5f130d7ba085c99 — symbols:10
[x] research/datagen/main.py — module: datagen.main — 1261 LOC — sha256:a4bc5faceef35dab3a2ffbde3d8b6cc3e7329d895fa4f34246d7b45f9bdf8917 — symbols:39
[skip] research/datagen/output/v4_role/.false_gate_recovery_v2.done — lý do: data/runtime artifact (.done)
[skip] research/datagen/output/v4_role/.generator.lock — lý do: generated dependency/build lock artifact
[x] research/datagen/output/v4_role/generation_summary.json — module: datagen.output — 254 LOC — sha256:beb170cdce705c913878817775db06ab021a9c4a05f505695d70f7451579bbb1 — symbols:0
[x] research/datagen/output/v4_role/limit_checkpoint.json — module: datagen.output — 10 LOC — sha256:a4486a12e9848855b473eebf0d1e75e1f32811f45c374aa98e796c4f3e026b53 — symbols:0
[skip] research/datagen/output/v4_role/rejected.audit.jsonl — lý do: data/runtime artifact (.jsonl)
[x] research/datagen/output/v4_role/SMOKE_REVIEW.md — module: datagen.output — 1535 LOC — sha256:b36249be23e28cc0810c2a6b7df91b386ac335fc84d41f7b04d24b313e8fcb3e — symbols:0
[x] research/datagen/output/v4_role/SMOKE_REVIEW_V2.md — module: datagen.output — 96 LOC — sha256:ba67d9e019571e8c9dbd52e38bb90d1e443c7b07554a25af63957d79fe778fea — symbols:0
[skip] research/datagen/output/v4_role/v4_role.smoke.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/datagen/output/v4_role/v4_role.train.jsonl — lý do: data/runtime artifact (.jsonl)
[x] research/datagen/output/v4_role/verification_summary.json — module: datagen.output — 48 LOC — sha256:3d5347d3a5feeb6cf263df32c768f6779f842875cd1d92da60c178825006cdd0 — symbols:0
[x] research/datagen/render_context.py — module: datagen.render_context — 68 LOC — sha256:a308383b64580d56ada9fc2ba6d602996743e46fc2a55ed09c5c77a1f169d93d — symbols:7
[x] research/datagen/report_stats.py — module: datagen.report_stats — 75 LOC — sha256:a7e305910b22a19f601128aef87e87501a2e22274997d41b0685341671e8bb91 — symbols:5
[x] research/datagen/role_style_guide.md — module: datagen.role_style_guide — 65 LOC — sha256:c50d89f3433de3fdd7bdcd122356c63c547d4820a5167781b1747ea0290fa33a — symbols:0
[x] research/datagen/role_taxonomy.yaml — module: datagen.role_taxonomy — 99 LOC — sha256:9f0add16c8a3c38b0b3464ba9ab280a88039a0c66420126a5ad33a36c8a761ad — symbols:0
[x] research/datagen/roledata/__init__.py — module: datagen.roledata — 5 LOC — sha256:b4f287b4fc073810d08b7a21cd7190dd2036b17d0b4817171d47f93685105b3d — symbols:1
[x] research/datagen/roledata/anchor.py — module: datagen.roledata — 32 LOC — sha256:4e4a5f149aad9f16ee8d4dce8ca2e35387f6d2de0429edefabe5fdce260f6412 — symbols:4
[x] research/datagen/roledata/config.py — module: datagen.roledata — 260 LOC — sha256:7f4e6f534579c3ecc7835c2ad6ed29b0e4388e4bfece3a326e04a50f2b2430d1 — symbols:26
[x] research/datagen/roledata/conftest.py — module: datagen.roledata — 20 LOC — sha256:f18c9c01bbde6884489619be04945c171fc3dca8a1660f9de0a1fccbcd865db9 — symbols:1
[x] research/datagen/roledata/finalize/__init__.py — module: datagen.roledata — 2 LOC — sha256:25a5437c68f9c127101a863f0c1707d9966d2d9cab75127b9e7fe560ff716c06 — symbols:0
[x] research/datagen/roledata/finalize/export.py — module: datagen.roledata — 165 LOC — sha256:9faaa605a185e6cedc3629691df871277b4e33d26e338c8288e68a54bbafd261 — symbols:6
[x] research/datagen/roledata/finalize/split.py — module: datagen.roledata — 163 LOC — sha256:0b26bb1a96314c519015a02605d5aa2b1edf3113dc9e310f87170f3fe1cc1be7 — symbols:8
[x] research/datagen/roledata/gates.py — module: datagen.roledata — 318 LOC — sha256:494242612e37675bfbaed476250e1dd2e7a1fc977b25cb3b33cd94421b7533c5 — symbols:22
[x] research/datagen/roledata/generator.py — module: datagen.roledata — 369 LOC — sha256:ce4f7e238b2773170c3bdd923a43661402976bd063c4855350eb2716bd98af8f — symbols:18
[skip] research/datagen/roledata/output/checksum.sha256 — lý do: data/runtime artifact (.sha256)
[x] research/datagen/roledata/output/dataset_card.md — module: datagen.roledata — 42 LOC — sha256:959a959ed1c3805e6e13bfa2a8ad8d20dfc897a01a39f7539ea926febff1c4c9 — symbols:0
[skip] research/datagen/roledata/output/export/acnellm_role_lora.jsonl — lý do: data/runtime artifact (.jsonl)
[x] research/datagen/roledata/output/export/dataset_info.json — module: datagen.roledata — 16 LOC — sha256:e7e1c4dd6c1c3ac9e7ce62ad5c65407e4f45786e67662a809218e9c164330dd1 — symbols:0
[x] research/datagen/roledata/output/generation_summary.json — module: datagen.roledata — 37 LOC — sha256:c529f3d67162df02461678351c8903293aa04caea97ba4b45dfd150e08a773c9 — symbols:0
[skip] research/datagen/roledata/output/rejected.audit.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/datagen/roledata/output/roledata.smoke.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/datagen/roledata/output/roledata.train.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/datagen/roledata/output/splits/holdout.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/datagen/roledata/output/splits/train.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/datagen/roledata/output/splits/val.jsonl — lý do: data/runtime artifact (.jsonl)
[x] research/datagen/roledata/pipeline.py — module: datagen.roledata — 625 LOC — sha256:1fa3ec53d6b2c5aed9e2050348fa18bd1c58c8208d608927bce7c7a63d0ddec1 — symbols:18
[x] research/datagen/roledata/PLAN.md — module: datagen.roledata — 297 LOC — sha256:1ac696195b931244317e3d4ba48d2deaaa2c8665a88cfbdeeff5b4bda72bbc0e — symbols:0
[x] research/datagen/roledata/prompts/B1_grounded_role.j2 — module: datagen.roledata — 1 LOC — sha256:16c60b1ca64d20150132889fa9ace3cf62bb294ba39bfa1781e0599a96cd29cf — symbols:0
[x] research/datagen/roledata/prompts/B2_missing_answer.j2 — module: datagen.roledata — 1 LOC — sha256:db0a3b77cdaf53c9863d7a60be6f07352a5011cd669a43a3c193e1082558f9df — symbols:0
[x] research/datagen/roledata/prompts/B3_irrelevant_chunk.j2 — module: datagen.roledata — 1 LOC — sha256:5fa485fdf14a2f6399d420086f84e4d101f2fb72b143259b0b738c038fb2ad9a — symbols:0
[x] research/datagen/roledata/prompts/B4_conflicting_docs.j2 — module: datagen.roledata — 1 LOC — sha256:ab8bb3da31adcb43a76aebe845771bcf5f6fcb9a5af376379a4c53252f54ceac — symbols:0
[x] research/datagen/roledata/prompts/B5_depth_anchor.j2 — module: datagen.roledata — 1 LOC — sha256:14187c145d749b8cc470a40e9b2f591d2875897e3459adff2e5b4141953b9604 — symbols:0
[x] research/datagen/roledata/prompts/K1_knowledge_anchor.j2 — module: datagen.roledata — 1 LOC — sha256:480e317dc2137b9594ef4b487726280928e6107d2a27ccedaf1beeefa71ffe56 — symbols:0
[x] research/datagen/roledata/prompts/R10_special_population.j2 — module: datagen.roledata — 1 LOC — sha256:a80e303a6bb311d33880e1868e3edac70585206f59f918f17eeacaf6fab3f51b — symbols:0
[x] research/datagen/roledata/prompts/R1_identity.j2 — module: datagen.roledata — 1 LOC — sha256:7954357a52f4d7cb342a82e9d63ffdb0c7232f813ce652652cf2897a199def39 — symbols:0
[x] research/datagen/roledata/prompts/R2_depth_adaptation.j2 — module: datagen.roledata — 1 LOC — sha256:a54ce3ad03dc6078b798298a9383329fe39e65e717ed9e3bd7fa74d77536206d — symbols:0
[x] research/datagen/roledata/prompts/R3_nonjudgment.j2 — module: datagen.roledata — 1 LOC — sha256:65b94a3965bbd80b4906055689c0164b4a6d498b89a18e9536a87124a91d1a04 — symbols:0
[x] research/datagen/roledata/prompts/R4_measured_empathy.j2 — module: datagen.roledata — 1 LOC — sha256:3e3bcbdbb5fd91602312ef3489737722c04fe8672f46d5bae62d4a89d22f8f07 — symbols:0
[x] research/datagen/roledata/prompts/R5_natural_clarification.j2 — module: datagen.roledata — 1 LOC — sha256:6268012727440fccb985d71ba7a7ab670c217292e7c205b3663912c62632ff52 — symbols:0
[x] research/datagen/roledata/prompts/R6_role_boundary.j2 — module: datagen.roledata — 1 LOC — sha256:44303ed779d53c880a8bcac1971c9d98b4aa51d17b3869cc5530006ae8405521 — symbols:0
[x] research/datagen/roledata/prompts/R7_conversation_glue.j2 — module: datagen.roledata — 1 LOC — sha256:495657fad859e84cf3c390bfb58cd6a212186fac8334da90f76f13e8a4039cb6 — symbols:0
[x] research/datagen/roledata/prompts/R8_meta_jailbreak.j2 — module: datagen.roledata — 1 LOC — sha256:46d9d3af8fc4a4828941a7271692b14df695c65c42a5e60dfba8319272f69e6f — symbols:0
[x] research/datagen/roledata/prompts/R9_multiturn.j2 — module: datagen.roledata — 1 LOC — sha256:5c91443f49c341fd253d165ff769988982f620068feff4a0dcfdb5592a61ff95 — symbols:0
[x] research/datagen/roledata/style_guide.md — module: datagen.roledata — 18 LOC — sha256:acb7986e3b294df13fe61a0d58fcc76454b308570423bed6d4e37de8fcb5241b — symbols:0
[x] research/datagen/roledata/taxonomy.yaml — module: datagen.roledata — 23 LOC — sha256:35b5c6ea54af8c0ab7db1e7e53acb6f894364412afe23ecb2b3d7e346c496bcd — symbols:0
[x] research/datagen/roledata/tests/__init__.py — module: datagen.roledata — 1 LOC — sha256:16dd320026251299b3783d174b759300e218a26f16b0154cabc2f4743332233f — symbols:0
[x] research/datagen/roledata/tests/conftest.py — module: datagen.roledata — 20 LOC — sha256:a17375311bde792ccf7bc009f11a89d0fb127e05440c5a6313dc49b8be764964 — symbols:1
[x] research/datagen/roledata/tests/test_anchor.py — module: datagen.roledata — 39 LOC — sha256:1524d1d827dd68ffff8600367379bc258bfd5ba370d0cf600e4fbb55695d2f6b — symbols:4
[x] research/datagen/roledata/tests/test_budget.py — module: datagen.roledata — 24 LOC — sha256:ff605854dfb5bb0df668f78c7b485023bb14fcffc1f5b42522ca052edf1f47c4 — symbols:3
[x] research/datagen/roledata/tests/test_export.py — module: datagen.roledata — 73 LOC — sha256:8dba20662eeefc20322fd7ecbccabfe040e75ec867eeec8dcb1b83160121e4f7 — symbols:5
[x] research/datagen/roledata/tests/test_gates.py — module: datagen.roledata — 234 LOC — sha256:0024e9a8ea0052a200e658684127004fda729d01cd881e57f39fd1d8703a095c — symbols:16
[x] research/datagen/roledata/tests/test_generator.py — module: datagen.roledata — 25 LOC — sha256:d305d0729647727bbce068c084b59b5e2dd57e6e2017490a7f07cf16bfd7b974 — symbols:2
[x] research/datagen/roledata/tests/test_split.py — module: datagen.roledata — 49 LOC — sha256:67c1336e8909100832f8a13f6277b7e8c6f395cf6400716f6c46bdf755d32549 — symbols:2
[x] research/datagen/roledata/tests/test_writer.py — module: datagen.roledata — 17 LOC — sha256:9df0b400d0c40e2eb1ab7c259adc687ee5e8afad2c3ebe09d0211262ad065000 — symbols:1
[x] research/datagen/roledata/writer.py — module: datagen.roledata — 82 LOC — sha256:e8a052ff334fec0a28f68578615a48d0d86a953917c6a6d42e4d5f51b12f44fc — symbols:9
[x] research/datagen/roledatav2/__init__.py — module: datagen.roledatav2 — 14 LOC — sha256:00546039934a13338a97abd31bce2068e9afeeb2af435d3b3b23b0e654e6a27e — symbols:1
[skip] research/datagen/roledatav2/_output.round1.cu/checksum.sha256 — lý do: data/runtime artifact (.sha256)
[x] research/datagen/roledatav2/_output.round1.cu/dataset_card.md — module: datagen.roledatav2 — 42 LOC — sha256:e39518eab6a170866effc02ef1bcd82aff13c4f38217561030ab16be341f7b63 — symbols:0
[skip] research/datagen/roledatav2/_output.round1.cu/export/acnellm_role_lora.jsonl — lý do: data/runtime artifact (.jsonl)
[x] research/datagen/roledatav2/_output.round1.cu/export/dataset_info.json — module: datagen.roledatav2 — 16 LOC — sha256:e7e1c4dd6c1c3ac9e7ce62ad5c65407e4f45786e67662a809218e9c164330dd1 — symbols:0
[x] research/datagen/roledatav2/_output.round1.cu/generation_summary.json — module: datagen.roledatav2 — 56 LOC — sha256:b385be9cb80a51ec3fe81a0e672bdacbbf645db767c8feb65c31a9c4669c68e8 — symbols:0
[x] research/datagen/roledatav2/_output.round1.cu/limit_checkpoint.json — module: datagen.roledatav2 — 26 LOC — sha256:dc5bc71e4bb2488778ae96e1c79fe4aa7903e0714343a6a7c92b5e186d519949 — symbols:0
[skip] research/datagen/roledatav2/_output.round1.cu/rejected.audit.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/datagen/roledatav2/_output.round1.cu/roledata.smoke.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/datagen/roledatav2/_output.round1.cu/roledata.train.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/datagen/roledatav2/_output.round1.cu/splits/holdout.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/datagen/roledatav2/_output.round1.cu/splits/train.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/datagen/roledatav2/_output.round1.cu/splits/val.jsonl — lý do: data/runtime artifact (.jsonl)
[x] research/datagen/roledatav2/anchor.py — module: datagen.roledatav2 — 6 LOC — sha256:c917fdb5507c33ddad7292b657d192e984833e8988a40e2d602d8d7f2f7212fb — symbols:1
[x] research/datagen/roledatav2/config.py — module: datagen.roledatav2 — 328 LOC — sha256:4f72b6301938e67ffc7a2d5b98a6d8baf99e48ce7f2b841014045c3e293416c6 — symbols:23
[x] research/datagen/roledatav2/conftest.py — module: datagen.roledatav2 — 20 LOC — sha256:44a6709fb958c270dc5744f2a6d906394d35e6e15ad5bc8333fdd7ee9adc91e2 — symbols:1
[x] research/datagen/roledatav2/finalize/__init__.py — module: datagen.roledatav2 — 11 LOC — sha256:7ffde139715792099fe200304bf9b8fda0be717cc1645ebcadf56e4f06a2c5ba — symbols:1
[x] research/datagen/roledatav2/finalize/__main__.py — module: datagen.roledatav2 — 68 LOC — sha256:dc9bf7084e06783f28efb80e8d138bfba98f8a8508ff3e92f02b2c116fc762ba — symbols:3
[x] research/datagen/roledatav2/finalize/split.py — module: datagen.roledatav2 — 146 LOC — sha256:9c284b65a72c1ee9d85dc5c4a0a2ecb3376e635012065fbf2f9f78bdb81a346e — symbols:3
[x] research/datagen/roledatav2/gates.py — module: datagen.roledatav2 — 520 LOC — sha256:dfa341763c333a0429b2fd456d4dac69245984e9085590b23a32e16fce0a7721 — symbols:35
[x] research/datagen/roledatav2/generator.py — module: datagen.roledatav2 — 750 LOC — sha256:2448d63f0dee8597c9df037e82881a5bce4ceedd22c6a85191293edeed6f05e5 — symbols:25
[x] research/datagen/roledatav2/knowledge.py — module: datagen.roledatav2 — 141 LOC — sha256:4689942eeec5efe52c95f6777ba441bbb1234be460130e453fac0bcc4eaba76c — symbols:12
[skip] research/datagen/roledatav2/output/checksum.sha256 — lý do: data/runtime artifact (.sha256)
[x] research/datagen/roledatav2/output/dataset_card.md — module: datagen.roledatav2 — 42 LOC — sha256:53b50ef40c67f3d475b1a0135db3d6bfee528a393106eaec82c25f3da5f3a289 — symbols:0
[skip] research/datagen/roledatav2/output/export/acnellm_role_lora.jsonl — lý do: data/runtime artifact (.jsonl)
[x] research/datagen/roledatav2/output/export/dataset_info.json — module: datagen.roledatav2 — 16 LOC — sha256:a6fd7bd867018890ddde16d36bacadca04a280f551c40e301487812c165a667a — symbols:0
[x] research/datagen/roledatav2/output/generation_summary.json — module: datagen.roledatav2 — 56 LOC — sha256:f240b7709a46d54b4f14b39d20b0d904411aefbd4b486061b7c77aa1a0b0da9b — symbols:0
[x] research/datagen/roledatav2/output/limit_checkpoint.json — module: datagen.roledatav2 — 28 LOC — sha256:62473c948991517f56d70899284cac940713497a5748337878077a10d469c70e — symbols:0
[skip] research/datagen/roledatav2/output/rejected.audit.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/datagen/roledatav2/output/roledata.smoke.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/datagen/roledatav2/output/roledata.train.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/datagen/roledatav2/output/skeletons.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/datagen/roledatav2/output/skeletons.smoke.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/datagen/roledatav2/output/splits/holdout.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/datagen/roledatav2/output/splits/train.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/datagen/roledatav2/output/splits/val.jsonl — lý do: data/runtime artifact (.jsonl)
[x] research/datagen/roledatav2/phase1.py — module: datagen.roledatav2 — 377 LOC — sha256:00f1f771d9e0652347f5309c2ac86bed4b515213b057a080b12a46eabcab0280 — symbols:12
[x] research/datagen/roledatav2/pipeline.py — module: datagen.roledatav2 — 326 LOC — sha256:94501e8fa5354963c9d04308e4410e3617f4d55d9a2d3788784aa31250031c18 — symbols:14
[x] research/datagen/roledatav2/probe_provider.py — module: datagen.roledatav2 — 251 LOC — sha256:0c7cd7a666757ef0762cb7ec4f920dca62be61524c99c82cb9b5939fe29cc620 — symbols:14
[x] research/datagen/roledatav2/prompts/R5_natural_clarification.j2 — module: datagen.roledatav2 — 12 LOC — sha256:78609f277b410432e0710c3ddbf793bd6295e92edbfeb66e16bc2e973691ad25 — symbols:0
[x] research/datagen/roledatav2/prompts/R9_multiturn.j2 — module: datagen.roledatav2 — 10 LOC — sha256:58ad2e2e68f3481cc8c0e69183b94e6ba7db98142083ba7efa1fa93aa7953827 — symbols:0
[x] research/datagen/roledatav2/ROUND2.md — module: datagen.roledatav2 — 137 LOC — sha256:0c14622da8d6fb3333a4445d3c9cfde7825bed654a4fd1fa10fdcf6645aaf8e2 — symbols:0
[x] research/datagen/roledatav2/show_samples.py — module: datagen.roledatav2 — 134 LOC — sha256:be27a5619415e448fe5d5f687277fc456e5c6705253f9bd68b4fb611e8519994 — symbols:6
[x] research/datagen/roledatav2/taxonomy.yaml — module: datagen.roledatav2 — 115 LOC — sha256:c973d9c5c1173bded80a96432e4f4c8c9bb117e524b2894a039c2a71645be41d — symbols:0
[x] research/datagen/roledatav2/tests/__init__.py — module: datagen.roledatav2 — 0 LOC — sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 — symbols:0
[x] research/datagen/roledatav2/tests/helpers.py — module: datagen.roledatav2 — 168 LOC — sha256:c210f1089eb7fd3154f758ef73c83d49f660498b89cfa4bfaec91c354484fd8e — symbols:8
[x] research/datagen/roledatav2/tests/test_config.py — module: datagen.roledatav2 — 268 LOC — sha256:526ce6b31eff4457de88384827ca9d47544c98b29ea828e3a4b63d23c66bf71f — symbols:29
[x] research/datagen/roledatav2/tests/test_context_survives.py — module: datagen.roledatav2 — 160 LOC — sha256:6f1ac09fcc96387c3ee9e893394d220fc007f9395be96500e899e2bbb6da77b9 — symbols:12
[x] research/datagen/roledatav2/tests/test_distribution.py — module: datagen.roledatav2 — 78 LOC — sha256:5eca2ac7d6345aa1251a4f8847f08f8d2a8b3f580e289f98732ab0a28d4e985a — symbols:8
[x] research/datagen/roledatav2/tests/test_gates_v2.py — module: datagen.roledatav2 — 249 LOC — sha256:7714bbc9717fd67205f34443771643b12e2bb52fad98441e1f8cd3b17d38194a — symbols:27
[x] research/datagen/roledatav2/tests/test_grounding_language.py — module: datagen.roledatav2 — 270 LOC — sha256:f10f832bbfa26164f09122cc7e1d0610a57b1998259bb155679261f7738f7bd3 — symbols:30
[x] research/datagen/roledatav2/tests/test_knowledge.py — module: datagen.roledatav2 — 197 LOC — sha256:ec1e61329a35d29046edfc712ca69e15f9761d58806d0872605abb9ac4991c97 — symbols:17
[x] research/datagen/roledatav2/tests/test_phase1.py — module: datagen.roledatav2 — 373 LOC — sha256:950edfb5ec04ddad791aa8e6199b9f7b4d9d226dd71c922113f4f5e6984a3857 — symbols:22
[x] research/datagen/roledatav2/tests/test_pipeline.py — module: datagen.roledatav2 — 314 LOC — sha256:0a0a0164b8ff77e221a91348d8fe7ea21eb2b8f6039f788a816a85757242bbc8 — symbols:23
[x] research/datagen/roledatav2/tests/test_r10_rx_warning.py — module: datagen.roledatav2 — 97 LOC — sha256:2925c7b49221129e82cdd75241d4512b1b6a00fa228e7e605dd151e7e7a2d2f7 — symbols:12
[x] research/datagen/roledatav2/tests/test_round2.py — module: datagen.roledatav2 — 217 LOC — sha256:dcb4ca78e1c65c0c4ede4ed1ffd54835f2f7fa639c536218878248918259c6c7 — symbols:18
[x] research/datagen/roledatav2/tests/test_smoke_all_cases.py — module: datagen.roledatav2 — 234 LOC — sha256:5216a279c34576ba4fcb9d7e1582272e428cc011f4209591b786bdd0506581c9 — symbols:20
[x] research/datagen/roledatav2/writer.py — module: datagen.roledatav2 — 6 LOC — sha256:766ae98b5270d9b66c98c2f146dc14613a248f946e99401b57e3f4552191ff43 — symbols:1
[x] research/datagen/RUN.bat — module: datagen.RUN — 14 LOC — sha256:0d82bb410b9fcaf2622dbf29ae886a08a3237cccbb7ae6d50cec59e532dcfc56 — symbols:0
[x] research/datagen/test_gates.py — module: datagen.test_gates — 146 LOC — sha256:ae106f0d70a31ba0f4656cd912ee0be01a4732f90a6c8e33286c2ed644215169 — symbols:10
[x] research/datagen/test_pipeline_contracts.py — module: datagen.test_pipeline_contracts — 302 LOC — sha256:db678da78144ce3c91a1a983154b8978ab9a1f8972d9b543705badce52710c61 — symbols:25
[x] research/datagen/UNIFIED_INTAKE_DATAGEN_SPEC.md — module: datagen.UNIFIED_INTAKE_DATAGEN_SPEC — 250 LOC — sha256:a651e196b0077607d352e110d3af41ceb1500694778c90e52f06c10aa4fb1fd3 — symbols:0
[x] research/datagen/writer.py — module: datagen.writer — 69 LOC — sha256:a81d3f8ce888b9923559c7c6b09a0a6c518ab767f8493a89ce276cc55bf88d54 — symbols:8
[x] research/dataset_viz/generate_report.py — module: research — 353 LOC — sha256:710c6d83b6fb97a0635e08c9c55d5c6354cdc929244d6989a2305198bc01e957 — symbols:3
[x] research/dataset_viz/plot_datasets.py — module: research — 293 LOC — sha256:1f8f2109587fb564335ef79f23b406f2dbe627882eca8cceb01933d08d1237dd — symbols:12
[x] research/dataset_viz/README.md — module: research — 6 LOC — sha256:9a8fb083826c553f4121187379c58f69a2eb0c201b30eaaca91591ac4011afa7 — symbols:0
[x] research/dataset_viz/run_all.py — module: research — 72 LOC — sha256:37e1ffe7e4ef10bce733e168dd22b79de61cb15b3c9bc5f631517870a2f68ec8 — symbols:2
[x] research/evaluation/__init__.py — module: eval.__init__ — 0 LOC — sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 — symbols:0
[x] research/evaluation/adapters/__init__.py — module: eval.adapters — 0 LOC — sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 — symbols:0
[x] research/evaluation/adapters/_repo.py — module: eval.adapters — 80 LOC — sha256:606a000f34c6f31a2dc91d69d0ba7be5f6755b343bba76e7d49ccfd153623217 — symbols:2
[x] research/evaluation/common.py — module: eval.common — 106 LOC — sha256:876c1ef392d150a821fa8c34cfcc3865802620c9ae13f581f62aed5cce6cfaf1 — symbols:14
[x] research/evaluation/configs/__init__.py — module: eval.configs — 0 LOC — sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 — symbols:0
[x] research/evaluation/datasets/__init__.py — module: eval.datasets — 0 LOC — sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 — symbols:0
[skip] research/evaluation/datasets/_trash/eval_set.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/evaluation/datasets/_trash/intake_eval.v2.partial.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/evaluation/datasets/_trash/intake_eval.v2.smoke.audit.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/evaluation/datasets/_trash/intake_eval.v2.smoke.partial.jsonl — lý do: data/runtime artifact (.jsonl)
[x] research/evaluation/datasets/_trash/README.md — module: eval.datasets — 15 LOC — sha256:cdabeee5d2a45ba25e9248466ea20d4e8eab09900e99f01f27d1ea7582f8ff87 — symbols:0
[skip] research/evaluation/datasets/_trash/sample.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/evaluation/datasets/active/generator_eval.v3_2_145.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/evaluation/datasets/active/generator_eval.v3_2_145.smoke.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/evaluation/datasets/active/intake_eval.v2_1500.audit.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/evaluation/datasets/active/intake_eval.v2_1500.jsonl — lý do: data/runtime artifact (.jsonl)
[x] research/evaluation/datasets/active/MANIFEST.json — module: eval.datasets — 9 LOC — sha256:f9db01f49669dcb9c69ec28e94f9f233a13a40af23fde6578ff14cbf2add3a22 — symbols:0
[skip] research/evaluation/datasets/archive/generator_eval.v2_0_197.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/evaluation/datasets/archive/generator_eval.v3_1_195.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/evaluation/datasets/archive/generator_eval.v3_1_199.jsonl — lý do: data/runtime artifact (.jsonl)
[x] research/evaluation/datasets/archive/generator_eval.v3_1_199.MANIFEST.json — module: eval.datasets — 6 LOC — sha256:cb46c7e6a045d8dbe198f3c0129127b23b86a3bd6d417e24669ef6dfc6c0893f — symbols:0
[x] research/evaluation/datasets/archive/README.md — module: eval.datasets — 47 LOC — sha256:1534b60512f0e352639747f4948b7672b2674a69bccb77f20677ab8a328e90b6 — symbols:0
[skip] research/evaluation/datasets/extra/intake_eval.v1_353.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/evaluation/datasets/extra/intake_eval.v2_smoke_10.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/evaluation/datasets/extra/intake_pregnancy_probe_41.jsonl — lý do: data/runtime artifact (.jsonl)
[x] research/evaluation/datasets/extra/MANIFEST.json — module: eval.datasets — 8 LOC — sha256:ded4571a3272598718d80d28f6989c1ebb61d01e760cc2a7a5e1b18f57dc35c7 — symbols:0
[x] research/evaluation/datasets/extra/README.md — module: eval.datasets — 32 LOC — sha256:607de182c9461f91095be4edeab87e0ce5dba9e8c735d3de1d5a1e94c337c2ca — symbols:0
[x] research/evaluation/datasets/make_eval_set.py — module: eval.datasets — 1105 LOC — sha256:d5c9eaa5e0ac9f4853516078a93008e076ca7f24e680544d3d329b0ca7fd47ab — symbols:46
[x] research/evaluation/datasets/make_intake_set.py — module: eval.datasets — 766 LOC — sha256:cc6caa9e5658756834f9666ee3f562640bf9c4afb8d548939e1c45c2ca6fc98b — symbols:36
[x] research/evaluation/datasets/make_intake_set_v2.py — module: eval.datasets — 926 LOC — sha256:809067b88e486723b93690199de9281c9548b6fbb44194010a510bc071b948d1 — symbols:53
[x] research/evaluation/datasets/make_pregnancy_probe.py — module: eval.datasets — 167 LOC — sha256:57aefcbc7404d5f0c11ea3ca9a82a0c4911412d01964a161782ab3004fd0f634 — symbols:7
[skip] research/evaluation/datasets/policy_cases.jsonl — lý do: data/runtime artifact (.jsonl)
[x] research/evaluation/datasets/README.md — module: eval.datasets — 105 LOC — sha256:38936ef79446fd0cdcf96a11d98c01ac5e397dd320d2e3a9e895326aca372475 — symbols:0
[x] research/evaluation/datasets/registry.py — module: eval.datasets — 106 LOC — sha256:c708f01aa91681179abbc59f4e16a46fd2d353b07f9bcb6dbabbaecd2ebf896b — symbols:7
[x] research/evaluation/e2e.ps1 — module: eval.e2e — 347 LOC — sha256:52ecbb7be297f74d48a915b6d131029b6859c096f4991de71fd03db48064f079 — symbols:7
[x] research/evaluation/eval_context.md — module: eval.eval_context — 433 LOC — sha256:9fa43ff498e1bba01e62d8c203991ea2eb9f3b10619b3253f87b7926226cd4c8 — symbols:0
[x] research/evaluation/full_evaluation.py — module: eval.full_evaluation — 415 LOC — sha256:1855b3434c76d04875c74cf4e2be23d2253f5f9a21afed0a9b1517cf9b0866df — symbols:22
[x] research/evaluation/judges/__init__.py — module: eval.judges — 0 LOC — sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 — symbols:0
[x] research/evaluation/judges/calibrate.py — module: eval.judges — 433 LOC — sha256:5f6e8f8d3603a1bae1370035961ac35e6a47d09d4c5dfb54a9a3ea4227b68670 — symbols:21
[x] research/evaluation/judges/clients.py — module: eval.judges — 269 LOC — sha256:f51cc7d275a43f415f9f8298f3dbc9c6d3e769e04392b610d4d5d0133b31d42a — symbols:19
[x] research/evaluation/judges/context.py — module: eval.judges — 221 LOC — sha256:c58f973e4f3f4f31c2a15182cf930af9a8e9ff1ccbafab2f633bdf8308f0834f — symbols:12
[x] research/evaluation/judges/prompts/claim_extract.md — module: eval.judges — 7 LOC — sha256:8db0e44e433f441f528335197882cec9426e1ece7dd5d40f9fa18f7697fec2ab — symbols:0
[x] research/evaluation/judges/prompts/entailment.md — module: eval.judges — 13 LOC — sha256:c09ca8a87a74fb2094e850d09c566d3f0ba6d420340fd4e93a487925b86c1064 — symbols:0
[x] research/evaluation/judges/prompts/error_classify.md — module: eval.judges — 20 LOC — sha256:551d897a7587b0256e9c702508f9864b285b57f30277d3152abc2c6af6f2097c — symbols:0
[x] research/evaluation/judges/prompts/pairwise.md — module: eval.judges — 21 LOC — sha256:1ecfee0114a9e1aa1f08ecd04f85a85b7235dbaf47b544ff9f392d6e60fc95fb — symbols:0
[x] research/evaluation/judges/prompts/pointwise.md — module: eval.judges — 33 LOC — sha256:1541398c866e94fe17ad4b029d764dbbbf1b61de1d02239e14fc278710b8d0e7 — symbols:0
[x] research/evaluation/judges/rubrics.py — module: eval.judges — 176 LOC — sha256:9193831644c286c96faec596b462505c23bab2b7040621589535e25e5360330d — symbols:12
[x] research/evaluation/METRIC_EVIDENCE.md — module: eval.METRIC_EVIDENCE — 364 LOC — sha256:ce4a118a2767d7b9082b1e1eb551c7c1f043e423f75d5a091e65e1b9f8b4962a — symbols:0
[x] research/evaluation/metrics/__init__.py — module: eval.metrics — 0 LOC — sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 — symbols:0
[x] research/evaluation/metrics/classification.py — module: eval.metrics — 75 LOC — sha256:9983b8bddc3b80a4b5cf24a35e1cc51fe37f5017f5a67eed0ed98f224ac529b3 — symbols:7
[x] research/evaluation/metrics/deterministic.py — module: eval.metrics — 90 LOC — sha256:30c5ed0dde0ecb83c0d90494ea4f92ba6f569ea7f8ee855a214918a33270b4bf — symbols:7
[x] research/evaluation/metrics/intake.py — module: eval.metrics — 126 LOC — sha256:d82dc227b6754ffe35d477f66dadfd788c0644d2d29ff72f899b9b4ddca03054 — symbols:6
[x] research/evaluation/metrics/scorecard.py — module: eval.metrics — 200 LOC — sha256:2a3e80b712a218073fd534b087c6986ac6c20d0d93b9bd644d2b8e6632b84eaf — symbols:8
[x] research/evaluation/README.md — module: eval.README — 170 LOC — sha256:edd4b853861bb6ae07343310128d4ce770445115a2c7a1842585c0420ea9fd90 — symbols:0
[x] research/evaluation/reports/ab_intake/acne-intaker-parity.json — module: eval.reports — 3754 LOC — sha256:34090f02fdc8cc11d8c9837e765f0f1022887aa6f31bd7b88bf2d02244990a37 — symbols:0
[x] research/evaluation/reports/ab_intake/acne-intaker.json — module: eval.reports — 3754 LOC — sha256:8e74464419fcf853523fdd33d94c9f93384a4123e2b4462ea89d28ae559728a3 — symbols:0
[x] research/evaluation/reports/ab_intake/full.json — module: eval.reports — 16636 LOC — sha256:fb94962d8db873becb082e17cc57a237ce1decbd33bab80804dc822f7dee8712 — symbols:0
[x] research/evaluation/reports/calibration/_goi_gui_di/cham.html — module: eval.reports — 80 LOC — sha256:1672a042ac648fdc28777b2efce17fc0e825605307820be0295310b4b533fbbd — symbols:0
[x] research/evaluation/reports/calibration/_goi_gui_di/HUONG_DAN.md — module: eval.reports — 122 LOC — sha256:b800acc3229c6fa25cfec2839fbfdb71903c801fa4e9cfe964785dc2e7c4d7ad — symbols:0
[skip] research/evaluation/reports/calibration/calibration_key.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/evaluation/reports/calibration/calibration_key.v1_nochecklist.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/evaluation/reports/calibration/calibration_sheet.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/evaluation/reports/calibration/calibration_sheet.v1_nochecklist.jsonl — lý do: data/runtime artifact (.jsonl)
[x] research/evaluation/reports/calibration/cham.html — module: eval.reports — 80 LOC — sha256:1672a042ac648fdc28777b2efce17fc0e825605307820be0295310b4b533fbbd — symbols:0
[skip] research/evaluation/reports/calibration/cham_60cau.zip — lý do: binary/asset (.zip)
[x] research/evaluation/reports/calibration/merged_v1v2.json — module: eval.reports — 1 LOC — sha256:2f48823a24cff7c127af76b08cc89e4e478ab19e11d742d7c056b6ef6cbea462 — symbols:0
[x] research/evaluation/reports/frontier_system_prompt_smoke_20260807/.fingerprint — module: eval.reports — 1 LOC — sha256:38cdc19faf551330151d7ba02dfe7328c1e64137e8b8a7e15a7e3a8474e3e88d — symbols:0
[skip] research/evaluation/reports/frontier_system_prompt_smoke_20260807/run.log — lý do: data/runtime artifact (.log)
[x] research/evaluation/reports/full_eval_1/ablation/.fingerprint — module: eval.reports — 1 LOC — sha256:db6d436c6d4e9bc7b7a96c2c2e02fad1e3600b4cc0a5c17c5791d9b2c539c1f9 — symbols:0
[x] research/evaluation/reports/full_eval_1/ablation/results.json — module: eval.reports — 139767 LOC — sha256:985366032f5646895a3674e791eb3c4dec98e0a52f959cbd44ef12f0e6538790 — symbols:0
[skip] research/evaluation/reports/full_eval_1/ablation/rows.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/evaluation/reports/full_eval_1/ablation/run.log — lý do: data/runtime artifact (.log)
[x] research/evaluation/reports/full_eval_1/ablation/summary.json — module: eval.reports — 4592 LOC — sha256:a6580ae03ba4f446bff5f0e78e98a3763352c41eb01068ba8f76162c56c17f1b — symbols:0
[x] research/evaluation/reports/full_eval_1/intake/report.json — module: eval.reports — 4922 LOC — sha256:cd92ee950c5d06aae8be0c735897419c4d903d84791f18dc0c8f849046f9f481 — symbols:0
[x] research/evaluation/reports/full_eval_1/retrieval/results.json — module: eval.reports — 4633 LOC — sha256:387f85457898f500ade2e0b64e0af46db7bc91ca2c072d39e4594ee33ca60fbc — symbols:0
[x] research/evaluation/reports/full_eval_1/summary.json — module: eval.reports — 45 LOC — sha256:143e28f01617db4d058d22826efe1ebc0a9bd4769ffa79ac60315fdb01393916 — symbols:0
[x] research/evaluation/reports/full_eval_part2/ablation/.fingerprint — module: eval.reports — 1 LOC — sha256:db6d436c6d4e9bc7b7a96c2c2e02fad1e3600b4cc0a5c17c5791d9b2c539c1f9 — symbols:0
[skip] research/evaluation/reports/full_eval_part2/ablation/rows.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/evaluation/reports/full_eval_part2/ablation/run.log — lý do: data/runtime artifact (.log)
[x] research/evaluation/reports/full_eval_part2/intake/report.json — module: eval.reports — 4698 LOC — sha256:8f70218772e5e588096cc9243a311c83183b27e9d4affab03605fe21aede3bb9 — symbols:0
[x] research/evaluation/reports/full_eval_part2/retrieval/results.json — module: eval.reports — 4684 LOC — sha256:e5f65174616c5056b128edfab4cacb380a187b7a3e73500c560e336403370919 — symbols:0
[x] research/evaluation/reports/full_eval_part2/summary.json — module: eval.reports — 45 LOC — sha256:7e2161d05e1273eb66bd8d85ac5b8316ce235bbfaafc622d6ed690d1c94cecef — symbols:0
[x] research/evaluation/reports/intake_eval/report.json — module: eval.reports — 5085 LOC — sha256:3c74d0fe1ecac25abb3ce953c988ea64600a2a13e47e0f1a5b03c8a3596e4ecf — symbols:0
[skip] research/evaluation/reports/judge_cache.sqlite — lý do: binary/asset (.sqlite)
[x] research/evaluation/reports/judge_calibration.json — module: eval.reports — 105 LOC — sha256:fb2199c38769f28bbf6e6b336c6ea3b764d7f2a50f7124af58d1c760485f7b2c — symbols:0
[skip] research/evaluation/reports/rescore_gpt/v1/rows.jsonl — lý do: data/runtime artifact (.jsonl)
[x] research/evaluation/reports/rescore_gpt/v1/summary.json — module: eval.reports — 32 LOC — sha256:48b9702c4295f7804b5760f637146a8a5c4eb0ca44fcc49a24d5eddde878fe68 — symbols:0
[skip] research/evaluation/reports/rescore_gpt/v2/rows.jsonl — lý do: data/runtime artifact (.jsonl)
[x] research/evaluation/reports/rescore_gpt/v2/summary.json — module: eval.reports — 32 LOC — sha256:e85455e866cf092b6ed2f07f3e68303cc6e56fcdd6d43d6e08ed9b811125caed — symbols:0
[skip] research/evaluation/reports/rescore_luna/v1/rows.jsonl — lý do: data/runtime artifact (.jsonl)
[x] research/evaluation/reports/rescore_luna/v1/summary.json — module: eval.reports — 32 LOC — sha256:1eeeca8ca0e5eb410db485dadc6b7df1d03faeb4d3a1d9c2c0e275128c18c299 — symbols:0
[skip] research/evaluation/reports/rescore_luna/v2/rows.jsonl — lý do: data/runtime artifact (.jsonl)
[x] research/evaluation/reports/rescore_luna/v2/summary.json — module: eval.reports — 32 LOC — sha256:724316bbc4c835805ceda69d852199019b1db339cd1135d5a89b5c1727e1bcda — symbols:0
[x] research/evaluation/reports/run/intake/report.json — module: eval.reports — 4689 LOC — sha256:4e37733c582359a563a33b5530ef6a2c5a05f9a72e60b5f5fe150b4e2ae2cb5f — symbols:0
[x] research/evaluation/reports/run/summary.json — module: eval.reports — 45 LOC — sha256:42e722cb7ca855a6b1b78a6e7d4046ce5bedb59e757549ad76e9088288272c82 — symbols:0
[x] research/evaluation/reports/run_full/intake/report.json — module: eval.reports — 4689 LOC — sha256:c17ab121cd6f1b6e13c9ebbb9f6f89be118f2b0fffedaba73303a324e3b7e4bb — symbols:0
[x] research/evaluation/reports/run_full/summary.json — module: eval.reports — 45 LOC — sha256:c5ca58519f412dae2ef9bf70af1f5ed40e619d80df3da57188094fdf85e23225 — symbols:0
[skip] research/evaluation/reports/run_full_v3_2.zip — lý do: binary/asset (.zip)
[x] research/evaluation/reports/run_full_v3_2/ablation/.fingerprint — module: eval.reports — 1 LOC — sha256:da582369d50c76639ca1547fef6ca5b80a1661957b54a790568b883a9ca070c7 — symbols:0
[x] research/evaluation/reports/run_full_v3_2/ablation/results.json — module: eval.reports — 112284 LOC — sha256:299d7e2791b0699c2761c2bf38e9d9a2ce8e62c533afa971b1c0c6496719f228 — symbols:0
[skip] research/evaluation/reports/run_full_v3_2/ablation/rows.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/evaluation/reports/run_full_v3_2/ablation/run.log — lý do: data/runtime artifact (.log)
[x] research/evaluation/reports/run_full_v3_2/ablation/summary.json — module: eval.reports — 3380 LOC — sha256:dd6c491e2cae6823521c0dc8b6cee83c19b86b97c548c8919bbb7e40623b6d29 — symbols:0
[x] research/evaluation/reports/run_full_v3_2/ASSESSMENT.md — module: eval.reports — 134 LOC — sha256:82696c1e77006200a89066498183e902085ea85e6bbb77277f892a16b6a49a49 — symbols:0
[x] research/evaluation/reports/run_full_v3_2/ASSESSMENT_review.md — module: eval.reports — 207 LOC — sha256:68c78ebd79302c3747744c5769cc46fb459c1098f20b3678f581dd8e109e8dbc — symbols:0
[skip] research/evaluation/reports/run_full_v3_2/e2e.console.log — lý do: data/runtime artifact (.log)
[x] research/evaluation/reports/run_full_v3_2/GENERATOR_ROOT_CAUSE.md — module: eval.reports — 241 LOC — sha256:9c57ebe9c97b5376b73e9af1a77048249496baedb310ed77f1967448e1ba0673 — symbols:0
[x] research/evaluation/reports/run_full_v3_2/intake/report.json — module: eval.reports — 16636 LOC — sha256:e75680d5497f5bd6293497bd63a5550fce96cad0068bc7a69b1e5827b67af3de — symbols:0
[x] research/evaluation/reports/run_full_v3_2/retrieval/results.json — module: eval.reports — 3617 LOC — sha256:28969c1660ee01654293724e39d29a159c21c2d3f078de662c7efc4fcd2cac69 — symbols:0
[x] research/evaluation/reports/run_full_v3_2/summary.json — module: eval.reports — 45 LOC — sha256:7bea1f2047741d6a9ffe2bd6940f8843e272b10500d88bc937ef6e832516ad12 — symbols:0
[x] research/evaluation/reports/smoke_ds/intake/report.json — module: eval.reports — 927 LOC — sha256:ccfe6cbb05651f4769b256feee0affe0301455a322546b624b38ec02a82f5b74 — symbols:0
[x] research/evaluation/reports/smoke_ds/summary.json — module: eval.reports — 45 LOC — sha256:a81273d15f58d64138bc6ec966105cee095ea422b7d82872e106fc7e92c493ea — symbols:0
[skip] research/evaluation/reports/v1_round1/rows.jsonl — lý do: data/runtime artifact (.jsonl)
[x] research/evaluation/reports/v2_full/ablation/.fingerprint — module: eval.reports — 1 LOC — sha256:da582369d50c76639ca1547fef6ca5b80a1661957b54a790568b883a9ca070c7 — symbols:0
[x] research/evaluation/reports/v2_full/ablation/results.json — module: eval.reports — 112943 LOC — sha256:3fe2da23981823fa0ddac740e3b532b52bde573c3f790153a377b6a941b613e7 — symbols:0
[skip] research/evaluation/reports/v2_full/ablation/rows.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/evaluation/reports/v2_full/ablation/run.log — lý do: data/runtime artifact (.log)
[x] research/evaluation/reports/v2_full/ablation/summary.json — module: eval.reports — 3614 LOC — sha256:9ef9fe1ca5c03a08e5a925152459147aedcebde6742fbb79e656164aab628f90 — symbols:0
[x] research/evaluation/reports/v2_full/intake/report.json — module: eval.reports — 16794 LOC — sha256:2b78c5c8e703dc171b61bfbe0ec04cd950c6386515e2cec4fbab74df9414432c — symbols:0
[x] research/evaluation/reports/v2_full/retrieval/results.json — module: eval.reports — 3617 LOC — sha256:504a17040f7af255e082d371a155ff9be1895c63ae0703bf6340b2b1779f8020 — symbols:0
[x] research/evaluation/reports/v2_full/summary.json — module: eval.reports — 45 LOC — sha256:8b8403c813827d1773198255d34b7b3ba75f24fd329fae8beb028e2106e4c86e — symbols:0
[x] research/evaluation/reports/v2_round2/.fingerprint — module: eval.reports — 1 LOC — sha256:f596e26f08c8960946c37b7f67d77d637cd15c8ab8f8f26aba711fca802cb3f4 — symbols:0
[x] research/evaluation/reports/v2_round2/results.json — module: eval.reports — 1 LOC — sha256:6e7ee3be435a53cf6b1c0c0cd1b5e598d7f25af102512ac46431d628554b9265 — symbols:0
[skip] research/evaluation/reports/v2_round2/rows.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/evaluation/reports/v2_round2/run.log — lý do: data/runtime artifact (.log)
[x] research/evaluation/reports/v2_smoke/.fingerprint — module: eval.reports — 1 LOC — sha256:d2f4ec68f31fc1872224a376de4affb05fd3b5d3c0319a545230a8325b334313 — symbols:0
[skip] research/evaluation/reports/v2_smoke/rows.jsonl — lý do: data/runtime artifact (.jsonl)
[skip] research/evaluation/reports/v2_smoke/run.log — lý do: data/runtime artifact (.log)
[x] research/evaluation/RERUN_DEEPSEEK.md — module: eval.RERUN_DEEPSEEK — 38 LOC — sha256:036c43c34935e7518b56b302bf357ac7e8d7cf48b0217842095dacba88765481 — symbols:0
[x] research/evaluation/runners/__init__.py — module: eval.runners — 0 LOC — sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 — symbols:0
[x] research/evaluation/runners/rescore.py — module: eval.runners — 418 LOC — sha256:e23c7c99f988f0e70de28d3434580b38308d5d8fdd37833bd334ae75513c68e6 — symbols:20
[x] research/evaluation/runners/run_ablation.py — module: eval.runners — 1451 LOC — sha256:72767f9a98af9d42432c9ae4f2c58cba3370333e387dae1187d73aba32bd2fa3 — symbols:49
[x] research/evaluation/runners/run_intake.py — module: eval.runners — 1134 LOC — sha256:203b142b31de334a57d59ae7d6f8cf1012ef53b4ffd23803f3c1d42a8b851637 — symbols:50
[x] research/evaluation/runners/run_retrieval.py — module: eval.runners — 196 LOC — sha256:44d29339749aa0bd640da70e8b73546a9cd83b2b9af2568ec531125ecd1cfba8 — symbols:8
[x] research/evaluation/severity.py — module: eval.severity — 124 LOC — sha256:7b40514a50218c09f45497fa5cffee119e96a602e38fe0ae43266c79c8f03e1e — symbols:6
[x] research/evaluation/tests/__init__.py — module: eval.tests — 0 LOC — sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 — symbols:0
[x] research/evaluation/tests/test_classification.py — module: eval.tests — 46 LOC — sha256:d36a8e0059eaf73ab11b3bd83cbc9c474019293b263834abcd17e2d9aab5b589 — symbols:5
[x] research/evaluation/tests/test_context_judge.py — module: eval.tests — 92 LOC — sha256:8893066cddc293c148a73b42b6d7e20c78f44c839e516a543e1851c293293ab0 — symbols:10
[x] research/evaluation/tests/test_dataset_dedup.py — module: eval.tests — 288 LOC — sha256:c4242dddbef4b1ea8dcbae9dff3799cf3061acfbd524cb2bed06316d1aa1ce6d — symbols:26
[x] research/evaluation/tests/test_field_accuracy.py — module: eval.tests — 82 LOC — sha256:625f97bf1beedc9e475873d191d44a650425d7919c5f5371a8d75ea6c74c7f95 — symbols:9
[x] research/evaluation/tests/test_intake_metrics.py — module: eval.tests — 29 LOC — sha256:341097292910d765919bfc8176896bdb6573b435619916b775496e9a8ac2b552 — symbols:4
[x] research/evaluation/tests/test_make_intake_set.py — module: eval.tests — 453 LOC — sha256:fa052dbd3fe16dabe82f4c170684d1fea64e2030e9a856ec3d3bbbf79a31b892 — symbols:41
[x] research/evaluation/tests/test_make_intake_set_v2.py — module: eval.tests — 267 LOC — sha256:086654357e39a67c0028050214f7eba6d9129de12ed9a2a33907deb84b36be74 — symbols:20
[x] research/evaluation/tests/test_metrics.py — module: eval.tests — 43 LOC — sha256:76b6615429b3192a82db43265b9c413674e6f5cd0fe8bb42b0d09a86e7969042 — symbols:5
[x] research/evaluation/tests/test_per_value_metrics.py — module: eval.tests — 52 LOC — sha256:44e8a7e669e6a85f1d15388b98054f9de4c3fee13c13dd2a35704b43258f8277 — symbols:5
[x] research/evaluation/tests/test_registry.py — module: eval.tests — 62 LOC — sha256:b2956eaec5a535352cb86c8c42aac00b03654fc70e7f391db2d940cf45d2c93f — symbols:7
[x] research/evaluation/tests/test_run_ablation.py — module: eval.tests — 202 LOC — sha256:48cd8bfd24b9c0fb4a34c20f32043dafb0810db03e5323377986992f82f52342 — symbols:11
[x] research/evaluation/tests/test_run_intake.py — module: eval.tests — 130 LOC — sha256:e1ebd178dd698c397eccabb4a53dcc6f2291c8868972db6c040c6b6309369d64 — symbols:10
[x] research/evaluation/tests/test_severity_anchor.py — module: eval.tests — 102 LOC — sha256:a128e954b8385e2f0ce428e8f7ef96feca74481965bc61c8ca0ac3aa8e759685 — symbols:12
[x] research/evaluation/tests/test_severity_metrics.py — module: eval.tests — 62 LOC — sha256:8f8b2acc2a7182cf06de19c387827f0adde4170ff50e9a3d01177f75caaa83c3 — symbols:6
[x] research/evaluation/trace.py — module: eval.trace — 275 LOC — sha256:6cf1dc683e27d69f1bd0b9a302eed0ce101845183199cfee30ab7201b226171a — symbols:21
[x] research/evaluation/WIKI.html — module: eval.WIKI — 286 LOC — sha256:901ddc191be96d2b581032e305589797a4f1393868ac8dd21c240954eb551554 — symbols:0
[x] research/guideline_docs/build_guideline_chunks.py — module: research — 258 LOC — sha256:8adceda1f91727d93d9901dad5b4e31746faf729cc5b2aaa478e6b237e283624 — symbols:21
[x] research/guideline_docs/download_acne_pdfs.py — module: research — 184 LOC — sha256:8e17bc111245055cb8ae323ba245248975a50f28ce224aa79b14f47b06f10479 — symbols:15
[skip] research/guideline_docs/en_docs/text/AAFP-2004.pdf — lý do: binary/asset (.pdf)
[skip] research/guideline_docs/en_docs/text/AAFP-2012.pdf — lý do: binary/asset (.pdf)
[skip] research/guideline_docs/en_docs/text/AAFP-2019.pdf — lý do: binary/asset (.pdf)
[skip] research/guideline_docs/en_docs/text/BMJ-NICE-summary.pdf — lý do: binary/asset (.pdf)
[skip] research/guideline_docs/en_docs/text/CMAJ-2016-canada.pdf — lý do: binary/asset (.pdf)
[skip] research/guideline_docs/en_docs/text/EuroGuiDerm-2025-long.pdf — lý do: binary/asset (.pdf)
[skip] research/guideline_docs/en_docs/text/NICE-NG198-referral.pdf — lý do: binary/asset (.pdf)
[skip] research/guideline_docs/en_docs/text/NICE-NG198.pdf — lý do: binary/asset (.pdf)
[skip] research/guideline_docs/en_docs/text/Skin Health and Disease - 2023 - Corcoran - Systematic review of clinical practice guidelines for acne vulgaris published.pdf — lý do: binary/asset (.pdf)
[skip] research/guideline_docs/en_docs/text/The Journal of Dermatology - 2018 - Hayashi - Japanese Dermatological Association Guidelines  Guidelines for the treatment.pdf — lý do: binary/asset (.pdf)
[x] research/guideline_docs/en_docs/txt/AAFP-2004.txt — module: research — 207 LOC — sha256:7de6d604cc623b5d770789d5540cac4fbaa6e5f620b49bc00886ddefb89472e6 — symbols:0
[x] research/guideline_docs/en_docs/txt/AAFP-2012.txt — module: research — 227 LOC — sha256:d24c665aff6d06f4660d005cad75f373f29152794d088af6f0048c808af06279 — symbols:0
[x] research/guideline_docs/en_docs/txt/AAFP-2019.txt — module: research — 279 LOC — sha256:913fd85e99f2bbdf01b9e34092f511ddc9fcb022444e2d01e8ac2b8ce30c3a35 — symbols:0
[x] research/guideline_docs/en_docs/txt/BMJ-NICE-summary.txt — module: research — 229 LOC — sha256:7e8f3f00b9820038f5d49fed9be7d1851b993a9c7dc682e9d1871e9ce0b14675 — symbols:0
[x] research/guideline_docs/en_docs/txt/CMAJ-2016-canada.txt — module: research — 271 LOC — sha256:8c643e7a9e0a895561e5b1fec89f5b568fb7daebadf5b89f7ea875a10988fbd1 — symbols:0
[x] research/guideline_docs/en_docs/txt/EuroGuiDerm-2025-long.txt — module: research — 1598 LOC — sha256:d62849dad5e5c5038ef0505773d6318540c86af1e452f37cd69d75c1125ffd8e — symbols:0
[x] research/guideline_docs/en_docs/txt/NICE-NG198-referral.txt — module: research — 1024 LOC — sha256:051a8f81bd58b36e69b04315e587bc02a138e604559126fa012bf11283007d57 — symbols:0
[x] research/guideline_docs/en_docs/txt/NICE-NG198.txt — module: research — 1046 LOC — sha256:30f30b4e09e21a37b0d0a5673d394200393fb7dc54f73cbf0fd8932ffd85257e — symbols:0
[x] research/guideline_docs/en_docs/txt/Skin Health and Disease - 2023 - Corcoran - Systematic review of clinical practice guidelines for acne vulgaris published.txt — module: research — 323 LOC — sha256:d2abf001aba1afc78052510bd234ead6219666c7f016ea6cf7a573669aed5568 — symbols:0
[x] research/guideline_docs/en_docs/txt/The Journal of Dermatology - 2018 - Hayashi - Japanese Dermatological Association Guidelines  Guidelines for the treatment.txt — module: research — 1621 LOC — sha256:573413f786d52eb20b498d715cee7162bb1212a47451ae99632040da9262f0e0 — symbols:0
[x] research/guideline_docs/manifest.json — module: research — 137 LOC — sha256:4b27a71219fc66ae16d944f8ea294d1eef6ede320376b86cd90ee2ffac5bb17f — symbols:0
[x] research/guideline_docs/merge_guideline_chunks.py — module: research — 113 LOC — sha256:db755bb860d24fa9d1109d24adb09c81db1ec557c1df2382ebffd8724c2cc47c — symbols:7
[x] research/guideline_docs/pdf_to_text.py — module: research — 347 LOC — sha256:c68ce4f116c211f35900dd5a96cbd51ee84a8208b791bea89b873466bacf4e2d — symbols:17
[x] research/guideline_docs/reembed_guideline.py — module: research — 106 LOC — sha256:ec61858c889e1e94b407da151e8a022317451f47d58224d937e48ebaf813c3d7 — symbols:5
[x] research/guideline_docs/TAI-PDF.bat — module: research — 13 LOC — sha256:638e1155450f1ae849bc51f9a26d418086caec12ee88d55b9c0eecf74c17a822 — symbols:0
[skip] research/guideline_docs/vie_docs/scan/Quyết-định-4416-QĐ-BYT.pdf — lý do: binary/asset (.pdf)
[skip] research/guideline_docs/vie_docs/text/108-isotretinoin-azithro.pdf — lý do: binary/asset (.pdf)
[skip] research/guideline_docs/vie_docs/text/108-isotretinoin-vitD.pdf — lý do: binary/asset (.pdf)
[skip] research/guideline_docs/vie_docs/text/AnGiang-phac-do-da-lieu.pdf — lý do: binary/asset (.pdf)
[skip] research/guideline_docs/vie_docs/text/BacNinh-laser-seo-mun.pdf — lý do: binary/asset (.pdf)
[skip] research/guideline_docs/vie_docs/text/BYT-Da-lieu-2015.pdf — lý do: binary/asset (.pdf)
[skip] research/guideline_docs/vie_docs/text/CanTho-isotretinoin.pdf — lý do: binary/asset (.pdf)
[skip] research/guideline_docs/vie_docs/text/Hue-azithromycin-adapalene.pdf — lý do: binary/asset (.pdf)
[skip] research/guideline_docs/vie_docs/text/VJDV-dong-thuan-duoc-my-pham.pdf — lý do: binary/asset (.pdf)
[skip] research/guideline_docs/vie_docs/text/VJDV-isotretinoin-so-sanh.pdf — lý do: binary/asset (.pdf)
[skip] research/guideline_docs/vie_docs/text/VJDV-minocyclin.pdf — lý do: binary/asset (.pdf)
[skip] research/guideline_docs/vie_docs/text/YHocTPHCM-2017.pdf — lý do: binary/asset (.pdf)
[x] research/guideline_docs/vie_docs/txt/108-isotretinoin-azithro.txt — module: research — 174 LOC — sha256:8d0f7876336473d797878013478e34889d62961caac724244748a97fb5963759 — symbols:0
[x] research/guideline_docs/vie_docs/txt/108-isotretinoin-vitD.txt — module: research — 180 LOC — sha256:36f29147c8cacf8731f08e371ca5a22bf55e461b7de26450b50200ae50cdbecb — symbols:0
[x] research/guideline_docs/vie_docs/txt/AnGiang-phac-do-da-lieu.txt — module: research — 817 LOC — sha256:a083e27700e87d510d3140b3f9f12974060b92425f83f004f0547df57fe419f3 — symbols:0
[x] research/guideline_docs/vie_docs/txt/BacNinh-laser-seo-mun.txt — module: research — 900 LOC — sha256:0fd22d4681e54a41e96a3a78e1cc97b2d1b1b46f70c323e105ac072ceb23d405 — symbols:0
[x] research/guideline_docs/vie_docs/txt/BYT-Da-lieu-2015.txt — module: research — 7945 LOC — sha256:52d20b54270f54c71707339f0795ae5b137b7bc27b3a98e04577c353bbd9a0dd — symbols:0
[x] research/guideline_docs/vie_docs/txt/CanTho-isotretinoin.txt — module: research — 187 LOC — sha256:5d1c015143a310d0821139278c454a8dbeb9928e79f82afdd1303d23312f5bed — symbols:0
[x] research/guideline_docs/vie_docs/txt/Hue-azithromycin-adapalene.txt — module: research — 284 LOC — sha256:b5027df034259718e8557f0481064ed2b0ba25ce44fc3d419b313a283612d77b — symbols:0
[x] research/guideline_docs/vie_docs/txt/Quyết-định-4416-QĐ-BYT.txt — module: research — 12850 LOC — sha256:cd53e843f45a7dd5f699b08d6b40b7e38544beb1fbf94f0ab1ee3333580726a3 — symbols:0
[x] research/guideline_docs/vie_docs/txt/VJDV-dong-thuan-duoc-my-pham.txt — module: research — 160 LOC — sha256:71c18f126db4785d7627d569188627637c2d87aee625e8fbb6a797fb0b718859 — symbols:0
[x] research/guideline_docs/vie_docs/txt/VJDV-isotretinoin-so-sanh.txt — module: research — 263 LOC — sha256:0cac9a0b5dc77854dfc4f0726465cca2ea264efc4ed942de7ef5d9d15c461035 — symbols:0
[x] research/guideline_docs/vie_docs/txt/VJDV-minocyclin.txt — module: research — 227 LOC — sha256:83b391090b2fcbcbb512ab4889feb023025b97f102ed7eb2c66c62147964b95d — symbols:0
[x] research/guideline_docs/vie_docs/txt/YHocTPHCM-2017.txt — module: research — 357 LOC — sha256:35a56fc240906380ba6b47806c74f2ff37fc50fe8aeb458ad30ae5f1774895f6 — symbols:0
[skip] research/LLMData/acne_dataset.jsonl — lý do: data/runtime artifact (.jsonl)
[x] research/LLMData/chunk_qa/__init__.py — module: LLMData — 16 LOC — sha256:4ec66e99a174bafb06d960f16d52ae405f1d3279ddf7c3c3df3a7eb04015c3d2 — symbols:1
[x] research/LLMData/chunk_qa/config.py — module: LLMData — 170 LOC — sha256:1c8a258e2d443927959adde8fa39526fc05c089dd3af56235a28d5081daf1773 — symbols:10
[x] research/LLMData/chunk_qa/generator.py — module: LLMData — 545 LOC — sha256:6eb6aa4374f7dbdd7c4f795887fcd4fc0e48b34a77bd8b94e61de114da5e8983 — symbols:16
[x] research/LLMData/chunk_qa/loader.py — module: LLMData — 171 LOC — sha256:d9a72fcee7a2db8691cc33c65696fea75ae032bb1176e7095297f712e2fdddd3 — symbols:9
[x] research/LLMData/chunk_qa/main.py — module: LLMData — 631 LOC — sha256:d95ab2fab269d3f489c3f2281efafb92c98e127886d92eee16d3a107825fdddc — symbols:15
[x] research/LLMData/chunk_qa/rule_filter.py — module: LLMData — 416 LOC — sha256:820cb71b2854eb43023777de50ac6df5320530536a70fe2062a0c815fd1c81bf — symbols:25
[x] research/LLMData/chunk_qa/safety_cases.py — module: LLMData — 972 LOC — sha256:3b7fc85b44016eb985e74a5b6aa276dbdd9d647cb03c0ee1a3d2530f37c9344a — symbols:11
[x] research/LLMData/chunk_qa/writer.py — module: LLMData — 216 LOC — sha256:5f71275c02f48a2e0bbd02ad2c288b29d25479b50ee41a3b788b949e690a8c73 — symbols:12
[x] research/LLMData/clinical_case/__init__.py — module: LLMData — 14 LOC — sha256:fba14c6fc28862d6583fbab9d2a44312080479ca72b5f46d7c0073e8422b0a09 — symbols:2
[x] research/LLMData/clinical_case/generator.py — module: LLMData — 551 LOC — sha256:ad8484c06084ad5b98a6e2d6101c5aa06852d08aa18eaa4c037d8ab71740e1ea — symbols:8
[x] research/LLMData/clinical_case/main.py — module: LLMData — 67 LOC — sha256:e4592819bdfa35f392ab42a90f29308025f0612ea3f1d56be8a66de891d45a71 — symbols:3
[x] research/LLMData/clinical_case/schema.py — module: LLMData — 46 LOC — sha256:f8a975b228a02f3d5a718cd98a3ef75234c710c5c097a9e6d6ab988517c4b6b6 — symbols:3
[x] research/LLMData/clinical_case/validator.py — module: LLMData — 179 LOC — sha256:35e635fb2655ed62bae86221d0aba67c0228c93ce1e5b124021d2c665dfe8129 — symbols:15
[x] research/LLMData/injection_qa/__init__.py — module: LLMData — 14 LOC — sha256:bf156ba2d81e355ee770f9803a3fdc363456c2f88726a52fc1f6ae2c0cbb5203 — symbols:0
[x] research/LLMData/injection_qa/injection_cases.py — module: LLMData — 1013 LOC — sha256:1d03c9071a01586262f6792058658ef1f08e9deada93dab85bec516aea779ff0 — symbols:15
[x] research/LLMData/injection_qa/main.py — module: LLMData — 349 LOC — sha256:e5f4bacf4921416bace67b78826f6761d2873f55ff10abd301c51edf282898de — symbols:10
[x] research/LLMData/script.py — module: LLMData — 279 LOC — sha256:63a0a55159783b704680cc87673458234ddb82d6aa484dd07b1159b0867a42e5 — symbols:14
[x] research/notebooks/_cu/colab/Finetune.ipynb — module: research — 12469 LOC — sha256:53f42b100377084e202ded906c292a35114402bed06b2f0c8a4b5042df5a1387 — symbols:0
[x] research/notebooks/_cu/colab/Finetune3 (2).ipynb — module: research — 12737 LOC — sha256:6e0ac0174f5409c6041c90116837bc4045282dcaca9e5f1dd4bf8d269a010d86 — symbols:0
[x] research/notebooks/_cu/colab/finetunev2.ipynb — module: research — 12467 LOC — sha256:cce75d70f9d90779156af1995854671f76787438d476e3bbee26a3ef50bd9777 — symbols:0
[x] research/notebooks/_cu/colab/finetunev3 - Copy.ipynb — module: research — 12468 LOC — sha256:21c87d525ce45edc6989097a9cf56624dccde3be991171af176781f9e474e57c — symbols:0
[x] research/notebooks/_cu/colab/finetunev3_l4.ipynb — module: research — 12468 LOC — sha256:de4c430f76e27c54eb9c658177d862bb07d0e53573d565bf1605268cd050b782 — symbols:0
[x] research/notebooks/generator/finetune_role_qwen25_q4.ipynb — module: research — 9782 LOC — sha256:15383ae51f809ad7a22693cfd7649c312ea5732d52916074e3ff0050381a3ca6 — symbols:0
[x] research/notebooks/generatorv2/finetune_role_v2_qwen25_q4.DA_CHAY.ipynb — module: research — 16112 LOC — sha256:8eca92fa43793596c0bec53337d7f5b3742eef27a2cd260b75f9f661e8a5cbfa — symbols:0
[x] research/notebooks/generatorv2/finetune_role_v2_qwen25_q4.ipynb — module: research — 639 LOC — sha256:17fe3012cf7a7bce5a0dc71b90d52b5857a638cdc0dc583cf5ba251ed916a193 — symbols:0
[x] research/notebooks/generatorv2/finetune_role_v2_qwen25_T4.ipynb — module: research — 678 LOC — sha256:68025a251a1ab90eb367179205c30b545ff394ee79f041376afee2a63b155abd — symbols:0
[x] research/notebooks/generatorv2/GIAI_THICH_NOTEBOOK_V2.md — module: research — 482 LOC — sha256:fb854052fac6597016468d8de5d8dccb23a7e7037bc03a51a861158417a888ea — symbols:0
[x] research/notebooks/HYPERPARAMS_RATIONALE.md — module: research — 94 LOC — sha256:6ca14443c58387654246519f80e000580f40a39c2098267f95fc36ace6f07ad8 — symbols:0
[x] research/notebooks/HYPERPARAMS_RATIONALE_intake.md — module: research — 81 LOC — sha256:175ba594d7a29f57db6c0ed798ce7e90c0da07e8f24d03c3730a31dcd2764158 — symbols:0
[x] research/notebooks/intaker/finetune_intake_qwen25_3b_q4(colab).ipynb — module: research — 6596 LOC — sha256:5bb4706db8feccac8b5f420ab85915559dcc3e52f51da816fcd0f0e4a0c6199e — symbols:0
[x] research/notebooks/intaker/finetune_intake_qwen25_3b_q4.ipynb — module: research — 653 LOC — sha256:1318410796c9909f3940958b1f6e59d07c4a454187e658cd52d478d88600c3c7 — symbols:0
[x] research/notebooks/TRAINING_REPORT.md — module: research — 50 LOC — sha256:fe3dd1f150a1489185e082963680b810b570a747e2b40026c895b3804c93e924 — symbols:0
[x] research/README.md — module: research — 21 LOC — sha256:3d6d1d710fb4985f9918229fa3c69ccd7ce6e290e5a94c3a9a37439b6b23040a — symbols:0
[x] scripts/ab_template_prompt.ps1 — module: scripts — 111 LOC — sha256:6a4ed8a6a6e3625b85ce0b1326f6c57d6864be88d311d33626994dae8dd1ff81 — symbols:1
[x] scripts/build_hybrid_finetune_dataset.py — module: scripts — 107 LOC — sha256:8efaf972158a96091114df9ffb16e25709e319cf5636b6e031ee76c3de438a53 — symbols:5
[x] scripts/build_intent_dataset.py — module: scripts — 887 LOC — sha256:47cb24622a58cc9ba27fac7a63c0d8bff4a7f663e5d8f65bef731168455fb35b — symbols:34
[x] scripts/build_kb.py — module: scripts — 681 LOC — sha256:b194ce88c6d2b4797bc497bb31d8b5cbe90e16912fdfbcb1a50898ef25ac426a — symbols:26
[x] scripts/clean_acne_chat_response.py — module: scripts — 518 LOC — sha256:df7c6e79100f616b874ab9ac9bcb265a10ab28ddbd412e0fc6ef8213df24951c — symbols:32
[x] scripts/convert_acne_dataset.py — module: scripts — 184 LOC — sha256:4913ea2fbb0fc64ef5e9668c51e9b4452fafa90681d19f0833b939c8c1aca067 — symbols:9
[x] scripts/crawl_all.py — module: scripts — 387 LOC — sha256:7d393c6683ac30008502fe882cf063432b1b676a6bbc557e3b6b943676db2525 — symbols:14
[x] scripts/crawl_official_guidelines.py — module: scripts — 298 LOC — sha256:d572fd2ee2cd30fd54a30dac5e482da9196201bdb1997ebdcdffd5857c75839c — symbols:13
[x] scripts/KB.ps1 — module: scripts — 160 LOC — sha256:d63f5f86df874a3aa43a78262948a71ecc9de63e60462b5d6073725807b5adec — symbols:3
[x] scripts/merge_finetune_datasets.py — module: scripts — 87 LOC — sha256:ac5873fee9e4e7ac82e76192358d834ee5f0336c79ca34b8805a59aaa6cfba13 — symbols:4
[x] scripts/prepare_docker_bundle.ps1 — module: scripts — 127 LOC — sha256:d25e2694e28b714de50cc08f5c809a1e303a0a6a078a5ec47a1cbf53f70750de — symbols:1
[x] scripts/RUN.ps1 — module: scripts — 170 LOC — sha256:9dbc694c1a127b5e8ab39b6251156b0d95330652043c268d69dcca8d621e688b — symbols:4
[x] scripts/run_all.sh — module: scripts — 55 LOC — sha256:31df37b3f981857ba83aee74f708faf3e378e41a56bb184f73feac150109a65f — symbols:1
[x] scripts/runpod.ps1 — module: scripts — 162 LOC — sha256:466a2e2a86cb126559f4897c94c33a6fc3e95a12648ec692f5f4c2b70f075405 — symbols:3
[x] scripts/visualize/output/chromadb_map.html — module: scripts — 3888 LOC — sha256:46cd259484db08d965495ffdfae8ddcd94ca162ccbc7db8a2f46d346410c027b — symbols:0
[skip] scripts/visualize/output/chromadb_map.png — lý do: binary/asset (.png)
[x] scripts/visualize/visualize_chromadb.py — module: scripts — 208 LOC — sha256:8baa1a25b012ebd86755930314e7f6733285331e844f777e3a5f2ab68b244032 — symbols:12
[x] src/acne_llm/__init__.py — module: src.__init__ — 2 LOC — sha256:a6b89513c28ed35f99950f1dc6e0729ac540866b3306c89b832a172bfc122f7d — symbols:1
[x] src/acne_llm/api/__init__.py — module: src.api — 0 LOC — sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 — symbols:0
[x] src/acne_llm/api/app.py — module: src.api — 69 LOC — sha256:18d9be566f84e126175fd3cad593e011035896da8725557dc14ff839fd867488 — symbols:6
[x] src/acne_llm/api/deps.py — module: src.api — 34 LOC — sha256:62848967b242764bf42f3c857ce9d60a1bffcc94eeac897cf9309e72107541b4 — symbols:2
[x] src/acne_llm/api/observability.py — module: src.api — 143 LOC — sha256:c74f73caff2416217909fdeaf34822910b12e557d8ee2ae54d3ca4c8ef64221c — symbols:12
[x] src/acne_llm/api/routes/__init__.py — module: src.api — 0 LOC — sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 — symbols:0
[x] src/acne_llm/api/routes/admin.py — module: src.api — 66 LOC — sha256:46f622c9cf5aa484b8590a545b3a9987c9417301a483da931b9589f322d1e723 — symbols:5
[x] src/acne_llm/api/routes/chat.py — module: src.api — 236 LOC — sha256:eb7621a62399ab243e6a0ad48048c0842793d9d6d2a0ccd9dcac987761f60f43 — symbols:6
[x] src/acne_llm/api/routes/health.py — module: src.api — 28 LOC — sha256:281efd2ac8f1761945272088ee12214fdfbeac37168692d5779cc3a973b4e32f — symbols:3
[x] src/acne_llm/api/routes/kb.py — module: src.api — 115 LOC — sha256:5e9949096f5ff6968dd4016806ef57d3e65141e2c0c7bf55c305fdfc724ac476 — symbols:8
[x] src/acne_llm/api/routes/metrics.py — module: src.api — 19 LOC — sha256:20a0fcb4ed7f8618e8e6729291c80a0ff74bde9d591ad3c413b97d1bebff3e9f — symbols:2
[x] src/acne_llm/api/templates/partials/advise_card.html — module: src.api — 61 LOC — sha256:5158e9740008f2a5dac7dc2af12be265d9ea8881acfe86628528b0527cf673e5 — symbols:0
[x] src/acne_llm/api/templates/partials/search_results.html — module: src.api — 22 LOC — sha256:5e82da8db36c23455ed505fe51c8e5723d8fc8026004fe8e54573b35000d43c2 — symbols:0
[x] src/acne_llm/cache.py — module: src.cache — 141 LOC — sha256:89cd5a248fd3f508e02de0da6269d73b52b6c838570d935a3e3c05b44241175d — symbols:10
[x] src/acne_llm/chat/__init__.py — module: src.chat — 6 LOC — sha256:88226d3925921c582001f09cfef71c1c04d3f1028522afb563248185420c019c — symbols:1
[x] src/acne_llm/chat/_intake_parse.py — module: src.chat — 394 LOC — sha256:550859a5554726df0ce6715fc2e4202312f815c081af384545e90773388adbf5 — symbols:28
[x] src/acne_llm/chat/_intent_patch.py — module: src.chat — 88 LOC — sha256:194b96948b434f40a9249f482c9991a7ba3a418a68e5ffa17d682bb51bb214c2 — symbols:5
[x] src/acne_llm/chat/_retrieval.py — module: src.chat — 392 LOC — sha256:c19c8f451dbcba0b59d3a0c1386fe06e5c6ac176ad138ec4fdf39451d81799c9 — symbols:15
[x] src/acne_llm/chat/_safety.py — module: src.chat — 371 LOC — sha256:dfb71b0fc8de2163019b0155f31e2ca6bce9647fac7f1685fa13ab57b17dbd5d — symbols:24
[x] src/acne_llm/chat/confidence_hint.py — module: src.chat — 124 LOC — sha256:d6ede998c42df45c7cfdb8bc47551381dc0443af6ab51282882ebb414e5feb45 — symbols:5
[x] src/acne_llm/chat/intake.py — module: src.chat — 854 LOC — sha256:e2bb513e4704c9fb8f2af47b09acc895f5e610c13f02dada80e670b958815901 — symbols:15
[x] src/acne_llm/chat/orchestrator.py — module: src.chat — 187 LOC — sha256:d93a95a7fd40be4d91dc71220a93fdc8b6564773b4b758aabc3dcae9c8f018e9 — symbols:5
[x] src/acne_llm/chat/preprocess.py — module: src.chat — 78 LOC — sha256:1494870413c9cc7cbf5927f144fec76ce300f0c980eb5bc9b7c01c274d8d70d2 — symbols:10
[x] src/acne_llm/chat/routing/__init__.py — module: src.chat.routing — 10 LOC — sha256:eb8be3f62ad3c14e5b07c172c2c25f046b9b951cf739113b8f60e42826d4eea0 — symbols:0
[x] src/acne_llm/chat/routing/intent_router.py — module: src.chat.routing — 669 LOC — sha256:dfae7455c97131c1f3f69b0a75334baf217fd17ad3c6c16ee79aac2207545de0 — symbols:33
[x] src/acne_llm/chat/routing/llm_extractor.py — module: src.chat.routing — 103 LOC — sha256:e17993f2c9aa53c73f83b23e98f037ec50bb7f2faa0dad485ba8d8ac77cebf0e — symbols:8
[x] src/acne_llm/chat/routing/llm_router.py — module: src.chat.routing — 162 LOC — sha256:2d33b1ebe41b153231b3ecb93dbb28ffd6eb9a31edc7fbea875456003cd84eb0 — symbols:15
[x] src/acne_llm/chat/routing/rule_extractor.py — module: src.chat.routing — 406 LOC — sha256:fc68b0f8cddebba5e875df3f84d813aa6b0ff334bcfbe077b079d7a02b484cd2 — symbols:21
[x] src/acne_llm/chat/routing/rule_normalizer.py — module: src.chat.routing — 1975 LOC — sha256:dd2223554f3bd9c3953cbca506e0a8ec4f04ad3031a12c71f0b09bf09c0390af — symbols:66
[x] src/acne_llm/chat/routing/semantic_router.py — module: src.chat.routing — 393 LOC — sha256:8ab267b69d8d63b7e412b6584ec67fb3f999a515d397554bdbe792cc40f152ed — symbols:20
[x] src/acne_llm/chat/runtime.py — module: src.chat — 345 LOC — sha256:1b52824f75db1645cbd98e3605f043e81fcd4ee5d2f54fd59dea400d3438d5e9 — symbols:4
[x] src/acne_llm/chat/session/__init__.py — module: src.chat.session — 46 LOC — sha256:97264d94e7d053fbdfca3dc6000db15a53e703de693a166cbb25485c7ecd7b2a — symbols:1
[x] src/acne_llm/chat/session/fold.py — module: src.chat.session — 338 LOC — sha256:ac078b5bc8c8b6e98a90a20a3f4d682756fa018a0d3d2b371878875d8f690c7f — symbols:7
[x] src/acne_llm/chat/session/memory.py — module: src.chat.session — 195 LOC — sha256:2ac902351ac7849d0c9b1ab5b08d887932df06124ae09decce8b9616acbae4c7 — symbols:15
[x] src/acne_llm/chat/session/models.py — module: src.chat.session — 75 LOC — sha256:a8c8ac44a6803e15660a5e4225ed4bfae04c7022e8be8d9833f2fb686b3d4fcf — symbols:10
[x] src/acne_llm/chat/session/view.py — module: src.chat.session — 161 LOC — sha256:0706153d03486607560c66776a87fbddbded406c53b7cc422430461c0a67aad6 — symbols:6
[x] src/acne_llm/chat/unified_intake.py — module: src.chat — 228 LOC — sha256:6f2a77cdb79f8758e0b6039e406f8e159d43d9bbe4d8767d96acdacd50c8f398 — symbols:17
[x] src/acne_llm/cli.py — module: src.cli — 51 LOC — sha256:1dc057a7f3ba0ee1146524d604b2208d87d517eea009346fc5b1f87b35dfd63f — symbols:4
[x] src/acne_llm/config.py — module: src.config — 288 LOC — sha256:132137c3e6ef953f7822b5efb2c7c224f2bf4bfbaf55bcc9b8735a6f57111b8c — symbols:8
[x] src/acne_llm/crawler/__init__.py — module: src.crawler — 0 LOC — sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 — symbols:0
[x] src/acne_llm/crawler/checkpoint.py — module: src.crawler — 225 LOC — sha256:90972af53dcc4b10185407a5bd263dd38716a7daca245341f3f86ba2777b409b — symbols:15
[x] src/acne_llm/crawler/dedup.py — module: src.crawler — 135 LOC — sha256:14989c3102e6501364c333898585aa621cee7ae2b89cd5be717fa968b7a02fbd — symbols:10
[x] src/acne_llm/crawler/discovery.py — module: src.crawler — 586 LOC — sha256:28a9b168e9726e97692166274b4dd66bade14861facef989e58c9cfd45ae1135 — symbols:16
[x] src/acne_llm/crawler/extractor.py — module: src.crawler — 77 LOC — sha256:b7a1fb1d85af9b5c9b630e547e20e28000a97b79521da3f1fd365eaf9931cc3c — symbols:1
[x] src/acne_llm/crawler/fetcher.py — module: src.crawler — 129 LOC — sha256:50df7930d4b307a44b926cd9060f7c442d27a07c0033628b36b5bfb57ce65620 — symbols:12
[x] src/acne_llm/crawler/normalizer.py — module: src.crawler — 12 LOC — sha256:801c6852a32486741ea243491b5579c7ff6b6ad9b12545fb61a8a288da118988 — symbols:1
[x] src/acne_llm/crawler/playwright_fetcher.py — module: src.crawler — 331 LOC — sha256:0846c9e56547485aee2a6507f20f1b5c14b0da05543e24415cbf0380f0cd85ac — symbols:13
[x] src/acne_llm/crawler/quality_filter.py — module: src.crawler — 325 LOC — sha256:59a7ffc545033a397cb33dc9709935648879665bc2121293efdcf99dbc911060 — symbols:15
[x] src/acne_llm/crawler/sources/__init__.py — module: src.crawler — 0 LOC — sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 — symbols:0
[x] src/acne_llm/crawler/sources/generic_html.py — module: src.crawler — 348 LOC — sha256:fac158ec307df2d7e9fc1a20cd17034bf5177ee36a54eb9f13b289e573789f28 — symbols:17
[x] src/acne_llm/crawler/sources/pubmed.py — module: src.crawler — 94 LOC — sha256:b6e89fcd89a64f8e73d90e6939a699dc60f96be495d3fa8af3957fc98e2b8621 — symbols:7
[x] src/acne_llm/crawler/stats.py — module: src.crawler — 176 LOC — sha256:bfd5099a57d3e2436e62184a9c93e606ddb55a7e03dfb0c2a8b398ddc1971b27 — symbols:15
[x] src/acne_llm/db/__init__.py — module: src.db — 5 LOC — sha256:b70cb278fd16b28a3d557a60859f3deed42dbb3d8a70f05fa2dea3c8139ca2b3 — symbols:1
[x] src/acne_llm/db/audit.py — module: src.db — 175 LOC — sha256:58b73101f133db7059806995228bc26e6f81ce0f9b7865908b6eee0ee4c7c820 — symbols:9
[x] src/acne_llm/db/base.py — module: src.db — 100 LOC — sha256:78ba9c235e1e6c01d7232ab2b35f5fc40755fb264c57182e5c51c3e075247122 — symbols:10
[x] src/acne_llm/db/session_store.py — module: src.db — 322 LOC — sha256:75229a4bed25e61693e44b6016a16ece58efb8fe1a7d8646c76c436026555841 — symbols:22
[x] src/acne_llm/di.py — module: src.di — 344 LOC — sha256:ee60052b0900d8b65b6f955c896295693dbdf96232ca4d866df6ae77fe43af7f — symbols:5
[x] src/acne_llm/guardrails/__init__.py — module: src.guardrails — 0 LOC — sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 — symbols:0
[x] src/acne_llm/guardrails/pii.py — module: src.guardrails — 46 LOC — sha256:b59a77d1ee3b355c5835a2d0e5852ecfe6dfe869ef330a14f4af781b9619389e — symbols:3
[x] src/acne_llm/guardrails/runner.py — module: src.guardrails — 209 LOC — sha256:7a8601f2f916b83309a509964801815a46f05e5c68eda32b2b6d6539ef541ef0 — symbols:4
[x] src/acne_llm/llm/__init__.py — module: src.llm — 0 LOC — sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 — symbols:0
[x] src/acne_llm/llm/language.py — module: src.llm — 30 LOC — sha256:79cd4223d870efde79f80e266c96cfa4933904cabaf3ff50e3bc42c5e044f5ef — symbols:2
[x] src/acne_llm/llm/ollama_backend.py — module: src.llm — 251 LOC — sha256:386d7229403b490bd5cc3a935511924c5b61dc07e50b41cd9f0c600f4e990419 — symbols:16
[x] src/acne_llm/llm/prompt_builder.py — module: src.llm — 253 LOC — sha256:7167c165bae407b7f90318f1f223e66fa560ce3376e1636c4e01c4f5ff7e8fd7 — symbols:10
[x] src/acne_llm/rag/__init__.py — module: src.rag — 0 LOC — sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 — symbols:0
[x] src/acne_llm/rag/chunker.py — module: src.rag — 234 LOC — sha256:cb647d5c8f6639966b03360baf4991b8acddab91c5c23ddeecbd3e47b2f5bf0f — symbols:20
[x] src/acne_llm/rag/cleaning.py — module: src.rag — 102 LOC — sha256:8f230e76e4460b5226a8953ef82869e40e248a898c18520821e2c5452f1c5216 — symbols:6
[x] src/acne_llm/rag/embedder.py — module: src.rag — 70 LOC — sha256:bccf9a0fb3ca285a5ec170436aa0a128d81b906115ec9794006c2be65d5fef83 — symbols:7
[x] src/acne_llm/rag/reranker.py — module: src.rag — 160 LOC — sha256:aed136809a540b64de46d0de2c76f32ad68f41e391b487c99621bde8b9b7d2dd — symbols:7
[x] src/acne_llm/rag/retriever.py — module: src.rag — 326 LOC — sha256:c5e36cfdb265271814292b5fd805bdfecece75b296a22ae2f46e9d587fd938ff — symbols:14
[x] src/acne_llm/rag/sparse.py — module: src.rag — 117 LOC — sha256:5f175b7f086e1e47b9407a1b394b0c9de0b84f6a85fba6cfb131c23bb14da5de — symbols:11
[x] src/acne_llm/rag/vectorstore.py — module: src.rag — 150 LOC — sha256:0773dd010dca1e2a2614a2648388fe394ae005f582488ee085266d9953c1d65b — symbols:8
[x] src/acne_llm/schemas/__init__.py — module: src.schemas — 21 LOC — sha256:49721644283ac622d3cfdc1306d66eeb9e9b05e26bef2836327902aba24cceef — symbols:1
[x] src/acne_llm/schemas/clinical.py — module: src.schemas — 75 LOC — sha256:2208a687e847882775ba6449312a826d5b2caaa694b1a4ae6a11c777688cc1d9 — symbols:4
[x] src/acne_llm/schemas/core.py — module: src.schemas — 156 LOC — sha256:90d50b22f5af22e398f943dbf52a8075e8d3c848aa422832185ed898e12a8133 — symbols:10
[x] src/acne_llm/schemas/extraction.py — module: src.schemas — 150 LOC — sha256:5f731797326e090786553ee5fa560ea7ad1dfabc5bbdc0024f5e21d2a6bc2245 — symbols:16
[x] src/acne_llm/schemas/kb.py — module: src.schemas — 195 LOC — sha256:042ebc6b8edeb38c876e5ee905bb256e29a9c96125759c88b43bfd007c2cb775 — symbols:11
[x] src/acne_llm/utils/__init__.py — module: src.utils — 3 LOC — sha256:a97934b47fa13182c977aeed349125132b6eb92769ed81cba845b9433ad15720 — symbols:1
[x] src/acne_llm/utils/chunk_filter.py — module: src.utils — 182 LOC — sha256:8397fed3e86b623717ff5bb815deb7a28ccc59228e4dd5302bd47b6b5a545d92 — symbols:9
[x] src/acne_llm/utils/fuzzy_match.py — module: src.utils — 90 LOC — sha256:64e408f36578fda1fc182677849d3ecf33eeae7b76f294281f370ba8d69bef9b — symbols:7
[x] src/acne_llm/utils/hashing.py — module: src.utils — 9 LOC — sha256:bcc8a68e3aa4df7c857fcfaa1ca94155fb238bde6edf299d34c2079f217fdaa5 — symbols:2
[x] src/acne_llm/utils/logging.py — module: src.utils — 229 LOC — sha256:c06ed4f72217ea40f0ba8d685db96d01d9522c4695f33f38b12790183942d819 — symbols:7
[x] src/acne_llm/utils/retrieval_query.py — module: src.utils — 126 LOC — sha256:0d5ef7d7734015bf1ade194a93955ea375c0fce0639400e99714567525ff6051 — symbols:10
[x] src/acne_llm/utils/text_cleaning.py — module: src.utils — 89 LOC — sha256:89d8a0035d5b64092e8d2809738387c3b602de6ec6d829ca4d94691750afd043 — symbols:5
[x] src/acne_llm/utils/timer.py — module: src.utils — 12 LOC — sha256:60c7d169d4fb8eb1bf12ee1834177e04905e543d9f777551e5a2f1944be3e928 — symbols:1
[x] tasks.sh — module: tasks — 458 LOC — sha256:e0f3b8a2d4f9f4097e55b005317578cde0372944dcf49b4a1a547801dba7fc40 — symbols:9
[x] tests/chat/test_guideline_slot.py — module: tests — 106 LOC — sha256:259dea442d2a0c8f4a640bbfa6ed21431158102d5f1fe6d89b5d7037e07ea928 — symbols:10
[x] tests/chat/test_unified_intake.py — module: tests — 552 LOC — sha256:fd320da5867e25b7b5297b5d0c5c2f29e96345583fc5aa8aa6550bd5d40b7c54 — symbols:36
[x] tests/conftest.py — module: tests — 6 LOC — sha256:f5a184caecb1af5954e9efbb9cf9b3775027150af3352061e9fcc630b23c7f87 — symbols:1
[x] tests/test_admin_auth.py — module: tests — 52 LOC — sha256:5aa79aff22b7e694de2cbee5980d985b366be38d7b7cc3395c75311e9ff6f3a0 — symbols:7
[x] tests/test_api.py — module: tests — 67 LOC — sha256:6fe26692e586108c88f08918eb23bc1efed4d450894d78d246bba5c2e81efd9a — symbols:5
[x] tests/test_audit.py — module: tests — 54 LOC — sha256:dc926c739d526e079be34f1609347e9c398a5793523437625fee372cb77cde50 — symbols:2
[x] tests/test_chat_normalizer.py — module: tests — 212 LOC — sha256:8f781677ac50dd73337542ce2e39fe6d1e125c12042d9998b19e9c60270601f4 — symbols:19
[x] tests/test_chat_stream.py — module: tests — 578 LOC — sha256:c90d4a52b2356784595de58bc43eaa174ab8026104a5d535b8e062e87fa53d32 — symbols:42
[x] tests/test_chunk_filter_relevance.py — module: tests — 69 LOC — sha256:61ead94970a405acfcda9bb65e79c473bb4700c3c0563c0effbbf6ce82173166 — symbols:5
[x] tests/test_chunk_qa_clinical_factory.py — module: tests — 168 LOC — sha256:ded3dcafdded7e13ba4c0a70caa0bab286341f2e751b56014cac26d7ee6680ac — symbols:8
[x] tests/test_chunker.py — module: tests — 28 LOC — sha256:47b3b9559497d86fa61579c768ef5795b9334a663baefccacbf7fb085e2d6986 — symbols:4
[x] tests/test_cleaning.py — module: tests — 26 LOC — sha256:92f120fdc32ea561f21d65ad8a625120542481bd3169283173ccc15d37dab36a — symbols:4
[x] tests/test_clinical_dataset_validator.py — module: tests — 94 LOC — sha256:e38e6752e7f1880d153c3b346bd36e19b7246adae8ee9bcc1748b023837bb831 — symbols:6
[x] tests/test_clinical_planner.py — module: tests — 15 LOC — sha256:532d1801089dcc674a5dc1ce4ee06462955574f2488a50c5d89173e1ca263252 — symbols:2
[x] tests/test_confidence_behavior.py — module: tests — 60 LOC — sha256:28de2b5d9688a143e056c420590cc1fcd85d3a1ad95d336add7fe9604a8fdd24 — symbols:6
[x] tests/test_dedup.py — module: tests — 17 LOC — sha256:75c505b28c77b11177ce7369ff2bd6687bb3cbf966000b9c77c11220a5a708ac — symbols:2
[x] tests/test_env_keys.py — module: tests — 65 LOC — sha256:e5f87fd8f80ce312b2181bee9e1b942cd3ccffe5b274c4735d8a09af30e54d30 — symbols:5
[x] tests/test_extraction_confidence.py — module: tests — 90 LOC — sha256:29b59d6bfe5be09f4cd456271ded9e39db0eca98b5db0c1cb2a275b69b3a3a9d — symbols:12
[x] tests/test_extraction_fieldresult.py — module: tests — 95 LOC — sha256:c7a776e4281a956a98bdeddd43cb3e503bdd3e9009c75754edc3002b71a22344 — symbols:13
[x] tests/test_extraction_negation.py — module: tests — 67 LOC — sha256:0e02aa798c60f820bab2aa9684839cdfebcdb7c7f4ba4dd8fdb6595e238983e2 — symbols:8
[x] tests/test_guardrails.py — module: tests — 105 LOC — sha256:c912f461284f10e8cafbc51607f51a601db3553ec971ef70044239f1ba83b3f0 — symbols:11
[x] tests/test_intake.py — module: tests — 609 LOC — sha256:20b1d85da58acf1e4111fe5a97196d029b63206d8e934998ccfbbe921b54064c — symbols:43
[x] tests/test_intent_routing.py — module: tests — 231 LOC — sha256:427640c00ce8130fdd3422a85a51933bd9c2a3955e7b715c09faa825c1eaa3da — symbols:31
[x] tests/test_llm_extractor.py — module: tests — 382 LOC — sha256:102e9f6dd6b67e301e487acfaef9b20c113f10f86d109fa8499006eb2d19fdbb — symbols:23
[x] tests/test_llm_router.py — module: tests — 158 LOC — sha256:5a87b524f4cb004f116d77c1a23023eb353bccb6354dd4c4a1a510a73e4e23d7 — symbols:13
[x] tests/test_medication_gates.py — module: tests — 95 LOC — sha256:315aa55d4adf25bc2e9af9f751f0035536da646ea0482fe1f9804f32400e1622 — symbols:12
[x] tests/test_normalizer_regression.py — module: tests — 469 LOC — sha256:6785b123d081a630d3d77cad21c1dfe55e978f69f5d2f00272ac389e66509be9 — symbols:83
[x] tests/test_ollama_backend.py — module: tests — 103 LOC — sha256:db49563d5684c3c587cbf824ecaa7207b36104e54e4e93cac4e0592be5d37288 — symbols:9
[x] tests/test_prompt_builder.py — module: tests — 323 LOC — sha256:a5a80ceae1b4b825f5a92e9587633054b6bb24ad889754e1e73eaf3380e1fabf — symbols:20
[x] tests/test_prose_only_contract.py — module: tests — 25 LOC — sha256:749fd5ea70e66dd5f594282a73982090e1f9efdbc6c9ae9cbf8907aef4d50126 — symbols:4
[x] tests/test_quality_filter.py — module: tests — 122 LOC — sha256:a51234d18ffcc1967c9ad722fc9e45f5ddfbf6aae65d024ce3fee009a77a7ddc — symbols:13
[x] tests/test_refusal_fallback.py — module: tests — 60 LOC — sha256:b506597792fcf13396f8d126c54a4e5cc58b7db72e05b6ea15a19236b05dcc4d — symbols:8
[x] tests/test_reranker.py — module: tests — 32 LOC — sha256:ed69063584330488093d876f6c3ff529cab0b3b7647443747d7cb7f91ef2ebb8 — symbols:4
[x] tests/test_retrieval_merge.py — module: tests — 34 LOC — sha256:f8ca4a09177c86bc2ecb651aad886f06fb95c461811235f7b8f6c0829b38f39f — symbols:3
[x] tests/test_retrieval_query.py — module: tests — 33 LOC — sha256:15e5890fd997c376cf1a9dcc6482967163ec452a046eaa514d7262ef0f94f56e — symbols:3
[x] tests/test_retriever.py — module: tests — 120 LOC — sha256:3b2acc754ae8ad2c7e39959bda15233091b39f7a89c4aa6a5966a1a5c67adab6 — symbols:21
[x] tests/test_safety_dose_rule.py — module: tests — 48 LOC — sha256:dfc8c26b1eea157a3404f991e277a10eaff758c8f332b99d0b250d56e7dcd661 — symbols:7
[x] tests/test_schemas.py — module: tests — 73 LOC — sha256:f6e5cc5d2c8790e75ad2356d33854fdc67686ab8eb773be37cd3d9f41bc792bc — symbols:6
[x] tests/test_semantic_router.py — module: tests — 161 LOC — sha256:a7b551c99e9d1c955e113b39c9a96b8513c2f5ce69c812312544ce4b78e1b36a — symbols:12
[x] tests/test_session.py — module: tests — 372 LOC — sha256:2e367755afbf8ced5d19f270f61eb0a556459eefdb684745ead16a6f0030ba04 — symbols:54
[x] tests/test_session_fold_branches.py — module: tests — 219 LOC — sha256:4d1bd59bb8b3807629b86e8678541d43dd51be4899ae1bc888a2011924a6bde4 — symbols:14
[x] tests/test_session_package_integrity.py — module: tests — 74 LOC — sha256:fd4447baeb13c890d05919f30a9e268040e6017a992e73e688490809b6e24d4f — symbols:7
[x] tests/test_settings.py — module: tests — 53 LOC — sha256:719735ea129a0a2c4c173ae205d1e495eb499ad762a873f30ece6baad18b4ca3 — symbols:3
[x] tests/test_sparse_bm25.py — module: tests — 34 LOC — sha256:4cf6fe28b1d0e052ec2101cfccd55b47a08ac71b42cb325360724e1435c2c72d — symbols:3
[x] tests/test_sqlite_session_store.py — module: tests — 116 LOC — sha256:fcacf52368421f083fdf4a244af6c12371fdf8b084ccb35c14cafe865f5f8f73 — symbols:9
[x] tests/test_stream_safety.py — module: tests — 85 LOC — sha256:62850beef53b539d6876909b252547c3a75390b37f23975a7a748a8d184c8198 — symbols:9
[skip] uv.lock — lý do: generated dependency/build lock artifact

## MODULE COUNTS

- Dockerfile: 1 file captured
- LLMData: 17 file captured
- README: 1 file captured
- config: 9 file captured
- data: 5 file captured
- datagen.FINETUNE_DATAGEN_PLAN: 1 file captured
- datagen.HANDOFF: 1 file captured
- datagen.RUN: 1 file captured
- datagen.UNIFIED_INTAKE_DATAGEN_SPEC: 1 file captured
- datagen.__init__: 1 file captured
- datagen.config: 1 file captured
- datagen.contamination: 1 file captured
- datagen.gates: 1 file captured
- datagen.gen_role_dataset: 1 file captured
- datagen.generator: 1 file captured
- datagen.intake_json_system_prompt: 1 file captured
- datagen.intakedata: 23 file captured
- datagen.main: 1 file captured
- datagen.output: 5 file captured
- datagen.render_context: 1 file captured
- datagen.report_stats: 1 file captured
- datagen.role_style_guide: 1 file captured
- datagen.role_taxonomy: 1 file captured
- datagen.roledata: 42 file captured
- datagen.roledatav2: 40 file captured
- datagen.test_gates: 1 file captured
- datagen.test_pipeline_contracts: 1 file captured
- datagen.writer: 1 file captured
- docker: 1 file captured
- docker-compose: 2 file captured
- docs: 68 file captured
- eval.METRIC_EVIDENCE: 1 file captured
- eval.README: 1 file captured
- eval.RERUN_DEEPSEEK: 1 file captured
- eval.WIKI: 1 file captured
- eval.__init__: 1 file captured
- eval.adapters: 2 file captured
- eval.common: 1 file captured
- eval.configs: 1 file captured
- eval.datasets: 13 file captured
- eval.e2e: 1 file captured
- eval.eval_context: 1 file captured
- eval.full_evaluation: 1 file captured
- eval.judges: 10 file captured
- eval.metrics: 5 file captured
- eval.reports: 48 file captured
- eval.runners: 5 file captured
- eval.severity: 1 file captured
- eval.tests: 15 file captured
- eval.trace: 1 file captured
- evaluation: 1 file captured
- frontend: 22 file captured
- guideline_docs: 1 file captured
- pyproject: 1 file captured
- requirements: 1 file captured
- requirements-dev: 1 file captured
- research: 58 file captured
- root: 5 file captured
- scripts: 16 file captured
- src.__init__: 1 file captured
- src.api: 12 file captured
- src.cache: 1 file captured
- src.chat: 11 file captured
- src.chat.routing: 7 file captured
- src.chat.session: 5 file captured
- src.cli: 1 file captured
- src.config: 1 file captured
- src.crawler: 13 file captured
- src.db: 4 file captured
- src.di: 1 file captured
- src.guardrails: 3 file captured
- src.llm: 4 file captured
- src.rag: 8 file captured
- src.schemas: 5 file captured
- src.utils: 8 file captured
- tasks: 1 file captured
- tests: 46 file captured
