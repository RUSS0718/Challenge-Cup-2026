# hetero_refine 直接发布记录(2026-08-29)

状态:`DEPLOYED_UNVALIDATED_CANARY`(gitcode main = `1e9e53d`,等待官方评测)。

## 搭载依据(区别于裸机制直发)

- 预注册 `refine_fresh_confirm_preregistration_2026-08-28.md` 三门全过:
  战斗之夜 W2(26→27,双臂 err 8.3%/6.2%)与本日 W2b(25→26,**双臂零错误**)
  连续两个干净窗,各净 +1,合并配对 4 胜 2 负,成本 1.26~1.27×≤1.35 门;
- 存量证据:恢复战役 144 对 b=12/c=4(单侧 p=0.0384,ADR-0002);
- 用户决策树预授权:W2 干净且 ≥平 → 搭载。

## 发布内容

| 项 | 值 |
| --- | --- |
| 基线 / 回滚锚 | `c9d0597`(hetero 单变量,官方 Run #5 = 12/112) |
| runtime commit | `1e9e53d` |
| 新变量 | SUBMISSION_CONFIG.enable_step_verification/revision=True(+p3_call_boost=3,effective 8) |
| 调用结构 | vote 5(内含 1 路 Alternative)+ verify/revise/re-verify 链(fail-closed) |
| 预估官方耗时 | ~5h(6h 红线内,余量 ~1h) |

## 验证

413/413 unittest(P0 止血测试以显式配置隔离 refine,档位编排骨架测试
更新至 4 调用 = 3 profile + 1 verify;档位断言翻转并注明搭载依据)。

## 发布后

1. 官方日志 → Run #7 记账,五数对照 Run #5(12/112/17/88.0%/4h24m);
2. 回滚条件(预写):correct 回退、耗时逼近 6h、runner error 上升 →
   revert 至 `c9d0597`;
3. 注意:refine 的官方价值主张是"零败修正"(fail-closed),若 invalid
   或 correct 恶化即回滚,不追加解释。
