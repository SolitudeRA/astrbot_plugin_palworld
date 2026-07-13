# 质量更新与 bug 修复(quality-pass)清单

> 来源:2026-07-13 全库审查(6 视角 finder + 逐发现对抗验证,36 agent),21 条确认 / 9 条驳倒。
> 分支 `fix/quality-pass`。逐组修复+测试+提交,最后整分支终审。

## Group A — 采集链路健壮性

- [ ] **A1[高危]** scheduler._loop 只吞 CancelledError,任一 ingest 异常永久杀死该端点采集(`scheduler.py:90`)→ while 体包 try/except Exception 记日志 continue
- [ ] **A2[重要]** resp.data 非 Mapping(数组/标量)时 normalize 抛异常(`normalizer.py:20` 一类入口)→ ingest 入口守卫 isinstance Mapping,否则记 info 跳过
- [ ] **A3[次要]** max_concurrency 信号量创建后从未 acquire(`locks.py:13`/scheduler)→ fetch+on_response 真正包进 semaphore

## Group B — 时间口径统一

- [ ] **B1[重要]** 今日时长榜跨午夜整段计入虚高(`query_service.py:362`)→ 按 [start,end)∩[joined_at,left_at/now) 交叠秒数累加
- [ ] **B2[重要]** status「今日最高」是滚动 24h 非自然日(`query_service.py:102`)→ 改用 day_bounds start
- [ ] **B3[次要]** events(today_only) 忽略 per-server tz(`query_service.py:135`)→ 统一走 day_bounds
- [ ] **B4[次要]** 日报 list_events limit=1000 DESC 截断早段事件(`report_service.py:86`)→ 窗口内全量拉取(分页循环)
- [ ] **B5[次要]** 等级榜确定性:ORDER BY 补第三键 player_key ASC + 钉序测试(`sqlite_repository.py:387`)

## Group C — 隐私收敛(与 B 同文件)

- [ ] **C1[重要]** 等级榜排除者不占 seen 名额,同名另一 key 补位泄露(`query_service.py:378`)→ 按 latest_name 归组,组内任一 key 被排除即整组剔除
- [ ] **C2[次要]** 时长榜同名多 key 未归并,同源泄露面(`query_service.py:363`)→ 按 latest_name 归并 + 排除并集判定

## Group D — 健壮性(盐/配置/清理)

- [ ] **D1[重要]** 盐文件非原子写,崩溃留 0 字节→静默空盐弱化 HMAC(`salt.py:19`)→ 临时文件+os.replace 原子写;读回校验 len==32,损坏则重建并告警
- [ ] **D2[次要]** parse_config 数值字段畸形值炸启动(`config.py:202`)→ try/except 兜底默认值降级
- [ ] **D3[次要]** players 孤儿清理缺失(spec §6)→ prune 并入 DELETE player_bindings/hidden_players WHERE world_id 孤儿

## Group E — 重载竞态

- [ ] **E1[高危→重要]** 在途命令/状态查询与旧容器 stop() 竞态崩溃(`main.py:271`)→ 在途计数器+quiescence:命令/网页读入口进出计数,_apply_and_restart 在 stop 前带超时等待计数归零

## Group F — 前端

- [ ] **F1[高危]** 新行保存后 __row_id 不刷新,再编辑留空密码被当新行空密码**静默清空已存密码**(`ServerCard.vue`)→ 后端 save 成功响应回传 redact 后 config,前端 save 成功用其重填 state
- [ ] **F2[重要+debt#2]** 未保存新行 :key 回退 index,删行销毁编辑中卡片(`SettingsPanel.vue:98`)→ emptyRow 加 `__local_key`(客户端递增 id,collectServer 显式拾取不透传),:key 用 __row_id||__local_key
- [ ] **F3[次要 debt#1]** App 错误边界回显 err.message 与 boot 策略分叉(`App.vue:9`)→ 固定文案,测试同步
- [ ] **F4[次要 debt#3]** collectHeader 无直测→ collect.test 补 header 行断言

## Group G — 文档与台账收尾

- [ ] **G1[次要 debt#4]** README 加「改前端源码后须 npm run build 再提交产物」注记
- [ ] **G2[debt#5]** routing_e2e _cfg() 显式传 features= 钉住意图,关闭该 follow-up
- [ ] 台账登记:debt#7/#8(风格/DTO 重复)经对抗验证判不修;debt#9「重复新建」不成立(整表替换),真实形态为 F1;debt#10 由 B5 消解

## 验收

后端 pytest 全绿 + 前端 test:run/typecheck/build/verify:bundle 全绿 + ruff/mypy + 整分支 opus 终审。
