# AI Data Analysis & Insight Agent Platform

[![FastAPI](https://img.shields.io/badge/FastAPI-0.109.0-009688.svg?style=flat&logo=FastAPI&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A production-grade backend system that enables users to interact with their datasets using natural language queries. Powered by LLMs and agent-based architectures, the platform automatically analyzes data, generates visualizations, and produces actionable insights.

## 🌟 Features

- **Natural Language Queries**: Ask questions in plain English
- **AI-Powered Analysis**: LangChain agents orchestrate intelligent data exploration
- **LLM Relevance Guard**: Validates query relevance before processing
- **Automatic Visualizations**: Context-aware chart generation with Plotly
- **Insight Generation**: Natural language summaries and recommendations
- **Redis Caching**: Lightning-fast repeat query responses
- **Multi-Format Support**: CSV and Excel file handling
- **RESTful API**: Clean, documented endpoints
- **Async Architecture**: Non-blocking FastAPI with SQLAlchemy 2.0
- **Docker Ready**: Complete containerized deployment

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    FastAPI Server                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │   Upload    │  │   Metadata  │  │    Query    │    │
│  │  Endpoint   │  │  Endpoint   │  │  Endpoint   │    │
│  └─────────────┘  └─────────────┘  └─────────────┘    │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│            LLM Orchestration Layer                       │
│  ┌─────────────────────────────────────────────────┐   │
│  │  Relevance Guard (OpenAI GPT-3.5-Turbo)         │   │
│  └─────────────────────────────────────────────────┘   │
│                          ↓                               │
│  ┌─────────────────────────────────────────────────┐   │
│  │  Data Analyst Agent (LangChain ReAct)           │   │
│  │  - Task Planning                                │   │
│  │  - Tool Execution                               │   │
│  │  - Result Synthesis                             │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│                   Tool Execution Layer                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │  Load    │ │ Analyze  │ │Visualize │ │ Insights │ │
│  │ Dataset  │ │   Data   │ │   Data   │ │Generator │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│              Data Storage & Cache                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐             │
│  │PostgreSQL│  │  Redis   │  │   File   │             │
│  │ Metadata │  │  Cache   │  │ Storage  │             │
│  └──────────┘  └──────────┘  └──────────┘             │
└─────────────────────────────────────────────────────────┘
```

## 📋 Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- Docker & Docker Compose (optional)
- OpenAI API Key

## 🚀 Quick Start

### 1. Clone and Setup

```bash
# Clone repository
cd ai-data-analysis-platform

# Copy environment file
cp .env.example .env

# Edit .env and add your OpenAI API key
nano .env
```

### 2. Using Docker (Recommended)

```bash
# Start all services
docker-compose up --build

# The API will be available at http://localhost:8000
# API docs at http://localhost:8000/docs
```

### 3. Manual Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Setup PostgreSQL database
createdb ai_platform_db

# Run migrations
alembic upgrade head

# Start Redis
redis-server

# Run the application
uvicorn app.main:app --reload
```

## 📖 API Documentation

### Upload Dataset

```bash
curl -X POST "http://localhost:8000/api/v1/datasets/upload" \
  -F "file=@sales_data.csv"
```

Response:
```json
{
  "dataset_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "sales_data.csv",
  "status": "ready",
  "metadata": {
    "rows": 1000,
    "columns": 4,
    "column_names": ["date", "product", "region", "revenue"]
  }
}
```

### Query Dataset

```bash
curl -X POST "http://localhost:8000/api/v1/queries/datasets/{dataset_id}/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "Which region has the highest revenue?"}'
```

Response:
```json
{
  "query_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "answer": "The North region generated the highest revenue with $2,456,789.50, accounting for 35% of total sales.",
  "visualizations": [{
    "type": "bar",
    "title": "Revenue by Region",
    "data": {...}
  }],
  "insights": {
    "summary": "North region leads in revenue generation",
    "key_findings": [
      "North: $2,456,789.50 (35%)",
      "South: $2,100,234.75 (30%)"
    ]
  },
  "execution_time": 2.34,
  "cache_hit": false
}
```

### Interactive API Documentation

Visit `http://localhost:8000/docs` for Swagger UI with all endpoints.

## 🛠️ Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Web Framework** | FastAPI 0.109 | High-performance async API |
| **Database** | PostgreSQL 15 | Relational data storage |
| **ORM** | SQLAlchemy 2.0 | Async database operations |
| **Cache** | Redis 7 | Query result caching |
| **LLM** | OpenAI GPT-3.5-Turbo | Natural language processing |
| **Agent Framework** | LangChain Classic | ReAct pattern orchestration |
| **Data Processing** | Pandas 2.1 | DataFrame operations |
| **Visualization** | Plotly 5.18 | Interactive charts |
| **Migrations** | Alembic 1.13 | Database schema management |
| **Server** | Uvicorn | ASGI server |

## 📁 Project Structure

```
ai-data-analysis-platform/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application
│   ├── config.py               # Configuration management
│   ├── database.py             # Database connection
│   ├── models/                 # SQLAlchemy models
│   │   └── dataset.py
│   ├── schemas/                # Pydantic schemas
│   │   ├── dataset.py
│   │   └── query.py
│   ├── api/
│   │   └── v1/
│   │       └── endpoints/
│   │           ├── datasets.py  # Dataset endpoints
│   │           └── queries.py   # Query endpoints
│   ├── services/               # Business logic
│   │   ├── dataset_service.py
│   │   ├── query_service.py
│   │   ├── metadata_extractor.py
│   │   └── cache_service.py
│   ├── agents/                 # AI agents
│   │   ├── relevance_guard.py
│   │   └── data_analyst_agent.py
│   ├── tools/                  # Agent tools
│   │   ├── dataset_tools.py
│   │   ├── analysis_tools.py
│   │   ├── visualization_tools.py
│   │   └── insight_tools.py
│   └── utils/                  # Utilities
│       ├── error_handlers.py
│       └── file_utils.py
├── alembic/                    # Database migrations
│   ├── versions/
│   └── env.py
├── uploads/                    # Uploaded datasets
├── .env.example               # Environment template
├── .gitignore
├── alembic.ini
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── README.md
└── DO_IT_YOURSELF.md          # Learning guide
```

## 🔐 Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Required |
| `REDIS_URL` | Redis connection string | Required |
| `OPENAI_API_KEY` | OpenAI API key | Required |
| `OPENAI_MODEL` | OpenAI model to use | gpt-3.5-turbo |
| `UPLOAD_DIR` | Directory for uploads | ./uploads |
| `MAX_UPLOAD_SIZE` | Max file size in bytes | 104857600 (100MB) |
| `CACHE_TTL` | Cache expiration (seconds) | 3600 |
| `ENABLE_CACHE` | Enable Redis caching | True |
| `AGENT_MAX_ITERATIONS` | Max agent iterations | 10 |

## 📊 Example Use Cases

1. **Sales Analysis**: "What were our top 5 products by revenue last quarter?"
2. **Trend Detection**: "Show me the sales trend over the past 12 months"
3. **Comparative Analysis**: "Compare revenue between regions"
4. **Statistical Insights**: "What's the average order value by customer segment?"
5. **Data Exploration**: "What are the most common categories in this dataset?"

## 🧪 Testing

```bash
# Run with pytest (not included in this version)
pytest

# Manual testing with curl
curl http://localhost:8000/health
```

## 🐛 Troubleshooting

### Common Issues

**Database Connection Error**
```bash
# Ensure PostgreSQL is running
docker-compose ps postgres

# Check logs
docker-compose logs postgres
```

**Redis Connection Error**
```bash
# Check Redis status
docker-compose ps redis

# Test connection
redis-cli ping
```

**OpenAI API Errors**
- Verify API key in `.env`
- Check API quota and billing

## 📝 License

MIT License - see LICENSE file for details

## 🤝 Contributing

Contributions welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch
3. Commit changes
4. Push to the branch
5. Open a pull request

## 📧 Support

For issues and questions:
- Open a GitHub issue
- Check `DO_IT_YOURSELF.md` for detailed guidance

## 🚧 Roadmap

- [ ] Multi-dataset queries
- [ ] Advanced ML model training
- [ ] Real-time data connections
- [ ] Scheduled reports
- [ ] Export to PDF/PowerPoint
- [ ] Team collaboration features

---

**Built with ❤️ using FastAPI, LangChain, and OpenAI**
