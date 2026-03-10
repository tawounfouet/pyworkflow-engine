# IAS Workflow Engine Examples

This directory contains practical examples demonstrating the capabilities of the IAS Workflow Engine.

## Available Examples

### 1. Simple Examples (`simple_examples.py`)
Basic demonstrations of core workflow features:
- **Linear Workflows**: Steps executed in sequence with dependencies
- **Parallel Execution**: Multiple tasks running concurrently  
- **Context Sharing**: Data passed between workflow steps
- **Execution Planning**: Shows execution order and parallel groups

**Run:** `uv run python examples/simple_examples.py`

### 2. Basic ETL (`basic_etl.py`)
A comprehensive ETL (Extract, Transform, Load) pipeline demonstrating:
- Data extraction from sources
- Data transformation and filtering
- Database loading simulation
- Report generation
- Step output chaining

**Run:** `uv run python examples/basic_etl.py`

### 3. Human Approval Workflow (`human_approval.py`)
Advanced workflow with human intervention capabilities:
- Workflow suspension for approval
- Resume functionality with external input
- Multi-step approval process
- Expense request processing example

**Run:** `uv run python examples/human_approval.py`

**Note:** Human approval workflow demonstrates suspension but the resume functionality needs refinement for production use.

### 4. Parallel Processing (`parallel_processing.py`)
Data processing pipeline with parallel analytics:
- Concurrent data analysis tasks
- Regional and product statistics
- Data quality validation
- Comprehensive reporting
- Performance optimization through parallelization

**Run:** `uv run python examples/parallel_processing.py`

### 5. Retry Mechanisms (`simple_retry_test.py`)
Demonstrates automatic retry functionality for handling transient failures:
- Configurable retry count and delays
- Automatic retry on step failures
- Retry exhaustion handling
- Context preservation across retries
- Performance timing validation

**Run:** `uv run python examples/simple_retry_test.py`

### 6. Timeout Handling and Advanced Executors (`timeout_and_executors.py`)
**NEW in Phase 1 Week 4:** Advanced execution features:

**Timeout Management:**
- Step-level timeout configuration
- Thread-based timeout enforcement
- Timeout error handling and cleanup

**Advanced Executors:**
- **ThreadPoolExecutor**: I/O-bound concurrent operations
- **ProcessPoolExecutor**: CPU-intensive multiprocessing tasks  
- **AsyncExecutor**: Async/await function integration
- **RetryableExecutor**: Advanced retry with exponential backoff and jitter
- **ExecutorRegistry**: Managing multiple executors

**Features Demonstrated:**
- Timeout success and failure scenarios
- Concurrent I/O operations with thread pools
- CPU-intensive tasks with process pools
- Async function execution with proper timeout handling
- Advanced retry strategies with backoff
- Complex workflows mixing multiple executor types
- Executor lifecycle management

**Run:** `uv run python examples/timeout_and_executors.py`

**Architecture:** Pure Python implementation with zero external dependencies, using only stdlib modules (threading, multiprocessing, asyncio, concurrent.futures).

## Key Features Demonstrated

### ✅ Working Features
- **Sequential Workflows**: Steps with dependencies execute in order
- **Parallel Execution**: Independent steps run concurrently
- **Context Management**: Data sharing between steps
- **Execution Planning**: DAG analysis and optimization
- **Error Handling**: Graceful failure management
- **Retry Mechanisms**: Automatic retry with configurable delays
- **Step Outputs**: Accessing results from completed steps
- **Workflow Validation**: Job and step validation
- **Performance Tracking**: Duration and progress monitoring

### 🔄 Partial Implementation
- **Workflow Suspension**: Basic suspension works, but resume needs enhancement
- **Human Approval**: Demonstrates concept but needs production refinements

## Architecture Highlights

The examples showcase the **"Library-first, Framework-second"** architecture:

- ✅ **Zero Core Dependencies**: Pure Python implementation
- ✅ **Immutable Models**: Thread-safe design-time and runtime models
- ✅ **DAG Resolution**: Automatic dependency analysis and optimization
- ✅ **Flexible Execution**: Support for different step types and executors
- ✅ **Production Logging**: Comprehensive error tracking and monitoring
- ✅ **Type Safety**: Full type annotations throughout

## Performance Characteristics

Based on example runs:
- **Simple Linear Workflows**: ~0ms execution time for basic operations
- **Parallel Processing**: ~40% time savings through concurrent execution
- **ETL Pipelines**: Efficient step-by-step data processing
- **Context Overhead**: Minimal performance impact for data sharing

## Next Steps

These examples provide the foundation for:

1. **Enhanced Features**: Retry mechanisms, timeout handling, advanced executors
2. **Framework Adapters**: Django, FastAPI, Celery integration
3. **Advanced Capabilities**: Persistence, monitoring, scheduling
4. **Production Deployment**: Scaling and enterprise features

## Running All Examples

```bash
# Run individual examples
uv run python examples/simple_examples.py
uv run python examples/basic_etl.py  
uv run python examples/parallel_processing.py
uv run python examples/human_approval.py
uv run python examples/simple_retry_test.py
uv run python examples/timeout_and_executors.py

# Run tests to verify engine stability
uv run pytest -v --cov=src --cov-report=term-missing
```

All examples use the same core engine and demonstrate real-world workflow patterns that can be adapted for production use cases.
