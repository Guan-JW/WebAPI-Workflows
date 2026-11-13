"""Load the pinned upstream app and build its RAGLite configuration.

The app's ``initialize_config`` (main.py L23-56) builds the configuration from the API keys typed
into the sidebar. ``build_config`` returns the same configuration with the two values listed in the
README's Adaptations section changed (answering LLM, reranker endpoint) and the database path
chosen by the driver. Every other value is the app's own.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP_PATH = "rag_tutorials/hybrid_search_rag"
DEFAULT_UPSTREAM = os.path.join(HERE, "upstream")
DEFAULT_RERANK_URL = "http://127.0.0.1:18444/v1/rerank"
RERANK_KEY = "local-sim"  # bearer token sent to the rerank stand-in, which does not check it
APP_SHA256 = "e099e9fe654ddb82083a1b255d1ca11fd1fab7579657e41acf6da9bc5d430cc2"  # main.py at the pinned commit


def app_dir(upstream_dir=None):
    return os.path.join(upstream_dir or DEFAULT_UPSTREAM, APP_PATH)


def load_app(upstream_dir=None):
    """Import the unmodified main.py. Environment settings come first (README, Adaptations)."""
    # litellm 1.53.9 otherwise downloads today's model map at import; its schema no longer parses,
    # raglite then assumes a 2048-token context and rag() refuses to run. Use the bundled map.
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    d = app_dir(upstream_dir)
    if not os.path.exists(os.path.join(d, "main.py")):
        raise SystemExit(f"upstream app not found at {d}; run fetch_upstream.sh first")
    if d not in sys.path:
        sys.path.insert(0, d)
    # Importing raglite 0.2.1 builds its default RAGLiteConfig (raglite/_cli.py), whose two FlashRank
    # rerankers load from ./.flashrank_cache and download about 120 MB there when missing. The
    # workload does not use them. Concurrent first imports in one directory would race on that
    # download, so client processes import one at a time.
    import fcntl

    os.makedirs(".flashrank_cache", exist_ok=True)
    with open(os.path.join(".flashrank_cache", ".import.lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        import main as app  # noqa: E402  the pinned app module

    return app


def build_config(db_path, rerank_url=DEFAULT_RERANK_URL):
    """main.py initialize_config with llm and the reranker URL changed (README, Adaptations)."""
    from raglite import RAGLiteConfig
    from rerankers import Reranker

    # The app's own Cohere client (rerankers APIRanker, model rerank-english-v3.0), pointed at the
    # stand-in service instead of api.cohere.ai. verbose=0 only silences the library's load message.
    ranker = Reranker("cohere", api_key=RERANK_KEY, lang="en", verbose=0)
    ranker.url = rerank_url
    return RAGLiteConfig(
        db_url=f"sqlite:///{db_path}",
        llm="gpt-4o-mini",
        embedder="text-embedding-3-large",
        embedder_normalize=True,
        chunk_max_size=2000,
        embedder_sentence_window_size=2,
        reranker=ranker,
    )


def install_config(config):
    """What the app's "Save Configuration" button does (main.py L145): keep the config in session state."""
    import streamlit as st

    st.session_state.my_config = config
