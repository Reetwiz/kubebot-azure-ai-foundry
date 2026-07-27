"""RAG knowledge base: local troubleshooting docs + scraped AKS/Kubernetes web
docs, embedded into a persisted ChromaDB store, plus the 'consult_knowledge_base'
tool the agent uses to search it.
"""

import os

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.tools import tool
from langchain_chroma import Chroma
from langchain_community.document_loaders import TextLoader, WebBaseLoader

from kubebot import config, llm
from kubebot.console import console

vector_db = None
retriever = None


def setup_vector_db():
    missing_files = [path for path in config.DOC_PATHS if not os.path.exists(path)]
    if missing_files:
        console.print(f"[bold red]Error:[/bold red] Missing local files: {missing_files}")
        raise FileNotFoundError(f"Missing files: {missing_files}")

    embeddings = llm.get_embeddings()

    if not os.path.exists(config.PERSIST_DIR):
        console.print("[yellow]Building Knowledge Base (Local + Web)...[/yellow]")
        try:
            all_docs = []

            for doc_path in config.DOC_PATHS:
                console.print(f"  [dim]Loading local: {doc_path}...[/dim]")
                loader = TextLoader(doc_path)
                all_docs.extend(loader.load())

            console.print(f"  [dim]Loading {len(config.WEB_DOC_URLS)} web pages... (This may take a moment)[/dim]")
            try:
                web_loader = WebBaseLoader(config.WEB_DOC_URLS)
                web_docs = web_loader.load()
                all_docs.extend(web_docs)
                console.print(f"  [dim]Scraped {len(web_docs)} pages successfully[/dim]")
            except Exception as e:
                console.print(f"[bold red]Warning:[/bold red] Failed to load web docs: {e}")
                console.print("Proceeding with local docs only...")

            console.print(f"  [dim]Splitting {len(all_docs)} documents...[/dim]")
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,  # Increased chunk size for web articles
                chunk_overlap=200
            )
            chunks = splitter.split_documents(all_docs)

            console.print(f"  [dim]Embedding {len(chunks)} chunks into ChromaDB...[/dim]")
            db = Chroma.from_documents(
                documents=chunks,
                embedding=embeddings,
                persist_directory=config.PERSIST_DIR
            )
            console.print(f"[green]SUCCESS:[/green] Knowledge Base Ready: {len(chunks)} total chunks")
            return db

        except Exception as e:
            console.print(f"[bold red]Error building knowledge base:[/bold red] {e}")
            raise
    else:
        console.print("[green]SUCCESS:[/green] Loading existing knowledge base")
        return Chroma(persist_directory=config.PERSIST_DIR, embedding_function=embeddings)


def init():
    """Build/load the vector DB and retriever. Must run after llm.init()."""
    global vector_db, retriever
    vector_db = setup_vector_db()
    # MMR (max-marginal-relevance) trades a little pure similarity for
    # diversity across the fetched candidates, and fetch_k widens the initial
    # candidate pool before re-ranking -- this makes multi-topic queries (e.g.
    # "BadUserInputException and JWT" ) more likely to surface chunks from
    # more than one relevant document, instead of k near-duplicate chunks
    # from a single lucky match.
    retriever = vector_db.as_retriever(
        search_type="mmr",
        search_kwargs={"k": 4, "fetch_k": 15},
    )


@tool
def consult_knowledge_base(query: str):
    """
    Searches the internal knowledge base for troubleshooting information

    1. INFRASTRUCTURE/KUBERNETES ISSUES:
       - CrashLoopBackOff, ImagePullBackOff, OOMKilled
       - Pending pods, NodeNotReady
       - Ingress issues, PVC problems
       - ConfigMap/Secret mounting issues
       - Storage classes, persistent volumes, and scaling (HPA/VPA/Cluster Autoscaler/KEDA)

     2. APPLICATION ERRORS:
         - Invalid request parameters or missing required fields
         - Expired authentication tokens and insufficient permissions
         - Unavailable dependencies and database connection failures
         - Unhandled internal errors

     3. API CONTRACT AND QUERY PATTERNS:
         - How to format array parameters
       - Date range query formats (ISO 8601)
       - Array parameters in GET requests
       - Required fields for booking/slot/campaign endpoints

     4. APPLICATION ARCHITECTURE:
         - Multi-tenant data isolation
       - JWT authentication requirements
       - Health check endpoint usage
       - Common kubectl commands for scheduling pods

    Only call this for the specific error codes/exception names/topics listed
    above -- do not use it for generic conversation or questions already
    answerable from live cluster data.

    Args:
        query: The specific error message, exception name, API question, or component to search for
    """
    try:
        if config.DEV_MODE:
            console.print(f"[dim cyan]RAG Query: '{query}'[/dim cyan]")

        docs = retriever.invoke(query)

        if not docs:
            if config.DEV_MODE:
                console.print("[dim yellow]WARNING: RAG: No documents found[/dim yellow]")
            return "No relevant documentation found for this query."

        if config.DEV_MODE:
            console.print(f"[dim green]SUCCESS: RAG: Retrieved {len(docs)} relevant chunks[/dim green]")

        result = "Knowledge Base Results:\n\n"
        sections = []
        for d in docs:
            source = d.metadata.get("source", "unknown source")
            sections.append(f"[Source: {source}]\n{d.page_content}")
        result += "\n\n---\n\n".join(sections)
        return result
    except Exception as e:
        if config.DEV_MODE:
            console.print(f"[dim red]ERROR: RAG Error: {str(e)}[/dim red]")
        return f"ERROR: Error searching knowledge base: {str(e)}"
