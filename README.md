# zoo-calrissian-runner

Python library for bridging zoo execution context and calrissian

## 🔗 Dependencies

This runner now uses **[zoo-runner-common](https://github.com/ZOO-Project/zoo-runner-common)** for shared functionality, eliminating ~166 lines of duplicated code.

**Key changes:**
- ✅ Inherits from `BaseRunner` for common methods
- ✅ Uses shared `ZooConf`, `ZooInputs`, `ZooOutputs`, `CWLWorkflow` classes
- ✅ Implements `ExecutionHandler` interface from zoo-runner-common
- ✅ Focuses only on Calrissian/Kubernetes-specific logic

## Installation

Install with zoo-runner-common dependency:

```bash
pip install zoo-calrissian-runner
# Or from source:
pip install -e . 
```

## Environment variables

* `STORAGE_CLASS`: RWX storage class (use `"hostpath"` for Docker Desktop on Mac)
* `CALRISSIAN_IMAGE`: Calrissian container image
* `DEFAULT_VOLUME_SIZE`: default size for RWX storage volume
* `DEFAULT_MAX_CORES`: maximum number of cores if CWL doesn't specify resource requirements
* `DEFAULT_MAX_RAM`: maximum RAM (in MB) if CWL doesn't specify resource requirements

CWL wrapper templates:

* `WRAPPER_STAGE_IN`
* `WRAPPER_STAGE_OUT`
* `WRAPPER_STAGE_MAIN`
* `WRAPPER_STAGE_RULES`

## Running the tests

Add a `tests/.env` file including the values with::

```
CR_USERNAME=""
CR_TOKEN=""
CR_ENDPOINT="https://index.docker.io/v1/"
CR_EMAIL=""
AWS_SERVICE_URL=""
AWS_REGION=""
AWS_ACCESS_KEY_ID=""
AWS_SECRET_ACCESS_KEY=""

KUBECONFIG=""
STORAGE_CLASS=""

DEFAULT_MAX_CORES=8
DEFAULT_MAX_RAM=1024
DEFAULT_VOLUME_SIZE=10000 # mebibytes (2**20)


ADES_STAGEOUT_OUTPUT=""
```
