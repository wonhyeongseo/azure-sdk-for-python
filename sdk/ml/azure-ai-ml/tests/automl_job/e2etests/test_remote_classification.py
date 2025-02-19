from typing import Tuple

import pytest
from test_utilities.utils import assert_final_job_status, get_automl_job_properties

from azure.ai.ml import MLClient
from azure.ai.ml.automl import ColumnTransformer, classification
from azure.ai.ml.entities._inputs_outputs import Input
from azure.ai.ml.entities._job.automl.tabular.classification_job import ClassificationJob
from azure.ai.ml.operations._run_history_constants import JobStatus


@pytest.mark.automle2etest
class TestAutoMLClassification:
    def get_classification_task(
        self, dataset: Tuple[Input, Input, str], experiment_name: str, add_validation: bool = False
    ) -> ClassificationJob:
        # Get training and validation data
        training_data, validation_data, label_column_name = dataset

        classification_task = classification(
            training_data=training_data,
            target_column_name=label_column_name,
            primary_metric="accuracy",
            compute="automl-cpu-cluster",
            experiment_name=experiment_name,
            properties=get_automl_job_properties(),
        )

        if add_validation:
            classification_task.set_data(
                training_data=training_data, validation_data=validation_data, target_column_name=label_column_name
            )

        classification_task.set_limits(
            trial_timeout_minutes=10,
            timeout_minutes=600,
            max_trials=1,
            max_concurrent_trials=1,
            enable_early_termination=True,
        )

        classification_task.set_training(enable_stack_ensemble=False, enable_vote_ensemble=False)

        return classification_task

    def test_classification(self, bankmarketing_dataset: Tuple[Input, Input, str], client: MLClient) -> None:
        # get classification task
        classification_task = self.get_classification_task(bankmarketing_dataset, "DPv2-classification")
        # Trigger job
        created_job = client.jobs.create_or_update(classification_task)
        # Assert completion
        assert_final_job_status(created_job, client, ClassificationJob, JobStatus.COMPLETED)

    def test_classification_with_custom_featurization(
        self, bankmarketing_dataset: Tuple[Input, Input, str], client: MLClient
    ) -> None:
        # get classification task
        classification_task = self.get_classification_task(
            bankmarketing_dataset, "DPv2-classification-custom-featurization"
        )

        # Set featurization
        # Drop columns, add mode, add transformer_params,add block_transformers
        transformer_params = {
            "imputer": [
                ColumnTransformer(fields=["job"], parameters={"strategy": "most_frequent"}),
            ],
        }
        classification_task.set_featurization(
            mode="custom",
            transformer_params=transformer_params,
            blocked_transformers=["WordEmbedding"],
        )

        # Trigger job
        created_job = client.jobs.create_or_update(classification_task)
        # Assert completion
        assert_final_job_status(created_job, client, ClassificationJob, JobStatus.COMPLETED)

    def test_classification_fail_without_featurization(
        self, bankmarketing_dataset: Tuple[Input, Input, str], client: MLClient
    ) -> None:
        # get classification task
        classification_task = self.get_classification_task(
            bankmarketing_dataset, "DPv2-classification-fail-without-featurization"
        )
        # Set featurization off
        classification_task.set_featurization(mode="off")
        # Trigger job
        created_job = client.jobs.create_or_update(classification_task)
        # Assert Failure without featurization
        assert_final_job_status(created_job, client, ClassificationJob, JobStatus.FAILED)

    def test_classification_with_training_settings(
        self, bankmarketing_dataset: Tuple[Input, Input, str], client: MLClient
    ) -> None:
        # get classification task with validation data
        classification_task = self.get_classification_task(
            bankmarketing_dataset, "DPv2-classification-training-settings", add_validation=True
        )
        # Featurization set to auto by default
        # Set training
        # blocked models
        blocked_models = ["LightGBM"]
        classification_task.set_training(
            enable_model_explainability=True,
            enable_vote_ensemble=False,
            enable_stack_ensemble=False,
            blocked_training_algorithms=blocked_models,
        )
        # Trigger job
        created_job = client.jobs.create_or_update(classification_task)
        # Assert completion
        assert_final_job_status(created_job, client, ClassificationJob, JobStatus.COMPLETED)
