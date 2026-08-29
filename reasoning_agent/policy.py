"""Task routing, prompts and immutable agent configuration."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# ── Task-type constants (universal, problem-text based) ────────────────────
TASK_TYPE_CHOICE = "choice"
TASK_TYPE_FILL_BLANK = "fill_blank"
TASK_TYPE_CALCULATION = "calculation"
TASK_TYPE_DERIVATION = "derivation"
TASK_TYPE_PROOF = "proof"
TASK_TYPE_EXPLANATION = "explanation"

# P1.1 采纳：三轮 12/15/12 均 > 旧基线 ~11/23；默认使用答案优先短提示。
POLICY_PROMPT = """你是严谨的数学推理智能体。解决用户给出的数学问题。不要复述题意、不要输出 Thinking Process、计划、标题、格式说明或无关说明。只输出一行“最终答案：”后接数学答案。"""
ANSWER_FIRST_POLICY_PROMPT = POLICY_PROMPT
ANSWER_ONLY_POLICY_PROMPT = """你是数学求解器。直接解题，不要输出 Thinking Process、计划、标题或格式说明。只输出一行“最终答案：”后接数学答案。"""
VERIFIER_PROMPT = """你是数学解答审核员。独立检查候选答案是否能正确解决题目。
若发现错误，指出第一个可证实的错误位置；不要复述完整解答。
最后一行必须且只能为：VERDICT: A、VERDICT: B 或 VERDICT: UNCERTAIN。
A 表示未发现可证实错误，B 表示发现可证实错误，UNCERTAIN 表示无法判断。"""
SUBSTITUTION_CHECK_PROMPT = """你是数学约束验证器。针对题目和给定候选答案，生成一个极短的 Python 检验程序。
程序运行时已经提供变量 candidate，它表示候选答案；不要给 candidate 赋值，也不要把候选答案写进程序字面量。
程序只能使用白名单数学表达式，并且必须通过 print(...) 输出一个布尔值：约束成立输出 True，否则输出 False。
只输出程序本身，可使用代码围栏但不要添加解释、导入、文件或网络操作。"""

# ── Task-aware prompts ─────────────────────────────────────────────────────
# Each prompt guides the model toward the expected output format for a specific
# question type.  All are universal (never refer to sample idx or answer).

CHOICE_PROMPT = """你是数学求解器。这是一道选择题。选出唯一正确的一项。不要输出分析、理由或无关说明。只输出一行“最终答案：X”，其中 X 是选项字母。"""

FILL_BLANK_PROMPT = """你是数学求解器。这是一道填空题。直接计算并填入结果。不要输出推导或无关说明。只输出一行“最终答案：”后接填入值。"""

CALCULATION_PROMPT = POLICY_PROMPT  # 复用已验证的 answer-first 提示词

# Experimental prompt for the numerical A/B arm.  It is opt-in so the
# promoted F+4096 default remains unchanged while the prompt effect is measured
# independently from parsing and token-budget changes.
NUMERIC_ANSWER_FIRST_PROMPT = """你是数学求解器。只解决题目本身，不输出标题或格式说明。
第一行必须且只能写：最终答案：<答案>
从第二行起可以给出必要的简短推理或校验；不要在第一行之前输出任何内容，也不要重复最终答案。"""

# CoD-style adaptation (candidate line, default off; see
# cod_numeric_screen_draft_2026-08-27.md): numeric-family only, keeps the
# answer-first contract, compresses the reasoning draft after line 1.
NUMERIC_COD_ANSWER_FIRST_PROMPT = NUMERIC_ANSWER_FIRST_PROMPT + """
从第二行起仅写最小必要草稿；每个草稿步骤最多5个词。优先使用算式和符号，省略解释性完整句。"""

DERIVATION_PROMPT = """你是严谨的数学推理智能体。这是一道推导题。请直接输出面向用户的正式答案，不要输出 Thinking Process、内部计划或格式说明。严格按照以下结构输出：

最终答案：<只写最终表达式、数值或结论>

推导：
<完整的关键推导链、中间步骤和定理引用>"""

PROOF_PROMPT = """你是严谨的数学推理智能体。这是一道证明题。请直接输出面向用户的正式答案，不要输出 Thinking Process、内部计划或格式说明。严格按照以下结构输出：

最终答案：<命题成立/不成立及必要的核心结论；若题目要求求值则写求得的值>

证明：
<完整而紧凑的证明，含命题陈述、关键推理步骤和结论>"""

EXPLANATION_PROMPT = """你是严谨的数学推理智能体。这是一道解释/说明题。请直接输出面向用户的正式答案，不要输出 Thinking Process、内部计划或格式说明。严格按照以下结构输出：

最终答案：<一句能够独立判定的核心回答>

解释：
<清晰、紧凑的数学解释，含关键定义和逻辑推理>"""

# ── P2: heterogeneous reasoner prompts ──────────────────────────────────────
# DirectReasoner uses standard forward derivation (definitions → theorems → answer).
# AlternativeReasoner uses complementary strategies (contradiction, construction,
# boundary checks, numerical verification) to approach from a different angle.
# When both agree, confidence is high; conflicts are resolved by the audit step.

DIRECT_REASONER_PROMPT = """你是数学推理智能体，使用标准正向推导方法。
步骤：
1. 明确关键定义和已知条件。
2. 引用或陈述相关定理/公式。
3. 从条件出发，逐步严格推演到结论，每步给出依据。
4. 检查定义域、边界条件和遗漏情形。
最后一行必须使用"最终答案："明确写出答案。"""

ALTERNATIVE_REASONER_PROMPT = """你是数学推理智能体，使用互补策略从另一角度验证或求解。
选择至少一种方法：
- 反证法：假设结论不成立，推导矛盾。
- 构造法：构造满足条件的实例或反例。
- 边界/特例检查：验证极端值、退化情形。
- 数值/代数验证：代入数值交叉检查。
不要重复标准正向推导的全部步骤，聚焦于不同的推理路径或验证。
最后一行必须使用"最终答案："明确写出答案。"""

# ── P3: step verification and revision prompts ────────────────────────────
# InternLM models embed a verbose "Thinking Process" before every response,
# which consumes tokens and makes structured lemma extraction unreliable.
# Strategy: single-call step-by-step verification instead of lemma extraction.

STEP_VERIFY_PROMPT = """你是数学验证员。逐步检查以下解答：
对每一步输出：OK 或 ERROR:步骤:原因。
所有步骤检查完毕后，最后一行输出：
ALL_OK:COMPLETE   — 全部正确且解答完整
ALL_OK:GAPS:缺失1;缺失2   — 步骤正确但不完整
ERRORS   — 发现有步骤错误（此时前面已有 ERROR 行指出）
不要输出 Thinking Process。"""

# ponytail: merged step+full verify into single call; split again if two-call accuracy measurably better.
SOLUTION_VERIFY_PROMPT = STEP_VERIFY_PROMPT  # backward-compat alias

STEP_REVISE_PROMPT = """你是数学修正员。原解答在指定步骤有错误。请只修正受影响的推导部分，保持正确步骤不变。
输入包含：原题、原解答、错误定位和原因。
输出修正后的完整解答。最后一行必须使用"最终答案："明确写出答案。"""

# ── GSA: generative self-aggregation ────────────────────────────────────
GSA_AGGREGATE_PROMPT = """你是数学评审员。下面是同一道题的多个独立解答得出的候选答案。请对比各候选的推理路径与结论：若一致，直接采纳该共识；若分歧，独立复核分歧点后给出你认为最可能正确的唯一答案。不要复述全部推理。

最后必须以一行「最终答案：<答案>」结尾。"""

# ── Verification-gated retry instructions ────────────────────────────────
# These are universal counter-evidence prompts for the single recovery slot.
GATED_TRUNCATION_INSTRUCTION = (
    "检查提示：你上一次的回答在写出完整结论前被截断。"
    "请改用最短完备推导重新作答：第一行立即写“最终答案：<答案>”，"
    "随后每一步只保留一行关键中间结果，禁止长篇展开或重复计算。"
)
GATED_UNSTRUCTURED_INSTRUCTION = (
    "检查提示：你上一次的回答缺少规定的“最终答案：”结论行。"
    "请严格按格式重新作答：先写一行“最终答案：<答案>”，再给出紧凑的解答主体。"
)
GATED_PLACEHOLDER_INSTRUCTION = (
    "检查提示：你上一次的回答只给出了占位符而不是真实答案。"
    "请直接完成计算，并写出一行“最终答案：<具体的数值、表达式或选项字母>”。"
)
GATED_CONFLICT_INSTRUCTION = (
    "检查提示：你上一次的回答包含两个互相矛盾的最终答案（“{first}”与“{second}”），两者不可能同时成立。"
    "请重新核对推导，只保留一个经过验证的最终答案，写在一行“最终答案：<答案>”。"
)
GATED_SANITY_INSTRUCTION = (
    "检查提示：你给出的答案 {answer} 不满足条件：{constraint}。"
    "请对照该约束重新核查推导，修正错误后给出一行“最终答案：<满足约束的答案>”。"
)


# Map task type → generation prompt.
TASK_PROMPTS: dict[str, str] = {
    TASK_TYPE_CHOICE: CHOICE_PROMPT,
    TASK_TYPE_FILL_BLANK: FILL_BLANK_PROMPT,
    TASK_TYPE_CALCULATION: CALCULATION_PROMPT,
    TASK_TYPE_DERIVATION: DERIVATION_PROMPT,
    TASK_TYPE_PROOF: PROOF_PROMPT,
    TASK_TYPE_EXPLANATION: EXPLANATION_PROMPT,
}

# Proof / explanation types that should never be rejected just because
# ``extract_final_answer`` found no "最终答案：" marker.
_NON_NUMERIC_TASK_TYPES: frozenset[str] = frozenset({TASK_TYPE_PROOF, TASK_TYPE_EXPLANATION, TASK_TYPE_DERIVATION})


def classify_problem_type(problem: str) -> str:
    """Return the dominant math-problem type based on problem-text signals.

    Classification is purely textual — no metadata, no sample idx, no subject.
    Order matters: more-specific patterns are checked first.
    """
    if not isinstance(problem, str) or not problem.strip():
        return TASK_TYPE_CALCULATION

    text = problem.strip()

    # ── Choice (format constraint, must precede content-type checks) ──
    if (
        re.search(r"(?:^|\n)\s*[A-D]\s*[.、．。]", text)
        or re.search(r"下列.*?(?:正确|错误|不正确).*?[是有的]", text)
        or re.search(r"选择|选项|单选|多选|[Cc]hoose\b|[Ss]elect\b", text)
    ):
        return TASK_TYPE_CHOICE

    # ── Proof ──
    if re.search(r"证明|求证|[Pp]rove\b|[Ss]how\s+that\b", text):
        return TASK_TYPE_PROOF

    # ── Explanation ──
    if re.search(r"解释|说明理由|阐述|[Ee]xplain\b|[Dd]escribe\b|为什么", text):
        return TASK_TYPE_EXPLANATION

    # ── Derivation ──
    if re.search(r"推导|导出|推演|[Dd]erive\b|[Dd]educe\b", text):
        return TASK_TYPE_DERIVATION

    # ── Fill-in-the-blank ──
    if re.search(r"_{3,}|（\s*）|填空|填入|[Ff]ill\s+in\b", text):
        return TASK_TYPE_FILL_BLANK

    # ── Default: calculation ──
    return TASK_TYPE_CALCULATION

@dataclass
class AgentConfig:
    # ── P0 stop-bleeding defaults ─────────────────────────────────────────
    # Official runs showed 1024-token truncation fanning one question into ~7
    # model calls (~98.7% finish_reason=length) with near-zero accuracy.
    # Single main call + at most one conditional retry; no per-candidate audit
    # and no verify-only P3.
    #
    # Token cap: 4096 (promoted from 3072 on 2026-08-15).  The official hidden
    # set run of the 3072 config (commit 174bbbb) scored 4.46% with a 91.7%
    # truncation rate (155/169 requests hit finish_reason=length), proving 3072
    # is still far too short on the hidden set even though it passed Gate 2 on
    # the local 112-question set (81.2% / 80.4%, length 10-18%).  Paired
    # single-variable 3072-vs-4096 A/B on the complex freeze set showed 4096
    # cuts length (35-42% -> 12-23%) and thinking leakage (33% -> 8-21%) with
    # no reproducible accuracy regression and at most +20.4% per-question token
    # cost.  The official 91.7% truncation is stronger evidence than the local
    # 5% pollution gate, so 4096 is adopted as the default.
    policy_sample_times: int = 1
    verifier_voting_times: int = 0
    max_model_calls: int = 2
    policy_temperature: float = 0.6
    policy_prompt: str = POLICY_PROMPT
    verifier_temperature: float = 0.0
    max_tokens: int = 4096
    l0_max_tokens: int = 4096
    verifier_max_tokens: int = 256
    enable_sympy_evidence: bool = False
    enable_substitution_check: bool = False
    substitution_max_tokens: int = 512
    enable_dynamic_budget: bool = False
    enable_l0_extended_tokens: bool = True
    enable_l2_routing: bool = False
    enable_local_repair: bool = False
    enable_uncertain_repair: bool = False
    max_repairs: int = 1
    l2_max_model_calls: int = 8
    # ── P0: task-aware routing ──
    enable_task_aware_prompt: bool = True
    # ── P0: time convergence (per-question wall-clock) ──
    enable_time_convergence: bool = True
    solve_converge_timeout_seconds: float = 960.0   # ~16 min → stop new candidates
    solve_hard_timeout_seconds: float = 1080.0       # ~18 min → stop all calls
    # ── P2: heterogeneous reasoners ──
    enable_heterogeneous_reasoners: bool = False
    # ── P3: step verification + targeted revision ──
    enable_step_verification: bool = False
    enable_step_revision: bool = False
    # P3 needs extra call budget beyond generation + audit.  When P3 is
    # re-enabled later, this boost reserves room for verify + revise + re-verify.
    p3_call_boost: int = 3
    # Offline method-card RAG experiment. Disabled by default; the official
    # path must remain independent of local assets until an A/B gate passes.
    enable_method_rag: bool = False
    method_rag_top_k: int = 2
    method_rag_max_context_chars: int = 4000
    enable_deterministic_solver: bool = False
    # Experimental A/B switches.  All remain opt-in; the current F+4096 path
    # is the default baseline until a freeze-set gate promotes a candidate.
    enable_numeric_answer_first_prompt: bool = False
    enable_numeric_answer_only_prompt: bool = False
    enable_strict_numeric_salvage: bool = False
    enable_conditional_token_retry: bool = False
    conditional_retry_max_tokens: int = 6144
    # ARH (answer representation alignment): numeric-family final_response
    # emitted in dual form — answer line + $\boxed{}$ canonical — covering
    # both positional and last-boxed judge extraction hypotheses. Pure
    # post-processing; zero extra calls. Default off.
    enable_answer_dual_form: bool = False
    enable_failure_retry_backoff: bool = False
    failure_retry_backoff_seconds: float = 1.0
    enable_explicit_answer_conflict_retry: bool = False
    # B1: deterministic verification gate for the single recovery call.
    enable_verification_gated_retry: bool = False
    # P1 invalid reduction: when every candidate is rejected and the solve
    # would return the apology fallback, best-effort salvage an answer-like
    # token from the rejected responses (numeric-family problems only).
    # Failure-path only: the success path never runs this.
    enable_failure_salvage: bool = False
    # Re2 (re-reading): input-side only — the problem statement is shown a
    # second time in the user prompt before answering. No extra calls,
    # no output-constraint changes.
    enable_re2_reread: bool = False
    # CoD-style adaptation: numeric-family answer-first prompt switches to a
    # minimal-draft variant (each draft step ≤5 words). Default off.
    enable_numeric_chain_of_draft: bool = False
    # ARH (answer representation alignment): numeric-family final_response
    # emitted in dual form — answer line + $\\boxed{}$ canonical — covering
    # both positional and last-boxed judge extraction hypotheses. Pure
    # post-processing; zero extra calls. Default off.
    enable_answer_dual_form: bool = False
    # GSA (generative self-aggregation): replaces majority voting with a fixed
    # 3+1 pattern — 3 independent samples, then 1 aggregation call that
    # reconciles them into a single answer. Compute-matched (4 calls < k5's 5).
    # Aggregate failure falls back to plain candidate selection. Default off.
    enable_gsa_aggregation: bool = False
    # B2 remains an explicit, disabled experiment; B1 does not depend on it.
    enable_truncation_recovery_prompt: bool = False
    # Adaptive consistency voting: independent full resamples of the same
    # problem; consensus is decided by conservative equivalence groups with
    # early exit once the top group reaches vote_agree_threshold clear answers.
    # Default off. When enabled (non-L0) it replaces the single conditional
    # retry slot and still respects max_model_calls and per-question time.
    enable_adaptive_voting: bool = False
    vote_k_max: int = 3
    vote_agree_threshold: int = 2


# ── Submission profile ────────────────────────────────────────────────────
# The official runner constructs ``ReasoningAgent(client=official_client)``
# without a config, which resolves here.
#
# 2026-08-27 user-approved experimental canary: C0 answer-first adaptive k5
# with one AlternativeReasoner call inside the non-L0 vote budget; remaining
# samples use DirectReasoner. This bypasses the unfinished local A/B gate.
# Rollback anchor: 242c480 (C0 runtime, official Run #4 = 9/112).
SUBMISSION_CONFIG = AgentConfig(
    policy_sample_times=1,
    policy_temperature=0.6,
    verifier_voting_times=0,
    enable_dynamic_budget=False,
    enable_l0_extended_tokens=True,
    enable_task_aware_prompt=True,
    enable_time_convergence=True,
    enable_adaptive_voting=True,
    vote_k_max=5,
    vote_agree_threshold=3,
    enable_verification_gated_retry=False,
    enable_truncation_recovery_prompt=False,
    max_model_calls=5,
    max_tokens=4096,
    l0_max_tokens=4096,
    enable_heterogeneous_reasoners=True,
    # P3 refine chain (verify -> revise -> re-verify) on top
    # of the hetero baseline; boarding qualification: battle-night W2+W2b
    # double clean confirm (net +1 each, cost 1.26x, zero paired losses
    # accumulated). Single new variable vs 25f99b5 behavior.
    enable_step_verification=True,
    enable_step_revision=True,
    enable_answer_dual_form=True,
    enable_method_rag=False,
    enable_deterministic_solver=False,
    enable_numeric_answer_first_prompt=True,
    enable_numeric_answer_only_prompt=False,
    enable_strict_numeric_salvage=False,
    enable_conditional_token_retry=False,
    enable_failure_retry_backoff=False,
    enable_explicit_answer_conflict_retry=False,
    enable_l2_routing=False,
    enable_local_repair=False,
    enable_uncertain_repair=False,
    enable_sympy_evidence=False,
)
