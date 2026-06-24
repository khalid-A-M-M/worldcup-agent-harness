from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Protocol


@dataclass
class MatchContext:
    match_id: str
    home_team: str
    away_team: str
    kickoff_utc: datetime
    generated_at_utc: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    agent_name: str
    status: str
    summary: str
    payload: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


@dataclass
class PipelineState:
    match: MatchContext
    results: Dict[str, AgentResult] = field(default_factory=dict)
    audit_log: List[str] = field(default_factory=list)

    def add_result(self, result: AgentResult) -> None:
        self.results[result.agent_name] = result
        self.audit_log.append(f"{result.agent_name}: {result.status} - {result.summary}")

    def get_payload(self, agent_name: str) -> Dict[str, Any]:
        return self.results.get(agent_name, AgentResult(agent_name, "missing", "")).payload


class Agent(Protocol):
    name: str

    def run(self, state: PipelineState) -> AgentResult:
        ...


class AgentHarness:
    """Small deterministic harness that executes agents against one match state."""

    def __init__(self, agents: List[Agent]):
        self.agents = agents

    def run_match(self, match: MatchContext) -> PipelineState:
        state = PipelineState(match=match)
        for agent in self.agents:
            result = agent.run(state)
            state.add_result(result)
        return state
