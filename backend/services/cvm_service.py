"""
CVM Analyzer - CVM Service
===========================

Serviço para buscar e listar documentos (FRE, DFP, FCA, IPE) de qualquer empresa
aberta brasileira a partir dos CSVs abertos da CVM.

Fontes: https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/{TIPO}/DADOS/
"""

import asyncio
import io
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict
from urllib.parse import urlparse, parse_qs
import logging

import httpx
import pandas as pd

from config import get_settings, Settings
from utils import get_cache_manager, get_logger, download_with_retry, download_with_retry_sync


# URLs dos ZIPs anuais por tipo de documento
_CVM_ZIP_URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FRE/DADOS/fre_cia_aberta_{year}.zip"

_DOC_ZIP_URLS = {
    "FRE": "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FRE/DADOS/fre_cia_aberta_{year}.zip",
    "DFP": "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/dfp_cia_aberta_{year}.zip",
    "FCA": "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FCA/DADOS/fca_cia_aberta_{year}.zip",
    "IPE": "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_{year}.zip",
}


class CVMService:
    """
    Serviço genérico para acesso aos dados de FRE de qualquer empresa aberta
    publicados pela CVM. Suporta busca por nome/CNPJ e download de PDFs com cache.
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.settings = settings or get_settings()
        self.logger = logger or get_logger()
        self.cache = get_cache_manager()
        # Cache em memória dos DataFrames por ano (chave: ano int)
        self._csv_cache: Dict[int, pd.DataFrame] = {}
        # Cache em memória para CSVs multi-tipo (chave: "{TIPO}_{year}")
        self._doc_csv_cache: Dict[str, pd.DataFrame] = {}

    # ─── CSV loading ──────────────────────────────────────────────────────────

    async def _load_year_csv(self, year: int) -> pd.DataFrame:
        """Baixa e cacheia o CSV anual de FREs da CVM."""
        if year in self._csv_cache:
            return self._csv_cache[year]

        url = _CVM_ZIP_URL.format(year=year)
        cache_key = f"cvm_csv/fre_cia_aberta_{year}.csv"

        # Tenta cache em disco (CSV já extraído)
        cached_path = self.cache.get(cache_key)
        if cached_path:
            try:
                df = pd.read_csv(cached_path, sep=";", encoding="latin-1", dtype=str)
                self._csv_cache[year] = df
                self.logger.info(f"CSV {year} carregado do cache: {len(df)} registros")
                return df
            except Exception as exc:
                self.logger.warning(f"Cache CSV corrompido para {year}: {exc}")

        # Download do ZIP
        self.logger.info(f"Baixando ZIP CVM {year}: {url}")
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.get(url, follow_redirects=True)
                resp.raise_for_status()
                zip_content = resp.content
        except Exception as exc:
            self.logger.error(f"Falha ao baixar ZIP CVM {year}: {exc}")
            return pd.DataFrame()

        # Extrai o CSV do ZIP
        try:
            with zipfile.ZipFile(io.BytesIO(zip_content)) as zf:
                csv_names = [n for n in zf.namelist() if n.endswith(".csv")]
                if not csv_names:
                    self.logger.error(f"Nenhum CSV encontrado no ZIP {year}")
                    return pd.DataFrame()
                csv_content = zf.read(csv_names[0])
        except Exception as exc:
            self.logger.error(f"Falha ao extrair CSV do ZIP {year}: {exc}")
            return pd.DataFrame()

        # Salva CSV extraído no cache
        try:
            self.cache.put(cache_key, csv_content, pinned=False)
        except Exception as exc:
            self.logger.warning(f"Não foi possível cachear CSV {year}: {exc}")

        df = pd.read_csv(io.BytesIO(csv_content), sep=";", encoding="latin-1", dtype=str)
        self._csv_cache[year] = df
        self.logger.info(f"CSV {year} extraído do ZIP: {len(df)} registros")
        return df

    async def _load_doc_csv(self, tipo: str, year: int, force: bool = False) -> pd.DataFrame:
        """Baixa e cacheia o CSV anual de qualquer tipo de documento (FRE/DFP/FCA/IPE)."""
        cache_key_mem = f"{tipo}_{year}"

        if force:
            # Limpa cache em memória e em disco antes de re-baixar
            self._doc_csv_cache.pop(cache_key_mem, None)
            disk_key = f"cvm_csv/{tipo.lower()}_{year}.csv"
            existing = self.cache.get(disk_key)
            if existing and existing.exists():
                try:
                    existing.unlink()
                except Exception:
                    pass

        if cache_key_mem in self._doc_csv_cache:
            return self._doc_csv_cache[cache_key_mem]

        url = _DOC_ZIP_URLS[tipo].format(year=year)
        cache_key = f"cvm_csv/{tipo.lower()}_{year}.csv"

        cached_path = self.cache.get(cache_key)
        if cached_path:
            try:
                df = pd.read_csv(cached_path, sep=";", encoding="latin-1", dtype=str)
                self._doc_csv_cache[cache_key_mem] = df
                self.logger.info(f"CSV {tipo} {year} carregado do cache: {len(df)} registros")
                return df
            except Exception as exc:
                self.logger.warning(f"Cache CSV corrompido para {tipo} {year}: {exc}")

        self.logger.info(f"Baixando ZIP CVM {tipo} {year}: {url}")
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.get(url, follow_redirects=True)
                resp.raise_for_status()
                zip_content = resp.content
        except Exception as exc:
            self.logger.error(f"Falha ao baixar ZIP CVM {tipo} {year}: {exc}")
            return pd.DataFrame()

        try:
            # O CSV principal tem sempre o mesmo nome do ZIP: {tipo}_cia_aberta_{year}.csv
            target_csv = f"{tipo.lower()}_cia_aberta_{year}.csv"
            with zipfile.ZipFile(io.BytesIO(zip_content)) as zf:
                available = zf.namelist()
                # Procura pelo nome exato (pode estar em subpasta)
                match = next((n for n in available if n.endswith(target_csv)), None)
                if match is None:
                    self.logger.error(f"CSV '{target_csv}' não encontrado no ZIP {tipo} {year}. Disponíveis: {available[:5]}")
                    return pd.DataFrame()
                csv_content = zf.read(match)
        except Exception as exc:
            self.logger.error(f"Falha ao extrair CSV do ZIP {tipo} {year}: {exc}")
            return pd.DataFrame()

        try:
            self.cache.put(cache_key, csv_content, pinned=False)
        except Exception as exc:
            self.logger.warning(f"Não foi possível cachear CSV {tipo} {year}: {exc}")

        df = pd.read_csv(io.BytesIO(csv_content), sep=";", encoding="latin-1", dtype=str)
        self._doc_csv_cache[cache_key_mem] = df
        self.logger.info(f"CSV {tipo} {year} extraído: {len(df)} registros")
        return df

    @staticmethod
    def _s(val) -> str:
        """Converte valor pandas para string, tratando NaN como string vazia."""
        import math
        if val is None:
            return ""
        try:
            if math.isnan(float(val)):
                return ""
        except (TypeError, ValueError):
            pass
        return str(val).strip()

    def _normalize_doc_row(self, tipo: str, row) -> Optional[Dict]:
        """Normaliza uma linha do CSV para o formato comum de documento."""
        s = self._s
        try:
            if tipo == "IPE":
                link = s(row.get("Link_Download", ""))
                params = parse_qs(urlparse(link).query)
                id_doc = params.get("numSequencia", [""])[0]
                num_versao = params.get("numVersao", [""])[0]
                num_protocolo = params.get("numProtocolo", [""])[0]
                return {
                    "tipo_doc": "IPE",
                    "cnpj": s(row.get("CNPJ_Companhia", "")),
                    "nome_empresa": s(row.get("Nome_Companhia", "")),
                    "dt_refer": s(row.get("Data_Referencia", "")),
                    "versao": s(row.get("Versao", "")),
                    "id_doc": id_doc,
                    "link_doc": link,
                    "dt_receb": s(row.get("Data_Entrega", "")),
                    "categoria": s(row.get("Categoria", "")),
                    "tipo": s(row.get("Tipo", "")),
                    "assunto": s(row.get("Assunto", "")),
                    "num_protocolo": num_protocolo,
                    "num_versao": num_versao,
                }
            else:
                return {
                    "tipo_doc": tipo,
                    "cnpj": s(row.get("CNPJ_CIA", "")),
                    "nome_empresa": s(row.get("DENOM_CIA", "")),
                    "dt_refer": s(row.get("DT_REFER", "")),
                    "versao": s(row.get("VERSAO", "")),
                    "id_doc": s(row.get("ID_DOC", "")),
                    "link_doc": s(row.get("LINK_DOC", "")),
                    "dt_receb": s(row.get("DT_RECEB", "")),
                    "categoria": "",
                    "tipo": "",
                    "assunto": "",
                    "num_protocolo": "",
                    "num_versao": "",
                }
        except Exception as exc:
            self.logger.warning(f"Erro ao normalizar linha {tipo}: {exc}")
            return None

    async def get_company_documents(
        self,
        cnpj: str,
        tipos: Optional[List[str]] = None,
        years: Optional[List[int]] = None,
    ) -> List[Dict]:
        """
        Retorna lista unificada de documentos (FRE/DFP/FCA/IPE) de uma empresa
        a partir dos CSVs abertos da CVM.

        Campos retornados: tipo_doc, cnpj, nome_empresa, dt_refer, versao,
        id_doc, link_doc, dt_receb, categoria, tipo, assunto,
        num_protocolo (IPE), num_versao (IPE).
        """
        if tipos is None:
            tipos = ["FRE", "DFP", "FCA", "IPE"]
        if years is None:
            current_year = datetime.utcnow().year
            years = list(range(current_year - 3, current_year + 1))

        cnpj_norm = cnpj.strip()

        tasks = []
        task_meta = []
        for tipo in tipos:
            if tipo not in _DOC_ZIP_URLS:
                continue
            for year in years:
                tasks.append(self._load_doc_csv(tipo, year))
                task_meta.append((tipo, year))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        docs = []
        for (tipo, year), result in zip(task_meta, results):
            if isinstance(result, Exception):
                self.logger.warning(f"Erro ao carregar CSV {tipo} {year}: {result}")
                continue
            df = result
            if df.empty:
                continue

            cnpj_col = "CNPJ_Companhia" if tipo == "IPE" else "CNPJ_CIA"
            if cnpj_col not in df.columns:
                continue

            filtered = df[df[cnpj_col].str.strip() == cnpj_norm]
            for _, row in filtered.iterrows():
                doc = self._normalize_doc_row(tipo, row)
                if doc:
                    docs.append(doc)

        # Remove duplicatas por (tipo_doc, id_doc, versao)
        seen = set()
        unique_docs = []
        for doc in docs:
            key = (doc["tipo_doc"], doc["id_doc"], doc["versao"])
            if key not in seen:
                seen.add(key)
                unique_docs.append(doc)

        unique_docs.sort(key=lambda d: d["dt_refer"], reverse=True)
        return unique_docs

    # ─── Public API ───────────────────────────────────────────────────────────

    async def search_companies(
        self,
        query: str,
        year: int = 2024,
        years: Optional[List[int]] = None,
    ) -> List[Dict]:
        """
        Busca empresas pelo nome (DENOM_CIA) ou CNPJ (CNPJ_CIA).

        Por padrão combina os CSVs dos últimos 5 anos para garantir cobertura
        completa (empresas que saíram de bolsa em anos recentes continuam visíveis).
        O parâmetro ``year`` é mantido por compatibilidade mas ignorado quando
        ``years`` não é informado.

        Retorna lista de dicts com { cnpj, name, cod_cvm } sem duplicatas,
        limitada a 50 resultados ordenados alfabeticamente pelo nome.
        """
        if years is None:
            current_year = datetime.utcnow().year
            # Inclui os últimos 5 anos disponíveis para máxima cobertura
            years = list(range(current_year - 4, current_year + 1))

        # Carrega todos os anos em paralelo
        tasks = [self._load_year_csv(y) for y in years]
        dfs_raw = await asyncio.gather(*tasks, return_exceptions=True)

        # Combina apenas os DataFrames válidos
        frames = []
        for y, result in zip(years, dfs_raw):
            if isinstance(result, Exception):
                self.logger.warning(f"Ignorando CSV {y} na busca: {result}")
                continue
            if not result.empty:
                frames.append(result)

        if not frames:
            return []

        # Concatena e desduplicata por CNPJ mantendo o registro mais recente
        # (ao concatenar na ordem crescente de ano, o último registro por CNPJ
        # corresponde ao ano mais atual)
        combined = pd.concat(frames, ignore_index=True)

        query_lower = query.strip().lower()
        if not query_lower:
            hits = combined
        else:
            mask = (
                combined["CNPJ_CIA"].str.lower().str.contains(query_lower, na=False)
                | combined["DENOM_CIA"].str.lower().str.contains(query_lower, na=False)
            )
            hits = combined[mask]

        # Desduplicata por CNPJ: mantém o registro mais recente (último por DT_REFER)
        hits_dedup = (
            hits.sort_values("DT_REFER", ascending=True)
            .drop_duplicates(subset=["CNPJ_CIA"], keep="last")
            .sort_values("DENOM_CIA")
        )

        results = []
        for _, row in hits_dedup.iterrows():
            cnpj = str(row.get("CNPJ_CIA", "")).strip()
            if not cnpj:
                continue
            results.append({
                "cnpj": cnpj,
                "name": str(row.get("DENOM_CIA", "")).strip(),
                "cod_cvm": str(row.get("CD_CVM", "")).strip(),
            })
            if len(results) >= 50:
                break

        return results

    async def get_company_fres(self, cnpj: str, years: Optional[List[int]] = None) -> pd.DataFrame:
        """
        Retorna um DataFrame com todos os FREs de uma empresa (filtrado por CNPJ_CIA)
        para os anos indicados.

        Colunas relevantes: DT_REFER, VERSAO, LINK_DOC, DENOM_CIA, TIPO_DOC
        """
        if years is None:
            current_year = datetime.utcnow().year
            years = list(range(current_year - 3, current_year + 1))

        cnpj_norm = cnpj.strip()
        frames = []
        tasks = [self._load_year_csv(y) for y in years]
        dfs = await asyncio.gather(*tasks, return_exceptions=True)

        for year, result in zip(years, dfs):
            if isinstance(result, Exception):
                self.logger.warning(f"Erro ao carregar CSV {year}: {result}")
                continue
            df = result
            if df.empty:
                continue
            filtered = df[df["CNPJ_CIA"].str.strip() == cnpj_norm]
            if not filtered.empty:
                frames.append(filtered)

        if not frames:
            return pd.DataFrame()

        combined = pd.concat(frames, ignore_index=True)
        # Normaliza colunas essenciais.
        # ATENÇÃO: o CSV da CVM NÃO possui coluna TIPO_DOC.
        # A coluna real equivalente é CATEG_DOC (valor fixo "FRE WEB").
        # ID_DOC é o identificador numérico do documento no sistema RAD da CVM.
        for col in ("DT_REFER", "VERSAO", "LINK_DOC", "DENOM_CIA", "CATEG_DOC", "ID_DOC"):
            if col not in combined.columns:
                combined[col] = ""
        combined = combined.sort_values("DT_REFER", ascending=False)
        return combined

    async def download_pdf(
        self,
        link_doc: str,
        dt_refer: str,
        versao: int,
        cnpj: str = "",
        company_name: str = "",
        pin: bool = True,
    ) -> Path:
        """Download e cache de um PDF de FRE. Usa web_search como fallback."""
        cnpj_slug = cnpj.replace("/", "_").replace(".", "_").replace("-", "_").strip("_")
        if cnpj_slug:
            cache_key = f"pdfs/{cnpj_slug}/{dt_refer}_v{versao}.pdf"
        else:
            cache_key = f"pdfs/fre_{dt_refer}_v{versao}.pdf"

        cached_path = self.cache.get(cache_key)
        if cached_path:
            self.logger.info(f"PDF em cache: {cache_key}")
            return cached_path

        source_url = link_doc
        self.logger.info(f"Baixando PDF: {link_doc}")
        content = await download_with_retry(
            link_doc,
            timeout=self.settings.download_timeout,
            max_retries=self.settings.download_max_retries,
            logger=self.logger,
        )
        if not content.startswith(b"%PDF"):
            raise ValueError(
                f"PDF não encontrado. O link da CVM ({link_doc}) não contém PDF válido."
            )

        path = self.cache.put(
            cache_key,
            content,
            pinned=pin,
            metadata={
                "dt_refer": dt_refer,
                "versao": versao,
                "cnpj": cnpj,
                "source_url": source_url,
                "downloaded_at": datetime.utcnow().isoformat(),
            },
        )
        self.logger.info(f"PDF cacheado: {cache_key} ({len(content)} bytes)")
        return path

    def download_pdf_sync(
        self,
        link_doc: str,
        dt_refer: str,
        versao: int,
        cnpj: str = "",
        pin: bool = True,
    ) -> Path:
        """Versão síncrona de download_pdf."""
        cnpj_slug = cnpj.replace("/", "_").replace(".", "_").replace("-", "_").strip("_")
        if cnpj_slug:
            cache_key = f"pdfs/{cnpj_slug}/{dt_refer}_v{versao}.pdf"
        else:
            cache_key = f"pdfs/fre_{dt_refer}_v{versao}.pdf"

        cached_path = self.cache.get(cache_key)
        if cached_path:
            self.logger.info(f"PDF em cache: {cache_key}")
            return cached_path

        self.logger.info(f"Baixando PDF (sync): {link_doc}")
        content = download_with_retry_sync(
            link_doc,
            timeout=self.settings.download_timeout,
            max_retries=self.settings.download_max_retries,
            logger=self.logger,
        )

        if not content.startswith(b"%PDF"):
            raise ValueError(f"Conteúdo baixado de {link_doc} não é um PDF válido")

        path = self.cache.put(
            cache_key,
            content,
            pinned=pin,
            metadata={
                "dt_refer": dt_refer,
                "versao": versao,
                "cnpj": cnpj,
                "link_doc": link_doc,
                "downloaded_at": datetime.utcnow().isoformat(),
            },
        )
        self.logger.info(f"PDF cacheado: {cache_key} ({len(content)} bytes)")
        return path


# =============================================================================
# Singleton
# =============================================================================

_cvm_service: Optional[CVMService] = None


def get_cvm_service() -> CVMService:
    """Retorna a instância singleton do CVMService."""
    global _cvm_service
    if _cvm_service is None:
        _cvm_service = CVMService()
    return _cvm_service
