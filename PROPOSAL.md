# Project Proposal: Intelligent Data Analysis Agent

**Co-Curricular Activity:** Building Advanced AI Agents & RAG Systems
**School of Physics, Engineering & Computer Science | Data Science Subject Group**
**Proposed Track:** Data Analysis & Insight Agent

---

## 1. Overview

We propose to build an **Intelligent Data Analysis Agent**, a system that allows users to upload a dataset and ask questions about it in plain English, receiving clear, computed answers alongside visualisations and follow-up suggestions.

The core idea is straightforward: instead of users needing to write code or use specialised tools to explore their data, they simply describe what they want to know. The agent handles the rest: deciding what analysis to run, executing it, and explaining the results in plain language.

---

## 2. Why This Project

Data analysis is one of the most natural and impactful applications of agentic AI. It is also one of the more technically demanding: the agent must reason about data it cannot directly see, plan its approach before executing anything, run code against real datasets, and produce answers it can stand behind.

This makes it an ideal project for exploring what modern AI agents are actually capable of: not just generating text, but planning, acting, and reasoning about the results of their own actions.

---

## 3. What We Will Build

The system will consist of three main parts:

**A natural-language query interface**
Users upload a dataset (CSV or Excel) and type their question. The system handles everything from there, with no coding required.

**An agentic analysis pipeline**
Rather than sending the question directly to a language model, the system will use a structured agent that first plans its approach, then executes analysis steps one at a time, then synthesises the results into a clear response. This planning-before-acting design is what separates a capable agent from a basic chatbot.

**A multi-agent layer for specialist tasks**
For more complex questions such as statistical testing, time-series forecasting, or visualisation-heavy analyses, a supervisor agent will route the query to a specialist sub-agent equipped with the right tools and domain knowledge for that type of work.

---

## 4. Key Capabilities

- Ask analytical questions in plain English against any uploaded dataset
- Receive answers that include computed results, charts, and key findings
- Continue a conversation across multiple questions within a session
- Complex queries automatically routed to the most appropriate specialist agent
- Follow-up question suggestions to guide further exploration

---

## 5. Approach & Timeline

The project will be developed over 8 weeks, broadly across three phases:

**Weeks 1–2: Foundation**
Core backend, dataset upload and storage, authentication, and the initial single-agent query pipeline.

**Weeks 3–4: Agent Depth**
Multi-turn conversation sessions, real-time streaming of agent progress, and robustness improvements (error recovery, retry logic).

**Weeks 5–6: Multi-Agent Architecture**
Supervisor agent with specialist sub-agents for statistical analysis, forecasting, and visualisation.

**Weeks 7–8: Evaluation & Delivery**
Quality benchmarking against a curated set of test questions, final polish, and demonstration.

---

## 6. Technologies

The system will be built in Python using FastAPI for the backend, LangGraph for agent orchestration, and OpenAI as the underlying language model. Data will be stored in PostgreSQL, with Redis used for caching and response speed. The application will be containerised with Docker for consistent deployment.

---

## 7. What We Expect to Learn

This project will give the team hands-on experience with the real challenges of building production-quality AI agents: how to structure an agent that plans before it acts, how to enforce tool use reliably, how to coordinate multiple agents for different tasks, and how to measure whether an AI system is actually doing its job well.

---

*Submitted for consideration: Building Advanced AI Agents & RAG Systems Co-Curricular Activity*
*Department of Computer Science, School of Physics, Engineering & Computer Science*
