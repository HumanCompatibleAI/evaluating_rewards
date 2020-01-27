# Copyright 2020 Adam Gleave
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#            http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""CLI script to plot heatmap of divergence between reward models in gridworlds."""

import collections
import os
from typing import Any, Dict, Iterable, Mapping, Optional

from imitation import util
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sacred

from evaluating_rewards import serialize, tabular
from evaluating_rewards.analysis import gridworld_rewards, stylesheets, visualize
from evaluating_rewards.scripts import script_utils

plot_gridworld_divergence_ex = sacred.Experiment("plot_gridworld_divergence")


@plot_gridworld_divergence_ex.config
def default_config():
    """Default configuration values."""
    # Dataset parameters
    log_root = serialize.get_output_dir()  # where results are read from/written to
    discount = 0.99
    reward_subset = None

    # Figure parameters
    styles = ["paper", "huge", "tex"]
    save_kwargs = {
        "fmt": "pdf",
    }

    _ = locals()
    del _


@plot_gridworld_divergence_ex.named_config
def test():
    """Unit tests/debugging."""
    reward_subset = ["sparse_goal", "dense_goal"]  # noqa: F841  pylint:disable=unused-variable


@plot_gridworld_divergence_ex.config
def logging_config(log_root):
    log_dir = os.path.join(  # noqa: F841  pylint:disable=unused-variable
        log_root, "plot_gridworld_divergence", util.make_unique_timestamp(),
    )


def state_to_3d(reward: np.ndarray, ns: int, na: int) -> np.ndarray:
    """Convert state-only reward R[s] to 3D reward R[s,a,s'].

    Args:
        - reward: state only reward.
        - ns: number of states.
        - na: number of actions.

    Returns:
        State-action-next state reward from tiling `reward`.
    """
    assert reward.ndim == 1
    assert reward.shape[0] == ns
    return np.tile(reward[:, np.newaxis, np.newaxis], (1, na, ns))


def grid_to_3d(reward: np.ndarray) -> np.ndarray:
    """Convert gridworld state-only reward R[i,j] to 3D reward R[s,a,s']."""
    assert reward.ndim == 2
    reward = reward.flatten()
    ns = reward.shape[0]
    return state_to_3d(reward, ns, 5)


def make_reward(cfg, discount):
    """Create reward from state-only reward and potential."""
    state_reward = grid_to_3d(cfg["state_reward"])
    potential = cfg["potential"]
    assert potential.ndim == 2  # gridworld, (i,j) indexed
    potential = potential.flatten()
    return tabular.shape(state_reward, potential, discount)


def compute_divergence(reward_cfg: Dict[str, Any], discount: float) -> pd.Series:
    """Compute divergence for each pair of rewards in `reward_cfg`."""
    rewards = {name: make_reward(cfg, discount) for name, cfg in reward_cfg.items()}
    divergence = collections.defaultdict(dict)
    for src_name, src_reward in rewards.items():
        for target_name, target_reward in rewards.items():
            if target_name == "all_zero":
                continue
            closest_reward = tabular.closest_reward_em(src_reward, target_reward, discount=discount)
            div = tabular.direct_sq_divergence(closest_reward, target_reward)
            divergence[target_name][src_name] = div
    divergence = pd.DataFrame(divergence)
    divergence = divergence.stack()
    divergence.index.names = ["source_reward_type", "target_reward_type"]
    return divergence


@plot_gridworld_divergence_ex.main
def plot_gridworld_divergence(
    styles: Iterable[str],
    reward_subset: Optional[Iterable[str]],
    discount: float,
    log_dir: str,
    save_kwargs: Mapping[str, Any],
):
    """Entry-point into script to produce divergence heatmaps.

    Args:
        styles: styles to apply from `evaluating_rewards.analysis.stylesheets`.
        reward_subset: if specified, subset of keys to plot.
        discount: discount rate of MDP.
        log_dir: directory to write figures and other logging to.
        save_kwargs: passed through to `analysis.save_figs`.
        """
    with stylesheets.setup_styles(styles):
        rewards = gridworld_rewards.REWARDS
        if reward_subset is not None:
            rewards = {k: rewards[k] for k in reward_subset}
        divergence = compute_divergence(rewards, discount)

        fig, ax = plt.subplots(1, 1)
        visualize.comparison_heatmap(vals=divergence, ax=ax)
        visualize.save_fig(os.path.join(log_dir, "fig"), fig, **save_kwargs)

        return fig


if __name__ == "__main__":
    script_utils.experiment_main(plot_gridworld_divergence_ex, "plot_gridworld_divergence")
