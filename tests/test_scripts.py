# Copyright 2019 DeepMind Technologies Limited and Adam Gleave
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Smoke tests for CLI scripts."""

import tempfile

import pandas as pd
import xarray as xr

from evaluating_rewards.scripts.model_comparison import model_comparison_ex
from evaluating_rewards.scripts.train_preferences import train_preferences_ex
from evaluating_rewards.scripts.train_regress import train_regress_ex
from evaluating_rewards.scripts.visualize_divergence_heatmap import visualize_divergence_heatmap_ex
from evaluating_rewards.scripts.visualize_pm_reward import visualize_pm_reward_ex
from tests import common

EXPERIMENTS = {
    # experiment, expected_type
    "comparison": (model_comparison_ex, dict),
    "regress": (train_regress_ex, dict),
    "preferences": (train_preferences_ex, pd.DataFrame),
    "visualize_divergence": (visualize_divergence_heatmap_ex, dict),
    "visualize_pm": (visualize_pm_reward_ex, xr.DataArray),
}


@common.mark_parametrize_dict("experiment,expected_type", EXPERIMENTS)
def test_experiment(experiment, expected_type):
    with tempfile.TemporaryDirectory(prefix="eval-rewards-exp") as tmpdir:
        run = experiment.run(named_configs=["fast"], config_updates=dict(log_root=tmpdir))
    assert run.status == "COMPLETED"
    assert isinstance(run.result, expected_type)
