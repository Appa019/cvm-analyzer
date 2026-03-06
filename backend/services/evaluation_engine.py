"""
CVM Analyzer - Evaluation Engine Service
=====================================

Core engine for evaluating FRE documents using OpenAI Responses API.
Implements structured outputs, scoring, and suggestion generation.
"""

import asyncio
import json
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, asdict, field
from datetime import datetime
import logging

from openai import AsyncOpenAI

from config import get_settings, STATUS_CONFIG, SEVERITY_PENALTIES
from services.pdf_extractor import PDFSection, get_pdf_extractor
from services.checklist_parser import ChecklistItem, NormativeChecklist, get_checklist_parser


# =============================================================================
# Structured Output Schemas
# =============================================================================

ITEM_EVALUATION_SCHEMA = {
    "name": "fre_item_evaluation",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "item_id": {
                "type": "string",
                "description": "ID do item avaliado (ex: 7.3)"
            },
            "status": {
                "type": "string",
                "enum": ["COMPLETO", "PARCIAL", "AUSENTE", "CRITICO"],
                "description": "Status da avaliação do item"
            },
            "issues": {
                "type": "array",
                "description": "Lista de problemas encontrados",
                "items": {
                    "type": "object",
                    "properties": {
                        "severity": {
                            "type": "string",
                            "enum": ["low", "medium", "high", "critical"]
                        },
                        "description": {
                            "type": "string",
                            "description": "Descrição do problema"
                        }
                    },
                    "required": ["severity", "description"],
                    "additionalProperties": False
                }
            },
            "missing_checklist": {
                "type": "array",
                "description": "Lista de itens faltantes no checklist",
                "items": {"type": "string"}
            },
            "suggestion": {
                "type": "string",
                "description": "Sugestão de texto para completar (com {{placeholders}})"
            },
            "confidence": {
                "type": "number",
                "description": "Confiança na avaliação (0.0 a 1.0)"
            },
            "reasoning": {
                "type": "string",
                "description": "Explicação do raciocínio por trás da avaliação"
            }
        },
        "required": ["item_id", "status", "issues", "missing_checklist", "suggestion", "confidence", "reasoning"],
        "additionalProperties": False
    }
}


@dataclass
class Issue:
    """Represents an issue found in the evaluation."""
    severity: str  # low, medium, high, critical
    description: str


@dataclass
class ItemEvaluationResult:
    """Result of evaluating a single FRE item."""
    item_id: str
    titulo: str
    status: str  # COMPLETO, PARCIAL, AUSENTE, CRITICO
    score: int  # 0-100
    peso: int  # 1-3
    issues: List[Issue]
    missing_checklist: List[str]
    suggestion: str
    confidence: float
    reasoning: str
    tokens_used: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    
    def to_dict(self) -> Dict:
        return {
            **asdict(self),
            "issues": [asdict(i) for i in self.issues]
        }


@dataclass
class EvaluationSummary:
    """Summary of full document evaluation (FRE, DFP, FCA or IPE)."""
    document_id: str
    dt_refer: str
    versao: int
    total_score: Optional[float]  # None for qualitative evaluations (IPE)
    total_items: int
    complete_count: int
    partial_count: int
    absent_count: int
    critical_count: int
    item_results: List[ItemEvaluationResult]
    evaluated_at: str
    model_used: str
    total_tokens: int
    tipo_doc: str = "FRE"
    
    def to_dict(self) -> Dict:
        return {
            **asdict(self),
            "item_results": [r.to_dict() for r in self.item_results]
        }


def _parse_model(model_str: str) -> tuple:
    """Faz parse de 'modelo:effort' → (base_model, reasoning_dict | None).
    Ex: 'gpt-5.4:high' → ('gpt-5.4', {'effort': 'high'})
    """
    if ':' in model_str:
        base, effort = model_str.split(':', 1)
        return base, {"effort": effort}
    return model_str, None


class EvaluationEngineService:
    """
    Service for evaluating FRE documents.
    
    Uses OpenAI Responses API with Structured Outputs:
    - Evaluates each section against normative checklist
    - Calculates weighted scores
    - Generates improvement suggestions with placeholders
    - Compares with historical FREs
    """
    
    SYSTEM_PROMPTS = {
        "FRE": """Você é um especialista em análise de Formulários de Referência (FRE) da CVM brasileira.

Sua tarefa é avaliar se cada seção do FRE está em conformidade com os requisitos da Resolução CVM 80, Anexo C.

Para cada item, você deve:
1. Verificar se todas as informações obrigatórias estão presentes
2. Identificar informações faltantes ou incompletas
3. Detectar inconsistências ou erros graves
4. Sugerir melhorias quando necessário

Critérios de classificação:
- COMPLETO: Todas as informações obrigatórias estão presentes e adequadas
- PARCIAL: Há informações, mas estão incompletas ou genéricas demais
- AUSENTE: O item existe no índice mas não há conteúdo substantivo
- CRITICO: Falta informação regulatória essencial (riscos, contingências, partes relacionadas, governança)

Ao sugerir melhorias, use placeholders no formato {{nome_snake_case}} para valores específicos.
Por exemplo: "A empresa deve divulgar {{valor_contingencia_total}} referente às contingências trabalhistas."

Seja preciso e objetivo. Cite especificamente o que está faltando.""",

        "DFP": """Você é um especialista em análise de Demonstrações Financeiras Padronizadas (DFP) da CVM brasileira.

Sua tarefa é avaliar se cada demonstração e nota explicativa está em conformidade com as normas CVM, CPC e IFRS.

Para cada item, você deve:
1. Verificar se os saldos, comparativos e estrutura estão corretos
2. Identificar notas explicativas ausentes ou insuficientes
3. Avaliar a aderência ao CPC/IFRS aplicável
4. Verificar se há parecer de auditoria e principais assuntos de auditoria (PAA)

Critérios de classificação:
- COMPLETO: Demonstração/nota completa, adequada e com comparativos
- PARCIAL: Há informações mas faltam detalhes, comparativos ou notas explicativas
- AUSENTE: Demonstração ou nota obrigatória não localizada no documento
- CRITICO: Problema material: saldos sem conciliação, notas de contingência ausentes, auditoria com ressalva

Use placeholders {{nome_snake_case}} para valores específicos nas sugestões.""",

        "FCA": """Você é um especialista em análise de Formulários Cadastrais (FCA) da CVM brasileira.

Sua tarefa é avaliar se cada seção do FCA está corretamente preenchida conforme a Resolução CVM 80.

Para cada item, você deve:
1. Verificar se os dados cadastrais estão completos e atualizados
2. Identificar campos obrigatórios ausentes ou desatualizados
3. Verificar consistência entre dados declarados e documentos societários
4. Avaliar adequação das assinaturas e declarações

Critérios de classificação:
- COMPLETO: Campo preenchido corretamente com informações atualizadas
- PARCIAL: Campo preenchido mas com informações incompletas ou possivelmente desatualizadas
- AUSENTE: Campo obrigatório não preenchido
- CRITICO: Informação incorreta ou inconsistente com documentos societários

Use placeholders {{nome_snake_case}} para valores específicos nas sugestões.""",
    }

    # Prompt padrão (fallback)
    SYSTEM_PROMPT = SYSTEM_PROMPTS["FRE"]

    def _get_system_prompt(self, tipo_doc: str) -> str:
        return self.SYSTEM_PROMPTS.get(tipo_doc, self.SYSTEM_PROMPTS["FRE"])

    def __init__(
        self,
        api_key: Optional[str] = None,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize evaluation engine.
        
        Args:
            api_key: OpenAI API key (stored in memory only)
            logger: Logger instance
        """
        self.settings = get_settings()
        self.api_key = api_key or self.settings.openai_api_key
        self.logger = logger or logging.getLogger(__name__)
        self._client: Optional[AsyncOpenAI] = None
        
        self.pdf_extractor = get_pdf_extractor()
        self.checklist_parser = get_checklist_parser()
    
    def set_api_key(self, api_key: str):
        """Set API key (stored in memory only)."""
        self.api_key = api_key
        self._client = None  # Reset client
        self.logger.info("API key updated")
    
    def clear_api_key(self):
        """Clear API key from memory."""
        self.api_key = None
        self._client = None
        self.logger.info("API key cleared")
    
    @property
    def client(self) -> AsyncOpenAI:
        """Get AsyncOpenAI client."""
        if not self.api_key:
            raise ValueError("API key not set. Configure FRE_OPENAI_API_KEY em .env")

        if self._client is None:
            self._client = AsyncOpenAI(api_key=self.api_key)

        return self._client
    
    def calculate_score(
        self,
        status: str,
        peso: int,
        issues: List[Issue]
    ) -> int:
        """
        Calculate weighted score for an item.
        
        Formula:
        - base_status: COMPLETO=1.0, PARCIAL=0.6, AUSENTE=0.0, CRITICO=0.0
        - peso: 3 (alto), 2 (médio), 1 (baixo)
        - penalty: sum of severity penalties
        - score = 100 * base_status * (peso/3) - (100 * penalty)
        
        Args:
            status: Evaluation status
            peso: Item weight (1-3)
            issues: List of issues found
            
        Returns:
            Score between 0 and 100
        """
        base = STATUS_CONFIG.get(status, {}).get("score_base", 0.0)
        
        # Calculate penalty from issues
        penalty = sum(
            SEVERITY_PENALTIES.get(issue.severity, 0)
            for issue in issues
        )
        
        # Calculate final score
        score = (100 * base * (peso / 3.0)) - (100 * penalty)
        
        return max(0, min(100, int(round(score))))
    
    def _cnpj_slug(self, cnpj: str) -> str:
        return cnpj.replace("/", "_").replace(".", "_").replace("-", "_").strip("_")

    def _load_historical_sections(
        self,
        cnpj: str,
        tipo_doc: str,
        current_filename: Optional[str] = None,
        n: int = 5,
    ) -> Dict[str, List[str]]:
        """Carrega até n docs históricos do mesmo tipo e retorna mapa item_id → [textos]."""
        hist_map: Dict[str, List[str]] = {}
        try:
            company_dir = self.settings.base_dir / "enet_local" / self._cnpj_slug(cnpj)
            index_path = company_dir / "index.json"
            if not index_path.exists():
                return hist_map
            index = json.loads(index_path.read_text(encoding="utf-8"))
            files = index if isinstance(index, list) else index.get("files", [])
            # Filtra por tipo, exclui o arquivo atual, ordena por dt_refer desc
            candidates = [
                f for f in files
                if (f.get("tipo_doc") or "FRE").upper() == tipo_doc.upper()
                and f.get("filename") != current_filename
            ]
            candidates.sort(key=lambda f: f.get("dt_refer", ""), reverse=True)
            candidates = candidates[:n]
            for entry in candidates:
                pdf_path = company_dir / entry["filename"]
                if not pdf_path.exists():
                    continue
                try:
                    extraction = self.pdf_extractor.extract_full(pdf_path)
                    for sec in extraction.sections:
                        if sec.content_text:
                            hist_map.setdefault(sec.item_id, []).append(
                                sec.content_text[:2000]
                            )
                except Exception as exc:
                    self.logger.debug(f"Histórico {entry['filename']}: {exc}")
        except Exception as exc:
            self.logger.warning(f"Erro ao carregar histórico ({cnpj}): {exc}")
        return hist_map

    async def evaluate_item(
        self,
        section: PDFSection,
        normative_item: Optional[ChecklistItem],
        tipo_doc: str = "FRE",
        historical_texts: Optional[List[str]] = None,
    ) -> ItemEvaluationResult:
        """
        Evaluate a single FRE item using OpenAI.

        Args:
            section: Extracted PDF section
            normative_item: Corresponding normative checklist item
            tipo_doc: Tipo do documento (FRE, DFP, FCA, IPE)
            historical_texts: Textos do mesmo item em documentos anteriores (contexto histórico)

        Returns:
            ItemEvaluationResult with full evaluation
        """
        peso = normative_item.peso if normative_item else 1
        normative_text = normative_item.texto_normativo if normative_item else ""

        # Build historical context block
        hist_block = ""
        if historical_texts:
            snippets = "\n---\n".join(
                f"Versão anterior {i+1}:\n{txt}" for i, txt in enumerate(historical_texts[:5])
            )
            hist_block = f"\n\n**Conteúdo do mesmo item em versões anteriores (para comparação):**\n{snippets}\n"

        # Build evaluation prompt
        doc_label = tipo_doc
        user_prompt = f"""Avalie o seguinte item do {doc_label}:

**Item:** {section.item_id} - {section.titulo}

**Requisito Normativo (Resolução CVM 80):**
{normative_text or "Requisito não especificado"}

**Conteúdo atual do documento:**
{section.content_text[:6000] if section.content_text else "[CONTEÚDO AUSENTE]"}

{"**Tabelas encontradas:** " + str(len(section.tables)) + " tabela(s)" if section.tables else ""}{hist_block}
Avalie este item e forneça sua análise estruturada."""

        try:
            base_model, reasoning = _parse_model(self.settings.openai_model)
            eval_kwargs: Dict[str, Any] = {
                "model": base_model,
                "instructions": self._get_system_prompt(tipo_doc),
                "input": user_prompt,
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "fre_item_evaluation",
                        "strict": True,
                        "schema": ITEM_EVALUATION_SCHEMA["schema"]
                    }
                },
            }
            if reasoning:
                eval_kwargs["reasoning"] = reasoning
            response = await self.client.responses.create(**eval_kwargs)
            
            # Parse response
            result_text = response.output_text
            result_data = json.loads(result_text)
            
            # Convert issues
            issues = [
                Issue(severity=i["severity"], description=i["description"])
                for i in result_data.get("issues", [])
            ]
            
            status = result_data.get("status", "AUSENTE")
            
            # Calculate score
            score = self.calculate_score(status, peso, issues)
            
            # Get token usage (split exato da Responses API)
            usage = getattr(response, 'usage', None)
            input_tokens = getattr(usage, 'input_tokens', 0) if usage else 0
            output_tokens = getattr(usage, 'output_tokens', 0) if usage else 0
            tokens_used = getattr(usage, 'total_tokens', input_tokens + output_tokens) if usage else 0

            return ItemEvaluationResult(
                item_id=section.item_id,
                titulo=section.titulo,
                status=status,
                score=score,
                peso=peso,
                issues=issues,
                missing_checklist=result_data.get("missing_checklist", []),
                suggestion=result_data.get("suggestion", ""),
                confidence=result_data.get("confidence", 0.0),
                reasoning=result_data.get("reasoning", ""),
                tokens_used=tokens_used,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            
        except Exception as e:
            self.logger.error(f"Error evaluating item {section.item_id}: {e}")
            
            # Return error result
            return ItemEvaluationResult(
                item_id=section.item_id,
                titulo=section.titulo,
                status="CRITICO",
                score=0,
                peso=peso,
                issues=[Issue(severity="critical", description=f"Erro na avaliação: {str(e)}")],
                missing_checklist=[],
                suggestion="",
                confidence=0.0,
                reasoning=f"Falha ao avaliar: {str(e)}",
                tokens_used=0
            )
    
    def evaluate_item_sync(
        self,
        section: PDFSection,
        normative_item: Optional[ChecklistItem]
    ) -> ItemEvaluationResult:
        """Synchronous version of evaluate_item."""
        import asyncio
        return asyncio.run(self.evaluate_item(section, normative_item))
    
    async def evaluate_document(
        self,
        pdf_path: str,
        dt_refer: str,
        versao: int,
        tipo_doc: str = "FRE",
        cnpj: Optional[str] = None,
        current_filename: Optional[str] = None,
    ) -> EvaluationSummary:
        """
        Evaluate complete document (FRE, DFP, FCA or IPE).

        - FRE/DFP/FCA: avaliação estruturada por checklist normativo, paralela em lotes de 15
        - IPE: análise qualitativa livre por LLM (sem score numérico)

        Contexto por item:
          1. Requisito normativo da Resolução CVM 80 (resol080consolid.docx)
          2. Seção atual do documento inserido
          3. Mesma seção em até 5 documentos anteriores do mesmo tipo (histórico)
        """
        self.logger.info(f"Iniciando avaliação {tipo_doc} {dt_refer} v{versao}")

        if tipo_doc == "IPE":
            return await self._evaluate_qualitative(pdf_path, dt_refer, versao)

        # Avaliação estruturada por checklist
        extraction = self.pdf_extractor.extract_full(Path(pdf_path))

        checklist = await self.checklist_parser.parse_checklist(tipo_doc)
        normative_map = {item.item_id: item for item in checklist.items}

        # Carrega seções históricas (até 5 docs anteriores do mesmo tipo)
        hist_map: Dict[str, List[str]] = {}
        if cnpj:
            hist_map = await asyncio.to_thread(
                self._load_historical_sections, cnpj, tipo_doc, current_filename
            )
            self.logger.info(
                f"Histórico carregado: {len(hist_map)} itens de documentos anteriores"
            )

        # Avalia todos os itens em paralelo, limitado a 15 requisições simultâneas
        sem = asyncio.Semaphore(15)

        async def _eval(section: PDFSection) -> ItemEvaluationResult:
            async with sem:
                result = await self.evaluate_item(
                    section,
                    normative_map.get(section.item_id),
                    tipo_doc,
                    historical_texts=hist_map.get(section.item_id),
                )
                self.logger.info(
                    f"Avaliado {section.item_id}: {result.status} (score: {result.score})"
                )
                return result

        results: List[ItemEvaluationResult] = list(
            await asyncio.gather(*[_eval(s) for s in extraction.sections])
        )
        total_tokens = sum(r.tokens_used for r in results)

        complete_count = sum(1 for r in results if r.status == "COMPLETO")
        partial_count = sum(1 for r in results if r.status == "PARCIAL")
        absent_count = sum(1 for r in results if r.status == "AUSENTE")
        critical_count = sum(1 for r in results if r.status == "CRITICO")

        if results:
            total_weight = sum(r.peso for r in results)
            weighted_sum = sum(r.score * r.peso for r in results)
            total_score: Optional[float] = round(weighted_sum / max(total_weight, 1), 1)
        else:
            total_score = 0.0

        summary = EvaluationSummary(
            document_id=f"{tipo_doc.lower()}_{dt_refer}_v{versao}",
            dt_refer=dt_refer,
            versao=versao,
            total_score=total_score,
            total_items=len(results),
            complete_count=complete_count,
            partial_count=partial_count,
            absent_count=absent_count,
            critical_count=critical_count,
            item_results=results,
            evaluated_at=datetime.utcnow().isoformat(),
            model_used=self.settings.openai_model,
            total_tokens=total_tokens,
            tipo_doc=tipo_doc,
        )

        self.logger.info(
            f"Avaliação concluída: score={total_score}, "
            f"items={len(results)}, tokens={total_tokens}"
        )

        return summary

    async def _evaluate_qualitative(
        self,
        pdf_path: str,
        dt_refer: str,
        versao: int,
    ) -> EvaluationSummary:
        """
        Avaliação qualitativa livre para documentos IPE.
        Não usa checklist fixo; retorna análise textual por LLM.
        total_score=None para indicar avaliação qualitativa.
        """
        from pathlib import Path
        import fitz

        self.logger.info(f"Avaliação qualitativa IPE {dt_refer} v{versao}")

        # Extrai texto do PDF
        try:
            doc = fitz.open(str(pdf_path))
            full_text = "\n".join(page.get_text("text") for page in doc)
            doc.close()
        except Exception as exc:
            self.logger.error(f"Erro ao extrair texto IPE: {exc}")
            full_text = ""

        prompt = f"""Analise o seguinte documento IPE (Informe Periódico de Evento) da CVM e forneça uma análise qualitativa.

Avalie:
1. Completude das informações prestadas
2. Clareza e objetividade
3. Conformidade geral com as normas CVM
4. Pontos de atenção ou riscos identificados
5. Sugestões de melhoria

Texto do documento (primeiros 12.000 caracteres):
{full_text[:12000]}

Forneça sua análise em português, de forma estruturada."""

        try:
            base_model, reasoning = _parse_model(self.settings.openai_model)
            qual_kwargs: Dict[str, Any] = {
                "model": base_model,
                "input": [
                    {"role": "system", "content": "Você é um especialista em regulação CVM e análise de documentos de mercado de capitais."},
                    {"role": "user", "content": prompt},
                ],
            }
            if reasoning:
                qual_kwargs["reasoning"] = reasoning
            response = await self.client.responses.create(**qual_kwargs)
            analysis_text = response.output_text
            usage = getattr(response, "usage", None)
            input_tokens = getattr(usage, "input_tokens", 0) if usage else 0
            output_tokens = getattr(usage, "output_tokens", 0) if usage else 0
            tokens_used = getattr(usage, "total_tokens", input_tokens + output_tokens) if usage else 0
        except Exception as exc:
            self.logger.error(f"Erro na avaliação qualitativa IPE: {exc}")
            analysis_text = f"Erro ao analisar documento: {exc}"
            tokens_used = input_tokens = output_tokens = 0

        qualitative_result = ItemEvaluationResult(
            item_id="qualitative",
            titulo="Análise Qualitativa IPE",
            status="QUALITATIVO",
            score=0,
            peso=1,
            issues=[],
            missing_checklist=[],
            suggestion="",
            confidence=1.0,
            reasoning=analysis_text,
            tokens_used=tokens_used,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

        return EvaluationSummary(
            document_id=f"ipe_{dt_refer}_v{versao}",
            dt_refer=dt_refer,
            versao=versao,
            total_score=None,  # qualitativo — sem score numérico
            total_items=1,
            complete_count=0,
            partial_count=0,
            absent_count=0,
            critical_count=0,
            item_results=[qualitative_result],
            evaluated_at=datetime.utcnow().isoformat(),
            model_used=self.settings.openai_model,
            total_tokens=tokens_used,
            tipo_doc="IPE",
        )

    def evaluate_document_sync(
        self,
        pdf_path: str,
        dt_refer: str,
        versao: int,
        tipo_doc: str = "FRE",
    ) -> EvaluationSummary:
        """Synchronous version of evaluate_document."""
        import asyncio
        return asyncio.run(self.evaluate_document(pdf_path, dt_refer, versao, tipo_doc))
    
    def compare_with_historical(
        self,
        current_results: List[ItemEvaluationResult],
        historical_results: List[ItemEvaluationResult]
    ) -> Dict[str, Any]:
        """
        Compare current evaluation with historical.
        
        Args:
            current_results: Current FRE evaluation results
            historical_results: Previous FRE evaluation results
            
        Returns:
            Dict with comparison analysis
        """
        current_map = {r.item_id: r for r in current_results}
        historical_map = {r.item_id: r for r in historical_results}
        
        all_ids = set(current_map.keys()) | set(historical_map.keys())
        
        comparisons = []
        for item_id in sorted(all_ids):
            curr = current_map.get(item_id)
            hist = historical_map.get(item_id)
            
            comparison = {
                "item_id": item_id,
                "current_status": curr.status if curr else None,
                "historical_status": hist.status if hist else None,
                "current_score": curr.score if curr else None,
                "historical_score": hist.score if hist else None,
                "score_change": None,
                "status_improved": False,
                "status_worsened": False,
                "new_item": curr is not None and hist is None,
                "removed_item": curr is None and hist is not None
            }
            
            if curr and hist:
                comparison["score_change"] = curr.score - hist.score
                
                # Status order: COMPLETO > PARCIAL > AUSENTE > CRITICO
                status_order = {"COMPLETO": 4, "PARCIAL": 3, "AUSENTE": 2, "CRITICO": 1}
                curr_order = status_order.get(curr.status, 0)
                hist_order = status_order.get(hist.status, 0)
                
                comparison["status_improved"] = curr_order > hist_order
                comparison["status_worsened"] = curr_order < hist_order
            
            comparisons.append(comparison)
        
        # Summary
        improved = [c for c in comparisons if c["status_improved"]]
        worsened = [c for c in comparisons if c["status_worsened"]]
        new_items = [c for c in comparisons if c["new_item"]]
        removed_items = [c for c in comparisons if c["removed_item"]]
        
        return {
            "comparisons": comparisons,
            "summary": {
                "total_items": len(comparisons),
                "improved_count": len(improved),
                "worsened_count": len(worsened),
                "new_items_count": len(new_items),
                "removed_items_count": len(removed_items),
                "avg_score_change": (
                    sum(c["score_change"] or 0 for c in comparisons) / 
                    max(len([c for c in comparisons if c["score_change"] is not None]), 1)
                )
            }
        }


# =============================================================================
# Singleton Instance
# =============================================================================

_evaluation_engine: Optional[EvaluationEngineService] = None


def get_evaluation_engine() -> EvaluationEngineService:
    """Get or create the evaluation engine singleton."""
    global _evaluation_engine
    if _evaluation_engine is None:
        from utils import get_logger
        _evaluation_engine = EvaluationEngineService(logger=get_logger())
    return _evaluation_engine
