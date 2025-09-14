import os
proxy_vars = [
    'HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 
    'ALL_PROXY', 'all_proxy', 'NO_PROXY', 'no_proxy'
]

for var in proxy_vars:
    if var in os.environ:
        print(f"Removing proxy env var: {var}={os.environ[var]}")
        del os.environ[var]
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from src.rag_module import RAGModule
from src.vectorization import VectorizationModule
from src.faiss_db_manager import FaissVectorDB
from src.gcp_storage_adapter import GCPStorageAdapter
from src.clinical_trials_rag_pipeline import ClinicalTrialsRAGPipeline

import openai
from langchain_core.documents import Document
from prompt import create_study_profile_prompt, create_one_vs_one_comparison_prompt, create_final_summary_prompt
import asyncio
from concurrent.futures import ThreadPoolExecutor
import os 
from dotenv import load_dotenv
load_dotenv()

class BenchmarkComparison:
    def __init__(self, api_key: Optional[str] = None,
                 model: str = os.getenv("MODEL_ID_GPT5", "gpt-5-2025-08-07"),
                 temperature: float = 0.0,
                 max_tokens: int = 1000):
        self.vectorizer = VectorizationModule()
        self.vector_db = FaissVectorDB()
        self.rag = RAGModule()
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        load_dotenv()
        
        # Set up OpenAI API key
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key not found")
        
        # Initialize OpenAI client
        self.client = openai.OpenAI(api_key=self.api_key)
        self.gcp_storage = GCPStorageAdapter(
            bucket_name="intraintel-cloudrun-clinical-volume",
            credentials_path="service_account_credentials.json"
        )
        
    def get_summary(self) -> str:
        return "Benchmark comparison between local and FDA agents"
        
    def query(self, question: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            model_id = context.get('model_id', 'medical_papers')
            top_k = context.get('top_k', 5)
            
            # Download and load index
            index_path = os.path.join("gcp-indexes", model_id)
            if not os.path.exists(index_path):
                if not self.gcp_storage.download_index_using_model_id(model_id, index_path):
                    raise ValueError(f"Failed to download index: {model_id}")
            
            if not self.vector_db.load(f"gcp-indexes/{model_id}"):
                raise ValueError(f"Failed to load index: {model_id}")
            
            # Process query
            query_embedding = self.vectorizer.embed_query(question)
            results, _ = self.vector_db.similarity_search(query_embedding, k=top_k)
            documents = self.vector_db.get_langchain_documents(results)
            
            return {
                "context": documents
            }
            
        except Exception as e:
            return {
                "answer": f"Error: {str(e)}",
                "citations": [],
                "confidence": 0.0
            }

    def create_local_study_profile(self, question: str, context: Optional[Dict[str, Any]] = None):
        full_context = self.query(question, context)
        # print(full_context)
        print(len(full_context['context']))
        print(type(full_context['context']))
        document_dicts = [{"metadata": doc.metadata, "page_content": doc.page_content} for doc in full_context["context"]]
        prompt = create_study_profile_prompt(document_dicts)
        # print("****************************")
        # print(prompt)
        # print("****************************")   
        
        # Call OpenAI API using chat completions
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are an expert medical research assistant specializing in evidence-based analysis of scientific literature."},
                {"role": "user", "content": prompt}
            ],
            # temperature=self.temperature,
            # max_tokens=self.max_tokens
        )
        
        answer = response.choices[0].message.content.strip()
        return answer

    def fetch_clinical_ncts(self, local_study: str):
        clinical_fetcher = ClinicalTrialsRAGPipeline(openai_client=self.client, model_name=self.model)
        fetch_result = clinical_fetcher.fetch_clinical_trials_data(local_study)
        trials_data = fetch_result['data']
        # print(f"Fetched (trials_data) clinical trials from ClinicalTrials.gov : {trials_data}")
        chunks = clinical_fetcher.process_and_chunk_data(trials_data)
        chunk_embeddings = clinical_fetcher.vectorize_chunks(chunks)
        context_result = clinical_fetcher.retrieve_relevant_context(local_study, chunk_embeddings, top_k=10)

        nct_data = {}
        nct_ids = []
        for entry in context_result['studies']:
            nct_id = entry['study_id']
            for entry in trials_data['studies']:
                if nct_id == entry['protocolSection']['identificationModule']['nctId']:
                    nct_data[nct_id] = entry
                    nct_ids.append(nct_id)
                    print(f"Matched NCT ID: {nct_id}")

        # print(nct_data)
        if nct_data:
            return {"success": True, "data": nct_data, "nct_ids": nct_ids}
        else:
            return {"success": False, "data": {}, "nct_ids": []}

    def create_benchmark_comparison_1_v_1(self, question: str, local_agent_summary: str, study_id: str, study_content: str):
        """
        Synchronous version for individual 1v1 comparisons
        """
        prompt = create_one_vs_one_comparison_prompt(
            query=question,
            user_study_profile=local_agent_summary,
            study_id=study_id,
            study_content=study_content
        )
        
        # Call OpenAI API using chat completions
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are an expert medical research assistant specializing in evidence-based analysis of scientific literature."},
                {"role": "user", "content": prompt}
            ],
            # temperature=self.temperature,
            # max_tokens=self.max_tokens
        )
        
        answer = response.choices[0].message.content.strip()
        return answer

    async def create_benchmark_comparison_1_v_1_async(self, question: str, local_agent_summary: str, study_id: str, study_content: str):
        """
        Async version for parallel processing of 1v1 comparisons
        """
        def _sync_comparison():
            return self.create_benchmark_comparison_1_v_1(question, local_agent_summary, study_id, study_content)
        
        # Run in executor to avoid blocking
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            result = await loop.run_in_executor(executor, _sync_comparison)
        return result

    def create_benchmark_comparison_combined(self, question: str, local_agent_summary: str, individual_reports: list[str]):
        prompt = create_final_summary_prompt(
            query=question,
            local_agent_summary=local_agent_summary,
            individual_reports=individual_reports
        )
        
        # Call OpenAI API using chat completions
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are an expert medical research assistant specializing in evidence-based analysis of scientific literature."},
                {"role": "user", "content": prompt}
            ],
            # temperature=self.temperature,
            # max_tokens=self.max_tokens
        )
        
        answer = response.choices[0].message.content.strip()
        return answer

    # Batch processing methods for multiple comparisons
    async def create_multiple_comparisons_parallel(self, question: str, local_agent_summary: str, 
                                                   clinical_trials_data: Dict[str, Any], 
                                                   max_workers: int = 5) -> list[str]:
        """
        Create multiple 1v1 comparisons in parallel
        """
        tasks = []
        for study_id, study_content in clinical_trials_data.items():
            task = self.create_benchmark_comparison_1_v_1_async(
                question=question,
                local_agent_summary=local_agent_summary,
                study_id=study_id,
                study_content=str(study_content)
            )
            tasks.append((study_id, task))
        
        # Execute all tasks concurrently
        individual_reports = []
        results = await asyncio.gather(*[task for _, task in tasks], return_exceptions=True)
        
        for i, result in enumerate(results):
            study_id = tasks[i][0]
            if isinstance(result, Exception):
                report_text = f"Error generating report for {study_id}: {str(result)}"
            else:
                report_text = f"Comparison report for NCT ID {study_id}:\n{result}"
            individual_reports.append(report_text)
        
        return individual_reports