# DO IT YOURSELF: Learning Guide
## AI Data Analysis & Insight Agent Platform

Welcome! This guide will help you understand the platform architecture, learn how each component works, and extend the system with new capabilities.

---

## 📚 Table of Contents

1. [System Overview](#system-overview)
2. [Core Concepts](#core-concepts)
3. [Understanding the Code](#understanding-the-code)
4. [How Data Flows](#how-data-flows)
5. [The Agent System](#the-agent-system)
6. [Adding New Features](#adding-new-features)
7. [Common Customizations](#common-customizations)
8. [Debugging Tips](#debugging-tips)
9. [Performance Optimization](#performance-optimization)
10. [Learning Resources](#learning-resources)

---

## System Overview

### What This Platform Does

The AI Data Analysis Platform is a backend system that:
1. Accepts dataset uploads (CSV/Excel)
2. Validates questions using LLM-based guards
3. Uses AI agents to analyze data
4. Generates visualizations automatically
5. Produces natural language insights

### Key Architecture Components

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  FastAPI    │───▶│  Services   │───▶│   Agents    │
│  Endpoints  │    │   Layer     │    │   & Tools   │
└─────────────┘    └─────────────┘    └─────────────┘
       │                  │                    │
       ▼                  ▼                    ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  Database   │    │    Redis    │    │   OpenAI    │
│ PostgreSQL  │    │    Cache    │    │     API     │
└─────────────┘    └─────────────┘    └─────────────┘
```

---

## Core Concepts

### 1. Async/Await Pattern

This platform uses Python's async/await for non-blocking I/O:

```python
# Synchronous (blocking)
def get_data():
    result = database.query()  # Blocks until done
    return result

# Asynchronous (non-blocking)
async def get_data():
    result = await database.query()  # Allows other tasks
    return result
```

**Why it matters**: Handles multiple requests simultaneously without waiting.

### 2. SQLAlchemy 2.0 Async

Modern ORM with async support:

```python
# Creating a session
async with AsyncSessionLocal() as session:
    result = await session.execute(select(Dataset))
    datasets = result.scalars().all()
```

**Key differences from sync SQLAlchemy**:
- Use `async with` for sessions
- Await all database operations
- Use `AsyncSession` instead of `Session`

### 3. LangChain ReAct Agents

The agent follows the Reasoning-Action pattern:

```
Thought: What do I need to do?
Action: load_dataset
Observation: Dataset has columns: date, product, revenue
Thought: Now I should analyze revenue by product
Action: execute_python
Action Input: print(df.groupby('product')['revenue'].sum().nlargest(5))
Observation: Widget A: $500,000 ...
Thought: I can create a visualization
Action: create_visualization
...
Final Answer: Widget A generated the most revenue
```

### 4. Pydantic V2 Schemas

Type-safe request/response validation:

```python
class QueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    
# FastAPI automatically validates:
@router.post("/query")
async def query(request: QueryRequest):  # ✓ Validated!
    ...
```

---

## Understanding the Code

### File Organization

#### `app/main.py` - Application Entry Point

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Connect to Redis
    await cache_service.connect()
    yield
    # Shutdown: Cleanup
    await cache_service.disconnect()
```

**What it does**:
- Initializes FastAPI app
- Sets up CORS middleware
- Registers exception handlers
- Manages application lifecycle

#### `app/config.py` - Configuration Management

```python
class Settings(BaseSettings):
    DATABASE_URL: str
    OPENAI_API_KEY: str
    
    model_config = SettingsConfigDict(env_file=".env")
```

**How to add a new setting**:
1. Add field to `Settings` class
2. Add to `.env.example`
3. Access via `settings.YOUR_SETTING`

#### `app/database.py` - Database Connection

```python
engine = create_async_engine(settings.DATABASE_URL)
AsyncSessionLocal = async_sessionmaker(engine)
```

**Understanding sessions**:
- Sessions are short-lived
- Each request gets its own session
- Always close sessions (handled by dependency)

#### `app/models/dataset.py` - Database Models

```python
class Dataset(Base):
    __tablename__ = "datasets"
    id = Column(UUID, primary_key=True)
    # Relationships
    queries = relationship("Query", back_populates="dataset")
```

**Key SQLAlchemy concepts**:
- `Base` = declarative base for all models
- `__tablename__` = actual database table name
- `relationship()` = defines associations

#### `app/services/` - Business Logic Layer

**Why separate services?**
- Keeps endpoints clean
- Reusable logic
- Easier to test
- Clear separation of concerns

Example pattern:
```python
# Endpoint (thin layer)
@router.post("/upload")
async def upload(file: UploadFile, db: AsyncSession):
    service = DatasetService(db)
    return await service.upload_dataset(file)

# Service (thick layer with logic)
class DatasetService:
    async def upload_dataset(self, file):
        # Validate
        # Process
        # Save
        # Return
```

---

## How Data Flows

### Upload Flow

```
1. User uploads CSV/Excel
   ↓
2. FastAPI receives file
   ↓
3. DatasetService.upload_dataset()
   ↓
4. Save file to disk
   ↓
5. MetadataExtractor.extract_metadata()
   ├─ Load into Pandas DataFrame
   ├─ Extract column names/types
   ├─ Calculate statistics
   └─ Get sample rows
   ↓
6. Create Dataset record in PostgreSQL
   ↓
7. Return dataset_id to user
```

### Query Flow

```
1. User sends question
   ↓
2. Check Redis cache
   ├─ Cache hit → Return cached result
   └─ Cache miss → Continue
   ↓
3. RelevanceGuard.validate_query()
   ├─ Build dataset context
   ├─ Ask GPT-4o-mini: "Is this question relevant?"
   ├─ If NO → Raise IrrelevantQuestionError
   └─ If YES → Continue
   ↓
4. Load dataset from file
   ↓
5. DataAnalystAgent.analyze()
   ├─ Initialize LangChain agent
   ├─ Load dataset into context
   ├─ Run ReAct loop:
   │   ├─ Think
   │   ├─ Choose tool
   │   ├─ Execute tool
   │   └─ Observe result
   └─ Generate final answer
   ↓
6. Generate insights (if requested)
   ↓
7. Save Query record to database
   ↓
8. Cache result in Redis
   ↓
9. Return to user
```

---

## The Agent System

### How LangChain Agents Work

**The ReAct Pattern**:
```
ReAct = Reasoning + Acting

Step 1: Think about the task
Step 2: Choose an action (tool)
Step 3: Execute the action
Step 4: Observe the result
Step 5: Think about next step
...repeat until solved...
Step N: Provide final answer
```

### Understanding Tools

Tools are functions the agent can call:

```python
def execute_python_func(code: str) -> str:
    """
    Executes Python code against the loaded dataset.
    Input is raw Python code (not JSON).
    """
    # Run code in restricted sandbox
    return captured_stdout

# Wrap in LangChain Tool
execute_python_tool = Tool(
    name="execute_python",
    description="Execute Python code to analyze the dataset...",
    func=execute_python_func
)
```

**Key points**:
- Tool names should be descriptive
- Description guides the agent when to use it
- `execute_python` accepts raw code; other tools accept JSON strings
- Tools should be focused (do one thing well)

### Agent Execution Example

Given question: "What's the average revenue by region?"

```
Agent thinks: "I need to load the dataset first"
→ Action: load_dataset
→ Observation: "Dataset has columns: region, revenue..."

Agent thinks: "I should group by region and calculate mean"
→ Action: execute_python
→ Action Input: print(df.groupby('region')['revenue'].mean())
→ Observation: "North: $2.5M, South: $2.1M, ..."

Agent thinks: "Let me create a chart"
→ Action: create_visualization
→ Action Input: {"chart_type": "bar", ...}
→ Observation: "Created bar chart"

Agent thinks: "I have enough information"
→ Final Answer: "The average revenue is..."
```

### Adding a New Tool

1. **Create the tool function** (`app/tools/my_tool.py`):

```python
def my_custom_func(input_str: str) -> str:
    """Your tool logic here."""
    params = json.loads(input_str)
    # Do something
    return "Result"

my_custom_tool = Tool(
    name="my_custom_tool",
    description="What this tool does and when to use it",
    func=my_custom_func
)
```

2. **Register in agent** (`app/agents/data_analyst_agent.py`):

```python
from app.tools.my_tool import my_custom_tool

class DataAnalystAgent:
    def __init__(self):
        self.tools = [
            load_dataset_tool,
            execute_python_tool,
            create_visualization_tool,
            generate_insights_tool,
            my_custom_tool,  # ← Add here
        ]
```

3. **Test it**:
```python
# The agent will now have access to your tool
# and can call it based on the description
```

---

## Adding New Features

### Example 1: Add Column Filtering Endpoint

**Goal**: Get specific columns from a dataset

1. **Add schema** (`app/schemas/dataset.py`):

```python
class ColumnFilterRequest(BaseModel):
    columns: List[str]

class ColumnFilterResponse(BaseModel):
    data: List[Dict[str, Any]]
```

2. **Add service method** (`app/services/dataset_service.py`):

```python
async def get_columns(self, dataset_id: UUID, columns: List[str]):
    dataset = await self.get_dataset(dataset_id)
    df = await self.metadata_extractor.load_dataset(dataset.file_path)
    filtered = df[columns]
    return filtered.to_dict('records')
```

3. **Add endpoint** (`app/api/v1/endpoints/datasets.py`):

```python
@router.post("/{dataset_id}/columns")
async def get_specific_columns(
    dataset_id: UUID,
    request: ColumnFilterRequest,
    db: AsyncSession = Depends(get_db)
):
    service = DatasetService(db)
    data = await service.get_columns(dataset_id, request.columns)
    return ColumnFilterResponse(data=data)
```

### Example 2: Add Export to CSV Endpoint

1. **Install pandas** (already included)

2. **Add service method**:

```python
async def export_query_result(self, query_id: UUID) -> bytes:
    query = await self.get_query(query_id)
    # Convert results to DataFrame
    df = pd.DataFrame(...)  # Your logic
    # Export to CSV
    return df.to_csv(index=False).encode()
```

3. **Add endpoint with file response**:

```python
from fastapi.responses import StreamingResponse
import io

@router.get("/{query_id}/export")
async def export_result(query_id: UUID, db: AsyncSession = Depends(get_db)):
    service = QueryService(db)
    csv_data = await service.export_query_result(query_id)
    
    return StreamingResponse(
        io.BytesIO(csv_data),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=result.csv"}
    )
```

### Example 3: Add Scheduled Queries

1. **Install celery**:
```bash
pip install celery
```

2. **Create celery task**:

```python
# app/tasks.py
from celery import Celery

celery = Celery(__name__)

@celery.task
def run_scheduled_query(dataset_id, question):
    # Execute query
    # Save results
    # Send notification
    pass
```

3. **Add scheduling endpoint**:

```python
@router.post("/schedule")
async def schedule_query(
    dataset_id: UUID,
    question: str,
    schedule: str  # cron expression
):
    # Create scheduled task
    pass
```

---

## Common Customizations

### Change OpenAI Model

In `.env`:
```bash
# Default model (fast and cost-effective)
OPENAI_MODEL=gpt-4o-mini

# Use a more powerful model for complex datasets
OPENAI_MODEL=gpt-4o
```

### Adjust Agent Behavior

In `.env`:
```bash
# More creative responses
LLM_TEMPERATURE=0.7

# More thinking steps
AGENT_MAX_ITERATIONS=15

# See agent's thought process
AGENT_VERBOSE=True
```

### Add Custom Error Handling

```python
# app/utils/error_handlers.py

class MyCustomError(Exception):
    pass

async def my_custom_exception_handler(request, exc):
    return JSONResponse(
        status_code=400,
        content={"error": "my_error", "message": str(exc)}
    )

# Register in main.py
app.add_exception_handler(MyCustomError, my_custom_exception_handler)
```

### Add Authentication

1. **Install dependencies**:
```bash
pip install python-jose[cryptography] passlib[bcrypt]
```

2. **Create auth service**:

```python
# app/services/auth_service.py
from jose import jwt
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"])

def create_access_token(data: dict):
    return jwt.encode(data, SECRET_KEY, algorithm="HS256")
```

3. **Add dependency**:

```python
# app/dependencies.py
async def get_current_user(token: str = Depends(oauth2_scheme)):
    # Verify token
    # Return user
    pass
```

4. **Protect endpoints**:

```python
@router.post("/upload", dependencies=[Depends(get_current_user)])
async def upload_dataset(...):
    # Now requires authentication
```

---

## Debugging Tips

### Enable Verbose Logging

```python
# app/main.py
import logging

logging.basicConfig(level=logging.DEBUG)
```

### Check Agent Reasoning

Set `AGENT_VERBOSE=True` in `.env` to see:
```
> Entering new AgentExecutor chain...
Thought: I need to load the dataset first
Action: load_dataset
...
```

### Inspect Database Queries

```python
# app/database.py
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=True,  # ← Prints all SQL queries
)
```

### Test Individual Components

```python
# Test metadata extraction
from app.services.metadata_extractor import MetadataExtractor

extractor = MetadataExtractor()
df, metadata = await extractor.extract_metadata("test.csv")
print(metadata)
```

### Common Issues

**"Tool not found" error**:
- Check tool is imported in agent
- Verify tool name matches exactly
- Check tool description is clear

**Agent loops infinitely**:
- Increase `AGENT_MAX_ITERATIONS`
- Check tool is returning useful output
- Simplify the question

**Database connection errors**:
```bash
# Check PostgreSQL is running
docker-compose ps postgres

# Test connection
psql -U ai_platform -d ai_platform_db
```

---

## Performance Optimization

### 1. Database Indexing

```python
# Add index to frequently queried column
class Dataset(Base):
    __tablename__ = "datasets"
    
    status = Column(String(50), index=True)  # ← Indexed
```

### 2. Query Optimization

```python
# Bad: N+1 queries
for dataset in datasets:
    queries = await get_queries(dataset.id)  # ← Separate query each time

# Good: Join
result = await db.execute(
    select(Dataset)
    .options(selectinload(Dataset.queries))  # ← Loads in one query
)
```

### 3. Caching Strategy

```python
# Cache expensive computations
@lru_cache(maxsize=100)
def expensive_calculation(param):
    # Heavy processing
    return result
```

### 4. Async File I/O

```python
# Use aiofiles for large files
async with aiofiles.open('large_file.csv', 'r') as f:
    content = await f.read()
```

### 5. Connection Pooling

```python
# Already configured in database.py
engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,  # Adjust based on load
    max_overflow=10
)
```

---

## Learning Resources

### FastAPI
- [Official Documentation](https://fastapi.tiangolo.com/)
- [FastAPI Tutorial](https://fastapi.tiangolo.com/tutorial/)

### SQLAlchemy 2.0
- [Async I/O Guide](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [Relationship Loading Techniques](https://docs.sqlalchemy.org/en/20/orm/loading_relationships.html)

### LangChain
- [LangChain Docs](https://python.langchain.com/docs/get_started/introduction)
- [ReAct Agents](https://python.langchain.com/docs/modules/agents/agent_types/react)
- [Custom Tools](https://python.langchain.com/docs/modules/agents/tools/custom_tools)

### Pandas
- [10 Minutes to Pandas](https://pandas.pydata.org/docs/user_guide/10min.html)
- [Data Manipulation Guide](https://pandas.pydata.org/docs/user_guide/index.html)

### Plotly
- [Plotly Express Tutorial](https://plotly.com/python/plotly-express/)
- [Chart Types](https://plotly.com/python/)

---

## Next Steps

1. **Run the platform**: Follow README.md quick start
2. **Upload a dataset**: Try with your own CSV
3. **Ask questions**: See how the agent responds
4. **Read the code**: Start with `main.py`, follow the flow
5. **Add a feature**: Try implementing one of the examples
6. **Optimize**: Profile and improve performance
7. **Deploy**: Set up production environment

---

## Questions?

- Check existing issues on GitHub
- Review the TRD for architecture details
- Experiment with the code
- Build something awesome!

**Happy coding! 🚀**
