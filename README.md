# DraftBench

DraftBench is an offline assistant designed for primary school teachers in Nepal. It converts informal classroom observation notes into structured Individualized Education Program (IEP) goals and printable student worksheets aligned with Curriculum Development Centre (CDC) standards.

The application runs entirely locally on standard laptop hardware without an internet connection.

## Features

- Offline Execution: Runs locally using quantized Qwen 2.5 models via Ollama or llama-cpp.
- Modular Workflow: Separate steps handle observation parsing, IEP goal formulation, cultural localization, and document formatting.
- Local RAG: Uses an embedded ChromaDB database to query indexed CDC curriculum guidelines.
- Cultural Adaptation: Replaces generic textbook examples with Nepalese currency, local flora, and regional contexts.
- Printable Exports: Generates printable worksheets and SVG digit-tracing sheets directly in the interface.

## Architecture

```text
React Frontend (Vite) <---> FastAPI Backend <---> Local LLM (Qwen 2.5)
                              |
                              +---> ChromaDB (CDC Guidelines)
```
