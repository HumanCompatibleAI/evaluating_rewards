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

"""CLI script to plot heatmaps based on episode return of reward models."""

import logging
import os
from typing import Any, Dict, Iterable, Mapping, Sequence, Tuple

import gym
from imitation.util import data, util
import matplotlib.pyplot as plt
import pandas as pd
import sacred
from stable_baselines.common import vec_env
import tensorflow as tf

from evaluating_rewards import canonical_sample, datasets, rewards, serialize, tabular
from evaluating_rewards.analysis import stylesheets, visualize
from evaluating_rewards.analysis.dissimilarity_heatmaps import config, heatmaps
from evaluating_rewards.scripts import script_utils

plot_return_heatmap_ex = sacred.Experiment("plot_return_heatmap")
logger = logging.getLogger("evaluating_rewards.analysis.plot_return_heatmap")


config.make_config(plot_return_heatmap_ex)


@plot_return_heatmap_ex.config
def default_config(env_name, log_root):
    """Default configuration values."""
    data_root = log_root  # root of data directory for learned reward models
    computation_kind = "sample"  # either "sample" or "mesh"
    corr_kind = "pearson"  # either "pearson" or "spearman"
    discount = 0.99  # discount rate for shaping
    n_episodes = 1024  # number of episodes to compute correlation w.r.t.

    # n_samples and n_mean_samples only applicable for sample approach
    trajectory_factory = datasets.trajectory_factory_from_serialized_policy
    trajectory_factory_kwargs = {
        "env_name": env_name,
        "policy_type": "random",
        "policy_path": "dummy",
        "parallel": True,
    }
    dataset_tag = "random"

    # Figure parameters
    heatmap_kwargs = {"log": False}
    _ = locals()
    del _


@plot_return_heatmap_ex.config
def logging_config(log_root, env_name, dataset_tag, corr_kind, discount):
    """Default logging configuration: hierarchical directory structure based on config."""
    log_dir = os.path.join(  # noqa: F841  pylint:disable=unused-variable
        log_root,
        "plot_return_heatmap",
        env_name,
        dataset_tag,
        corr_kind,
        f"discount{discount}",
        util.make_unique_timestamp(),
    )


@plot_return_heatmap_ex.named_config
def test():
    """Intended for debugging/unit test."""
    n_episodes = 64
    # Do not include "tex" in styles here: this will break on CI.
    styles = ["paper", "heatmap-1col"]
    _ = locals()
    del _


# TODO(adam): do we need this? if so, refactor into common file? duplicated!
def load_models(
    env_name: str, reward_cfgs: Iterable[config.RewardCfg], discount: float,
) -> Mapping[config.RewardCfg, rewards.RewardModel]:
    venv = vec_env.DummyVecEnv([lambda: gym.make(env_name)])
    return {
        (kind, path): serialize.load_reward(kind, path, venv, discount)
        for kind, path in reward_cfgs
    }


# TODO(adam): do we need this? if so, refactor into common file? duplicated!
def dissimilarity_mapping_to_series(
    dissimilarity: Mapping[Tuple[config.RewardCfg, config.RewardCfg], float]
) -> pd.Series:
    """Converts dissimilarity mapping to a MultiIndex series."""
    dissimilarity = {
        (xtype, xpath, ytype, ypath): v
        for ((xtype, xpath), (ytype, ypath)), v in dissimilarity.items()
    }
    dissimilarity = pd.Series(dissimilarity)
    dissimilarity.index.names = [
        "target_reward_type",
        "target_reward_path",
        "source_reward_type",
        "source_reward_path",
    ]
    return dissimilarity


# TODO(adam): do we need this? if so, refactor into common file? duplicated!
def _canonicalize_reward_cfg(
    reward_cfg: Iterable[config.RewardCfg], data_root: str
) -> Iterable[config.RewardCfg]:
    res = []
    for kind, path in reward_cfg:
        if path != "dummy":
            path = os.path.join(data_root, path)
        res.append((kind, path))
    return res


@plot_return_heatmap_ex.capture
def correlation_distance(
    sess: tf.Session,
    trajectories: Sequence[data.Trajectory],
    models: Mapping[config.RewardCfg, rewards.RewardModel],
    x_reward_cfgs: Iterable[config.RewardCfg],
    y_reward_cfgs: Iterable[config.RewardCfg],
    corr_kind: str,
    discount: float,
) -> Mapping[Tuple[config.RewardCfg, config.RewardCfg], float]:
    """
    Computes approximation of canon distance using `canonical_sample.sample_canon_shaping`.

    Args:
        sess: the TensorFlow session.
        trajectories: sequence of trajectories.
        models: loaded reward models for all of `x_reward_cfgs` and `y_reward_cfgs`.
        x_reward_cfgs: tuples of reward_type and reward_path for x-axis.
        y_reward_cfgs: tuples of reward_type and reward_path for y-axis.
        corr_kind: method to compute results, either "pearson" or "spearman".
        discount: the discount rate for shaping.

    Returns:
        Dissimilarity matrix.
    """
    with sess.as_default():
        logger.info("Computing returns")
        rets = rewards.compute_return_of_models(models, trajectories, discount)

    x_rets = {cfg: rets[cfg] for cfg in x_reward_cfgs}
    y_rets = {cfg: rets[cfg] for cfg in y_reward_cfgs}

    if corr_kind == "pearson":
        distance_fn = tabular.pearson_distance
    elif corr_kind == "spearman":
        # TODO(adam): implement me!
        raise NotImplementedError("")
    else:
        raise ValueError(f"Unrecognized correlation '{corr_kind}'")

    logger.info("Computing distance")
    return canonical_sample.cross_distance(x_rets, y_rets, distance_fn, parallelism=1)


@plot_return_heatmap_ex.main
def plot_return_heatmap(
    env_name: str,
    discount: float,
    x_reward_cfgs: Iterable[config.RewardCfg],
    y_reward_cfgs: Iterable[config.RewardCfg],
    trajectory_factory: datasets.TrajectoryFactory,
    trajectory_factory_kwargs: Dict[str, Any],
    n_episodes: int,
    styles: Iterable[str],
    heatmap_kwargs: Mapping[str, Any],
    log_dir: str,
    data_root: str,
    save_kwargs: Mapping[str, Any],
) -> Mapping[str, plt.Figure]:
    """Entry-point into script to produce divergence heatmaps.

    Args:
        env_name: the name of the environment to plot rewards for.
        x_reward_cfgs: tuples of reward_type and reward_path for x-axis.
        y_reward_cfgs: tuples of reward_type and reward_path for y-axis.
        trajectory_factory: factory to generate trajectories.
        trajectory_factory_kwargs: arguments to pass to the factory.
        n_episodes: the number of episodes to compute correlation over.
        styles: styles to apply from `evaluating_rewards.analysis.stylesheets`.
        heatmap_kwargs: passed through to `analysis.compact_heatmaps`.
        log_dir: directory to write figures and other logging to.
        data_root: directory to load learned reward models from.
        save_kwargs: passed through to `analysis.save_figs`.

    Returns:
        A mapping of keywords to figures.
    """
    # TODO(adam): code duplication? :( merge plot_* into one CLI script?
    # Sacred turns our tuples into lists :(, undo
    x_reward_cfgs = _canonicalize_reward_cfg(x_reward_cfgs, data_root)
    y_reward_cfgs = _canonicalize_reward_cfg(y_reward_cfgs, data_root)

    logger.info("Loading models")
    g = tf.Graph()
    with g.as_default():
        sess = tf.Session()
        with sess.as_default():
            reward_cfgs = list(x_reward_cfgs) + list(y_reward_cfgs)
            models = load_models(env_name, reward_cfgs, discount)

    logger.info("Sampling trajectories")
    with trajectory_factory(**trajectory_factory_kwargs) as trajectory_callable:
        trajectories = trajectory_callable(n_episodes)

    dissimilarity = correlation_distance(  # pylint:disable=no-value-for-parameter
        sess, trajectories, models, x_reward_cfgs, y_reward_cfgs
    )
    dissimilarity = dissimilarity_mapping_to_series(dissimilarity)

    with stylesheets.setup_styles(styles):
        figs = heatmaps.compact_heatmaps(dissimilarity=dissimilarity, **heatmap_kwargs)
        visualize.save_figs(log_dir, figs.items(), **save_kwargs)

    return figs


if __name__ == "__main__":
    script_utils.experiment_main(plot_return_heatmap_ex, "plot_return_heatmap")
