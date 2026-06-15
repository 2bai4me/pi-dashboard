"""SelfImprovement: Knowledge hub & framework comparison for self-improving agents."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..auth import require_auth

router = APIRouter(prefix="/api/selfimprovement", tags=["selfimprovement"])

FRAMEWORKS = [
    {
        "name": "GenericAgent",
        "stars": "12.8K",
        "description": "Self-evolving agent framework. 3K lines seed code wächst einen Skill-Tree. 9 atomare Tools, ~100 Zeilen Agent Loop.",
        "url": "https://github.com/lsdefine/GenericAgent",
        "approach": "Skill crystallization: Jede gelöste Aufgabe wird als Skill gespeichert. Nächstes Mal direkter Recall statt Neuberechnung.",
        "key_insight": "MiniMax-M3 + Ollama Gemma4 kompatibel. ~30K context window (sehr token-effizient). Layered Memory (L0-L4).",
        "applicable": True,
        "rationale": "Kann mit deinen vorhandenen MiniMax/Ollama-Modellen laufen. Selbst-evolvierender Skill-Tree passt perfekt zu deinen swarm-spawner Rollen.",
    },
    {
        "name": "EvoAgentX",
        "stars": "3K",
        "description": "Framework for building, evaluating, and evolving LLM agent workflows in an automated, modular, goal-driven manner.",
        "url": "https://github.com/EvoAgentX/EvoAgentX",
        "approach": "Self-evolution engine mit TextGrad, MIPRO, AFlow, EvoPrompt Algorithmen. Workflows werden automatisch generiert und optimiert.",
        "key_insight": "Human-in-the-Loop (HITL), Memory Module (short+long term), Built-in Tools (Search, Code, Browser, DB). MCP-kompatibel.",
        "applicable": True,
        "rationale": "Enthält AFlow (MCTS-basierte Workflow-Evolution) — könnte deine context-workflow Extension ersetzen oder ergänzen.",
    },
    {
        "name": "AgentEvolver (ModelScope)",
        "stars": "1K",
        "description": "End-to-end self-evolving training framework: self-questioning, self-navigating, self-attributing.",
        "url": "https://github.com/modelscope/AgentEvolver",
        "approach": "GRPO + Self-Questioning (autonome Task-Generierung), Self-Navigating (cross-task experience), Self-Attributing (fine-grained credit assignment).",
        "key_insight": "7B Modell erreicht 60%+ auf SWE-bench. 3 Self-Evolving Mechanisms aus einer Hand.",
        "applicable": False,
        "rationale": "Requires custom model training (GRPO). Für dich zu heavy, aber die Ideen (Self-Questioning für Task-Generierung) sind adaptierbar.",
    },
    {
        "name": "Agent0 (UNC/Salesforce)",
        "stars": "1.2K",
        "description": "Self-evolving agents from ZERO data. Curriculum Agent + Executor Agent. ICML'26.",
        "url": "https://github.com/aiming-lab/Agent0",
        "approach": "Curriculum Agent schlägt Aufgaben vor, Executor Agent lernt sie mit Tools zu lösen. Symbiotic competition.",
        "key_insight": "+18% auf math reasoning, +24% general reasoning. Zero external data. Funktioniert mit Qwen, Gemma, etc.",
        "applicable": True,
        "rationale": "Das Curriculum-Agent-Prinzip passt perfekt: Dein Haupt-PI (MiniMax) als Curriculum Agent, Sub-Agenten (Ollama) als Executors.",
    },
    {
        "name": "AutoAgent (HKU)",
        "stars": "9.3K",
        "description": "Fully-automated zero-code LLM agent framework. Baut Agenten aus natürlicher Sprache.",
        "url": "https://github.com/HKUDS/AutoAgent",
        "approach": "Agent Editor + Workflow Editor per Natural Language. Self-Play Agent Customization.",
        "key_insight": "Deep Research Mode (multi-agent). Container-basierte Isolation für Code-Ausführung.",
        "applicable": False,
        "rationale": "Zu high-level für deine bestehende Architektur, aber die Zero-Code-Idee für Rapid Prototyping interessant.",
    },
    {
        "name": "Lumos",
        "stars": "Neu",
        "description": "Self-evolving coding agent mit Trajectory Logging, Evaluator, Optimizer und Harness Packages.",
        "url": "https://github.com/SallyKAN/lumos",
        "approach": "Observe → Evaluate → Optimize → Distribute. Interceptor-System (10 Lifecycle Points). Memory Synthesis mit 3-Tier Decay.",
        "key_insight": "Harness Packages bündeln optimiertes Agent-Verhalten. Trajectory als First-Class Data für Evaluation.",
        "applicable": True,
        "rationale": "Das Interceptor-System (10 Lifecycle Points mit Onion Model) ist perfekt für deine context-workflow Extension.",
    },
    {
        "name": "Darwin Gödel Machine",
        "stars": "Projekt",
        "description": "Open-ended evolution of self-improving agents. Iteriert Code, validiert mit SWE-bench.",
        "url": "https://github.com/HarleyCoops/dgm",
        "approach": "Agent modifiziert eigenen Code, validiert Änderungen mit Coding Benchmarks. Polyglot + SWE-bench Evaluation.",
        "key_insight": "Self-modification Loop: Agent → Code ändern → Benchmark → Keep/Revert → Repeat.",
        "applicable": False,
        "rationale": "Zu akademisch/forschungsorientiert, aber das Keep/Revert-Prinzip ist in den Karpathy-Auto-Research-Loop eingeflossen.",
    },
    {
        "name": "Huxley-Gödel Machine",
        "stars": "356 (ICLR 2026 Oral)",
        "description": "Approximation des theoretischen Gödel Machine. Clade-basierte Self-Modification.",
        "url": "https://github.com/metauto-ai/HGM",
        "approach": "Estimates promise of entire subtrees (clades) to decide which self-modifications to expand.",
        "key_insight": "ICLR 2026 Oral Paper. Gödel Machine ist die theoretisch optimale Self-Improving Machine.",
        "applicable": False,
        "rationale": "Reine Forschung, aber die Clade-Idee ist interessant: Gruppe verwandter Verbesserungen evaluieren.",
    },
    {
        "name": "SII CLI (GAIR-NLP/SJTU)",
        "stars": "34",
        "description": "Cognitive Agentic Intelligence Ecosystem. Self-evolution durch Data Flywheel + Model Training.",
        "url": "https://github.com/GAIR-NLP/SII-CLI",
        "approach": "Data Flywheel: Automatic Query Synthesis → Simulated Agent Interaction → Continuous Reinforcement.",
        "key_insight": "Domain-Specific SFT + Vibe Coding + Research Workflows. Five-Module Architecture.",
        "applicable": False,
        "rationale": "Model-Training-Fokus. Zu heavy für dein Setup, aber die Data Flywheel Idee ist gut.",
    },
    {
        "name": "Self-Improving Coding Agent",
        "stars": "312",
        "description": "Agent der an seinem eigenen Codebase arbeitet. Benchmark → Improve → Re-Benchmark Loop.",
        "url": "https://github.com/MaximeRobeyns/self_improving_coding_agent",
        "approach": "ICLR 2025 Workshop Paper. Docker-isolated. Agent evaluiert sich selbst auf Benchmarks, dann verbessert er seinen eigenen Code.",
        "key_insight": "Meta-improvement: Der Agent verbessert nicht nur seine Outputs, sondern seine eigene Architektur.",
        "applicable": False,
        "rationale": "Forschung. Aber Meta-Improvement ist der nächste Schritt nach deinem swarm-spawner.",
    },
    {
        "name": "Midas Agent",
        "stars": "Neu",
        "description": "Coding agent der aus Fehlern lernt. Lesson Library + DAG Workflows + Importance Voting.",
        "url": "https://github.com/zysilm/midas-agent",
        "approach": "ExpeL-style self-reflection. Lessons werden extrahiert, via Embedding gespeichert und bei ähnlichen Issues wieder eingespielt.",
        "key_insight": "65% Pass Rate auf SWE-bench mit MiniMax-M2.5. 25% weniger Tokens durch Lesson Injection.",
        "applicable": True,
        "rationale": "MiniMax-M2.5 + Lesson Library = direkt nutzbar. Importance Voting verhindert Lesson Bloat. Perfekt für deine Sub-Agenten.",
    },
]


@router.get("/frameworks")
async def list_frameworks() -> list[dict]:
    """Liste aller recherchierten Self-Improvement Frameworks."""
    return FRAMEWORKS


@router.get("/strategy")
async def improvement_strategy() -> dict:
    """Konkreter Aktionsplan für Self-Improvement in deiner Pi-Architektur."""
    return {
        "title": "Pi Agent Self-Improvement Strategy",
        "date": "2026-06-14",
        "current_architecture": {
            "main_agent": "PI (MiniMax-M3)",
            "sub_agents": "swarm-spawner (Ollama Gemma4 12b)",
            "extensions": ["context-workflow", "cost-tracker", "openbrain-bridge", "git-checkpoint"],
        },
        "phases": [
            {
                "phase": 1,
                "name": "Lesson Library (Midas-Ansatz)",
                "description": "Jeder Sub-Agent speichert Lessons aus Fehlschlägen. Bei neuen Tasks werden relevante Lessons via Embedding-Suche injiziert.",
                "implementation": "Erweitere swarm-spawner um Failure Analyzer. Speichere Lessons in OpenBrain. Nutze Sentence-Transformers für Semantic Search.",
                "effort": "2-3 Sessions",
                "impact": "Sub-Agenten werden mit jeder Iteration besser. Weniger Wiederholungsfehler.",
                "packages": "sentence-transformers, faiss-cpu (oder OpenBrain als Vector Store)",
            },
            {
                "phase": 2,
                "name": "Skill Tree Evolution (GenericAgent-Ansatz)",
                "description": "Jede erfolgreich gelöste Sub-Agent-Aufgabe wird als Skill im Skill-Tree kristallisiert. Nächstes Mal direkter Recall.",
                "implementation": "Erweitere context-workflow: Nach erfolgreichem write→test→review→fix→verify Zyklus wird der Lösungsweg als Skill gespeichert.",
                "effort": "3-5 Sessions",
                "impact": "Häufige Tasks werden in Sekunden statt Minuten gelöst. Token-Verbrauch sinkt dramatisch.",
                "packages": "Bestehende SKILL.md-Struktur + OpenBrain-Speicherung",
            },
            {
                "phase": 3,
                "name": "Curriculum Learning (Agent0-Ansatz)",
                "description": "Haupt-PI (Curriculum Agent) schlägt zunehmend schwierigere Tasks vor, Sub-Agenten (Executors) lernen sie zu lösen.",
                "implementation": "Baue einen Difficulty-Scorer für Tasks. Automatische Progression von einfach → komplex.",
                "effort": "5-8 Sessions",
                "impact": "Systematische Kompetenzentwicklung. Der Agent wird mit der Zeit objektiv besser.",
            },
            {
                "phase": 4,
                "name": "Meta-Improvement Loop (DGM/HGM-Ansatz)",
                "description": "Der Haupt-Agent modifiziert seine eigene Konfiguration (toolWhitelist, systemPrompt, timeout) und validiert die Änderung.",
                "implementation": "Baue einen Meta-Agent: A/B-Test von Konfig-Änderungen. Keep/Revert basierend auf Token-Effizienz und Success-Rate.",
                "effort": "8-12 Sessions",
                "impact": "Der Agent optimiert sich selbst. Kein manuelles Tuning mehr nötig.",
            },
            {
                "phase": 5,
                "name": "Architecture Evolution (EvoAgentX-Ansatz)",
                "description": "AFlow-ähnliche MCTS-basierte Workflow-Evolution. context-workflow wird automatisch restrukturiert.",
                "implementation": "Trial verschiedene Stage-Sequenzen. Finde die optimale Pipeline für jeden Task-Typ.",
                "effort": "10-15 Sessions",
                "impact": "Maximale Effizienz durch optimierte Workflow-Strukturen.",
            },
        ],
        "recommended_start": "Phase 1 (Lesson Library) — niedrigste Einstiegshürde, höchster ROI. Basis für alle weiteren Phasen.",
        "key_papers": [
            {"title": "ExpeL: LLM Agents That Learn from Experience", "url": "https://arxiv.org/abs/2308.10144"},
            {"title": "GenericAgent Technical Report", "url": "https://arxiv.org/abs/2604.17091"},
            {"title": "Agent0: Self-Evolving Agents from Zero Data", "url": "https://arxiv.org/abs/2511.16043"},
            {"title": "EvoAgentX Framework Paper", "url": "https://arxiv.org/abs/2507.03616"},
            {"title": "Self-Evolving AI Agents Survey", "url": "https://arxiv.org/abs/2508.07407"},
            {"title": "EvoAgentX Survey on Self-Evolving Agents", "url": "https://arxiv.org/abs/2508.07407"},
            {"title": "Darwin Gödel Machine", "url": "https://arxiv.org/abs/2505.22954"},
            {"title": "Huxley-Gödel Machine (ICLR 2026)", "url": "https://arxiv.org/abs/2510.21614"},
            {"title": "AutoAgent: Zero-Code LLM Agent Framework", "url": "https://arxiv.org/abs/2502.05957"},
        ],
    }
