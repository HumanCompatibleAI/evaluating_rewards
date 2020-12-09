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

"""CLI script to analyse combined EPIC, NPEC and ERC distances from a reward model.

Can output a table (all cases), or a lineplot (for timeseries over checkpoints)."""

import copy
import functools
import glob
import logging
import os
import pickle
import re
from typing import Any, Callable, Iterable, Mapping, Sequence, Tuple, TypeVar

from imitation.util import util as imit_util
import matplotlib.pyplot as plt
import pandas as pd
import sacred
import seaborn as sns

from evaluating_rewards import serialize
from evaluating_rewards.analysis import results, stylesheets, visualize
from evaluating_rewards.analysis.distances import aggregated
from evaluating_rewards.distances import common_config
from evaluating_rewards.scripts import script_utils
from evaluating_rewards.scripts.distances import epic, erc, npec

Vals = Mapping[Tuple[str, str], Any]
ValsFiltered = Mapping[str, Mapping[Tuple[str, str], pd.Series]]

combined_ex = sacred.Experiment("combined")
logger = logging.getLogger("evaluating_rewards.analysis.distances.combined")


@combined_ex.config
def default_config():
    """Default configuration for combined."""
    vals_paths = []
    log_root = serialize.get_output_dir()  # where results are read from/written to
    distance_kinds = ("epic", "npec", "erc")
    experiment_kinds = ()
    config_updates = {}  # config updates applied to all subcommands
    named_configs = {}
    skip = {}
    target_reward_type = None
    target_reward_path = None
    pretty_models = {}
    # Output formats
    output_fn = latex_table
    styles = ["paper", "tex"]
    tag = "default"
    _ = locals()
    del _


@combined_ex.config
def logging_config(log_root, tag):
    """Default logging configuration: hierarchical directory structure based on config."""
    log_dir = os.path.join(  # noqa: F841  pylint:disable=unused-variable
        log_root,
        "combined",
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
        r"\bettergoalmethod{}": ("evaluating_rewards/PointMazeBetterGoalWithCtrl-v0", "dummy"),
        r"\regressionmethod{}": (
            "evaluating_rewards/RewardModel-v0",
            r"(.*/)?transfer_point_maze(_fast)?/reward/regress/checkpoints/(final|[0-9]+)",
        ),
        r"\preferencesmethod{}": (
            "evaluating_rewards/RewardModel-v0",
            "(.*/)?transfer_point_maze(_fast)?/reward/preferences/checkpoints/(final|[0-9]+)",
        ),
        r"\airlstateonlymethod{}": (
            "imitation/RewardNet_unshaped-v0",
            "(.*/)?transfer_point_maze(_fast)?/reward/irl_state_only/checkpoints/(final|[0-9]+)"
            "/discrim/reward_net",
        ),
        r"\airlstateactionmethod{}": (
            "imitation/RewardNet_unshaped-v0",
            "(.*/)?transfer_point_maze(_fast)?/reward/irl_state_action/checkpoints/(final|[0-9]+)"
            "/discrim/reward_net",
        ),
    },
}


def _make_visitations_config_updates(method):
    return {
        "epic": {k: {"visitations_factory_kwargs": v} for k, v in method.items()},
        "erc": {k: {"trajectory_factory_kwargs": v} for k, v in method.items()},
        "npec": {k: {"visitations_factory_kwargs": v} for k, v in method.items()},
    }


_POINT_MAZE_EXPERT = (
    f"{serialize.get_output_dir()}/train_experts/ground_truth/20201203_105631_297835/"
    "imitation_PointMazeLeftVel-v0/evaluating_rewards_PointMazeGroundTruthWithCtrl-v0/best/"
)


@combined_ex.named_config
def point_maze_learned_good():
    """Compare rewards learned in PointMaze to the ground-truth reward.

    Use sensible ("good") visitation distributions.
    """
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
                "policy_path": _POINT_MAZE_EXPERT,
            },
            "mixture": {
                "policy_type": "mixture",
                "policy_path": f"0.05:random:dummy:ppo2:{_POINT_MAZE_EXPERT}",
            },
            "global": {"env_name": "imitation/PointMazeLeftVel-v0"},
        }
    )
    tag = "point_maze_learned"
    _ = locals()
    del _


@combined_ex.named_config
def point_maze_learned_pathological():
    """Compare PointMaze rewards under pathological distributions."""
    locals().update(**POINT_MAZE_LEARNED_COMMON)
    experiment_kinds = ("random_policy_permuted", "iid", "small", "wrong")
    config_updates = _make_visitations_config_updates(
        {
            "random_policy_permuted": {
                "policy_type": "random",
                "policy_path": "dummy",
            },
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
            "global": {
                "env_name": "imitation/PointMazeLeftVel-v0",
            },
        }
    )
    del config_updates["erc"]["random_policy_permuted"]
    named_configs = POINT_MAZE_LEARNED_COMMON["named_configs"]
    named_configs["point_maze_learned_pathological"] = {
        k: {
            "iid": (
                "sample_from_env_spaces",
                "dataset_iid",
            ),
            "random_policy_permuted": (
                "visitation_config",
                "dataset_permute",
            ),
        }
        for k in ("epic", "npec")
    }
    skip = {
        # ERC does not support these since there are no trajectories (just transitions).
        "erc": ("iid", "random_policy_permuted")
    }
    tag = "point_maze_learned_pathological"
    _ = locals()
    del _


@combined_ex.named_config
def point_maze_checkpoints():
    """Compare rewards learned in PointMaze to the ground-truth reward over time.

    Use sensible ("good") visitation distributions.
    """
    # Analyzes models generated by `runners/transfer_point_maze.sh`.
    # SOMEDAY(adam): this ignores `log_root` and uses `serialize.get_output_dir()`
    # No way to get `log_root` in a named config due to Sacred config limitations.
    locals().update(**POINT_MAZE_LEARNED_COMMON)
    named_configs = {
        "point_maze_learned": {
            "global": ("point_maze_checkpoints",),
        }
    }
    experiment_kinds = ("mixture",)
    config_updates = _make_visitations_config_updates(
        {
            "mixture": {
                "policy_type": "mixture",
                "policy_path": f"0.05:random:dummy:ppo2:{_POINT_MAZE_EXPERT}",
            },
            "global": {"env_name": "imitation/PointMazeLeftVel-v0"},
        }
    )
    tag = "point_maze_checkpoints"
    output_fn = distance_over_time
    _ = locals()
    del _


@combined_ex.named_config
def high_precision():
    named_configs = {  # noqa: F841  pylint:disable=unused-variable
        "precision": {
            "global": ("high_precision",),
        }
    }


@combined_ex.named_config
def test():
    """Simple, quick config for unit testing."""
    experiment_kinds = ("test",)
    target_reward_type = "evaluating_rewards/PointMassGroundTruth-v0"
    target_reward_path = "dummy"
    named_configs = {
        "test": {"global": ("test",)},
        # duplicate to get some coverage of recursive_dict_merge
        "test2": {"global": ("test",)},
        "test3": {
            k: {
                "test": ("test",),
            }
            for k in ("epic", "npec", "erc")
        },
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


@combined_ex.named_config
def epic_only():
    distance_kinds = ("epic",)  # noqa: F841  pylint:disable=unused-variable


@combined_ex.named_config
def npec_only():
    distance_kinds = ("npec",)  # noqa: F841  pylint:disable=unused-variable


@combined_ex.named_config
def erc_only():
    distance_kinds = ("erc",)  # noqa: F841  pylint:disable=unused-variable


@combined_ex.named_config
def fast():
    named_configs = {  # noqa: F841  pylint:disable=unused-variable
        "precision": {"global": ("fast",)}
    }


K = TypeVar("K")


def common_keys(vals: Iterable[Mapping[K, Any]]) -> Sequence[K]:
    first = next(iter(vals)).keys()
    res = set(first)
    for v in vals:
        res = res.intersection(v.keys())
    return [k for k in first if k in res]  # preserve order


def _fixed_width_format(x: float, figs: int = 3) -> str:
    """Format x as a number targeting `figs+1` characters.

    This is intended for cramming as much information as possible in a fixed-width
    format. If `x >= 10 ** figs`, then we format it as an integer. Note this will
    use more than `figs` characters if `x >= 10 ** (figs+1)`. Otherwise, we format
    it as a float with as many significant figures as we can fit into the space.
    If `x < 10 ** (-figs + 1)`, then we represent it as "<"+str(10 ** (-figs + 1)),
    unless `x == 0` in which case we format `x` as "0" exactly.

    Args:
        x: The number to format. The code assumes this is non-negative; the return
            value may exceed the character target if it is negative.
        figs: The number of digits to target.

    Returns:
        The number formatted as described above.
    """
    smallest_representable = 10 ** (-figs + 1)
    if 0 < x < 10 ** (-figs + 1):
        return "<" + str(smallest_representable)

    raw_repr = str(x).replace(".", "")
    num_leading_zeros = 0
    for digit in raw_repr:
        if digit == "0":
            num_leading_zeros += 1
        else:
            break
    if x >= 10 ** figs:
        # No decimal point gives us an extra character to use
        figs += 1
    fstr = "{:." + str(max(0, figs - num_leading_zeros)) + "g}"
    res = fstr.format(x)

    if "." in res:
        delta = (figs + 1) - len(res)
        if delta > 0:  # g drops trailing zeros, add them back
            res += "0" * delta

    return res


def _pretty_label(
    cfg: common_config.RewardCfg, pretty_models: Mapping[str, common_config.RewardCfg]
) -> str:
    """Map `cfg` to a more readable label in `pretty_models`.

    Raises:
        ValueError if `cfg` does not match any label in `pretty_models`.
    """
    kind, path = cfg
    label = None
    for search_label, (search_kind, search_pattern) in pretty_models.items():
        if kind == search_kind and re.match(search_pattern, path):
            assert label is None
            label = search_label
    if label is None:
        raise ValueError(f"Did not find '{cfg}' in '{pretty_models}'")
    return label


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
        distance_kinds: The distance metrics to compare with.
        experiment_kinds: Different subsets of data to plot, e.g. visitation distributions.
    """
    y_reward_cfgs = common_keys(vals.values())

    rows = []
    for model in y_reward_cfgs:
        cols = []
        label = _pretty_label(model, pretty_models)
        row = f"{label} & & "
        for distance in distance_kinds:
            for visitation in experiment_kinds:
                k = (distance, visitation)
                if k in vals:
                    val = vals[k].loc[model]
                    multiplier = 100 if key.endswith("relative") else 1000
                    val = val * multiplier
                    # Fit as many SFs as we can into 4 characters

                    col = _fixed_width_format(val)
                    try:
                        float(col)
                        # If we're here, then col is numeric
                        col = "\\num{" + col + "}"
                    except ValueError:
                        pass
                else:
                    col = "---"
                cols.append(col)
            cols.append("")  # spacer between distance metric groups
        row += " & ".join(cols[:-1])
        rows.append(row)
    rows.append("")
    return " \\\\\n".join(rows)


@combined_ex.capture
def _input_validation(
    experiments: Mapping[str, sacred.Experiment],
    experiment_kinds: Tuple[str],
    distance_kinds: Tuple[str],
    config_updates: Mapping[str, Any],
    named_configs: Mapping[str, Mapping[str, Any]],
    skip: Mapping[str, Mapping[str, bool]],
):
    """Validate input.

    See `combined` for args definition."""
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


def load_vals(vals_paths: Sequence[str]) -> Vals:
    """Loads and combines values from vals_path, recursively searching in subdirectories."""
    pickle_paths = []
    for path in vals_paths:
        if os.path.isdir(path):
            nested_paths = glob.glob(os.path.join(path, "**", "vals.pkl"), recursive=True)
            if not nested_paths:
                raise ValueError(f"No 'vals.pkl' files found in {path}")
            pickle_paths += nested_paths
        else:
            pickle_paths.append(path)

    vals = {}
    keys_to_path = {}
    for path in pickle_paths:
        with open(path, "rb") as f:
            val = pickle.load(f)
        for k, v in val.items():
            keys_to_path.setdefault(k, []).append(path)
            if k in vals:
                logger.info(f"Duplicate key {k} present in {keys_to_path[k]}")
            else:
                vals[k] = v

    return vals


@combined_ex.capture
def compute_vals(
    experiments: Mapping[str, sacred.Experiment],
    experiment_kinds: Tuple[str],
    config_updates: Mapping[str, Any],
    named_configs: Mapping[str, Mapping[str, Any]],
    skip: Mapping[str, Mapping[str, bool]],
    log_dir: str,
) -> Vals:
    """
    Run experiments to compute distance values.

    Args:
        experiments: Mapping from an experiment kind to a sacred.Experiment to run.
        experiment_kinds: Different subsets of data to plot, e.g. visitation distributions.
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
        log_dir: The directory to write tables and other logging to.
    """
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

            if "log_dir" in local_updates:
                raise ValueError("Cannot override `log_dir`.")
            local_updates["log_dir"] = os.path.join(log_dir, ex_key, kind)

            local_named = tuple(named_configs.get("global", ()))
            local_named += tuple(named_configs.get(ex_key, {}).get("global", ()))
            local_named += tuple(named_configs.get(ex_key, {}).get(kind, ()))

            logger.info(f"Running ({ex_key}, {kind}): {local_updates} plus {local_named}")
            runs[(ex_key, kind)] = ex.run(config_updates=local_updates, named_configs=local_named)
    return {k: run.result for k, run in runs.items()}


def _canonicalize_cfg(cfg: common_config.RewardCfg) -> common_config.RewardCfg:
    kind, path = cfg
    return kind, results.canonicalize_data_root(path)


@combined_ex.capture
def filter_values(
    vals: Vals,
    target_reward_type: str,
    target_reward_path: str,
) -> ValsFiltered:
    """
    Extract values for the target reward from `vals`.

    Args:
        target_reward_type: The target reward type to output distance from in the table;
            others are ignored.
        target_reward_path: The target reward path to output distance from in the table;
            others are ignored.

    Returns:
        The subset of values in `vals` corresponding to the target, converted to pd.Series.
        Nested dictionary. Outer key corresponds to the table kind (e.g. `bootstrap_lower`,
        `studentt_middle`). Inner key corresponds to the comparison kind (e.g. EPIC with
        a particular visitation distribution).

    """
    vals_filtered = {}
    for model_key, outer_val in vals.items():
        for table_key, inner_val in outer_val.items():
            inner_val = {
                (_canonicalize_cfg(target), _canonicalize_cfg(source)): v
                for (target, source), v in inner_val.items()
            }
            inner_val = aggregated.oned_mapping_to_series(inner_val)
            vals_filtered.setdefault(table_key, {})[model_key] = inner_val.xs(
                key=(target_reward_type, target_reward_path),
                level=("target_reward_type", "target_reward_path"),
            )
    return vals_filtered


@combined_ex.capture
def latex_table(
    vals_filtered: ValsFiltered,
    pretty_models: Mapping[str, common_config.RewardCfg],
    log_dir: str,
    distance_kinds: Tuple[str],
    experiment_kinds: Tuple[str],
) -> None:
    """
    Writes tables of data from `vals_filtered`.

    Args:
        vals_filtered: Filtered values returned by `filter_values`.
        pretty_models: A Mapping from short-form ("pretty") labels to reward configurations.
            A model matching that reward configuration has the associated short label.

    For other arguments, see `combined`.
    """
    for k, v in vals_filtered.items():
        v = vals_filtered[k]
        path = os.path.join(log_dir, f"{k}.csv")
        logger.info(f"Writing table to '{path}'")
        with open(path, "wb") as f:
            table = make_table(k, v, pretty_models, distance_kinds, experiment_kinds)
            f.write(table.encode())


def _checkpoint_to_progress(df: pd.DataFrame) -> pd.DataFrame:
    ckpts = df["Checkpoint"].astype("int")
    if len(ckpts) == 1:
        progress = ckpts * 0.0
    else:
        progress = ckpts * 100 / ckpts.max()

    return progress


def _add_label_and_progress(
    s: pd.Series, pretty_models: Mapping[str, common_config.RewardCfg]
) -> pd.DataFrame:
    """Add pretty label and checkpoint progress to reward distances."""
    labels = s.index.map(functools.partial(_pretty_label, pretty_models=pretty_models))
    # TODO(adam): get LaTeX labels to work.
    df = s.reset_index(name="Distance")

    regex = ".*/checkpoints/(?P<Checkpoint>final|[0-9]+)(?:/.*)?$"
    match = df["source_reward_path"].str.extract(regex)
    match["Label"] = labels

    grp = match.groupby("Label")
    progress = grp.apply(_checkpoint_to_progress)
    progress = progress.reset_index("Label", drop=True)
    df["Progress"] = progress
    df["Label"] = labels

    return df


def _timeseries_distances(
    vals: Mapping[Tuple[str, str], pd.Series], pretty_models: Mapping[str, common_config.RewardCfg]
) -> pd.DataFrame:
    """Merge vals into a single DataFrame, adding label and progress."""
    vals = {k: _add_label_and_progress(v, pretty_models) for k, v in vals.items()}
    df = pd.concat(vals, names=("Algorithm", "Distribution", "Original"))
    df = df.reset_index().drop(columns=["Original"])
    df["Algorithm"] = df["Algorithm"].str.upper()
    return df


class CustomCILinePlotter(sns.relational._LinePlotter):  # pylint:disable=protected-access
    """
    LinePlotter supporting custom confidence interval width.

    This is unfortunately entangled with seaborn internals so may break with seaborn upgrades.
    """

    def __init__(self, lower, upper, **kwargs):
        super().__init__(**kwargs)
        self.lower = lower
        self.upper = upper
        self.estimator = "dummy"

    def aggregate(self, vals, grouper, units=None):
        y_ci = pd.DataFrame(
            {
                "low": self.lower.loc[vals.index, "Distance"],
                "high": self.upper.loc[vals.index, "Distance"],
            }
        )
        return grouper, vals, y_ci


@combined_ex.capture
def distance_over_time(
    vals_filtered: ValsFiltered,
    pretty_models: Mapping[str, common_config.RewardCfg],
    log_dir: str,
    styles: Iterable[str],
    prefix: str = "bootstrap",
) -> None:
    """
    Plots timeseries of distances.

    Only works with certain configs, like `point_maze_checkpoints`.
    """
    lower = _timeseries_distances(vals_filtered[f"{prefix}_lower"], pretty_models)
    mid = _timeseries_distances(vals_filtered[f"{prefix}_middle"], pretty_models)
    upper = _timeseries_distances(vals_filtered[f"{prefix}_upper"], pretty_models)

    with stylesheets.setup_styles(styles):
        fig, ax = plt.subplots(1, 1)
        variables = sns.relational._LinePlotter.get_semantics(  # pylint:disable=protected-access
            dict(x="Progress", y="Distance", hue="Label", style="Algorithm", size=None, units=None),
        )
        plotter = CustomCILinePlotter(
            variables=variables,
            data=mid,
            lower=lower,
            upper=upper,
            legend="auto",
        )
        plotter.map_hue(palette=None, order=None, norm=None)  # pylint:disable=no-member
        plotter.map_size(sizes=None, order=None, norm=None)  # pylint:disable=no-member
        plotter.map_style(markers=True, dashes=True, order=None)  # pylint:disable=no-member
        plotter._attach(ax)  # pylint:disable=protected-access
        plotter.plot(ax, {})

        plt.xlabel("Training Progress (%)")
        plt.ylabel("Distance")

        visualize.save_fig(os.path.join(log_dir, "timeseries"), fig)


@combined_ex.main
def combined(
    vals_paths: Sequence[str],
    log_dir: str,
    distance_kinds: Tuple[str],
    experiment_kinds: Tuple[str],
    named_configs: Mapping[str, Mapping[str, Any]],
    output_fn: Callable[[ValsFiltered], None],
) -> None:
    """Entry-point into CLI script.

    Args:
        vals_paths: Paths to precomputed values to tabulate. Skips everything but table generation
            if non-empty. This is useful for regenerating tables in a new style from old data,
            including combining results from multiple previous runs.
        log_dir: The directory to write tables and other logging to.
        distance_kinds: The distance metrics to compare with.
        experiment_kinds: Different subsets of data to plot, e.g. visitation distributions.
        named_configs: Named configs to apply. First key is a namespace which has no semantic
            meaning, but should be unique for each Sacred config scope. Second key is the algorithm
            scope and third key the experiment kind, like with config_updates. Values at the leaf
            are tuples of named configs. The dicts across namespaces are recursively merged
            using `recursive_dict_merge`.
        output_fn: Function to call to generate saved output.
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

    if vals_paths:
        vals = load_vals(vals_paths)
    else:
        vals = compute_vals(  # pylint:disable=no-value-for-parameter
            experiments=experiments, named_configs=named_configs
        )

        with open(os.path.join(log_dir, "vals.pkl"), "wb") as f:
            pickle.dump(vals, f)

    # TODO(adam): how to get generator reward? that might be easiest as side-channel.
    # or separate script, which you could potentially combine here.
    vals_filtered = filter_values(vals)  # pylint:disable=no-value-for-parameter

    output_fn(vals_filtered)


if __name__ == "__main__":
    script_utils.experiment_main(combined_ex, "combined")
