# 🔄 Migration Guide: ias_workflow_engine → pyworkflow_engine

## Overview

The workflow engine has been renamed from `ias_workflow_engine` to `pyworkflow_engine` to make it more generic and suitable for use across different projects and organizations.

## Breaking Changes

### Package Name
- **Old**: `ias-workflow-engine`
- **New**: `pyworkflow-engine`

### Import Statements

**Before (v0.1.x):**
```python
from ias_workflow_engine import WorkflowEngine, Job, Step
from ias_workflow_engine.core.executors import ThreadPoolStepExecutor
from ias_workflow_engine.persistence import InMemoryPersistence
```

**After (v0.2.0+):**
```python
from pyworkflow_engine import WorkflowEngine, Job, Step
from pyworkflow_engine.core.executors import ThreadPoolStepExecutor
from pyworkflow_engine.persistence import InMemoryPersistence
```

### Installation

**Before:**
```bash
pip install ias-workflow-engine
```

**After:**
```bash
pip install pyworkflow-engine
```

### CLI Command

**Before:**
```bash
# The old CLI was: ias_workflow_engine.cli.main:cli
workflow --help
```

**After:**
```bash
# The new CLI is: pyworkflow_engine.cli.main:cli
workflow --help
```

## Migration Steps

### 1. Update Installation
```bash
pip uninstall ias-workflow-engine
pip install pyworkflow-engine
```

### 2. Update Import Statements
Use find and replace in your IDE to update all imports:
- Find: `ias_workflow_engine`
- Replace: `pyworkflow_engine`

### 3. Update Configuration Files
If you have any configuration files referencing the old package:
- `pyproject.toml` dependencies
- `requirements.txt` files
- Docker files
- CI/CD configurations

### 4. Verify Tests
Run your test suite to ensure all imports are working correctly.

## Functionality

✅ **All functionality remains identical**
- Same API surface
- Same behavior
- Same performance characteristics
- Same optional dependencies

## Optional Dependencies

The optional dependency installation remains the same pattern:

```bash
# Core persistence (no extra dependencies)
pip install pyworkflow-engine

# With SQLAlchemy support  
pip install pyworkflow-engine[sqlalchemy]

# With database-specific support
pip install pyworkflow-engine[postgresql]
pip install pyworkflow-engine[mysql]

# All features
pip install pyworkflow-engine[all]
```

## Why This Change?

1. **Generic Naming**: `pyworkflow_engine` is more generic and suitable for any project
2. **Broader Adoption**: Not tied to IAS-specific naming conventions
3. **Open Source Ready**: Better positioned for open source distribution
4. **Consistency**: Aligns with Python package naming conventions

## Examples

### Basic Workflow Example
```python
# ✅ New v0.2.0+ syntax
from pyworkflow_engine import WorkflowEngine, Job, Step, StepType

def my_task(context):
    return "Hello from PyWorkflow Engine!"

job = Job(
    name="example_job",
    steps=[
        Step(
            name="hello_step",
            step_type=StepType.PYTHON_FUNCTION,
            callable_func=my_task
        )
    ]
)

engine = WorkflowEngine()
result = engine.run(job)
print(f"Status: {result.status}")
```

### Persistence Example
```python
# ✅ New v0.2.0+ syntax
from pyworkflow_engine import WorkflowEngine
from pyworkflow_engine.persistence import InMemoryPersistence
from pyworkflow_engine.core.models import Job, Step, StepType

# Setup with persistence
engine = WorkflowEngine()
engine.persistence = InMemoryPersistence()

job = Job(name="persistent_job", steps=[...])
result = engine.run_with_persistence(job)
```

## Support

If you encounter any issues during migration:
1. Check that all imports have been updated
2. Verify the new package is installed: `pip list | grep pyworkflow`
3. Run tests to identify any remaining references to old imports

## Version History

- **v0.1.x**: `ias_workflow_engine` (deprecated)
- **v0.2.0+**: `pyworkflow_engine` (current)

---

*This migration guide covers all breaking changes. The core functionality and API remain unchanged.*
