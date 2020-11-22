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

"""CLI script to make table of EPIC, NPEC and ERC distances from a reward model."""

import copy
import functools
import itertools
import logging
import os
import pickle
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple, TypeVar

from imitation.util import util as imit_util
import pandas as pd
import sacred

from evaluating_rewards import serialize
from evaluating_rewards.analysis.distances import aggregated
from evaluating_rewards.distances import common_config
from evaluating_rewards.scripts import script_utils
from evaluating_rewards.scripts.distances import epic, erc, npec

table_combined_ex = sacred.Experiment("table_combined")
logger = logging.getLogger("evaluating_rewards.analysis.distances.table_combined")


@table_combined_ex.config
def default_config():
    """Default configuration for table_combined."""
    vals_path = None
    log_root = serialize.get_output_dir()  # where results are read from/written to
    distance_kinds = ("epic", "npec", "erc")
    experiment_kinds = ()
    config_updates = {}  # config updates applied to all subcommands
    named_configs = {}
    skip = {}
    target_reward_type = None
    target_reward_path = None
    pretty_models = {}
    tag = "default"
    _ = locals()
    del _


@table_combined_ex.config
def logging_config(log_root, tag):
    """Default logging configuration: hierarchical directory structure based on config."""
    log_dir = os.path.join(  # noqa: F841  pylint:disable=unused-variable
        log_root,
        "table_combined",
        tag,
        imit_util.make_unique_timestamp(),
    )


POINT_MAZE_LEARNED_COMMON = {
    "target_reward_type": "evaluating_rewards/PointMazeGroundTruthWithCtrl-v0",
    "target_reward_path": "dummy",
    "named_configs": {
        "point_maze_learned": {
            "global": ("point_maze_learned",),
        }
    },
    "pretty_models": {
        r"\repelstaticmethod{}": ("evaluating_rewards/PointMazeRepellentWithCtrl-v0", "dummy"),
        r"\bettergoalmethod{}": ("evaluating_rewards/PointMazeBetterGoalWithCtrl-v0", "dummy"),
        r"\regressionmethod{}": (
            "evaluating_rewards/RewardModel-v0",
            "transfer_point_maze/reward/regress/model",
        ),
        r"\preferencesmethod{}": (
            "evaluating_rewards/RewardModel-v0",
            "transfer_point_maze/reward/preferences/model",
        ),
        r"\airlstateonlymethod{}": (
            "imitation/RewardNet_unshaped-v0",
            "transfer_point_maze/reward/irl_state_only/checkpoints/final/discrim/reward_net",
        ),
        r"\airlstateactionmethod{}": (
            "imitation/RewardNet_unshaped-v0",
            "transfer_point_maze/reward/irl_state_action/checkpoints/final/discrim/reward_net",
        ),
    },
}


def _make_visitations_config_updates(method):
    return {
        "epic": {k: {"visitations_factory_kwargs": v} for k, v in method.items()},
        "erc": {k: {"trajectory_factory_kwargs": v} for k, v in method.items()},
        "npec": {k: {"visitations_factory_kwargs": v} for k, v in method.items()},
    }


@table_combined_ex.named_config
def point_maze_learned_good():
    """Compare rewards learned in PointMaze to the ground-truth reward."""
    # Analyzes models generated by `runners/transfer_point_maze.sh`.
    # SOMEDAY(adam): this ignores `log_root` and uses `serialize.get_output_dir()`
    # No way to get `log_root` in a named config due to Sacred config limitations.
    locals().update(**POINT_MAZE_LEARNED_COMMON)
    experiment_kinds = ("random", "expert", "mixture")
    config_updates = _make_visitations_config_updates(
        {
            "random": {
                "policy_type": "random",
                "policy_path": "dummy",
            },
            "expert": {
                "policy_type": "ppo2",
                "policy_path": (
                    f"{serialize.get_output_dir()}/transfer_point_maze/"
                    "expert/train/policies/final/"
                ),
            },
            "mixture": {
                "policy_type": "mixture",
                "policy_path": (
                    f"0.05:random:dummy:ppo2:{serialize.get_output_dir()}/"
                    "transfer_point_maze/expert/train/policies/final/"
                ),
            },
            "global": {"env_name": "imitation/PointMazeLeftVel-v0"},
        }
    )
    tag = "point_maze_learned"
    _ = locals()
    del _


@table_combined_ex.named_config
def point_maze_learned_pathological():
    """Compare PointMaze rewards under pathological distributions."""
    locals().update(**POINT_MAZE_LEARNED_COMMON)
    experiment_kinds = ("random_policy_permuted", "iid", "small", "wrong")
    config_updates = _make_visitations_config_updates(
        {
            "small": {
                "env_name": "evaluating_rewards/PointMaze0.01Left-v0",
                "policy_type": "random",
                "policy_path": "dummy",
            },
            "wrong": {
                "policy_type": "ppo2",
                "policy_path": (
                    f"{serialize.get_output_dir()}/train_experts/point_maze_wrong_target/"
                    "20201122_053216_fb1b0e/imitation_PointMazeLeftVel-v0/"
                    "evaluating_rewards_PointMazeWrongTarget-v0/0/policies/final"
                ),
            },
            "random_policy_permuted": {
                "env_name": "imitation/PointMazeLeftVel-v0",
                "policy_type": "random",
                "policy_path": "dummy",
            },
            "global": {
                "env_name": "imitation/PointMazeLeftVel-v0",
            },
        }
    )
    del config_updates["erc"]["random_policy_permuted"]
    named_configs = POINT_MAZE_LEARNED_COMMON["named_configs"]
    named_configs["point_maze_learned_pathological"] = {
        "epic": {
            "iid": (
                "sample_from_env_spaces",
                "dataset_iid",
            ),
            "random_policy_permuted": (
                "visitation_config",
                "dataset_permute",
            ),
        },
        "npec": {
            "iid": (
                "sample_from_env_spaces",
                "dataset_iid",
            ),
            "random_policy_permuted": (
                "visitation_config",
                "dataset_permute",
            ),
        },
    }
    skip = {
        # ERC does not support these since there are no trajectories (just transitions).
        "erc": ("iid", "random_policy_permuted")
    }
    tag = "point_maze_learned_pathological"
    _ = locals()
    del _


# TODO(adam): remove these two following configs
@table_combined_ex.named_config
def pathological_first():
    experiment_kinds = (  # noqa: F841  pylint:disable=unused-variable
        "random_policy_permuted",
        "iid",
    )


@table_combined_ex.named_config
def pathological_second():
    experiment_kinds = ("small", "wrong")  # noqa: F841  pylint:disable=unused-variable


@table_combined_ex.named_config
def high_precision():
    named_configs = {  # noqa: F841  pylint:disable=unused-variable
        "precision": {"global": ("high_precision",)}
    }


@table_combined_ex.named_config
def test():
    """Simple, quick config for unit testing."""
    experiment_kinds = ("test",)
    target_reward_type = "evaluating_rewards/PointMassGroundTruth-v0"
    target_reward_path = "dummy"
    named_configs = {
        "test": {"global": ("test",)},
        # duplicate to get some coverage of recursive_dict_merge
        "test2": {"global": ("test",)},
    }
    pretty_models = {
        "GT": ("evaluating_rewards/PointMassGroundTruth-v0", "dummy"),
        "SparseCtrl": ("evaluating_rewards/PointMassSparseWithCtrl-v0", "dummy"),
        "SparseNoCtrl": ("evaluating_rewards/PointMassSparseNoCtrl-v0", "dummy"),
        "DenseCtrl": ("evaluating_rewards/PointMassDenseWithCtrl-v0", "dummy"),
        "DenseNoCtrl": ("evaluating_rewards/PointMassDenseNoCtrl-v0", "dummy"),
    }
    _ = locals()
    del _


@table_combined_ex.named_config
def epic_only():
    distance_kinds = ("epic",)  # noqa: F841  pylint:disable=unused-variable


@table_combined_ex.named_config
def npec_only():
    distance_kinds = ("npec",)  # noqa: F841  pylint:disable=unused-variable


@table_combined_ex.named_config
def erc_only():
    distance_kinds = ("erc",)  # noqa: F841  pylint:disable=unused-variable


@table_combined_ex.named_config
def quick():
    named_configs = {  # noqa: F841  pylint:disable=unused-variable
        "precision": {"global": ("test",)}
    }


K = TypeVar("K")


def common_keys(vals: Iterable[Mapping[K, Any]]) -> Sequence[K]:
    first = next(iter(vals)).keys()
    res = set(first)
    for v in vals:
        res = res.intersection(v.keys())
    return [k for k in first if k in res]  # preserve order


def make_table(
    key: str,
    vals: Mapping[Tuple[str, str], pd.Series],
    pretty_models: Mapping[str, common_config.RewardCfg],
    distance_kinds: Tuple[str],
    experiment_kinds: Tuple[str],
) -> str:
    """Generate LaTeX table.

    Args:
        key: Key describing where the data comes from. This is used to change formatting options.
        vals: A Mapping from (distance, visitation) to a Series of values.
        pretty_models: A Mapping from short-form ("pretty") labels to reward configurations.
            A model matching that reward configuration is given the associated short label.
        distance_kinds: the distance metrics to compare with.
        experiment_kinds: different subsets of data to plot, e.g. visitation distributions.
    """
    y_reward_cfgs = common_keys(vals.values())

    rows = []
    for model in y_reward_cfgs:
        cols = []
        kind, path = model
        label = None

        for search_label, (search_kind, search_path) in pretty_models.items():
            if kind == search_kind and path.endswith(search_path):
                assert label is None
                label = search_label
        assert label is not None
        row = f"{label} & "
        for distance, visitation in itertools.product(distance_kinds, experiment_kinds):
            k = (distance, visitation)
            if k in vals:
                col = vals[k].loc[model]
                multiplier = 100 if key.endswith("relative") else 1000
                col = f"{col * multiplier:.4g}"
            else:
                col = "---"
            cols.append(col)
        row += r"\resultrow{" + "}{".join(cols) + "}"
        rows.append(row)
    rows.append("")
    return " \\\\\n".join(rows)


@table_combined_ex.capture
def _input_validation(
    experiments: Mapping[str, sacred.Experiment],
    experiment_kinds: Tuple[str],
    distance_kinds: Tuple[str],
    config_updates: Mapping[str, Any],
    named_configs: Mapping[str, Mapping[str, Any]],
    skip: Mapping[str, Mapping[str, bool]],
):
    """Validate input.

    See `table_combined` for args definition."""
    if not experiment_kinds:
        raise ValueError("Empty `experiment_kinds`.")
    if not distance_kinds:
        raise ValueError("Empty `distance_kinds`.")

    for ex_key in experiments.keys():
        for kind in experiment_kinds:
            skipped = kind in skip.get(ex_key, ())
            update_local = config_updates.get(ex_key, {}).get(kind, {})
            named_local = named_configs.get(ex_key, {}).get(kind, ())
            configured = update_local or named_local

            if configured and skipped:
                raise ValueError(f"Skipping ({ex_key}, {kind}) that is configured.")
            if not configured and not skipped:
                raise ValueError(f"({ex_key}, {kind}) unconfigured but not skipped.")


@table_combined_ex.main
def table_combined(
    vals_path: Optional[str],
    log_dir: str,
    distance_kinds: Tuple[str],
    experiment_kinds: Tuple[str],
    config_updates: Mapping[str, Any],
    named_configs: Mapping[str, Mapping[str, Any]],
    skip: Mapping[str, Mapping[str, bool]],
    target_reward_type: str,
    target_reward_path: str,
    pretty_models: Mapping[str, common_config.RewardCfg],
) -> None:
    """Entry-point into CLI script.

    Args:
        vals_path: path to precomputed values to tabulate. Skips everything but table generation
            if specified. This is useful for regenerating tables in a new style from old data.
        log_dir: directory to write figures and other logging to.
        distance_kinds: the distance metrics to compare with.
        experiment_kinds: different subsets of data to plot, e.g. visitation distributions.
        config_updates: Config updates to apply. Hierarchically specified by algorithm and
            experiment kind. "global" may be specified at top-level (applies to all algorithms)
            or at first-level (applies to particular algorithm, all experiment kinds).
        named_configs: Named configs to apply. First key is a namespace which has no semantic
            meaning, but should be unique for each Sacred config scope. Second key is the algorithm
            scope and third key the experiment kind, like with config_updates. Values at the leaf
            are tuples of named configs. The dicts across namespaces are recursively merged
            using `recursive_dict_merge`.
        skip: If `skip[ex_key][kind]` is True, then skip that experiment (e.g. if a metric
            does not support a particular configuration).
        target_reward_type: The target reward type to output distance from in the table;
            others are ignored.
        target_reward_path: The target reward path to output distance from in the table;
            others are ignored.
        pretty_models: A Mapping from short-form ("pretty") labels to reward configurations.
            A model matching that reward configuration has the associated short label.
    """
    experiments = {
        "npec": npec.npec_distance_ex,
        "epic": epic.epic_distance_ex,
        "erc": erc.erc_distance_ex,
    }
    experiments = {k: experiments[k] for k in distance_kinds}

    # Merge named_configs. We have a faux top-level layer to workaround Sacred being unable to
    # have named configs build on top of each others definitions in a particular order.
    named_configs = [copy.deepcopy(cfg) for cfg in named_configs.values()]
    named_configs = functools.reduce(script_utils.recursive_dict_merge, named_configs)

    _input_validation(  # pylint:disable=no-value-for-parameter
        experiments,
        experiment_kinds,
        distance_kinds,
        named_configs=named_configs,
    )

    if vals_path is not None:
        with open(vals_path, "rb") as f:
            vals = pickle.load(f)
    else:
        runs = {}
        for ex_key, ex in experiments.items():
            for kind in experiment_kinds:
                if kind in skip.get(ex_key, ()):
                    logging.info(f"Skipping ({ex_key}, {kind})")
                    continue

                local_updates = [
                    config_updates.get("global", {}),
                    config_updates.get(ex_key, {}).get("global", {}),
                    config_updates.get(ex_key, {}).get(kind, {}),
                ]
                local_updates = [copy.deepcopy(cfg) for cfg in local_updates]
                local_updates = functools.reduce(
                    functools.partial(script_utils.recursive_dict_merge, overwrite=True),
                    local_updates,
                )
                local_updates["log_dir"] = os.path.join(log_dir, ex_key, kind)

                local_named = tuple(named_configs.get("global", ()))
                local_named += tuple(named_configs.get(ex_key, {}).get("global", ()))
                local_named += tuple(named_configs.get(ex_key, {}).get(kind, ()))

                print(f"Running ({ex_key}, {kind}): {local_updates} plus {local_named}")
                runs[(ex_key, kind)] = ex.run(
                    config_updates=local_updates, named_configs=local_named
                )
        vals = {k: run.result for k, run in runs.items()}

        with open(os.path.join(log_dir, "vals.pkl"), "wb") as f:
            pickle.dump(vals, f)

    # TODO(adam): how to get generator reward? that might be easiest as side-channel.
    # or separate script, which you could potentially combine here.
    vals_filtered = {}
    for model_key, outer_val in vals.items():
        for table_key, inner_val in outer_val.items():
            inner_val = aggregated.oned_mapping_to_series(inner_val)
            vals_filtered.setdefault(table_key, {})[model_key] = inner_val.xs(
                key=(target_reward_type, target_reward_path),
                level=("target_reward_type", "target_reward_path"),
            )

    for k in common_keys(vals.values()):
        v = vals_filtered[k]
        path = os.path.join(log_dir, f"{k}.csv")
        logger.info(f"Writing table to '{path}'")
        with open(path, "wb") as f:
            table = make_table(k, v, pretty_models, distance_kinds, experiment_kinds)
            f.write(table.encode())


if __name__ == "__main__":
    script_utils.experiment_main(table_combined_ex, "table_combined")
