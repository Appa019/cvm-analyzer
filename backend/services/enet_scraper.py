"""
CVM Analyzer - ENET Scraper
===========================

Busca e baixa documentos do portal ENET (rad.cvm.gov.br) da CVM.
Suporta FRE (via Playwright, gera PDF) e IPE (httpx direto).
"""

import re
import json
import logging
import tempfile
from pathlib import Path
from typing import Optional

import httpx
from playwright.async_api import async_playwright

from config import get_settings, Settings
from utils import get_cache_manager, get_logger


class ENETScraper:
    """
    Acessa o portal rad.cvm.gov.br/ENET para listar e baixar documentos CVM.

    Categorias suportadas (ver CATEGORIAS dict para lista completa):
      EST_2,EST_8,EST_9 → FRE (Formulário de Referência)         — VIEWER
      EST_4             → DFP (Demonstrações Financeiras Padr.)  — VIEWER
      EST_3             → ITR (Informações Trimestrais)           — VIEWER
      EST_1             → FCA (Formulário Cadastral)              — VIEWER
      IPE_7_29_-1       → Press-release (Dados Econômico-Fin.)   — DOWNLOAD
      IPE_7_43_-1       → Relatório de Análise Gerencial          — DOWNLOAD
      IPE_4_-1_-1       → Fato Relevante                          — DOWNLOAD
      IPE_6_-1_-1       → Comunicado ao Mercado                   — DOWNLOAD
      IPE_-1_-1_-1      → Todos os IPE                           — DOWNLOAD
    """

    BASE = "https://www.rad.cvm.gov.br/ENET"
    _LIST_URL = BASE + "/frmConsultaExternaCVM.aspx/ListarDocumentos"
    _DL_URL = BASE + "/frmDownloadDocumento.aspx"
    _VIEWER = BASE + "/frmGerenciaPaginaFRE.aspx"
    # Mapeamento label → código categoria ENET para documentos de RI.
    # Códigos confirmados via scripts/extrai_categorias_enet.py (cboCategorias).
    # Documentos Estruturados (900xxx) usam VIEWER → Playwright (download_fre_pdf).
    # IPE e numéricos simples usam DOWNLOAD → httpx (download_ipe_pdf).
    CATEGORIAS: dict[str, str] = {
        # ── Documentos Estruturados (VIEWER → Playwright) ──────────────────────
        "FRE - Formulário de Referência":         "EST_2,EST_8,EST_9",
        "DFP - Demonstrações Financeiras Padr.":  "EST_4",
        "ITR - Informações Trimestrais":          "EST_3",
        "FCA - Formulário Cadastral":             "EST_1",
        # ── IPE (DOWNLOAD → httpx) ─────────────────────────────────────────────
        "Press-release (Dados Econômico-Fin.)":   "IPE_7_29_-1",
        "Relatório de Análise Gerencial":         "IPE_7_43_-1",
        "Fato Relevante":                         "IPE_4_-1_-1",
        "Comunicado ao Mercado":                  "IPE_6_-1_-1",
        "Todos os IPE":                           "IPE_-1_-1_-1",
    }

    # Regex para IPE: OpenDownloadDocumentos('seq','ver','proto','tipo')
    _DL_RE = re.compile(
        r"OpenDownloadDocumentos\('(\d+)','(\d+)','(\d+)','([^']*)'\)"
    )
    # Regex para FRE/FCA/DFP: OpenPopUpVer('.../NumeroSequencialDocumento=XXXXXX...')
    _FRE_SEQ_RE = re.compile(r"NumeroSequencialDocumento=(\d+)")

    def __init__(
        self,
        settings: Optional[Settings] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.settings = settings or get_settings()
        self.logger = logger or get_logger()
        self.cache = get_cache_manager()

    # ─── Listagem ─────────────────────────────────────────────────────────────

    async def list_documents(
        self,
        cod_cvm: str,
        categorias: list[str],
        data_de: str = "",
        data_ate: str = "",
        latest_only: bool = True,
    ) -> list[dict]:
        """
        POST ListarDocumentos para cada categoria; parseia 'dados'.

        O payload é enviado como string no formato JS object literal (aspas simples),
        exatamente como o portal ENET envia — o servidor ASP.NET exige esse formato.

        Args:
            cod_cvm:     código CVM da empresa (ex: "009512" ou "027073")
            categorias:  lista de códigos de categoria ENET.
                         Use ENETScraper.CATEGORIAS.values() para os valores corretos.
                         FRE → "EST_2,EST_8,EST_9"
            data_de:     data inicial DD/MM/AAAA (padrão: 5 anos atrás)
            data_ate:    data final DD/MM/AAAA (padrão: hoje)
            latest_only: se True (padrão), retorna apenas a versão mais recente de
                         cada documento (agrupa por categoria_doc + data_ref)

        Returns:
            Lista de dicts com: num_seq, tipo_acao ("VIEWER"|"DOWNLOAD"),
            cod_cvm_enet, empresa, categoria_doc, data_ref, status, versao, categoria
        """
        from datetime import date, timedelta
        today = date.today()
        if not data_ate:
            data_ate = today.strftime("%d/%m/%Y")
        if not data_de:
            cinco_anos = today.replace(year=today.year - 5)
            data_de = cinco_anos.strftime("%d/%m/%Y")

        # O ENET espera `,{cod_cvm}` no campo empresa (extraído de retornoAutoComplete)
        empresa_param = f",{cod_cvm.zfill(6)}"
        results: list[dict] = []

        async with httpx.AsyncClient(timeout=30) as client:
            for categoria in categorias:
                # Payload como string JS literal — NÃO alterar para JSON puro,
                # o servidor rejeita ou retorna dados vazios com JSON normal.
                payload_str = (
                    f"{{ dataDe: '{data_de}', dataAte: '{data_ate}' ,"
                    f" empresa: '{empresa_param}',"
                    f" setorAtividade: '-1', categoriaEmissor: '-1',"
                    f" situacaoEmissor: '-1', tipoParticipante: '-1',"
                    f" dataReferencia: '', categoria: '{categoria}',"
                    f" periodo: '2', horaIni: '', horaFim: '',"
                    f" palavraChave:'',ultimaDtRef:'false',"
                    f" tipoEmpresa:'0', token: '', versaoCaptcha: ''}}"
                )
                try:
                    resp = await client.post(
                        self._LIST_URL,
                        content=payload_str.encode("utf-8"),
                        headers={"Content-Type": "application/json; charset=utf-8"},
                    )
                    resp.raise_for_status()
                    outer = resp.json()
                    d_val = outer.get("d", {})
                    inner = json.loads(d_val) if isinstance(d_val, str) else d_val
                    if inner.get("temErro"):
                        self.logger.warning(
                            f"ENET erro categoria={categoria}: {inner.get('msgErro')}"
                        )
                        continue
                    dados = inner.get("dados", "") or ""
                    if dados:
                        docs = self._parse_dados(dados, categoria)
                        results.extend(docs)
                        self.logger.info(
                            f"ENET categoria={categoria} cod_cvm={cod_cvm}: {len(docs)} documentos"
                        )
                except Exception as exc:
                    self.logger.warning(
                        f"Falha ao listar ENET categoria={categoria} cod_cvm={cod_cvm}: {exc}"
                    )

        if latest_only:
            results = self._keep_latest_versions(results)

        return results

    @staticmethod
    def _keep_latest_versions(docs: list[dict]) -> list[dict]:
        """
        Para cada combinação (categoria_doc, data_ref), mantém apenas o documento
        com a versão mais alta (campo 'versao' como inteiro).
        Documentos sem versão numérica recebem versão 0.
        """
        best: dict[tuple, dict] = {}
        for doc in docs:
            key = (doc["categoria_doc"], doc["data_ref"])
            try:
                ver = int(doc.get("versao") or 0)
            except (ValueError, TypeError):
                ver = 0
            existing = best.get(key)
            if existing is None:
                best[key] = {**doc, "_ver_int": ver}
            else:
                if ver > existing["_ver_int"]:
                    best[key] = {**doc, "_ver_int": ver}
        # Remove campo auxiliar
        result = []
        for doc in best.values():
            doc.pop("_ver_int", None)
            result.append(doc)
        # Ordena por data_ref desc
        result.sort(key=lambda d: d.get("data_ref", ""), reverse=True)
        return result

    @staticmethod
    def _clean_html(s: str) -> str:
        return re.sub(r"<[^>]+>", "", s).strip()

    def _parse_dados(self, dados: str, categoria_code: str) -> list[dict]:
        """
        Parseia a string 'dados' do ENET.

        Formato: linhas separadas por '*', colunas por '$&'.
          Col[0]=codCVM, Col[1]=empresa, Col[2]=categoria_doc, Col[3]=tipo,
          Col[5]=dataRef (HTML), Col[6]=dataEntrega (HTML), Col[7]=status,
          Col[8]=versao, Col[9]=apresentação, Col[10]=ações HTML

        Dois tipos de ação:
          - FRE/FCA/DFP → OpenPopUpVer('...NumeroSequencialDocumento=NNN...')
          - IPE          → OpenDownloadDocumentos('seq','ver','proto','tipo')
        """
        docs = []
        for linha in dados.split("*"):
            linha = linha.strip()
            if not linha:
                continue
            cols = linha.split("$&")
            if len(cols) < 11:
                continue
            acoes = cols[10]

            num_seq = None
            num_versao = ""
            num_protocolo = ""
            tipo_acao = None

            # FRE/documentos estruturados: usa OpenPopUpVer com NumeroSequencialDocumento
            m_fre = self._FRE_SEQ_RE.search(acoes)
            if m_fre:
                num_seq = m_fre.group(1)
                tipo_acao = "VIEWER"
                num_versao = cols[8].strip() if len(cols) > 8 else ""
            else:
                # IPE: usa OpenDownloadDocumentos
                m_dl = self._DL_RE.search(acoes)
                if m_dl:
                    num_seq, num_versao, num_protocolo, _ = m_dl.groups()
                    tipo_acao = "DOWNLOAD"

            if num_seq is None:
                continue

            docs.append({
                "num_seq": num_seq,
                "num_versao": num_versao,
                "num_protocolo": num_protocolo,
                "tipo_acao": tipo_acao,     # "VIEWER" = FRE, "DOWNLOAD" = IPE
                "categoria": categoria_code,
                "cod_cvm_enet": cols[0].strip(),
                "empresa": cols[1].strip(),
                "categoria_doc": cols[2].strip(),
                "data_ref": self._clean_html(cols[5] if len(cols) > 5 else ""),
                "data_entrega": self._clean_html(cols[6] if len(cols) > 6 else ""),
                "status": cols[7].strip() if len(cols) > 7 else "",
                "versao": cols[8].strip() if len(cols) > 8 else "",
            })
        return docs

    # ─── Download IPE (httpx direto) ──────────────────────────────────────────

    async def download_ipe_pdf(
        self,
        num_seq: str,
        num_versao: str,
        num_protocolo: str,
    ) -> bytes:
        """
        Baixa PDF IPE diretamente via httpx.

        URL: frmDownloadDocumento.aspx?Tela=ext&numSequencia=...&numVersao=...
             &numProtocolo=...&descTipo=IPE&CodigoInstituicao=1
        """
        url = (
            f"{self._DL_URL}"
            f"?Tela=ext"
            f"&numSequencia={num_seq}"
            f"&numVersao={num_versao}"
            f"&numProtocolo={num_protocolo}"
            f"&descTipo=IPE"
            f"&CodigoInstituicao=1"
        )
        self.logger.info(f"Baixando IPE PDF: {url}")
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        content = resp.content
        if not content[:4] == b"%PDF":
            raise ValueError(
                f"Conteúdo baixado não é PDF válido (primeiros bytes: {content[:20]!r})"
            )
        return content

    # ─── Download FRE (Playwright) ────────────────────────────────────────────

    async def download_fre_pdf(self, num_seq: str, output_path: Path) -> Path:
        """
        Baixa PDF de FRE via Playwright:
          1. Navega para frmGerenciaPaginaFRE.aspx?NumeroSequencialDocumento={seq}
          2. JS click em #btnGeraRelatorioPDF → abre dialog jQuery UI (mesma página)
          3. O dialog contém iframe#iFrameModal → frmRelatorioPDF.aspx
          4. Clica em #btnConsulta dentro do iframe → dispara download via FileSaver.js
          5. Captura o download e salva em output_path
        """
        viewer_url = (
            f"{self._VIEWER}"
            f"?NumeroSequencialDocumento={num_seq}"
            f"&CodigoTipoInstituicao=1"
        )
        self.logger.info(f"Gerando PDF FRE via Playwright: seq={num_seq}")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(accept_downloads=True)
            page = await context.new_page()
            try:
                await page.goto(viewer_url, wait_until="load", timeout=60_000)

                # Passo 1: abre o dialog "Documento em PDF" (jQuery UI modal na mesma página).
                # O dialog contém iframe#iFrameModal → frmRelatorioPDF.aspx com #btnConsulta.
                # Usa JS click para não ser bloqueado por ui-widget-overlay transitório.
                await page.evaluate(
                    "document.querySelector('#btnGeraRelatorioPDF').click()"
                )

                # Passo 2: clica em #btnConsulta dentro do iframe para disparar download.
                # frame_locator() lida automaticamente com a navegação do iframe.
                async with page.expect_download(timeout=120_000) as dl_info:
                    await page.frame_locator("iframe#iFrameModal").locator(
                        "#btnConsulta"
                    ).click(timeout=45_000)

                download = await dl_info.value
                await download.save_as(output_path)
                self.logger.info(
                    f"PDF FRE gerado: {output_path} ({output_path.stat().st_size} bytes)"
                )
            finally:
                await context.close()
                await browser.close()

        return output_path


# =============================================================================
# Singleton
# =============================================================================

_enet_scraper: Optional[ENETScraper] = None


def get_enet_scraper() -> ENETScraper:
    """Retorna a instância singleton do ENETScraper."""
    global _enet_scraper
    if _enet_scraper is None:
        _enet_scraper = ENETScraper()
    return _enet_scraper
