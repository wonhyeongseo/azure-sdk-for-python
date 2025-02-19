import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

import pytest

from azure.ai.ml import MLClient, load_batch_deployment, load_batch_endpoint, load_environment, load_model
from azure.ai.ml._utils._arm_id_utils import AMLVersionedArmId
from azure.ai.ml.constants._common import AssetTypes
from azure.ai.ml.entities import BatchDeployment, BatchEndpoint, Job
from azure.ai.ml.entities._inputs_outputs import Input
from azure.ai.ml.operations._job_ops_helper import _wait_before_polling
from azure.ai.ml.operations._run_history_constants import JobStatus, RunHistoryConstants


@contextmanager
def deployEndpointAndDeployment(client: MLClient, endpoint: BatchEndpoint, deployment: BatchDeployment):
    """Deploys endpoint and deployment, then automatically deletes the endpoint

    :param MLClient client: _description_
    :param BatchEndpoint endpoint: _description_
    :param BatchDeployment deployment: _description_
    :yield _type_: _description_
    """
    client.batch_endpoints.begin_create_or_update(endpoint)
    client.batch_deployments.begin_create_or_update(deployment)

    yield (endpoint, deployment)

    client.batch_endpoints.begin_delete(name=endpoint.name, no_wait=True)


@pytest.mark.e2etest
@pytest.mark.skip(reason="TODO (1546262): Test failing constantly, so disabling it")
def test_batch_deployment(client: MLClient, data_with_2_versions: str) -> None:
    endpoint_yaml = "tests/test_configs/endpoints/batch/batch_endpoint_mlflow_new.yaml"
    deployment_yaml = "tests/test_configs/deployments/batch/batch_deployment_mlflow_new.yaml"
    name = "batch-ept-" + uuid.uuid4().hex[:15]
    endpoint = load_batch_endpoint(endpoint_yaml)
    endpoint.name = name

    deployment = load_batch_deployment(deployment_yaml)
    deployment.endpoint_name = name
    deployment.name = "batch-dpm-" + uuid.uuid4().hex[:15]

    # create an endpoint
    client.batch_endpoints.begin_create_or_update(endpoint)
    # create a deployment
    client.batch_deployments.begin_create_or_update(deployment)

    dep = client.batch_deployments.get(name=deployment.name, endpoint_name=endpoint.name)
    assert dep.name == deployment.name

    deps = client.batch_deployments.list(endpoint_name=endpoint.name)
    assert len(list(deps)) > 0

    endpoint.traffic = {deployment.name: 100}
    client.batch_endpoints.begin_create_or_update(endpoint)

    # Invoke with output configs
    client.batch_endpoints.invoke(
        endpoint_name=endpoint.name,
        deployment_name=deployment.name,
        input=":".join((data_with_2_versions, "1")),
    )
    client.batch_endpoints.begin_delete(name=endpoint.name, no_wait=True)


@pytest.mark.e2etest
def test_batch_deployment_dependency_label_resolution(client: MLClient, randstr: Callable[[], str]) -> None:
    endpoint_yaml = "./tests/test_configs/endpoints/batch/batch_endpoint_mlflow_new.yaml"
    name = "batch-ept-" + uuid.uuid4().hex[:15]
    deployment_yaml = "./tests/test_configs/deployments/batch/batch_deployment_mlflow_new.yaml"
    deployment_name = "batch-dpm-" + uuid.uuid4().hex[:15]

    environment_name = randstr()
    environment_versions = ["foo", "bar"]

    for version in environment_versions:
        client.environments.create_or_update(
            load_environment(
                "./tests/test_configs/environment/environment_conda_inline.yml",
                params_override=[{"name": environment_name}, {"version": version}],
            )
        )

    model_name = randstr()
    model_versions = ["1", "2"]

    for version in model_versions:
        client.models.create_or_update(
            load_model(
                "./tests/test_configs/model/model_minimal.yml",
                params_override=[{"name": model_name}, {"version": version}],
            )
        )

    endpoint = load_batch_endpoint(endpoint_yaml, params_override=[{"name": name}])
    deployment = load_batch_deployment(
        deployment_yaml,
        params_override=[
            {"endpoint_name": name},
            {"name": deployment_name},
            {"environment": f"azureml:{environment_name}@latest"},
            {"model": f"azureml:{model_name}@latest"},
        ],
    )

    # create an endpoint
    client.batch_endpoints.begin_create_or_update(endpoint)
    # create a deployment
    client.batch_deployments.begin_create_or_update(deployment)
    dep = client.batch_deployments.get(name=deployment.name, endpoint_name=endpoint.name)
    client.batch_endpoints.begin_delete(name=endpoint.name, no_wait=True)

    resolved_environment = AMLVersionedArmId(dep.environment)
    resolved_model = AMLVersionedArmId(dep.model)
    assert dep.name == deployment.name
    assert (
        resolved_environment.asset_name == environment_name
        and resolved_environment.asset_version == environment_versions[-1]
    )
    assert resolved_model.asset_name == model_name and resolved_model.asset_version == model_versions[-1]


@pytest.mark.e2etest
def test_batch_job_download(client: MLClient, tmp_path: Path) -> str:
    def wait_until_done(job: Job, timeout: int = None) -> None:
        poll_start_time = time.time()
        while job.status not in RunHistoryConstants.TERMINAL_STATUSES:
            time.sleep(_wait_before_polling(time.time() - poll_start_time))
            job = client.jobs.get(job.name)
            if timeout is not None and time.time() - poll_start_time > timeout:
                # if timeout is passed in, execute job cancel if timeout and directly return CANCELED status
                client.jobs.cancel(job.name)
                return JobStatus.CANCELED
        return job.status

    endpoint = load_batch_endpoint(
        "./tests/test_configs/endpoints/batch/batch_endpoint_mlflow_new.yaml",
        params_override=[{"name": "batch-ept-" + uuid.uuid4().hex[:15]}],
    )
    deployment = load_batch_deployment(
        "./tests/test_configs/deployments/batch/batch_deployment_quick.yaml",
        params_override=[{"endpoint_name": endpoint.name}, {"name": "batch-dpm-" + uuid.uuid4().hex[:15]}],
    )
    endpoint.traffic = {deployment.name: 100}

    with deployEndpointAndDeployment(client, endpoint, deployment):
        batchjobresource = client.batch_endpoints.invoke(
            endpoint_name=endpoint.name,
            deployment_name=deployment.name,
            input=Input(
                path="https://azuremlexamples.blob.core.windows.net/datasets/iris.csv", type=AssetTypes.URI_FILE
            ),
        )

        batchjob = client.jobs.get(batchjobresource.name)

        # Adding a timeout value of 5 minutes to avoid future scenarios where wait
        # long periods for the test to finish. Instead if the job takes longer
        # than 5 minutes to finish we will make the test fail
        job_status = wait_until_done(batchjob, 300)

        # Check if the job was canceled due to a timeout.
        # If the job's status is CANCELED, we will make the test fail
        if job_status == JobStatus.CANCELED:
            pytest.fail(
                "Job was canceled because it was taking longer than 5 minutes to finish, not execute downloaded artifacts assertion."
            )
        else:
            client.jobs.download(batchjob.name, download_path=tmp_path)

            assert (tmp_path / "predictions.csv").exists(), "Scoring output was not downloaded"
