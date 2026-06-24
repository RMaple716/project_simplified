"""
协商核心模块包

功能:
1. ✅ 冲突检测封装 (conflict_detector)
2. ✅ 策略执行器 (strategy_executor) - 替代 if/elif 硬编码链
3. ✅ 协商协调器 (negotiation_orchestrator) - 拆分 negotiate_and_fix()
4. ✅ 事件发布封装 (event_publisher) 
5. ✅ 修复验证器 (repair_validator)
6. ✅ 【P2】反提案引擎 (counter_proposal) - Agent驱动的创造性协商
7. ✅ 【P2】LLM仲裁者 (llm_arbiter) + 合同网协议 (contract_net_protocol)
8. ✅ 【第三阶段】Pareto优化器 (pareto_optimizer) - 多目标优化
9. ✅ 【第四阶段】解释模板 (explanation_templates) - 人类可读的中文说明

使用方式:
    from src.services.negotiation_core import (
        detect_conflicts,
        strategy_executor,
        negotiation_orchestrator,
        event_publisher,
        repair_validator,
        counter_proposal_engine,
        llm_arbiter,
        contract_net_protocol,
        pareto_optimizer,
        format_strategy_explanation,
        format_conflict_explanation,
        build_human_readable_from_adjustment,
    )
"""

from .conflict_detector import (
    detect_conflicts,
    ConflictDetectionResult,
)
from .strategy_executor import (
    StrategyExecutor,
    strategy_executor,
)
from .event_publisher import (
    NegotiationEventPublisher,
    event_publisher,
)
from .repair_validator import (
    RepairValidator,
    repair_validator,
)
from .counter_proposal import (
    CounterProposalEngine,
    counter_proposal_engine,
)
from .negotiation_orchestrator import (
    NegotiationOrchestrator,
    negotiation_orchestrator,
    local_search_reshuffle,
)
from .pareto_optimizer import (
    ParetoOptimizer,
    ParetoCandidate,
    pareto_optimizer,
)
from .explanation_templates import (
    format_strategy_explanation,
    format_conflict_explanation,
    build_human_readable_from_adjustment,
    STRATEGY_CHINESE_NAMES,
    STRATEGY_EXPLANATIONS,
    CONFLICT_EXPLANATIONS,
)

__all__ = [
    "detect_conflicts",
    "ConflictDetectionResult",
    "StrategyExecutor",
    "strategy_executor",
    "NegotiationEventPublisher",
    "event_publisher",
    "RepairValidator",
    "repair_validator",
    "CounterProposalEngine",
    "counter_proposal_engine",
    "NegotiationOrchestrator",
    "negotiation_orchestrator",
    "local_search_reshuffle",
    "ParetoOptimizer",
    "ParetoCandidate",
    "pareto_optimizer",
    "format_strategy_explanation",
    "format_conflict_explanation",
    "build_human_readable_from_adjustment",
    "STRATEGY_CHINESE_NAMES",
    "STRATEGY_EXPLANATIONS",
    "CONFLICT_EXPLANATIONS",
]
